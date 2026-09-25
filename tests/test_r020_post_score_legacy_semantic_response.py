"""固定兩種已觀測的原生 post-score 語意及純 evaluator 回應。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app_module.recommendation.replay_numeric_projection import (
    classify_legacy_post_score_metric_scalar,
    project_legacy_post_score_threshold_input_hint,
)
from decision_module.recommendation.evaluate import (
    NeedCandidateScoring,
    ReplayCandidateHistoryFacts,
    ReplayFastFilterPolicyV1,
    ReplayPostScoreDeferredPolicyV1,
    ReplayPostScoreDiagnosticCodeV1,
    ReplayPostScoreDispositionV1,
    ReplayPostScoreFactsV1,
    ReplayPostScoreMetricFactV1,
    ReplayPostScoreMetricLegacyKindV1,
    ReplayPostScorePolicyV1,
    ReplayPostScoreRuleDispositionV1,
    ReplayPostScoreRuleV1,
    ReplayPostScoreThresholdInputHintV1,
    ReplayPostScoreThresholdResponseV1,
    ReplayPostScoreThresholdInputKindV1,
    ReplayScoredRowReadyV1,
    RecommendationEvaluator,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonOperand,
    ReplayMetricStatus,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
    ReplayPrefilterObservations,
    ReplayThreshold,
)
from decision_module.strategy_configurator import StrategyConfigurator


def _operand(value: int) -> ReplayComparisonOperand:
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_INT),
        domain=ReplayComparisonDomain.exact_rational(),
        real=ReplayComparisonComponent.finite(value),
    )


def _ready(metric: ReplayPostScoreMetricFactV1) -> tuple[
    RecommendationEvaluator, ReplayScoredRowReadyV1
]:
    evaluator = RecommendationEvaluator()
    history = ReplayCandidateHistoryFacts(
        invocation_id="legacy-semantic-invocation",
        observations=ReplayPrefilterObservations(
            stock_code="SYN-LEGACY",
            as_of_date=date(2026, 9, 4),
            history_rows=20,
            maximum_row_date=date(2026, 9, 4),
            availability_column_present=False,
            maximum_available_date=None,
        ),
    )
    prefilter = evaluator.start_replay_prefilter(
        history,
        ReplayFastFilterPolicyV1(),
    )
    request = prefilter.request
    assert type(request) is NeedCandidateScoring
    facts = ReplayPostScoreFactsV1(
        request=request,
        price_change=metric,
        volume_change_percent=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.MISSING_COLUMN,
            value=None,
        ),
        rsi=ReplayPostScoreMetricFactV1(
            status=ReplayMetricStatus.AVAILABLE,
            value=_operand(50),
        ),
        rsi_source_column="RSI",
    )
    return evaluator, ReplayScoredRowReadyV1(request=request, facts=facts)


def _unsupported_metric(
    legacy_kind: ReplayPostScoreMetricLegacyKindV1,
) -> ReplayPostScoreMetricFactV1:
    return ReplayPostScoreMetricFactV1(
        status=ReplayMetricStatus.UNSUPPORTED,
        value=None,
        unsupported_reason="present_metric_not_projectable",
        legacy_kind=legacy_kind,
    )


def _deferred_policy(
    ready: ReplayScoredRowReadyV1,
    hint: ReplayPostScoreThresholdInputHintV1 | None,
) -> ReplayPostScoreDeferredPolicyV1:
    return ReplayPostScoreDeferredPolicyV1(
        policy=ReplayPostScorePolicyV1(invocation_id=ready.request.invocation_id),
        deferred_rules=(ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,),
        threshold_input_hints=() if hint is None else (hint,),
    )


def test_projector_classifies_only_the_two_frozen_legacy_scalar_cases() -> None:
    assert classify_legacy_post_score_metric_scalar(
        Decimal("1.25"), series_dtype=object
    ) is (
        ReplayPostScoreMetricLegacyKindV1.PYTHON_DECIMAL_OBJECT
    )
    assert classify_legacy_post_score_metric_scalar(
        pd.NA, series_dtype=object
    ) is (
        ReplayPostScoreMetricLegacyKindV1.PANDAS_OBJECT_NA
    )
    assert classify_legacy_post_score_metric_scalar(1.25, series_dtype=object) is None
    assert classify_legacy_post_score_metric_scalar(None, series_dtype=object) is None
    assert classify_legacy_post_score_metric_scalar(
        pd.NA, series_dtype=pd.Series([pd.NA], dtype="Int64").dtype
    ) is None

    string_hint = project_legacy_post_score_threshold_input_hint(
        "bad",
        filter_id=ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
    )
    assert string_hint is not None
    assert string_hint.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    assert string_hint.input_kind is ReplayPostScoreThresholdInputKindV1.PYTHON_STRING
    assert string_hint.display_text == "bad"
    assert (
        project_legacy_post_score_threshold_input_hint(
            1,
            filter_id=ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
        )
        is None
    )


def test_decimal_string_threshold_returns_native_type_error_before_threshold_request(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Decimal + str 先回報原生 TypeError；不呼叫 threshold 解析階段。"""

    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")
    with pytest.raises(
        TypeError,
        match=r"'>=' not supported between instances of 'decimal\.Decimal' and 'str'",
    ):
        StrategyConfigurator().screen_stocks(
            pd.DataFrame(
                {
                    "證券代號": ["DECIMAL"],
                    "漲幅%": pd.Series([Decimal("1.25")], dtype=object),
                }
            ),
            {"price_change_min": "bad"},
        )
    assert not [record for record in caplog.records if record.levelname == "WARNING"]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 0

    metric = _unsupported_metric(
        ReplayPostScoreMetricLegacyKindV1.PYTHON_DECIMAL_OBJECT
    )
    evaluator, ready = _ready(metric)
    hint = project_legacy_post_score_threshold_input_hint(
        "bad",
        filter_id=ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
    )
    step = evaluator.start_replay_post_score_staged(
        ready,
        _deferred_policy(ready, hint),
    )

    assert step.request is None
    assert step.outcome is not None
    assert step.outcome.disposition is ReplayPostScoreDispositionV1.LEGACY_ERROR
    rule = step.outcome.rules[0]
    assert rule.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    assert rule.disposition is ReplayPostScoreRuleDispositionV1.LEGACY_TYPE_ERROR
    assert rule.legacy_exception_type == "TypeError"
    assert rule.legacy_exception_message == (
        "'>=' not supported between instances of 'decimal.Decimal' and 'str'"
    )
    assert rule.threshold_input_hint == hint
    assert step.state.next_rule_index == len(ReplayPostScoreRuleV1)
    assert step.state.deferred_policy.deferred_rules == ()
    assert step.state.deferred_policy.threshold_input_hints == ()
    assert not [record for record in caplog.records if record.levelname == "WARNING"]


