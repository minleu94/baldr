from dataclasses import dataclass, field, replace
from decimal import Decimal
from datetime import date
from enum import Enum
import dis
import logging
import math
import operator
import sys
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4
import warnings

import numpy as np
import pandas as pd

from decision_module.industry_mapper import IndustryMapper
from decision_module.reason_engine import ReasonEngine
from decision_module.strategy_configurator import (
    StrategyConfigurator,
    normalize_recommendation_filter_aliases,
    observe_screening_diagnostics,
)
from app_module.recommendation_portfolio_dates import parse_stock_dates
from decision_module.recommendation.contracts import RecommendationItem
from app_module.recommendation.replay_numeric_projection import (
    ReplayThresholdUnit,
    UnsupportedReplayNumericScalarError,
    classify_legacy_post_score_metric_scalar,
    project_legacy_comparison_pair,
    project_legacy_post_score_comparison_pair,
    project_legacy_post_score_threshold_input_hint,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    NeedCompatibilityScoring,
    NeedReplayPrefilterFact,
    NeedReplayPostScoreThresholdV1,
    RecommendationEvaluator,
    ReplayCandidateHistoryFacts,
    ReplayCandidatePrefilterStep,
    ReplayCandidateScoringOutcomeV1,
    ReplayCompatibilityScorerDispositionV1,
    ReplayCompatibilityScorerResponseV1,
    ReplayCompatibilityScoringOutcomeV1,
    ReplayPrefilterFactResponse,
    ReplayPostScoreDeferredPolicyV1,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreEffectKindV1,
    ReplayPostScoreEffectV1,
    ReplayPostScoreFactsV1,
    ReplayPostScoreMetricFactV1,
    ReplayPostScorePolicyV1,
    ReplayPostScoreRuleV1,
    ReplayPostScoreThresholdResponseV1,
    ReplayPostScorePairedMetricV1,
    ReplayScoredRowReadyV1,
    ReplayScorerDispositionV1,
    ReplayScorerResponseV1,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayCompatibilityCandidateKeyV1,
    ReplayCompatibilityPrefilterObservationsV1,
    ReplayComparisonDomainKind,
    ReplayFastFilterPolicyV1,
    ReplayHistoryPreflightDisposition,
    ReplayMetricStatus,
    ReplayPrefilterFactKind,
    ReplayPrefilterObservations,
    ReplayThreshold,
    ReplayVolumeThresholdV1,
)
from decision_module.recommendation.replay_policy import (
    ReplayExecutionPolicyV1,
    ReplayScoreOrderingV1,
)


_BUILTIN_STRATEGY_GENERATE_RECOMMENDATIONS = (
    StrategyConfigurator.generate_recommendations
)


def _is_builtin_strategy_scorer(
    configurator: StrategyConfigurator,
    scorer: object,
) -> bool:
    """只將原始 built-in scorer 接入 replay canonical child。"""

    return (
        type(configurator) is StrategyConfigurator
        and getattr(scorer, "__func__", None)
        is _BUILTIN_STRATEGY_GENERATE_RECOMMENDATIONS
    )


def _resolve_numpy_rank_warning(numpy_module: Any) -> type[Warning]:
    """跨 NumPy 1/2 解析 RankWarning，且只忽略該一種警告。"""

    try:
        warning_type = numpy_module.exceptions.RankWarning
    except AttributeError:
        # NumPy 1.x 將 RankWarning 暴露在頂層；只在新路徑不存在時才讀取。
        warning_type = numpy_module.RankWarning
    if not isinstance(warning_type, type) or not issubclass(warning_type, Warning):
        raise TypeError("NumPy RankWarning 必須是 Warning 型別")
    return warning_type


class _LegacyFastFilterTraceStatus(str, Enum):
    FINITE = "finite"
    UNORDERED = "unordered"
    POSITIVE_INFINITY = "positive_infinity"
    NEGATIVE_INFINITY = "negative_infinity"
    UNAVAILABLE = "unavailable"


class _LegacyFastFilterTraceStage(str, Enum):
    PRICE_CHANGE_METRIC = "price_change_metric"
    PRICE_CHANGE_MIN_THRESHOLD = "price_change_min_threshold"
    PRICE_CHANGE_MAX_THRESHOLD = "price_change_max_threshold"
    VOLUME_CHANGE_METRIC = "volume_change_metric"
    VOLUME_CHANGE_MIN_EFFECTIVE_PERCENT = "volume_change_min_effective_percent"


@dataclass(frozen=True, slots=True)
class _LegacyFastFilterTraceEvent:
    stock_code: str | None
    stage: _LegacyFastFilterTraceStage
    status: _LegacyFastFilterTraceStatus
    value: Decimal | None


@dataclass(slots=True)
class _LegacyFastFilterTraceCapture:
    """呼叫區域 shadow trace；不參與篩選決策。"""

    events: list[_LegacyFastFilterTraceEvent] = field(default_factory=list)
    available: bool = True


@dataclass(frozen=True, slots=True)
class _RecommendationProviderCallContext:
    """單次 replay 呼叫的市場 cutoff；不保存到 provider instance。"""

    as_of_date: date

    def __post_init__(self) -> None:
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")


@dataclass(frozen=True, slots=True)
class _ReplayScoredCandidateV1:
    """保留一次排序候選，供 typed child 與 v1 相容輸出共同投影。"""

    stock_code: str
    stock_name: str
    total_score: float
    technical_score: float
    pattern_score: float
    volume_score: float
    broker_flow_score: float
    revenue_score: float
    # legacy v1 row 可攜帶不支援 typed child 的 opaque reason object。
    selection_reason: object
    legacy_score_ordering: ReplayScoreOrderingV1
    scoring_outcome: ReplayCandidateScoringOutcomeV1 | None = None
    selected_ordinal: int | None = None

    def __post_init__(self) -> None:
        if type(self.legacy_score_ordering) is not ReplayScoreOrderingV1:
            raise TypeError("legacy_score_ordering 必須是 ReplayScoreOrderingV1")
        if self.selected_ordinal is not None and (
            type(self.selected_ordinal) is not int or self.selected_ordinal < 0
        ):
            raise ValueError("selected_ordinal 必須是非負整數或 None")
        if self.scoring_outcome is None:
            return
        outcome = self.scoring_outcome
        if type(outcome) is not ReplayCandidateScoringOutcomeV1:
            raise TypeError("scoring_outcome 必須是 typed replay outcome 或 None")
        if outcome.request.stock_code != self.stock_code:
            raise ValueError("scoring outcome stock_code 與 v1 row 不一致")
        if outcome.disposition is ReplayScorerDispositionV1.SCORED:
            if outcome.item is None or outcome.score_ordering != self.legacy_score_ordering:
                raise ValueError("scored outcome 必須與 v1 row 排序值一致")
            return
        if outcome.disposition is not ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION:
            raise ValueError("僅 projection 失敗可保留 legacy-only v1 row")

    def to_v1_row(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "total_score": self.total_score,
            "factor_scores": {
                "technical": self.technical_score,
                "pattern": self.pattern_score,
                "volume": self.volume_score,
                "broker_flow": self.broker_flow_score,
                "revenue": self.revenue_score,
            },
            "selection_reason": self.selection_reason,
        }


