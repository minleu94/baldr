"""推薦 execute 用例與舊 DTO façade 的單次 invocation 接線。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from types import TracebackType
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np

from app_module.recommendation.legacy_dtos import RecommendationDTO
from app_module.recommendation.body_result import (
    LegacyRecommendationSnapshot,
    RecommendationBodyContextFacts,
    RecommendationBodyResult,
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
)
from app_module.recommendation.negative_evidence_projection import (
    project_canonical_negative_evidence,
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
from app_module.recommendation.personal_use_policy import (
    PERSONAL_CALIBRATED_PROBABILITY_MODE,
    RULE_ONLY_MODE,
    validate_personal_use_policy_snapshot,
)
from decision_module.recommendation.contracts import (
    DecisionBatch,
    RecommendationItem,
    UniverseReference,
)
from data_module.industry_mapper_data_provider import (
    industry_index_source_observation_hash_matches,
)
from app_module.v4_evidence_identity import DEFAULT_RETURN_BASIS
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenario,
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
)


_LEGACY_STATE_FIELDS = LEGACY_COMPATIBILITY_FIELDS

_SCHEDULED_DECISION_TIMEZONE = ZoneInfo("America/Los_Angeles")


def _utc_now() -> datetime:
    """Return the single aware clock sample captured for one invocation."""

    return datetime.now(timezone.utc)


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
    invocation_frozen_at = _utc_now()
    capture["invocation_frozen_at"] = invocation_frozen_at.isoformat(
        timespec="microseconds"
    )
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
            invocation_frozen_at=invocation_frozen_at,
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
            invocation_frozen_at=invocation_frozen_at,
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
        _sync_partial_capture_sink(
            capture_sink,
            capture,
        )
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
        negative_evidence = project_canonical_negative_evidence(
            body_result.decision,
            allow_empty=True,
        )
        postprocess_input = RecommendationPostprocessInput(
            result_id=result_id_from_context,
            request=request,
            runtime_config=deepcopy(dict(runtime_config)),
            recommendations=tuple(
                deepcopy(cast_recommendations(capture["legacy_recommendations"]))
            ),
            screening_matrix=negative_evidence.screening_matrix,
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

    # Event construction validates current-fundamental lineage and may fail
    # after a successful body. Publish the exact invocation snapshot first so
    # callers can inspect the source diagnostics without publishing an execution.
    _sync_partial_capture_sink(
        capture_sink,
        capture,
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
            max_stocks=max_stocks,
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
            max_stocks=max_stocks,
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
            max_stocks=max_stocks,
        )

    if capture_sink is not None:
        capture_sink.clear()
        capture_sink.update(capture)
        capture_sink["execution"] = execution
    _notify_progress(progress, "recommendation_execution_finished", 100, capture)
    return execution


def _sync_partial_capture_sink(
    capture_sink: MutableMapping[str, Any] | None,
    capture: Mapping[str, Any],
) -> None:
    """Expose the exact invocation capture before later event validation."""

    if capture_sink is None:
        return
    capture_sink.clear()
    capture_sink.update(capture)


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
        if raw_result_config.get("date_semantics_schema") is not None:
            if (raw_result_config.get("date_semantics_schema") != "scheduled-recommendation-date-roles.v1"
                    or raw_result_config.get("decision_timezone") != "Asia/Taipei"
                    or raw_result_config.get("market_cutoff_date") != context.as_of_date):
                raise ValueError("scheduled date roles schema/timezone/cutoff mismatch")
            assert facts.created_at is not None
            expected_decision_date = facts.created_at.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
            captured_decision_at = datetime.fromisoformat(context.decision_at)
            if captured_decision_at.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != expected_decision_date:
                raise ValueError("scheduled invocation crossed Taipei decision-date boundary; retry with a new invocation")
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
            else body_context.as_of_date
            if body_context is not None
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
    max_stocks: int,
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
            max_stocks=max_stocks,
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
    market_data_snapshot_refs: tuple[VersionReference, ...] = ()
    if body_context is not None:
        legacy_context_value = body_context.legacy_context.thaw()
        if isinstance(legacy_context_value, Mapping) and legacy_context_value.get(
            "personal_live_clock_schema"
        ) == "recommendation-personal-live-clock.v1":
            source_id = legacy_context_value.get("source_id")
            market_fingerprint = legacy_context_value.get("market_data_fingerprint")
            market_data_date = legacy_context_value.get("data_date")
            if (
                type(source_id) is not str
                or not source_id.strip()
                or type(market_fingerprint) is not str
                or len(market_fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in market_fingerprint)
                or type(market_data_date) is not str
            ):
                raise ValueError("personal live market source identity is incomplete")
            if market_data_date:
                try:
                    parsed_market_date = date.fromisoformat(market_data_date)
                except ValueError as exc:
                    raise ValueError("personal live market data_date is invalid") from exc
                if parsed_market_date.isoformat() != market_data_date:
                    raise ValueError("personal live market data_date is not canonical")
                if actual_date is None or parsed_market_date > actual_date:
                    raise ValueError("personal live market data_date is after decision date")
            market_data_snapshot_refs = (
                VersionReference(
                    kind=ReferenceKind.DATA_SNAPSHOT,
                    reference_id=market_fingerprint,
                    version=f"{source_id}:{market_data_date or 'undated'}",
                ),
            )
    context = Context(
        as_of_date=actual_date,
        decision_at=decision_at,
        source_refs=(),
        data_snapshot_refs=market_data_snapshot_refs,
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
        status=status,
        body_result=body_result,
        result_id=result_id,
        max_stocks=max_stocks,
        context_as_of_date=actual_date,
        context_decision_at=decision_at,
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
    *,
    status: ExecutionStatus,
    body_result: RecommendationBodyResult | None,
    result_id: str,
    max_stocks: int,
    context_as_of_date: date | None,
    context_decision_at: datetime | None,
) -> tuple[ExecutionEvent, ...]:
    events: list[ExecutionEvent] = []
    legacy_state = (
        compatibility_snapshot.materialize()
        if compatibility_snapshot is not None
        else {}
    )
    legacy_context = legacy_state.get("last_run_context", {})
    if legacy_context:
        diagnostics_raw = legacy_context.get(
            "current_market_status_preflight_diagnostics", ()
        )
        if not isinstance(diagnostics_raw, (tuple, list)) or any(
            type(item) is not str for item in diagnostics_raw
        ):
            raise TypeError(
                "current_market_status_preflight_diagnostics 必須是字串序列"
            )
        legacy_details: dict[str, object] = {
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
            "current_market_status_preflight_diagnostics": _string_tuple(
                diagnostics_raw
            ),
        }
        if body_result is not None:
            legacy_details["invocation_id"] = body_result.invocation_id
        market_data_provenance = _market_data_provenance_details(
            legacy_context,
            status=status,
            body_result=body_result,
            result_id=result_id,
            context_as_of_date=context_as_of_date,
            context_decision_at=context_decision_at,
        )
        if market_data_provenance is not None:
            legacy_details["market_data_provenance"] = market_data_provenance
        events.append(
            ExecutionEvent(
                event_type="legacy_invocation_context",
                message=(
                    "封存本次 legacy recommendation context；行情資料日只記錄同次執行"
                    "的來源日期與指紋，不代表可得時間或 PIT 資格。"
                ),
                occurred_at=_datetime_value(legacy_context.get("decision_at")),
                details=legacy_details,
            )
        )
        # A lineage event is a record of a successfully published typed body,
        # not of a partial legacy context. Failed body construction has no
        # invocation identity to bind; preserve its ordinary failure events
        # without masking the original exception with an invalid empty ID.
        if body_result is not None:
            chart_capture = legacy_context.get("saved_technical_charts")
            if isinstance(chart_capture, Mapping) and status == ExecutionStatus.COMPLETED:
                events.append(ExecutionEvent(
                    event_type="recommendation_saved_technical_charts",
                    message="封存同次推薦來源價格與既有MA20／MA60，僅供研究重讀，不授予PIT或交易資格。",
                    occurred_at=context_decision_at,
                    details=dict(chart_capture),
                ))
            current_lineage_event = _current_fundamental_lineage_event(
                legacy_context,
                result_id=result_id,
                invocation_id=body_result.invocation_id,
                decision_at=context_decision_at,
                max_stocks=max_stocks,
            )
            if current_lineage_event is not None:
                events.append(current_lineage_event)
    personal_policy_snapshot = legacy_context.get("personal_use_policy")
    if personal_policy_snapshot is not None:
        if not isinstance(personal_policy_snapshot, Mapping):
            raise TypeError("personal_use_policy 必須是同次 invocation 的完整 object")
        try:
            validated_policy_snapshot = validate_personal_use_policy_snapshot(
                personal_policy_snapshot
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("personal policy event 的設定快照無效") from exc
        requested_mode = legacy_context.get("personal_use_requested_mode")
        effective_mode = legacy_context.get("personal_use_effective_mode")
        if (
            dict(personal_policy_snapshot) != validated_policy_snapshot
            or requested_mode != validated_policy_snapshot["mode"]
            or requested_mode
            not in {RULE_ONLY_MODE, PERSONAL_CALIBRATED_PROBABILITY_MODE}
            or effective_mode
            not in {RULE_ONLY_MODE, PERSONAL_CALIBRATED_PROBABILITY_MODE}
            or (
                requested_mode == RULE_ONLY_MODE
                and effective_mode != RULE_ONLY_MODE
            )
        ):
            raise ValueError("personal policy event 的模式與驗證快照不一致")
        decision_at = _datetime_value(legacy_context.get("decision_at"))
        if (
            decision_at is None
            or type(result_id) is not str
            or not result_id.strip()
            or decision_at != context_decision_at
            or str(legacy_context.get("result_id") or "") != result_id
        ):
            raise ValueError("personal policy event 缺少 aware decision_at")
        if validated_policy_snapshot["revision"] > 0:
            confirmed_at = _datetime_value(
                validated_policy_snapshot.get("confirmed_at")
            )
            if confirmed_at is None or confirmed_at > decision_at:
                raise ValueError("personal policy event 確認時間晚於決策時間")
        events.append(
            ExecutionEvent(
                event_type="personal_use_policy_snapshot",
                message="封存本次 recommendation invocation 實際使用的個人政策快照與模式。",
                occurred_at=decision_at,
                details={
                    "schema_version": (
                        "recommendation-personal-use-policy-snapshot.v2"
                        if validated_policy_snapshot.get("schema_version")
                        == "recommendation-personal-use-policy.v2"
                        else "recommendation-personal-use-policy-snapshot.v1"
                    ),
                    "result_id": result_id,
                    "decision_at": decision_at,
                    "policy_snapshot": _safe_contract_value(
                        validated_policy_snapshot,
                        field_path="personal_use_policy",
                    ),
                    "requested_mode": legacy_context[
                        "personal_use_requested_mode"
                    ],
                    "effective_mode": legacy_context[
                        "personal_use_effective_mode"
                    ],
                    **(
                        {
                            "source_time_basis": "user_declared_source_time",
                            "research_only": True,
                            "official_historical_pit_verified": False,
                        }
                        if validated_policy_snapshot.get("schema_version")
                        == "recommendation-personal-use-policy.v2"
                        and validated_policy_snapshot.get("source_time_trust")
                        is not None
                        else {}
                    ),
                },
            )
        )
    industry_source_snapshot = legacy_context.get(
        "industry_mapping_source_snapshot"
    )
    if industry_source_snapshot is not None:
        if not isinstance(industry_source_snapshot, Mapping):
            raise TypeError("industry_mapping_source_snapshot 必須是 object")
        snapshot = dict(industry_source_snapshot)
        declared_snapshot_hash = snapshot.pop("snapshot_sha256", None)
        try:
            snapshot_bytes = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("industry mapping source snapshot 不是 canonical JSON") from exc
        expected_snapshot_hash = "sha256:" + hashlib.sha256(snapshot_bytes).hexdigest()
        snapshot_decision_at = snapshot.get("decision_at")
        legacy_decision_at = legacy_context.get("decision_at")
        decision_at = _datetime_value(snapshot_decision_at)
        if snapshot_decision_at is not None and decision_at is None:
            raise ValueError("industry mapping source snapshot decision_at 無效")
        # 未產生決策結果的路徑可以保留無時鐘的來源事件，但不可補造時間。
        if decision_at is not None or snapshot_decision_at is None:
            usages = snapshot.get("usage")
            source_contract = snapshot.get("company_registry_source_contract")
            source_warnings = snapshot.get("warnings")
            source_contract_hash_matches = (
                _company_registry_contract_hash_matches(source_contract)
                if isinstance(source_contract, Mapping)
                else None
            )
            snapshot_schema_version = snapshot.get("schema_version")
            if snapshot_schema_version == "recommendation-company-registry-source-snapshot.v1":
                source_date_binding_valid = snapshot.get("data_as_of_date") == (
                    context_as_of_date.isoformat()
                    if context_as_of_date is not None
                    else None
                )
            elif snapshot_schema_version == "recommendation-company-registry-source-snapshot.v2":
                market_data_date = legacy_context.get("data_date")
                expected_market_data_date = market_data_date or None
                market_date_binding_valid = type(market_data_date) is str
                if market_date_binding_valid and expected_market_data_date is not None:
                    try:
                        parsed_market_date = date.fromisoformat(expected_market_data_date)
                    except ValueError:
                        market_date_binding_valid = False
                    else:
                        market_date_binding_valid = (
                            parsed_market_date.isoformat() == expected_market_data_date
                            and context_as_of_date is not None
                            and parsed_market_date <= context_as_of_date
                        )
                source_date_binding_valid = (
                    legacy_context.get("personal_live_clock_schema")
                    == "recommendation-personal-live-clock.v1"
                    and snapshot.get("decision_date")
                    == (
                        context_as_of_date.isoformat()
                        if context_as_of_date is not None
                        else None
                    )
                    and snapshot.get("data_as_of_date") == expected_market_data_date
                    and snapshot.get("source_id") == legacy_context.get("source_id")
                    and snapshot.get("market_data_fingerprint")
                    == legacy_context.get("market_data_fingerprint")
                    and market_date_binding_valid
                )
            else:
                source_date_binding_valid = False
            valid_usages = {
                "current_filter_selection",
                "current_filter_empty_industries_diagnostic",
                "current_filter_example_industry_diagnostic",
                "current_industry_context_display_reason",
                "current_fallback_display_reason",
                "current_industry_index_performance_for_reason",
            }
            current_industry_index_used = (
                isinstance(usages, list)
                and "current_industry_index_performance_for_reason" in usages
            )
            observation_fields = (
                "industry_index_source_observation",
                "industry_index_source_observation_sha256",
                "industry_index_source_time_status",
                "industry_index_source_available_at",
                "industry_index_source_published_at",
            )
            has_observation_fields = any(
                field_name in snapshot for field_name in observation_fields
            )
            industry_index_observation_binding_valid = True
            if current_industry_index_used and has_observation_fields:
                failure_warnings = {
                    "industry_index_source_observation_missing_for_current_use",
                    "industry_index_source_observation_mismatch_for_current_use",
                    "industry_index_source_observation_not_json_snapshot",
                }
                warnings_set = (
                    set(source_warnings)
                    if isinstance(source_warnings, list)
                    and all(type(item) is str for item in source_warnings)
                    else set()
                )
                industry_observation = snapshot.get(
                    "industry_index_source_observation"
                )
                industry_observation_sha256 = snapshot.get(
                    "industry_index_source_observation_sha256"
                )
                industry_index_observation_binding_valid = (
                    all(field_name in snapshot for field_name in observation_fields)
                    and snapshot.get("industry_index_source_status") == "unknown"
                    and snapshot.get("industry_index_source_time_status") == "unknown"
                    and snapshot.get("industry_index_source_available_at") is None
                    and snapshot.get("industry_index_source_published_at") is None
                    and "industry_index_source_capture_time_unknown_for_current_use"
                    in warnings_set
                )
                if industry_index_observation_binding_valid:
                    if industry_observation is None:
                        industry_index_observation_binding_valid = (
                            industry_observation_sha256 is None
                            and bool(warnings_set & failure_warnings)
                        )
                    elif isinstance(industry_observation, Mapping):
                        try:
                            detached_observation = dict(industry_observation)
                        except (TypeError, ValueError):
                            industry_index_observation_binding_valid = False
                        else:
                            industry_index_observation_binding_valid = (
                                not bool(warnings_set & failure_warnings)
                                and industry_index_source_observation_hash_matches(
                                    detached_observation
                                )
                                and industry_observation_sha256
                                == detached_observation.get("observation_sha256")
                            )
                    else:
                        industry_index_observation_binding_valid = False
            if (
                declared_snapshot_hash != expected_snapshot_hash
                or snapshot_schema_version
                not in (
                    "recommendation-company-registry-source-snapshot.v1",
                    "recommendation-company-registry-source-snapshot.v2",
                )
                or snapshot.get("scope") != "current_classification_only"
                or snapshot.get("pit_eligible") is not False
                or type(result_id) is not str
                or not result_id.strip()
                or snapshot.get("result_id")
                != result_id
                or snapshot_decision_at != legacy_decision_at
                or not source_date_binding_valid
                or snapshot.get("company_registry_source_status")
                not in {"captured", "unknown"}
                or snapshot.get("industry_index_source_status")
                not in {"not_observed", "unknown"}
                or not isinstance(usages, list)
                or not usages
                or any(type(item) is not str or item not in valid_usages for item in usages)
                or len(set(usages)) != len(usages)
                or type(source_warnings) is not list
                or any(type(item) is not str for item in source_warnings)
                or (
                    source_contract is not None
                    and not isinstance(source_contract, Mapping)
                )
                or (
                    isinstance(source_contract, Mapping)
                    and source_contract.get("source_contract_sha256") is not None
                    and not source_contract_hash_matches
                    and (
                        snapshot.get("company_registry_source_status") != "unknown"
                        or "company_registry_source_contract_hash_mismatch"
                        not in source_warnings
                    )
                )
                or (
                    snapshot.get("company_registry_source_status") == "captured"
                    and (
                        not isinstance(source_contract, Mapping)
                        or source_contract.get("schema_version")
                        != "company-registry-source-contract.v1"
                        or source_contract.get("scope")
                        != "current_classification_only"
                        or source_contract.get("pit_eligible") is not False
                        or source_contract.get("status") != "captured"
                        or not source_contract_hash_matches
                        or snapshot.get("company_registry_source_contract_sha256")
                        != source_contract.get("source_contract_sha256")
                    )
                )
                or (
                    snapshot.get("company_registry_source_status") == "unknown"
                    and snapshot.get("company_registry_source_contract_sha256")
                    != (
                        source_contract.get("source_contract_sha256")
                        if isinstance(source_contract, Mapping)
                        else None
                    )
                )
                or (
                    "current_industry_index_performance_for_reason" in usages
                    and snapshot.get("industry_index_source_status") != "unknown"
                )
                or (
                    "current_industry_index_performance_for_reason" in usages
                    and "industry_index_source_contract_unavailable_for_current_use"
                    not in source_warnings
                )
                or not industry_index_observation_binding_valid
            ):
                raise ValueError("industry mapping source snapshot binding 無效")
            if (
                _datetime_value(legacy_decision_at) != decision_at
                or context_decision_at != decision_at
                or str(legacy_context.get("result_id") or "") != result_id
            ):
                raise ValueError("industry mapping source snapshot decision_at 不一致")
            events.append(
                ExecutionEvent(
                    event_type="company_registry_source_snapshot",
                    message="封存本次 current-only 公司產業分類來源與實際 mapper 用途。",
                    occurred_at=decision_at,
                    details={
                        "schema_version": "recommendation-company-registry-source-snapshot-event.v1",
                        "result_id": result_id,
                        "decision_at": decision_at,
                        "snapshot": _safe_contract_value(
                            {**snapshot, "snapshot_sha256": declared_snapshot_hash},
                            field_path="industry_mapping_source_snapshot",
                        ),
                    },
                )
            )
    if status is ExecutionStatus.COMPLETED:
        if type(body_result) is not RecommendationBodyResult:
            raise ValueError("completed execution 缺少 typed BodyResult negative evidence")
        projection = project_canonical_negative_evidence(
            body_result.decision,
            allow_empty=True,
        )
        matrix = projection.screening_matrix
        event_details = projection.as_event_details()
    else:
        # 失敗或取消時沿用原本的部分相容事件，不以 typed 投影取代。
        matrix = legacy_state.get("last_screening_matrix", ())
        event_details = {
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
        }
    if matrix:
        message = (
            "封存 legacy:<stage> assessment 的 v1 screening projection，"
            "供舊 reader 延續讀取。"
            if status is ExecutionStatus.COMPLETED
            else "Negative-evidence typed assessments 以外的原始 matrix 欄位保存在同次 invocation capture。"
        )
        events.append(
            ExecutionEvent(
                event_type="legacy_negative_evidence_capture",
                message=message,
                details=event_details,
            )
        )
    receipt_event = post_calibration_handoff.receipt_event
    if receipt_event is not None:
        receipt_event_details = receipt_event.event_details()
        events.append(
            ExecutionEvent(
                event_type="ml_projection_receipt_capture",
                message="封存本次 receipt 寫入、readback 與候選 identity 檢查結果。",
                details=receipt_event_details,
            )
        )
        baseline_inputs = legacy_context.get("personal_probability_baseline_inputs")
        if baseline_inputs is not None:
            if not isinstance(baseline_inputs, Mapping):
                raise TypeError("personal probability baseline inputs 必須是同次 object")
            try:
                baseline_input = _safe_contract_value(
                    baseline_inputs,
                    field_path="personal_probability_baseline_inputs",
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("personal probability baseline inputs 無法封存") from exc
            baseline_schema = baseline_input.get("schema_version")
            is_v3_baseline = (
                baseline_schema
                == "recommendation-personal-probability-baseline-inputs.v3"
            )
            input_fields = (
                {
                    "schema_version",
                    "result_id",
                    "decision_at",
                    "decision_date",
                    "projected_stock_codes",
                    "delivered_stock_codes",
                    "model_active_stock_codes",
                    "rule_only_fallback_stock_codes",
                    "delivered_count",
                    "model_active_count",
                    "fallback_count",
                    "model_coverage_bp",
                    "upside_baseline_kind",
                    "upside_baseline_id",
                    "upside_probability_bp_by_symbol",
                    "after_cost_baseline_status",
                    "after_cost_baseline_id",
                    "after_cost_probability_bp_by_symbol",
                    "cost_scenario",
                }
                if is_v3_baseline
                else {
                    "schema_version",
                    "result_id",
                    "decision_at",
                    "decision_date",
                    "upside_baseline_kind",
                    "upside_baseline_id",
                    "upside_probability_bp_by_symbol",
                    "after_cost_baseline_status",
                    "after_cost_baseline_id",
                    "after_cost_probability_bp_by_symbol",
                }
            )
            decision_at = _datetime_value(legacy_context.get("decision_at"))
            effective_mode = legacy_context.get("personal_use_effective_mode")
            requested_mode = legacy_context.get("personal_use_requested_mode")
            policy_mode = (
                validated_policy_snapshot.get("mode")
                if isinstance(personal_policy_snapshot, Mapping)
                else None
            )
            projected_codes = receipt_event_details.get("projected_stock_codes")
            if isinstance(projected_codes, tuple):
                projected_codes = list(projected_codes)
            normalized_projected_codes = (
                cast(list[str], projected_codes)
                if type(projected_codes) is list
                else []
            )
            projection_rows = legacy_context.get("calibration_projection_rows")
            baseline_decision_at = _datetime_value(
                baseline_input.get("decision_at")
            )
            canonical_decision_at = (
                decision_at.astimezone(ZoneInfo("UTC"))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
                if decision_at is not None
                else None
            )
            projected_codes_valid = (
                bool(normalized_projected_codes)
                and all(
                    type(code) is str and bool(code)
                    for code in normalized_projected_codes
                )
                and len(set(normalized_projected_codes))
                == len(normalized_projected_codes)
            )
            code_set = (
                set(normalized_projected_codes) if projected_codes_valid else set()
            )
            active_codes_value = baseline_input.get("model_active_stock_codes")
            fallback_codes_value = baseline_input.get("rule_only_fallback_stock_codes")
            delivered_codes_value = baseline_input.get("delivered_stock_codes")
            active_codes_valid = (
                isinstance(active_codes_value, (list, tuple))
                and all(
                    type(code) is str and bool(code) for code in active_codes_value
                )
            )
            fallback_codes_valid = (
                isinstance(fallback_codes_value, (list, tuple))
                and all(
                    type(code) is str and bool(code) for code in fallback_codes_value
                )
            )
            delivered_codes_valid = (
                isinstance(delivered_codes_value, (list, tuple))
                and all(
                    type(code) is str and bool(code)
                    for code in delivered_codes_value
                )
            )
            active_codes = (
                list(cast(Sequence[str], active_codes_value))
                if active_codes_valid
                else []
            )
            fallback_codes = (
                list(cast(Sequence[str], fallback_codes_value))
                if fallback_codes_valid
                else []
            )
            delivered_codes = (
                list(cast(Sequence[str], delivered_codes_value))
                if delivered_codes_valid
                else []
            )
            baseline_projected_value = baseline_input.get("projected_stock_codes")
            baseline_projected_codes = (
                list(cast(Sequence[str], baseline_projected_value))
                if isinstance(baseline_projected_value, (list, tuple))
                else []
            )
            baseline_codes = (
                set(active_codes)
                if is_v3_baseline and active_codes_valid
                else code_set
            )
            partition_valid = (
                not is_v3_baseline
                or (
                    bool(active_codes)
                    and active_codes_valid
                    and fallback_codes_valid
                    and delivered_codes_valid
                    # Projection order is receipt order; delivered order is
                    # recommendation rank order.  Bind the same universe here
                    # while preserving each ordered list in its own field.
                    and set(delivered_codes) == set(normalized_projected_codes)
                    and len(delivered_codes) == len(normalized_projected_codes)
                    and baseline_projected_codes == normalized_projected_codes
                    and set(active_codes).isdisjoint(fallback_codes)
                    and set(active_codes) | set(fallback_codes) == set(delivered_codes)
                    and len(set(active_codes)) == len(active_codes)
                    and len(set(fallback_codes)) == len(fallback_codes)
                    and len(set(delivered_codes)) == len(delivered_codes)
                    and baseline_input.get("delivered_count") == len(delivered_codes)
                    and baseline_input.get("model_active_count") == len(active_codes)
                    and baseline_input.get("fallback_count") == len(fallback_codes)
                    and type(baseline_input.get("model_coverage_bp")) is int
                    and baseline_input.get("model_coverage_bp")
                    == len(active_codes) * 10_000 // len(delivered_codes)
                )
            )
            upside_values = baseline_input.get("upside_probability_bp_by_symbol")
            after_cost_values = baseline_input.get(
                "after_cost_probability_bp_by_symbol"
            )
            scenario_value = baseline_input.get("cost_scenario")
            scenario_metadata = (
                scenario_value if isinstance(scenario_value, Mapping) else {}
            )
            receipt_hash = receipt_event_details.get("receipt_hash")
            projection_hash = receipt_event_details.get("projection_rows_sha256")
            cost_hash = receipt_event_details.get("cost_scenario_hash")
            after_cost_status = baseline_input.get("after_cost_baseline_status")
            scenario: RecommendationCostScenario | None = None
            scenario_valid = not is_v3_baseline
            scenario_projection_fields: dict[str, Any] = {}
            if is_v3_baseline:
                try:
                    parsed_scenario = cost_scenario_from_metadata(
                        {
                            "cost_scenario": scenario_value,
                            "cost_scenario_hash": cost_hash,
                        }
                    )
                    scenario_payload = parsed_scenario.to_dict(include_hash=True)
                    scenario = parsed_scenario
                    scenario_valid = (
                        isinstance(scenario_value, Mapping)
                        and scenario_payload == dict(scenario_value)
                        and parsed_scenario.scenario_hash == cost_hash
                        and parsed_scenario.scenario_id
                        == receipt_event_details.get("cost_scenario_id")
                        and parsed_scenario.scenario_version
                        == next(
                            (
                                projection_rows[code].get("cost_scenario_version")
                                for code in active_codes
                                if isinstance(projection_rows, Mapping)
                                and isinstance(projection_rows.get(code), Mapping)
                            ),
                            None,
                        )
                    )
                    scenario_projection_fields = {
                        "cost_scenario_id": parsed_scenario.scenario_id,
                        "cost_scenario_version": parsed_scenario.scenario_version,
                        "cost_scenario_hash": parsed_scenario.scenario_hash,
                        "cost_basis_bp": parsed_scenario.fixed_round_trip_cost_bp,
                        "cost_policy_id": parsed_scenario.policy_id,
                        "cost_policy_version": parsed_scenario.policy_version,
                        "policy_estimate_date": parsed_scenario.policy_estimate_date,
                        "research_order_amount_twd": scenario_payload[
                            "research_order_amount_twd"
                        ],
                        "research_order_quantity_shares": (
                            parsed_scenario.research_order_quantity_shares
                        ),
                        "lot_type": parsed_scenario.lot_type,
                        "instrument_type": parsed_scenario.instrument_type,
                    }
                except (KeyError, TypeError, ValueError, RecommendationCostScenarioError):
                    scenario_valid = False
            upside_map_valid = (
                isinstance(upside_values, Mapping)
                and set(upside_values) == baseline_codes
                and all(
                    type(value) is int and value == 5_000
                    for value in upside_values.values()
                )
            )
            after_cost_map_valid = (
                isinstance(after_cost_values, Mapping)
                and set(after_cost_values) == baseline_codes
                and all(
                    value is None
                    or (type(value) is int and 0 <= value <= 10_000)
                    for value in after_cost_values.values()
                )
            )
            if after_cost_map_valid and isinstance(after_cost_values, Mapping):
                after_cost_values_all = tuple(after_cost_values.values())
            else:
                after_cost_values_all = ()
            after_cost_identity_valid = (
                after_cost_status == "available"
                and type(baseline_input.get("after_cost_baseline_id")) is str
                and bool(baseline_input.get("after_cost_baseline_id"))
                and bool(after_cost_values_all)
                and all(value is not None for value in after_cost_values_all)
            ) or (
                after_cost_status == "unavailable"
                and baseline_input.get("after_cost_baseline_id") is None
                and bool(after_cost_values_all)
                and all(value is None for value in after_cost_values_all)
            )
            if is_v3_baseline:
                projection_has_active_model = (
                    isinstance(projection_rows, Mapping)
                    and set(projection_rows) == code_set
                    and all(
                        isinstance(projection_rows.get(code), Mapping)
                        and projection_rows[code].get("status") == "active_candidate"
                        and projection_rows[code].get("calibrated_probability_status")
                        == "active_effective"
                        and type(projection_rows[code].get("calibrated_probability_bp")) is int
                        and 0 <= projection_rows[code]["calibrated_probability_bp"] <= 10_000
                        and projection_rows[code].get("model_version")
                        == receipt_event_details.get("candidate_id")
                        and scenario is not None
                        and type(projection_rows[code].get("cost_basis")) is str
                        and bool(projection_rows[code].get("cost_basis"))
                        and all(
                            projection_rows[code].get(field) == expected
                            for field, expected in scenario_projection_fields.items()
                        )
                        for code in active_codes
                    )
                    and all(
                        isinstance(projection_rows.get(code), Mapping)
                        and projection_rows[code].get("status") == "rule_only"
                        and projection_rows[code].get("calibrated_probability_status")
                        == "unavailable"
                        and projection_rows[code].get("calibrated_probability_bp") is None
                        and projection_rows[code].get("after_cost_profit_probability_bp") is None
                        and not str(projection_rows[code].get("model_version") or "").strip()
                        for code in fallback_codes
                    )
                )
            else:
                projection_has_active_model = (
                    isinstance(projection_rows, Mapping)
                    and set(projection_rows) == code_set
                    and any(
                        isinstance(projection_rows.get(code), Mapping)
                        and projection_rows[code].get("status") == "active_candidate"
                        and type(projection_rows[code].get("calibrated_probability_bp")) is int
                        and 0 <= projection_rows[code]["calibrated_probability_bp"] <= 10_000
                        for code in code_set
                    )
                )
            baseline_checks = {
                "input_fields": set(baseline_input) == input_fields,
                "input_schema": baseline_schema
                in {
                    "recommendation-personal-probability-baseline-inputs.v1",
                    "recommendation-personal-probability-baseline-inputs.v3",
                },
                "result_id": baseline_input.get("result_id") == result_id,
                "decision_date": baseline_input.get("decision_date")
                == (context_as_of_date.isoformat() if context_as_of_date else None),
                "decision_at": decision_at is not None
                and baseline_decision_at == decision_at,
                "context_clock": decision_at == context_decision_at,
                "personal_mode": requested_mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
                and effective_mode == PERSONAL_CALIBRATED_PROBABILITY_MODE
                and policy_mode == PERSONAL_CALIBRATED_PROBABILITY_MODE,
                "fixed_null_benchmark": baseline_input.get("upside_baseline_kind")
                == "fixed_null_benchmark_50pct"
                and baseline_input.get("upside_baseline_id")
                == "null_benchmark_50pct_v1",
                "projected_codes": projected_codes_valid,
                "partition": partition_valid,
                "upside_values": upside_map_valid,
                "after_cost_values": after_cost_map_valid,
                "after_cost_identity": after_cost_identity_valid,
                "receipt_hashes": _is_sha256_contract_value(receipt_hash)
                and _is_sha256_contract_value(projection_hash)
                and _is_sha256_contract_value(cost_hash),
                "receipt_verified": receipt_event_details.get("persisted") is True
                and receipt_event_details.get("readback_verified") is True
                and receipt_event_details.get("identity_verified") is True
                and receipt_event_details.get("receipt_body_hash_verified") is True
                and receipt_event_details.get("error") == ""
                and receipt_event_details.get("result_id") == result_id
                and receipt_event_details.get("decision_date")
                == baseline_input.get("decision_date"),
                "active_projection": projection_has_active_model,
                "cost_scenario": scenario_valid,
            }
            failed_baseline_checks = tuple(
                name for name, passed in baseline_checks.items() if not passed
            )
            if failed_baseline_checks:
                raise ValueError(
                    "personal probability baseline 與同次 receipt/projection 不一致: "
                    + ",".join(failed_baseline_checks)
                )
            snapshot_body = {
                "schema_version": (
                    "recommendation-personal-probability-baseline-snapshot.v2"
                    if is_v3_baseline
                    else "recommendation-personal-probability-baseline-snapshot.v1"
                ),
                "result_id": result_id,
                "decision_at": canonical_decision_at,
                "decision_date": baseline_input["decision_date"],
                "receipt_hash": receipt_hash,
                "projection_rows_sha256": projection_hash,
                "cost_scenario_hash": cost_hash,
                "projected_stock_codes": list(normalized_projected_codes),
                "upside_baseline_kind": baseline_input["upside_baseline_kind"],
                "upside_baseline_id": baseline_input["upside_baseline_id"],
                "upside_probability_bp_by_symbol": dict(upside_values),
                "after_cost_baseline_status": baseline_input[
                    "after_cost_baseline_status"
                ],
                "after_cost_baseline_id": baseline_input[
                    "after_cost_baseline_id"
                ],
                "after_cost_probability_bp_by_symbol": dict(after_cost_values),
            }
            if is_v3_baseline:
                snapshot_body.update(
                    {
                        "delivered_stock_codes": list(delivered_codes),
                        "model_active_stock_codes": list(active_codes),
                        "rule_only_fallback_stock_codes": list(fallback_codes),
                        "delivered_count": baseline_input["delivered_count"],
                        "model_active_count": baseline_input["model_active_count"],
                        "fallback_count": baseline_input["fallback_count"],
                        "model_coverage_bp": baseline_input["model_coverage_bp"],
                        "cost_scenario": dict(scenario_metadata),
                    }
                )
            baseline_bytes = json.dumps(
                snapshot_body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            snapshot = {
                **snapshot_body,
                "snapshot_sha256": "sha256:" + hashlib.sha256(baseline_bytes).hexdigest(),
            }
            events.append(
                ExecutionEvent(
                    event_type="personal_probability_baseline_snapshot",
                    message=(
                        "封存同次 projector 輸入的固定上漲基準及可用 after-cost 基準；"
                        "基準值不由 receipt projection rows 回推。"
                    ),
                    occurred_at=decision_at,
                    details={
                        "schema_version": (
                            "recommendation-personal-probability-baseline-event.v2"
                            if is_v3_baseline
                            else "recommendation-personal-probability-baseline-event.v1"
                        ),
                        "result_id": result_id,
                        "decision_at": canonical_decision_at,
                        "snapshot": _safe_contract_value(
                            snapshot,
                            field_path="personal_probability_baseline_snapshot",
                        ),
                    },
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


_MARKET_DATA_PROVENANCE_SCHEMA = "recommendation-market-data-provenance.v1"


def _market_data_provenance_details(
    legacy_context: Mapping[str, Any],
    *,
    status: ExecutionStatus,
    body_result: RecommendationBodyResult | None,
    result_id: str,
    context_as_of_date: date | None,
    context_decision_at: datetime | None,
) -> Mapping[str, object] | None:
    """封存同次執行的行情日與來源識別，不宣稱可得時間或 PIT 資格。"""

    if status is not ExecutionStatus.COMPLETED or body_result is None:
        return None
    facts = body_result.context
    if facts.legacy_context.thaw() != legacy_context:
        return None
    invocation_id = body_result.invocation_id
    prefix = f"{result_id}:"
    invocation_suffix = (
        invocation_id[len(prefix) :] if invocation_id.startswith(prefix) else ""
    )
    if (
        body_result.result_id != result_id
        or facts.result_id != result_id
        or facts.invocation_id != invocation_id
        or len(invocation_suffix) != 32
        or any(character not in "0123456789abcdef" for character in invocation_suffix)
        or legacy_context.get("result_id") != result_id
    ):
        return None

    scope = legacy_context.get("fundamental_input_scope")
    if type(scope) is not str or scope not in (
        "natural_current_observation",
        "formal_pit",
    ):
        return None
    as_of = _canonical_market_date(facts.as_of_date)
    legacy_as_of = _canonical_market_date(legacy_context.get("as_of_date"))
    data_date = _canonical_market_date(legacy_context.get("data_date"))
    if (
        as_of is None
        or context_as_of_date != as_of
        or legacy_as_of != as_of
        or data_date is None
        or data_date > as_of
    ):
        return None

    source_id = facts.source_id
    fingerprint = facts.market_data_fingerprint
    if (
        type(source_id) is not str
        or not source_id.strip()
        or legacy_context.get("source_id") != source_id
        or not _is_raw_sha256_digest(fingerprint)
        or legacy_context.get("market_data_fingerprint") != fingerprint
    ):
        return None

    typed_decision_at = _datetime_value(facts.decision_at)
    if typed_decision_at != context_decision_at:
        return None
    legacy_decision_at_raw = legacy_context.get("decision_at")
    if legacy_decision_at_raw not in (None, ""):
        legacy_decision_at = _datetime_value(legacy_decision_at_raw)
        if legacy_decision_at is None or legacy_decision_at != typed_decision_at:
            return None

    return {
        "schema_version": _MARKET_DATA_PROVENANCE_SCHEMA,
        "result_id": result_id,
        "invocation_id": invocation_id,
        "scope": scope,
        "as_of_date": as_of.isoformat(),
        "data_date": data_date.isoformat(),
        "decision_at": (
            typed_decision_at.isoformat() if typed_decision_at is not None else None
        ),
        "source_id": source_id,
        "market_data_fingerprint": fingerprint,
    }


def _canonical_market_date(value: object) -> date | None:
    if type(value) is date:
        return value
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


_CURRENT_FUNDAMENTAL_LINEAGE_SCHEMA = (
    "recommendation-current-fundamental-lineage.v1"
)
_CURRENT_FUNDAMENTAL_LINEAGE_MAX_BYTES = 16 * 1024 * 1024
_CURRENT_FUNDAMENTAL_INPUT_FIELDS = frozenset(
    {
        "stock_code",
        "metric",
        "scope",
        "input_role",
        "parent_report_period",
        "period",
        "available_date",
        "available_at",
        "observed_at",
        "source_available_at",
        "availability_basis",
        "expected_market_date",
        "market_calendar_session_date",
        "market_calendar_reason_code",
        "as_of_date",
        "source",
        "source_version",
        "raw_source_version",
        "raw_source_sha256",
        "raw_response_sha256",
        "market",
        "unit",
        "period_basis",
        "basis_verified",
        "aggregate_feature_eligible",
        "formal_pit_eligible",
        "value",
    }
)
_CURRENT_FUNDAMENTAL_REQUEST_FIELDS = frozenset(
    {
        "request_id",
        "stock_code",
        "metric",
        "scope",
        "decision_date",
        "current_observation_cutoff_at",
    }
)


def _current_lineage_json_value(
    value: object, field_path: str, *, max_sequence_items: int
) -> object:
    """Freeze small current-input evidence without binary floats or ambient objects."""

    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError(f"{field_path} must be a finite Decimal")
        return str(value)
    if type(value) is datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_path} datetime must be aware")
        return value.isoformat()
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, Mapping):
        converted: dict[str, object] = {}
        for key, child in cast(Mapping[object, object], value).items():
            if type(key) is not str:
                raise TypeError(f"{field_path} mapping keys must be strings")
            converted[cast(str, key)] = _current_lineage_json_value(
                child,
                f"{field_path}.{cast(str, key)}",
                max_sequence_items=max_sequence_items,
            )
        return converted
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[object], value)
        if len(sequence) > max_sequence_items:
            raise ValueError(f"{field_path} exceeds the bounded lineage row limit")
        return tuple(
            _current_lineage_json_value(
                child,
                f"{field_path}[{index}]",
                max_sequence_items=max_sequence_items,
            )
            for index, child in enumerate(sequence)
        )
    if type(value) is float:
        raise TypeError(f"{field_path} must not persist a binary float")
    raise TypeError(f"{field_path} has unsupported lineage type {type(value).__name__}")


def _current_fundamental_lineage_event(
    legacy_context: Mapping[str, Any],
    *,
    result_id: str,
    invocation_id: str,
    decision_at: datetime | None,
    max_stocks: int,
) -> ExecutionEvent | None:
    """Persist only current-observation facts captured by this body invocation.

    Historical/fixed-cutoff callers keep their existing formal-PIT payloads and
    never gain a current-fundamental event.
    """

    if legacy_context.get("fundamental_input_scope") != "natural_current_observation":
        return None
    if type(max_stocks) is not int or max_stocks < 1:
        raise ValueError("current-fundamental lineage has an invalid universe bound")
    request_limit = 2 * max_stocks
    fact_limit = 3 * max_stocks
    if (
        legacy_context.get("result_id") != result_id
        or type(invocation_id) is not str
        or not invocation_id.strip()
    ):
        raise ValueError("current-fundamental lineage is not bound to this execution")
    cutoff_at = _datetime_value(legacy_context.get("current_observation_cutoff_at"))
    captured_decision_at = _datetime_value(legacy_context.get("decision_at"))
    if cutoff_at is None:
        raise ValueError("current-fundamental lineage lacks same-invocation aware clocks")
    if (
        decision_at is not None
        and captured_decision_at is not None
        and captured_decision_at != decision_at
    ):
        raise ValueError("current-fundamental lineage decision clock differs from its body")
    event_decision_at = decision_at or captured_decision_at

    source_id = legacy_context.get("source_id")
    market_fingerprint = legacy_context.get("market_data_fingerprint")
    data_fingerprint = legacy_context.get("data_fingerprint")
    if (
        type(source_id) is not str
        or not source_id.strip()
        or not _is_raw_sha256_digest(market_fingerprint)
        or not _is_raw_sha256_digest(data_fingerprint)
    ):
        raise ValueError("current-fundamental lineage lacks same-run source fingerprints")

    requests = _current_lineage_rows(
        legacy_context.get("fundamental_input_requests"),
        allowed_fields=_CURRENT_FUNDAMENTAL_REQUEST_FIELDS,
        field_name="fundamental_input_requests",
        max_rows=request_limit,
    )
    facts = _current_lineage_rows(
        legacy_context.get("fundamental_inputs"),
        allowed_fields=_CURRENT_FUNDAMENTAL_INPUT_FIELDS,
        field_name="fundamental_inputs",
        max_rows=fact_limit,
    )
    captured_observations = _current_lineage_rows(
        legacy_context.get("current_fundamental_observations"),
        allowed_fields=_CURRENT_FUNDAMENTAL_INPUT_FIELDS,
        field_name="current_fundamental_observations",
        max_rows=fact_limit,
    )
    facts = tuple(
        _truthful_monthly_lineage_fact(row)
        for row in _merge_current_fundamental_facts(facts, captured_observations)
    )
    if len(facts) > fact_limit:
        raise ValueError("current-fundamental facts exceed the selected universe bound")
    diagnostic_source_row_count = legacy_context.get(
        "fundamental_input_diagnostic_source_row_count", 0
    )
    diagnostic_comparator_row_count = legacy_context.get(
        "fundamental_input_diagnostic_comparator_row_count", 0
    )
    if (
        type(diagnostic_source_row_count) is not int
        or diagnostic_source_row_count < 0
        or type(diagnostic_comparator_row_count) is not int
        or diagnostic_comparator_row_count < 0
    ):
        raise ValueError("current-fundamental diagnostic source counts are invalid")
    # Monthly provider diagnostics are emitted per scanned source revision,
    # per comparator revision, plus bounded per-request resolution messages.
    # This keeps every original warning while tying the row limit to the exact
    # read-only source row counts captured by this invocation.
    diagnostic_limit = (
        2 * diagnostic_source_row_count
        + 2 * diagnostic_comparator_row_count
        + 4 * len(requests)
    )
    diagnostics_raw = legacy_context.get("fundamental_input_diagnostics", ())
    if not isinstance(diagnostics_raw, (tuple, list)):
        raise TypeError("fundamental_input_diagnostics must be a sequence")
    if len(diagnostics_raw) > diagnostic_limit or any(
        type(item) is not str for item in diagnostics_raw
    ):
        raise ValueError("fundamental_input_diagnostics is malformed or unbounded")
    diagnostics = tuple(diagnostics_raw)

    for request in requests:
        if request.get("scope") != "natural_current_observation":
            raise ValueError("current-fundamental event contains a non-current request")
    for fact in facts:
        _validate_current_fundamental_fact(fact, cutoff_at)

    details = {
        "schema_version": _CURRENT_FUNDAMENTAL_LINEAGE_SCHEMA,
        "result_id": result_id,
        "invocation_id": invocation_id,
        "scope": "natural_current_observation",
        "max_stocks": max_stocks,
        "as_of_date": str(legacy_context.get("as_of_date") or ""),
        "data_date": str(legacy_context.get("data_date") or ""),
        "expected_market_date": legacy_context.get("expected_market_date"),
        "market_calendar_status": legacy_context.get("market_calendar_status"),
        "market_calendar_reason_code": legacy_context.get(
            "market_calendar_reason_code"
        ),
        "decision_at": (
            event_decision_at.astimezone(timezone.utc).isoformat()
            if event_decision_at is not None
            else None
        ),
        "current_observation_cutoff_at": cutoff_at.astimezone(
            timezone.utc
        ).isoformat(),
        "source_id": source_id,
        "market_data_fingerprint": market_fingerprint,
        "data_fingerprint": data_fingerprint,
        "requests": requests,
        "facts": facts,
        "diagnostics": diagnostics,
        "diagnostic_source_row_count": diagnostic_source_row_count,
        "diagnostic_comparator_row_count": diagnostic_comparator_row_count,
    }
    safe_details = _current_lineage_json_value(
        details,
        "current_fundamental_lineage",
        max_sequence_items=max(request_limit, fact_limit, diagnostic_limit),
    )
    if not isinstance(safe_details, Mapping):
        raise TypeError("current-fundamental lineage event details are not a mapping")
    serialized = json.dumps(
        safe_details,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) > _CURRENT_FUNDAMENTAL_LINEAGE_MAX_BYTES:
        raise ValueError("current-fundamental lineage event exceeds its byte limit")
    return ExecutionEvent(
        event_type="current_fundamental_lineage",
        message="Same-invocation natural current fundamental inputs and diagnostics.",
        occurred_at=event_decision_at or cutoff_at,
        details=safe_details,
    )


def _current_lineage_rows(
    value: object,
    *,
    allowed_fields: frozenset[str],
    field_name: str,
    max_rows: int,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a sequence")
    if len(value) > max_rows:
        raise ValueError(f"{field_name} exceeds the bounded lineage row limit")
    rows: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"{field_name}[{index}] must be a mapping")
        if item.get("scope") != "natural_current_observation":
            continue
        stock_code = item.get("stock_code")
        if type(stock_code) is not str or not stock_code.strip():
            raise ValueError(f"{field_name}[{index}] lacks stock_code")
        copied: dict[str, object] = {}
        for key in sorted(allowed_fields):
            if key in item:
                copied[key] = _current_lineage_json_value(
                    item[key],
                    f"{field_name}[{index}].{key}",
                    max_sequence_items=max_rows,
                )
        rows.append(copied)
    return tuple(rows)


def _truthful_monthly_lineage_fact(
    fact: Mapping[str, object],
) -> Mapping[str, object]:
    """Distinguish a source-version content hash from original response bytes."""

    if fact.get("metric") != "monthly_revenue":
        return fact
    copied = dict(fact)
    source_version = str(copied.get("source_version") or "")
    raw_source_version = str(copied.get("raw_source_version") or "")
    if not raw_source_version:
        raw_source_version = _extract_monthly_raw_source_version(source_version)
    source_hash = _extract_monthly_source_content_hash(raw_source_version)
    declared_hash = copied.pop("raw_source_sha256", None)
    if declared_hash is not None and declared_hash != source_hash:
        raise ValueError("monthly source version content hash does not match its token")
    copied["raw_source_version"] = raw_source_version
    copied["source_version_content_sha256"] = source_hash
    copied["source_version_content_hash_basis"] = (
        "decoded_html_reencoded_utf8"
    )
    copied["verified_response_body_bytes_sha256"] = None
    copied["response_body_bytes_hash_status"] = (
        "not_persisted_on_current_observation_row"
    )
    return copied


def _extract_monthly_raw_source_version(source_version: str) -> str:
    marker = ":raw:"
    if marker not in source_version:
        raise ValueError("monthly lineage source version lacks a raw-source token")
    raw_token = source_version.split(marker, 1)[1]
    for terminator in (":derived:sha256:", ":same-report-yoy-baseline:"):
        if terminator in raw_token:
            raw_token = raw_token.split(terminator, 1)[0]
    if not raw_token:
        raise ValueError("monthly lineage raw-source token is empty")
    return raw_token


def _extract_monthly_source_content_hash(raw_source_version: str) -> str:
    import re

    match = re.search(r"(?:-sha256-|:sha256:)([0-9a-f]{64})$", raw_source_version)
    if match is None:
        raise ValueError("monthly lineage source-version content hash is invalid")
    return match.group(1)


def _merge_current_fundamental_facts(
    projected_facts: Sequence[Mapping[str, object]],
    captured_observations: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Include only projected inputs and the latest same-report source rows."""

    latest_period_by_stock: dict[str, str] = {}
    for observation in captured_observations:
        if observation.get("metric") != "monthly_revenue":
            continue
        if observation.get("input_role") != "reported_period_value":
            continue
        code = str(observation.get("stock_code") or "")
        period = str(observation.get("period") or "")
        if code and period:
            latest_period_by_stock[code] = max(
                period, latest_period_by_stock.get(code, "")
            )

    selected_observations = tuple(
        observation
        for observation in captured_observations
        if observation.get("metric") != "monthly_revenue"
        or (
            observation.get("input_role") == "reported_period_value"
            and observation.get("period")
            == latest_period_by_stock.get(str(observation.get("stock_code") or ""))
        )
        or (
            observation.get("input_role")
            == "same_report_prior_year_comparison_baseline"
            and observation.get("parent_report_period")
            == latest_period_by_stock.get(str(observation.get("stock_code") or ""))
        )
    )
    merged: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
    for row in (*selected_observations, *projected_facts):
        key = (
            str(row.get("stock_code") or ""),
            str(row.get("metric") or ""),
            str(row.get("period") or ""),
            str(row.get("source_version") or ""),
            str(row.get("input_role") or ""),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(row)
            continue
        for name, value in row.items():
            if name in existing and existing[name] != value:
                raise ValueError(
                    "current-fundamental projected fact conflicts with captured source row: "
                    f"{key[0]}:{key[1]}:{key[2]}:{name}"
                )
            existing[name] = value
    return tuple(
        merged[key]
        for key in sorted(merged)
    )


def _validate_current_fundamental_fact(
    fact: Mapping[str, object], cutoff_at: datetime
) -> None:
    metric = fact.get("metric")
    if metric not in {"pe", "monthly_revenue"}:
        raise ValueError("current-fundamental event contains an unsupported metric")
    if fact.get("formal_pit_eligible") is not False:
        raise ValueError("natural current fundamental facts cannot be formal PIT")
    for field_name in ("available_at",):
        field_clock = _datetime_value(fact.get(field_name))
        if field_clock is None or field_clock > cutoff_at:
            raise ValueError(f"current-fundamental {field_name} is missing or after freeze")
    for field_name in ("observed_at", "source_available_at"):
        raw_clock = fact.get(field_name)
        if raw_clock is None:
            continue
        field_clock = _datetime_value(raw_clock)
        if field_clock is None or field_clock > cutoff_at:
            raise ValueError(f"current-fundamental {field_name} is invalid or after freeze")
    for field_name in ("source", "source_version", "market"):
        if type(fact.get(field_name)) is not str or not str(fact[field_name]).strip():
            raise ValueError(f"current-fundamental {field_name} is missing")
    if metric == "pe":
        raw_hash = fact.get("raw_response_sha256")
        if not _is_raw_sha256_digest(raw_hash):
            raise ValueError("current PE raw-response hash is invalid")
        if type(fact.get("value")) is not str or type(fact.get("as_of_date")) is not str:
            raise ValueError("current PE value/date must be captured as strings")
        if type(fact.get("expected_market_date")) is not str:
            raise ValueError("current PE expected market date is missing")
        if fact.get("as_of_date") != fact.get("expected_market_date"):
            raise ValueError("current PE capture date differs from the report quote date")
    else:
        source_hash = fact.get("source_version_content_sha256")
        if not _is_raw_sha256_digest(source_hash):
            raise ValueError("current monthly source-version content hash is invalid")
        if fact.get("source_version_content_hash_basis") != "decoded_html_reencoded_utf8":
            raise ValueError("current monthly source-version hash semantics are unclear")
        if fact.get("verified_response_body_bytes_sha256") is not None:
            raise ValueError("current monthly response-byte hash was not persisted")
        if fact.get("response_body_bytes_hash_status") != "not_persisted_on_current_observation_row":
            raise ValueError("current monthly response-byte hash status is unclear")
        raw_source_version = fact.get("raw_source_version")
        if type(raw_source_version) is not str or _extract_monthly_source_content_hash(raw_source_version) != source_hash:
            raise ValueError("current monthly raw-source token and content hash differ")
        for field_name in ("value", "period", "unit", "period_basis"):
            if type(fact.get(field_name)) is not str:
                raise ValueError(f"current monthly {field_name} must be a string")
        if fact.get("unit") != "TWD" or fact.get("period_basis") != "monthly_flow":
            raise ValueError("current monthly fact unit/basis is not verified")
        if fact.get("basis_verified") is not True or fact.get("aggregate_feature_eligible") is not False:
            raise ValueError("current monthly fact basis/aggregate flags are unsafe")


def _is_raw_sha256_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _company_registry_contract_hash_matches(
    contract: Mapping[str, Any],
) -> bool:
    """以 company registry 使用的 canonical JSON bytes 核對來源契約 hash。"""

    declared = contract.get("source_contract_sha256")
    if (
        type(declared) is not str
        or len(declared) != 71
        or not declared.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in declared[7:])
    ):
        return False
    body = dict(contract)
    body.pop("source_contract_sha256", None)
    try:
        canonical = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    return declared == "sha256:" + hashlib.sha256(canonical).hexdigest()


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


def _is_sha256_contract_value(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


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
