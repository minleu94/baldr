"""推薦決策的純 staged evaluator contracts。

Evaluator 本身不讀取資料。每一檔候選在當前 gate 通過後至多要求一種
SourceFact；app 只能在該步讀取，並用原 request 回填。分數在 app 邊界轉成
Decimal/int 與舊 quantile basis points；此模組不接觸 legacy 浮點 sidecar。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256

from decision_module.recommendation.contracts import (
    CandidateAssessment,
    DecisionBatch,
    FilterOutcome,
    RecommendationItem,
)
from decision_module.recommendation.evaluation_constants import (
    MINIMUM_RECOMMENDATION_HISTORY_ROWS,
)
from decision_module.recommendation_percentile_ranker import (
    calculate_score_percentiles,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonResult,
    ReplayComparisonOperand,
    ReplayComparisonValue,
    ReplayComparisonKind,
    ReplayComparisonOperator,
    ReplayCompatibilityCandidateKeyV1,
    ReplayCompatibilityPrefilterObservationsV1,
    ReplayCompatibilityPreflightOutcomeV1,
    ReplayFastFilterPolicyV1,
    ReplayHistoryPreflightV1,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayPrefilterFactKind,
    ReplayPrefilterObservations,
    ReplayPrefilterObservationV1,
    ReplayPreflightDisposition,
    ReplayPreflightOutcome,
    ReplayPreflightStage,
    ReplayThreshold,
    ReplayThresholdStatus,
    ReplayThresholdMetricProjection,
    ReplayVolumeThresholdKind,
    ReplayVolumeThresholdV1,
    compare_replay_operands_with_status,
    evaluate_replay_history_preflight,
    evaluate_replay_prefilter,
)
from decision_module.recommendation.replay_policy import (
    ReplayExecutionPolicyV1,
    ReplayScoreOrderingKindV1,
    ReplayScoreOrderingV1,
)


DecisionNumber = Decimal | int | str


class SourceFactKind(str, Enum):
    PE = "pe"
    MONTHLY_REVENUE = "monthly_revenue"
    INDUSTRY_CONTEXT = "industry_context"


class IndustryChangeSourceKind(str, Enum):
    """Compatibility-relevant source representation for industry change."""

    UNAVAILABLE = "unavailable"
    LEGACY_FLOAT = "legacy_float"
    LEGACY_DECIMAL = "legacy_decimal"
    INTEGER = "integer"
    LEGACY_INTEGER_OVERFLOW = "legacy_integer_overflow"
    FALLBACK_ZERO = "fallback_zero"
    UNSUPPORTED = "unsupported"


class CandidateStage(str, Enum):
    READY = "ready"
    WAITING_FOR_PE = "waiting_for_pe"
    PE_RECEIVED = "pe_received"
    WAITING_FOR_MONTHLY_REVENUE = "waiting_for_monthly_revenue"
    MONTHLY_REVENUE_RECEIVED = "monthly_revenue_received"
    WAITING_FOR_INDUSTRY_CONTEXT = "waiting_for_industry_context"
    INDUSTRY_CONTEXT_RECEIVED = "industry_context_received"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class RecommendationEvaluationPolicy:
    """app 由不可變 run snapshot 投影的決策政策。"""

    invocation_id: str
    decision_date: date | None
    decision_date_text: str
    pe_ratio_max: Decimal | None = None
    monthly_revenue_yoy_min: Decimal | None = None
    volume_change_min_percent: Decimal | None = None
    industry_context_required: bool = False
    threshold_mode: str = "fixed"
    top_n: int = 50
    minimum_percentile_bp: int | None = None
    minimum_universe_size: int | None = None
    ranking_method: str = "fixed"
    eligible_universe_date: date | None = None

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.decision_date_text) is not str:
            raise TypeError("decision_date_text 必須是 str")
        if self.decision_date is not None and type(self.decision_date) is not date:
            raise TypeError("decision_date 必須是 date 或 None")
        if (
            self.eligible_universe_date is not None
            and type(self.eligible_universe_date) is not date
        ):
            raise TypeError("eligible_universe_date 必須是 date 或 None")
        for name in (
            "pe_ratio_max",
            "monthly_revenue_yoy_min",
            "volume_change_min_percent",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not Decimal:
                raise TypeError(f"{name} 必須是 Decimal 或 None")
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} 必須是有限 Decimal")
        if type(self.industry_context_required) is not bool:
            raise TypeError("industry_context_required 必須是 bool")
        if self.threshold_mode not in {"fixed", "quantile"}:
            raise ValueError("threshold_mode 必須是 fixed 或 quantile")
        if type(self.top_n) is not int or self.top_n < 0:
            raise ValueError("top_n 必須是非負整數")
        if self.threshold_mode == "quantile":
            if (
                type(self.minimum_percentile_bp) is not int
                or not 0 <= self.minimum_percentile_bp <= 10_000
            ):
                raise ValueError("minimum_percentile_bp 必須介於 0 到 10000")
            if (
                type(self.minimum_universe_size) is not int
                or self.minimum_universe_size < 2
            ):
                raise ValueError("minimum_universe_size 必須至少為 2")
            if self.ranking_method != "nearest_rank":
                raise ValueError("quantile ranking_method 必須是 nearest_rank")
        elif (
            self.minimum_percentile_bp is not None
            or self.minimum_universe_size is not None
            or self.ranking_method != "fixed"
        ):
            raise ValueError("fixed policy 不接受 quantile 設定")


@dataclass(frozen=True, slots=True)
class RecommendationScore:
    """由 app 數值邊界投影的無浮點 canonical 排名值。

    ordering_value 保持原 float 的精確 IEEE 值所對應的 Decimal、原 Decimal/int，
    或經 Decimal 驗證的原始數字字串；最後一種保留舊 Python 字串排序行為。
    quantile_score_bp 由 app 對原始值呼叫舊 quantizer 後傳入，避免改變半點規則。
    """

    ordering_value: DecisionNumber
    quantile_score_bp: int | None = None

    def __post_init__(self) -> None:
        if type(self.ordering_value) not in (Decimal, int, str):
            raise TypeError("ordering_value 僅接受 Decimal、int 或數字字串")
        if type(self.ordering_value) is Decimal and not self.ordering_value.is_finite():
            raise ValueError("ordering_value 必須有限")
        if type(self.ordering_value) is str:
            try:
                parsed_value = Decimal(self.ordering_value)
            except InvalidOperation as exc:
                raise ValueError("ordering_value 必須是有效數字字串") from exc
            if not parsed_value.is_finite():
                raise ValueError("ordering_value 必須有限")
        if self.quantile_score_bp is not None:
            if (
                type(self.quantile_score_bp) is not int
                or not 0 <= self.quantile_score_bp <= 10_000
            ):
                raise ValueError("quantile_score_bp 必須介於 0 到 10000")


@dataclass(frozen=True, slots=True)
class NeedSourceFact:
    """唯一待讀 fact；request_id 將 invocation、候選、日期和 fact kind 綁定。"""

    request_id: str
    invocation_id: str
    kind: SourceFactKind
    stock_code: str
    decision_date: date

    def __post_init__(self) -> None:
        for name in ("request_id", "invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.kind) is not SourceFactKind:
            raise TypeError("kind 必須是 SourceFactKind")
        if type(self.decision_date) is not date:
            raise TypeError("decision_date 必須是 date")


@dataclass(frozen=True, slots=True)
class PEFact:
    value: Decimal | None
    available_date: date | None
    as_of_date: date | None = None
    source: str | None = None
    source_version: str | None = None
    quality_literal: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None:
            if type(self.value) is not Decimal:
                raise TypeError("PE value 必須是 Decimal 或 None")
        if self.available_date is not None and type(self.available_date) is not date:
            raise TypeError("PE available_date 必須是 date 或 None")
        if self.as_of_date is not None and type(self.as_of_date) is not date:
            raise TypeError("PE as_of_date 必須是 date 或 None")
        for name in ("source", "source_version", "quality_literal"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} 必須是 str 或 None")


@dataclass(frozen=True, slots=True)
class MonthlyRevenueFact:
    period: str
    available_date: date
    source_version: str
    revenue: Decimal
    source: str = "unknown"
    quality_literal: str | None = None

    def __post_init__(self) -> None:
        if type(self.period) is not str or len(self.period) != 7 or self.period[4] != "-":
            raise ValueError("period 必須採 YYYY-MM")
        try:
            year = int(self.period[:4])
            month = int(self.period[5:])
        except ValueError as exc:
            raise ValueError("period 必須採 YYYY-MM") from exc
        if year < 1 or not 1 <= month <= 12:
            raise ValueError("period 必須是有效年月")
        if type(self.available_date) is not date:
            raise TypeError("available_date 必須是 date")
        if type(self.source_version) is not str or not self.source_version.strip():
            raise ValueError("source_version 不可為空")
        if type(self.revenue) is not Decimal:
            raise TypeError("revenue 必須是 Decimal")
        if type(self.source) is not str or not self.source.strip():
            raise ValueError("source 不可為空")
        if self.quality_literal is not None and type(self.quality_literal) is not str:
            raise TypeError("quality_literal 必須是 str 或 None")


@dataclass(frozen=True, slots=True)
class MonthlyRevenueFacts:
    records: tuple[MonthlyRevenueFact, ...] = ()

    def __post_init__(self) -> None:
        if type(self.records) is not tuple or any(
            type(record) is not MonthlyRevenueFact for record in self.records
        ):
            raise TypeError("records 必須是 MonthlyRevenueFact tuple")


@dataclass(frozen=True, slots=True)
class IndustryContextFact:
    industries: tuple[str, ...] = ()
    first_industry_change_percent: Decimal | None = None
    first_industry_change_source_kind: IndustryChangeSourceKind = (
        IndustryChangeSourceKind.UNAVAILABLE
    )

    def __post_init__(self) -> None:
        if type(self.industries) is not tuple or any(
            type(industry) is not str for industry in self.industries
        ):
            raise TypeError("industries 必須是 str tuple")
        if self.first_industry_change_percent is not None and type(
            self.first_industry_change_percent
        ) is not Decimal:
            raise TypeError("first_industry_change_percent 必須是 Decimal 或 None")
        if type(self.first_industry_change_source_kind) is not IndustryChangeSourceKind:
            raise TypeError(
                "first_industry_change_source_kind 必須是 IndustryChangeSourceKind"
            )
        if (
            self.first_industry_change_percent is not None
            and self.first_industry_change_source_kind
            is IndustryChangeSourceKind.UNAVAILABLE
        ):
            # Preserve the pre-source-kind constructor shape: callers that only
            # supplied a Decimal still identify the native Decimal legacy path.
            object.__setattr__(
                self,
                "first_industry_change_source_kind",
                IndustryChangeSourceKind.LEGACY_DECIMAL,
            )
        if (
            self.first_industry_change_source_kind
            is IndustryChangeSourceKind.UNAVAILABLE
            and self.first_industry_change_percent is not None
        ):
            raise ValueError("unavailable industry change 必須是 None")
        if (
            self.first_industry_change_percent is None
            and self.first_industry_change_source_kind
            not in {
                IndustryChangeSourceKind.UNAVAILABLE,
                IndustryChangeSourceKind.UNSUPPORTED,
            }
        ):
            raise ValueError("industry change value 缺少 source kind")


@dataclass(frozen=True, slots=True)
class SourceFactError:
    error_type: str
    message: str

    def __post_init__(self) -> None:
        if type(self.error_type) is not str or not self.error_type.strip():
            raise ValueError("error_type 不可為空")
        if type(self.message) is not str:
            raise TypeError("message 必須是 str")


SourceFactValue = PEFact | MonthlyRevenueFacts | IndustryContextFact


@dataclass(frozen=True, slots=True)
class SourceFactResponse:
    """app 的 typed readback；來源錯誤與合法空值分開表達。"""

    request: NeedSourceFact
    value: SourceFactValue | None = None
    error: SourceFactError | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not NeedSourceFact:
            raise TypeError("request 必須是 NeedSourceFact")
        if (self.value is None) == (self.error is None):
            raise ValueError("SourceFactResponse 必須且只能有 value 或 error")
        if self.error is not None and type(self.error) is not SourceFactError:
            raise TypeError("error 必須是 SourceFactError")
        if self.value is not None:
            expected_type = {
                SourceFactKind.PE: PEFact,
                SourceFactKind.MONTHLY_REVENUE: MonthlyRevenueFacts,
                SourceFactKind.INDUSTRY_CONTEXT: IndustryContextFact,
            }[self.request.kind]
            if type(self.value) is not expected_type:
                raise TypeError("source fact value 與 request kind 不相符")


@dataclass(frozen=True, slots=True)
class StrategyEvaluationError:
    """Typed failure returned by the app's strategy scorer boundary."""

    error_type: str
    message: str

    def __post_init__(self) -> None:
        if type(self.error_type) is not str or not self.error_type.strip():
            raise ValueError("error_type 不可為空")
        if type(self.message) is not str:
            raise TypeError("message 必須是 str")


@dataclass(frozen=True, slots=True)
class CandidateHistoryFacts:
    """策略評估前已知的候選歷史列數與身分。"""

    invocation_id: str
    stock_code: str
    history_rows: int

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.history_rows) is not int or self.history_rows < 0:
            raise ValueError("history_rows 必須是非負整數")


@dataclass(frozen=True, slots=True)
class CandidateSeed:
    """app 將原候選當下已取得的 scorer 輸出投影為純值。"""

    invocation_id: str
    stock_code: str
    stock_name: str
    history_rows: int
    strategy_result_present: bool
    strategy_error: StrategyEvaluationError | None = None
    latest_volume_change_percent: Decimal | None = None
    item: RecommendationItem | None = None
    score: RecommendationScore | None = None

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.stock_name) is not str:
            raise TypeError("stock_name 必須是 str")
        if type(self.history_rows) is not int or self.history_rows < 0:
            raise ValueError("history_rows 必須是非負整數")
        if type(self.strategy_result_present) is not bool:
            raise TypeError("strategy_result_present 必須是 bool")
        if self.strategy_error is not None and type(self.strategy_error) is not StrategyEvaluationError:
            raise TypeError("strategy_error 必須是 StrategyEvaluationError 或 None")
        if self.strategy_error is not None and self.strategy_result_present:
            raise ValueError("strategy error candidate cannot have a strategy result")
        if self.latest_volume_change_percent is not None:
            if (
                type(self.latest_volume_change_percent) is not Decimal
                or not self.latest_volume_change_percent.is_finite()
            ):
                raise TypeError("latest_volume_change_percent 必須是有限 Decimal")
        if self.item is not None and type(self.item) is not RecommendationItem:
            raise TypeError("item 必須是 RecommendationItem 或 None")
        if self.score is not None and type(self.score) is not RecommendationScore:
            raise TypeError("score 必須是 RecommendationScore 或 None")
        if self.item is not None and self.item.stock_code != self.stock_code:
            raise ValueError("CandidateSeed item.stock_code 必須相同")
        if (self.item is None) != (self.score is None):
            raise ValueError("item 與 score 必須同時存在或同時缺席")