@dataclass(frozen=True, slots=True)
class ReplayProviderCallResultV1:
    """單次 provider 呼叫的 typed candidates；v1 rows 僅由 candidates 投影。"""

    candidates: tuple[_ReplayScoredCandidateV1, ...]
    as_of_date: date
    requested_top_n: int
    # 只供本次 handoff 稽核；不進 SnapshotDTO、child 或任何保存 payload。
    compatibility_scoring_outcomes: tuple[ReplayCompatibilityScoringOutcomeV1, ...] = ()

    def __post_init__(self) -> None:
        if type(self.candidates) is not tuple or any(
            type(candidate) is not _ReplayScoredCandidateV1
            for candidate in self.candidates
        ):
            raise TypeError("candidates 必須是 typed candidate tuple")
        if type(self.as_of_date) is not date or type(self.requested_top_n) is not int:
            raise TypeError("handoff date/top_n 型別不正確")
        if any(candidate.selected_ordinal is None for candidate in self.candidates):
            raise ValueError("handoff candidates 必須帶有 provider 排序序號")
        scoring_requests = tuple(
            candidate.scoring_outcome.request
            for candidate in self.candidates
            if candidate.scoring_outcome is not None
        )
        if any(request.as_of_date != self.as_of_date for request in scoring_requests):
            raise ValueError("typed scorer cutoff 與 call result 不一致")
        if len({request.request_id for request in scoring_requests}) != len(
            scoring_requests
        ):
            raise ValueError("typed scorer request_id 不可重複")
        if len({request.invocation_id for request in scoring_requests}) > 1:
            raise ValueError("typed scorer outcomes 必須來自同一 invocation")
        if type(self.compatibility_scoring_outcomes) is not tuple or any(
            type(outcome) is not ReplayCompatibilityScoringOutcomeV1
            for outcome in self.compatibility_scoring_outcomes
        ):
            raise TypeError("compatibility_scoring_outcomes 必須是 typed outcome tuple")
        compatibility_requests = tuple(
            outcome.request for outcome in self.compatibility_scoring_outcomes
        )
        if any(request.as_of_date != self.as_of_date for request in compatibility_requests):
            raise ValueError("compatibility scorer audit cutoff 與 call result 不一致")
        if len({request.request_id for request in compatibility_requests}) != len(
            compatibility_requests
        ):
            raise ValueError("compatibility scorer audit request_id 不可重複")
        if len(
            {
                request.compatibility_candidate_key
                for request in compatibility_requests
            }
        ) != len(compatibility_requests):
            raise ValueError("compatibility scorer audit candidate key 不可重複")
        audit_invocations = {request.invocation_id for request in compatibility_requests}
        if len(audit_invocations) > 1:
            raise ValueError("compatibility scorer audit 必須來自同一 invocation")
        if scoring_requests and audit_invocations and {
            request.invocation_id for request in scoring_requests
        } != audit_invocations:
            raise ValueError("typed 與 compatibility scorer audit 必須來自同一 invocation")

    def project_v1_rows(self) -> List[Dict[str, Any]]:
        """從同一候選序列新建 v1 list，不回讀 list 建立 typed child。"""

        return [candidate.to_v1_row() for candidate in self.candidates]

    @property
    def rows(self) -> List[Dict[str, Any]]:
        """相容讀取介面；每次都由 typed candidates 建立新 list。"""

        return self.project_v1_rows()

    @property
    def scoring_outcomes(self) -> tuple[ReplayCandidateScoringOutcomeV1 | None, ...]:
        """與候選同序的 scorer outcome 投影；不另存可錯接的平行序列。"""

        return tuple(candidate.scoring_outcome for candidate in self.candidates)


def _replay_score_order_token(score: float) -> ReplayScoreOrderingV1:
    """在 app 相容邊界把舊 float key 無損投影為純排序值。"""

    if math.isnan(score):
        return ReplayScoreOrderingV1.nan()
    if math.isinf(score):
        return (
            ReplayScoreOrderingV1.negative_infinity()
            if score < 0
            else ReplayScoreOrderingV1.positive_infinity()
        )
    numerator, denominator = score.as_integer_ratio()
    return ReplayScoreOrderingV1.finite(numerator, denominator)


def _finite_legacy_score_decimal(score: float) -> Decimal | None:
    """投影有限 legacy float；非有限分數在 canonical item 表示為缺值。"""

    if not math.isfinite(score):
        return None
    return Decimal(str(score))


def _capture_legacy_filter_value(
    capture: _LegacyFastFilterTraceCapture | None,
    stock_code: str | None,
    stage: _LegacyFastFilterTraceStage,
    value: object,
) -> None:
    if capture is None:
        return

    try:
        if isinstance(value, (float, np.floating)):
            converted = float(value)
            if np.isnan(converted):
                event = _LegacyFastFilterTraceEvent(
                    stock_code, stage, _LegacyFastFilterTraceStatus.UNORDERED, None
                )
            elif np.isposinf(converted):
                event = _LegacyFastFilterTraceEvent(
                    stock_code,
                    stage,
                    _LegacyFastFilterTraceStatus.POSITIVE_INFINITY,
                    None,
                )
            elif np.isneginf(converted):
                event = _LegacyFastFilterTraceEvent(
                    stock_code,
                    stage,
                    _LegacyFastFilterTraceStatus.NEGATIVE_INFINITY,
                    None,
                )
            else:
                event = _LegacyFastFilterTraceEvent(
                    stock_code,
                    stage,
                    _LegacyFastFilterTraceStatus.FINITE,
                    Decimal.from_float(converted),
                )
        elif isinstance(value, (int, np.integer)) and not isinstance(
            value, (bool, np.bool_)
        ):
            event = _LegacyFastFilterTraceEvent(
                stock_code,
                stage,
                _LegacyFastFilterTraceStatus.FINITE,
                Decimal(int(value)),
            )
        else:
            event = _LegacyFastFilterTraceEvent(
                stock_code, stage, _LegacyFastFilterTraceStatus.UNAVAILABLE, None
            )
            capture.available = False
    except Exception:
        event = _LegacyFastFilterTraceEvent(
            stock_code, stage, _LegacyFastFilterTraceStatus.UNAVAILABLE, None
        )
        capture.available = False

    try:
        capture.events.append(event)
    except Exception:
        capture.available = False


_POST_SCORE_RULE_SCREEN_KEYS = {
    ReplayPostScoreRuleV1.PRICE_CHANGE_MIN: "price_change_min",
    ReplayPostScoreRuleV1.PRICE_CHANGE_MAX: "price_change_max",
    ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN: "volume_ratio_min",
    ReplayPostScoreRuleV1.RSI_MIN: "rsi_min",
    ReplayPostScoreRuleV1.RSI_MAX: "rsi_max",
}


