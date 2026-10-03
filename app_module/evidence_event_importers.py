from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Mapping, Protocol

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    DecisionDeskRiskPromptSummary,
    PortfolioAlertSummary,
    WatchlistTriggerSummary,
)
from app_module.evidence_event_dtos import EvidenceDataQuality, EvidenceEventType
from app_module.evidence_event_importer_dtos import (
    EvidenceCaptureRequest,
    EvidenceImportDiagnostic,
    EvidenceImportResult,
)
from app_module.evidence_importer_support import (
    date_text as _date_text,
    normalize_quality as _quality,
    score_bp as _score_bp,
    string_tuple as _tuple,
)
from app_module.recommendation.contracts import (
    ExecutionStatus,
    QualityStatus,
)
from app_module.recommendation.queries import RecommendationExecutionReadModel
from app_module.recommendation.persistence import ExecutionPersistenceError
from app_module.saved_recommendation_queries import (
    execution_result_config,
    select_latest_saved_recommendation,
    verified_saved_calibration_projections,
)


class EvidenceImporter(Protocol):
    source_name: str

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult: ...


def _legacy_metadata_date(value: Any) -> Any:
    """將 legacy recommendation 的具名日期欄位穩定投影為 ISO 日期。"""
    if type(value) is date:
        return value.isoformat()
    return value


def _legacy_metadata_datetime(value: Any) -> Any:
    """將 legacy recommendation 的具名時間欄位投影為保留原時區的 ISO timestamp。"""
    if type(value) is datetime:
        return value.isoformat()
    return value


class UnsupportedEvidenceImporter:
    def __init__(self, source_name: str, reason: str = "source provider is not configured") -> None:
        self.source_name = source_name
        self.reason = reason

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        return EvidenceImportResult(
            source_name=self.source_name,
            decision_date=request.decision_date_text,
            diagnostics=(
                EvidenceImportDiagnostic(
                    code="source_unsupported",
                    message=self.reason,
                    source_name=self.source_name,
                    severity="warning",
                ),
            ),
        )


class MissingSnapshotEvidenceImporter:
    def __init__(self, source_name: str, reason: str = "durable decision desk snapshot not found") -> None:
        self.source_name = source_name
        self.reason = reason

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        return EvidenceImportResult(
            source_name=self.source_name,
            decision_date=request.decision_date_text,
            diagnostics=(
                EvidenceImportDiagnostic(
                    code="source_missing_snapshot",
                    message=self.reason,
                    source_name=self.source_name,
                    severity="warning",
                    metadata={"suggested_command": "python scripts/capture_decision_desk_snapshot.py --decision-date <YYYY-MM-DD> --confirm"},
                ),
            ),
        )


