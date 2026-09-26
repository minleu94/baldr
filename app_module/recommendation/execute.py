"""推薦 execute 用例與舊 DTO façade 的單次 invocation 接線。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from types import TracebackType
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np

from app_module.dtos import RecommendationDTO
from app_module.recommendation.body_result import (
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
)
from app_module.recommendation.legacy_compatibility import (
    LEGACY_COMPATIBILITY_FIELDS,
    LegacyCompatibilitySnapshot,
)
from app_module.recommendation.contracts import (
    Context,
    ExecutionEvent,
    ExecutionStatus,
    MLAvailability,
    MLAvailabilityStatus,
    QualityReport,
    QualityStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    ReferenceKind,
    Request,
    SnapshotCohort,
    StrategyConfigIdentity,
    UniversePolicyIdentity,
    UniverseSnapshotIdentity,
    RecommendationUniverseIdentity,
    VersionReference,
)
from app_module.recommendation.ml_postcalibration_handoff import (
    RecommendationPostCalibrationHandoffSinkV1,
    RecommendationPostCalibrationHandoffV1,
    ml_availability_from_handoff_v1,
    verified_receipt_references_v1,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
    UniverseReference,
)
from app_module.v4_evidence_identity import DEFAULT_RETURN_BASIS


_LEGACY_STATE_FIELDS = LEGACY_COMPATIBILITY_FIELDS

_SCHEDULED_DECISION_TIMEZONE = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True, slots=True)
class RecommendationInvocationContext:
    """由 invocation-local capture 投影的 postprocess context。"""

    as_of_date: date | None
    created_at: datetime | None
    service_run_started_at: datetime | None
    available_at: datetime | None
    decision_at: datetime | None
    strategy_identity: StrategyConfigIdentity | None
    universe_identity: RecommendationUniverseIdentity | None
    raw_context: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RecommendationPostprocessInput:
    """同步 postprocess callback 可見的單次呼叫材料。"""

    result_id: str
    request: Request
    runtime_config: Mapping[str, Any]
    recommendations: tuple[RecommendationDTO, ...]
    screening_matrix: tuple[Mapping[str, Any], ...]
    context: RecommendationInvocationContext
    body_result: RecommendationBodyResult

    def __post_init__(self) -> None:
        if type(self.body_result) is not RecommendationBodyResult:
            raise TypeError("body_result 必須是 RecommendationBodyResult")
        if self.result_id != self.body_result.result_id:
            raise ValueError("postprocess input result_id 與 BodyResult 不一致")
        if type(self.context) is not RecommendationInvocationContext:
            raise TypeError("context 必須是 RecommendationInvocationContext")
        expected_context = self.body_result.context
        if self.context.as_of_date != _date_value(expected_context.as_of_date):
            raise ValueError("postprocess input as_of_date 與 BodyResult 不一致")
        if self.context.strategy_identity != expected_context.strategy_identity:
            raise ValueError("postprocess input strategy identity 與 BodyResult 不一致")
        if self.context.universe_identity != expected_context.universe_identity:
            raise ValueError("postprocess input universe identity 與 BodyResult 不一致")
        expected_raw_context = expected_context.legacy_context.thaw()
        if dict(self.context.raw_context) != expected_raw_context:
            raise ValueError("postprocess input legacy context 與 BodyResult 不一致")
        expected_recommendations = tuple(
            LegacyRecommendationSnapshot.capture(
                recommendation,
                invocation_id=self.body_result.invocation_id,
                result_id=self.body_result.result_id,
            )
            for recommendation in self.recommendations
        )
        if expected_recommendations != self.body_result.legacy_recommendations:
            raise ValueError("postprocess input recommendation sidecar 與 BodyResult 不一致")


@dataclass(frozen=True, slots=True)
class RecommendationPostprocessFacts:
    """callback 為同次 invocation 補齊的具名 post-run facts。"""

    result_id: str
    invocation_id: str
    created_at: datetime | None
    snapshot_cohort: SnapshotCohort
    evidence_identity: RecommendationRunEvidenceIdentity
    result_config_snapshot: RecommendationResultConfigSnapshot

    def __post_init__(self) -> None:
        for name in ("result_id", "invocation_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")
        if self.created_at is not None:
            if type(self.created_at) is not datetime:
                raise TypeError("created_at 必須是 aware datetime 或 None")
            if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
                raise ValueError("created_at 必須是 aware datetime 或 None")
        if type(self.snapshot_cohort) is not SnapshotCohort:
            raise TypeError("snapshot_cohort 必須是 SnapshotCohort")
        if type(self.evidence_identity) is not RecommendationRunEvidenceIdentity:
            raise TypeError(
                "evidence_identity 必須是 RecommendationRunEvidenceIdentity"
            )
        if type(self.result_config_snapshot) is not RecommendationResultConfigSnapshot:
            raise TypeError(
                "result_config_snapshot 必須是 RecommendationResultConfigSnapshot"
            )


def execute_recommendation(
    service: Any,
    runtime_config: Mapping[str, Any],
    max_stocks: int = 200,
    top_n: int = 50,
    *,
    as_of_date: str | date | None = None,
    universe: list[str] | None = None,
    result_id: str | None = None,
    historical_research: bool = False,
    select_latest_available_cutoff: bool = False,
    request_config_snapshot: RecommendationConfigSnapshot | None = None,
    postprocess_callback: Callable[
        [RecommendationPostprocessInput], RecommendationPostprocessFacts
    ] | None = None,
    created_at: datetime | None = None,
    cancel: Callable[[], bool] | None = None,
    progress: Callable[[str, int], None] | None = None,
    capture_sink: MutableMapping[str, Any] | None = None,
) -> RecommendationExecution:
    """以隔離的 service view 執行一次原計算 body，並立即封存結果。

    `runtime_config` 是傳給原 recommendation body 的執行設定；原 caller
    JSON 另由 `request_config_snapshot` 保存，不從 runtime config 反推。
    `postprocess_callback` 只在本函式同步執行，且只能收到本次 private capture。
    `capture_sink` 只供同一呼叫堆疊中的舊 DTO façade 投影使用；相容狀態
    只以 `compatibility_snapshot` 提供，不重複寫入通用 dict。它不會寫入
    service，也不會被保存到 execution 之外的共用狀態。
    """

    if request_config_snapshot is not None and type(
        request_config_snapshot
    ) is not RecommendationConfigSnapshot:
        raise TypeError("request_config_snapshot 必須是 RecommendationConfigSnapshot")
    if postprocess_callback is not None and request_config_snapshot is None:
        raise ValueError(
            "postprocess_callback 必須搭配原 caller RecommendationConfigSnapshot"
        )
    if (
        postprocess_callback is None
        and _contains_scheduled_marker(runtime_config, request_config_snapshot)
    ):
        raise ValueError(
            "scheduled recommendation 必須在 execute 返回前完成 postprocess capture"
        )
    if created_at is not None and (
        type(created_at) is not datetime
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at 必須是 aware datetime 或 None")

    capture: dict[str, Any] = {
        "body_entered": False,
        "legacy_recommendations": [],
        "compatibility_snapshot": None,
        "receipt": {},
        "error": None,
        "traceback": None,
        "calibration_consumer_configured": getattr(
            service, "calibration_consumer", None
        ) is not None,
    }
    if capture_sink is not None:
        capture_sink.clear()
        capture_sink.update(capture)

    resolved_id = _requested_result_id(runtime_config, result_id)
    capture["caller_created_at"] = created_at
    _notify_progress(progress, "recommendation_started", 10, capture)
    if cancel is not None and cancel():
        execution = _cancelled_before_start(
            config=runtime_config,
            as_of_date=as_of_date,
            result_id=resolved_id,
            request_config_snapshot=request_config_snapshot,
            max_stocks=max_stocks,
            top_n=top_n,
        )
        if capture_sink is not None:
            capture_sink.update(capture)
        _notify_progress(progress, "recommendation_cancelled", 100, capture)
        return execution

    invocation = copy(service)
    invocation._r011_invocation_capture = capture
    post_calibration_sink = RecommendationPostCalibrationHandoffSinkV1(
        consumer_configured=(
            getattr(service, "calibration_consumer", None) is not None
        )
    )
    invocation._r026_post_calibration_handoff_sink = post_calibration_sink
    invocation.last_run_context = object()
    input_preparer = getattr(service, "recommendation_input_preparer", None)
    begin_input_session = getattr(input_preparer, "begin", None)
    market_data_provider = getattr(service, "market_data_provider", None)
    input_session = (
        begin_input_session(
            getattr(service, "config", None),
            market_data_provider=market_data_provider,
        )
        if callable(begin_input_session)
        else None
    )
    original_reset = invocation._reset_negative_evidence_buffers

    def tracked_reset() -> None:
        capture["body_entered"] = True
        _notify_progress(progress, "recommendation_body_started", 35, capture)
        original_reset()

    invocation._reset_negative_evidence_buffers = tracked_reset
    # 基本面 provider 是跨 run 的 lazy cache。委派到原 service 並沿用其鎖，
    # 避免 shallow view 把初始化改成 invocation-local。
    invocation._get_fundamental_sqlite_provider = service._get_fundamental_sqlite_provider

    caught: BaseException | None = None
    traceback: TracebackType | None = None
    recommendations: list[RecommendationDTO] = []
    body_result: RecommendationBodyResult | None = None
    compatibility_snapshot: LegacyCompatibilitySnapshot | None = None
    try:
        captured_body_result = invocation._run_recommendation_body_result(
            config=dict(runtime_config),
            max_stocks=max_stocks,
            top_n=top_n,
            as_of_date=as_of_date,
            universe=universe,
            result_id=resolved_id,
            historical_research=historical_research,
            select_latest_available_cutoff=select_latest_available_cutoff,
            input_session=input_session,
        )
        if type(captured_body_result) is not RecommendationBodyResult:
            raise TypeError(
                "successful recommendation body 必須直接回傳 RecommendationBodyResult"
            )
        if captured_body_result.result_id != resolved_id:
            raise ValueError("RecommendationBodyResult result_id 與 execute request 不一致")
        if captured_body_result.context.legacy_context.thaw() != invocation.last_run_context:
            raise ValueError(
                "RecommendationBodyResult context 與同次 invocation context 不一致"
            )
        recommendations = [
            snapshot.materialize()
            for snapshot in captured_body_result.legacy_recommendations
        ]
        expected_sidecars = tuple(
            LegacyRecommendationSnapshot.capture(
                recommendation,
                invocation_id=captured_body_result.invocation_id,
                result_id=captured_body_result.result_id,
            )
            for recommendation in recommendations
        )
        if expected_sidecars != captured_body_result.legacy_recommendations:
            raise ValueError(
                "RecommendationBodyResult DTO sidecar 與 body return rows 不一致"
            )
        body_result = captured_body_result
        capture["legacy_recommendations"] = deepcopy(recommendations)
    except BaseException as exc:  # 保留 façade 必須重拋的原始例外物件。
        body_result = None
        caught = exc
        traceback = exc.__traceback__
        capture["error"] = exc
        capture["traceback"] = traceback
    finally:
        if capture["body_entered"]:
            compatibility_snapshot = LegacyCompatibilitySnapshot.capture_from_invocation(
                invocation,
                capture_id=uuid4().hex,
                result_id=resolved_id,
                body_invocation_id=(
                    body_result.invocation_id if body_result is not None else None
                ),
                allow_partial_state=True,
            )
            capture["compatibility_snapshot"] = compatibility_snapshot
            capture["personalization_clocks"] = deepcopy(
                invocation._personalization_execution_clocks
            )
            _notify_progress(progress, "recommendation_body_finished", 90, capture)

    if caught is not None and postprocess_callback is not None:
        # 新 direct execution seam 表示 caller 要求返回完整 capture；不得將
        # callback 尚未有機會建立的 partial FAILED execution 公布給 scheduled consumer。
        raise caught.with_traceback(traceback)

    # A partial legacy context is a compatibility sidecar only.  If the body
    # failed before publishing its typed result, keep the request identity.
    result_id_from_context = body_result.result_id if body_result is not None else resolved_id
    if not result_id_from_context:
        result_id_from_context = f"rec_{uuid4().hex}"
    cancelled_after_body = cancel is not None and cancel()
    if cancelled_after_body:
        capture["cancelled_after_body"] = True
    elif body_result is not None:
        if compatibility_snapshot is None:
            raise ValueError("completed typed body 缺少 compatibility snapshot")
        compatibility_snapshot.validate_complete_state()

    request = _build_request(
        runtime_config=runtime_config,
        as_of_date=as_of_date,
        legacy_context={},
        body_context=body_result.context if body_result is not None else None,
        request_config_snapshot=request_config_snapshot,
        max_stocks=max_stocks,
        top_n=top_n,
    )
    invocation_context = (
        _invocation_context(capture, body_result=body_result)
        if postprocess_callback is not None and caught is None
        else None
    )
    postprocess_facts: RecommendationPostprocessFacts | None = None
    if (
        postprocess_callback is not None
        and caught is None
        and not cancelled_after_body
    ):
        if result_id_from_context != resolved_id:
            raise ValueError(
                "invocation result_id 與 execute request identity 不一致"
            )
        if invocation_context is None:
            raise ValueError("postprocess capture 缺少 invocation context")
        if type(body_result) is not RecommendationBodyResult:
            raise ValueError("postprocess capture 缺少 successful typed BodyResult")
        if type(compatibility_snapshot) is not LegacyCompatibilitySnapshot:
            raise ValueError("postprocess capture 缺少同次 legacy compatibility snapshot")
        if (
            invocation_context.available_at is None
            or invocation_context.decision_at is None
        ):
            raise ValueError(
                "postprocess capture 缺少同次 available_at 或 decision_at"
            )
        postprocess_input = RecommendationPostprocessInput(
            result_id=result_id_from_context,
            request=request,
            runtime_config=deepcopy(dict(runtime_config)),
            recommendations=tuple(
                deepcopy(cast_recommendations(capture["legacy_recommendations"]))
            ),
            screening_matrix=tuple(
                compatibility_snapshot.materialize()["last_screening_matrix"]
            ),
            context=invocation_context,
            body_result=body_result,
        )
        postprocess_facts = postprocess_callback(postprocess_input)
        if type(postprocess_facts) is not RecommendationPostprocessFacts:
            raise TypeError(
                "postprocess_callback 必須回傳 RecommendationPostprocessFacts"
            )
        scheduled_input = _contains_scheduled_marker(
            runtime_config, request_config_snapshot
        )
        scheduled_output = _is_scheduled_result_config(postprocess_facts)
        if scheduled_input and not scheduled_output:
            raise ValueError(
                "scheduled caller config 必須產生 scheduled result config"
            )
        if scheduled_output and invocation_context.created_at is None:
            raise ValueError(
                "scheduled result config 必須有明示原 caller created_at"
            )
        if postprocess_facts.created_at != invocation_context.created_at:
            raise ValueError(
                "postprocess created_at 必須沿用同次 invocation created_at"
            )
        _validate_postprocess_facts(
            facts=postprocess_facts,
            body_result=body_result,
            scheduled=scheduled_input or scheduled_output,
        )

    if caught is not None:
        execution = _build_execution(
            result_id=result_id_from_context,
            config=runtime_config,
            as_of_date=as_of_date,
            capture=capture,
            compatibility_snapshot=compatibility_snapshot,
            post_calibration_handoff=post_calibration_sink.snapshot(),
            status=ExecutionStatus.FAILED,
            failure_reason=f"{type(caught).__name__}: {caught}",
            request=request,
        )
    elif cancelled_after_body:
        execution = _build_execution(
            result_id=result_id_from_context,
            config=runtime_config,
            as_of_date=as_of_date,
            capture=capture,
            compatibility_snapshot=compatibility_snapshot,
            post_calibration_handoff=post_calibration_sink.snapshot(),
            status=ExecutionStatus.CANCELLED,
            failure_reason="cancelled_after_recommendation_body",
            request=request,
            body_result=body_result,
        )
    else:
        execution = _build_execution(
            result_id=result_id_from_context,
            config=runtime_config,
            as_of_date=as_of_date,
            capture=capture,
            compatibility_snapshot=compatibility_snapshot,
            post_calibration_handoff=post_calibration_sink.snapshot(),
            status=ExecutionStatus.COMPLETED,
            recommendations=capture["legacy_recommendations"],
            request=request,
            invocation_context=invocation_context,
            postprocess_facts=postprocess_facts,
            body_result=body_result,
        )

    if capture_sink is not None:
        capture_sink.clear()
        capture_sink.update(capture)
        capture_sink["execution"] = execution
    _notify_progress(progress, "recommendation_execution_finished", 100, capture)
    return execution


def _contains_scheduled_marker(
    runtime_config: Mapping[str, Any],
    request_config_snapshot: RecommendationConfigSnapshot | None,
) -> bool:
    if runtime_config.get("scheduled_snapshot") is True:
        return True
    if request_config_snapshot is None:
        return False
    try:
        raw_config = json.loads(request_config_snapshot.raw_config_json)
    except (TypeError, ValueError):
        return False
    return isinstance(raw_config, Mapping) and raw_config.get("scheduled_snapshot") is True


def _scheduled_decision_date(created_at: datetime | None) -> str:
    """Return the scheduler-local date captured when this invocation started."""

    if (
        type(created_at) is not datetime
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("scheduled facts.created_at 必須是具時區的時間")
    return created_at.astimezone(_SCHEDULED_DECISION_TIMEZONE).date().isoformat()


def _validate_postprocess_facts(
    *,
    facts: RecommendationPostprocessFacts,
    body_result: RecommendationBodyResult,
    scheduled: bool,
) -> None:
    """Fail closed if callback facts are cross-invocation or raw-sidecar based."""

    if facts.result_id != body_result.result_id:
        raise ValueError("postprocess facts result_id 與 BodyResult 不一致")
    if facts.invocation_id != body_result.invocation_id:
        raise ValueError("postprocess facts invocation_id 與 BodyResult 不一致")

    expected_cohort = snapshot_cohort_from_body_result(body_result)
    if facts.snapshot_cohort != expected_cohort:
        raise ValueError("postprocess cohort 必須由同次 typed BodyResult 投影")
    expected_cohort_payload = snapshot_cohort_payload_from_body_result(body_result)

    body_evidence = body_result.context.evidence_identity
    if body_evidence is None:
        raise ValueError("BodyResult 缺少 typed evidence identity")
    expected_evidence = body_evidence
    if scheduled:
        expected_evidence = RecommendationRunEvidenceIdentity(
            cost_model_id=body_evidence.cost_model_id,
            benchmark_id=body_evidence.benchmark_id,
            industry_benchmark_id=body_evidence.industry_benchmark_id,
            horizon_days=body_evidence.horizon_days,
            evidence_tier="forward",
            return_basis=body_evidence.return_basis or DEFAULT_RETURN_BASIS,
        )
    if facts.evidence_identity != expected_evidence:
        raise ValueError("postprocess evidence identity 與 typed BodyResult 不一致")

    try:
        raw_result_config = json.loads(
            facts.result_config_snapshot.raw_result_config_json
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("postprocess result config snapshot 不是有效 JSON") from exc
    if not isinstance(raw_result_config, Mapping):
        raise ValueError("postprocess result config snapshot 必須是 JSON object")

    if raw_result_config.get("snapshot_cohort") is None or _canonical_json_value(
        raw_result_config.get("snapshot_cohort")
    ) != _canonical_json_value(expected_cohort_payload):
        raise ValueError("result config snapshot cohort 與 typed BodyResult 不一致")

    context = body_result.context
    if scheduled:
        scheduled_context_values = (
            ("data_as_of_date", context.as_of_date),
            ("temporal_mode", context.temporal_mode),
            ("cutoff_selection", context.cutoff_selection),
            ("cutoff_policy", context.cutoff_policy),
        )
        for key, expected in scheduled_context_values:
            if key not in raw_result_config:
                raise ValueError(
                    f"scheduled result config 缺少同次 typed {key}"
                )
            if raw_result_config[key] != expected:
                raise ValueError(
                    f"scheduled result config {key} 與 typed BodyResult 不一致"
                )
        expected_decision_date = _scheduled_decision_date(facts.created_at)
        if raw_result_config.get("decision_date") != expected_decision_date:
            raise ValueError(
                "scheduled result config decision_date 必須符合同次 invocation created_at 排程日期"
            )

    for key, expected_value in (
        ("result_id", body_result.result_id),
        ("as_of_date", context.as_of_date),
        ("temporal_mode", context.temporal_mode),
        ("cutoff_selection", context.cutoff_selection),
        ("cutoff_policy", context.cutoff_policy),
        ("cost_model_id", expected_evidence.cost_model_id),
        ("benchmark_id", expected_evidence.benchmark_id),
        ("industry_benchmark_id", expected_evidence.industry_benchmark_id),
        ("horizon_days", expected_evidence.horizon_days),
        ("evidence_tier", expected_evidence.evidence_tier),
        ("return_basis", expected_evidence.return_basis),
    ):
        if key in raw_result_config and raw_result_config[key] != expected_value:
            raise ValueError(f"result config snapshot {key} 與 typed facts 不一致")


def _canonical_json_value(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _build_request(
    *,
    runtime_config: Mapping[str, Any],
    as_of_date: str | date | None,
    legacy_context: Mapping[str, Any],
    body_context: RecommendationBodyContextFacts | None = None,
    request_config_snapshot: RecommendationConfigSnapshot | None,
    max_stocks: int,
    top_n: int,
) -> Request:
    strategy_identity = body_context.strategy_identity if body_context else None
    universe_identity = body_context.universe_identity if body_context else None
    if body_context is not None:
        strategy_config_id = (
            strategy_identity.strategy_config_id
            if strategy_identity is not None
            else None
        )
        strategy_config_version = (
            strategy_identity.strategy_config_schema
            if strategy_identity is not None
            else None
        )
        universe_policy_id = (
            universe_identity.policy.universe_policy_id
            if universe_identity is not None and universe_identity.policy is not None
            else None
        )
    else:
        strategy_config_id = legacy_context.get("strategy_config_id")
        strategy_config_version = legacy_context.get("strategy_config_schema")
        universe_policy_id = legacy_context.get("universe_policy_id")
    config_ref = _version_reference(
        ReferenceKind.CONFIG,
        strategy_config_id or runtime_config.get("config_id"),
        strategy_config_version or runtime_config.get("config_version"),
    )
    return Request(
        as_of_date=_date_value(
            as_of_date
            if as_of_date is not None
            else runtime_config.get("as_of_date")
        ),
        config_ref=config_ref,
        profile_ref=_version_reference(
            ReferenceKind.PROFILE,
            runtime_config.get("profile_id"),
            runtime_config.get("profile_version"),
        ),
        strategy_ref=_version_reference(
            ReferenceKind.STRATEGY,
            runtime_config.get("strategy_version_id")
            or runtime_config.get("strategy_version"),
            runtime_config.get("strategy_version"),
        ),
        policy_ref=_version_reference(
            ReferenceKind.POLICY, runtime_config.get("recommendation_policy_id")
        ),
        universe_policy_ref=_version_reference(
            ReferenceKind.UNIVERSE_POLICY,
            universe_policy_id,
        ),
        config_snapshot=request_config_snapshot,
        max_stocks=max_stocks if request_config_snapshot is not None else None,
        top_n=top_n if request_config_snapshot is not None else None,
    )


def _invocation_context(
    capture: Mapping[str, Any],
    *,
    body_result: RecommendationBodyResult | None,
) -> RecommendationInvocationContext:
    if type(body_result) is not RecommendationBodyResult:
        raise TypeError("postprocess capture 必須有 typed RecommendationBodyResult")
    body_context = body_result.context
    raw_context = body_context.legacy_context.thaw()
    if not isinstance(raw_context, Mapping):
        raise TypeError("RecommendationBodyResult legacy context sidecar 必須是 mapping")
    clocks = capture.get("personalization_clocks", {})
    if not isinstance(clocks, Mapping):
        raise TypeError("invocation capture clocks 必須是 mapping")
    created_at = _datetime_value(capture.get("caller_created_at"))
    available_at = _datetime_value(clocks.get("available_at"))
    decision_at = _datetime_value(body_context.decision_at)
    return RecommendationInvocationContext(
        as_of_date=_date_value(body_context.as_of_date),
        created_at=created_at,
        service_run_started_at=_datetime_value(clocks.get("run_started_at")),
        available_at=available_at,
        decision_at=decision_at,
        strategy_identity=body_context.strategy_identity,
        universe_identity=body_context.universe_identity,
        raw_context=deepcopy(dict(raw_context)),
    )


def _strategy_identity(
    context: Mapping[str, Any],
) -> StrategyConfigIdentity | None:
    values = (
        context.get("strategy_version_id"),
        context.get("strategy_config_id"),
        context.get("strategy_config_hash"),
        context.get("strategy_config_schema"),
        context.get("strategy_config_spec"),
    )
    if not any(value is not None for value in values):
        return None
    spec = context.get("strategy_config_spec")
    return StrategyConfigIdentity(
        strategy_version_id=context.get("strategy_version_id"),
        strategy_config_id=context.get("strategy_config_id"),
        strategy_config_hash=context.get("strategy_config_hash"),
        strategy_config_schema=context.get("strategy_config_schema"),
        strategy_config_spec_json=_json_object_text(spec),
    )


def _universe_identity(
    context: Mapping[str, Any],
) -> RecommendationUniverseIdentity | None:
    values = (
        context.get("universe_id"),
        context.get("universe_hash"),
        context.get("universe_identity_schema"),
        context.get("universe_policy_id"),
        context.get("universe_snapshot_id"),
    )
    if not any(value is not None for value in values):
        return None
    policy = UniversePolicyIdentity(
        universe_policy_id=context.get("universe_policy_id"),
        universe_policy_hash=context.get("universe_policy_hash"),
        universe_policy_schema=context.get("universe_policy_schema"),
        universe_policy_spec_json=_json_object_text(
            context.get("universe_policy_spec")
        ),
    )
    snapshot = UniverseSnapshotIdentity(
        universe_snapshot_id=context.get("universe_snapshot_id"),
        universe_snapshot_hash=context.get("universe_snapshot_hash"),
        universe_snapshot_schema=context.get("universe_snapshot_schema"),
        universe_snapshot_source_provider_id=context.get(
            "universe_snapshot_source_provider_id"
        ),
        universe_snapshot_selected_codes_hash=context.get(
            "universe_snapshot_selected_codes_hash"
        ),
        universe_snapshot_spec_json=_json_object_text(
            context.get("universe_snapshot_spec")
        ),
    )
    return RecommendationUniverseIdentity(
        universe_id=context.get("universe_id"),
        universe_hash=context.get("universe_hash"),
        universe_identity_schema=context.get("universe_identity_schema"),
        policy=policy,
        snapshot=snapshot,
    )


def _json_object_text(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_scheduled_result_config(
    postprocess_facts: RecommendationPostprocessFacts | None,
) -> bool:
    if postprocess_facts is None:
        return False
    try:
        value = json.loads(
            postprocess_facts.result_config_snapshot.raw_result_config_json
        )
    except (TypeError, ValueError):
        return False
    return isinstance(value, Mapping) and value.get("scheduled_snapshot") is True


def publish_legacy_invocation_state(service: Any, capture: Mapping[str, Any]) -> None:
    """將本次 body 的 legacy state 一次發布，保留跨欄位巢狀 alias。"""

    if not capture.get("body_entered"):
        return
    compatibility_snapshot = capture.get("compatibility_snapshot")
    if type(compatibility_snapshot) is not LegacyCompatibilitySnapshot:
        raise ValueError("body-entered capture 缺少 typed compatibility snapshot")
    snapshot = compatibility_snapshot.materialize()
    lock = getattr(service, "_r011_last_state_lock", None)
    if lock is None:
        for name in _LEGACY_STATE_FIELDS:
            setattr(service, name, snapshot[name])
        if "personalization_clocks" in capture:
            service._personalization_execution_clocks = deepcopy(
                capture["personalization_clocks"]
            )
        return
    with lock:
        for name in _LEGACY_STATE_FIELDS:
            setattr(service, name, snapshot[name])
        service._personalization_execution_clocks = deepcopy(
            capture.get("personalization_clocks", {})
        )


def project_legacy_recommendations(
    execution: RecommendationExecution,
    capture: Mapping[str, Any],
) -> list[RecommendationDTO]:
    """從 execution 的有序 item 與同次 DTO snapshot 投影舊 list ABI。"""

    if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
        return []
    legacy_by_code = {
        str(item.stock_code): item
        for item in cast_recommendations(capture.get("legacy_recommendations", ()))
    }
    projected: list[RecommendationDTO] = []
    for item in execution.decision.items:
        legacy = legacy_by_code.get(item.stock_code)
        if legacy is None:
            continue
        # DTO 欄位超出 canonical RecommendationItem；保留同 invocation 的原型別
        # 數值與 calibration wire，再用 execution item 鎖定投影順序與排名欄位。
        dto = deepcopy(legacy)
        dto.stock_code = item.stock_code
        if item.stock_name is not None:
            dto.stock_name = item.stock_name
        if item.regime_match is not None:
            dto.regime_match = item.regime_match
        dto.score_percentile_bp = item.score_percentile_bp
        dto.eligible_universe_size = item.eligible_universe_size
        dto.eligible_universe_date = (
            item.eligible_universe_date.isoformat()
            if item.eligible_universe_date is not None
            else None
        )
        if item.ranking_method is not None:
            dto.ranking_method = item.ranking_method
        if item.threshold_mode is not None:
            dto.threshold_mode = item.threshold_mode
        projected.append(dto)
    return projected


def _build_execution(
    *,
    result_id: str,
    config: Mapping[str, Any],
    as_of_date: str | date | None,
    capture: Mapping[str, Any],
    status: ExecutionStatus,
    failure_reason: str | None = None,
    recommendations: Sequence[RecommendationDTO] = (),
    request: Request | None = None,
    invocation_context: RecommendationInvocationContext | None = None,
    postprocess_facts: RecommendationPostprocessFacts | None = None,
    body_result: RecommendationBodyResult | None = None,
    compatibility_snapshot: LegacyCompatibilitySnapshot | None = None,
    post_calibration_handoff: RecommendationPostCalibrationHandoffV1,
) -> RecommendationExecution:
    body_context = body_result.context if body_result is not None else None
    if compatibility_snapshot is not None and type(
        compatibility_snapshot
    ) is not LegacyCompatibilitySnapshot:
        raise TypeError("compatibility_snapshot 必須是 LegacyCompatibilitySnapshot")
    if status is ExecutionStatus.COMPLETED and type(body_result) is not RecommendationBodyResult:
        raise TypeError("completed execution 必須直接使用 RecommendationBodyResult")
    if body_result is not None and body_result.result_id != result_id:
        raise ValueError("RecommendationBodyResult result_id 與 execution 不一致")
    dto_rows = tuple(cast_recommendations(recommendations))
    actual_date = (
        invocation_context.as_of_date
        if invocation_context is not None
        else (
            _date_value(body_context.as_of_date)
            if body_context is not None
            else _date_value(request.as_of_date) if request is not None else None
        )
    ) or _date_value(as_of_date if as_of_date is not None else config.get("as_of_date"))
    if request is None:
        request = _build_request(
            runtime_config=config,
            as_of_date=as_of_date,
            legacy_context={},
            body_context=body_context,
            request_config_snapshot=None,
            max_stocks=200,
            top_n=50,
        )
    strategy_identity = (
        body_context.strategy_identity
        if body_context is not None
        else (
            invocation_context.strategy_identity
            if invocation_context is not None
            else None
        )
    )
    universe_identity = (
        body_context.universe_identity
        if body_context is not None
        else (
            invocation_context.universe_identity
            if invocation_context is not None
            else None
        )
    )
    decision_at = (
        _datetime_value(body_context.decision_at)
        if body_context is not None
        else (
            invocation_context.decision_at
            if invocation_context is not None
            else None
        )
    )
    universe_policy_ref = request.universe_policy_ref
    universe_snapshot_ref = (
        _version_reference(
            ReferenceKind.UNIVERSE_SNAPSHOT,
            universe_identity.snapshot.universe_snapshot_id,
        )
        if universe_identity is not None and universe_identity.snapshot is not None
        else None
    )

    warnings = (
        body_context.warnings
        if body_context is not None
        else ()
    )
    warnings = _append_once(warnings, "legacy_source_identity_unbound")
    if body_result is not None:
        quality_status = (
            QualityStatus.DEGRADED
            if any(
                disposition.quality in {"missing", "degraded"}
                for disposition in body_result.dispositions
            )
            else QualityStatus.UNKNOWN
        )
        screening_row_count = len(body_result.dispositions)
        canonical_recommendation_count = len(body_result.decision.items)
    else:
        # Failed executions have no canonical body facts.  Preserve their
        # partial matrix/context in events only; never infer canonical quality
        # from a body that did not publish a typed result.
        quality_status = QualityStatus.UNKNOWN
        screening_row_count = 0
        canonical_recommendation_count = 0
    input_quality = QualityReport(
        status=quality_status,
        warnings=warnings,
        metrics={
            "screening_row_count": screening_row_count,
            "recommendation_count": canonical_recommendation_count,
        },
    )
    context = Context(
        as_of_date=actual_date,
        decision_at=decision_at,
        source_refs=(),
        data_snapshot_refs=(),
        config_ref=request.config_ref,
        profile_ref=request.profile_ref,
        strategy_ref=request.strategy_ref,
        universe_policy_ref=universe_policy_ref,
        universe_snapshot_ref=universe_snapshot_ref,
        input_quality=input_quality,
        warnings=warnings,
        created_at=(
            postprocess_facts.created_at if postprocess_facts is not None else None
        ),
        available_at=(
            invocation_context.available_at
            if invocation_context is not None
            else None
        ),
        strategy_identity=strategy_identity,
        universe_identity=universe_identity,
        snapshot_cohort=(
            postprocess_facts.snapshot_cohort
            if postprocess_facts is not None
            else None
        ),
        evidence_identity=(
            postprocess_facts.evidence_identity
            if postprocess_facts is not None
            else None
        ),
        result_config_snapshot=(
            postprocess_facts.result_config_snapshot
            if postprocess_facts is not None
            else None
        ),
    )

    receipt_binding, projection_refs = verified_receipt_references_v1(
        handoff=post_calibration_handoff,
        result_id=result_id,
        context_date=actual_date,
    )
    ml_availability = ml_availability_from_handoff_v1(
        handoff=post_calibration_handoff,
        bindings=receipt_binding,
        recommendation_count=canonical_recommendation_count,
    )
    events = _capture_events(
        compatibility_snapshot,
        capture,
        post_calibration_handoff,
    )
    if invocation_context is not None:
        events = (
            *events,
            ExecutionEvent(
                event_type="recommendation_invocation_clock_capture",
                message="保存 callback 所用 caller clock 與 service body clock，兩者維持各自來源。",
                occurred_at=invocation_context.decision_at,
                details={
                    "created_at": invocation_context.created_at,
                    "service_run_started_at": invocation_context.service_run_started_at,
                    "available_at": invocation_context.available_at,
                    "decision_at": invocation_context.decision_at,
                },
            ),
        )

    decision: DecisionBatch | None = None
    if status is ExecutionStatus.COMPLETED:
        assert body_result is not None
        scheduled_capture = _is_scheduled_result_config(postprocess_facts)
        if scheduled_capture:
            for dto in dto_rows:
                numeric_fields = {
                    "rule_score": _contract_numeric(dto.total_score),
                    "close_price": _contract_numeric(dto.close_price),
                    "price_change": _contract_numeric(dto.price_change),
                    "indicator_score": _contract_numeric(dto.indicator_score),
                    "pattern_score": _contract_numeric(dto.pattern_score),
                    "volume_score": _contract_numeric(dto.volume_score),
                }
                missing_numeric = [
                    name for name, value in numeric_fields.items() if value is None
                ]
                if missing_numeric:
                    raise ValueError(
                        "scheduled RecommendationItem 缺少有限數值欄位: "
                        + ", ".join(missing_numeric)
                    )
                industry = _optional_str(dto.industry)
                if industry is None or not industry.strip():
                    raise ValueError("scheduled RecommendationItem.industry 不可缺漏")
                reason_text = _optional_str(dto.recommendation_reasons)
                if reason_text is None or not reason_text.strip():
                    raise ValueError("scheduled RecommendationItem.reason_text 不可缺漏")
        decision = body_result.decision

    return RecommendationExecution(
        result_id=result_id,
        request=request,
        context=context,
        status=status,
        decision=decision,
        quality=input_quality,
        ml_availability=ml_availability,
        events=events,
        ml_projection_refs=projection_refs,
        ml_receipt_refs=receipt_binding,
        failure_reason=failure_reason,
    )


def _capture_events(
    compatibility_snapshot: LegacyCompatibilitySnapshot | None,
    capture: Mapping[str, Any],
    post_calibration_handoff: RecommendationPostCalibrationHandoffV1,
) -> tuple[ExecutionEvent, ...]:
    events: list[ExecutionEvent] = []
    legacy_state = (
        compatibility_snapshot.materialize()
        if compatibility_snapshot is not None
        else {}
    )
    legacy_context = legacy_state.get("last_run_context", {})
    if legacy_context:
        events.append(
            ExecutionEvent(
                event_type="legacy_invocation_context",
                message="封存本次 legacy recommendation context；來源版本未被 typed source ref 證明。",
                occurred_at=_datetime_value(legacy_context.get("decision_at")),
                details={
                    "result_id": str(legacy_context.get("result_id") or ""),
                    "source_id": str(legacy_context.get("source_id") or ""),
                    "market_data_fingerprint": str(
                        legacy_context.get("market_data_fingerprint") or ""
                    ),
                    "data_fingerprint": str(
                        legacy_context.get("data_fingerprint") or ""
                    ),
                    "warnings": _string_tuple(legacy_context.get("warnings")),
                    "eligible_universe_size": _optional_int(
                        legacy_context.get("eligible_universe_size")
                    ),
                },
            )
        )
    matrix = legacy_state.get("last_screening_matrix", ())
    if matrix:
        events.append(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message="Negative-evidence typed assessments 以外的原始 matrix 欄位保存在同次 invocation capture。",
                details={
                    "screening_matrix": _safe_contract_value(matrix),
                    "excluded_candidates": _safe_contract_value(
                        legacy_state.get("last_excluded_candidates_json", ())
                    ),
                    "why_not_payload": _safe_contract_value(
                        legacy_state.get("last_why_not_payload_json", ())
                    ),
                    "liquidity_gate_payload": _safe_contract_value(
                        legacy_state.get("last_liquidity_gate_payload_json", ())
                    ),
                    "exclusion_quality": str(
                        legacy_state.get("last_exclusion_quality", "unknown")
                    ),
                    "exclusion_warnings": _string_tuple(
                        legacy_state.get("last_exclusion_warnings_json", ())
                    ),
                },
            )
        )
    receipt_event = post_calibration_handoff.receipt_event
    if receipt_event is not None:
        events.append(
            ExecutionEvent(
                event_type="ml_projection_receipt_capture",
                message="封存本次 receipt 寫入、readback 與候選 identity 檢查結果。",
                details=receipt_event.event_details(),
            )
        )
    error = capture.get("error")
    if error is not None:
        events.append(
            ExecutionEvent(
                event_type="recommendation_execution_error",
                message=f"{type(error).__name__}: {error}",
                details={"exception_type": type(error).__name__},
            )
        )
    progress_errors = capture.get("progress_callback_errors", ())
    if progress_errors:
        events.append(
            ExecutionEvent(
                event_type="progress_callback_error",
                message="進度 callback 發生錯誤；推薦計算結果未因此改變。",
                details={"errors": _string_tuple(progress_errors)},
            )
        )
    if capture.get("cancelled_after_body"):
        events.append(
            ExecutionEvent(
                event_type="recommendation_execution_cancelled",
                message="body 已完成，但其結果依取消語意不發布。",
                details={
                    "discarded_recommendation_count": len(
                        capture.get("legacy_recommendations", ())
                    )
                },
            )
        )
    return tuple(events)


def _universe_reference(
    context: Mapping[str, Any],
    as_of_date: date | None,
) -> UniverseReference | None:
    policy_id = str(context.get("universe_policy_id") or "").strip()
    snapshot_id = str(context.get("universe_snapshot_id") or "").strip()
    spec = context.get("universe_snapshot_spec")
    members_hash = (
        str(spec.get("selected_codes_hash") or "").strip()
        if isinstance(spec, Mapping)
        else ""
    )
    if not policy_id or not snapshot_id or not members_hash:
        return None
    return UniverseReference(
        policy_id=policy_id,
        snapshot_id=snapshot_id,
        as_of_date=as_of_date,
        members_hash=members_hash,
    )


def _requested_result_id(config: Mapping[str, Any], result_id: str | None) -> str:
    requested = str(result_id or config.get("result_id") or "").strip()
    return requested or f"rec_{uuid4().hex}"


def _version_reference(
    kind: ReferenceKind,
    value: object,
    version: object = None,
) -> VersionReference | None:
    reference_id = str(value or "").strip()
    if not reference_id:
        return None
    version_text = str(version).strip() if version is not None else ""
    return VersionReference(kind, reference_id, version_text or None)


def _date_value(value: object) -> date | None:
    if type(value) is date:
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10].replace("/", "-"))
    except ValueError:
        if len(text) == 8 and text.isdigit():
            try:
                return datetime.strptime(text, "%Y%m%d").date()
            except ValueError:
                return None
        return None


def _datetime_value(value: object) -> datetime | None:
    if type(value) is datetime:
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _contract_numeric(value: object) -> Decimal | int | None:
    if type(value) is int:
        return value
    if type(value) is Decimal:
        return value if value.is_finite() else None
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return numeric if numeric.is_finite() else None


def _optional_int(value: object) -> int | None:
    return value if type(value) is int else None


def _optional_str(value: object) -> str | None:
    return value if type(value) is str else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value if item is not None)


def _append_once(values: tuple[str, ...], item: str) -> tuple[str, ...]:
    return values if item in values else (*values, item)


def _safe_contract_value(
    value: object,
    active: set[int] | None = None,
    field_path: str = "value",
) -> Any:
    """依明示 allowlist 轉換舊 evidence；未知型別一律拒絕封存。"""

    if active is None:
        active = set()

    if value is None or type(value) in (str, int, bool, Decimal, date, datetime):
        if type(value) is Decimal and not value.is_finite():
            raise ValueError(f"{field_path} 的 Decimal 必須是有限值")
        if type(value) is datetime and (value.tzinfo is None or value.utcoffset() is None):
            return value.isoformat()
        return value

    if type(value) is float:
        try:
            converted = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field_path} 的 float 無法封存") from exc
        if not converted.is_finite():
            raise ValueError(f"{field_path} 的 float 必須是有限值")
        return converted

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        try:
            converted = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field_path} 的 NumPy 浮點值無法封存") from exc
        if not converted.is_finite():
            raise ValueError(f"{field_path} 的 NumPy 浮點值必須是有限值")
        return converted

    if isinstance(value, np.str_):
        return str(value)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環 mapping")
        active.add(identity)
        try:
            converted_mapping: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError(f"{field_path} 的 mapping key 必須是 str")
                converted_mapping[key] = _safe_contract_value(
                    item, active, f"{field_path}.{key}"
                )
            return converted_mapping
        finally:
            active.remove(identity)

    if type(value) in (list, tuple):
        identity = id(value)
        if identity in active:
            raise TypeError(f"{field_path} 不接受循環 sequence")
        active.add(identity)
        try:
            sequence = cast(Sequence[object], value)
            converted_items = tuple(
                _safe_contract_value(item, active, f"{field_path}[{index}]")
                for index, item in enumerate(sequence)
            )
        finally:
            active.remove(identity)
        return converted_items

    raise TypeError(
        f"{field_path} 型別 {type(value).__name__} 不在 execution evidence allowlist"
    )


def cast_recommendations(value: object) -> tuple[RecommendationDTO, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, RecommendationDTO))


def _cancelled_before_start(
    *,
    config: Mapping[str, Any],
    as_of_date: str | date | None,
    result_id: str,
    request_config_snapshot: RecommendationConfigSnapshot | None = None,
    max_stocks: int = 200,
    top_n: int = 50,
) -> RecommendationExecution:
    warning = ("execution_cancelled_before_start", "legacy_source_identity_unbound")
    quality = QualityReport(status=QualityStatus.UNKNOWN, warnings=warning)
    as_of = _date_value(as_of_date if as_of_date is not None else config.get("as_of_date"))
    return RecommendationExecution(
        result_id=result_id,
        request=_build_request(
            runtime_config=config,
            as_of_date=as_of,
            legacy_context={},
            request_config_snapshot=request_config_snapshot,
            max_stocks=max_stocks,
            top_n=top_n,
        ),
        context=Context(as_of_date=as_of, input_quality=quality, warnings=warning),
        status=ExecutionStatus.CANCELLED,
        quality=quality,
        ml_availability=MLAvailability(status=MLAvailabilityStatus.UNKNOWN),
        events=(
            ExecutionEvent(
                event_type="recommendation_execution_cancelled",
                message="取消在推薦計算開始前收到；未呼叫 legacy body。",
            ),
        ),
        failure_reason="cancelled_before_start",
    )


def _notify_progress(
    callback: Callable[[str, int], None] | None,
    stage: str,
    percent: int,
    capture: MutableMapping[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(stage, percent)
    except Exception as exc:  # 進度顯示失敗不改變原計算結果。
        errors = capture.setdefault("progress_callback_errors", [])
        errors.append(f"{type(exc).__name__}: {exc}")