def _post_score_metric_fact(
    frame: pd.DataFrame,
    column: str | None,
) -> ReplayPostScoreMetricFactV1:
    if column is None or column not in frame.columns:
        return ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.MISSING_COLUMN,
            value=None,
        )
    series = frame[column]
    metric = series.iloc[-1]
    return ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
        value=None,
        legacy_kind=classify_legacy_post_score_metric_scalar(
            metric,
            series_dtype=series.dtype,
        ),
    )


def _raise_legacy_rsi_string_threshold_error(
    metric_series: pd.Series,
    threshold: object,
    *,
    rule: ReplayPostScoreRuleV1,
) -> None:
    """重現 RSI object/numeric 與字串比較的原生錯誤，而不作篩選比較。"""

    if type(threshold) is not str:
        return
    if pd.api.types.is_numeric_dtype(metric_series.dtype):
        raise TypeError(
            f"Invalid comparison between dtype={metric_series.dtype} and str"
        )
    metric = metric_series.iloc[-1]
    if metric is None or metric is pd.NA:
        return
    if type(metric) in (int, float, complex, Decimal):
        symbol = (
            ">="
            if rule is ReplayPostScoreRuleV1.RSI_MIN
            else "<="
        )
        type_name = (
            "decimal.Decimal" if type(metric) is Decimal else type(metric).__name__
        )
        raise TypeError(
            f"'{symbol}' not supported between instances of '{type_name}' and 'str'"
        )


def _emit_legacy_filter_rejection_warning(
    frame: pd.DataFrame,
    screen_filters: dict[str, Any],
) -> None:
    logger = logging.getLogger(StrategyConfigurator.__module__)
    row = frame.iloc[0]
    before_score = row.get("TotalScore", row.get("FinalScore", 0))
    before_price_change = row.get("漲幅%", "N/A")
    before_volume_change = row.get("成交量變化率%", "N/A")
    stock_code = row.get("證券代號", "Unknown")
    filter_log_count = getattr(StrategyConfigurator, "_filter_log_count", 0) + 1
    setattr(StrategyConfigurator, "_filter_log_count", filter_log_count)
    if filter_log_count <= 5:
        has_price_change = "漲幅%" in frame.columns
        has_volume_change = "成交量變化率%" in frame.columns
        logger.warning(
            f"[篩選診斷 #{filter_log_count}] 股票 {stock_code} 被過濾："
            f"總分={before_score:.2f}, "
            f"漲幅%={before_price_change} (欄位存在: {has_price_change}), "
            f"成交量變化率%={before_volume_change} (欄位存在: {has_volume_change}), "
            f"篩選條件={screen_filters}"
        )


class ReplayNativeEffectProjectionUnavailableError(RuntimeError):
    """目前 runtime 的 Pandas warning location 未經 native parity 驗證。"""


def _pandas_comparison_warning_location() -> tuple[str, int, str, dict[str, Any]]:
    """只接受已驗證的 runtime 與 Pandas 原生比較 bytecode 位置。"""

    if sys.platform != "win32":
        raise ReplayNativeEffectProjectionUnavailableError(
            "未驗證的作業系統平台；拒絕投影 Pandas comparison effect"
        )
    if tuple(sys.version_info[:3]) != (3, 11, 9):
        raise ReplayNativeEffectProjectionUnavailableError(
            "未驗證的 Python runtime；拒絕投影 Pandas comparison effect"
        )
    if pd.__version__ != "2.3.3" or np.__version__ not in {"1.26.4", "2.3.5"}:
        raise ReplayNativeEffectProjectionUnavailableError(
            "未驗證的 Pandas/NumPy runtime；拒絕投影 Pandas comparison effect"
        )

    module = sys.modules.get("pandas.core.computation.expressions")
    standard_compare = getattr(module, "_evaluate_standard", None)
    if module is None or not callable(standard_compare):
        raise ReplayNativeEffectProjectionUnavailableError(
            "無法定位 Pandas native comparison warning source"
        )
    code = getattr(standard_compare, "__code__", None)
    if (
        code is None
        or code.co_name != "_evaluate_standard"
        or code.co_firstlineno != 67
    ):
        raise ReplayNativeEffectProjectionUnavailableError(
            "Pandas native comparison function metadata 與驗證版本不符"
        )
    instructions = tuple(dis.get_instructions(standard_compare))
    call_positions = tuple(
        index for index, instruction in enumerate(instructions) if instruction.opname == "CALL"
    )
    if len(call_positions) != 2:
        raise ReplayNativeEffectProjectionUnavailableError(
            "Pandas native comparison bytecode call shape 未經驗證"
        )
    call_position = call_positions[-1]
    expected_ops = (
        "PUSH_NULL",
        "LOAD_FAST",
        "LOAD_FAST",
        "LOAD_FAST",
        "PRECALL",
        "CALL",
        "RETURN_VALUE",
    )
    observed_ops = tuple(
        instruction.opname
        for instruction in instructions[call_position - 5 : call_position + 2]
    )
    if (
        observed_ops != expected_ops
        or tuple(
            instruction.argval
            for instruction in instructions[call_position - 4 : call_position - 1]
        )
        != ("op", "a", "b")
        or instructions[call_position - 1].argval != 2
        or instructions[call_position].arg != 2
    ):
        raise ReplayNativeEffectProjectionUnavailableError(
            "Pandas native comparison call site bytecode 未經驗證"
        )
    operation_offset = instructions[call_position].offset
    starts = tuple(dis.findlinestarts(code))
    operation_lines = tuple(
        line for offset, line in starts if offset <= operation_offset
    )
    if not operation_lines or operation_lines[-1] != 73:
        raise ReplayNativeEffectProjectionUnavailableError(
            "Pandas native comparison line 未經 warning-filter parity 驗證"
        )
    filename = getattr(module, "__file__", None)
    module_name = getattr(module, "__name__", None)
    module_globals = getattr(module, "__dict__", None)
    if (
        type(filename) is not str
        or type(module_name) is not str
        or module_name != "pandas.core.computation.expressions"
        or type(module_globals) is not dict
        or not filename.replace("\\", "/").endswith(
            "/pandas/core/computation/expressions.py"
        )
    ):
        raise ReplayNativeEffectProjectionUnavailableError(
            "Pandas native comparison warning metadata 不完整或未經驗證"
        )
    return filename, 73, module_name, module_globals