class RecommendationEvidenceImporter:
    source_name = "recommendation"

    def __init__(self, queries: Any) -> None:
        self.queries = queries

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        read_model, latest_selection_diagnostic = self._load_result(request)
        if read_model is None:
            if latest_selection_diagnostic:
                is_query_failure = latest_selection_diagnostic.startswith(
                    "recommendation_query_failure:"
                )
                return EvidenceImportResult(
                    source_name=self.source_name,
                    decision_date=request.decision_date_text,
                    diagnostics=(
                        EvidenceImportDiagnostic(
                            code=latest_selection_diagnostic,
                            message=(
                                "推薦結果 query 驗證失敗；拒絕使用未驗證資料。"
                                if is_query_failure
                                else "canonical/legacy mixed latest timestamp 不完整或不明確；拒絕猜測選取結果。"
                            ),
                            source_name=self.source_name,
                        ),
                    ),
                )
            return EvidenceImportResult(
                source_name=self.source_name,
                decision_date=request.decision_date_text,
                diagnostics=(
                    EvidenceImportDiagnostic(
                        code="source_missing",
                        message="recommendation result not found",
                        source_name=self.source_name,
                    ),
                ),
            )

        result = self._consumer_result(read_model)
        if result is None:
            return EvidenceImportResult(
                source_name=self.source_name,
                decision_date=request.decision_date_text,
                diagnostics=(
                    EvidenceImportDiagnostic(
                        code="source_unsupported_execution",
                        message="保存 execution 沒有可讀的 completed decision；未使用其他 decoder。",
                        source_name=self.source_name,
                    ),
                ),
            )

        if request.decision_date_text:
            decision_date = request.decision_date_text
        elif read_model.execution is not None:
            if result.as_of_date is None:
                return EvidenceImportResult(
                    source_name=self.source_name,
                    decision_date=None,
                    diagnostics=(
                        EvidenceImportDiagnostic(
                            code="source_missing_as_of_date",
                            message="execution 未保存 as_of_date，不能以 created_at 補造決策日。",
                            source_name=self.source_name,
                        ),
                    ),
                )
            decision_date = result.as_of_date.isoformat()
        else:
            decision_date = _date_text(getattr(result, "created_at", None))
        config = dict(getattr(result, "config", {}) or {})
        profile_id = str(config.get("profile_id") or config.get("selected_profile") or "")
        profile_version = str(config.get("profile_version") or "")
        identity = self._identity_payload(result)
        saved_calibrations = verified_saved_calibration_projections(read_model)
        payloads: list[dict[str, Any]] = []
        diagnostics: list[EvidenceImportDiagnostic] = []

        for index, rec in enumerate(getattr(result, "recommendations", ())):
            symbol = str(getattr(rec, "stock_code", "")).strip()
            if request.symbol and symbol != str(request.symbol).strip():
                continue
            if not symbol:
                diagnostics.append(
                    EvidenceImportDiagnostic(
                        code="event_invalid_symbol",
                        message="recommendation row has empty stock_code",
                        source_name=self.source_name,
                    )
                )
                continue

            warnings = []
            percentile = getattr(rec, "score_percentile_bp", None)
            threshold_value = getattr(rec, "threshold_mode", None)
            threshold_mode = (
                str(threshold_value or "fixed").strip().lower()
                if read_model.legacy_result is not None
                else str(threshold_value).strip().lower() if threshold_value is not None else ""
            )
            if percentile is None and threshold_mode != "fixed":
                warnings.append("score_percentile_missing")
            payloads.append(
                {
                    "event_date": decision_date,
                    "decision_date": decision_date,
                    "symbol": symbol,
                    "event_type": EvidenceEventType.RECOMMENDATION_INCLUDED,
                    "event_family": "recommendation",
                    "source_type": "recommendation_result",
                    "source_id": str(getattr(result, "result_id", "")),
                    "source_snapshot_id": str(getattr(result, "result_id", "")),
                    "profile_id": profile_id,
                    "reason_codes": _tuple(getattr(rec, "recommendation_reasons", "")),
                    "risk_codes": (),
                    "score_bp": _score_bp(getattr(rec, "total_score", None)),
                    "score_percentile_bp": percentile,
                    "regime": getattr(result, "regime", None),
                    "sector": getattr(rec, "industry", None),
                    "data_quality": EvidenceDataQuality.OBSERVED,
                    "warnings": tuple(warnings),
                    "as_of_date": decision_date,
                    "available_date": decision_date,
                    "source_version": "recommendation_importer_v1",
                    "metadata": {
                        "result_name": str(getattr(result, "result_name", "")),
                        "profile_version": profile_version,
                        "stock_name": str(getattr(rec, "stock_name", "")),
                        "threshold_mode": threshold_mode,
                        "eligible_universe_size": getattr(rec, "eligible_universe_size", None),
                        "eligible_universe_date": _legacy_metadata_date(
                            getattr(rec, "eligible_universe_date", None)
                        ),
                        "ranking_method": getattr(rec, "ranking_method", None),
                        "recommendation_rank": index + 1,
                        "source_created_at": _legacy_metadata_datetime(
                            getattr(result, "created_at", None)
                        ),
                        **identity["metadata"],
                        # V4.1 只保存決策當下已存在的 component score；
                        # 這些欄位供後續 price/volume ablation 使用，不回填歷史事件。
                        "indicator_score_bp": _score_bp(getattr(rec, "indicator_score", None)),
                        "pattern_score_bp": _score_bp(getattr(rec, "pattern_score", None)),
                        "volume_score_bp": _score_bp(getattr(rec, "volume_score", None)),
                        **(
                            {"saved_calibration_projection": saved_calibrations[symbol].to_dict()}
                            if symbol in saved_calibrations
                            else {}
                        ),
                    },
                    **identity["fields"],
                }
            )
            if request.limit is not None and len(payloads) >= request.limit:
                break

        matrix_payloads = self._screening_matrix_payloads(result, request, decision_date)
        if matrix_payloads:
            for payload in matrix_payloads:
                if request.limit is not None and len(payloads) >= request.limit:
                    break
                payloads.append(payload)
        else:
            diagnostics.append(
                EvidenceImportDiagnostic(
                    code="source_missing_screening_matrix",
                    message="saved recommendation does not contain screening matrix evidence",
                    source_name=self.source_name,
                )
            )

        if request.capture_exclusion_payloads:
            exclusion_payloads = self._exclusion_payloads(result, request, decision_date)
            if exclusion_payloads:
                for payload in exclusion_payloads:
                    if request.limit is not None and len(payloads) >= request.limit:
                        break
                    payloads.append(payload)
            else:
                diagnostics.append(
                    EvidenceImportDiagnostic(
                        code="source_missing_exclusion_payload",
                        message="saved recommendation does not contain why-not/liquidity exclusion payloads",
                        source_name=self.source_name,
                    )
                )

        return EvidenceImportResult(
            source_name=self.source_name,
            decision_date=decision_date,
            event_payloads=tuple(payloads),
            diagnostics=tuple(diagnostics),
        )

    def _consumer_result(self, read_model: RecommendationExecutionReadModel) -> Any | None:
        if read_model.legacy_result is not None:
            return read_model.legacy_result
        execution = read_model.execution
        if execution is None or execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
            return None
        config = execution_result_config(execution)
        context = execution.context
        run_context: dict[str, Any] = {}
        if context.as_of_date is not None:
            run_context["as_of_date"] = context.as_of_date.isoformat()
        if context.profile_ref is not None:
            run_context["profile_id"] = context.profile_ref.reference_id
            if context.profile_ref.version is not None:
                run_context["profile_version"] = context.profile_ref.version
        source_ids = tuple(dict.fromkeys(item.source_id for item in context.source_refs))
        if len(source_ids) == 1:
            run_context["source_id"] = source_ids[0]
        snapshot_ids = tuple(dict.fromkeys(item.snapshot_id for item in context.source_refs if item.snapshot_id))
        if len(snapshot_ids) == 1:
            run_context["source_snapshot_id"] = snapshot_ids[0]
        if context.strategy_identity is not None:
            strategy_identity = context.strategy_identity
            for name in ("strategy_version_id", "strategy_config_id", "strategy_config_hash", "strategy_config_schema"):
                value = getattr(strategy_identity, name)
                if value is not None:
                    run_context[name] = value
            if strategy_identity.strategy_config_spec_json is not None:
                run_context["strategy_config"] = json.loads(strategy_identity.strategy_config_spec_json)
        if context.universe_identity is not None:
            universe_identity = context.universe_identity
            for name in ("universe_id", "universe_hash", "universe_identity_schema"):
                value = getattr(universe_identity, name)
                if value is not None:
                    run_context[name] = value
            if universe_identity.policy is not None:
                for name in ("universe_policy_id", "universe_policy_hash", "universe_policy_schema"):
                    value = getattr(universe_identity.policy, name)
                    if value is not None:
                        run_context[name] = value
                if universe_identity.policy.universe_policy_spec_json is not None:
                    run_context["universe_policy_spec"] = json.loads(universe_identity.policy.universe_policy_spec_json)
            if universe_identity.snapshot is not None:
                for name in (
                    "universe_snapshot_id",
                    "universe_snapshot_hash",
                    "universe_snapshot_schema",
                    "universe_snapshot_source_provider_id",
                    "universe_snapshot_selected_codes_hash",
                ):
                    value = getattr(universe_identity.snapshot, name)
                    if value is not None:
                        run_context[name] = value
                if universe_identity.snapshot.universe_snapshot_spec_json is not None:
                    run_context["universe_snapshot_spec"] = json.loads(universe_identity.snapshot.universe_snapshot_spec_json)
        if context.evidence_identity is not None:
            evidence_identity = context.evidence_identity
            for name in (
                "cost_model_id",
                "benchmark_id",
                "industry_benchmark_id",
                "horizon_days",
                "evidence_tier",
                "return_basis",
            ):
                value = getattr(evidence_identity, name)
                if value is not None:
                    run_context[name] = value

        calibrations = verified_saved_calibration_projections(read_model)
        item_rows = []
        for item in execution.decision.items:
            calibration = calibrations.get(item.stock_code)
            item_rows.append(
                SimpleNamespace(
                    stock_code=item.stock_code,
                    stock_name=item.stock_name or "",
                    recommendation_reasons=(
                        "; ".join(item.reasons)
                        if item.reasons
                        else item.reason_text or ""
                    ),
                    total_score=item.rule_score,
                    score_percentile_bp=(
                        calibration.ranking_percentile_bp
                        if calibration is not None
                        else item.score_percentile_bp
                    ),
                    threshold_mode=item.threshold_mode,
                    industry=item.industry,
                    eligible_universe_size=item.eligible_universe_size,
                    eligible_universe_date=(
                        item.eligible_universe_date.isoformat()
                        if item.eligible_universe_date is not None
                        else None
                    ),
                    ranking_method=item.ranking_method,
                    indicator_score=item.indicator_score,
                    pattern_score=item.pattern_score,
                    volume_score=item.volume_score,
                )
            )

        screening_rows: list[dict[str, Any]] = []
        why_not_rows: list[dict[str, Any]] = []
        liquidity_rows: list[dict[str, Any]] = []
        quality = _quality_for_execution(execution.quality.status)
        for assessment in execution.decision.assessments:
            filter_outcomes = assessment.filter_outcomes or {}
            for filter_id, outcome in filter_outcomes.items():
                outcome_evidence: Mapping[str, object] = outcome.evidence or {}
                status = "pass" if outcome.passed is True else "fail" if outcome.passed is False else "missing"
                row: dict[str, Any] = {
                    "stock_code": assessment.stock_code,
                    "status": status,
                    "quality": quality if status != "missing" else EvidenceDataQuality.MISSING.value,
                    "stage": filter_id,
                    "reason_codes": (outcome.reason,) if outcome.reason else (),
                    "evidence": dict(outcome_evidence),
                }
                for name in ("threshold_name", "observed_value", "required_value", "score_percentile_bp", "eligible_universe_size", "threshold_mode"):
                    if name in outcome_evidence:
                        row[name] = outcome_evidence[name]
                screening_rows.append(row)
            for negative in assessment.negative_evidence:
                negative_details: Mapping[str, object] = negative.details or {}
                row = {
                    "stock_code": assessment.stock_code,
                    "exclusion_reason_codes": (negative.reason,),
                    "quality": quality,
                    "evidence_id": negative.evidence_id,
                    "source_refs": tuple(
                        {
                            "source_id": ref.source_id,
                            "revision": ref.revision,
                            "snapshot_id": ref.snapshot_id,
                        }
                        for ref in negative.source_refs
                    ),
                    "observed_at": negative.observed_at.isoformat() if negative.observed_at else None,
                    "details": dict(negative_details),
                    **dict(negative_details),
                }
                why_not_rows.append(row)
            liquidity = assessment.liquidity
            if liquidity is not None and liquidity.acceptable is False:
                liquidity_rows.append(
                    {
                        "stock_code": assessment.stock_code,
                        "exclusion_reason_codes": liquidity.reasons,
                        "quality": quality,
                        "missing_data": liquidity.missing_data,
                        "observations": dict(liquidity.observations or {}),
                    }
                )
        if execution.quality.status in (QualityStatus.UNKNOWN, QualityStatus.UNAVAILABLE):
            exclusion_quality = EvidenceDataQuality.MISSING.value
        else:
            exclusion_quality = quality
        return SimpleNamespace(
            result_id=execution.result_id,
            result_name=read_model.label or "",
            config=config,
            recommendations=tuple(item_rows),
            regime=execution.decision.regime,
            created_at=(execution.context.created_at.isoformat() if execution.context.created_at else None),
            as_of_date=execution.context.as_of_date,
            screening_matrix_json=screening_rows,
            why_not_payload_json=why_not_rows,
            liquidity_gate_payload_json=liquidity_rows,
            exclusion_quality=exclusion_quality,
            exclusion_warnings_json=tuple(execution.context.warnings) + tuple(execution.quality.warnings),
            run_context=run_context,
        )

    def _screening_matrix_payloads(
        self,
        result: Any,
        request: EvidenceCaptureRequest,
        decision_date: str,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for row in self._payload_rows(getattr(result, "screening_matrix_json", ())):
            payload = self._screening_matrix_payload(
                result=result,
                row=row,
                request=request,
                decision_date=decision_date,
            )
            if payload is not None:
                payloads.append(payload)
        return payloads

    def _screening_matrix_payload(
        self,
        *,
        result: Any,
        row: Mapping[str, Any],
        request: EvidenceCaptureRequest,
        decision_date: str,
    ) -> dict[str, Any] | None:
        symbol = str(row.get("stock_code") or row.get("symbol") or row.get("code") or "").strip()
        if request.symbol and symbol != str(request.symbol).strip():
            return None
        if not symbol:
            return None
        status = str(row.get("status") or "missing").strip().lower()
        event_type = self._screening_event_type(status)
        reason_codes = _tuple(row.get("reason_codes") or row.get("exclusion_reason_codes") or row.get("reasons"))
        warnings = _tuple(row.get("warnings"))
        quality = str(row.get("quality") or self._quality_for_screening_status(status))
        metadata = {
            "screening_status": status,
            "stage": row.get("stage"),
            "stock_name": row.get("stock_name"),
            "threshold_name": row.get("threshold_name"),
            "observed_value": row.get("observed_value"),
            "required_value": row.get("required_value"),
            "total_score": row.get("total_score"),
            "score_percentile_bp": row.get("score_percentile_bp"),
            "eligible_universe_size": row.get("eligible_universe_size"),
            "threshold_mode": row.get("threshold_mode"),
            "source_result_id": str(getattr(result, "result_id", "")),
        }
        if "evidence" in row:
            metadata["evidence"] = row["evidence"]
        identity = self._identity_payload(result)
        metadata.update(identity["metadata"])
        payload: dict[str, Any] = {
            "event_date": decision_date,
            "decision_date": decision_date,
            "symbol": symbol,
            "event_type": event_type,
            "event_family": "screening_matrix",
            "source_type": "recommendation_result_screening_matrix",
            "source_id": str(getattr(result, "result_id", "")),
            "source_snapshot_id": str(getattr(result, "result_id", "")),
            "reason_codes": reason_codes or (status,),
            "why_not_codes": reason_codes if status in {"fail", "degraded", "skipped", "missing"} else (),
            "risk_codes": reason_codes if status in {"degraded", "missing"} else (),
            "score_bp": row.get("score_bp"),
            "score_percentile_bp": row.get("score_percentile_bp"),
            "regime": getattr(result, "regime", None),
            "sector": row.get("sector") or row.get("industry"),
            "liquidity_state": row.get("liquidity_state"),
            "data_quality": _quality(quality),
            "warnings": warnings,
            "as_of_date": decision_date,
            "available_date": decision_date,
            "source_version": "recommendation_screening_matrix_importer_v1",
            "metadata": metadata,
            **identity["fields"],
        }
        return payload

    def _screening_event_type(self, status: str) -> EvidenceEventType:
        mapping = {
            "pass": EvidenceEventType.SCREENING_MATRIX_PASS,
            "fail": EvidenceEventType.SCREENING_MATRIX_FAIL,
            "degraded": EvidenceEventType.SCREENING_MATRIX_DEGRADED,
            "skipped": EvidenceEventType.SCREENING_MATRIX_SKIPPED,
            "missing": EvidenceEventType.SCREENING_MATRIX_MISSING,
        }
        return mapping.get(status, EvidenceEventType.SCREENING_MATRIX_MISSING)

    def _quality_for_screening_status(self, status: str) -> str:
        if status == "pass" or status == "fail":
            return EvidenceDataQuality.OBSERVED.value
        if status == "missing":
            return EvidenceDataQuality.MISSING.value
        return EvidenceDataQuality.DEGRADED.value

    def _exclusion_payloads(
        self,
        result: Any,
        request: EvidenceCaptureRequest,
        decision_date: str,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        result_warnings = _tuple(getattr(result, "exclusion_warnings_json", ()) or ())
        default_quality = str(getattr(result, "exclusion_quality", None) or EvidenceDataQuality.DEGRADED.value)
        for row in self._payload_rows(getattr(result, "why_not_payload_json", ())):
            payload = self._exclusion_payload(
                result=result,
                row=row,
                request=request,
                decision_date=decision_date,
                event_type=EvidenceEventType.WHY_NOT_EXCLUDED,
                payload_kind="why_not",
                default_quality=default_quality,
                result_warnings=result_warnings,
            )
            if payload is not None:
                payloads.append(payload)
        for row in self._payload_rows(getattr(result, "liquidity_gate_payload_json", ())):
            payload = self._exclusion_payload(
                result=result,
                row=row,
                request=request,
                decision_date=decision_date,
                event_type=EvidenceEventType.LIQUIDITY_GATE_EXCLUDED,
                payload_kind="liquidity_gate",
                default_quality=default_quality,
                result_warnings=result_warnings,
            )
            if payload is not None:
                payloads.append(payload)
        return payloads

    def _payload_rows(self, value: Any) -> tuple[Mapping[str, Any], ...]:
        if value is None:
            return ()
        if isinstance(value, Mapping):
            rows = value.get("items") or value.get("excluded_candidates") or value.get("rows") or []
            if isinstance(rows, Mapping):
                return (rows,)
            return tuple(row for row in rows if isinstance(row, Mapping))
        return tuple(row for row in value if isinstance(row, Mapping))

    def _exclusion_payload(
        self,
        *,
        result: Any,
        row: Mapping[str, Any],
        request: EvidenceCaptureRequest,
        decision_date: str,
        event_type: EvidenceEventType,
        payload_kind: str,
        default_quality: str,
        result_warnings: tuple[str, ...],
    ) -> dict[str, Any] | None:
        symbol = str(row.get("stock_code") or row.get("symbol") or row.get("code") or "").strip()
        if request.symbol and symbol != str(request.symbol).strip():
            return None
        if not symbol:
            return None
        reason_codes = _tuple(row.get("exclusion_reason_codes") or row.get("reason_codes") or row.get("reasons"))
        warnings = tuple(result_warnings) + _tuple(row.get("warnings"))
        quality = str(row.get("quality") or default_quality or EvidenceDataQuality.DEGRADED.value)
        threshold_name = row.get("threshold_name")
        observed_value = row.get("observed_value")
        required_value = row.get("required_value")
        why_not_codes = reason_codes if event_type == EvidenceEventType.WHY_NOT_EXCLUDED else ()
        risk_codes = reason_codes if event_type == EvidenceEventType.LIQUIDITY_GATE_EXCLUDED else ()
        identity = self._identity_payload(result)
        payload: dict[str, Any] = {
            "event_date": decision_date,
            "decision_date": decision_date,
            "symbol": symbol,
            "event_type": event_type,
            "event_family": "recommendation_exclusion",
            "source_type": f"recommendation_result_{payload_kind}",
            "source_id": str(getattr(result, "result_id", "")),
            "source_snapshot_id": str(getattr(result, "result_id", "")),
            "reason_codes": reason_codes,
            "why_not_codes": why_not_codes,
            "risk_codes": risk_codes,
            "data_quality": _quality(quality),
            "warnings": warnings,
            "as_of_date": decision_date,
            "available_date": decision_date,
            "source_version": "recommendation_exclusion_importer_v1",
            "metadata": {
                "exclusion_reason_codes": list(reason_codes),
                "threshold_name": threshold_name,
                "observed_value": observed_value,
                "required_value": required_value,
                "quality": quality,
                "warnings": list(warnings),
                "source_result_id": str(getattr(result, "result_id", "")),
                "exclusion_payload_kind": payload_kind,
                **identity["metadata"],
            },
            **identity["fields"],
        }
        for name in ("evidence_id", "source_refs", "observed_at", "details", "missing_data", "observations"):
            if name in row:
                payload["metadata"][name] = row[name]
        return payload

    def _identity_payload(self, result: Any) -> dict[str, dict[str, Any]]:
        """Read only explicitly declared V4 identity; never infer missing fields."""

        mappings = self._identity_mappings(result)
        strategy_version_id = self._first_text(mappings, ("strategy_version_id", "strategy_version"))
        strategy_config_id = self._first_text(mappings, ("strategy_config_id",))
        strategy_config_hash = self._first_text(mappings, ("strategy_config_hash",))
        strategy_config_schema = self._first_text(mappings, ("strategy_config_schema",))
        cost_model_id = self._first_text(mappings, ("cost_model_id",))
        benchmark_id = self._first_text(mappings, ("benchmark_id",))
        industry_benchmark_id = self._first_text(mappings, ("industry_benchmark_id",))
        universe_id = self._first_text(mappings, ("universe_id",))
        universe_hash = self._first_text(mappings, ("universe_hash",))
        universe_identity_schema = self._first_text(mappings, ("universe_identity_schema",))
        universe_policy_id = self._first_text(mappings, ("universe_policy_id",))
        universe_policy_hash = self._first_text(mappings, ("universe_policy_hash",))
        universe_policy_schema = self._first_text(mappings, ("universe_policy_schema",))
        universe_snapshot_id = self._first_text(mappings, ("universe_snapshot_id",))
        universe_snapshot_hash = self._first_text(mappings, ("universe_snapshot_hash",))
        universe_snapshot_schema = self._first_text(mappings, ("universe_snapshot_schema",))
        universe_snapshot_source_provider_id = self._first_text(
            mappings, ("universe_snapshot_source_provider_id",)
        )
        universe_snapshot_selected_codes_hash = self._first_text(
            mappings, ("universe_snapshot_selected_codes_hash",)
        )
        horizon_days = self._first_positive_integer(mappings, ("horizon_days", "expected_horizon_days"))
        evidence_tier = self._first_text(mappings, ("evidence_tier",))
        return_basis = self._first_text(mappings, ("return_basis",))

        fields = {
            key: value
            for key, value in {
                "strategy_version_id": strategy_version_id,
                "cost_model_id": cost_model_id,
                "benchmark_id": benchmark_id,
                "industry_benchmark_id": industry_benchmark_id,
            }.items()
            if value
        }
        metadata = {
            key: value
            for key, value in {
                "strategy_version_id": strategy_version_id,
                "cost_model_id": cost_model_id,
                "benchmark_id": benchmark_id,
                "industry_benchmark_id": industry_benchmark_id,
                "strategy_config_id": strategy_config_id,
                "strategy_config_hash": strategy_config_hash,
                "strategy_config_schema": strategy_config_schema,
                "universe_id": universe_id,
                "universe_hash": universe_hash,
                "universe_identity_schema": universe_identity_schema,
                "universe_policy_id": universe_policy_id,
                "universe_policy_hash": universe_policy_hash,
                "universe_policy_schema": universe_policy_schema,
                "universe_snapshot_id": universe_snapshot_id,
                "universe_snapshot_hash": universe_snapshot_hash,
                "universe_snapshot_schema": universe_snapshot_schema,
                "universe_snapshot_source_provider_id": universe_snapshot_source_provider_id,
                "universe_snapshot_selected_codes_hash": universe_snapshot_selected_codes_hash,
                "horizon_days": horizon_days,
                "evidence_tier": evidence_tier,
                "return_basis": return_basis,
            }.items()
            if value not in (None, "")
        }
        snapshot_spec = self._first_mapping(mappings, ("universe_snapshot_spec",))
        if snapshot_spec:
            # 每筆 event 只保存精簡的快照摘要；完整成分仍留在推薦結果 JSON。
            selected_count = snapshot_spec.get("selected_count")
            if selected_count is not None and not isinstance(selected_count, bool):
                try:
                    metadata["universe_snapshot_selected_count"] = int(selected_count)
                except (TypeError, ValueError):
                    pass
        return {"fields": fields, "metadata": metadata}

    def _identity_mappings(self, result: Any) -> tuple[Mapping[str, Any], ...]:
        mappings: list[Mapping[str, Any]] = []
        for candidate in (
            getattr(result, "run_context", None),
            getattr(result, "config", None),
        ):
            if not isinstance(candidate, Mapping):
                continue
            mappings.append(candidate)
            nested = candidate.get("strategy_config")
            if isinstance(nested, Mapping):
                mappings.append(nested)
        return tuple(mappings)

    def _first_text(self, mappings: tuple[Mapping[str, Any], ...], keys: tuple[str, ...]) -> str:
        for mapping in mappings:
            for key in keys:
                value = mapping.get(key)
                if value is None or isinstance(value, (bool, Mapping, list, tuple)):
                    continue
                text = str(value).strip()
                if text:
                    return text
        return ""

    def _first_positive_integer(self, mappings: tuple[Mapping[str, Any], ...], keys: tuple[str, ...]) -> int | None:
        for mapping in mappings:
            for key in keys:
                value = mapping.get(key)
                if value is None or isinstance(value, bool):
                    continue
                try:
                    parsed = Decimal(str(value).strip())
                except (InvalidOperation, ValueError, TypeError):
                    continue
                if parsed.is_finite() and parsed == parsed.to_integral_value() and parsed > 0:
                    return int(parsed)
        return None

    def _first_mapping(
        self,
        mappings: tuple[Mapping[str, Any], ...],
        keys: tuple[str, ...],
    ) -> Mapping[str, Any] | None:
        for mapping in mappings:
            for key in keys:
                value = mapping.get(key)
                if isinstance(value, Mapping):
                    return value
        return None

    def _load_result(
        self, request: EvidenceCaptureRequest
    ) -> tuple[Any | None, str | None]:
        try:
            if request.result_id:
                return self.queries.get(request.result_id), None
            results = self.queries.list()
            if not results:
                return None, None
            latest, diagnostic = select_latest_saved_recommendation(results)
            return latest, diagnostic
        except (ExecutionPersistenceError, ValueError) as exc:
            return None, f"recommendation_query_failure:{type(exc).__name__}"


def _quality_for_execution(status: QualityStatus) -> str:
    return {
        QualityStatus.COMPLETE: EvidenceDataQuality.OBSERVED.value,
        QualityStatus.DEGRADED: EvidenceDataQuality.DEGRADED.value,
        QualityStatus.UNKNOWN: EvidenceDataQuality.MISSING.value,
        QualityStatus.UNAVAILABLE: EvidenceDataQuality.MISSING.value,
    }[status]


class WatchlistTriggerEvidenceImporter:
    source_name = "watchlist-trigger"

    def __init__(self, snapshot_provider: Any | None = None) -> None:
        self.snapshot_provider = snapshot_provider

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        if self.snapshot_provider is None:
            return UnsupportedEvidenceImporter(self.source_name).collect(request)
        decision_date = request.decision_date_text or date.today().isoformat()
        summary: WatchlistTriggerSummary = self.snapshot_provider.build_snapshot(datetime.fromisoformat(decision_date).date())
        as_of = _date_text(summary.as_of_date, decision_date)
        signal_types = self._parse_top_signal(summary.top_signal)
        payloads: list[dict[str, Any]] = []
        for code in summary.triggered_codes:
            event_type = signal_types.get(code, EvidenceEventType.WATCHLIST_TRIGGER_ADDED)
            payloads.append(self._payload(summary, code, event_type, decision_date, as_of, fallback=code not in signal_types))
        for warning in summary.warnings:
            prefix = "watchlist_trigger_risk_alert:"
            if warning.startswith(prefix):
                code = warning.removeprefix(prefix).strip()
                if code:
                    payloads.append(self._payload(summary, code, EvidenceEventType.WATCHLIST_TRIGGER_RISK_ALERT, decision_date, as_of))
        return EvidenceImportResult(
            self.source_name,
            decision_date,
            tuple(payloads),
            advisory_tokens=tuple(summary.warnings),
        )

    def _payload(
        self,
        summary: WatchlistTriggerSummary,
        code: str,
        event_type: EvidenceEventType,
        decision_date: str,
        as_of: str,
        *,
        fallback: bool = False,
    ) -> dict[str, Any]:
        source_snapshot_id = str(getattr(self.snapshot_provider, "snapshot_id", "") or f"watchlist-trigger:{as_of}")
        source_metadata = dict(getattr(self.snapshot_provider, "metadata", {}) or {})
        return {
            "event_date": as_of,
            "decision_date": decision_date,
            "symbol": str(code),
            "event_type": event_type,
            "event_family": "watchlist",
            "source_type": "daily_decision_desk_watchlist_trigger",
            "source_id": f"watchlist-trigger:{as_of}",
            "source_snapshot_id": source_snapshot_id,
            "reason_codes": (event_type.value,),
            "risk_codes": ("watchlist_risk_alert",) if event_type == EvidenceEventType.WATCHLIST_TRIGGER_RISK_ALERT else (),
            "data_quality": _quality(summary.quality),
            "warnings": (),
            "as_of_date": as_of,
            "available_date": decision_date,
            "source_version": "watchlist_trigger_importer_v1",
            "metadata": {
                "top_signal": summary.top_signal,
                "trigger_count": summary.trigger_count,
                "fallback_signal_type": fallback,
                **source_metadata,
            },
        }

    def _parse_top_signal(self, top_signal: str | None) -> dict[str, EvidenceEventType]:
        mapping: dict[str, EvidenceEventType] = {}
        if not top_signal:
            return mapping
        type_by_key = {
            "new": EvidenceEventType.WATCHLIST_TRIGGER_ADDED,
            "added": EvidenceEventType.WATCHLIST_TRIGGER_ADDED,
            "removed": EvidenceEventType.WATCHLIST_TRIGGER_REMOVED,
            "up": EvidenceEventType.WATCHLIST_TRIGGER_STRENGTH_UP,
            "down": EvidenceEventType.WATCHLIST_TRIGGER_STRENGTH_DOWN,
        }
        for part in top_signal.split(";"):
            key, sep, raw_codes = part.partition("=")
            if not sep:
                continue
            event_type = type_by_key.get(key.strip().lower())
            if event_type is None:
                continue
            for code in raw_codes.split(","):
                clean = code.strip()
                if clean:
                    mapping[clean] = event_type
        return mapping


class PortfolioAlertEvidenceImporter:
    source_name = "portfolio-alert"

    def __init__(self, snapshot_provider: Any | None = None) -> None:
        self.snapshot_provider = snapshot_provider

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        if self.snapshot_provider is None:
            return UnsupportedEvidenceImporter(self.source_name).collect(request)
        decision_date = request.decision_date_text or date.today().isoformat()
        summary: PortfolioAlertSummary = self.snapshot_provider.build_snapshot(datetime.fromisoformat(decision_date).date())
        as_of = _date_text(summary.as_of_date, decision_date)
        payloads = [
            self._payload(summary, attribution, decision_date, as_of)
            for attribution in summary.attributions
            if not request.symbol or str(attribution.stock_code) == str(request.symbol)
        ]
        return EvidenceImportResult(
            self.source_name,
            decision_date,
            tuple(payloads),
            advisory_tokens=tuple(summary.warnings),
        )

    def _payload(self, summary: PortfolioAlertSummary, attribution: Any, decision_date: str, as_of: str) -> dict[str, Any]:
        event_type = self._event_type(attribution)
        source_snapshot_id = str(getattr(self.snapshot_provider, "snapshot_id", "") or f"portfolio-alert:{as_of}")
        source_metadata = dict(getattr(self.snapshot_provider, "metadata", {}) or {})
        return {
            "event_date": as_of,
            "decision_date": decision_date,
            "symbol": str(attribution.stock_code),
            "event_type": event_type,
            "event_family": "portfolio",
            "source_type": "daily_decision_desk_portfolio_alert",
            "source_id": f"portfolio-alert:{as_of}",
            "source_snapshot_id": source_snapshot_id,
            "reason_codes": tuple(attribution.reasons),
            "risk_codes": (event_type.value,),
            "data_quality": _quality(summary.quality),
            "warnings": (),
            "as_of_date": as_of,
            "available_date": decision_date,
            "source_version": "portfolio_alert_importer_v1",
            "metadata": {
                "source_label": attribution.source_label,
                "condition_status": attribution.condition_status,
                "chip_risk_level": attribution.chip_risk_level,
                "severity": attribution.severity,
                "data_quality_flags": list(attribution.data_quality_flags),
                "chip_observed_event_count": attribution.chip_observed_event_count,
                "chip_estimated_event_count": attribution.chip_estimated_event_count,
                "chip_unavailable_event_count": attribution.chip_unavailable_event_count,
                "alert_level": summary.alert_level,
                **source_metadata,
            },
        }

    def _event_type(self, attribution: Any) -> EvidenceEventType:
        if str(attribution.condition_status).lower() == "invalid":
            return EvidenceEventType.PORTFOLIO_ALERT_CONDITION_INVALID
        if str(attribution.condition_status).lower() == "warning":
            return EvidenceEventType.PORTFOLIO_ALERT_CONDITION_WARNING
        if str(attribution.chip_risk_level).lower() in {"bearish", "extreme", "risk", "error"}:
            return EvidenceEventType.PORTFOLIO_ALERT_CHIP_RISK
        return EvidenceEventType.PORTFOLIO_ALERT_DATA_QUALITY


class RiskPromptEvidenceImporter:
    source_name = "risk-prompt"

    def __init__(self, snapshot_provider: Any | None = None) -> None:
        self.snapshot_provider = snapshot_provider

    def collect(self, request: EvidenceCaptureRequest) -> EvidenceImportResult:
        if self.snapshot_provider is None:
            return UnsupportedEvidenceImporter(self.source_name).collect(request)
        decision_date = request.decision_date_text or date.today().isoformat()
        summary: DecisionDeskRiskPromptSummary = self.snapshot_provider.build_snapshot(datetime.fromisoformat(decision_date).date())
        as_of = _date_text(summary.as_of_date, decision_date)
        source_snapshot_id = str(getattr(self.snapshot_provider, "snapshot_id", "") or f"risk-prompt:{as_of}")
        source_metadata = dict(getattr(self.snapshot_provider, "metadata", {}) or {})
        payloads = []
        for prompt in summary.prompts:
            symbol = str(prompt.code or "").strip() or "MARKET"
            if request.symbol and symbol != str(request.symbol):
                continue
            payloads.append(
                {
                    "event_date": as_of,
                    "decision_date": decision_date,
                    "symbol": symbol,
                    "event_type": self._event_type(prompt.category),
                    "event_family": "risk_prompt",
                    "source_type": "daily_decision_desk_risk_prompt",
                    "source_id": f"risk-prompt:{as_of}",
                    "source_snapshot_id": source_snapshot_id,
                    "reason_codes": (prompt.category, prompt.source),
                    "risk_codes": (prompt.severity,),
                    "data_quality": _quality(summary.quality),
                    "warnings": (),
                    "as_of_date": as_of,
                    "available_date": decision_date,
                    "source_version": "risk_prompt_importer_v1",
                    "metadata": {
                        "title": prompt.title,
                        "reason": prompt.reason,
                        "action_hint": prompt.action_hint,
                        "source": prompt.source,
                        "category": prompt.category,
                        **source_metadata,
                    },
                }
            )
        return EvidenceImportResult(
            self.source_name,
            decision_date,
            tuple(payloads),
            advisory_tokens=tuple(summary.warnings),
        )

    def _event_type(self, category: str) -> EvidenceEventType:
        if category == "liquidity":
            return EvidenceEventType.RISK_PROMPT_LOW_LIQUIDITY
        if category == "weakness":
            return EvidenceEventType.RISK_PROMPT_RELATIVE_WEAKNESS
        if category == "fundamental_diagnostic":
            return EvidenceEventType.RISK_PROMPT_FUNDAMENTAL_DIAGNOSTIC
        return EvidenceEventType.RISK_PROMPT_DATA_QUALITY