def test_object_pd_na_returns_rejection_and_exact_diagnostic_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """object-dtype pd.NA + str 產生 legacy 警告資料並排除，不解析門檻。"""

    from app_module.recommendation.replay_numeric_projection import (
        classify_legacy_post_score_metric_scalar,
    )

    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)
    caplog.set_level("WARNING", logger="decision_module.strategy_configurator")
    legacy_frame = pd.DataFrame(
        {
            "證券代號": ["NA"],
            "漲幅%": pd.Series([pd.NA], dtype=object),
        }
    )
    legacy_result = StrategyConfigurator().screen_stocks(
        legacy_frame,
        {"price_change_min": "bad"},
    )
    assert legacy_result.empty
    assert [record.getMessage() for record in caplog.records] == [
        "[漲幅篩選] 要求 >= bad%, 但樣本值=<NA>%"
    ]
    assert getattr(StrategyConfigurator, "_price_filter_log_count") == 1
    caplog.clear()
    monkeypatch.setattr(StrategyConfigurator, "_price_filter_log_count", 0, raising=False)

    legacy_kind = classify_legacy_post_score_metric_scalar(
        pd.NA,
        series_dtype=legacy_frame["漲幅%"].dtype,
    )
    assert legacy_kind is ReplayPostScoreMetricLegacyKindV1.PANDAS_OBJECT_NA
    metric = _unsupported_metric(legacy_kind)
    evaluator, ready = _ready(metric)
    hint = project_legacy_post_score_threshold_input_hint(
        "bad",
        filter_id=ReplayPostScoreRuleV1.PRICE_CHANGE_MIN,
    )
    step = evaluator.start_replay_post_score_staged(
        ready,
        _deferred_policy(ready, hint),
    )

    assert step.request is None
    assert step.outcome is not None
    assert step.outcome.disposition is ReplayPostScoreDispositionV1.REJECTED
    assert len(step.outcome.rules) == 1
    rule = step.outcome.rules[0]
    assert rule.disposition is ReplayPostScoreRuleDispositionV1.REJECTED
    assert rule.reason_code == "legacy_object_na_rejected"
    assert rule.threshold_input_hint == hint
    assert rule.diagnostic_event is not None
    assert rule.diagnostic_event.code is (
        ReplayPostScoreDiagnosticCodeV1.PRICE_CHANGE_OBJECT_NA_REJECTED
    )
    assert rule.diagnostic_event.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
    assert rule.diagnostic_event.message == (
        "[漲幅篩選] 要求 >= bad%, 但樣本值=<NA>%"
    )
    assert rule.diagnostic_event.counter_delta == 1
    assert step.state.next_rule_index == len(ReplayPostScoreRuleV1)
    assert step.state.deferred_policy.deferred_rules == ()
    assert step.state.deferred_policy.threshold_input_hints == ()
    assert not caplog.records


def test_uncharacterized_unsupported_combinations_remain_unsupported() -> None:
    """沒有凍結 raw-string hint 時，不推廣 Decimal／pd.NA 的 native 特例。"""

    for legacy_kind in (
        ReplayPostScoreMetricLegacyKindV1.PYTHON_DECIMAL_OBJECT,
        ReplayPostScoreMetricLegacyKindV1.PANDAS_OBJECT_NA,
    ):
        evaluator, ready = _ready(_unsupported_metric(legacy_kind))
        step = evaluator.start_replay_post_score_staged(
            ready,
            _deferred_policy(ready, None),
        )
        assert step.request is not None
        assert step.request.filter_id is ReplayPostScoreRuleV1.PRICE_CHANGE_MIN
        terminal = evaluator.advance_replay_post_score_staged(
            step,
            # 只驗證未凍結組合保留既有 generic unsupported contract。
            ReplayPostScoreThresholdResponseV1(
                request=step.request,
                threshold=ReplayThreshold.enabled(_operand(0)),
            ),
        )
        assert terminal.outcome is not None
        assert terminal.outcome.disposition is ReplayPostScoreDispositionV1.UNSUPPORTED