@dataclass(frozen=True, slots=True)
class CandidateEvaluationOutcome:
    invocation_id: str
    stock_code: str
    status: str
    quality: str
    stage: str
    reason_codes: tuple[str, ...]
    threshold_name: str = ""
    observed_value: str = ""
    required_value: str = ""
    item: RecommendationItem | None = None
    assessment: CandidateAssessment | None = None
    score: RecommendationScore | None = None
    warnings: tuple[str, ...] = ()
    source_responses: tuple[SourceFactResponse, ...] = ()

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code", "status", "quality", "stage"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.reason_codes) is not tuple or any(
            type(code) is not str for code in self.reason_codes
        ):
            raise TypeError("reason_codes 必須是 str tuple")
        for name in ("threshold_name", "observed_value", "required_value"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if type(self.warnings) is not tuple or any(
            type(warning) is not str for warning in self.warnings
        ):
            raise TypeError("warnings 必須是 str tuple")
        if self.item is not None and type(self.item) is not RecommendationItem:
            raise TypeError("item 必須是 RecommendationItem 或 None")
        if self.assessment is not None and type(self.assessment) is not CandidateAssessment:
            raise TypeError("assessment 必須是 CandidateAssessment 或 None")
        if self.score is not None and type(self.score) is not RecommendationScore:
            raise TypeError("score 必須是 RecommendationScore 或 None")
        if (self.item is None) != (self.score is None):
            raise ValueError("item 與 score 必須同時存在或同時缺席")
        if self.item is not None and self.item.stock_code != self.stock_code:
            raise ValueError("CandidateEvaluationOutcome item.stock_code 必須相同")
        if self.assessment is not None and self.assessment.stock_code != self.stock_code:
            raise ValueError(
                "CandidateEvaluationOutcome assessment.stock_code 必須相同"
            )
        if type(self.source_responses) is not tuple or any(
            type(response) is not SourceFactResponse
            for response in self.source_responses
        ):
            raise TypeError("source_responses 必須是 SourceFactResponse tuple")
        for response in self.source_responses:
            if (
                response.request.invocation_id != self.invocation_id
                or response.request.stock_code != self.stock_code
            ):
                raise ValueError(
                    "CandidateEvaluationOutcome source response identity 不一致"
                )


def _failure_outcome(
    *,
    invocation_id: str,
    stock_code: str,
    status: str,
    quality: str,
    reason: str,
    stage: str = "strategy_evaluation",
    threshold_name: str = "",
    observed_value: str = "",
    required_value: str = "",
    warnings: tuple[str, ...] = (),
    source_responses: tuple[SourceFactResponse, ...] = (),
) -> CandidateEvaluationOutcome:
    """Build a typed failure outcome using the shared diagnostic shape."""

    eligible = None if status in {"missing", "degraded"} else False
    assessment = CandidateAssessment(
        stock_code=stock_code,
        eligible=eligible,
        filter_outcomes={
            stage: FilterOutcome(
                filter_id=stage,
                passed=eligible,
                reason=reason,
                evidence={
                    "status": status,
                    "quality": quality,
                    "stage": stage,
                    "threshold_name": threshold_name,
                    "observed_value": observed_value,
                    "required_value": required_value,
                    "warnings": warnings,
                },
            )
        },
        reasons=(reason,),
        missing_data=(reason,) if status in {"missing", "degraded"} else (),
    )
    return CandidateEvaluationOutcome(
        invocation_id=invocation_id,
        stock_code=stock_code,
        status=status,
        quality=quality,
        stage=stage,
        reason_codes=(reason,),
        threshold_name=threshold_name,
        observed_value=observed_value,
        required_value=required_value,
        assessment=assessment,
        warnings=warnings,
        source_responses=source_responses,
    )


@dataclass(frozen=True, slots=True)
class CandidateDecisionDisposition:
    """完成 source gates 與 ranking 後的單一候選決策結果。"""

    invocation_id: str
    stock_code: str
    status: str
    quality: str
    stage: str
    reason_codes: tuple[str, ...]
    threshold_name: str
    observed_value: str
    required_value: str
    warnings: tuple[str, ...]
    assessment: CandidateAssessment
    scored: bool

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code", "status", "quality", "stage"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        for name in ("reason_codes", "warnings"):
            value = getattr(self, name)
            if type(value) is not tuple or any(type(item) is not str for item in value):
                raise TypeError(f"{name} 必須是 str tuple")
        for name in ("threshold_name", "observed_value", "required_value"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} 必須是 str")
        if type(self.assessment) is not CandidateAssessment:
            raise TypeError("assessment 必須是 CandidateAssessment")
        if self.assessment.stock_code != self.stock_code:
            raise ValueError("disposition assessment.stock_code 必須相同")
        if type(self.scored) is not bool:
            raise TypeError("scored 必須是 bool")


@dataclass(frozen=True, slots=True)
class RecommendationEvaluationResult:
    """同一批次的 canonical items/assessments 與最終 typed dispositions。"""

    decision: DecisionBatch
    dispositions: tuple[CandidateDecisionDisposition, ...]

    def __post_init__(self) -> None:
        if type(self.decision) is not DecisionBatch:
            raise TypeError("decision 必須是 DecisionBatch")
        if type(self.dispositions) is not tuple or any(
            type(item) is not CandidateDecisionDisposition
            for item in self.dispositions
        ):
            raise TypeError("dispositions 必須是 CandidateDecisionDisposition tuple")
        codes = [item.stock_code for item in self.dispositions]
        if len(codes) != len(set(codes)):
            raise ValueError("dispositions 不可有重複 stock_code")
        invocation_ids = {item.invocation_id for item in self.dispositions}
        if len(invocation_ids) > 1:
            raise ValueError("dispositions 不可混用 invocation_id")
        assessment_codes = tuple(
            assessment.stock_code for assessment in self.decision.assessments
        )
        if assessment_codes != tuple(codes):
            raise ValueError("decision assessments 必須依序對應 dispositions")
        if tuple(self.decision.assessments) != tuple(
            item.assessment for item in self.dispositions
        ):
            raise ValueError("decision assessments 必須等於 disposition assessments")
        dispositions_by_code = {item.stock_code: item for item in self.dispositions}
        item_codes = {item.stock_code for item in self.decision.items}
        selected_codes = {
            item.stock_code
            for item in self.dispositions
            if item.status.lower() == "pass"
            and item.scored
            and item.assessment.eligible is True
        }
        if item_codes != selected_codes:
            raise ValueError(
                "decision items 必須且只能來自 pass/scored/eligible dispositions"
            )
        ordered_selected: list[tuple[int, str]] = []
        selected_evidence_by_code: dict[str, dict[str, object]] = {}
        for disposition in self.dispositions:
            if disposition.stock_code not in selected_codes:
                continue
            ranking = dict(disposition.assessment.filter_outcomes or {}).get(
                "recommendation_ranking"
            )
            evidence = dict(ranking.evidence or {}) if ranking is not None else {}
            ordered_rank = evidence.get("ordered_rank")
            if (
                ranking is None
                or ranking.passed is not True
                or evidence.get("selected") is not True
                or type(ordered_rank) is not int
                or ordered_rank < 1
            ):
                raise ValueError(
                    "selected disposition 必須有通過的 recommendation_ranking evidence"
                )
            ordered_selected.append((ordered_rank, disposition.stock_code))
            selected_evidence_by_code[disposition.stock_code] = evidence
        ordered_selected.sort(key=lambda ranked: ranked[0])
        expected_item_codes = tuple(ranked[1] for ranked in ordered_selected)
        if tuple(
            decision_item.stock_code for decision_item in self.decision.items
        ) != expected_item_codes:
            raise ValueError("decision items 順序必須符合 evaluator ranking order")
        for index, decision_item in enumerate(self.decision.items, start=1):
            disposition = dispositions_by_code[decision_item.stock_code]
            if (
                disposition.status.lower() != "pass"
                or not disposition.scored
                or disposition.assessment.eligible is not True
            ):
                raise ValueError(
                    "decision item 必須對應 pass/scored/eligible disposition"
            )
            evidence = selected_evidence_by_code[decision_item.stock_code]
            if (
                decision_item.rank != index
                or decision_item.rank != evidence.get("ordered_rank")
                or decision_item.score_percentile_bp
                != evidence.get("score_percentile_bp")
                or decision_item.eligible_universe_size
                != evidence.get("eligible_universe_size")
                or decision_item.eligible_universe_date
                != evidence.get("eligible_universe_date")
                or decision_item.ranking_method != evidence.get("ranking_method")
                or decision_item.threshold_mode != evidence.get("threshold_mode")
            ):
                raise ValueError(
                    "decision item ranking metadata 必須符合 evaluator evidence"
                )


@dataclass(frozen=True, slots=True)
class CandidatePrefilterFact:
    """進入逐檔 evaluator 前已由 typed universe source 得到的結果。"""

    invocation_id: str
    stock_code: str
    requested_industry: str
    point_in_time_required: bool
    membership_usable: bool
    matching_stock_count: int

    def __post_init__(self) -> None:
        for name in ("invocation_id", "stock_code", "requested_industry"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        for name in ("point_in_time_required", "membership_usable"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} 必須是 bool")
        if type(self.matching_stock_count) is not int or self.matching_stock_count < 0:
            raise ValueError("matching_stock_count 必須是非負 int")


@dataclass(frozen=True, slots=True)
class CandidateEvaluationState:
    policy: RecommendationEvaluationPolicy
    seed: CandidateSeed
    stage: CandidateStage = CandidateStage.READY
    pending: NeedSourceFact | None = None
    pe_fact: PEFact | None = None
    pe_error: SourceFactError | None = None
    revenue_facts: MonthlyRevenueFacts | None = None
    revenue_error: SourceFactError | None = None
    industry_fact: IndustryContextFact | None = None
    industry_error: SourceFactError | None = None
    source_responses: tuple[SourceFactResponse, ...] = ()
    outcome: CandidateEvaluationOutcome | None = None

    def __post_init__(self) -> None:
        if self.policy.invocation_id != self.seed.invocation_id:
            raise ValueError("policy/seed invocation_id 不一致")
        waiting_stages = {
            CandidateStage.WAITING_FOR_PE,
            CandidateStage.WAITING_FOR_MONTHLY_REVENUE,
            CandidateStage.WAITING_FOR_INDUSTRY_CONTEXT,
        }
        if (self.stage in waiting_stages) != (self.pending is not None):
            raise ValueError("state stage 與 pending request 不一致")
        if (self.stage is CandidateStage.COMPLETE) != (self.outcome is not None):
            raise ValueError("complete state 必須且只能包含 outcome")
        if type(self.source_responses) is not tuple or any(
            type(response) is not SourceFactResponse
            for response in self.source_responses
        ):
            raise TypeError("source_responses 必須是 SourceFactResponse tuple")


@dataclass(frozen=True, slots=True)
class CandidateEvaluationStep:
    state: CandidateEvaluationState
    request: NeedSourceFact | None = None
    outcome: CandidateEvaluationOutcome | None = None

    def __post_init__(self) -> None:
        if (self.request is None) == (self.outcome is None):
            raise ValueError("step 必須且只能回傳 request 或 outcome")
        if self.request is not None and self.state.pending != self.request:
            raise ValueError("step request 必須與 state.pending 相同")
        if self.outcome is not None and self.state.outcome != self.outcome:
            raise ValueError("step outcome 必須與 state.outcome 相同")


@dataclass(frozen=True, slots=True)
class ReplayCandidateHistoryFacts:
    """replay 候選在任何 fast-filter 資料讀取前已知的 PIT/history facts。"""

    invocation_id: str
    observations: ReplayPrefilterObservationV1

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.observations) not in {
            ReplayPrefilterObservations,
            ReplayCompatibilityPrefilterObservationsV1,
        }:
            raise TypeError(
                "observations 必須是 ReplayPrefilterObservations 或明示相容契約"
            )
        if (
            type(self.observations) is ReplayCompatibilityPrefilterObservationsV1
            and self.observations.compatibility_candidate_key.invocation_id
            != self.invocation_id
        ):
            raise ValueError("compatibility candidate key 必須綁定 facts invocation")


@dataclass(frozen=True, slots=True)
class NeedReplayPrefilterFact:
    """唯一待讀 replay prefilter fact，綁定 invocation／候選／cutoff／種類。"""

    request_id: str
    invocation_id: str
    kind: ReplayPrefilterFactKind
    stock_code: str
    as_of_date: date
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1 | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "invocation_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.stock_code) is not str:
            raise TypeError("stock_code 必須是 str")
        if self.compatibility_candidate_key is None:
            if not self.stock_code.strip():
                raise ValueError("stock_code 不可為空")
        else:
            if type(self.compatibility_candidate_key) is not ReplayCompatibilityCandidateKeyV1:
                raise TypeError(
                    "compatibility_candidate_key 必須是 ReplayCompatibilityCandidateKeyV1"
                )
            if self.stock_code.strip():
                raise ValueError("compatibility key 僅適用於原始空白 stock_code")
            if self.compatibility_candidate_key.invocation_id != self.invocation_id:
                raise ValueError("compatibility candidate key invocation 不一致")
        if type(self.kind) is not ReplayPrefilterFactKind:
            raise TypeError("kind 必須是 ReplayPrefilterFactKind")
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")


@dataclass(frozen=True, slots=True)
class ReplayPrefilterFactResponse:
    """對 replay prefilter request 的 typed numeric/status 回填。"""

    request: NeedReplayPrefilterFact
    metric_status: ReplayMetricStatus | None = None
    metric_value: Decimal | int | ReplayComparisonValue | ReplayComparisonOperand | None = None
    threshold: ReplayThreshold | None = None
    volume_threshold: ReplayVolumeThresholdV1 | None = None
    paired_metric_request_id: str | None = None
    paired_metric_status: ReplayMetricStatus | None = None
    paired_metric_value: ReplayComparisonOperand | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not NeedReplayPrefilterFact:
            raise TypeError("request 必須是 NeedReplayPrefilterFact")
        kind = self.request.kind
        metric_kinds = {
            ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
            ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
        }
        if kind in metric_kinds:
            if any(
                value is not None
                for value in (
                    self.paired_metric_request_id,
                    self.paired_metric_status,
                    self.paired_metric_value,
                )
            ):
                raise ValueError("metric response 不可帶 threshold projection")
            if type(self.metric_status) is not ReplayMetricStatus:
                raise TypeError("metric response 必須有 ReplayMetricStatus")
            if self.metric_status is ReplayMetricStatus.NOT_REQUESTED:
                raise ValueError("metric response 不可仍是 NOT_REQUESTED")
            if self.metric_value is not None and type(self.metric_value) not in (
                Decimal,
                int,
                ReplayComparisonValue,
                ReplayComparisonOperand,
            ):
                raise TypeError(
                    "metric_value 必須是 Decimal、int、ReplayComparisonValue、"
                    "ReplayComparisonOperand 或 None"
                )
            if type(self.metric_value) is Decimal and not self.metric_value.is_finite():
                raise ValueError("metric_value Decimal 必須有限")
            has_value = self.metric_value is not None
            if self.metric_status in (
                ReplayMetricStatus.AVAILABLE,
                ReplayMetricStatus.ZERO_DENOMINATOR,
            ):
                if not has_value:
                    raise ValueError("available metric response 必須有值")
            elif has_value:
                raise ValueError("缺值／unsupported metric response 不可帶數值")
            if self.metric_status is ReplayMetricStatus.ZERO_DENOMINATOR:
                if not _is_zero_replay_number(self.metric_value):
                    raise ValueError("zero-denominator metric response 必須是 0")
            if self.threshold is not None or self.volume_threshold is not None:
                raise ValueError("metric response 不可同時帶 threshold")
            return

        if self.metric_status is not None or self.metric_value is not None:
            raise ValueError("threshold response 不可帶 metric fields")
        if kind is ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD:
            if type(self.volume_threshold) is not ReplayVolumeThresholdV1:
                raise TypeError("volume threshold response 必須是 ReplayVolumeThresholdV1")
            if self.volume_threshold.kind is not ReplayVolumeThresholdKind.EFFECTIVE_CHANGE_PERCENT:
                raise ValueError("staged volume response 必須是 effective percent")
            _validate_resolved_threshold(self.volume_threshold.threshold)
            if self.threshold is not None:
                raise ValueError("volume response 不可同時帶一般 threshold")
            _validate_paired_metric_projection(
                threshold=self.volume_threshold.threshold,
                paired_metric_request_id=self.paired_metric_request_id,
                paired_metric_status=self.paired_metric_status,
                paired_metric_value=self.paired_metric_value,
            )
            return

        if type(self.threshold) is not ReplayThreshold:
            raise TypeError("price threshold response 必須是 ReplayThreshold")
        _validate_resolved_threshold(self.threshold)
        if self.volume_threshold is not None:
            raise ValueError("price threshold response 不可帶 volume threshold")
        _validate_paired_metric_projection(
            threshold=self.threshold,
            paired_metric_request_id=self.paired_metric_request_id,
            paired_metric_status=self.paired_metric_status,
            paired_metric_value=self.paired_metric_value,
        )


def _validate_paired_metric_projection(
    *,
    threshold: ReplayThreshold,
    paired_metric_request_id: str | None,
    paired_metric_status: ReplayMetricStatus | None,
    paired_metric_value: ReplayComparisonOperand | None,
) -> None:
    pair_fields = (
        paired_metric_request_id,
        paired_metric_status,
        paired_metric_value,
    )
    has_pair = tuple(value is not None for value in pair_fields)
    if any(has_pair) and not all(has_pair):
        raise ValueError("paired metric projection 欄位必須一起提供")
    if not any(has_pair):
        return
    if threshold.status is not ReplayThresholdStatus.ENABLED:
        raise ValueError("只有 enabled threshold 可帶 paired metric projection")
    if type(paired_metric_request_id) is not str or not paired_metric_request_id.strip():
        raise ValueError("paired_metric_request_id 不可為空")
    if type(paired_metric_status) is not ReplayMetricStatus or paired_metric_status not in (
        ReplayMetricStatus.AVAILABLE,
        ReplayMetricStatus.ZERO_DENOMINATOR,
    ):
        raise ValueError("paired_metric_status 必須是 AVAILABLE 或 ZERO_DENOMINATOR")
    if type(paired_metric_value) is not ReplayComparisonOperand:
        raise TypeError("paired_metric_value 必須是 ReplayComparisonOperand")
    threshold_value = threshold.value
    if type(threshold_value) is not ReplayComparisonOperand:
        raise ValueError("paired metric 與 threshold 必須使用同一 typed domain")
    if paired_metric_value.domain != threshold_value.domain:
        raise ValueError("paired metric 與 threshold comparison domain 不一致")
    if paired_metric_status is ReplayMetricStatus.ZERO_DENOMINATOR and not (
        _is_zero_replay_number(paired_metric_value)
    ):
        raise ValueError("ZERO_DENOMINATOR paired metric 必須是 0")


def _is_zero_replay_number(
    value: Decimal | int | ReplayComparisonValue | ReplayComparisonOperand | None,
) -> bool:
    if type(value) is int:
        return value == 0
    if type(value) is Decimal:
        return value == 0
    if type(value) is ReplayComparisonValue:
        return value.kind is ReplayComparisonKind.FINITE and value.value == 0
    return (
        type(value) is ReplayComparisonOperand
        and value.imaginary is None
        and value.real.kind is ReplayComparisonKind.FINITE
        and value.real.numerator == 0
    )


def _normalize_replay_comparison(
    value: Decimal | int | ReplayComparisonValue | ReplayComparisonOperand | None,
) -> ReplayComparisonValue | ReplayComparisonOperand | None:
    if value is None:
        return None
    if type(value) is ReplayComparisonValue:
        return value
    if type(value) is ReplayComparisonOperand:
        return value
    if type(value) is int:
        return ReplayComparisonValue.finite(value)
    if type(value) is Decimal:
        return ReplayComparisonValue.finite(value)
    raise TypeError("不支援的 replay comparison value")


def _validate_resolved_threshold(threshold: ReplayThreshold) -> None:
    if type(threshold) is not ReplayThreshold:
        raise TypeError("threshold 必須是 ReplayThreshold")
    if threshold.status in (
        ReplayThresholdStatus.DISABLED,
        ReplayThresholdStatus.PENDING,
    ):
        raise ValueError("threshold response 必須已解析為 enabled 或 unsupported")


@dataclass(frozen=True, slots=True)
class NeedCandidateScoring:
    """Fast-filter READY 後交給 app scorer 的唯一 request。"""

    request_id: str
    invocation_id: str
    stock_code: str
    as_of_date: date
    history_rows: int
    prefilter_outcome: ReplayPreflightOutcome

    def __post_init__(self) -> None:
        for name in ("request_id", "invocation_id", "stock_code"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")
        if type(self.history_rows) is not int or self.history_rows < 0:
            raise ValueError("history_rows 必須是非負整數")
        if self.history_rows < MINIMUM_RECOMMENDATION_HISTORY_ROWS:
            raise ValueError("scoring request history_rows 未達 minimum history")
        if type(self.prefilter_outcome) is not ReplayPreflightOutcome:
            raise TypeError("prefilter_outcome 必須是 ReplayPreflightOutcome")
        if (
            self.prefilter_outcome.disposition is not ReplayPreflightDisposition.READY
            or self.prefilter_outcome.stage is not ReplayPreflightStage.READY
            or self.prefilter_outcome.reason_code != "ready"
            or self.prefilter_outcome.stock_code != self.stock_code
            or self.prefilter_outcome.as_of_date != self.as_of_date
        ):
            raise ValueError("scoring request 必須綁定同一候選的 READY prefilter")


@dataclass(frozen=True, slots=True)
class NeedCompatibilityScoring:
    """空白原始 code 的 scorer handoff；不授權建立 canonical item/assessment。"""

    request_id: str
    invocation_id: str
    stock_code: str
    as_of_date: date
    history_rows: int
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1
    prefilter_outcome: ReplayCompatibilityPreflightOutcomeV1

    def __post_init__(self) -> None:
        for name in ("request_id", "invocation_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if type(self.stock_code) is not str or self.stock_code.strip():
            raise ValueError("compatibility scoring 僅接受原始空白 stock_code")
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")
        if type(self.history_rows) is not int or self.history_rows < MINIMUM_RECOMMENDATION_HISTORY_ROWS:
            raise ValueError("compatibility scoring history_rows 未達 minimum history")
        if type(self.compatibility_candidate_key) is not ReplayCompatibilityCandidateKeyV1:
            raise TypeError("compatibility_candidate_key 必須是 ReplayCompatibilityCandidateKeyV1")
        if self.compatibility_candidate_key.invocation_id != self.invocation_id:
            raise ValueError("compatibility candidate key invocation 不一致")
        if type(self.prefilter_outcome) is not ReplayCompatibilityPreflightOutcomeV1:
            raise TypeError("prefilter_outcome 必須是相容 preflight 結果")
        if (
            self.prefilter_outcome.disposition is not ReplayPreflightDisposition.READY
            or self.prefilter_outcome.stage is not ReplayPreflightStage.READY
            or self.prefilter_outcome.reason_code != "ready"
            or self.prefilter_outcome.stock_code != self.stock_code
            or self.prefilter_outcome.as_of_date != self.as_of_date
            or self.prefilter_outcome.compatibility_candidate_key
            != self.compatibility_candidate_key
        ):
            raise ValueError("compatibility scorer request 必須綁定同一 READY 候選")


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityPrefilterOutcomeV1:
    """空白 raw code 的 terminal filter outcome，不含 canonical assessment 欄位。"""

    invocation_id: str
    stock_code: str
    prefilter_outcome: ReplayCompatibilityPreflightOutcomeV1

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.stock_code) is not str or self.stock_code.strip():
            raise ValueError("compatibility outcome 僅接受原始空白 stock_code")
        if type(self.prefilter_outcome) is not ReplayCompatibilityPreflightOutcomeV1:
            raise TypeError("prefilter_outcome 必須是相容 preflight 結果")
        if (
            self.prefilter_outcome.disposition
            not in {ReplayPreflightDisposition.REJECT, ReplayPreflightDisposition.UNSUPPORTED}
            or self.prefilter_outcome.stock_code != self.stock_code
            or self.prefilter_outcome.compatibility_candidate_key.invocation_id
            != self.invocation_id
        ):
            raise ValueError("compatibility terminal outcome identity/disposition 不一致")


class ReplayCompatibilityScorerDispositionV1(str, Enum):
    """空白 raw code 相容 scorer 的 invocation-local terminal 狀態。"""

    SCORED = "scored"
    SKIPPED_EMPTY = "skipped_empty"
    SKIPPED_SCORER_EXCEPTION = "skipped_scorer_exception"
    SKIPPED_PROJECTION_EXCEPTION = "skipped_projection_exception"


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityScorerResponseV1:
    """App 對同一空白 code compatibility scorer request 的非 canonical 回覆。"""

    request: NeedCompatibilityScoring
    disposition: ReplayCompatibilityScorerDispositionV1
    error_type: str | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not NeedCompatibilityScoring:
            raise TypeError("request 必須是 NeedCompatibilityScoring")
        if type(self.disposition) is not ReplayCompatibilityScorerDispositionV1:
            raise TypeError("disposition 必須是 ReplayCompatibilityScorerDispositionV1")
        if self.error_type is not None and type(self.error_type) is not str:
            raise TypeError("error_type 僅接受 str 或 None，不可傳 exception instance")
        if self.disposition is ReplayCompatibilityScorerDispositionV1.SCORED:
            if self.error_type is not None:
                raise ValueError("scored compatibility response 不可帶 error_type")
            return
        if self.disposition is ReplayCompatibilityScorerDispositionV1.SKIPPED_EMPTY:
            if self.error_type is not None:
                raise ValueError("empty compatibility response 不可帶 error_type")
            return
        if type(self.error_type) is not str or not self.error_type.strip():
            raise ValueError("compatibility exception skip 必須帶 error_type 名稱")


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityScoringOutcomeV1:
    """空白 raw code scorer 的 terminal receipt；不建立 item 或 assessment。"""

    response: ReplayCompatibilityScorerResponseV1

    def __post_init__(self) -> None:
        if type(self.response) is not ReplayCompatibilityScorerResponseV1:
            raise TypeError("response 必須是 ReplayCompatibilityScorerResponseV1")

    @property
    def request(self) -> NeedCompatibilityScoring:
        return self.response.request

    @property
    def disposition(self) -> ReplayCompatibilityScorerDispositionV1:
        return self.response.disposition


class ReplayCandidatePrefilterPhase(str, Enum):
    READY = "ready"
    WAITING_FOR_FACT = "waiting_for_fact"
    NEEDS_SCORING = "needs_scoring"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ReplayCandidatePrefilterState:
    """單一 replay 候選的 immutable staged prefilter 狀態。"""

    invocation_id: str
    policy: ReplayFastFilterPolicyV1
    observations: ReplayPrefilterObservationV1
    phase: ReplayCandidatePrefilterPhase = ReplayCandidatePrefilterPhase.READY
    pending: NeedReplayPrefilterFact | None = None
    scoring_request: NeedCandidateScoring | NeedCompatibilityScoring | None = None
    outcome: (
        CandidateEvaluationOutcome
        | ReplayCompatibilityPrefilterOutcomeV1
        | ReplayCompatibilityScoringOutcomeV1
        | None
    ) = None
    responses: tuple[ReplayPrefilterFactResponse, ...] = ()

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if type(self.policy) is not ReplayFastFilterPolicyV1:
            raise TypeError("policy 必須是 ReplayFastFilterPolicyV1")
        if type(self.observations) not in {
            ReplayPrefilterObservations,
            ReplayCompatibilityPrefilterObservationsV1,
        }:
            raise TypeError("observations 必須是 replay prefilter observations contract")
        compatibility_key = (
            self.observations.compatibility_candidate_key
            if type(self.observations) is ReplayCompatibilityPrefilterObservationsV1
            else None
        )
        if compatibility_key is not None and compatibility_key.invocation_id != self.invocation_id:
            raise ValueError("compatibility candidate key 必須綁定 state invocation")
        if type(self.phase) is not ReplayCandidatePrefilterPhase:
            raise TypeError("phase 必須是 ReplayCandidatePrefilterPhase")
        if (self.phase is ReplayCandidatePrefilterPhase.WAITING_FOR_FACT) != (
            self.pending is not None
        ):
            raise ValueError("state phase 與 pending fact 不一致")
        if (self.phase is ReplayCandidatePrefilterPhase.NEEDS_SCORING) != (
            self.scoring_request is not None
        ):
            raise ValueError("state phase 與 scoring request 不一致")
        if (self.phase is ReplayCandidatePrefilterPhase.COMPLETE) != (
            self.outcome is not None
        ):
            raise ValueError("complete state 必須且只能包含 outcome")
        if self.pending is not None and type(self.pending) is not NeedReplayPrefilterFact:
            raise TypeError("pending 必須是 NeedReplayPrefilterFact")
        if self.scoring_request is not None and type(self.scoring_request) not in {
            NeedCandidateScoring,
            NeedCompatibilityScoring,
        }:
            raise TypeError("scoring_request 必須是 typed replay scorer request")
        if self.outcome is not None and type(self.outcome) not in {
            CandidateEvaluationOutcome,
            ReplayCompatibilityPrefilterOutcomeV1,
            ReplayCompatibilityScoringOutcomeV1,
        }:
            raise TypeError("outcome 必須是 typed replay prefilter outcome")
        for request in (self.pending, self.scoring_request):
            if request is None:
                continue
            if (
                request.invocation_id != self.invocation_id
                or request.stock_code != self.observations.stock_code
                or request.as_of_date != self.observations.as_of_date
                or getattr(request, "compatibility_candidate_key", None)
                != compatibility_key
            ):
                raise ValueError("replay request identity 與 state 不一致")
        if type(self.outcome) is CandidateEvaluationOutcome and (
            self.outcome.invocation_id != self.invocation_id
            or self.outcome.stock_code != self.observations.stock_code
            or self.outcome.item is not None
            or self.outcome.score is not None
            or self.outcome.assessment is None
        ):
            raise ValueError("replay prefilter outcome identity/item 不一致")
        if type(self.outcome) is ReplayCompatibilityPrefilterOutcomeV1 and (
            self.outcome.invocation_id != self.invocation_id
            or self.outcome.stock_code != self.observations.stock_code
            or self.outcome.prefilter_outcome.as_of_date
            != self.observations.as_of_date
            or compatibility_key is None
            or self.outcome.prefilter_outcome.compatibility_candidate_key
            != compatibility_key
        ):
            raise ValueError("compatibility prefilter outcome identity 不一致")
        if type(self.outcome) is ReplayCompatibilityScoringOutcomeV1 and (
            compatibility_key is None
            or self.outcome.request.invocation_id != self.invocation_id
            or self.outcome.request.stock_code != self.observations.stock_code
            or self.outcome.request.as_of_date != self.observations.as_of_date
            or self.outcome.request.history_rows != self.observations.history_rows
            or self.outcome.request.compatibility_candidate_key != compatibility_key
        ):
            raise ValueError("compatibility scoring outcome identity 不一致")
        if type(self.responses) is not tuple or any(
            type(response) is not ReplayPrefilterFactResponse
            for response in self.responses
        ):
            raise TypeError("responses 必須是 ReplayPrefilterFactResponse tuple")
        response_ids = tuple(response.request.request_id for response in self.responses)
        response_kinds = tuple(response.request.kind for response in self.responses)
        if len(response_ids) != len(set(response_ids)):
            raise ValueError("replay response request_id 不可重複")
        if len(response_kinds) != len(set(response_kinds)):
            raise ValueError("同一候選不可重複回填相同 replay fact kind")
        kind_order = {
            kind: index
            for index, kind in enumerate(
                (
                    ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                    ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
                    ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
                    ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
                    ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
                )
            )
        }
        if tuple(kind_order[kind] for kind in response_kinds) != tuple(
            sorted(kind_order[kind] for kind in response_kinds)
        ):
            raise ValueError("replay responses 必須符合 evaluator stage 順序")
        response_by_id = {
            response.request.request_id: (index, response)
            for index, response in enumerate(self.responses)
        }
        metric_response_by_kind: dict[
            ReplayPrefilterFactKind, tuple[int, ReplayPrefilterFactResponse]
        ] = {}
        pairings_by_metric_request: dict[
            str, list[tuple[int, ReplayMetricStatus, ReplayComparisonOperand]]
        ] = {}
        pair_origin_status_by_metric_request: dict[
            str, tuple[ReplayMetricStatus, ReplayNumericOrigin]
        ] = {}
        threshold_to_metric_kind = {
            ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD: ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
            ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD: ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
            ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD: ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
        }
        for index, response in enumerate(self.responses):
            request = response.request
            if (
                request.invocation_id != self.invocation_id
                or request.stock_code != self.observations.stock_code
                or request.as_of_date != self.observations.as_of_date
                or request.compatibility_candidate_key != compatibility_key
            ):
                raise ValueError("replay response identity 與 state 不一致")
            if request.kind in {
                ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
            }:
                metric_response_by_kind[request.kind] = (index, response)
                continue

            if request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD:
                if response.threshold != self.policy.price_change_min:
                    raise ValueError("price minimum response 未反映到 policy")
            elif request.kind is ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD:
                if response.threshold != self.policy.price_change_max:
                    raise ValueError("price maximum response 未反映到 policy")
            elif request.kind is ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD:
                if response.volume_threshold != self.policy.volume_minimum:
                    raise ValueError("volume minimum response 未反映到 policy")

            expected_metric_kind = threshold_to_metric_kind[request.kind]
            metric_request_id = response.paired_metric_request_id
            if metric_request_id is None:
                metric_entry = metric_response_by_kind.get(expected_metric_kind)
                if metric_entry is not None:
                    metric_response = metric_entry[1]
                    if request.kind is ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD:
                        assert response.volume_threshold is not None
                        threshold_is_enabled = (
                            response.volume_threshold.threshold.status
                            is ReplayThresholdStatus.ENABLED
                        )
                    else:
                        threshold_is_enabled = (
                            response.threshold is not None
                            and response.threshold.status is ReplayThresholdStatus.ENABLED
                        )
                    if (
                        metric_response.metric_status
                        is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
                        and threshold_is_enabled
                    ):
                        raise ValueError(
                            "awaiting threshold projection 必須原子回填 paired metric"
                        )
                continue

            metric_entry = response_by_id.get(metric_request_id)
            if metric_entry is None:
                raise ValueError("paired_metric_request_id 不屬於既有 metric response")
            metric_index, metric_response = metric_entry
            metric_request = metric_response.request
            if (
                metric_index >= index
                or metric_request.kind is not expected_metric_kind
                or metric_request.invocation_id != request.invocation_id
                or metric_request.stock_code != request.stock_code
                or metric_request.as_of_date != request.as_of_date
                or metric_response.metric_status
                is not ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
            ):
                raise ValueError("paired metric request identity/stage 不一致")
            assert response.paired_metric_status is not None
            assert response.paired_metric_value is not None
            origin_status = (
                response.paired_metric_status,
                response.paired_metric_value.origin,
            )
            previous_origin_status = pair_origin_status_by_metric_request.setdefault(
                metric_request_id,
                origin_status,
            )
            if previous_origin_status != origin_status:
                raise ValueError(
                    "same metric request 的 threshold pairs 必須保留來源 origin/status"
                )
            pairings_by_metric_request.setdefault(metric_request_id, []).append(
                (
                    index,
                    response.paired_metric_status,
                    response.paired_metric_value,
                )
            )

        for metric_kind, metric_name, observation_status, observation_value in (
            (
                ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                "price",
                self.observations.price_change_status,
                self.observations.price_change_percent,
            ),
            (
                ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
                "volume",
                self.observations.volume_change_status,
                self.observations.volume_change_percent,
            ),
        ):
            metric_entry = metric_response_by_kind.get(metric_kind)
            if metric_entry is None:
                continue
            metric_response = metric_entry[1]
            metric_request_id = metric_response.request.request_id
            if (
                metric_response.metric_status
                is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
            ):
                projected = pairings_by_metric_request.get(metric_request_id)
                if projected is None:
                    if (
                        observation_status
                        is not ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
                        or observation_value is not None
                    ):
                        raise ValueError(
                            f"{metric_name} awaiting metric 未保留 projection 狀態"
                        )
                else:
                    _, latest_status, latest_value = projected[-1]
                    if (
                        observation_status is latest_status
                        and observation_value == latest_value
                    ):
                        continue
                    raise ValueError(
                        f"{metric_name} paired metric projection 未反映到 observations"
                    )
            elif (
                metric_response.metric_status is not observation_status
                or _normalize_replay_comparison(metric_response.metric_value)
                != observation_value
            ):
                raise ValueError(f"{metric_name} metric response 未反映到 observations")
        if self.pending is not None:
            if (
                self.pending.request_id in response_ids
                or self.pending.kind in response_kinds
            ):
                raise ValueError("pending replay fact 不可重複既有 response")
        if self.scoring_request is not None:
            if self.scoring_request.request_id in response_ids:
                raise ValueError("scoring request_id 不可重複 replay response")
            if self.scoring_request.history_rows != self.observations.history_rows:
                raise ValueError("scoring request history_rows 與 state 不一致")


@dataclass(frozen=True, slots=True)
class ReplayCandidatePrefilterStep:
    state: ReplayCandidatePrefilterState
    request: NeedReplayPrefilterFact | NeedCandidateScoring | NeedCompatibilityScoring | None = None
    outcome: (
        CandidateEvaluationOutcome
        | ReplayCompatibilityPrefilterOutcomeV1
        | ReplayCompatibilityScoringOutcomeV1
        | None
    ) = None

    def __post_init__(self) -> None:
        if type(self.state) is not ReplayCandidatePrefilterState:
            raise TypeError("state 必須是 ReplayCandidatePrefilterState")
        if (self.request is None) == (self.outcome is None):
            raise ValueError("step 必須且只能回傳 request 或 outcome")
        if type(self.request) is NeedReplayPrefilterFact:
            if self.state.pending != self.request:
                raise ValueError("fact request 必須與 state.pending 相同")
        elif type(self.request) is NeedCandidateScoring:
            if self.state.scoring_request != self.request:
                raise ValueError("scoring request 必須與 state.scoring_request 相同")
        elif type(self.request) is NeedCompatibilityScoring:
            if self.state.scoring_request != self.request:
                raise ValueError("compatibility scoring request 必須與 state 相同")
        elif self.request is not None:
            raise TypeError("request 必須是 replay fact 或 scoring request")
        if self.outcome is not None and self.state.outcome != self.outcome:
            raise ValueError("outcome 必須與 state.outcome 相同")


class ReplayScorerDispositionV1(str, Enum):
    """Replay scorer 回覆的成功或逐檔略過結果。"""

    SCORED = "scored"
    SKIPPED_EMPTY = "skipped_empty"
    SKIPPED_SCORER_EXCEPTION = "skipped_scorer_exception"
    SKIPPED_PROJECTION_EXCEPTION = "skipped_projection_exception"


@dataclass(frozen=True, slots=True)
class ReplayScorerResponseV1:
    """App 對單一 `NeedCandidateScoring` 的純 typed 回覆。

    Response 保留原 request 身份。App 只傳已投影的 item、排序 token，或明示的
    per-stock skip 類型；不傳 Pandas、原始 float 或 exception instance。
    """

    request: NeedCandidateScoring
    disposition: ReplayScorerDispositionV1
    item: RecommendationItem | None = None
    score_ordering: ReplayScoreOrderingV1 | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not NeedCandidateScoring:
            raise TypeError("request 必須是 NeedCandidateScoring")
        if type(self.disposition) is not ReplayScorerDispositionV1:
            raise TypeError("disposition 必須是 ReplayScorerDispositionV1")
        if self.error_type is not None and type(self.error_type) is not str:
            raise TypeError("error_type 僅接受 str 或 None，不可傳 exception instance")

        if self.disposition is ReplayScorerDispositionV1.SCORED:
            if type(self.item) is not RecommendationItem:
                raise TypeError("scored response 必須有 RecommendationItem")
            if type(self.score_ordering) is not ReplayScoreOrderingV1:
                raise TypeError("scored response 必須有 ReplayScoreOrderingV1")
            if self.item.stock_code != self.request.stock_code:
                raise ValueError("scored item stock_code 與 scorer request 不一致")
            if (
                self.item.rule_score is not None
                and self.score_ordering.kind is not ReplayScoreOrderingKindV1.FINITE
            ):
                raise ValueError(
                    "有限 canonical rule_score 必須配有限 replay 排序值"
                )
            if self.error_type is not None:
                raise ValueError("scored response 不可帶 error_type")
            return

        if self.item is not None or self.score_ordering is not None:
            raise ValueError("skipped response 不可帶 item 或 score_ordering")
        if self.disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY:
            if self.error_type is not None:
                raise ValueError("empty response 不可帶 error_type")
            return
        if type(self.error_type) is not str or not self.error_type.strip():
            raise ValueError("exception skip 必須帶 error_type 名稱")

    @property
    def reason_code(self) -> str | None:
        return _replay_scorer_reason_code(self.disposition)


@dataclass(frozen=True, slots=True)
class ReplayCandidateScoringOutcomeV1:
    """Evaluator 驗證 handoff 後形成的 replay 專用候選結果。"""

    response: ReplayScorerResponseV1
    assessment: CandidateAssessment

    def __post_init__(self) -> None:
        if type(self.response) is not ReplayScorerResponseV1:
            raise TypeError("response 必須是 ReplayScorerResponseV1")
        if type(self.assessment) is not CandidateAssessment:
            raise TypeError("assessment 必須是 CandidateAssessment")
        if self.assessment.stock_code != self.response.request.stock_code:
            raise ValueError("assessment stock_code 與 scorer request 不一致")

        filters = self.assessment.filter_outcomes or {}
        if set(filters) != {"replay_prefilter", "replay_scoring"}:
            raise ValueError("assessment 只能包含 replay prefilter/scoring outcomes")
        prefilter = filters.get("replay_prefilter")
        scoring = filters.get("replay_scoring")
        if (
            type(prefilter) is not FilterOutcome
            or prefilter.passed is not True
            or prefilter.reason != "ready"
            or type(scoring) is not FilterOutcome
        ):
            raise ValueError("assessment 必須保留 READY prefilter 與 replay scoring")

        request = self.response.request
        expected_prefilter_evidence = {
            "as_of_date": request.as_of_date.isoformat(),
            "history_rows": request.history_rows,
            "reason_code": request.prefilter_outcome.reason_code,
            "stage": request.prefilter_outcome.stage.value,
        }
        if dict(prefilter.evidence or {}) != expected_prefilter_evidence:
            raise ValueError("assessment prefilter evidence 與 scorer request 不一致")
        expected_scoring_evidence = {
            "request_id": request.request_id,
            "disposition": self.response.disposition.value,
            "error_type": self.response.error_type,
        }
        if dict(scoring.evidence or {}) != expected_scoring_evidence:
            raise ValueError("assessment scoring evidence 與 scorer response 不一致")
        if (
            self.assessment.negative_evidence
            or self.assessment.liquidity is not None
            or self.assessment.missing_data
        ):
            raise ValueError("scorer outcome assessment 不可含未提供的 source evidence")

        if self.response.disposition is ReplayScorerDispositionV1.SCORED:
            if self.assessment.eligible is not True or scoring.passed is not True:
                raise ValueError("scored outcome assessment 必須為 eligible/pass")
            if scoring.reason != "scored" or self.assessment.reasons:
                raise ValueError("scored outcome assessment reason 不一致")
            return

        reason_code = self.response.reason_code
        if (
            reason_code is None
            or self.assessment.eligible is not None
            or self.assessment.reasons != (reason_code,)
            or scoring.passed is not None
            or scoring.reason != reason_code
        ):
            raise ValueError("skipped outcome assessment 必須保留明確 skip reason")

    @property
    def request(self) -> NeedCandidateScoring:
        return self.response.request

    @property
    def disposition(self) -> ReplayScorerDispositionV1:
        return self.response.disposition

    @property
    def item(self) -> RecommendationItem | None:
        return self.response.item

    @property
    def score_ordering(self) -> ReplayScoreOrderingV1 | None:
        return self.response.score_ordering

    @property
    def reason_code(self) -> str | None:
        return self.response.reason_code

    @property
    def error_type(self) -> str | None:
        return self.response.error_type


REPLAY_POST_SCORE_POLICY_VERSION_V1 = "replay-post-score.v1"


class ReplayPostScoreRuleV1(str, Enum):
    """`filter_completed_frame` 的單列最終比較順序。"""

    PRICE_CHANGE_MIN = "price_change_min"
    PRICE_CHANGE_MAX = "price_change_max"
    VOLUME_CHANGE_MIN = "volume_change_min_percent"
    RSI_MIN = "rsi_min"
    RSI_MAX = "rsi_max"


class ReplayPostScoreRuleDispositionV1(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    SKIPPED_MISSING_COLUMN = "skipped_missing_column"
    UNSUPPORTED = "unsupported"
    LEGACY_TYPE_ERROR = "legacy_type_error"


class ReplayPostScoreDispositionV1(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"
    LEGACY_ERROR = "legacy_error"


class ReplayPostScoreMetricLegacyKindV1(str, Enum):
    """少數已由 legacy oracle 凍結、不可合併成 generic unsupported 的 scalar。"""

    PYTHON_DECIMAL_OBJECT = "python_decimal_object"
    PANDAS_OBJECT_NA = "pandas_object_na"


class ReplayPostScoreThresholdInputKindV1(str, Enum):
    """threshold adapter 尚未轉換前可安全傳給 evaluator 的原始型別分類。"""

    PYTHON_STRING = "python_string"
    PYTHON_NONE = "python_none"


class ReplayPostScoreDiagnosticCodeV1(str, Enum):
    PRICE_CHANGE_OBJECT_NA_REJECTED = "price_change_object_na_rejected"


@dataclass(frozen=True, slots=True)
class ReplayPostScoreThresholdInputHintV1:
    """不含原始物件的 threshold 型別與診斷文字提示。"""

    filter_id: ReplayPostScoreRuleV1
    input_kind: ReplayPostScoreThresholdInputKindV1
    display_text: str

    def __post_init__(self) -> None:
        if type(self.filter_id) is not ReplayPostScoreRuleV1:
            raise TypeError("filter_id 必須是 ReplayPostScoreRuleV1")
        if type(self.input_kind) is not ReplayPostScoreThresholdInputKindV1:
            raise TypeError("input_kind 必須是 ReplayPostScoreThresholdInputKindV1")
        if type(self.display_text) is not str:
            raise TypeError("display_text 必須是 str")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreDiagnosticEventV1:
    """純 evaluator 回傳的診斷事件；呼叫端負責套用 warning/counter 副作用。"""

    code: ReplayPostScoreDiagnosticCodeV1
    filter_id: ReplayPostScoreRuleV1
    message: str
    counter_key: str
    counter_delta: int = 1

    def __post_init__(self) -> None:
        if type(self.code) is not ReplayPostScoreDiagnosticCodeV1:
            raise TypeError("code 必須是 ReplayPostScoreDiagnosticCodeV1")
        if type(self.filter_id) is not ReplayPostScoreRuleV1:
            raise TypeError("filter_id 必須是 ReplayPostScoreRuleV1")
        if (
            self.code is ReplayPostScoreDiagnosticCodeV1.PRICE_CHANGE_OBJECT_NA_REJECTED
            and self.filter_id is not ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
        ):
            raise ValueError("object NA diagnostic 只適用 price-change min")
        if type(self.message) is not str or not self.message:
            raise ValueError("message 不可為空")
        if type(self.counter_key) is not str or not self.counter_key.strip():
            raise ValueError("counter_key 不可為空")
        if type(self.counter_delta) is not int or self.counter_delta <= 0:
            raise ValueError("counter_delta 必須是正整數")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreMetricFactV1:
    """由 app numeric projector 投影的單一 scored-row metric。"""

    status: ReplayMetricStatus
    value: ReplayComparisonOperand | None
    unsupported_reason: str | None = None
    legacy_kind: ReplayPostScoreMetricLegacyKindV1 | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not ReplayMetricStatus:
            raise TypeError("status 必須是 ReplayMetricStatus")
        if self.status not in {
            ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
            ReplayMetricStatus.AVAILABLE,
            ReplayMetricStatus.ZERO_DENOMINATOR,
            ReplayMetricStatus.MISSING_COLUMN,
            ReplayMetricStatus.UNSUPPORTED,
        }:
            raise ValueError("post-score metric status 不適用於此 phase")
        if self.status in {
            ReplayMetricStatus.AVAILABLE,
            ReplayMetricStatus.ZERO_DENOMINATOR,
        }:
            if type(self.value) is not ReplayComparisonOperand:
                raise TypeError("available metric 必須是 ReplayComparisonOperand")
        elif self.status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
            if self.value is not None:
                raise ValueError("awaiting metric 不可先帶 comparison value")
        elif self.value is not None:
            raise ValueError("missing/unsupported metric 不可帶 comparison value")

        if self.status is ReplayMetricStatus.ZERO_DENOMINATOR:
            value = self.value
            if (
                type(value) is not ReplayComparisonOperand
                or value.imaginary is not None
                or value.real.kind is not ReplayComparisonKind.FINITE
                or value.real.numerator != 0
            ):
                raise ValueError("ZERO_DENOMINATOR metric 必須是有限實數 0")

        if self.status is ReplayMetricStatus.UNSUPPORTED:
            if type(self.unsupported_reason) is not str or not self.unsupported_reason.strip():
                raise ValueError("unsupported metric 必須提供原因碼")
        elif self.unsupported_reason is not None:
            raise ValueError("非 unsupported metric 不可帶 unsupported_reason")
        if self.legacy_kind is not None:
            if type(self.legacy_kind) is not ReplayPostScoreMetricLegacyKindV1:
                raise TypeError("legacy_kind 必須是 ReplayPostScoreMetricLegacyKindV1 或 None")
            if self.status not in {
                ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
                ReplayMetricStatus.UNSUPPORTED,
            }:
                raise ValueError("legacy_kind 僅可搭配 awaiting/unsupported metric")


@dataclass(frozen=True, slots=True, eq=False)
class _ReplayPostScoreFactsIdentityTokenV1:
    """Opaque token whose identity binds staged projections to one facts object."""


@dataclass(frozen=True, slots=True)
class ReplayPostScoreFactsV1:
    """同一 scorer request 的最後一列 metric；不含 DataFrame 或 row dict。"""

    request: NeedCandidateScoring
    price_change: ReplayPostScoreMetricFactV1
    volume_change_percent: ReplayPostScoreMetricFactV1
    rsi: ReplayPostScoreMetricFactV1
    rsi_source_column: str | None
    identity_token: _ReplayPostScoreFactsIdentityTokenV1 = field(
        default_factory=_ReplayPostScoreFactsIdentityTokenV1,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if type(self.request) is not NeedCandidateScoring:
            raise TypeError("request 必須是 NeedCandidateScoring")
        if type(self.identity_token) is not _ReplayPostScoreFactsIdentityTokenV1:
            raise TypeError("identity_token 必須是 process-local scored-facts token")
        for name in ("price_change", "volume_change_percent", "rsi"):
            if type(getattr(self, name)) is not ReplayPostScoreMetricFactV1:
                raise TypeError(f"{name} 必須是 ReplayPostScoreMetricFactV1")
        if self.rsi_source_column is not None:
            if type(self.rsi_source_column) is not str:
                raise TypeError("rsi_source_column 必須是 str 或 None")
            if self.rsi_source_column not in {"RSI", "rsi", "RSI_14"}:
                raise ValueError("rsi_source_column 必須遵守 legacy alias 名稱")
        if self.rsi_source_column is None:
            if self.rsi.status is not ReplayMetricStatus.MISSING_COLUMN:
                raise ValueError("沒有 RSI 欄位時必須明示 MISSING_COLUMN")
        elif self.rsi.status is ReplayMetricStatus.MISSING_COLUMN:
            raise ValueError("有 RSI 欄位時不可標示 MISSING_COLUMN")


@dataclass(frozen=True, slots=True)
class ReplayScoredRowReadyV1:
    """非空 scorer row 的 request-bound facts；尚未建立 item 或 v1 row。"""

    request: NeedCandidateScoring
    facts: ReplayPostScoreFactsV1

    def __post_init__(self) -> None:
        if type(self.request) is not NeedCandidateScoring:
            raise TypeError("request 必須是 NeedCandidateScoring")
        if type(self.facts) is not ReplayPostScoreFactsV1:
            raise TypeError("facts 必須是 ReplayPostScoreFactsV1")
        if self.facts.request != self.request:
            raise SourceFactMismatchError("scored-row facts 不屬於 scorer request")


@dataclass(frozen=True, slots=True)
class ReplayPostScorePolicyV1:
    """已由 app boundary 投影的最終 post-score 門檻，不含原始 config。"""

    invocation_id: str
    price_change_min: ReplayThreshold = ReplayThreshold()
    price_change_max: ReplayThreshold = ReplayThreshold()
    volume_change_min_percent: ReplayThreshold = ReplayThreshold()
    rsi_min: ReplayThreshold = ReplayThreshold()
    rsi_max: ReplayThreshold = ReplayThreshold()
    version: str = REPLAY_POST_SCORE_POLICY_VERSION_V1

    def __post_init__(self) -> None:
        if type(self.invocation_id) is not str or not self.invocation_id.strip():
            raise ValueError("invocation_id 不可為空")
        if self.version != REPLAY_POST_SCORE_POLICY_VERSION_V1:
            raise ValueError("不支援的 replay post-score policy version")
        for name in (
            "price_change_min",
            "price_change_max",
            "volume_change_min_percent",
            "rsi_min",
            "rsi_max",
        ):
            threshold = getattr(self, name)
            if type(threshold) is not ReplayThreshold:
                raise TypeError(f"{name} 必須是 ReplayThreshold")
            if threshold.status is ReplayThresholdStatus.PENDING:
                raise ValueError("post-score policy 不可保留 pending threshold")
            if threshold.status is ReplayThresholdStatus.ENABLED and type(
                threshold.value
            ) is not ReplayComparisonOperand:
                raise TypeError(
                    "enabled post-score threshold 必須是 numeric projector 的 operand"
                )


@dataclass(frozen=True, slots=True)
class ReplayPostScoreRuleOutcomeV1:
    filter_id: ReplayPostScoreRuleV1
    disposition: ReplayPostScoreRuleDispositionV1
    reason_code: str
    threshold_input_hint: ReplayPostScoreThresholdInputHintV1 | None = None
    legacy_exception_type: str | None = None
    legacy_exception_message: str | None = None
    diagnostic_event: ReplayPostScoreDiagnosticEventV1 | None = None

    def __post_init__(self) -> None:
        if type(self.filter_id) is not ReplayPostScoreRuleV1:
            raise TypeError("filter_id 必須是 ReplayPostScoreRuleV1")
        if type(self.disposition) is not ReplayPostScoreRuleDispositionV1:
            raise TypeError("disposition 必須是 ReplayPostScoreRuleDispositionV1")
        if type(self.reason_code) is not str or not self.reason_code.strip():
            raise ValueError("reason_code 不可為空")
        if self.threshold_input_hint is not None:
            if type(self.threshold_input_hint) is not ReplayPostScoreThresholdInputHintV1:
                raise TypeError("threshold_input_hint 型別錯誤")
            if self.threshold_input_hint.filter_id is not self.filter_id:
                raise ValueError("threshold_input_hint 不屬於目前 filter")
        if self.disposition is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR:
            if self.legacy_exception_type != "TypeError":
                raise ValueError("legacy type error 必須明示 TypeError")
            if type(self.legacy_exception_message) is not str or not self.legacy_exception_message:
                raise ValueError("legacy type error 必須明示原生錯誤訊息")
            if self.threshold_input_hint is None or self.diagnostic_event is not None:
                raise ValueError("legacy type error 必須保留 threshold hint 且不可帶診斷事件")
            if (
                self.filter_id is not ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
                or self.threshold_input_hint.input_kind
                is not ReplayPostScoreThresholdInputKindV1.PYTHON_STRING
            ):
                raise ValueError("legacy Decimal/string error 只適用 price-change min")
        elif self.legacy_exception_type is not None or self.legacy_exception_message is not None:
            raise ValueError("非 legacy type error 不可帶原生例外欄位")
        if self.diagnostic_event is not None:
            if type(self.diagnostic_event) is not ReplayPostScoreDiagnosticEventV1:
                raise TypeError("diagnostic_event 型別錯誤")
            if (
                self.disposition is not ReplayPostScoreRuleDispositionV1.REJECTED
                or self.diagnostic_event.filter_id is not self.filter_id
                or self.threshold_input_hint is None
                or self.threshold_input_hint.input_kind
                is not ReplayPostScoreThresholdInputKindV1.PYTHON_STRING
            ):
                raise ValueError("diagnostic_event 必須綁定目前 rejected rule 與原始 threshold hint")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreOutcomeV1:
    """單列最後過濾結果；diagnostic passes 與其副作用留在 app。"""

    request: NeedCandidateScoring
    disposition: ReplayPostScoreDispositionV1
    rules: tuple[ReplayPostScoreRuleOutcomeV1, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not NeedCandidateScoring:
            raise TypeError("request 必須是 NeedCandidateScoring")
        if type(self.disposition) is not ReplayPostScoreDispositionV1:
            raise TypeError("disposition 必須是 ReplayPostScoreDispositionV1")
        if type(self.rules) is not tuple or any(
            type(rule) is not ReplayPostScoreRuleOutcomeV1 for rule in self.rules
        ):
            raise TypeError("rules 必須是 ReplayPostScoreRuleOutcomeV1 tuple")
        order = {rule: index for index, rule in enumerate(ReplayPostScoreRuleV1)}
        positions = tuple(order[rule.filter_id] for rule in self.rules)
        if positions != tuple(sorted(set(positions))):
            raise ValueError("post-score rules 必須唯一且依 legacy 順序排列")
        expected = (
            ReplayPostScoreDispositionV1.LEGACY_ERROR
            if any(
                rule.disposition is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR
                for rule in self.rules
            )
            else ReplayPostScoreDispositionV1.UNSUPPORTED
            if any(
                rule.disposition is ReplayPostScoreRuleDispositionV1.UNSUPPORTED
                for rule in self.rules
            )
            else ReplayPostScoreDispositionV1.REJECTED
            if any(
                rule.disposition is ReplayPostScoreRuleDispositionV1.REJECTED
                for rule in self.rules
            )
            else ReplayPostScoreDispositionV1.ACCEPTED
        )
        if self.disposition is not expected:
            raise ValueError("overall disposition 與 filter outcomes 不一致")
        legacy_errors = tuple(
            index
            for index, rule in enumerate(self.rules)
            if rule.disposition is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR
        )
        if legacy_errors and legacy_errors != (len(self.rules) - 1,):
            raise ValueError("legacy type error 必須是最後已評估的 rule")


REPLAY_POST_SCORE_DEFERRED_POLICY_VERSION_V1 = "replay-post-score-deferred.v1"


@dataclass(frozen=True, slots=True)
class ReplayPostScoreDeferredPolicyV1:
    """已知哪些 filter key 存在、但尚未解析其值的 call-local policy。"""

    policy: ReplayPostScorePolicyV1
    deferred_rules: tuple[ReplayPostScoreRuleV1, ...]
    version: str = REPLAY_POST_SCORE_DEFERRED_POLICY_VERSION_V1
    threshold_input_hints: tuple[ReplayPostScoreThresholdInputHintV1, ...] = ()

    def __post_init__(self) -> None:
        if type(self.policy) is not ReplayPostScorePolicyV1:
            raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
        if self.version != REPLAY_POST_SCORE_DEFERRED_POLICY_VERSION_V1:
            raise ValueError("不支援的 replay deferred post-score policy version")
        if type(self.deferred_rules) is not tuple or any(
            type(rule) is not ReplayPostScoreRuleV1 for rule in self.deferred_rules
        ):
            raise TypeError("deferred_rules 必須是 ReplayPostScoreRuleV1 tuple")
        positions = tuple(
            _replay_post_score_rule_index(rule) for rule in self.deferred_rules
        )
        if positions != tuple(sorted(set(positions))):
            raise ValueError("deferred_rules 必須唯一且依 legacy 順序排列")
        for rule in self.deferred_rules:
            if _replay_post_score_policy_threshold(self.policy, rule).status is not ReplayThresholdStatus.DISABLED:
                raise ValueError("deferred rule 的 policy slot 必須先保持 disabled")
        if type(self.threshold_input_hints) is not tuple or any(
            type(hint) is not ReplayPostScoreThresholdInputHintV1
            for hint in self.threshold_input_hints
        ):
            raise TypeError("threshold_input_hints 必須是明示 typed hint tuple")
        hint_rules = tuple(hint.filter_id for hint in self.threshold_input_hints)
        if hint_rules != tuple(
            rule for rule in self.deferred_rules if rule in hint_rules
        ) or len(set(hint_rules)) != len(hint_rules):
            raise ValueError("threshold hints 必須唯一且依 deferred rule 順序排列")
        if any(rule not in self.deferred_rules for rule in hint_rules):
            raise ValueError("threshold hint 必須綁定 deferred rule")


@dataclass(frozen=True, slots=True)
class NeedReplayPostScoreThresholdV1:
    """要求 app 僅解析目前 filter stage 的原始 threshold。"""

    request_id: str
    candidate_request: NeedCandidateScoring
    filter_id: ReplayPostScoreRuleV1
    facts_identity_token: _ReplayPostScoreFactsIdentityTokenV1

    def __post_init__(self) -> None:
        if type(self.request_id) is not str or not self.request_id.strip():
            raise ValueError("request_id 不可為空")
        if type(self.candidate_request) is not NeedCandidateScoring:
            raise TypeError("candidate_request 必須是 NeedCandidateScoring")
        if type(self.filter_id) is not ReplayPostScoreRuleV1:
            raise TypeError("filter_id 必須是 ReplayPostScoreRuleV1")
        if type(self.facts_identity_token) is not _ReplayPostScoreFactsIdentityTokenV1:
            raise TypeError("facts_identity_token 必須是 process-local scored-facts token")


@dataclass(frozen=True, slots=True)
class ReplayPostScorePairedMetricV1:
    """與單一 deferred threshold request 綁定的暫時 metric 投影。"""

    request: NeedReplayPostScoreThresholdV1
    metric: ReplayPostScoreMetricFactV1

    def __post_init__(self) -> None:
        if type(self.request) is not NeedReplayPostScoreThresholdV1:
            raise TypeError("request 必須是 NeedReplayPostScoreThresholdV1")
        if type(self.metric) is not ReplayPostScoreMetricFactV1:
            raise TypeError("metric 必須是 ReplayPostScoreMetricFactV1")
        if self.metric.status not in {
            ReplayMetricStatus.AVAILABLE,
            ReplayMetricStatus.ZERO_DENOMINATOR,
        }:
            raise ValueError("paired metric 必須是已投影的 numeric metric")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreThresholdResponseV1:
    """app 對單一 deferred threshold request 的已投影 numeric 回覆。"""

    request: NeedReplayPostScoreThresholdV1
    threshold: ReplayThreshold
    paired_metric: ReplayPostScorePairedMetricV1 | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not NeedReplayPostScoreThresholdV1:
            raise TypeError("request 必須是 NeedReplayPostScoreThresholdV1")
        if type(self.threshold) is not ReplayThreshold:
            raise TypeError("threshold 必須是 ReplayThreshold")
        if self.threshold.status not in {
            ReplayThresholdStatus.ENABLED,
            ReplayThresholdStatus.UNSUPPORTED,
        }:
            raise ValueError("deferred threshold response 必須為 enabled 或 unsupported")
        if self.paired_metric is not None:
            if type(self.paired_metric) is not ReplayPostScorePairedMetricV1:
                raise TypeError("paired_metric 必須是 ReplayPostScorePairedMetricV1 或 None")
            if self.threshold.status is not ReplayThresholdStatus.ENABLED:
                raise ValueError("只有 enabled threshold 可攜帶 paired metric")
            if self.paired_metric.request != self.request:
                raise SourceFactMismatchError("paired metric 不屬於目前 threshold request")
            metric_value = self.paired_metric.metric.value
            threshold_value = self.threshold.value
            if (
                type(metric_value) is not ReplayComparisonOperand
                or type(threshold_value) is not ReplayComparisonOperand
            ):
                raise ValueError("paired metric/threshold 必須帶 numeric operand")
            if metric_value.domain != threshold_value.domain:
                raise ValueError("paired metric 與 threshold comparison domain 不一致")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreEvaluationStateV1:
    """逐 stage 回填 threshold 的 immutable evaluator 狀態。"""

    ready: ReplayScoredRowReadyV1
    deferred_policy: ReplayPostScoreDeferredPolicyV1
    next_rule_index: int = 0
    rules: tuple[ReplayPostScoreRuleOutcomeV1, ...] = ()
    pending: NeedReplayPostScoreThresholdV1 | None = None
    outcome: ReplayPostScoreOutcomeV1 | None = None

    def __post_init__(self) -> None:
        if type(self.ready) is not ReplayScoredRowReadyV1:
            raise TypeError("ready 必須是 ReplayScoredRowReadyV1")
        if type(self.deferred_policy) is not ReplayPostScoreDeferredPolicyV1:
            raise TypeError("deferred_policy 必須是 ReplayPostScoreDeferredPolicyV1")
        if self.deferred_policy.policy.invocation_id != self.ready.request.invocation_id:
            raise ValueError("deferred policy invocation 不一致")
        if type(self.next_rule_index) is not int or not (
            0 <= self.next_rule_index <= len(ReplayPostScoreRuleV1)
        ):
            raise ValueError("next_rule_index 超出 post-score stage 範圍")
        if type(self.rules) is not tuple or any(
            type(rule) is not ReplayPostScoreRuleOutcomeV1 for rule in self.rules
        ):
            raise TypeError("rules 必須是 ReplayPostScoreRuleOutcomeV1 tuple")
        rule_positions = tuple(
            _replay_post_score_rule_index(rule.filter_id) for rule in self.rules
        )
        if rule_positions != tuple(sorted(set(rule_positions))) or any(
            position >= self.next_rule_index for position in rule_positions
        ):
            raise ValueError("已評估 post-score rules 必須依序位於目前 stage 之前")
        if any(
            _replay_post_score_rule_index(rule) < self.next_rule_index
            for rule in self.deferred_policy.deferred_rules
        ):
            raise ValueError("尚未要求的 deferred threshold 不可落後於目前 stage")
        if self.pending is not None:
            if type(self.pending) is not NeedReplayPostScoreThresholdV1:
                raise TypeError("pending 必須是 NeedReplayPostScoreThresholdV1")
            if self.next_rule_index >= len(ReplayPostScoreRuleV1):
                raise ValueError("terminal stage 不可再要求 threshold")
            expected_rule = tuple(ReplayPostScoreRuleV1)[self.next_rule_index]
            if (
                self.pending.candidate_request != self.ready.request
                or self.pending.filter_id is not expected_rule
                or self.pending.facts_identity_token is not self.ready.facts.identity_token
                or expected_rule not in self.deferred_policy.deferred_rules
                or self.pending.request_id
                != _replay_request_id(
                    invocation_id=self.ready.request.invocation_id,
                    stock_code=self.ready.request.stock_code,
                    as_of_date=self.ready.request.as_of_date,
                    ordinal=self.next_rule_index,
                    kind=f"post_score_threshold:{expected_rule.value}",
                )
            ):
                raise ValueError("pending threshold identity/stage 不一致")
        if self.outcome is not None:
            if type(self.outcome) is not ReplayPostScoreOutcomeV1:
                raise TypeError("outcome 必須是 ReplayPostScoreOutcomeV1")
            if (
                self.pending is not None
                or self.next_rule_index != len(ReplayPostScoreRuleV1)
                or self.deferred_policy.deferred_rules
                or self.outcome.request != self.ready.request
                or self.outcome.rules != self.rules
            ):
                raise ValueError("completed post-score state identity 不一致")


@dataclass(frozen=True, slots=True)
class ReplayPostScoreEvaluationStepV1:
    """每次 staged evaluation 只回一個 threshold request 或 terminal outcome。"""

    state: ReplayPostScoreEvaluationStateV1
    request: NeedReplayPostScoreThresholdV1 | None = None
    outcome: ReplayPostScoreOutcomeV1 | None = None

    def __post_init__(self) -> None:
        if type(self.state) is not ReplayPostScoreEvaluationStateV1:
            raise TypeError("state 必須是 ReplayPostScoreEvaluationStateV1")
        if (self.request is None) == (self.outcome is None):
            raise ValueError("step 必須且只能包含 request 或 outcome")
        if self.request != self.state.pending or self.outcome != self.state.outcome:
            raise ValueError("step payload 必須與 evaluator state 一致")


class _ReplayPostScoreRuleNeedsThreshold(Enum):
    INSTANCE = "needs_threshold"


@dataclass(frozen=True, slots=True)
class _ReplayPostScoreRuleSpecV1:
    filter_id: ReplayPostScoreRuleV1
    threshold: ReplayThreshold
    metric: ReplayPostScoreMetricFactV1
    operator: ReplayComparisonOperator
    failure_reason: str
    threshold_input_hint: ReplayPostScoreThresholdInputHintV1 | None = None


def _replay_post_score_rule_index(rule: ReplayPostScoreRuleV1) -> int:
    if type(rule) is not ReplayPostScoreRuleV1:
        raise TypeError("rule 必須是 ReplayPostScoreRuleV1")
    return tuple(ReplayPostScoreRuleV1).index(rule)


def _replay_post_score_policy_threshold(
    policy: ReplayPostScorePolicyV1,
    rule: ReplayPostScoreRuleV1,
) -> ReplayThreshold:
    if type(policy) is not ReplayPostScorePolicyV1:
        raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
    if type(rule) is not ReplayPostScoreRuleV1:
        raise TypeError("rule 必須是 ReplayPostScoreRuleV1")
    threshold = getattr(policy, rule.value)
    if type(threshold) is not ReplayThreshold:
        raise AssertionError("post-score policy threshold contract 不一致")
    return threshold


def _replace_replay_post_score_threshold(
    policy: ReplayPostScorePolicyV1,
    rule: ReplayPostScoreRuleV1,
    threshold: ReplayThreshold,
) -> ReplayPostScorePolicyV1:
    if rule is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN:
        return replace(policy, price_change_min=threshold)
    if rule is ReplayPostScoreRuleV1.PRICE_CHANGE_MAX:
        return replace(policy, price_change_max=threshold)
    if rule is ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN:
        return replace(policy, volume_change_min_percent=threshold)
    if rule is ReplayPostScoreRuleV1.RSI_MIN:
        return replace(policy, rsi_min=threshold)
    if rule is ReplayPostScoreRuleV1.RSI_MAX:
        return replace(policy, rsi_max=threshold)
    raise AssertionError("未知 replay post-score rule")


def _replay_post_score_rule_specs(
    facts: ReplayPostScoreFactsV1,
    policy: ReplayPostScorePolicyV1,
    threshold_input_hints: tuple[ReplayPostScoreThresholdInputHintV1, ...] = (),
) -> tuple[_ReplayPostScoreRuleSpecV1, ...]:
    if type(facts) is not ReplayPostScoreFactsV1:
        raise TypeError("facts 必須是 ReplayPostScoreFactsV1")
    if type(policy) is not ReplayPostScorePolicyV1:
        raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
    if type(threshold_input_hints) is not tuple or any(
        type(hint) is not ReplayPostScoreThresholdInputHintV1
        for hint in threshold_input_hints
    ):
        raise TypeError("threshold_input_hints 必須是 typed tuple")
    hints_by_rule = {hint.filter_id: hint for hint in threshold_input_hints}
    return (
        _ReplayPostScoreRuleSpecV1(
            ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
            policy.price_change_min,
            facts.price_change,
            ReplayComparisonOperator.GREATER_THAN_OR_EQUAL,
            "below_minimum",
            hints_by_rule.get(ReplayPostScoreRuleV1.PRICE_CHANGE_MIN),
        ),
        _ReplayPostScoreRuleSpecV1(
            ReplayPostScoreRuleV1.PRICE_CHANGE_MAX,
            policy.price_change_max,
            facts.price_change,
            ReplayComparisonOperator.LESS_THAN_OR_EQUAL,
            "above_maximum",
            hints_by_rule.get(ReplayPostScoreRuleV1.PRICE_CHANGE_MAX),
        ),
        _ReplayPostScoreRuleSpecV1(
            ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN,
            policy.volume_change_min_percent,
            facts.volume_change_percent,
            ReplayComparisonOperator.GREATER_THAN_OR_EQUAL,
            "below_minimum",
            hints_by_rule.get(ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN),
        ),
        _ReplayPostScoreRuleSpecV1(
            ReplayPostScoreRuleV1.RSI_MIN,
            policy.rsi_min,
            facts.rsi,
            ReplayComparisonOperator.GREATER_THAN_OR_EQUAL,
            "below_minimum",
            hints_by_rule.get(ReplayPostScoreRuleV1.RSI_MIN),
        ),
        _ReplayPostScoreRuleSpecV1(
            ReplayPostScoreRuleV1.RSI_MAX,
            policy.rsi_max,
            facts.rsi,
            ReplayComparisonOperator.LESS_THAN_OR_EQUAL,
            "above_maximum",
            hints_by_rule.get(ReplayPostScoreRuleV1.RSI_MAX),
        ),
    )


def _evaluate_replay_post_score_rule(
    spec: _ReplayPostScoreRuleSpecV1,
) -> ReplayPostScoreRuleOutcomeV1 | None | _ReplayPostScoreRuleNeedsThreshold:
    """唯一 post-score 單規則核心；pending 只供 staged adapter 暫停。"""

    threshold = spec.threshold
    metric = spec.metric
    filter_id = spec.filter_id
    if threshold.status is ReplayThresholdStatus.DISABLED:
        return None
    if metric.status is ReplayMetricStatus.MISSING_COLUMN:
        return ReplayPostScoreRuleOutcomeV1(
            filter_id,
            ReplayPostScoreRuleDispositionV1.SKIPPED_MISSING_COLUMN,
            "missing_column",
        )
    if (
        threshold.status is ReplayThresholdStatus.PENDING
        and spec.threshold_input_hint is not None
        and spec.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
        and spec.threshold_input_hint.input_kind
        is ReplayPostScoreThresholdInputKindV1.PYTHON_STRING
    ):
        if metric.legacy_kind is ReplayPostScoreMetricLegacyKindV1.PYTHON_DECIMAL_OBJECT:
            return ReplayPostScoreRuleOutcomeV1(
                filter_id,
                ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR,
                "legacy_decimal_string_type_error",
                threshold_input_hint=spec.threshold_input_hint,
                legacy_exception_type="TypeError",
                legacy_exception_message=(
                    "'>=' not supported between instances of 'decimal.Decimal' and 'str'"
                ),
            )
        if metric.legacy_kind is ReplayPostScoreMetricLegacyKindV1.PANDAS_OBJECT_NA:
            return ReplayPostScoreRuleOutcomeV1(
                filter_id,
                ReplayPostScoreRuleDispositionV1.REJECTED,
                "legacy_object_na_rejected",
                threshold_input_hint=spec.threshold_input_hint,
                diagnostic_event=ReplayPostScoreDiagnosticEventV1(
                    code=ReplayPostScoreDiagnosticCodeV1.PRICE_CHANGE_OBJECT_NA_REJECTED,
                    filter_id=filter_id,
                    message=(
                        "[漲幅篩選] 要求 >= "
                        f"{spec.threshold_input_hint.display_text}%, 但樣本值=<NA>%"
                    ),
                    counter_key="StrategyConfigurator._price_filter_log_count",
                ),
            )
    if threshold.status is ReplayThresholdStatus.PENDING:
        return _ReplayPostScoreRuleNeedsThreshold.INSTANCE
    if metric.status is ReplayMetricStatus.UNSUPPORTED:
        return ReplayPostScoreRuleOutcomeV1(
            filter_id,
            ReplayPostScoreRuleDispositionV1.UNSUPPORTED,
            metric.unsupported_reason or "unsupported_metric",
        )
    if threshold.status is ReplayThresholdStatus.UNSUPPORTED:
        if (
            spec.threshold_input_hint is not None
            and spec.threshold_input_hint.input_kind
            is ReplayPostScoreThresholdInputKindV1.PYTHON_NONE
        ):
            return ReplayPostScoreRuleOutcomeV1(
                filter_id,
                ReplayPostScoreRuleDispositionV1.REJECTED,
                "legacy_none_threshold_rejected",
                threshold_input_hint=spec.threshold_input_hint,
            )
        return ReplayPostScoreRuleOutcomeV1(
            filter_id,
            ReplayPostScoreRuleDispositionV1.UNSUPPORTED,
            threshold.unsupported_reason or "unsupported_threshold",
        )
    if metric.status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
        raise ValueError("awaiting metric 必須由目前 threshold response 成對投影")
    if threshold.status is not ReplayThresholdStatus.ENABLED:
        raise AssertionError("post-score threshold 未解析")

    observed = metric.value
    required = threshold.value
    if type(observed) is not ReplayComparisonOperand or type(
        required
    ) is not ReplayComparisonOperand:
        raise AssertionError("enabled post-score comparison 缺少 typed operands")
    comparison: ReplayComparisonResult = compare_replay_operands_with_status(
        observed,
        required,
        operator=spec.operator,
    )
    if comparison.unordered:
        disposition = ReplayPostScoreRuleDispositionV1.REJECTED
        reason_code = "unordered_value"
    elif not comparison.matched:
        disposition = ReplayPostScoreRuleDispositionV1.REJECTED
        reason_code = spec.failure_reason
    else:
        disposition = ReplayPostScoreRuleDispositionV1.PASSED
        reason_code = "passed"
    return ReplayPostScoreRuleOutcomeV1(filter_id, disposition, reason_code)


def _replay_post_score_outcome(
    request: NeedCandidateScoring,
    rules: tuple[ReplayPostScoreRuleOutcomeV1, ...],
) -> ReplayPostScoreOutcomeV1:
    overall = (
        ReplayPostScoreDispositionV1.LEGACY_ERROR
        if any(
            rule.disposition is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR
            for rule in rules
        )
        else ReplayPostScoreDispositionV1.UNSUPPORTED
        if any(
            rule.disposition is ReplayPostScoreRuleDispositionV1.UNSUPPORTED
            for rule in rules
        )
        else ReplayPostScoreDispositionV1.REJECTED
        if any(
            rule.disposition is ReplayPostScoreRuleDispositionV1.REJECTED
            for rule in rules
        )
        else ReplayPostScoreDispositionV1.ACCEPTED
    )
    return ReplayPostScoreOutcomeV1(request, overall, rules)


def _evaluate_replay_post_score(
    scoring: ReplayCandidateScoringOutcomeV1,
    facts: ReplayPostScoreFactsV1,
    policy: ReplayPostScorePolicyV1,
) -> ReplayPostScoreOutcomeV1:
    if type(scoring) is not ReplayCandidateScoringOutcomeV1:
        raise TypeError("scoring 必須是 ReplayCandidateScoringOutcomeV1")
    if type(facts) is not ReplayPostScoreFactsV1:
        raise TypeError("facts 必須是 ReplayPostScoreFactsV1")
    if type(policy) is not ReplayPostScorePolicyV1:
        raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
    if scoring.disposition is not ReplayScorerDispositionV1.SCORED or scoring.item is None:
        raise ValueError("post-score phase 只接受 scored terminal")
    if facts.request != scoring.request:
        raise SourceFactMismatchError("post-score facts 不屬於目前 scorer request")
    if scoring.item.stock_code != facts.request.stock_code:
        raise SourceFactMismatchError("scored item 與 post-score candidate 不一致")

    return _evaluate_replay_post_score_facts(scoring.request, facts, policy)


def _evaluate_replay_post_score_ready(
    ready: ReplayScoredRowReadyV1,
    policy: ReplayPostScorePolicyV1,
) -> ReplayPostScoreOutcomeV1:
    if type(ready) is not ReplayScoredRowReadyV1:
        raise TypeError("ready 必須是 ReplayScoredRowReadyV1")
    if type(policy) is not ReplayPostScorePolicyV1:
        raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
    return _evaluate_replay_post_score_facts(ready.request, ready.facts, policy)


def _evaluate_replay_post_score_facts(
    request: NeedCandidateScoring,
    facts: ReplayPostScoreFactsV1,
    policy: ReplayPostScorePolicyV1,
) -> ReplayPostScoreOutcomeV1:
    """只依同一 scorer request 與 typed facts 執行共用純規則核心。"""

    if type(request) is not NeedCandidateScoring:
        raise TypeError("request 必須是 NeedCandidateScoring")
    if type(facts) is not ReplayPostScoreFactsV1:
        raise TypeError("facts 必須是 ReplayPostScoreFactsV1")
    if type(policy) is not ReplayPostScorePolicyV1:
        raise TypeError("policy 必須是 ReplayPostScorePolicyV1")
    if facts.request != request:
        raise SourceFactMismatchError("post-score facts 不屬於目前 scorer request")
    if policy.invocation_id != facts.request.invocation_id:
        raise ValueError("post-score policy invocation 不一致")

    rules: list[ReplayPostScoreRuleOutcomeV1] = []
    for spec in _replay_post_score_rule_specs(facts, policy):
        rule_outcome = _evaluate_replay_post_score_rule(spec)
        if rule_outcome is _ReplayPostScoreRuleNeedsThreshold.INSTANCE:
            raise ValueError("eager post-score policy 不可保留 pending threshold")
        if rule_outcome is not None:
            rules.append(rule_outcome)
    return _replay_post_score_outcome(facts.request, tuple(rules))


def _advance_replay_post_score_state(
    state: ReplayPostScoreEvaluationStateV1,
    *,
    paired_metric_rule: ReplayPostScoreRuleV1 | None = None,
    paired_metric: ReplayPostScoreMetricFactV1 | None = None,
) -> ReplayPostScoreEvaluationStepV1:
    if type(state) is not ReplayPostScoreEvaluationStateV1:
        raise TypeError("state 必須是 ReplayPostScoreEvaluationStateV1")
    if state.pending is not None or state.outcome is not None:
        raise ValueError("只能推進沒有 pending request 的 post-score state")
    if (paired_metric_rule is None) != (paired_metric is None):
        raise ValueError("paired metric rule/value 必須同時提供")
    if paired_metric_rule is not None:
        if type(paired_metric_rule) is not ReplayPostScoreRuleV1:
            raise TypeError("paired_metric_rule 必須是 ReplayPostScoreRuleV1")
        if type(paired_metric) is not ReplayPostScoreMetricFactV1:
            raise TypeError("paired_metric 必須是 ReplayPostScoreMetricFactV1")
        if paired_metric.status not in {
            ReplayMetricStatus.AVAILABLE,
            ReplayMetricStatus.ZERO_DENOMINATOR,
        }:
            raise ValueError("paired metric 必須是已投影的 numeric metric")

    specs = _replay_post_score_rule_specs(
        state.ready.facts,
        state.deferred_policy.policy,
        state.deferred_policy.threshold_input_hints,
    )
    rules = list(state.rules)
    deferred_policy = state.deferred_policy
    rule_index = state.next_rule_index
    while rule_index < len(specs):
        spec = specs[rule_index]
        if paired_metric_rule is spec.filter_id:
            if spec.metric.status is not ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
                raise SourceFactMismatchError(
                    "paired metric 只可替換目前 rule 的 awaiting metric"
                )
            assert paired_metric is not None
            spec = replace(spec, metric=paired_metric)
        is_deferred = spec.filter_id in deferred_policy.deferred_rules
        if is_deferred:
            spec = replace(spec, threshold=ReplayThreshold.pending())

        rule_outcome = _evaluate_replay_post_score_rule(spec)
        if rule_outcome is _ReplayPostScoreRuleNeedsThreshold.INSTANCE:
            request = NeedReplayPostScoreThresholdV1(
                request_id=_replay_request_id(
                    invocation_id=state.ready.request.invocation_id,
                    stock_code=state.ready.request.stock_code,
                    as_of_date=state.ready.request.as_of_date,
                    ordinal=rule_index,
                    kind=f"post_score_threshold:{spec.filter_id.value}",
                ),
                candidate_request=state.ready.request,
                filter_id=spec.filter_id,
                facts_identity_token=state.ready.facts.identity_token,
            )
            next_state = replace(
                state,
                deferred_policy=deferred_policy,
                next_rule_index=rule_index,
                rules=tuple(rules),
                pending=request,
            )
            return ReplayPostScoreEvaluationStepV1(
                state=next_state,
                request=request,
            )

        if is_deferred:
            deferred_policy = replace(
                deferred_policy,
                deferred_rules=tuple(
                    rule
                    for rule in deferred_policy.deferred_rules
                    if rule is not spec.filter_id
                ),
                threshold_input_hints=tuple(
                    hint
                    for hint in deferred_policy.threshold_input_hints
                    if hint.filter_id is not spec.filter_id
                ),
            )
        if rule_outcome is not None:
            rules.append(rule_outcome)
        if (
            rule_outcome is not None
            and rule_outcome.disposition
            is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR
        ):
            outcome = _replay_post_score_outcome(
                state.ready.request,
                tuple(rules),
            )
            terminal_policy = replace(
                deferred_policy,
                deferred_rules=(),
                threshold_input_hints=(),
            )
            next_state = replace(
                state,
                deferred_policy=terminal_policy,
                next_rule_index=len(specs),
                rules=tuple(rules),
                pending=None,
                outcome=outcome,
            )
            return ReplayPostScoreEvaluationStepV1(
                state=next_state,
                outcome=outcome,
            )
        rule_index += 1

    outcome = _replay_post_score_outcome(state.ready.request, tuple(rules))
    next_state = replace(
        state,
        deferred_policy=deferred_policy,
        next_rule_index=len(specs),
        rules=tuple(rules),
        pending=None,
        outcome=outcome,
    )
    return ReplayPostScoreEvaluationStepV1(state=next_state, outcome=outcome)


def _replay_scorer_reason_code(
    disposition: ReplayScorerDispositionV1,
) -> str | None:
    if disposition is ReplayScorerDispositionV1.SCORED:
        return None
    if disposition is ReplayScorerDispositionV1.SKIPPED_EMPTY:
        return "scorer_empty_result"
    if disposition is ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION:
        return "scorer_exception"
    if disposition is ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION:
        return "item_projection_exception"
    raise AssertionError("unsupported replay scorer disposition")


def _replay_scoring_assessment(
    response: ReplayScorerResponseV1,
) -> CandidateAssessment:
    request = response.request
    prefilter = FilterOutcome(
        filter_id="replay_prefilter",
        passed=True,
        reason="ready",
        evidence={
            "as_of_date": request.as_of_date.isoformat(),
            "history_rows": request.history_rows,
            "reason_code": request.prefilter_outcome.reason_code,
            "stage": request.prefilter_outcome.stage.value,
        },
    )
    if response.disposition is ReplayScorerDispositionV1.SCORED:
        scoring = FilterOutcome(
            filter_id="replay_scoring",
            passed=True,
            reason="scored",
            evidence={
                "request_id": request.request_id,
                "disposition": response.disposition.value,
                "error_type": None,
            },
        )
        return CandidateAssessment(
            stock_code=request.stock_code,
            eligible=True,
            filter_outcomes={
                "replay_prefilter": prefilter,
                "replay_scoring": scoring,
            },
        )

    reason_code = response.reason_code
    if reason_code is None:
        raise AssertionError("skip disposition 缺少 reason code")
    scoring = FilterOutcome(
        filter_id="replay_scoring",
        passed=None,
        reason=reason_code,
        evidence={
            "request_id": request.request_id,
            "disposition": response.disposition.value,
            "error_type": response.error_type,
        },
    )
    return CandidateAssessment(
        stock_code=request.stock_code,
        eligible=None,
        filter_outcomes={
            "replay_prefilter": prefilter,
            "replay_scoring": scoring,
        },
        reasons=(reason_code,),
    )


class SourceFactMismatchError(ValueError):
    """readback 不屬於 state 所等待的同一 request。"""


class DecisionUniverseTooSmallError(ValueError):
    def __init__(self, actual: int, minimum: int) -> None:
        self.actual = actual
        self.minimum = minimum
        super().__init__(
            f"quantile recommendation universe too small: actual={actual}, minimum={minimum}"
        )


def _replay_request_id(
    *,
    invocation_id: str,
    stock_code: str,
    as_of_date: date,
    ordinal: int,
    kind: str,
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1 | None = None,
) -> str:
    payload_parts = [
        "r020-replay-prefilter-v1",
        invocation_id,
        stock_code,
        as_of_date.isoformat(),
        str(ordinal),
        kind,
    ]
    if compatibility_candidate_key is not None:
        payload_parts.extend(
            (
                "compatibility-candidate-v1",
                compatibility_candidate_key.candidate_id,
            )
        )
    payload = "|".join(payload_parts)
    return sha256(payload.encode("utf-8")).hexdigest()


def _format_replay_value(
    value: Decimal | ReplayComparisonValue | ReplayComparisonOperand | None,
) -> str:
    if value is None:
        return ""
    if type(value) is Decimal:
        return str(value)
    if type(value) is ReplayComparisonOperand:
        domain = value.domain
        domain_parts = [domain.kind.value]
        if domain.format_name is not None:
            domain_parts.extend(
                (
                    domain.format_name,
                    str(domain.precision_bits),
                    str(domain.min_exponent),
                    str(domain.max_exponent),
                )
            )

        def format_component(component: ReplayComparisonComponent) -> str:
            if component.kind is ReplayComparisonKind.FINITE:
                assert component.numerator is not None
                assert component.denominator is not None
                return f"{component.numerator}/{component.denominator}"
            return component.kind.value

        formatted = (
            f"{value.origin.kind.value}:{value.origin.dtype_name or ''}"
            f"@{'/'.join(domain_parts)}:real={format_component(value.real)}"
        )
        if value.imaginary is not None:
            formatted += f":imaginary={format_component(value.imaginary)}"
        return formatted
    if type(value) is not ReplayComparisonValue:
        raise TypeError("不支援的 replay diagnostic value")
    if value.kind is ReplayComparisonKind.FINITE:
        assert value.value is not None
        return str(value.value)
    return value.kind.value


class RecommendationEvaluator:
    """無來源 I/O 的 staged gates 與批次 ranking。"""

    def preflight_replay_history(
        self, history_rows: int
    ) -> ReplayHistoryPreflightV1:
        """執行 count-only early gate；結果不代表已通過 replay fast filters。"""

        return evaluate_replay_history_preflight(history_rows)

    def start(
        self,
        seed: CandidateSeed,
        policy: RecommendationEvaluationPolicy,
    ) -> CandidateEvaluationStep:
        return self.advance(CandidateEvaluationState(policy=policy, seed=seed), None)

    def start_replay_prefilter(
        self,
        facts: ReplayCandidateHistoryFacts,
        policy: ReplayFastFilterPolicyV1,
    ) -> ReplayCandidatePrefilterStep:
        """啟動 replay prefilter，先把 stage 選擇交給共用 pure policy helper。

        app adapter 只應回填此 evaluator 要求的 typed fact。舊 threshold coercion
        若拋出例外，必須由 adapter 在原本的 provider 邊界傳出；本 pure contract
        不捕捉、不包裝為 per-candidate SourceFactError。
        """

        if type(facts) is not ReplayCandidateHistoryFacts:
            raise TypeError("facts 必須是 ReplayCandidateHistoryFacts")
        if type(policy) is not ReplayFastFilterPolicyV1:
            raise TypeError("policy 必須是 ReplayFastFilterPolicyV1")
        observations = facts.observations
        for status, value, name in (
            (
                observations.price_change_status,
                observations.price_change_percent,
                "price_change",
            ),
            (
                observations.volume_change_status,
                observations.volume_change_percent,
                "volume_change",
            ),
        ):
            if status not in {
                ReplayMetricStatus.NOT_REQUESTED,
                ReplayMetricStatus.MISSING_COLUMN,
                ReplayMetricStatus.INSUFFICIENT_WINDOW,
            } or value is not None:
                raise ValueError(f"初始 {name} 必須是未請求、缺欄或視窗不足狀態")
        state = ReplayCandidatePrefilterState(
            invocation_id=facts.invocation_id,
            policy=policy,
            observations=observations,
        )
        return self._replay_prefilter_step(state)

    def advance_replay_prefilter(
        self,
        state: ReplayCandidatePrefilterState,
        response: ReplayPrefilterFactResponse | None,
    ) -> ReplayCandidatePrefilterStep:
        """只接受 state 正在等待的同一 replay request，不讀 source 或執行 scorer。"""

        if type(state) is not ReplayCandidatePrefilterState:
            raise TypeError("state 必須是 ReplayCandidatePrefilterState")
        if state.phase in {
            ReplayCandidatePrefilterPhase.NEEDS_SCORING,
            ReplayCandidatePrefilterPhase.COMPLETE,
        }:
            raise ValueError("terminal replay prefilter state 不接受額外 facts")
        if state.phase is ReplayCandidatePrefilterPhase.WAITING_FOR_FACT:
            if response is None or response.request != state.pending:
                raise SourceFactMismatchError(
                    "replay fact 不屬於目前 pending request"
                )
            state = self._accept_replay_prefilter_fact(state, response)
        elif response is not None:
            raise SourceFactMismatchError("replay state 尚未要求 fact")
        return self._replay_prefilter_step(state)

    def complete_replay_scoring(
        self,
        prefilter_step: ReplayCandidatePrefilterStep,
        response: ReplayScorerResponseV1,
    ) -> ReplayCandidateScoringOutcomeV1:
        """驗證 READY handoff 的 scorer 回覆，形成 replay-specific outcome。"""

        if type(prefilter_step) is not ReplayCandidatePrefilterStep:
            raise TypeError("prefilter_step 必須是 ReplayCandidatePrefilterStep")
        if type(response) is not ReplayScorerResponseV1:
            raise TypeError("response 必須是 ReplayScorerResponseV1")

        request = prefilter_step.request
        state = prefilter_step.state
        if type(request) is not NeedCandidateScoring:
            raise ValueError("prefilter step 尚未到達 NeedCandidateScoring")
        if (
            state.phase is not ReplayCandidatePrefilterPhase.NEEDS_SCORING
            or state.scoring_request != request
            or state.pending is not None
            or state.outcome is not None
        ):
            raise ValueError("prefilter step 不是待完成的 scorer handoff")
        if response.request != request:
            raise SourceFactMismatchError(
                "scorer response 不屬於目前 invocation/candidate/cutoff request"
            )

        assessment = _replay_scoring_assessment(response)
        return ReplayCandidateScoringOutcomeV1(
            response=response,
            assessment=assessment,
        )

    def evaluate_replay_post_score(
        self,
        scoring: ReplayCandidateScoringOutcomeV1,
        facts: ReplayPostScoreFactsV1,
        policy: ReplayPostScorePolicyV1,
    ) -> ReplayPostScoreOutcomeV1:
        """執行 replay scored-row 最後過濾；不執行 legacy 診斷 passes。"""

        return _evaluate_replay_post_score(scoring, facts, policy)

    def evaluate_replay_post_score_ready(
        self,
        ready: ReplayScoredRowReadyV1,
        policy: ReplayPostScorePolicyV1,
    ) -> ReplayPostScoreOutcomeV1:
        """在 item／reason／v1 row 投影前評估非空 scorer row。"""

        return _evaluate_replay_post_score_ready(ready, policy)

    def start_replay_post_score_staged(
        self,
        ready: ReplayScoredRowReadyV1,
        deferred_policy: ReplayPostScoreDeferredPolicyV1,
    ) -> ReplayPostScoreEvaluationStepV1:
        """依舊 filter 順序逐次要求 threshold；不讀取或解析 raw config。"""

        if type(ready) is not ReplayScoredRowReadyV1:
            raise TypeError("ready 必須是 ReplayScoredRowReadyV1")
        if type(deferred_policy) is not ReplayPostScoreDeferredPolicyV1:
            raise TypeError("deferred_policy 必須是 ReplayPostScoreDeferredPolicyV1")
        if deferred_policy.policy.invocation_id != ready.request.invocation_id:
            raise ValueError("deferred policy invocation 不一致")
        return _advance_replay_post_score_state(
            ReplayPostScoreEvaluationStateV1(
                ready=ready,
                deferred_policy=deferred_policy,
            )
        )

    def advance_replay_post_score_staged(
        self,
        step: ReplayPostScoreEvaluationStepV1,
        response: ReplayPostScoreThresholdResponseV1 | None,
    ) -> ReplayPostScoreEvaluationStepV1:
        """只接受目前 request 的單一 threshold 回覆，不合併或重排 stages。"""

        if type(step) is not ReplayPostScoreEvaluationStepV1:
            raise TypeError("step 必須是 ReplayPostScoreEvaluationStepV1")
        state = step.state
        if state.outcome is not None:
            raise ValueError("terminal post-score state 不接受額外 threshold")
        pending = state.pending
        if pending is None:
            if response is not None:
                raise SourceFactMismatchError("post-score state 尚未要求 threshold")
            return _advance_replay_post_score_state(state)
        if response is None or type(response) is not ReplayPostScoreThresholdResponseV1:
            raise SourceFactMismatchError("post-score threshold response 不屬於目前 request")
        if response.request != pending:
            raise SourceFactMismatchError("post-score threshold response identity 不一致")

        metric_by_rule = {
            ReplayPostScoreRuleV1.PRICE_CHANGE_MIN: state.ready.facts.price_change,
            ReplayPostScoreRuleV1.PRICE_CHANGE_MAX: state.ready.facts.price_change,
            ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN: state.ready.facts.volume_change_percent,
            ReplayPostScoreRuleV1.RSI_MIN: state.ready.facts.rsi,
            ReplayPostScoreRuleV1.RSI_MAX: state.ready.facts.rsi,
        }
        current_metric = metric_by_rule[pending.filter_id]
        paired_projection = response.paired_metric
        if current_metric.status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
            if (
                response.threshold.status is ReplayThresholdStatus.ENABLED
                and paired_projection is None
            ):
                raise SourceFactMismatchError(
                    "awaiting metric 必須由目前 threshold response 成對投影"
                )
            if response.threshold.status is ReplayThresholdStatus.UNSUPPORTED and paired_projection is not None:
                raise SourceFactMismatchError(
                    "unsupported threshold 不可攜帶 numeric paired metric"
                )
        elif paired_projection is not None:
            raise SourceFactMismatchError(
                "只有 awaiting metric 的目前 rule 可接收 paired projection"
            )
        if paired_projection is not None and paired_projection.request != pending:
            raise SourceFactMismatchError("paired metric candidate/rule identity 不一致")

        resolved_policy = _replace_replay_post_score_threshold(
            state.deferred_policy.policy,
            pending.filter_id,
            response.threshold,
        )
        deferred_policy = replace(
            state.deferred_policy,
            policy=resolved_policy,
            deferred_rules=tuple(
                rule
                for rule in state.deferred_policy.deferred_rules
                if rule is not pending.filter_id
            ),
            threshold_input_hints=tuple(
                hint
                for hint in state.deferred_policy.threshold_input_hints
                if hint.filter_id is not pending.filter_id
            ),
        )
        return _advance_replay_post_score_state(
            replace(
                state,
                deferred_policy=deferred_policy,
                pending=None,
            ),
            paired_metric_rule=(
                pending.filter_id if paired_projection is not None else None
            ),
            paired_metric=(
                paired_projection.metric if paired_projection is not None else None
            ),
        )

    def complete_compatibility_scoring(
        self,
        prefilter_step: ReplayCandidatePrefilterStep,
        response: ReplayCompatibilityScorerResponseV1,
    ) -> ReplayCandidatePrefilterStep:
        """關閉空白 code 相容 scorer handoff，不產生 canonical candidate outcome。"""

        if type(prefilter_step) is not ReplayCandidatePrefilterStep:
            raise TypeError("prefilter_step 必須是 ReplayCandidatePrefilterStep")
        if type(response) is not ReplayCompatibilityScorerResponseV1:
            raise TypeError("response 必須是 ReplayCompatibilityScorerResponseV1")

        request = prefilter_step.request
        state = prefilter_step.state
        if type(request) is not NeedCompatibilityScoring:
            raise ValueError("prefilter step 尚未到達 NeedCompatibilityScoring")
        if (
            state.phase is not ReplayCandidatePrefilterPhase.NEEDS_SCORING
            or state.scoring_request != request
            or state.pending is not None
            or state.outcome is not None
        ):
            raise ValueError("prefilter step 不是待完成的 compatibility scorer handoff")
        if response.request != request:
            raise SourceFactMismatchError(
                "scorer response 不屬於目前 invocation/candidate/cutoff request"
            )

        outcome = ReplayCompatibilityScoringOutcomeV1(response=response)
        completed_state = replace(
            state,
            phase=ReplayCandidatePrefilterPhase.COMPLETE,
            scoring_request=None,
            outcome=outcome,
        )
        return ReplayCandidatePrefilterStep(
            state=completed_state,
            outcome=outcome,
        )

    @staticmethod
    def _accept_replay_prefilter_fact(
        state: ReplayCandidatePrefilterState,
        response: ReplayPrefilterFactResponse,
    ) -> ReplayCandidatePrefilterState:
        request = state.pending
        if request is None or response.request != request:
            raise SourceFactMismatchError("replay fact 不屬於目前 pending request")

        policy = state.policy
        observations = state.observations
        kind = request.kind
        if kind is ReplayPrefilterFactKind.PRICE_CHANGE_METRIC:
            assert response.metric_status is not None
            observations = replace(
                observations,
                price_change_status=response.metric_status,
                price_change_percent=response.metric_value,
            )
        elif kind is ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC:
            assert response.metric_status is not None
            observations = replace(
                observations,
                volume_change_status=response.metric_status,
                volume_change_percent=response.metric_value,
            )
        elif kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD:
            assert response.threshold is not None
            policy = replace(policy, price_change_min=response.threshold)
            if response.paired_metric_request_id is not None:
                assert response.paired_metric_status is not None
                assert response.paired_metric_value is not None
                observations = replace(
                    observations,
                    price_change_status=response.paired_metric_status,
                    price_change_percent=response.paired_metric_value,
                )
        elif kind is ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD:
            assert response.threshold is not None
            policy = replace(policy, price_change_max=response.threshold)
            if response.paired_metric_request_id is not None:
                assert response.paired_metric_status is not None
                assert response.paired_metric_value is not None
                observations = replace(
                    observations,
                    price_change_status=response.paired_metric_status,
                    price_change_percent=response.paired_metric_value,
                )
        elif kind is ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD:
            assert response.volume_threshold is not None
            policy = replace(
                policy,
                volume_ratio_min=ReplayThreshold.disabled(),
                volume_minimum=response.volume_threshold,
            )
            if response.paired_metric_request_id is not None:
                assert response.paired_metric_status is not None
                assert response.paired_metric_value is not None
                observations = replace(
                    observations,
                    volume_change_status=response.paired_metric_status,
                    volume_change_percent=response.paired_metric_value,
                )
        else:
            raise AssertionError("未處理的 replay prefilter fact kind")

        return replace(
            state,
            policy=policy,
            observations=observations,
            phase=ReplayCandidatePrefilterPhase.READY,
            pending=None,
            responses=(*state.responses, response),
        )

    @staticmethod
    def _replay_prefilter_step(
        state: ReplayCandidatePrefilterState,
    ) -> ReplayCandidatePrefilterStep:
        stage_projections = tuple(
            ReplayThresholdMetricProjection(
                threshold_fact=response.request.kind,
                metric_request_id=response.paired_metric_request_id,
                metric_status=response.paired_metric_status,
                metric_value=response.paired_metric_value,
            )
            for response in state.responses
            if response.paired_metric_request_id is not None
            and response.paired_metric_status is not None
            and response.paired_metric_value is not None
        )
        projection_by_stage = {
            projection.threshold_fact: projection
            for projection in stage_projections
        }
        metric_responses = {
            response.request.kind: response
            for response in state.responses
            if response.request.kind
            in {
                ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
            }
        }
        threshold_stages = (
            (
                ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
                ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                state.policy.price_change_min,
            ),
            (
                ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
                ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
                state.policy.price_change_max,
            ),
            (
                ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
                ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
                state.policy._effective_volume_threshold(),
            ),
        )
        pending_projection_stages = tuple(
            threshold_kind
            for threshold_kind, metric_kind, threshold in threshold_stages
            if threshold.status
            in {ReplayThresholdStatus.PENDING, ReplayThresholdStatus.ENABLED}
            and threshold_kind not in projection_by_stage
            and metric_kind in metric_responses
            and metric_responses[metric_kind].metric_status
            is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION
        )
        preflight = evaluate_replay_prefilter(
            state.policy,
            state.observations,
            stage_projections=stage_projections,
            pending_projection_stages=pending_projection_stages,
        )
        if preflight.disposition is ReplayPreflightDisposition.NEED_FACT:
            if preflight.required_fact is None:
                raise AssertionError("NEED_FACT outcome 缺少 request kind")
            request = NeedReplayPrefilterFact(
                request_id=_replay_request_id(
                    invocation_id=state.invocation_id,
                    stock_code=state.observations.stock_code,
                    as_of_date=state.observations.as_of_date,
                    ordinal=len(state.responses),
                    kind=preflight.required_fact.value,
                    compatibility_candidate_key=(
                        state.observations.compatibility_candidate_key
                        if type(state.observations)
                        is ReplayCompatibilityPrefilterObservationsV1
                        else None
                    ),
                ),
                invocation_id=state.invocation_id,
                kind=preflight.required_fact,
                stock_code=state.observations.stock_code,
                as_of_date=state.observations.as_of_date,
                compatibility_candidate_key=(
                    state.observations.compatibility_candidate_key
                    if type(state.observations)
                    is ReplayCompatibilityPrefilterObservationsV1
                    else None
                ),
            )
            state = replace(
                state,
                phase=ReplayCandidatePrefilterPhase.WAITING_FOR_FACT,
                pending=request,
            )
            return ReplayCandidatePrefilterStep(state=state, request=request)

        if preflight.disposition is ReplayPreflightDisposition.READY:
            compatibility_key = (
                state.observations.compatibility_candidate_key
                if type(state.observations)
                is ReplayCompatibilityPrefilterObservationsV1
                else None
            )
            if compatibility_key is not None:
                if type(preflight) is not ReplayCompatibilityPreflightOutcomeV1:
                    raise AssertionError("compatibility observation 必須回相容 preflight outcome")
                compatibility_scoring = NeedCompatibilityScoring(
                    request_id=_replay_request_id(
                        invocation_id=state.invocation_id,
                        stock_code=state.observations.stock_code,
                        as_of_date=state.observations.as_of_date,
                        ordinal=len(state.responses),
                        kind="compatibility_scoring",
                        compatibility_candidate_key=compatibility_key,
                    ),
                    invocation_id=state.invocation_id,
                    stock_code=state.observations.stock_code,
                    as_of_date=state.observations.as_of_date,
                    history_rows=state.observations.history_rows,
                    compatibility_candidate_key=compatibility_key,
                    prefilter_outcome=preflight,
                )
                state = replace(
                    state,
                    phase=ReplayCandidatePrefilterPhase.NEEDS_SCORING,
                    scoring_request=compatibility_scoring,
                )
                return ReplayCandidatePrefilterStep(
                    state=state,
                    request=compatibility_scoring,
                )

            if type(preflight) is not ReplayPreflightOutcome:
                raise AssertionError("canonical observation 必須回 canonical preflight outcome")
            scoring = NeedCandidateScoring(
                request_id=_replay_request_id(
                    invocation_id=state.invocation_id,
                    stock_code=state.observations.stock_code,
                    as_of_date=state.observations.as_of_date,
                    ordinal=len(state.responses),
                    kind="candidate_scoring",
                ),
                invocation_id=state.invocation_id,
                stock_code=state.observations.stock_code,
                as_of_date=state.observations.as_of_date,
                history_rows=state.observations.history_rows,
                prefilter_outcome=preflight,
            )
            state = replace(
                state,
                phase=ReplayCandidatePrefilterPhase.NEEDS_SCORING,
                scoring_request=scoring,
            )
            return ReplayCandidatePrefilterStep(state=state, request=scoring)

        if preflight.disposition is ReplayPreflightDisposition.REJECT:
            if preflight.stage is ReplayPreflightStage.MINIMUM_HISTORY:
                status = "missing"
                quality = "missing"
                outcome_stage = "pre_evaluation"
                threshold_name = "minimum_history_rows"
            else:
                status = "excluded"
                quality = "observed"
                outcome_stage = "replay_fast_filter"
                threshold_name = preflight.stage.value
        elif preflight.disposition is ReplayPreflightDisposition.UNSUPPORTED:
            status = "degraded"
            quality = "degraded"
            outcome_stage = "replay_fast_filter"
            threshold_name = preflight.stage.value
        else:
            raise AssertionError("未處理的 replay preflight disposition")

        if type(state.observations) is ReplayCompatibilityPrefilterObservationsV1:
            if type(preflight) is not ReplayCompatibilityPreflightOutcomeV1:
                raise AssertionError("compatibility observation 必須回相容 preflight outcome")
            compatibility_outcome = ReplayCompatibilityPrefilterOutcomeV1(
                invocation_id=state.invocation_id,
                stock_code=state.observations.stock_code,
                prefilter_outcome=preflight,
            )
            state = replace(
                state,
                phase=ReplayCandidatePrefilterPhase.COMPLETE,
                outcome=compatibility_outcome,
            )
            return ReplayCandidatePrefilterStep(
                state=state,
                outcome=compatibility_outcome,
            )

        if type(preflight) is not ReplayPreflightOutcome:
            raise AssertionError("canonical observation 必須回 canonical preflight outcome")
        outcome = _failure_outcome(
            invocation_id=state.invocation_id,
            stock_code=state.observations.stock_code,
            status=status,
            quality=quality,
            reason=preflight.reason_code,
            stage=outcome_stage,
            threshold_name=threshold_name,
            observed_value=_format_replay_value(preflight.observed_value),
            required_value=_format_replay_value(preflight.required_value),
        )
        state = replace(
            state,
            phase=ReplayCandidatePrefilterPhase.COMPLETE,
            outcome=outcome,
        )
        return ReplayCandidatePrefilterStep(state=state, outcome=outcome)

    @staticmethod
    def preflight_history(
        facts: CandidateHistoryFacts,
    ) -> CandidateEvaluationOutcome | None:
        """歷史不足時先回終止 outcome；否則回 None 允許後續 feature/scorer。

        最低歷史列數與相容診斷由 evaluator 單獨持有。
        """

        if type(facts) is not CandidateHistoryFacts:
            raise TypeError("facts 必須是 CandidateHistoryFacts")
        if facts.history_rows >= MINIMUM_RECOMMENDATION_HISTORY_ROWS:
            return None
        return _failure_outcome(
            invocation_id=facts.invocation_id,
            stock_code=facts.stock_code,
            status="missing",
            quality="missing",
            reason="insufficient_history",
            stage="pre_evaluation",
            threshold_name="minimum_history_rows",
            observed_value=str(facts.history_rows),
            required_value=str(MINIMUM_RECOMMENDATION_HISTORY_ROWS),
        )

    @staticmethod
    def prefilter_outcome(
        fact: CandidatePrefilterFact,
    ) -> CandidateEvaluationOutcome:
        """由 membership source facts 推導 PIT/industry universe disposition。"""

        if type(fact) is not CandidatePrefilterFact:
            raise TypeError("fact 必須是 CandidatePrefilterFact")
        if fact.point_in_time_required and not fact.membership_usable:
            status = "missing"
            quality = "missing"
            reason = "industry_membership_pit_unavailable"
        elif fact.matching_stock_count == 0:
            status = "excluded"
            quality = "observed"
            reason = "industry_filter_empty"
        else:
            raise ValueError(
                "prefilter fact does not describe a rejected industry universe"
            )
        stage = "universe_gate"
        eligible = None if status == "missing" else False
        reason_codes = (reason,)
        assessment = CandidateAssessment(
            stock_code=fact.stock_code,
            eligible=eligible,
            filter_outcomes={
                stage: FilterOutcome(
                    filter_id=stage,
                    passed=eligible,
                    reason=reason,
                    evidence={
                        "status": status,
                        "quality": quality,
                        "stage": stage,
                        "threshold_name": "",
                        "observed_value": "",
                        "required_value": "",
                        "warnings": (),
                        "reason_codes": reason_codes,
                        "requested_industry": fact.requested_industry,
                        "matching_stock_count": fact.matching_stock_count,
                        "point_in_time_required": fact.point_in_time_required,
                        "membership_usable": fact.membership_usable,
                    },
                )
            },
            reasons=reason_codes,
            missing_data=(
                reason_codes if status == "missing" else ()
            ),
        )
        return CandidateEvaluationOutcome(
            invocation_id=fact.invocation_id,
            stock_code=fact.stock_code,
            status=status,
            quality=quality,
            stage=stage,
            reason_codes=reason_codes,
            assessment=assessment,
        )

    def advance(
        self,
        state: CandidateEvaluationState,
        fact: SourceFactResponse | None,
    ) -> CandidateEvaluationStep:
        if state.stage is CandidateStage.COMPLETE:
            raise ValueError("完成的 candidate 不接受額外 facts")
        if state.pending is None:
            if fact is not None:
                raise SourceFactMismatchError("state 未要求 source fact")
        else:
            if fact is None or fact.request != state.pending:
                raise SourceFactMismatchError("source fact 不屬於目前 pending request")
            state = self._accept_fact(state, fact)

        if state.stage is CandidateStage.READY:
            early = self._early_outcome(state)
            if early is not None:
                return self._complete(state, early)
            if self._fundamental_enabled(state.policy) and state.policy.decision_date is None:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="skipped",
                        quality="degraded",
                        reason="fundamental_decision_date_invalid",
                        threshold_name="decision_date",
                        observed_value=state.policy.decision_date_text,
                        required_value="YYYY-MM-DD",
                    ),
                )
            if self._pe_enabled(state.policy):
                return self._request(state, SourceFactKind.PE)
            if self._revenue_enabled(state.policy):
                return self._request(state, SourceFactKind.MONTHLY_REVENUE)
            if state.policy.industry_context_required:
                return self._request(state, SourceFactKind.INDUSTRY_CONTEXT)
            return self._success(state)

        if state.stage is CandidateStage.PE_RECEIVED:
            pe_value = self._available_pe_value(state)
            if pe_value is None:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="skipped",
                        quality="missing",
                        reason="valuation_pe_missing",
                        threshold_name="filters.pe_ratio_max",
                        observed_value="missing",
                        required_value=str(state.policy.pe_ratio_max),
                    ),
                )
            assert state.policy.pe_ratio_max is not None
            if pe_value > state.policy.pe_ratio_max:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="skipped",
                        quality="observed",
                        reason="valuation_pe_above_max",
                        threshold_name="filters.pe_ratio_max",
                        observed_value=str(pe_value),
                        required_value=str(state.policy.pe_ratio_max),
                    ),
                )
            if self._revenue_enabled(state.policy):
                return self._request(state, SourceFactKind.MONTHLY_REVENUE)
            if state.policy.industry_context_required:
                return self._request(state, SourceFactKind.INDUSTRY_CONTEXT)
            return self._success(state)

        if state.stage is CandidateStage.MONTHLY_REVENUE_RECEIVED:
            yoy = self._revenue_yoy(
                state.revenue_facts,
                cutoff=state.policy.decision_date,
            )
            if yoy is None:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="skipped",
                        quality="missing",
                        reason="fundamental_revenue_yoy_missing",
                        threshold_name="filters.monthly_revenue_yoy_min",
                        observed_value="missing",
                        required_value=str(state.policy.monthly_revenue_yoy_min),
                    ),
                )
            assert state.policy.monthly_revenue_yoy_min is not None
            if yoy < state.policy.monthly_revenue_yoy_min:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="skipped",
                        quality="observed",
                        reason="fundamental_revenue_yoy_below_min",
                        threshold_name="filters.monthly_revenue_yoy_min",
                        observed_value=str(yoy.quantize(Decimal("0.01"))),
                        required_value=str(state.policy.monthly_revenue_yoy_min),
                    ),
                )
            if state.policy.industry_context_required:
                return self._request(state, SourceFactKind.INDUSTRY_CONTEXT)
            return self._success(state)

        if state.stage is CandidateStage.INDUSTRY_CONTEXT_RECEIVED:
            if state.industry_error is not None:
                return self._complete(
                    state,
                    self._failure(
                        state,
                        status="degraded",
                        quality="degraded",
                        reason="screening_exception",
                        stage="strategy_evaluation",
                        threshold_name=state.industry_error.error_type,
                        observed_value=state.industry_error.message,
                        required_value="successful_evaluation",
                        warnings=(
                            f"screening_exception:{state.industry_error.error_type}",
                        ),
                    ),
                )
            return self._success(state)

        raise AssertionError(f"unsupported candidate stage: {state.stage}")

    def evaluate_batch(
        self,
        outcomes: tuple[CandidateEvaluationOutcome, ...],
        policy: RecommendationEvaluationPolicy,
    ) -> DecisionBatch:
        """相容 API：依原候選次序穩定排名並輸出 canonical DecisionBatch。"""

        return self.evaluate_batch_result(outcomes, policy).decision

    def rank_replay_candidate_ordinals(
        self,
        scores: tuple[ReplayScoreOrderingV1, ...],
        policy: ReplayExecutionPolicyV1,
    ) -> tuple[int, ...]:
        """依 replay v1 的穩定反向排序，執行 provider 端第一段切片。"""

        if type(policy) is not ReplayExecutionPolicyV1:
            raise TypeError("policy 必須是 ReplayExecutionPolicyV1")
        if type(scores) is not tuple or any(
            type(score) is not ReplayScoreOrderingV1 for score in scores
        ):
            raise TypeError("scores 必須是 ReplayScoreOrderingV1 tuple")

        ordinals = sorted(
            range(len(scores)),
            key=scores.__getitem__,
            reverse=True,
        )
        return tuple(ordinals[: policy.top_n])

    def evaluate_batch_result(
        self,
        outcomes: tuple[CandidateEvaluationOutcome, ...],
        policy: RecommendationEvaluationPolicy,
    ) -> RecommendationEvaluationResult:
        """輸出排名後 batch 與每檔候選的最終 typed disposition。"""

        if type(outcomes) is not tuple or any(
            type(outcome) is not CandidateEvaluationOutcome for outcome in outcomes
        ):
            raise TypeError("outcomes 必須是 CandidateEvaluationOutcome tuple")
        if any(outcome.invocation_id != policy.invocation_id for outcome in outcomes):
            raise ValueError("outcomes 與 policy invocation_id 不一致")
        codes = [outcome.stock_code for outcome in outcomes]
        if len(codes) != len(set(codes)):
            raise ValueError("outcomes 不可有重複 stock_code")
        if any(outcome.assessment is None for outcome in outcomes):
            raise ValueError("每個 candidate outcome 都必須有 assessment")

        scored = [
            outcome
            for outcome in outcomes
            if outcome.item is not None and outcome.score is not None
        ]
        items_by_code = {outcome.stock_code: outcome.item for outcome in scored}
        percentiles: dict[str, int] = {}
        if policy.threshold_mode == "fixed":
            ordered = sorted(
                scored,
                key=lambda outcome: self._score_order(outcome),
                reverse=True,
            )
            ranking_method = "fixed"
        else:
            minimum_size = policy.minimum_universe_size
            minimum_bp = policy.minimum_percentile_bp
            assert minimum_size is not None and minimum_bp is not None
            if scored and len(scored) < minimum_size:
                raise DecisionUniverseTooSmallError(len(scored), minimum_size)
            scores_by_code: dict[str, int] = {}
            for outcome in scored:
                assert outcome.score is not None
                score_bp = outcome.score.quantile_score_bp
                if score_bp is None:
                    raise ValueError(
                        f"cannot quantize total score for stock {outcome.stock_code}"
                    )
                scores_by_code[outcome.stock_code] = score_bp
            percentiles = calculate_score_percentiles(scores_by_code)
            ordered = [
                outcome
                for outcome in scored
                if percentiles.get(outcome.stock_code, 0) >= minimum_bp
            ]
            ordered.sort(key=lambda outcome: outcome.stock_code)
            ordered.sort(
                key=lambda outcome: self._score_order(outcome),
                reverse=True,
            )
            ranking_method = policy.ranking_method

        ordered_codes = tuple(outcome.stock_code for outcome in ordered)
        selected_codes = set(ordered_codes[: policy.top_n])
        ranked_assessments: list[CandidateAssessment] = []
        dispositions: list[CandidateDecisionDisposition] = []
        for outcome in outcomes:
            assert outcome.assessment is not None
            assessment = outcome.assessment
            reason = ""
            passed: bool | None = assessment.eligible
            if outcome.stock_code in items_by_code:
                if (
                    policy.threshold_mode == "quantile"
                    and outcome.stock_code not in percentiles
                ):
                    reason = "recommendation_score_unrankable"
                    passed = False
                elif (
                    policy.threshold_mode == "quantile"
                    and percentiles[outcome.stock_code]
                    < (policy.minimum_percentile_bp or 0)
                ):
                    reason = "recommendation_percentile_below_min"
                    passed = False
                elif outcome.stock_code not in selected_codes:
                    reason = "recommendation_outside_top_n"
                    passed = False
                else:
                    passed = True
            if reason:
                assessment = replace(
                    assessment,
                    eligible=passed,
                    reasons=(*assessment.reasons, reason),
                )
            elif outcome.stock_code in selected_codes:
                assessment = replace(assessment, eligible=True)
            ordered_rank = (
                ordered_codes.index(outcome.stock_code) + 1
                if outcome.stock_code in ordered_codes
                else None
            )
            assessment = self._add_ranking_outcome(
                assessment,
                outcome,
                policy,
                percentile=percentiles.get(outcome.stock_code),
                ordered_rank=ordered_rank,
                selected=outcome.stock_code in selected_codes,
                reason=reason,
                universe_size=len(scored),
                ranking_method=ranking_method,
            )
            ranked_assessments.append(assessment)
            dispositions.append(
                self._final_disposition(
                    outcome,
                    assessment,
                    policy,
                    reason=reason,
                    percentile=percentiles.get(outcome.stock_code),
                    ordered_rank=ordered_rank,
                    selected=outcome.stock_code in selected_codes,
                )
            )

        selected_items: list[RecommendationItem] = []
        for index, code in enumerate(
            (code for code in ordered_codes if code in selected_codes), start=1
        ):
            item = items_by_code[code]
            assert item is not None
            selected_items.append(
                replace(
                    item,
                    rank=index,
                    score_percentile_bp=percentiles.get(code),
                    eligible_universe_size=len(scored),
                    eligible_universe_date=policy.eligible_universe_date,
                    ranking_method=ranking_method,
                    threshold_mode=policy.threshold_mode,
                )
            )
        return RecommendationEvaluationResult(
            decision=DecisionBatch(
                items=tuple(selected_items),
                assessments=tuple(ranked_assessments),
            ),
            dispositions=tuple(dispositions),
        )

    @staticmethod
    def _final_disposition(
        outcome: CandidateEvaluationOutcome,
        assessment: CandidateAssessment,
        policy: RecommendationEvaluationPolicy,
        *,
        reason: str,
        percentile: int | None,
        ordered_rank: int | None,
        selected: bool,
    ) -> CandidateDecisionDisposition:
        if outcome.item is None:
            return CandidateDecisionDisposition(
                invocation_id=outcome.invocation_id,
                stock_code=outcome.stock_code,
                status=outcome.status,
                quality=outcome.quality,
                stage=outcome.stage,
                reason_codes=outcome.reason_codes,
                threshold_name=outcome.threshold_name,
                observed_value=outcome.observed_value,
                required_value=outcome.required_value,
                warnings=outcome.warnings,
                assessment=assessment,
                scored=False,
            )

        reason_codes: tuple[str, ...]
        if reason == "recommendation_percentile_below_min":
            status = "fail"
            stage = "threshold_gate"
            threshold_name = "recommendation_min_percentile_bp"
            observed_value = str(percentile if percentile is not None else "")
            required_value = str(policy.minimum_percentile_bp or "")
            reason_codes = (reason,)
        elif reason == "recommendation_outside_top_n":
            status = "fail"
            stage = "top_n_gate"
            threshold_name = "top_n"
            observed_value = str(ordered_rank if ordered_rank is not None else "")
            required_value = str(policy.top_n)
            reason_codes = (reason,)
        elif selected:
            status = "pass"
            stage = "final_selection"
            threshold_name = ""
            observed_value = ""
            required_value = ""
            reason_codes = ("recommendation_selected",)
        else:
            status = outcome.status
            stage = outcome.stage
            threshold_name = outcome.threshold_name
            observed_value = outcome.observed_value
            required_value = outcome.required_value
            reason_codes = outcome.reason_codes

        return CandidateDecisionDisposition(
            invocation_id=outcome.invocation_id,
            stock_code=outcome.stock_code,
            status=status,
            quality=outcome.quality,
            stage=stage,
            reason_codes=reason_codes,
            threshold_name=threshold_name,
            observed_value=observed_value,
            required_value=required_value,
            warnings=outcome.warnings,
            assessment=assessment,
            scored=True,
        )

    @staticmethod
    def _score_order(outcome: CandidateEvaluationOutcome) -> DecisionNumber:
        assert outcome.score is not None
        return outcome.score.ordering_value

    @staticmethod
    def _add_ranking_outcome(
        assessment: CandidateAssessment,
        candidate: CandidateEvaluationOutcome,
        policy: RecommendationEvaluationPolicy,
        *,
        percentile: int | None,
        ordered_rank: int | None,
        selected: bool,
        reason: str,
        universe_size: int,
        ranking_method: str,
    ) -> CandidateAssessment:
        filters = dict(assessment.filter_outcomes or {})
        filter_id = "recommendation_ranking"
        filters[filter_id] = FilterOutcome(
            filter_id=filter_id,
            passed=not reason if candidate.item is not None else None,
            reason=reason or ("recommendation_selected" if selected else "not_ranked"),
            evidence={
                "status": candidate.status,
                "quality": candidate.quality,
                "stage": "final_selection" if selected else "ranking",
                "threshold_mode": policy.threshold_mode,
                "ranking_method": ranking_method,
                "score_percentile_bp": percentile,
                "eligible_universe_size": universe_size,
                "eligible_universe_date": policy.eligible_universe_date,
                "ordered_rank": ordered_rank,
                "top_n": policy.top_n,
                "selected": selected,
                "reason_codes": candidate.reason_codes,
                "threshold_name": (
                    "recommendation_min_percentile_bp"
                    if reason == "recommendation_percentile_below_min"
                    else "top_n"
                    if reason == "recommendation_outside_top_n"
                    else ""
                ),
                "observed_value": (
                    str(percentile)
                    if reason == "recommendation_percentile_below_min"
                    else str(ordered_rank or "")
                    if reason == "recommendation_outside_top_n"
                    else ""
                ),
                "required_value": (
                    str(policy.minimum_percentile_bp)
                    if reason == "recommendation_percentile_below_min"
                    else str(policy.top_n)
                    if reason == "recommendation_outside_top_n"
                    else ""
                ),
            },
        )
        return replace(assessment, filter_outcomes=filters)

    def _accept_fact(
        self,
        state: CandidateEvaluationState,
        response: SourceFactResponse,
    ) -> CandidateEvaluationState:
        assert state.pending is not None
        kind = state.pending.kind
        if response.error is not None:
            if kind is SourceFactKind.PE:
                return replace(
                    state,
                    stage=CandidateStage.PE_RECEIVED,
                    pending=None,
                    pe_fact=PEFact(None, None),
                    pe_error=response.error,
                    source_responses=(*state.source_responses, response),
                )
            if kind is SourceFactKind.MONTHLY_REVENUE:
                return replace(
                    state,
                    stage=CandidateStage.MONTHLY_REVENUE_RECEIVED,
                    pending=None,
                    revenue_facts=MonthlyRevenueFacts(),
                    revenue_error=response.error,
                    source_responses=(*state.source_responses, response),
                )
            return replace(
                state,
                stage=CandidateStage.INDUSTRY_CONTEXT_RECEIVED,
                pending=None,
                industry_fact=IndustryContextFact(),
                industry_error=response.error,
                source_responses=(*state.source_responses, response),
            )
        assert response.value is not None
        if kind is SourceFactKind.PE:
            assert type(response.value) is PEFact
            return replace(
                state,
                stage=CandidateStage.PE_RECEIVED,
                pending=None,
                pe_fact=response.value,
                pe_error=None,
                source_responses=(*state.source_responses, response),
            )
        if kind is SourceFactKind.MONTHLY_REVENUE:
            assert type(response.value) is MonthlyRevenueFacts
            return replace(
                state,
                stage=CandidateStage.MONTHLY_REVENUE_RECEIVED,
                pending=None,
                revenue_facts=response.value,
                revenue_error=None,
                source_responses=(*state.source_responses, response),
            )
        assert type(response.value) is IndustryContextFact
        return replace(
            state,
            stage=CandidateStage.INDUSTRY_CONTEXT_RECEIVED,
            pending=None,
            industry_fact=response.value,
            industry_error=None,
            source_responses=(*state.source_responses, response),
        )

    def _request(
        self,
        state: CandidateEvaluationState,
        kind: SourceFactKind,
    ) -> CandidateEvaluationStep:
        if state.policy.decision_date is None:
            raise ValueError("source fact request requires a valid decision_date")
        request_id = sha256(
            "\0".join(
                (
                    state.policy.invocation_id,
                    state.seed.stock_code,
                    state.policy.decision_date.isoformat(),
                    kind.value,
                )
            ).encode("utf-8")
        ).hexdigest()
        request = NeedSourceFact(
            request_id=request_id,
            invocation_id=state.policy.invocation_id,
            kind=kind,
            stock_code=state.seed.stock_code,
            decision_date=state.policy.decision_date,
        )
        waiting_stage = {
            SourceFactKind.PE: CandidateStage.WAITING_FOR_PE,
            SourceFactKind.MONTHLY_REVENUE: CandidateStage.WAITING_FOR_MONTHLY_REVENUE,
            SourceFactKind.INDUSTRY_CONTEXT: CandidateStage.WAITING_FOR_INDUSTRY_CONTEXT,
        }[kind]
        next_state = replace(state, stage=waiting_stage, pending=request)
        return CandidateEvaluationStep(state=next_state, request=request)

    def _early_outcome(
        self,
        state: CandidateEvaluationState,
    ) -> CandidateEvaluationOutcome | None:
        seed = state.seed
        policy = state.policy
        history_outcome = self.preflight_history(
            CandidateHistoryFacts(
                invocation_id=seed.invocation_id,
                stock_code=seed.stock_code,
                history_rows=seed.history_rows,
            )
        )
        if history_outcome is not None:
            return history_outcome
        if seed.strategy_error is not None:
            error = seed.strategy_error
            return self._failure(
                state,
                status="degraded",
                quality="degraded",
                reason="screening_exception",
                threshold_name=error.error_type,
                observed_value=error.message,
                required_value="successful_evaluation",
                warnings=(f"screening_exception:{error.error_type}",),
            )
        if not seed.strategy_result_present:
            reason = "strategy_filter_no_signal"
            threshold_name = "strategy_configurator_result"
            observed_value, required_value = "empty", "non_empty"
            volume_min = policy.volume_change_min_percent
            volume_change = seed.latest_volume_change_percent
            if (
                volume_min is not None
                and volume_change is not None
                and volume_change < volume_min
            ):
                reason = "liquidity_volume_ratio_below_min"
                threshold_name = "liquidity.volume_ratio_min"
                observed_value = self._format_decimal(volume_change)
                required_value = self._format_decimal(volume_min)
            return self._failure(
                state,
                status="skipped",
                quality="degraded",
                reason=reason,
                threshold_name=threshold_name,
                observed_value=observed_value,
                required_value=required_value,
            )
        return None

    def _failure(
        self,
        state: CandidateEvaluationState,
        *,
        status: str,
        quality: str,
        reason: str,
        stage: str = "strategy_evaluation",
        threshold_name: str = "",
        observed_value: str = "",
        required_value: str = "",
        warnings: tuple[str, ...] = (),
    ) -> CandidateEvaluationOutcome:
        return _failure_outcome(
            invocation_id=state.seed.invocation_id,
            stock_code=state.seed.stock_code,
            status=status,
            quality=quality,
            reason=reason,
            stage=stage,
            threshold_name=threshold_name,
            observed_value=observed_value,
            required_value=required_value,
            warnings=warnings,
            source_responses=state.source_responses,
        )

    def _success(self, state: CandidateEvaluationState) -> CandidateEvaluationStep:
        seed = state.seed
        if seed.item is None or seed.score is None:
            return self._complete(
                state,
                self._failure(
                    state,
                    status="missing",
                    quality="missing",
                    reason="total_score_missing_or_nonfinite",
                ),
            )
        item = seed.item
        if state.industry_fact is not None:
            industry_names = state.industry_fact.industries
            industry_display = ", ".join(industry_names[:2]) if industry_names else "未知"
            if len(industry_names) > 2:
                industry_display += "..."
            item = replace(item, industry=industry_display)
        assessment = CandidateAssessment(
            stock_code=seed.stock_code,
            eligible=True,
            filter_outcomes={
                "candidate_scored": FilterOutcome(
                    filter_id="candidate_scored",
                    passed=True,
                    reason="candidate_scored",
                    evidence={
                        "status": "fail",
                        "quality": "observed",
                        "stage": "candidate_scored",
                    },
                )
            },
        )
        outcome = CandidateEvaluationOutcome(
            invocation_id=seed.invocation_id,
            stock_code=seed.stock_code,
            status="fail",
            quality="observed",
            stage="candidate_scored",
            reason_codes=("pending_final_selection",),
            item=item,
            assessment=assessment,
            score=seed.score,
            source_responses=state.source_responses,
        )
        return self._complete(state, outcome)

    def _complete(
        self,
        state: CandidateEvaluationState,
        outcome: CandidateEvaluationOutcome,
    ) -> CandidateEvaluationStep:
        completed = replace(
            state,
            stage=CandidateStage.COMPLETE,
            pending=None,
            outcome=outcome,
        )
        return CandidateEvaluationStep(state=completed, outcome=outcome)

    @staticmethod
    def _pe_enabled(policy: RecommendationEvaluationPolicy) -> bool:
        return policy.pe_ratio_max is not None

    @staticmethod
    def _revenue_enabled(policy: RecommendationEvaluationPolicy) -> bool:
        return policy.monthly_revenue_yoy_min is not None

    @classmethod
    def _fundamental_enabled(cls, policy: RecommendationEvaluationPolicy) -> bool:
        return cls._pe_enabled(policy) or cls._revenue_enabled(policy)

    @staticmethod
    def _available_pe_value(state: CandidateEvaluationState) -> Decimal | None:
        fact = state.pe_fact
        cutoff = state.policy.decision_date
        if (
            fact is None
            or fact.value is None
            or fact.available_date is None
            or cutoff is None
            or fact.available_date > cutoff
        ):
            return None
        return fact.value

    @staticmethod
    def _revenue_yoy(
        facts: MonthlyRevenueFacts | None,
        *,
        cutoff: date | None,
    ) -> Decimal | None:
        if facts is None or cutoff is None:
            return None
        available = tuple(
            record for record in facts.records if record.available_date <= cutoff
        )
        if not available:
            return None
        latest = max(
            available,
            key=lambda record: (
                record.period,
                record.available_date,
                record.source_version,
            ),
        )
        year_text, month_text = latest.period.split("-")
        prior_period = f"{int(year_text) - 1:04d}-{int(month_text):02d}"
        prior_candidates = [
            record for record in available if record.period == prior_period
        ]
        if not prior_candidates:
            return None
        prior = max(
            prior_candidates,
            key=lambda record: (record.available_date, record.source_version),
        )
        if prior.revenue <= 0:
            return None
        return ((latest.revenue - prior.revenue) / prior.revenue) * Decimal("100.0")

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return format(value.normalize(), "f")