def _project_replay_post_score_effect(
    effect: ReplayPostScoreEffectV1,
    *,
    warning_location: tuple[str, int, str, dict[str, Any]] | None,
) -> None:
    """依 NumPy errstate 投影純 evaluator 回傳的 native warning effect。"""

    if type(effect) is not ReplayPostScoreEffectV1:
        raise TypeError("effect 必須是 ReplayPostScoreEffectV1")
    if effect.kind is not ReplayPostScoreEffectKindV1.NUMPY_INVALID_COMPARISON:
        raise ValueError("不支援的 replay post-score effect")

    if warning_location is None:
        raise ReplayNativeEffectProjectionUnavailableError(
            "native effect 缺少本次 complex comparison 的已驗證 runtime capability"
        )
    action = np.geterr()["invalid"]
    message = effect.message
    ufunc_name = message.rsplit(" ", 1)[-1]
    if action == "ignore":
        return
    if action == "raise":
        raise FloatingPointError(message)
    if action == "warn":
        filename, lineno, module_name, module_globals = warning_location
        registry = module_globals.setdefault("__warningregistry__", {})
        if type(registry) is not dict:
            raise ReplayNativeEffectProjectionUnavailableError(
                "Pandas warning registry 型別與 native warning 不相容"
            )
        warnings.warn_explicit(
            message,
            RuntimeWarning,
            filename=filename,
            lineno=lineno,
            module=module_name,
            module_globals=module_globals,
            registry=registry,
        )
        return
    if action == "print":
        sys.stderr.write(f"Warning: {message}\n")
        return
    if action == "log":
        callback = np.geterrcall()
        if callback is None:
            raise NameError(
                f"python callback specified for invalid value (in  {ufunc_name}) but no function found."
            )
        write_method = getattr(callback, "write", None)
        if not callable(write_method):
            raise ReplayNativeEffectProjectionUnavailableError(
                "NumPy log errstate callback 缺少 native write capability"
            )
        write_method(f"Warning: {message}\n")
        return
    if action == "call":
        callback = np.geterrcall()
        if callback is None:
            raise NameError(
                f"python callback specified for invalid value (in  {ufunc_name}) but no function found."
            )
        if not callable(callback):
            raise ReplayNativeEffectProjectionUnavailableError(
                "NumPy call errstate callback 不是可呼叫物件"
            )
        callback("invalid value", 8)
        return
    raise RuntimeError(f"不支援的 NumPy invalid errstate action：{action}")


def _evaluate_replay_post_score_filters(
    frame: pd.DataFrame,
    raw_filters: Any,
    request: NeedCandidateScoring,
    evaluator: RecommendationEvaluator,
) -> bool:
    """保留 scorer 後診斷，再由 typed evaluator 唯一裁決最終 eligibility。"""

    # 與 StrategyConfigurator.generate_recommendations 同步：原始別名正規化
    # 僅在非空 scorer result 後發生，保留原始 Python 算術與例外時點。
    copied_filters = raw_filters.copy()
    screen_filters = normalize_recommendation_filter_aliases(copied_filters)
    observe_screening_diagnostics(
        frame,
        screen_filters,
        logger=logging.getLogger(StrategyConfigurator.__module__),
        counter_owner=StrategyConfigurator,
    )

    rsi_column = next(
        (column for column in ("RSI", "rsi", "RSI_14") if column in frame.columns),
        None,
    )
    facts = ReplayPostScoreFactsV1(
        request=request,
        price_change=_post_score_metric_fact(frame, "漲幅%"),
        volume_change_percent=_post_score_metric_fact(frame, "成交量變化率%"),
        rsi=_post_score_metric_fact(frame, rsi_column),
        rsi_source_column=rsi_column,
    )
    enabled_rules = tuple(
        rule
        for rule, screen_key in _POST_SCORE_RULE_SCREEN_KEYS.items()
        if screen_key in screen_filters
    )
    hints = tuple(
        hint
        for rule in enabled_rules
        if (
            hint := project_legacy_post_score_threshold_input_hint(
                screen_filters[_POST_SCORE_RULE_SCREEN_KEYS[rule]],
                filter_id=rule,
            )
        ) is not None
    )
    deferred = ReplayPostScoreDeferredPolicyV1(
        policy=ReplayPostScorePolicyV1(invocation_id=request.invocation_id),
        deferred_rules=enabled_rules,
        threshold_input_hints=hints,
    )
    step = evaluator.start_replay_post_score_staged(
        ReplayScoredRowReadyV1(request=request, facts=facts),
        deferred,
    )
    metric_columns = {
        ReplayPostScoreRuleV1.PRICE_CHANGE_MIN: "漲幅%",
        ReplayPostScoreRuleV1.PRICE_CHANGE_MAX: "漲幅%",
        ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN: "成交量變化率%",
        ReplayPostScoreRuleV1.RSI_MIN: rsi_column,
        ReplayPostScoreRuleV1.RSI_MAX: rsi_column,
    }

    while step.request is not None:
        pending = step.request
        if type(pending) is not NeedReplayPostScoreThresholdV1:
            raise AssertionError("未知 replay post-score threshold request")
        # 每個 deferred rule 都獨立取得 runtime capability；不沿用前一 rule 的位置。
        warning_location = None
        rule = pending.filter_id
        screen_key = _POST_SCORE_RULE_SCREEN_KEYS[rule]
        raw_threshold = screen_filters[screen_key]
        metric_column = metric_columns[rule]
        if metric_column is None or metric_column not in frame.columns:
            raise AssertionError("evaluator 不應要求缺欄位 threshold")
        metric_series = frame[metric_column]
        metric_scalar = metric_series.iloc[-1]

        if rule in {ReplayPostScoreRuleV1.RSI_MIN, ReplayPostScoreRuleV1.RSI_MAX}:
            _raise_legacy_rsi_string_threshold_error(
                metric_series,
                raw_threshold,
                rule=rule,
            )

        if raw_threshold is None:
            threshold = ReplayThreshold.unsupported("legacy_none_threshold")
            paired_metric = None
            warning_location = None
        else:
            unit = (
                ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT
                if rule is ReplayPostScoreRuleV1.VOLUME_CHANGE_MIN
                else ReplayThresholdUnit.PRICE_CHANGE_PERCENT
            )
            try:
                pair = project_legacy_post_score_comparison_pair(
                    metric_scalar,
                    raw_threshold,
                    unit=unit,
                )
            except UnsupportedReplayNumericScalarError as exc:
                threshold = ReplayThreshold.unsupported(
                    f"legacy_post_score_pair_unavailable:{type(exc).__name__}"
                )
                paired_metric = None
            else:
                threshold = ReplayThreshold.enabled(pair.threshold)
                paired_metric = ReplayPostScorePairedMetricV1(
                    request=pending,
                    metric=ReplayPostScoreMetricFactV1(
                        status=ReplayMetricStatus.AVAILABLE,
                        value=pair.metric,
                    ),
                )
                warning_location = (
                    _pandas_comparison_warning_location()
                    if pair.metric.domain.kind
                    is ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES
                    else None
                )

        response = ReplayPostScoreThresholdResponseV1(
            request=pending,
            threshold=threshold,
            paired_metric=paired_metric,
        )
        previous_rule_count = len(step.state.rules)
        step = evaluator.advance_replay_post_score_staged(step, response)
        completed_rules = step.state.rules[previous_rule_count:]
        for completed_rule in completed_rules:
            for effect in completed_rule.effects:
                _project_replay_post_score_effect(
                    effect,
                    warning_location=warning_location,
                )

    outcome = step.outcome
    if outcome is None:
        raise AssertionError("post-score evaluator 未回傳 terminal outcome")
    if outcome.disposition is ReplayPostScoreDispositionV1.LEGACY_ERROR:
        legacy_error = next(
            rule
            for rule in outcome.rules
            if rule.legacy_exception_type is not None
        )
        raise TypeError(legacy_error.legacy_exception_message or "legacy TypeError")
    if outcome.disposition is ReplayPostScoreDispositionV1.ACCEPTED:
        return True

    _emit_legacy_filter_rejection_warning(frame, screen_filters)
    return False


