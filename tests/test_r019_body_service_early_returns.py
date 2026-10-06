"""R019 service 層成功早退的 typed body-result 測試。"""

from __future__ import annotations

from copy import copy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation.body_result import (
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
)
from app_module.recommendation.input_preparation import RecommendationInputSession
from app_module.recommendation_errors import RecommendationUniverseTooSmallError
from app_module.recommendation_service import RecommendationService
from decision_module.recommendation.contracts import DecisionBatch
from recommendation_test_support import build_recommendation_test_preparer


DECISION_DATE = "2026-05-20"
UNIVERSE_IDENTITY_KEYS = (
    "universe_id",
    "universe_hash",
    "universe_identity_schema",
    "universe_policy_id",
    "universe_policy_hash",
    "universe_policy_schema",
    "universe_policy_spec",
    "universe_snapshot_id",
    "universe_snapshot_hash",
    "universe_snapshot_schema",
    "universe_snapshot_selected_codes_hash",
    "universe_snapshot_source_provider_id",
    "universe_snapshot_spec",
)


class _FrameProvider:
    """只提供每個測試自建的記憶體行情 frame。"""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def __call__(self) -> pd.DataFrame:
        return self.frame.copy(deep=True)


def _market_frame(codes: tuple[str, ...], *, periods: int = 20) -> pd.DataFrame:
    dates = pd.date_range("2026-05-01", periods=periods, freq="D")
    rows: list[dict[str, object]] = []
    for code in codes:
        for current_date in dates:
            rows.append(
                {
                    "日期": current_date,
                    "available_date": current_date,
                    "證券代號": code,
                    "證券名稱": f"{code}_NAME",
                    "收盤價": Decimal("100.00"),
                    "成交股數": 1000,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ],
    )