__all__ = (
    "CandidateDecisionDisposition",
    "CandidateEvaluationOutcome",
    "CandidateEvaluationState",
    "CandidateEvaluationStep",
    "CandidateHistoryFacts",
    "CandidatePrefilterFact",
    "CandidateSeed",
    "CandidateStage",
    "DecisionNumber",
    "DecisionUniverseTooSmallError",
    "IndustryContextFact",
    "IndustryChangeSourceKind",
    "MonthlyRevenueFact",
    "MonthlyRevenueFacts",
    "NeedCandidateScoring",
    "NeedCompatibilityScoring",
    "NeedReplayPrefilterFact",
    "NeedSourceFact",
    "PEFact",
    "ReplayCandidateHistoryFacts",
    "ReplayCandidatePrefilterPhase",
    "ReplayCandidatePrefilterState",
    "ReplayCandidatePrefilterStep",
    "ReplayPostScoreDispositionV1",
    "ReplayPostScoreDiagnosticCodeV1",
    "ReplayPostScoreDiagnosticEventV1",
    "ReplayPostScoreDeferredPolicyV1",
    "ReplayPostScoreEvaluationStateV1",
    "ReplayPostScoreEvaluationStepV1",
    "ReplayPostScoreFactsV1",
    "ReplayPostScoreMetricFactV1",
    "ReplayPostScoreMetricLegacyKindV1",
    "ReplayPostScorePairedMetricV1",
    "ReplayPostScoreOutcomeV1",
    "ReplayPostScorePolicyV1",
    "ReplayPostScoreRuleDispositionV1",
    "ReplayPostScoreRuleOutcomeV1",
    "ReplayPostScoreRuleV1",
    "ReplayPostScoreThresholdResponseV1",
    "ReplayPostScoreThresholdInputHintV1",
    "ReplayPostScoreThresholdInputKindV1",
    "ReplayScoredRowReadyV1",
    "NeedReplayPostScoreThresholdV1",
    "REPLAY_POST_SCORE_POLICY_VERSION_V1",
    "REPLAY_POST_SCORE_DEFERRED_POLICY_VERSION_V1",
    "ReplayCompatibilityPrefilterOutcomeV1",
    "ReplayPrefilterFactResponse",
    "RecommendationEvaluationPolicy",
    "RecommendationEvaluationResult",
    "RecommendationEvaluator",
    "RecommendationScore",
    "SourceFactError",
    "SourceFactKind",
    "SourceFactMismatchError",
    "SourceFactResponse",
)