class RecommendationDataFrameProvider:
    """Use the existing recommendation scoring flow against an in-memory history slice."""

    def __init__(self, industry_mapper: Optional[IndustryMapper] = None):
        self.strategy_configurator = StrategyConfigurator()
        self.reason_engine = ReasonEngine()
        self.industry_mapper = industry_mapper

    def run_with_as_of(
        self,
        as_of_data: pd.DataFrame,
        config: Dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> List[Dict[str, Any]]:
        """以呼叫區域 typed context 接收 replay cutoff，並重用既有 provider 路徑。"""

        context = _RecommendationProviderCallContext(as_of_date=as_of_date)
        return self(
            as_of_data,
            config,
            top_n,
            _call_context=context,
        )

    def run_with_as_of_handoff(
        self,
        as_of_data: pd.DataFrame,
        config: Dict[str, Any],
        top_n: int,
        as_of_date: date,
    ) -> ReplayProviderCallResultV1:
        """同一次 scorer/evaluator 呼叫交出 typed candidates。"""

        selected: list[_ReplayScoredCandidateV1] = []
        compatibility_outcomes: list[ReplayCompatibilityScoringOutcomeV1] = []
        self(
            as_of_data,
            config,
            top_n,
            _call_context=_RecommendationProviderCallContext(as_of_date=as_of_date),
            _handoff_sink=selected,
            _compatibility_handoff_sink=compatibility_outcomes,
            _typed_handoff_only=True,
        )
        return ReplayProviderCallResultV1(
            candidates=tuple(selected),
            as_of_date=as_of_date,
            requested_top_n=operator.index(top_n),
            compatibility_scoring_outcomes=tuple(compatibility_outcomes),
        )

    def __call__(
        self,
        as_of_data: pd.DataFrame,
        config: Dict[str, Any],
        top_n: int,
        *,
        capture_sink: _LegacyFastFilterTraceCapture | None = None,
        _call_context: _RecommendationProviderCallContext | None = None,
        _handoff_sink: list[_ReplayScoredCandidateV1] | None = None,
        _compatibility_handoff_sink: list[ReplayCompatibilityScoringOutcomeV1] | None = None,
        _typed_handoff_only: bool = False,
    ) -> List[Dict[str, Any]]:
        if _call_context is not None and type(_call_context) is not _RecommendationProviderCallContext:
            raise TypeError("_call_context 必須是 RecommendationProviderCallContext 或 None")
        if type(_typed_handoff_only) is not bool:
            raise TypeError("_typed_handoff_only 必須是 bool")
        if _typed_handoff_only and _handoff_sink is None:
            raise ValueError("typed-only handoff 必須提供 invocation-local candidate sink")
        if _compatibility_handoff_sink is not None and (
            type(_compatibility_handoff_sink) is not list or _compatibility_handoff_sink
        ):
            raise ValueError("compatibility handoff sink 必須是新的空 list")

        data = self._normalize_columns(as_of_data)
        if data.empty:
            return []

        stock_col = "證券代號"
        lookback_days = int(config.get("_portfolio_lookback_days", 80))
        max_stocks = int(config.get("_portfolio_max_stocks", 200))
        latest_date = data["日期"].max()
        if pd.notna(latest_date) and lookback_days > 0:
            data = data[data["日期"] >= latest_date - pd.Timedelta(days=lookback_days)]
        stock_codes = data[stock_col].dropna().astype(str).unique()[:max_stocks]
        recommendations: list[_ReplayScoredCandidateV1] = []
        invocation_id = uuid4().hex
        evaluator = RecommendationEvaluator()

        def complete_compatibility_scoring(
            prefilter_step: ReplayCandidatePrefilterStep,
            request: NeedCompatibilityScoring,
            disposition: ReplayCompatibilityScorerDispositionV1,
            *,
            error_type: str | None = None,
        ) -> None:
            response = ReplayCompatibilityScorerResponseV1(
                request=request,
                disposition=disposition,
                error_type=error_type,
            )
            terminal_step = evaluator.complete_compatibility_scoring(
                prefilter_step,
                response,
            )
            if _compatibility_handoff_sink is not None:
                outcome = terminal_step.outcome
                if type(outcome) is not ReplayCompatibilityScoringOutcomeV1:
                    raise AssertionError("compatibility completion 缺少 terminal outcome")
                _compatibility_handoff_sink.append(outcome)

        for stock_code in stock_codes:
            stock_df = data[data[stock_col].astype(str) == stock_code].copy()
            stock_df = stock_df.sort_values("日期").reset_index(drop=True)
            history_preflight = evaluator.preflight_replay_history(len(stock_df))
            if (
                history_preflight.disposition
                is ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY
            ):
                continue
            prefilter_step = self._passes_fast_filters(
                stock_df,
                config,
                capture_sink,
                stock_code=stock_code,
                invocation_id=invocation_id,
                call_context=_call_context,
            )
            if prefilter_step is False:
                continue
            compatibility_scoring_request = None
            if prefilter_step is None:
                scoring_request = None
            elif type(prefilter_step.request) is NeedCandidateScoring:
                scoring_request = prefilter_step.request
            elif type(prefilter_step.request) is NeedCompatibilityScoring:
                scoring_request = None
                compatibility_scoring_request = prefilter_step.request
            else:
                continue

            try:
                scorer = self.strategy_configurator.generate_recommendations
                uses_builtin_scorer = _is_builtin_strategy_scorer(
                    self.strategy_configurator,
                    scorer,
                )
                uses_builtin_replay_filters = (
                    _call_context is not None
                    and scoring_request is not None
                    and uses_builtin_scorer
                    and "filters" in config
                    and bool(config["filters"])
                )
                scorer_config = config
                if uses_builtin_replay_filters:
                    # Replay 的內建 scorer 只負責建立 scored latest row；原始 filter
                    # 設定留在呼叫區域，後續由唯一 typed evaluator 消費。
                    scorer_config = dict(config)
                    scorer_config.pop("filters")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", _resolve_numpy_rank_warning(np))
                    result_df = scorer(stock_df, scorer_config)
                    result_is_empty = bool(result_df.empty)
                    if result_is_empty is False and uses_builtin_replay_filters:
                        assert scoring_request is not None
                        result_is_empty = not _evaluate_replay_post_score_filters(
                            result_df,
                            config["filters"],
                            scoring_request,
                            evaluator,
                        )
            except ReplayNativeEffectProjectionUnavailableError:
                # 沒有經驗證的 warning location 時，中止整次 replay 呼叫；
                # 不把未知 runtime 偽裝成可產生 canonical empty child 的 scorer skip。
                raise
            except Exception as exc:
                if scoring_request is not None:
                    assert prefilter_step is not None
                    response = ReplayScorerResponseV1(
                        request=scoring_request,
                        disposition=ReplayScorerDispositionV1.SKIPPED_SCORER_EXCEPTION,
                        error_type=type(exc).__name__,
                    )
                    evaluator.complete_replay_scoring(prefilter_step, response)
                elif compatibility_scoring_request is not None:
                    assert prefilter_step is not None
                    complete_compatibility_scoring(
                        prefilter_step,
                        compatibility_scoring_request,
                        ReplayCompatibilityScorerDispositionV1.SKIPPED_SCORER_EXCEPTION,
                        error_type=type(exc).__name__,
                    )
                continue
            if result_is_empty:
                if scoring_request is not None:
                    assert prefilter_step is not None
                    response = ReplayScorerResponseV1(
                        request=scoring_request,
                        disposition=ReplayScorerDispositionV1.SKIPPED_EMPTY,
                    )
                    evaluator.complete_replay_scoring(prefilter_step, response)
                elif compatibility_scoring_request is not None:
                    assert prefilter_step is not None
                    complete_compatibility_scoring(
                        prefilter_step,
                        compatibility_scoring_request,
                        ReplayCompatibilityScorerDispositionV1.SKIPPED_EMPTY,
                    )
                continue

            try:
                latest_row = result_df.iloc[-1].copy()
                close_col = self._first_existing_column(latest_row.index, ["收盤價", "Close", "close"])
                prev_price = pd.to_numeric(stock_df.iloc[-2].get(close_col, 0), errors="coerce") if close_col else 0
                curr_price = pd.to_numeric(latest_row.get(close_col, 0), errors="coerce") if close_col else 0
                price_change = ((curr_price - prev_price) / prev_price * 100) if prev_price and not pd.isna(prev_price) else 0
                latest_row["漲幅%"] = 0 if pd.isna(price_change) else price_change

                reasons = self.reason_engine.generate_reasons(latest_row, config)
                final_score = latest_row.get(
                    "FinalScore",
                    latest_row.get("TotalScore", latest_row.get("綜合評分", 0)),
                )
                stock_name = str(
                    latest_row.get(
                        "證券名稱", stock_df.iloc[-1].get("證券名稱", stock_code)
                    )
                )
                total_score = float(final_score or 0)
                technical_score = float(latest_row.get("IndicatorScore", 0) or 0)
                pattern_score = float(latest_row.get("PatternScore", 0) or 0)
                volume_score = float(latest_row.get("VolumeScore", 0) or 0)
                broker_flow_score = float(latest_row.get("BrokerFlowScore", 0) or 0)
                revenue_score = float(latest_row.get("RevenueScore", 0) or 0)
                selection_reason = self.reason_engine.format_reason_text(
                    reasons, max_reasons=3
                )
                candidate = _ReplayScoredCandidateV1(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    total_score=total_score,
                    technical_score=technical_score,
                    pattern_score=pattern_score,
                    volume_score=volume_score,
                    broker_flow_score=broker_flow_score,
                    revenue_score=revenue_score,
                    selection_reason=selection_reason,
                    legacy_score_ordering=_replay_score_order_token(total_score),
                )
            except Exception as exc:
                if scoring_request is not None:
                    assert prefilter_step is not None
                    # 維持既有 per-stock row projection skip，並留下 typed 原因。
                    # 這個區塊中的 float coercion 原本就在 scorer try 外層 skip 內。
                    response = ReplayScorerResponseV1(
                        request=scoring_request,
                        disposition=ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
                        error_type=type(exc).__name__,
                    )
                    evaluator.complete_replay_scoring(prefilter_step, response)
                elif compatibility_scoring_request is not None:
                    assert prefilter_step is not None
                    complete_compatibility_scoring(
                        prefilter_step,
                        compatibility_scoring_request,
                        ReplayCompatibilityScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
                        error_type=type(exc).__name__,
                    )
                continue

            if compatibility_scoring_request is not None:
                assert prefilter_step is not None
                complete_compatibility_scoring(
                    prefilter_step,
                    compatibility_scoring_request,
                    ReplayCompatibilityScorerDispositionV1.SCORED,
                )
                # 空白 code 保留 v1 row，但其 scorer terminal 只進 call-local audit。
                recommendations.append(candidate)
                continue

            if prefilter_step is None:
                # 空／純空白代碼只走明示的相容 scorer handoff；保留 v1 row，
                # 在無 active prefilter 的既有路徑不建立 evaluator identity。
                recommendations.append(candidate)
                continue

            assert prefilter_step is not None and scoring_request is not None
            if _call_context is not None and not uses_builtin_scorer:
                # 注入／覆寫 scorer 無法宣稱已套用 built-in replay policy；
                # 保留 v1 row，但關閉 canonical child，不解析自訂 filter 形狀。
                recommendations.append(candidate)
                continue
            try:
                if candidate.selection_reason is None:
                    typed_reason_text = None
                elif type(candidate.selection_reason) is str:
                    typed_reason_text = candidate.selection_reason
                else:
                    raise TypeError("selection_reason 不可投影為 RecommendationItem")
                item = RecommendationItem(
                    stock_code=stock_code,
                    stock_name=candidate.stock_name,
                    rule_score=_finite_legacy_score_decimal(candidate.total_score),
                    indicator_score=_finite_legacy_score_decimal(candidate.technical_score),
                    pattern_score=_finite_legacy_score_decimal(candidate.pattern_score),
                    volume_score=_finite_legacy_score_decimal(candidate.volume_score),
                    reason_text=typed_reason_text,
                )
                response = ReplayScorerResponseV1(
                    request=scoring_request,
                    disposition=ReplayScorerDispositionV1.SCORED,
                    item=item,
                    score_ordering=candidate.legacy_score_ordering,
                )
            except Exception as exc:
                # v1 row 已合法形成；typed projection 不可表達時保留相容 row，
                # 同時讓後續 canonical consumer 看見明示的 skipped outcome。
                response = ReplayScorerResponseV1(
                    request=scoring_request,
                    disposition=ReplayScorerDispositionV1.SKIPPED_PROJECTION_EXCEPTION,
                    error_type=type(exc).__name__,
                )
            outcome = evaluator.complete_replay_scoring(prefilter_step, response)
            recommendations.append(replace(candidate, scoring_outcome=outcome))

        policy = ReplayExecutionPolicyV1(
            top_n=operator.index(top_n),
            lookback_calendar_days=lookback_days,
            first_seen_max_stocks=max_stocks,
        )
        ordinals = evaluator.rank_replay_candidate_ordinals(
            tuple(item.legacy_score_ordering for item in recommendations),
            policy,
        )
        selected = [
            replace(recommendations[index], selected_ordinal=ordinal)
            for ordinal, index in enumerate(ordinals)
        ]
        if _handoff_sink is not None:
            _handoff_sink.extend(selected)
        if _typed_handoff_only:
            return []
        return [item.to_v1_row() for item in selected]

    def _passes_fast_filters(
        self,
        stock_df: pd.DataFrame,
        config: Dict[str, Any],
        capture_sink: _LegacyFastFilterTraceCapture | None = None,
        *,
        stock_code: str | None = None,
        invocation_id: str | None = None,
        call_context: _RecommendationProviderCallContext | None = None,
    ) -> ReplayCandidatePrefilterStep | Literal[False] | None:
        try:
            return self._passes_fast_filters_impl(
                stock_df,
                config,
                capture_sink,
                stock_code=stock_code,
                invocation_id=invocation_id,
                call_context=call_context,
            )
        except Exception:
            if capture_sink is not None:
                try:
                    capture_sink.available = False
                except Exception:
                    pass
            raise

    def _passes_fast_filters_impl(
        self,
        stock_df: pd.DataFrame,
        config: Dict[str, Any],
        capture_sink: _LegacyFastFilterTraceCapture | None = None,
        *,
        stock_code: str | None = None,
        invocation_id: str | None = None,
        call_context: _RecommendationProviderCallContext | None = None,
    ) -> ReplayCandidatePrefilterStep | Literal[False] | None:
        filters = config.get("filters", {})
        active_evaluator = RecommendationEvaluator()
        if not filters:
            candidate_code = (
                stock_code
                if stock_code is not None
                else str(stock_df.iloc[-1].get("證券代號", "UNKNOWN"))
            )
            if not candidate_code.strip():
                if call_context is not None:
                    maximum_row_date = parse_stock_dates(stock_df["日期"]).max().date()
                    if maximum_row_date > call_context.as_of_date:
                        raise ValueError("maximum_row_date 超過 replay cutoff")
                    if "available_date" in stock_df:
                        maximum_available_date = parse_stock_dates(
                            stock_df["available_date"]
                        ).max().date()
                        if maximum_available_date > call_context.as_of_date:
                            raise ValueError(
                                "maximum_available_date 超過 replay cutoff"
                            )
                return None
            maximum_row_date = parse_stock_dates(stock_df["日期"]).max().date()
            cutoff = (
                call_context.as_of_date
                if call_context is not None
                else maximum_row_date
            )
            available_present = (
                call_context is not None and "available_date" in stock_df
            )
            maximum_available_date = (
                parse_stock_dates(stock_df["available_date"]).max().date()
                if available_present
                else None
            )
            observations = ReplayPrefilterObservations(
                stock_code=candidate_code,
                as_of_date=cutoff,
                history_rows=len(stock_df),
                maximum_row_date=maximum_row_date,
                availability_column_present=available_present,
                maximum_available_date=maximum_available_date,
                price_change_status=ReplayMetricStatus.NOT_REQUESTED,
                volume_change_status=(
                    ReplayMetricStatus.NOT_REQUESTED
                    if len(stock_df) >= 21
                    else ReplayMetricStatus.INSUFFICIENT_WINDOW
                ),
            )
            return active_evaluator.start_replay_prefilter(
                ReplayCandidateHistoryFacts(
                    invocation_id=invocation_id or uuid4().hex,
                    observations=observations,
                ),
                ReplayFastFilterPolicyV1(),
            )

        close_col = self._first_existing_column(stock_df.columns, ["收盤價", "Close", "close"])
        price_change: object | None = None
        price_status = ReplayMetricStatus.MISSING_COLUMN
        if close_col and len(stock_df) >= 2:
            prev_price = pd.to_numeric(stock_df.iloc[-2].get(close_col, 0), errors="coerce")
            curr_price = pd.to_numeric(stock_df.iloc[-1].get(close_col, 0), errors="coerce")
            price_change = ((curr_price - prev_price) / prev_price * 100) if prev_price and not pd.isna(prev_price) else 0
            price_status = (
                ReplayMetricStatus.AVAILABLE
                if prev_price and not pd.isna(prev_price)
                else ReplayMetricStatus.ZERO_DENOMINATOR
            )
            _capture_legacy_filter_value(
                capture_sink,
                stock_code,
                _LegacyFastFilterTraceStage.PRICE_CHANGE_METRIC,
                price_change,
            )
        elif close_col:
            price_status = ReplayMetricStatus.INSUFFICIENT_WINDOW

        price_min = filters.get("price_change_min") if close_col else None
        price_max = filters.get("price_change_max") if close_col else None
        volume_col = self._first_existing_column(stock_df.columns, ["成交股數", "成交量", "Volume", "volume"])
        volume_min = filters.get("volume_ratio_min")
        if volume_col and volume_min is not None:
            volume_status = (
                ReplayMetricStatus.NOT_REQUESTED
                if len(stock_df) >= 21
                else ReplayMetricStatus.INSUFFICIENT_WINDOW
            )
        else:
            volume_status = ReplayMetricStatus.MISSING_COLUMN

        if price_min is not None or price_max is not None:
            staged_price_status = (
                ReplayMetricStatus.NOT_REQUESTED
                if price_status in {
                    ReplayMetricStatus.AVAILABLE,
                    ReplayMetricStatus.ZERO_DENOMINATOR,
                }
                else price_status
            )
        else:
            staged_price_status = ReplayMetricStatus.MISSING_COLUMN

        maximum_row_date = parse_stock_dates(stock_df["日期"]).max().date()
        cutoff = call_context.as_of_date if call_context is not None else maximum_row_date
        available_present = call_context is not None and "available_date" in stock_df
        maximum_available_date = (
            parse_stock_dates(stock_df["available_date"]).max().date()
            if available_present
            else None
        )
        candidate_code = (
            stock_code
            if stock_code is not None
            else str(stock_df.iloc[-1].get("證券代號", "UNKNOWN"))
        )
        compatibility_key = None
        if not candidate_code.strip():
            compatibility_key = ReplayCompatibilityCandidateKeyV1(
                invocation_id=invocation_id or uuid4().hex,
                candidate_id=uuid4().hex,
            )
        candidate_invocation_id = (
            invocation_id
            or (
                compatibility_key.invocation_id
                if compatibility_key is not None
                else uuid4().hex
            )
        )
        policy = ReplayFastFilterPolicyV1(
            price_change_min=(
                ReplayThreshold.pending()
                if price_min is not None
                else ReplayThreshold.disabled()
            ),
            price_change_max=(
                ReplayThreshold.pending()
                if price_max is not None
                else ReplayThreshold.disabled()
            ),
            volume_minimum=ReplayVolumeThresholdV1.effective_change_percent(
                ReplayThreshold.pending()
                if volume_min is not None
                else ReplayThreshold.disabled()
            ),
        )
        prefilter_observations: ReplayPrefilterObservations | ReplayCompatibilityPrefilterObservationsV1
        if compatibility_key is None:
            prefilter_observations = ReplayPrefilterObservations(
                stock_code=candidate_code,
                as_of_date=cutoff,
                history_rows=len(stock_df),
                maximum_row_date=maximum_row_date,
                availability_column_present=available_present,
                maximum_available_date=maximum_available_date,
                price_change_status=staged_price_status,
                volume_change_status=volume_status,
            )
        else:
            prefilter_observations = ReplayCompatibilityPrefilterObservationsV1(
                stock_code=candidate_code,
                as_of_date=cutoff,
                history_rows=len(stock_df),
                maximum_row_date=maximum_row_date,
                availability_column_present=available_present,
                maximum_available_date=maximum_available_date,
                compatibility_candidate_key=compatibility_key,
                price_change_status=staged_price_status,
                volume_change_status=volume_status,
            )
        step = active_evaluator.start_replay_prefilter(
            ReplayCandidateHistoryFacts(
                invocation_id=candidate_invocation_id,
                observations=prefilter_observations,
            ),
            policy,
        )
        # 原始 scalar 僅保留在本候選呼叫中；門檻解析前不得預先投影。
        raw_scalars: dict[str, tuple[object, ReplayMetricStatus]] = {}
        price_metric_request_id: str | None = None
        volume_metric_request_id: str | None = None
        while True:
            request = step.request
            if type(request) in {NeedCandidateScoring, NeedCompatibilityScoring}:
                return step
            if request is None:
                return step
            if type(request) is not NeedReplayPrefilterFact:
                raise AssertionError("未知的 replay prefilter request")

            kind = request.kind
            if kind is ReplayPrefilterFactKind.PRICE_CHANGE_METRIC:
                if price_change is None:
                    raise AssertionError("price metric request 缺少舊 scalar")
                price_metric_request_id = request.request_id
                raw_scalars[request.request_id] = (price_change, price_status)
                response = ReplayPrefilterFactResponse(
                    request=request,
                    metric_status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
                )
            elif kind is ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC:
                if volume_col is None:
                    raise AssertionError("volume metric request 缺少來源欄位")
                latest_volume = pd.to_numeric(stock_df[volume_col].iloc[-1], errors="coerce")
                volume_ma20 = pd.to_numeric(stock_df[volume_col].iloc[-21:-1], errors="coerce").mean()
                volume_change = ((latest_volume / volume_ma20) - 1) * 100 if volume_ma20 and not pd.isna(volume_ma20) else 0
                metric_status = (
                    ReplayMetricStatus.AVAILABLE
                    if volume_ma20 and not pd.isna(volume_ma20)
                    else ReplayMetricStatus.ZERO_DENOMINATOR
                )
                _capture_legacy_filter_value(
                    capture_sink,
                    stock_code,
                    _LegacyFastFilterTraceStage.VOLUME_CHANGE_METRIC,
                    volume_change,
                )
                volume_metric_request_id = request.request_id
                raw_scalars[request.request_id] = (volume_change, metric_status)
                response = ReplayPrefilterFactResponse(
                    request=request,
                    metric_status=ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION,
                )
            elif kind in {
                ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
                ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
                ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
            }:
                if kind is ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD:
                    raw_threshold = price_min
                    if raw_threshold is None:
                        raise AssertionError("price minimum request 缺少門檻")
                    metric_request_id = price_metric_request_id
                    unit = ReplayThresholdUnit.PRICE_CHANGE_PERCENT
                    trace_stage = _LegacyFastFilterTraceStage.PRICE_CHANGE_MIN_THRESHOLD
                    effective_threshold = float(raw_threshold)
                elif kind is ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD:
                    raw_threshold = price_max
                    if raw_threshold is None:
                        raise AssertionError("price maximum request 缺少門檻")
                    metric_request_id = price_metric_request_id
                    unit = ReplayThresholdUnit.PRICE_CHANGE_PERCENT
                    trace_stage = _LegacyFastFilterTraceStage.PRICE_CHANGE_MAX_THRESHOLD
                    effective_threshold = float(raw_threshold)
                else:
                    raw_threshold = volume_min
                    if raw_threshold is None:
                        raise AssertionError("volume minimum request 缺少門檻")
                    metric_request_id = volume_metric_request_id
                    unit = ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT
                    trace_stage = _LegacyFastFilterTraceStage.VOLUME_CHANGE_MIN_EFFECTIVE_PERCENT
                    effective_threshold = self._normalize_volume_threshold(float(raw_threshold))
                _capture_legacy_filter_value(
                    capture_sink,
                    stock_code,
                    trace_stage,
                    effective_threshold,
                )
                if metric_request_id is None:
                    raise AssertionError("threshold request 缺少先前的 metric request")
                raw_metric, metric_status = raw_scalars[metric_request_id]
                pair = project_legacy_comparison_pair(
                    raw_metric,
                    effective_threshold,
                    unit=unit,
                )
                response = ReplayPrefilterFactResponse(
                    request=request,
                    threshold=(
                        ReplayThreshold.enabled(pair.threshold)
                        if unit is ReplayThresholdUnit.PRICE_CHANGE_PERCENT
                        else None
                    ),
                    volume_threshold=(
                        ReplayVolumeThresholdV1.effective_change_percent(
                            ReplayThreshold.enabled(pair.threshold)
                        )
                        if unit is ReplayThresholdUnit.VOLUME_EFFECTIVE_CHANGE_PERCENT
                        else None
                    ),
                    paired_metric_request_id=metric_request_id,
                    paired_metric_status=metric_status,
                    paired_metric_value=pair.metric,
                )
            else:
                raise AssertionError("未知的 replay prefilter fact kind")
            step = active_evaluator.advance_replay_prefilter(step.state, response)

    def _normalize_volume_threshold(self, volume_ratio_min: float) -> float:
        if -50 <= volume_ratio_min <= 10:
            return (volume_ratio_min - 1) * 100
        return volume_ratio_min

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        if "日期" not in data.columns:
            raise ValueError("history 必須包含 日期 欄位")
        data["日期"] = parse_stock_dates(data["日期"])
        data = data[data["日期"].notna()]

        if "證券代號" not in data.columns and "股票代號" in data.columns:
            data["證券代號"] = data["股票代號"]
        if "證券代號" not in data.columns:
            raise ValueError("history 必須包含 證券代號 或 股票代號 欄位")
        data["證券代號"] = data["證券代號"].astype(str)

        if "證券名稱" not in data.columns:
            data["證券名稱"] = data["股票名稱"] if "股票名稱" in data.columns else data["證券代號"]
        return data

    def _first_existing_column(self, columns, candidates: List[str]) -> Optional[str]:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None