def _build_service(
    tmp_path: Path,
    codes: tuple[str, ...],
    scores: dict[str, object],
    *,
    empty_codes: tuple[str, ...] = (),
    pit_reader: object | None = None,
    periods: int = 20,
) -> tuple[RecommendationService, list[str]]:
    config = SimpleNamespace(
        db_file=tmp_path / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
    )
    market_provider = _FrameProvider(_market_frame(codes, periods=periods))
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        pit_membership_reader=pit_reader,
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=market_provider,
            pit_membership_reader=pit_reader,
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""
    calls: list[str] = []

    def generate(stock_frame: pd.DataFrame, _config: dict[str, object]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        calls.append(code)
        if code in empty_codes:
            return pd.DataFrame()
        score = scores[code]
        return pd.DataFrame(
            {
                "FinalScore": [score],
                "TotalScore": [score],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return service, calls


def _body_result(service: RecommendationService) -> RecommendationBodyResult:
    body = getattr(service, "_test_body_result", None)
    assert type(body) is RecommendationBodyResult
    assert type(body.decision) is DecisionBatch
    assert isinstance(body.context, RecommendationBodyContextFacts)
    return body


def _assessment_projection(body: RecommendationBodyResult) -> list[tuple[object, ...]]:
    return [
        (
            assessment.stock_code,
            assessment.eligible,
            assessment.reasons,
            assessment.missing_data,
            tuple(
                (item.evidence_id, item.reason)
                for item in assessment.negative_evidence
            ),
        )
        for assessment in body.decision.assessments
    ]


def _run_invocation_body(
    service: RecommendationService,
    config: dict[str, object],
    *,
    result_id: str,
    as_of_date: str = DECISION_DATE,
) -> tuple[RecommendationService, list[object]]:
    """複製基底 service，並透過 preparer.begin 建立本次公開 input session。"""
    invocation = copy(service)
    input_session = _begin_input_session(invocation)
    body = invocation._run_recommendation_body_result(
        config=config,
        as_of_date=as_of_date,
        result_id=result_id,
        input_session=input_session,
    )
    invocation._test_body_result = body
    return invocation, [snapshot.materialize() for snapshot in body.legacy_recommendations]


def _begin_input_session(
    invocation: RecommendationService,
) -> RecommendationInputSession:
    return invocation.recommendation_input_preparer.begin(
        invocation.config,
        market_data_provider=invocation.market_data_provider,
    )


def _run_empty_branch(
    tmp_path: Path,
    branch: str,
) -> tuple[RecommendationService, list[object]]:
    if branch == "empty_frame":
        service, _ = _build_service(tmp_path, (), {})
        invocation, result = _run_invocation_body(
            service, {}, result_id="r019-empty-frame"
        )
    elif branch == "pit_unavailable":
        service, _ = _build_service(
            tmp_path, ("OTHER", "PIT"), {"OTHER": 70, "PIT": 80}
        )
        invocation, result = _run_invocation_body(
            service,
            {"filters": {"industry": "半導體業"}},
            result_id="r019-pit-unavailable",
        )
    elif branch == "pit_empty":
        pit = SimpleNamespace(
            industry_filter_usable=True,
            rows=(),
            lineage={"fixture_id": "r019-empty-pit"},
            status="accepted",
            quality="observed",
            warnings=(),
        )
        reader = SimpleNamespace(read=MagicMock(return_value=pit))
        service, _ = _build_service(
            tmp_path,
            ("OTHER", "PIT"),
            {"OTHER": 70, "PIT": 80},
            pit_reader=reader,
        )
        invocation, result = _run_invocation_body(
            service,
            {
                "filters": {"industry": "半導體業"},
                "pit_decision_at": "2026-05-20T16:00:00+08:00",
            },
            result_id="r019-pit-empty",
        )
    elif branch == "no_scored_quantile":
        service, _ = _build_service(
            tmp_path,
            ("NO_SIGNAL_A", "NO_SIGNAL_B"),
            {},
            empty_codes=("NO_SIGNAL_A", "NO_SIGNAL_B"),
        )
        invocation, result = _run_invocation_body(
            service,
            {
                "recommendation_ranking": {
                    "threshold_mode": "quantile",
                    "recommendation_min_percentile_bp": 5000,
                    "recommendation_min_universe_size": 2,
                    "recommendation_ranking_method": "nearest_rank",
                }
            },
            result_id="r019-no-scored-quantile",
        )
    else:
        raise AssertionError(f"未支援測試分支：{branch}")
    assert result == []
    return invocation, result


@pytest.fixture
def isolated_test_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """將 profile 與資料根目錄限制在 pytest 的新暫存目錄。"""
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))
    return tmp_path


@pytest.mark.parametrize(
    ("branch", "result_id", "has_universe_identity"),
    [
        ("empty_frame", "r019-empty-frame", False),
        ("pit_unavailable", "r019-pit-unavailable", False),
        ("pit_empty", "r019-pit-empty", False),
        ("no_scored_quantile", "r019-no-scored-quantile", True),
    ],
)
def test_successful_early_return_publishes_empty_typed_body_result(
    isolated_test_profile: Path,
    branch: str,
    result_id: str,
    has_universe_identity: bool,
) -> None:
    service, result = _run_empty_branch(isolated_test_profile, branch)

    assert result == []
    body = _body_result(service)
    assert body.result_id == result_id
    assert body.decision.items == ()
    if branch == "empty_frame":
        assert body.decision.assessments == ()
    assert body.context.result_id == result_id
    assert body.context.invocation_id == body.invocation_id
    assert body.context.as_of_date == DECISION_DATE
    assert body.context.eligible_universe_size == 0
    assert body.context.decision_at == ""

    legacy = body.context.legacy_context.thaw()
    assert isinstance(legacy, dict)
    assert legacy["result_id"] == result_id
    assert legacy["as_of_date"] == DECISION_DATE
    assert legacy["data_fingerprint"] == body.context.data_fingerprint
    assert legacy["market_data_fingerprint"] == body.context.market_data_fingerprint
    assert legacy["source_id"] == body.context.source_id
    assert legacy["temporal_mode"] == body.context.temporal_mode
    assert legacy["eligible_universe_size"] == 0
    assert tuple(legacy["warnings"]) == body.context.warnings
    assert "decision_at" not in legacy
    if has_universe_identity:
        assert all(key in legacy for key in UNIVERSE_IDENTITY_KEYS)
        assert legacy["universe_id"].startswith("recommendation-universe-v1:")
        assert legacy["universe_hash"] == legacy["universe_snapshot_hash"]
        assert legacy["universe_identity_schema"] == "recommendation-universe-snapshot.v1"
        assert legacy["universe_policy_schema"] == "recommendation-universe-policy.v1"
        assert legacy["universe_snapshot_schema"] == "recommendation-universe-snapshot.v1"
        assert legacy["universe_policy_id"].startswith(
            "recommendation-universe-policy-v1:"
        )
        assert legacy["universe_snapshot_id"].startswith(
            "recommendation-universe-snapshot-v1:"
        )
        assert legacy["universe_snapshot_selected_codes_hash"] == legacy[
            "universe_snapshot_spec"
        ]["selected_codes_hash"]
        assert legacy["universe_snapshot_spec"]["selected_codes"] == [
            "NO_SIGNAL_A",
            "NO_SIGNAL_B",
        ]
        assert legacy["universe_snapshot_spec"]["selected_count"] == 2
        assert legacy["universe_snapshot_spec"]["decision_date"] == DECISION_DATE
        assert legacy["universe_snapshot_spec"]["selection_mode"] == "top_max_stocks"
        assert legacy["universe_policy_spec"] == {
            "schema": "recommendation-universe-policy.v1",
            "selection_algorithm": "ordered-candidate-frame-v1",
            "selection_mode": "top_max_stocks",
            "industry_filter": "全部",
            "max_stocks": 200,
            "source_provider_id": "_FrameProvider",
        }
        assert legacy["universe_spec"] == {
            "codes": None,
            "max_stocks": 200,
            "selected_codes": ["NO_SIGNAL_A", "NO_SIGNAL_B"],
            "selection_mode": "top_max_stocks",
            "industry_filter": "全部",
            "universe_policy_id": legacy["universe_policy_id"],
            "universe_policy_hash": legacy["universe_policy_hash"],
            "universe_snapshot_id": legacy["universe_snapshot_id"],
            "universe_snapshot_hash": legacy["universe_snapshot_hash"],
        }
    else:
        assert all(key not in legacy for key in UNIVERSE_IDENTITY_KEYS)


def test_pit_unavailable_and_empty_filter_preserve_matrix_and_negative_order(
    isolated_test_profile: Path,
) -> None:
    unavailable, _ = _run_empty_branch(isolated_test_profile, "pit_unavailable")
    assert [
        (
            row["stock_code"],
            row["status"],
            row["reason_codes"],
            row["quality"],
            row["stage"],
        )
        for row in unavailable.last_screening_matrix
    ] == [
        ("OTHER", "missing", ["industry_membership_pit_unavailable"], "missing", "universe_gate"),
        ("PIT", "missing", ["industry_membership_pit_unavailable"], "missing", "universe_gate"),
    ]
    assert [row["stock_code"] for row in unavailable.last_why_not_payload_json] == [
        "OTHER",
        "PIT",
    ]
    assert [row["quality"] for row in unavailable.last_why_not_payload_json] == [
        "missing",
        "missing",
    ]
    assert [row["stock_code"] for row in unavailable.last_excluded_candidates_json] == [
        "OTHER",
        "PIT",
    ]
    assert unavailable.last_exclusion_quality == "degraded"
    assert unavailable.last_exclusion_warnings_json == [
        "screening_matrix_persisted_v1",
        "screening_contains_unknown_evidence",
    ]
    assert _assessment_projection(_body_result(unavailable)) == [
        (
            "OTHER",
            None,
            ("industry_membership_pit_unavailable",),
            ("industry_membership_pit_unavailable",),
            ((
                "legacy:OTHER:0:industry_membership_pit_unavailable",
                "industry_membership_pit_unavailable",
            ),),
        ),
        (
            "PIT",
            None,
            ("industry_membership_pit_unavailable",),
            ("industry_membership_pit_unavailable",),
            ((
                "legacy:PIT:0:industry_membership_pit_unavailable",
                "industry_membership_pit_unavailable",
            ),),
        ),
    ]

    empty_filter, _ = _run_empty_branch(isolated_test_profile, "pit_empty")
    assert [
        (
            row["stock_code"],
            row["status"],
            row["reason_codes"],
            row["quality"],
            row["stage"],
        )
        for row in empty_filter.last_screening_matrix
    ] == [
        ("OTHER", "excluded", ["industry_filter_empty"], "observed", "universe_gate"),
        ("PIT", "excluded", ["industry_filter_empty"], "observed", "universe_gate"),
    ]
    assert empty_filter.last_why_not_payload_json == []
    assert empty_filter.last_excluded_candidates_json == []
    assert empty_filter.last_exclusion_quality == "observed"
    assert empty_filter.last_exclusion_warnings_json == [
        "screening_matrix_persisted_v1"
    ]
    empty_body = _body_result(empty_filter)
    assert _assessment_projection(empty_body) == [
        (
            "OTHER",
            False,
            ("industry_filter_empty",),
            (),
            (("legacy:OTHER:0:industry_filter_empty", "industry_filter_empty"),),
        ),
        (
            "PIT",
            False,
            ("industry_filter_empty",),
            (),
            (("legacy:PIT:0:industry_filter_empty", "industry_filter_empty"),),
        ),
    ]
    pit_context = empty_body.context.legacy_context.thaw()
    assert pit_context["industry_membership_status"] == "accepted"
    assert pit_context["industry_membership_quality"] == "observed"
    assert pit_context["warnings"] == [
        "industry_membership_pit_verified",
        "industry_filter_empty",
    ]


def test_zero_scored_quantile_returns_empty_body_without_minimum_size_error(
    isolated_test_profile: Path,
) -> None:
    service, result = _run_empty_branch(
        isolated_test_profile, "no_scored_quantile"
    )

    assert result == []
    body = _body_result(service)
    assert body.decision.items == ()
    assert [row["stock_code"] for row in service.last_screening_matrix] == [
        "NO_SIGNAL_A",
        "NO_SIGNAL_B",
    ]
    assert [row["reason_codes"] for row in service.last_screening_matrix] == [
        ["strategy_filter_no_signal"],
        ["strategy_filter_no_signal"],
    ]
    assert [row["quality"] for row in service.last_screening_matrix] == [
        "degraded",
        "degraded",
    ]
    assert [row["stock_code"] for row in service.last_why_not_payload_json] == [
        "NO_SIGNAL_A",
        "NO_SIGNAL_B",
    ]
    assert service.last_exclusion_quality == "degraded"
    assert _assessment_projection(body) == [
        (
            "NO_SIGNAL_A",
            False,
            ("strategy_filter_no_signal",),
            (),
            ((
                "legacy:NO_SIGNAL_A:0:strategy_filter_no_signal",
                "strategy_filter_no_signal",
            ),),
        ),
        (
            "NO_SIGNAL_B",
            False,
            ("strategy_filter_no_signal",),
            (),
            ((
                "legacy:NO_SIGNAL_B:0:strategy_filter_no_signal",
                "strategy_filter_no_signal",
            ),),
        ),
    ]


def test_scored_quantile_under_minimum_raises_without_publishing_body_result(
    isolated_test_profile: Path,
) -> None:
    service, _ = _build_service(
        isolated_test_profile, ("A", "B"), {"A": Decimal("80"), "B": Decimal("60")}
    )
    invocation_a, _ = _run_invocation_body(
        service, {}, result_id="r019-before-under-min"
    )
    body_a = _body_result(invocation_a)
    assert body_a.result_id == "r019-before-under-min"

    invocation_b = copy(service)
    with pytest.raises(RecommendationUniverseTooSmallError) as error:
        invocation_b._run_recommendation_body_result(
            config={
                "recommendation_ranking": {
                    "threshold_mode": "quantile",
                    "recommendation_min_percentile_bp": 5000,
                    "recommendation_min_universe_size": 3,
                    "recommendation_ranking_method": "nearest_rank",
                }
            },
            as_of_date=DECISION_DATE,
            result_id="r019-under-min",
            input_session=_begin_input_session(invocation_b),
        )
    assert (error.value.actual_size, error.value.minimum_size) == (2, 3)
    assert not hasattr(invocation_b, "_r019_body_result")
    assert _body_result(invocation_a) is body_a


def test_same_code_new_result_identity_keeps_prior_body_context_deep_frozen(
    isolated_test_profile: Path,
) -> None:
    scores = {"SAME": Decimal("80.00")}
    service, _ = _build_service(
        isolated_test_profile, ("SAME",), scores, periods=21
    )
    invocation_a, first = _run_invocation_body(
        service, {}, result_id="r019-same-code-a"
    )
    body_a = _body_result(invocation_a)
    assert [item.stock_code for item in first] == ["SAME"]
    assert body_a.decision.items[0].rule_score == Decimal("80.00")
    assert body_a.legacy_recommendations[0].field_value("stock_code") == "SAME"
    assert body_a.legacy_recommendations[0].result_id == "r019-same-code-a"
    assert body_a.legacy_recommendations[0].field_value("total_score") == Decimal(
        "80.00"
    )
    fingerprint_a = body_a.context.data_fingerprint

    legacy_context_a = body_a.context.legacy_context.thaw()
    mutable_context_a = invocation_a.last_run_context
    mutable_context_a["warnings"].append("after-capture-mutation")
    mutable_context_a["strategy_config"]["after_capture"] = {"nested": ["changed"]}
    assert body_a.context.legacy_context.thaw() == legacy_context_a

    scores["SAME"] = Decimal("91.00")
    invocation_b, second = _run_invocation_body(
        service,
        {},
        as_of_date="2026-05-21",
        result_id="r019-same-code-b",
    )
    body_b = _body_result(invocation_b)
    assert [item.stock_code for item in second] == ["SAME"]
    assert body_b.result_id == "r019-same-code-b"
    assert body_b.context.as_of_date == "2026-05-21"
    assert body_b.context.data_fingerprint != fingerprint_a
    assert body_b.decision.items[0].rule_score == Decimal("91.00")
    assert body_b.invocation_id != body_a.invocation_id
    assert body_b.legacy_recommendations[0].result_id == "r019-same-code-b"
    assert body_b.legacy_recommendations[0].invocation_id == body_b.invocation_id
    assert body_b.legacy_recommendations[0].field_value("total_score") == Decimal(
        "91.00"
    )
    assert body_a.result_id == "r019-same-code-a"
    assert body_a.context.as_of_date == DECISION_DATE
    assert body_a.context.data_fingerprint == fingerprint_a
    assert body_a.decision.items[0].stock_code == "SAME"
    assert body_a.decision.items[0].rule_score == Decimal("80.00")
    assert body_a.legacy_recommendations[0].field_value("total_score") == Decimal(
        "80.00"
    )
    assert body_a.context.legacy_context.thaw() == legacy_context_a
