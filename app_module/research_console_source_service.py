"""把 sanitized frozen projection 投影成 Research Console DTO；不連線資料庫。"""

from __future__ import annotations

import json
import inspect as pyinspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import Any

from app_module.research_console_dtos import (
    ResearchArtifactRowDTO,
    ResearchConsoleBoundaryDTO,
    ResearchConsoleDTO,
    ResearchGateCardDTO,
    ResearchPipelineRowDTO,
    ResearchSourceRowDTO,
)
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    check_read_cancelled,
    cooperative_read_cancellation,
)
from app_module.p0_source_control_center import (
    P0SourceControlCenterDTO,
    P0SourceControlCenterService,
)
from data_module.open_data_quarterly_candidate_audit import (
    AUDIT_SCHEMA as _QUARTERLY_CANDIDATE_AUDIT_SCHEMA,
    QuarterlyCandidateAuditError,
    audit_quarterly_candidate_root,
)
from data_module.open_data_quarterly_announcement_crosswalk import (
    AUDIT_SCHEMA as _QUARTERLY_ANNOUNCEMENT_CROSSWALK_SCHEMA,
    QuarterlyAnnouncementCrosswalkError,
    build_quarterly_announcement_crosswalk,
)
from data_module.formal_announcement_impact_reader import (
    read_quarterly_announcement_formal_impact,
)
from data_module.formal_monthly_revenue_quality_reader import (
    FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA,
    FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
    DEFAULT_DETAIL_PAGE_SIZE,
    read_formal_monthly_revenue_quality_by_period,
    read_formal_monthly_revenue_quality_missing_rows,
)
from data_module.open_data_issuer_directory_candidate_audit import (
    AUDIT_SCHEMA as _ISSUER_DIRECTORY_AUDIT_SCHEMA,
    IssuerDirectoryCandidateAuditError,
    audit_issuer_directory_candidate_root,
    build_quarterly_candidate_directory_comparison,
)
from data_module.source_acceptance_decision_registry import (
    SourceAcceptanceDecisionRevision,
    parse_source_acceptance_decisions,
)


ProjectionProvider = Callable[[], Mapping[str, object] | None]
GovernanceProvider = Callable[[], Mapping[str, object] | None]
P0AuditProvider = Callable[[], Mapping[str, Any] | None]
P0LicenseEvidenceProvider = Callable[[], Mapping[str, Any] | None]
P0DecisionProvider = Callable[[], Iterable[SourceAcceptanceDecisionRevision]]
ClockProvider = Callable[[], datetime]

P0_SOURCE_IDS = (
    "corporate_action.ex_dividend_timeline",
    "corporate_action.reduction_split_par_value",
    "microstructure.suspended_halt_resume",
    "microstructure.disposition_stock",
    "microstructure.periodic_call_auction",
    "microstructure.full_delivery",
    "microstructure.limit_lock",
    "institutional_flows",
    "credit_transactions",
    "tdcc_shareholding",
    "twse.monthly_revenue_announcement",
    "tpex.monthly_revenue_announcement",
    "pit.quarterly_financials",
)


def _resolve_candidate_roots(
    value: Sequence[str | Path] | str,
) -> tuple[Path, ...]:
    if isinstance(value, str):
        root_values: tuple[str | Path, ...] = tuple(
            item.strip() for item in value.split(os.pathsep) if item.strip()
        )
    else:
        root_values = tuple(value)
    if any(
        not isinstance(item, (str, Path)) or not str(item).strip()
        for item in root_values
    ):
        raise ValueError("MOPS announcement candidate roots must be non-empty paths")
    resolved = tuple(Path(item).expanduser().resolve() for item in root_values)
    if len(set(resolved)) != len(resolved):
        raise ValueError("MOPS announcement candidate roots must be unique")
    return resolved

_PIPELINE_LABELS = {
    "dataset": "Development Dataset V0",
    "rule": "Rule Development Baseline",
    "ml": "ML Development Challenger",
    "e2e": "Development E2E Run",
}

_REQUIRED_DISABLED_APPLY_FLAGS = (
    "apply_to_scoring",
    "apply_to_recommendation",
    "apply_to_portfolio",
    "apply_to_exit",
)

_DEFAULT_MAX_PROJECTION_AGE = timedelta(days=7)
_FUTURE_TIMESTAMP_TOLERANCE = timedelta(minutes=5)
_MOPS_SANITIZED_SCHEMA = "mops-sanitized-research-projection.v1"
_MOPS_SOURCE_ID = "mops.ezsearch.statement_publication"
_MOPS_DECISION_ID = "decision:mops.ezsearch.statement_publication:20260727-r1"
_MOPS_ALLOWED_USE = (
    "research_pit_statement_availability, development_shadow_projection"
)
_SHA256_REFERENCE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_MOPS_FORBIDDEN_KEYS = frozenset(
    {
        "rows",
        "availability_projection",
        "subject",
        "hyperlink",
        "detail_url",
        "cookies",
        "headers",
        "token",
        "credential",
        "session",
        "db_path",
    }
)


