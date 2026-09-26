from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import inspect
import json
import operator
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional, cast
from uuid import uuid4

import pandas as pd

from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    ReferenceKind,
    Request,
    VersionReference,
)
from app_module.recommendation_portfolio_dtos import RecommendationSnapshotDTO
from app_module.recommendation_portfolio_dates import parse_stock_dates
from app_module.recommendation_dataframe_provider import (
    RecommendationDataFrameProvider,
    ReplayProviderCallResultV1,
    _ReplayScoredCandidateV1,
    _replay_score_order_token,
)
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem
from decision_module.recommendation.evaluate import (
    ReplayCandidateScoringOutcomeV1,
    ReplayScorerDispositionV1,
)


RecommendationProvider = Callable[[pd.DataFrame, Dict[str, Any], int], List[Dict[str, Any]]]


def _v1_projection_matches_candidates(
    projected_rows: object,
    candidates: tuple[_ReplayScoredCandidateV1, ...],
) -> bool:
    """確認外層列仍是這批 typed candidates 的逐列投影。"""

    if type(projected_rows) is not list or type(candidates) is not tuple:
        return False
    if len(projected_rows) != len(candidates):
        return False

    def same_value(expected: object, actual: object) -> bool:
        if type(expected) is not type(actual):
            return False
        if type(expected) is dict:
            expected_dict = cast(dict[object, object], expected)
            actual_dict = cast(dict[object, object], actual)
            if expected_dict.keys() != actual_dict.keys():
                return False
            return all(
                same_value(value, actual_dict[key])
                for key, value in expected_dict.items()
            )
        if type(expected) is float:
            # 位元比較也能處理 NaN；此處只驗相容投影，不做金融運算。
            return struct.pack(">d", expected) == struct.pack(">d", cast(float, actual))
        if type(expected) in {str, int, bool, type(None)}:
            return expected == actual
        # 不呼叫不透明相容 payload 的自訂 __eq__；僅接受原物件投影。
        return expected is actual

    for row, candidate in zip(projected_rows, candidates, strict=True):
        if type(candidate) is not _ReplayScoredCandidateV1:
            return False
        if not same_value(candidate.to_v1_row(), row):
            return False
    return True


def _has_json_object_keys(value: object, active: set[int] | None = None) -> bool:
    if not isinstance(value, (Mapping, list, tuple)):
        return True
    active_values = set() if active is None else active
    value_id = id(value)
    if value_id in active_values:
        return False
    active_values.add(value_id)
    try:
        if isinstance(value, Mapping):
            return all(
                type(key) is str and _has_json_object_keys(item, active_values)
                for key, item in value.items()
            )
        return all(_has_json_object_keys(item, active_values) for item in value)
    finally:
        active_values.remove(value_id)