class ResearchConsoleSourceService:
    """只讀取呼叫端注入 payload 或顯式 JSON artifact。"""

    def __init__(
        self,
        *,
        projection_provider: ProjectionProvider | None = None,
        projection_path: str | Path | None = None,
        governance_provider: GovernanceProvider | None = None,
        p0_audit_provider: P0AuditProvider | None = None,
        p0_audit_path: str | Path | None = None,
        p0_license_evidence_provider: P0LicenseEvidenceProvider | None = None,
        p0_license_evidence_path: str | Path | None = None,
        p0_decision_provider: P0DecisionProvider | None = None,
        p0_decision_path: str | Path | None = None,
        p0_quarterly_candidate_root: str | Path | None = None,
        p0_formal_db_path: str | Path | None = None,
        p0_monthly_revenue_availability_path: str | Path | None = None,
        p0_issuer_directory_candidate_root: str | Path | None = None,
        p0_mops_announcement_candidate_roots: Sequence[str | Path] | str | None = None,
        clock: ClockProvider | None = None,
        max_projection_age: timedelta = _DEFAULT_MAX_PROJECTION_AGE,
    ) -> None:
        if projection_provider is not None and projection_path is not None:
            raise ValueError("use either projection_provider or projection_path")
        self._projection_provider = projection_provider
        self._projection_path = Path(projection_path).resolve() if projection_path is not None else None
        self._governance_provider = governance_provider
        self._p0_audit_provider = p0_audit_provider
        if p0_audit_provider is not None and p0_audit_path is not None:
            raise ValueError("use either p0_audit_provider or p0_audit_path")
        self._p0_audit_path = Path(p0_audit_path).resolve() if p0_audit_path is not None else None
        self._p0_license_evidence_provider = p0_license_evidence_provider
        if p0_license_evidence_provider is not None and p0_license_evidence_path is not None:
            raise ValueError(
                "use either p0_license_evidence_provider or p0_license_evidence_path"
            )
        self._p0_license_evidence_path = (
            Path(p0_license_evidence_path).resolve()
            if p0_license_evidence_path is not None
            else None
        )
        self._p0_decision_provider = p0_decision_provider
        if p0_decision_provider is not None and p0_decision_path is not None:
            raise ValueError("use either p0_decision_provider or p0_decision_path")
        self._p0_decision_path = (
            Path(p0_decision_path).resolve() if p0_decision_path is not None else None
        )
        configured_candidate_root = (
            p0_quarterly_candidate_root
            if p0_quarterly_candidate_root is not None
            else os.environ.get("P0_QUARTERLY_CANDIDATE_ROOT")
        )
        self._p0_quarterly_candidate_root = (
            Path(configured_candidate_root).expanduser().resolve()
            if configured_candidate_root
            else None
        )
        self._p0_quarterly_candidate_root_default = self._p0_quarterly_candidate_root
        self._p0_formal_db_path = (
            Path(p0_formal_db_path).expanduser()
            if p0_formal_db_path is not None
            else None
        )
        self._p0_monthly_revenue_availability_path = (
            Path(p0_monthly_revenue_availability_path).expanduser()
            if p0_monthly_revenue_availability_path is not None
            else None
        )
        configured_directory_root = (
            p0_issuer_directory_candidate_root
            if p0_issuer_directory_candidate_root is not None
            else os.environ.get("P0_ISSUER_DIRECTORY_CANDIDATE_ROOT")
        )
        self._p0_issuer_directory_candidate_root = (
            Path(configured_directory_root).expanduser().resolve()
            if configured_directory_root
            else None
        )
        self._p0_issuer_directory_candidate_root_default = (
            self._p0_issuer_directory_candidate_root
        )
        configured_mops_roots = p0_mops_announcement_candidate_roots
        if configured_mops_roots is None:
            configured_mops_roots = os.environ.get(
                "P0_MOPS_ANNOUNCEMENT_CANDIDATE_ROOTS", ""
            )
        self._p0_mops_announcement_candidate_roots = _resolve_candidate_roots(
            configured_mops_roots
        )
        self._p0_mops_announcement_candidate_roots_default = (
            self._p0_mops_announcement_candidate_roots
        )
        self._p0_control_center_service = P0SourceControlCenterService()
        if max_projection_age <= timedelta(0):
            raise ValueError("max_projection_age must be positive")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._max_projection_age = max_projection_age

    @property
    def p0_quarterly_candidate_root(self) -> Path | None:
        return self._p0_quarterly_candidate_root

    def set_p0_quarterly_candidate_root(self, path: str | Path | None) -> None:
        """設定本次執行要唯讀檢查的候選目錄；不保存設定或改寫輸入。"""

        if path is None or not str(path).strip():
            self._p0_quarterly_candidate_root = self._p0_quarterly_candidate_root_default
            return
        self._p0_quarterly_candidate_root = Path(path).expanduser().resolve()

    @property
    def p0_issuer_directory_candidate_root(self) -> Path | None:
        return self._p0_issuer_directory_candidate_root

    def set_p0_issuer_directory_candidate_root(self, path: str | Path | None) -> None:
        """設定本次執行唯讀檢查的 issuer 名錄候選；不保存設定或改寫輸入。"""

        if path is None or not str(path).strip():
            self._p0_issuer_directory_candidate_root = (
                self._p0_issuer_directory_candidate_root_default
            )
            return
        self._p0_issuer_directory_candidate_root = Path(path).expanduser().resolve()

    @property
    def p0_mops_announcement_candidate_roots(self) -> tuple[Path, ...]:
        return self._p0_mops_announcement_candidate_roots

    def set_p0_mops_announcement_candidate_roots(
        self, paths: Sequence[str | Path] | str | None
    ) -> None:
        """設定本次執行的唯讀 MOPS 公告候選目錄；不保存設定或改寫輸入。"""

        if paths is None or paths == "" or paths == () or paths == []:
            self._p0_mops_announcement_candidate_roots = (
                self._p0_mops_announcement_candidate_roots_default
            )
            return
        self._p0_mops_announcement_candidate_roots = _resolve_candidate_roots(paths)

    def inspect(
        self,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ResearchConsoleDTO:
        with cooperative_read_cancellation(cancel_callback):
            check_read_cancelled()
            try:
                payload, reference, artifact_hash = self._read_projection(cancel_callback)
            except ReadOperationCancelled:
                raise
            except Exception:
                check_read_cancelled()
                return self._missing(
                    "projection_read_failed",
                    overall_status="degraded",
                    cancel_callback=cancel_callback,
                )
            check_read_cancelled()
            if payload is None:
                return self._missing("projection_missing", cancel_callback=cancel_callback)
            if not self._has_safe_boundary(payload):
                return self._missing(
                    "projection_boundary_violation",
                    overall_status="degraded",
                    cancel_callback=cancel_callback,
                )
            try:
                return self._project(payload, reference, artifact_hash, cancel_callback)
            except ReadOperationCancelled:
                raise
            except Exception:
                check_read_cancelled()
                return self._missing(
                    "projection_schema_invalid",
                    overall_status="degraded",
                    cancel_callback=cancel_callback,
                )

    def missing_projection(self) -> ResearchConsoleDTO:
        """建立不讀取 provider 或檔案的本機 fail-closed 初始 DTO。"""

        return self._missing("projection_missing", include_optional_sources=False)

    def _read_projection(
        self,
        cancel_callback: Callable[[], bool] | None,
    ) -> tuple[Mapping[str, object] | None, str, str | None]:
        check_read_cancelled()
        if self._projection_provider is not None:
            payload = _call_provider(self._projection_provider, cancel_callback)
            check_read_cancelled()
            return payload, "injected_projection", None
        if self._projection_path is None or not self._projection_path.is_file():
            return None, "not_configured", None
        projection_bytes = self._projection_path.read_bytes()
        check_read_cancelled()
        payload = json.loads(projection_bytes)
        if not isinstance(payload, Mapping):
            raise TypeError("projection root must be an object")
        artifact_hash = "sha256:" + sha256(projection_bytes).hexdigest()
        return payload, str(self._projection_path), artifact_hash

    def _project(
        self,
        payload: Mapping[str, object],
        reference: str,
        artifact_hash: str | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> ResearchConsoleDTO:
        _validate_mops_sanitized_projection(payload)
        check_read_cancelled()
        identity = _mapping(payload, "identity")
        status = _mapping(payload, "status")
        metrics = _mapping(payload, "frozen_metrics")
        lineage = _mapping(payload, "lineage")
        blockers = _string_tuple(payload.get("blockers")) + self._freshness_blockers(lineage)
        governance = (
            _call_provider(self._governance_provider, cancel_callback)
            if self._governance_provider is not None
            else None
        )
        check_read_cancelled()
        if governance is None and ("sources" in payload or "gates" in payload):
            governance = payload
        if governance is not None and not isinstance(governance, Mapping):
            raise TypeError("governance projection must be an object")
        source_control_center = self._build_p0_source_control_center(
            governance, cancel_callback
        )
        check_read_cancelled()
        sample_count = _optional_int(metrics.get("sample_count"))
        feature_names = lineage.get("feature_names")
        feature_count = len(feature_names) if isinstance(feature_names, list) else None
        dataset_id = _required_string(identity, "dataset_id")
        generation_id = _required_string(identity, "generation_id")
        research_run_id = _required_string(identity, "research_run_id")
        dataset_status = str(status.get("scope") or "development_only")
        rule_metrics = metrics.get("rule")
        ml_metrics = metrics.get("ml")
        rule_status = _component_status(rule_metrics, "research_baseline")
        ml_status = _component_status(ml_metrics, "development_challenger")
        pipeline = (
            ResearchPipelineRowDTO(
                component_id="dataset",
                label=_PIPELINE_LABELS["dataset"],
                identity=dataset_id,
                status=dataset_status,
                cutoff=_optional_string(lineage.get("training_as_of")),
                feature_interval=_feature_interval(feature_names),
                label_maturity=_optional_string(lineage.get("max_label_available_date")),
                row_count=_optional_int(lineage.get("input_fit_row_count"), fallback=sample_count),
                eligible_count=sample_count,
                feature_count=feature_count,
                artifact_hash=_optional_string(lineage.get("dataset_manifest_hash")),
                blockers=blockers,
            ),
            ResearchPipelineRowDTO(
                component_id="rule",
                label=_PIPELINE_LABELS["rule"],
                identity=_optional_string(lineage.get("rule_configuration_hash")) or "Unknown",
                status=rule_status,
                row_count=_metric_count(rule_metrics),
                blockers=blockers,
            ),
            ResearchPipelineRowDTO(
                component_id="ml",
                label=_PIPELINE_LABELS["ml"],
                identity=research_run_id,
                status=ml_status,
                row_count=_metric_count(ml_metrics),
                blockers=blockers,
            ),
            ResearchPipelineRowDTO(
                component_id="e2e",
                label=_PIPELINE_LABELS["e2e"],
                identity=research_run_id,
                status="degraded" if blockers else "observed",
                generated_at=_optional_string(lineage.get("generated_at")),
                artifact_path=reference,
                artifact_hash=artifact_hash,
                blockers=blockers,
            ),
        )
        return ResearchConsoleDTO(
            overall_status="degraded" if blockers else "observed",
            source_reference=reference,
            boundary=ResearchConsoleBoundaryDTO(),
            pipeline=pipeline,
            gates=_governance_gates(governance),
            sources=_governance_sources(governance),
            artifacts=_artifact_rows(lineage) + _governance_artifacts(governance),
            source_control_center=source_control_center,
            frozen_metrics=metrics,
            blockers=blockers,
        )

    def _freshness_blockers(self, lineage: Mapping[str, object]) -> tuple[str, ...]:
        generated_at = _optional_string(lineage.get("generated_at"))
        if generated_at is None:
            return ("projection_generated_at_missing",)
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return ("projection_generated_at_invalid",)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return ("projection_generated_at_invalid",)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        age = now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
        if age < -_FUTURE_TIMESTAMP_TOLERANCE:
            return ("projection_generated_at_future",)
        if age > self._max_projection_age:
            return ("projection_stale",)
        return ()

    def _missing(
        self,
        blocker: str,
        *,
        overall_status: str = "missing",
        include_optional_sources: bool = True,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ResearchConsoleDTO:
        try:
            source_control_center = (
                self._build_p0_source_control_center(None, cancel_callback)
                if include_optional_sources
                else self._p0_control_center_service.build()
            )
        except ReadOperationCancelled:
            raise
        except Exception:
            check_read_cancelled()
            # A malformed optional audit/decision artifact must not make the
            # fail-closed fallback itself escape.  Keep the authoritative
            # thirteen contract rows visible without applying the bad input.
            source_control_center = self._p0_control_center_service.build()
        return ResearchConsoleDTO(
            overall_status=overall_status,
            source_reference="not_configured",
            boundary=ResearchConsoleBoundaryDTO(),
            pipeline=tuple(
                ResearchPipelineRowDTO(
                    component_id=component_id,
                    label=label,
                    identity="Missing",
                    status="missing",
                    blockers=(blocker,),
                )
                for component_id, label in _PIPELINE_LABELS.items()
            ),
            gates=_missing_gates(),
            sources=_missing_sources(),
            source_control_center=source_control_center,
            blockers=(blocker,),
        )

    def read_formal_monthly_revenue_quality_missing_rows(
        self,
        period: str,
        offset: int = 0,
        limit: int = DEFAULT_DETAIL_PAGE_SIZE,
    ) -> dict[str, Any]:
        """讀取明選月份公告日缺漏與報表日期待核實識別資料頁。"""

        if self._p0_formal_db_path is None:
            return {
                "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
                "status": "unavailable",
                "period": period,
                "rows": None,
                "mapping_status": "unknown",
                "total_count": None,
                "limit": limit,
                "offset": offset,
                "has_more": None,
                "blockers": ["formal_monthly_revenue_database_path_not_configured"],
                "scope": "unknown",
                "formal_db_write": False,
                "financial_values_returned": False,
            }
        return read_formal_monthly_revenue_quality_missing_rows(
            self._p0_formal_db_path,
            period=period,
            offset=offset,
            limit=limit,
            availability_mapping_path=self._p0_monthly_revenue_availability_path,
        )

    def _build_p0_source_control_center(
        self,
        governance: Mapping[str, object] | None,
        cancel_callback: Callable[[], bool] | None,
    ) -> P0SourceControlCenterDTO:
        check_read_cancelled()
        if self._p0_formal_db_path is None:
            formal_monthly_revenue_quality: Mapping[str, Any] = {
                "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA,
                "status": "unavailable",
                "periods": None,
                "blockers": ["formal_monthly_revenue_database_path_not_configured"],
                "scope": "unknown",
                "formal_db_write": False,
                "financial_values_returned": False,
            }
        else:
            formal_monthly_revenue_quality = (
                read_formal_monthly_revenue_quality_by_period(
                    self._p0_formal_db_path,
                    self._p0_monthly_revenue_availability_path,
                )
            )
        check_read_cancelled()
        audit = (
            _call_provider(self._p0_audit_provider, cancel_callback)
            if self._p0_audit_provider is not None
            else None
        )
        if audit is None and self._p0_audit_path is not None:
            audit_bytes = self._p0_audit_path.read_bytes()
            check_read_cancelled()
            parsed = json.loads(audit_bytes)
            if not isinstance(parsed, Mapping):
                raise TypeError("P0 audit artifact must be an object")
            audit = parsed  # type: ignore[assignment]
        if audit is None and governance is not None:
            schema = governance.get("schema_version")
            if schema in {"p0-candidate-audit.v1", "p0-source-evidence-audit.v1"}:
                audit = governance  # type: ignore[assignment]
            else:
                embedded = governance.get("p0_candidate_audit")
                if isinstance(embedded, Mapping):
                    audit = embedded  # type: ignore[assignment]
        decisions: Iterable[SourceAcceptanceDecisionRevision] = ()
        if self._p0_decision_provider is not None:
            decisions = _call_provider(self._p0_decision_provider, cancel_callback)
        elif self._p0_decision_path is not None:
            decision_bytes = self._p0_decision_path.read_bytes()
            check_read_cancelled()
            decisions = parse_source_acceptance_decisions(json.loads(decision_bytes))
        check_read_cancelled()
        license_evidence = (
            _call_provider(self._p0_license_evidence_provider, cancel_callback)
            if self._p0_license_evidence_provider is not None
            else None
        )
        if license_evidence is None and self._p0_license_evidence_path is not None:
            license_bytes = self._p0_license_evidence_path.read_bytes()
            check_read_cancelled()
            parsed_license = json.loads(license_bytes)
            if not isinstance(parsed_license, Mapping):
                raise TypeError("P0 license evidence artifact must be an object")
            license_evidence = parsed_license  # type: ignore[assignment]
        quarterly_candidate_audit: dict[str, Any] | None = None
        candidate_root = self._p0_quarterly_candidate_root
        if candidate_root is not None:
            check_read_cancelled()
            try:
                quarterly_candidate_audit = audit_quarterly_candidate_root(
                    candidate_root
                ).to_dict()
                quarterly_candidate_audit["source_id"] = "pit.quarterly_financials"
            except QuarterlyCandidateAuditError as exc:
                # Keep a failed explicit candidate selection visible while
                # preserving the same candidate-only boundary as valid audits.
                quarterly_candidate_audit = {
                    "schema_version": _QUARTERLY_CANDIDATE_AUDIT_SCHEMA,
                    "source_id": "pit.quarterly_financials",
                    "candidate_only": True,
                    "formal_db_write": False,
                    "source_acceptance": False,
                    "gate_credit": False,
                    "downstream_eligibility": "none",
                    "overall_state": "invalid",
                    "summary": {
                        "resource_count": 0,
                        "available_resource_count": 0,
                        "empty_response_resource_count": 0,
                        "missing_resource_count": 0,
                        "invalid_resource_count": 0,
                        "summary_complete": False,
                        "row_count": None,
                        "unique_issuer_resource_count": None,
                        "duplicate_business_key_count": None,
                    },
                    "resources": [],
                    "limitations": [
                        "明確選取的候選目錄無法通過離線 manifest／檔案驗證。",
                        "本次未把內容視為來源接受、Gate credit 或下游可用資料。",
                    ],
                    "errors": [str(exc).split(":", 1)[0]],
                }
        quarterly_announcement_crosswalk: dict[str, Any] | None = None
        announcement_roots = self._p0_mops_announcement_candidate_roots
        if quarterly_candidate_audit is not None and announcement_roots:
            check_read_cancelled()
            try:
                if quarterly_candidate_audit.get("errors"):
                    raise QuarterlyAnnouncementCrosswalkError(
                        "quarterly_candidate_audit_invalid"
                    )
                quarterly_announcement_crosswalk = build_quarterly_announcement_crosswalk(
                    quarterly_audit=quarterly_candidate_audit,
                    announcement_candidate_roots=announcement_roots,
                )
            except QuarterlyAnnouncementCrosswalkError as exc:
                quarterly_announcement_crosswalk = {
                    "schema_version": _QUARTERLY_ANNOUNCEMENT_CROSSWALK_SCHEMA,
                    "candidate_only": True,
                    "formal_db_write": False,
                    "source_acceptance": False,
                    "gate_credit": False,
                    "downstream_eligibility": "none",
                    "status": "invalid",
                    "announcement_candidate_bundle_count": len(announcement_roots),
                    "announcement_candidate_bundles": [],
                    "query_window_start": None,
                    "query_window_end": None,
                    "query_windows_complete_by_market_statement": {},
                    "query_windows": [],
                    "summary_by_market_statement": [],
                    "resources": [],
                    "limitations": [
                        "明選季度 CSV 或 MOPS 公告候選未通過結構、hash 或來源身分核對；沒有產生對照結果。",
                        "不改變來源接受、PIT 或 Gate 資格。",
                    ],
                    "errors": [str(exc).split(":", 1)[0]],
                }
        if quarterly_announcement_crosswalk is not None:
            check_read_cancelled()
            quarterly_announcement_crosswalk["formal_impact"] = (
                read_quarterly_announcement_formal_impact(
                    crosswalk=quarterly_announcement_crosswalk,
                    database_path=self._p0_formal_db_path,
                )
            )
            check_read_cancelled()
        directory_audit: dict[str, Any] | None = None
        directory_root = self._p0_issuer_directory_candidate_root
        if directory_root is not None:
            check_read_cancelled()
            try:
                directory_audit = audit_issuer_directory_candidate_root(
                    directory_root
                ).to_dict()
            except IssuerDirectoryCandidateAuditError as exc:
                directory_audit = {
                    "schema_version": _ISSUER_DIRECTORY_AUDIT_SCHEMA,
                    "candidate_only": True,
                    "formal_db_write": False,
                    "source_acceptance": False,
                    "gate_credit": False,
                    "downstream_eligibility": "none",
                    "resources": [],
                    "entries": [],
                    "directory_dates_by_market": {"TWSE": [], "TPEx": []},
                    "limitations": [
                        "明確選取的名錄候選未通過離線 manifest／檔案驗證。",
                        "本次不將名錄候選視為來源接受、Gate credit 或下游可用資料。",
                    ],
                    "errors": [str(exc).split(":", 1)[0]],
                }
        if (
            quarterly_candidate_audit is not None
            and directory_audit is not None
            and not quarterly_candidate_audit.get("errors")
            and not directory_audit.get("errors")
        ):
            try:
                quarterly_candidate_audit["issuer_directory_candidate_audit"] = (
                    directory_audit
                )
                quarterly_candidate_audit["coverage_comparison"] = (
                    build_quarterly_candidate_directory_comparison(
                        quarterly_audit=quarterly_candidate_audit,
                        directory_audit=directory_audit,
                    )
                )
            except IssuerDirectoryCandidateAuditError as exc:
                quarterly_candidate_audit["coverage_comparison"] = {
                    "schema_version": "baldr.quarterly_candidate_directory_comparison.v1",
                    "candidate_only": True,
                    "formal_db_write": False,
                    "source_acceptance": False,
                    "gate_credit": False,
                    "downstream_eligibility": "none",
                    "comparison_scope": "currently_selected_quarterly_candidate_root_only",
                    "complete": False,
                    "summary_by_market": {},
                    "rows": [],
                    "limitations": [
                        "候選資料未通過逐公司名錄對照條件；不顯示部分結果以免誤讀。"
                    ],
                    "errors": [str(exc).split(":", 1)[0]],
                }
        elif quarterly_candidate_audit is not None and directory_audit is not None:
            quarterly_candidate_audit["issuer_directory_candidate_audit"] = directory_audit
            quarterly_candidate_audit["coverage_comparison"] = {
                "schema_version": "baldr.quarterly_candidate_directory_comparison.v1",
                "candidate_only": True,
                "formal_db_write": False,
                "source_acceptance": False,
                "gate_credit": False,
                "downstream_eligibility": "none",
                "comparison_scope": "currently_selected_quarterly_candidate_root_only",
                "complete": False,
                "summary_by_market": {},
                "rows": [],
                "limitations": ["名錄候選未通過離線檔案驗證；不顯示比較結果。"],
                "errors": directory_audit.get("errors", []),
            }
        elif quarterly_candidate_audit is None and directory_audit is not None:
            quarterly_candidate_audit = {
                "schema_version": _QUARTERLY_CANDIDATE_AUDIT_SCHEMA,
                "source_id": "pit.quarterly_financials",
                "candidate_only": True,
                "formal_db_write": False,
                "source_acceptance": False,
                "gate_credit": False,
                "downstream_eligibility": "none",
                "overall_state": "not_selected",
                "summary": {
                    "resource_count": 0,
                    "available_resource_count": 0,
                    "empty_response_resource_count": 0,
                    "missing_resource_count": 0,
                    "invalid_resource_count": 0,
                    "summary_complete": False,
                    "row_count": None,
                    "unique_issuer_resource_count": None,
                    "duplicate_business_key_count": None,
                },
                "resources": [],
                "issuer_directory_candidate_audit": directory_audit,
                "coverage_comparison": {
                    "schema_version": "baldr.quarterly_candidate_directory_comparison.v1",
                    "candidate_only": True,
                    "formal_db_write": False,
                    "source_acceptance": False,
                    "gate_credit": False,
                    "downstream_eligibility": "none",
                    "comparison_scope": "currently_selected_quarterly_candidate_root_only",
                    "complete": False,
                    "summary_by_market": {},
                    "rows": [],
                    "limitations": ["尚未選取季度財報候選目錄；目前只驗證名錄候選。"],
                    "errors": ["quarterly_candidate_not_selected"],
                },
            }
        return self._p0_control_center_service.build(
            candidate_audit=audit,
            license_evidence=license_evidence,
            decisions=decisions,
            quarterly_candidate_audit=quarterly_candidate_audit,
            quarterly_announcement_crosswalk=quarterly_announcement_crosswalk,
            formal_monthly_revenue_quality=formal_monthly_revenue_quality,
        )

    @staticmethod
    def _has_safe_boundary(payload: Mapping[str, object]) -> bool:
        try:
            status = _mapping(payload, "status")
        except (KeyError, TypeError):
            return False
        flags = status.get("apply_flags")
        if not isinstance(flags, Mapping):
            return False
        alpha_bp = status.get("alpha_bp")
        return (
            status.get("scope") == "historical_research_seen_development_data"
            and status.get("formal_oos") is False
            and type(alpha_bp) is int
            and alpha_bp == 0
            and status.get("promotion_eligible") is False
            and set(flags) == set(_REQUIRED_DISABLED_APPLY_FLAGS)
            and all(flags.get(key) is False for key in _REQUIRED_DISABLED_APPLY_FLAGS)
        )


def _missing_gates() -> tuple[ResearchGateCardDTO, ...]:
    return tuple(
        ResearchGateCardDTO(
            gate_id=f"EV{index}",
            label=f"EV{index}",
            status="missing",
            detail="Not Available；未提供 sanitized gate projection。",
        )
        for index in range(1, 6)
    )


def _call_provider(
    provider: Callable[..., Any],
    cancel_callback: Callable[[], bool] | None,
) -> Any:
    check_read_cancelled()
    if cancel_callback is None:
        result = provider()
    else:
        try:
            signature = pyinspect.signature(provider)
        except (TypeError, ValueError):
            signature = None
        if signature is None:
            result = provider()
        else:
            parameters = signature.parameters
            accepts_kwargs = any(
                parameter.kind is pyinspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            cancel_parameter = parameters.get("cancel_callback") or parameters.get(
                "cancellation_callback"
            )
            if (
                cancel_parameter is not None
                and cancel_parameter.kind is pyinspect.Parameter.POSITIONAL_ONLY
            ):
                result = provider(cancel_callback)
            elif cancel_parameter is not None:
                result = provider(**{cancel_parameter.name: cancel_callback})
            elif accepts_kwargs:
                result = provider(cancel_callback=cancel_callback)
            else:
                result = provider()
    check_read_cancelled()
    return result


def _missing_sources() -> tuple[ResearchSourceRowDTO, ...]:
    p0 = tuple(
        ResearchSourceRowDTO(
            source_id=source_id,
            label=source_id,
            lane="p0",
            status="missing",
            allowed_use="Not Available",
            degraded_reason="sanitized_source_projection_missing",
        )
        for source_id in P0_SOURCE_IDS
    )
    return p0 + (
        ResearchSourceRowDTO(
            source_id="broker_dataset",
            label="Broker Dataset（獨立研究 lane）",
            lane="broker",
            status="missing",
            allowed_use="Development Only / Not formally accepted",
            degraded_reason="sanitized_broker_projection_missing",
        ),
    )


def _artifact_rows(lineage: Mapping[str, object]) -> tuple[ResearchArtifactRowDTO, ...]:
    rows = []
    for artifact_type, field_name in (
        ("dataset_manifest", "dataset_manifest_hash"),
        ("dataset_content", "dataset_content_hash"),
        ("feature_registry", "feature_registry_hash"),
        ("label_registry", "label_registry_hash"),
        ("rule_configuration", "rule_configuration_hash"),
    ):
        artifact_id = _optional_string(lineage.get(field_name))
        if artifact_id:
            rows.append(
                ResearchArtifactRowDTO(
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    status="development_only",
                    citation=f"ResearchConsoleProjection.lineage.{field_name}",
                )
            )
    return tuple(rows)


def _governance_gates(
    governance: Mapping[str, object] | None,
) -> tuple[ResearchGateCardDTO, ...]:
    rows = {item.gate_id: item for item in _missing_gates()}
    if governance is None:
        return tuple(rows.values())
    payload = governance.get("gates", [])
    if not isinstance(payload, list):
        raise TypeError("gates must be an array")
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise TypeError("gate row must be an object")
        gate_id = _required_string(raw, "gate_id")
        if gate_id not in rows:
            raise ValueError(f"unknown evidence gate: {gate_id}")
        rows[gate_id] = ResearchGateCardDTO(
            gate_id=gate_id,
            label=_optional_string(raw.get("label")) or gate_id,
            status=_required_string(raw, "status"),
            detail=_required_string(raw, "detail"),
            artifact_citation=_optional_string(raw.get("artifact_citation")),
        )
    return tuple(rows[f"EV{index}"] for index in range(1, 6))


def _governance_sources(
    governance: Mapping[str, object] | None,
) -> tuple[ResearchSourceRowDTO, ...]:
    defaults = {item.source_id: item for item in _missing_sources()}
    if governance is None:
        return tuple(defaults.values())
    payload = governance.get("sources", [])
    if not isinstance(payload, list):
        raise TypeError("sources must be an array")
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise TypeError("source row must be an object")
        source_id = _required_string(raw, "source_id")
        if source_id not in defaults:
            raise ValueError(f"unknown Research Console source: {source_id}")
        lane = _required_string(raw, "lane")
        expected_lane = defaults[source_id].lane
        if lane != expected_lane:
            raise ValueError(f"source lane mismatch: {source_id}")
        defaults[source_id] = ResearchSourceRowDTO(
            source_id=source_id,
            label=_optional_string(raw.get("label")) or defaults[source_id].label,
            lane=expected_lane,
            status=_required_string(raw, "status"),
            allowed_use=_required_string(raw, "allowed_use"),
            observed_rows=_optional_int(raw.get("observed_rows")),
            revision=_optional_string(raw.get("revision")),
            owner=_optional_string(raw.get("owner")),
            degraded_reason=_optional_string(raw.get("degraded_reason")),
        )
    return tuple(defaults[source_id] for source_id in P0_SOURCE_IDS) + (defaults["broker_dataset"],)


def _governance_artifacts(
    governance: Mapping[str, object] | None,
) -> tuple[ResearchArtifactRowDTO, ...]:
    if governance is None:
        return ()
    payload = governance.get("artifacts", [])
    if not isinstance(payload, list):
        raise TypeError("artifacts must be an array")
    rows = []
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise TypeError("artifact row must be an object")
        rows.append(
            ResearchArtifactRowDTO(
                artifact_type=_required_string(raw, "artifact_type"),
                artifact_id=_required_string(raw, "artifact_id"),
                status=_required_string(raw, "status"),
                citation=_required_string(raw, "citation"),
            )
        )
    return tuple(rows)


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be an object")
    return value


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = _optional_string(payload.get(key))
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _optional_string(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _optional_int(value: object, *, fallback: int | None = None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return fallback
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("blockers must be a string array")
    return tuple(value)


def _validate_mops_sanitized_projection(payload: Mapping[str, object]) -> None:
    is_mops_projection = (
        payload.get("source") == _MOPS_SOURCE_ID
        or payload.get("p0_lane") == "pit.quarterly_financials"
    )
    if not is_mops_projection:
        return
    if payload.get("schema_version") != _MOPS_SANITIZED_SCHEMA:
        raise ValueError("unsupported MOPS sanitized projection schema")
    if (
        payload.get("source") != _MOPS_SOURCE_ID
        or payload.get("p0_lane") != "pit.quarterly_financials"
        or payload.get("source_decision") != _MOPS_DECISION_ID
        or payload.get("acceptance") != "limited"
        or payload.get("allowed_use") != _MOPS_ALLOWED_USE
        or payload.get("formal_allowed") is not False
        or payload.get("formal_evidence_credit_authorized") is not False
        or payload.get("production_allowed") is not False
        or payload.get("production_blend_alpha_bp") != 0
        or payload.get("scheduler_allowed") is not False
        or payload.get("training_allowed") is not False
        or payload.get("promotion_allowed") is not False
        or payload.get("fubon_shadow_usable") is not True
        or payload.get("fubon_formal_credit_allowed") is not False
    ):
        raise ValueError("MOPS sanitized projection governance boundary is invalid")
    _reject_forbidden_projection_keys(payload)
    artifact_hash = payload.get("current_artifact_hash")
    if not isinstance(artifact_hash, str) or not _SHA256_REFERENCE.fullmatch(artifact_hash):
        raise ValueError("MOPS sanitized projection artifact hash is invalid")
    if type(payload.get("multi_day_evidence_ready")) is not bool:
        raise TypeError("multi_day_evidence_ready must be boolean")
    counts = _mapping(payload, "counts")
    for key, value in counts.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"MOPS sanitized projection count is invalid: {key}")
    run_status = payload.get("current_run_status")
    if run_status not in {
        "observed",
        "observed_empty",
        "degraded",
        "stale",
        "capture_failed",
    }:
        raise ValueError("MOPS sanitized projection run status is invalid")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("MOPS sanitized projection must contain exactly one source row")
    source = sources[0]
    if not isinstance(source, Mapping):
        raise TypeError("MOPS sanitized source row must be an object")
    expected_source_status = (
        "degraded" if run_status in {"degraded", "stale", "capture_failed"} else run_status
    )
    if (
        source.get("source_id") != "pit.quarterly_financials"
        or source.get("lane") != "p0"
        or source.get("status") != expected_source_status
        or source.get("allowed_use") != _MOPS_ALLOWED_USE
        or source.get("observed_rows") != counts.get("events")
    ):
        raise ValueError("MOPS sanitized source row is inconsistent with run status")


def _reject_forbidden_projection_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _MOPS_FORBIDDEN_KEYS:
                raise ValueError(f"forbidden key in MOPS sanitized projection: {key}")
            _reject_forbidden_projection_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_projection_keys(item)


def _component_status(value: object, fallback: str) -> str:
    if not isinstance(value, Mapping):
        return "missing"
    status = value.get("status")
    return str(status) if isinstance(status, str) and status else fallback


def _metric_count(value: object) -> int | None:
    return _optional_int(value.get("sample_count")) if isinstance(value, Mapping) else None


def _feature_interval(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    return f"{len(value)} frozen features"