def _config_snapshot(
    config: object,
) -> tuple[RecommendationConfigSnapshot | None, VersionReference | None]:
    if not isinstance(config, Mapping) or not _has_json_object_keys(config):
        return None, None
    try:
        raw_config_json = json.dumps(
            config,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        raw_config_hash = "sha256:" + hashlib.sha256(
            raw_config_json.encode("utf-8", errors="strict")
        ).hexdigest()
        snapshot = RecommendationConfigSnapshot(
            raw_config_json=raw_config_json,
            raw_json_sha256=raw_config_hash,
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeEncodeError,
        RecursionError,
    ):
        return None, None
    return snapshot, VersionReference(
        kind=ReferenceKind.CONFIG,
        reference_id=raw_config_hash,
        version=snapshot.schema_version,
    )


def _optional_decimal(value: object) -> tuple[Decimal | None, bool]:
    if value is None:
        return None, False
    if type(value) not in (int, float, Decimal):
        return None, True
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, True
    if not decimal_value.is_finite():
        return None, True
    return decimal_value, False


def _profile_reference(profile_id: object) -> VersionReference | None:
    if type(profile_id) is not str or not profile_id.strip():
        return None
    return VersionReference(
        kind=ReferenceKind.PROFILE,
        reference_id=profile_id,
    )


def _positive_optional_int(value: object) -> int | None:
    if type(value) is not int or value <= 0:
        return None
    return value


def _effective_max_stocks(config: Mapping[str, Any]) -> int | None:
    if "_portfolio_max_stocks" not in config:
        return None
    raw_value = config["_portfolio_max_stocks"]
    if type(raw_value) is bool:
        return None
    if type(raw_value) not in (int, float, str):
        return None
    if type(raw_value) is float and not raw_value.is_integer():
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value > 0 else None


def _supports_explicit_as_of_call(provider: object) -> bool:
    """避免三參數 provider 子類誤用繼承的四參數 as-of wrapper。"""

    run_with_as_of = getattr(provider, "run_with_as_of", None)
    if not callable(run_with_as_of):
        return False
    if not isinstance(provider, RecommendationDataFrameProvider):
        return True
    if type(provider).run_with_as_of is not RecommendationDataFrameProvider.run_with_as_of:
        return True
    try:
        parameters = inspect.signature(type(provider).__call__).parameters
    except (TypeError, ValueError):
        return False
    return "_call_context" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _canonical_replay_execution_from_decision(
    snapshot: RecommendationSnapshotDTO,
    *,
    top_n: object,
    parent_result_id: str,
    decision: DecisionBatch,
) -> RecommendationExecution:
    config_snapshot, config_ref = _config_snapshot(snapshot.strategy_config)
    profile_ref = _profile_reference(snapshot.profile_id)
    request = Request(
        as_of_date=date.fromisoformat(snapshot.as_of_date),
        config_ref=config_ref,
        profile_ref=profile_ref,
        config_snapshot=config_snapshot,
        max_stocks=_effective_max_stocks(snapshot.strategy_config),
        top_n=_positive_optional_int(top_n),
    )

    execution_context = Context(
        as_of_date=date.fromisoformat(snapshot.as_of_date),
        config_ref=config_ref,
        profile_ref=profile_ref,
    )
    child_result_id = f"replay-{uuid4().hex}"
    while child_result_id == parent_result_id:
        child_result_id = f"replay-{uuid4().hex}"
    return RecommendationExecution(
        result_id=child_result_id,
        request=request,
        context=execution_context,
        status=ExecutionStatus.COMPLETED,
        decision=decision,
        related_references=(
            VersionReference(
                kind=ReferenceKind.REPLAY_PARENT,
                reference_id=parent_result_id,
            ),
        ),
    )


def _build_canonical_replay_execution_from_handoff(
    snapshot: RecommendationSnapshotDTO,
    candidates: tuple[_ReplayScoredCandidateV1, ...],
    *,
    top_n: object,
    parent_result_id: str,
) -> RecommendationExecution | None:
    """直接採同次 typed candidate/outcome；不從外層 v1 row 重建決策。"""

    if type(candidates) is not tuple:
        return None
    expected_date = date.fromisoformat(snapshot.as_of_date)
    items: list[RecommendationItem] = []
    assessments = []
    seen_codes: set[str] = set()
    for ordinal, candidate in enumerate(candidates):
        if (
            type(candidate) is not _ReplayScoredCandidateV1
            or candidate.selected_ordinal != ordinal
        ):
            return None
        outcome = candidate.scoring_outcome
        if type(outcome) is not ReplayCandidateScoringOutcomeV1:
            return None
        if outcome.disposition is not ReplayScorerDispositionV1.SCORED:
            return None
        item = outcome.item
        if item is None or outcome.score_ordering is None:
            return None
        stock_code = candidate.stock_code
        if (
            type(stock_code) is not str
            or not stock_code.strip()
            or stock_code in seen_codes
            or stock_code != outcome.request.stock_code
            or stock_code != item.stock_code
            or outcome.request.as_of_date != expected_date
        ):
            return None
        seen_codes.add(stock_code)
        if candidate.stock_name != item.stock_name:
            return None
        raw_score = candidate.total_score
        if type(raw_score) is not float:
            return None
        rule_score, invalid_rule_score = _optional_decimal(raw_score)
        if (
            invalid_rule_score
            or rule_score != item.rule_score
            or outcome.score_ordering != _replay_score_order_token(raw_score)
        ):
            return None
        for observed_score, expected_score in (
            (candidate.technical_score, item.indicator_score),
            (candidate.pattern_score, item.pattern_score),
            (candidate.volume_score, item.volume_score),
        ):
            if type(observed_score) is not float:
                return None
            observed_decimal, invalid = _optional_decimal(observed_score)
            if invalid or observed_decimal != expected_score:
                return None
        reason_text = candidate.selection_reason
        if (reason_text is not None and type(reason_text) is not str) or reason_text != item.reason_text:
            return None
        items.append(item)
        assessments.append(outcome.assessment)
    return _canonical_replay_execution_from_decision(
        snapshot,
        top_n=top_n,
        parent_result_id=parent_result_id,
        decision=DecisionBatch(
            items=tuple(items),
            assessments=tuple(assessments),
            regime=snapshot.regime,
        ),
    )


class RecommendationReplayService:
    def __init__(self, provider: RecommendationProvider):
        self.provider = provider

    def run_snapshot(
        self,
        as_of_date: str,
        profile_id: str,
        config: Dict[str, Any],
        history: pd.DataFrame,
        universe: Optional[Iterable[str]],
        top_n: int,
        parent_result_id: str | None = None,
    ) -> RecommendationSnapshotDTO:
        parent_ref = VersionReference(
            kind=ReferenceKind.REPLAY_PARENT,
            reference_id=(
                f"replay-parent-{uuid4().hex}"
                if parent_result_id is None
                else parent_result_id
            ),
        )
        if "日期" not in history.columns:
            raise ValueError("history 必須包含 日期 欄位")

        as_of_ts = pd.to_datetime(as_of_date)
        data = history.copy()
        data["日期"] = parse_stock_dates(data["日期"])
        data = data[data["日期"].notna()]
        data = data[data["日期"] <= as_of_ts]

        diagnostics = []
        if "available_date" in data:
            available = parse_stock_dates(data["available_date"])
            rejected = available.isna() | (available > as_of_ts)
            if rejected.any():
                diagnostics.append(f"unavailable_rows_excluded:{int(rejected.sum())}")
            data = data[~rejected]
        if universe is not None:
            universe_set = {str(code) for code in universe}
            stock_col = "證券代號" if "證券代號" in data.columns else "股票代號"
            if stock_col in data.columns:
                data = data[data[stock_col].astype(str).isin(universe_set)]
            else:
                diagnostics.append("missing_stock_code_column")

        frozen_config = deepcopy(config)
        provider_config = deepcopy(frozen_config)
        handoff: ReplayProviderCallResultV1 | None = None
        if type(self.provider) is RecommendationDataFrameProvider:
            concrete_provider = cast(RecommendationDataFrameProvider, self.provider)
            handoff = concrete_provider.run_with_as_of_handoff(
                data,
                provider_config,
                top_n,
                as_of_ts.date(),
            )
            provider_rows = handoff.project_v1_rows()
        else:
            run_with_as_of = getattr(self.provider, "run_with_as_of", None)
            if _supports_explicit_as_of_call(self.provider) and callable(run_with_as_of):
                provider_rows = run_with_as_of(
                    data,
                    provider_config,
                    top_n,
                    as_of_ts.date(),
                )
            else:
                provider_rows = self.provider(data, provider_config, top_n)
        recommendations = deepcopy(provider_rows[:top_n])

        snapshot = RecommendationSnapshotDTO(
            as_of_date=as_of_ts.strftime("%Y-%m-%d"),
            profile_id=profile_id,
            strategy_config=frozen_config,
            regime=str(config.get("regime") or ""),
            recommendations=recommendations,
            diagnostics=diagnostics,
        )
        snapshot.attach_replay_parent_id(parent_ref.reference_id)
        if handoff is not None and (
            handoff.as_of_date == as_of_ts.date()
            and handoff.requested_top_n == operator.index(top_n)
        ):
            child_candidates = handoff.candidates[:top_n]
            canonical_execution = _build_canonical_replay_execution_from_handoff(
                snapshot,
                child_candidates,
                top_n=top_n,
                parent_result_id=parent_ref.reference_id,
            )
            if canonical_execution is not None and not _v1_projection_matches_candidates(
                snapshot.recommendations,
                child_candidates,
            ):
                canonical_execution = None
        else:
            canonical_execution = None
        if canonical_execution is not None:
            snapshot.attach_canonical_execution(canonical_execution)
        return snapshot
