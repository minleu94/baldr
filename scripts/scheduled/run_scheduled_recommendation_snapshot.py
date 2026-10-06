from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_module.forward_position_thesis_candidate_producer import (
    ForwardPositionThesisCandidateProducer,
    SCHEMA_VERSION as FORWARD_CANDIDATE_SCHEMA_VERSION,
)
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.codec import decode_artifact
from app_module.recommendation.contracts import (
    ExecutionStatus,
    IndexStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
)
from app_module.recommendation.queries import _read_regular_file_no_follow
from app_module.recommendation.execute import (
    RecommendationPostprocessFacts,
    RecommendationPostprocessInput,
)
from app_module.recommendation.body_result import (
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
)
from app_module.recommendation.negative_evidence_projection import (
    project_canonical_negative_evidence,
)
from app_module.recommendation_service import RecommendationService
from app_module.regime_service import RegimeService
from app_module.recommendation.input_preparation import (
    build_default_recommendation_input_preparer,
)
from app_module.v4_evidence_identity import (
    DEFAULT_RETURN_BASIS,
    SCHEDULED_RECOMMENDATION_BENCHMARK_ID,
    SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
    SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS,
    SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
)
from data_module.config import TWStockConfig
from data_module.official_trading_calendar_cache import (
    OfficialCalendarCacheError,
    _normalized_flag,
    load_verified_twse_calendar_cache,
)
from scripts.scheduled.scheduled_clock import scheduled_now


TASK_NAME = "baldr-recommendation-snapshot-daily"
FORWARD_CALENDAR_REFRESH_SCHEMA_VERSION = "official-calendar-refresh-status.v1"
FORWARD_CALENDAR_REFRESH_SUCCESS_STATUSES = frozenset(
    {"cache_valid_for_forward_horizon", "refreshed"}
)
DEFAULT_FORWARD_CALENDAR_REFRESH_STATUS_PATH = (
    REPO_ROOT
    / "output"
    / "v4_ml_forward_scheduler"
    / "calendar_cache_refresh"
    / "latest_status.json"
)
TAIPEI = ZoneInfo("Asia/Taipei")
PAPER_FROZEN_SCHEMA_VERSION = "paper-frozen-recommendation.v1"
PAPER_FROZEN_PURPOSE = "paper-next-session-research-source"
PAPER_FROZEN_PORTFOLIO_ID = "paper-main"
PAPER_FROZEN_ARTIFACT_MAX_BYTES = 8 * 1024 * 1024
PAPER_FROZEN_EXPORT_MAX_BYTES = 1024 * 1024
PAPER_FROZEN_SAFETY_FIELDS = (
    "confirm",
    "writes_evidence_db",
    "auto_trading",
    "lifecycle_action",
)


def _scheduled_default_config() -> dict[str, Any]:
    return {
        "strategy_version_id": SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID,
        # These are explicit research identities, not inferred defaults.  The
        # cost model is intentionally gross/unpriced until a governed cost
        # ledger is available; the evaluator exposes that limitation.
        "cost_model_id": SCHEDULED_RECOMMENDATION_COST_MODEL_ID,
        "benchmark_id": SCHEDULED_RECOMMENDATION_BENCHMARK_ID,
        "horizon_days": SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS,
        "technical": {
            "momentum": {
                "enabled": True,
                "rsi": {"enabled": True, "period": 14},
                "macd": {"enabled": True, "fast": 12, "slow": 26, "signal": 9},
                "kd": {"enabled": False},
            },
            "volatility": {
                "enabled": False,
                "bollinger": {"enabled": False, "window": 20, "std": 2},
                "atr": {"enabled": True, "period": 14},
            },
            "trend": {
                "enabled": True,
                "adx": {"enabled": True, "period": 14},
                "ma": {"enabled": True, "windows": [5, 10, 20, 60]},
            },
        },
        "patterns": {"selected": ["旗形", "三角形", "矩形", "V形反轉"]},
        "signals": {
            "technical_indicators": ["momentum", "trend"],
            "volume_conditions": ["increasing", "spike"],
            "weights": {"pattern": "0.25", "technical": "0.55", "volume": "0.20"},
        },
        "filters": {
            "price_change_min": "2.0",
            "price_change_max": "100.0",
            "volume_ratio_min": "1.5",
            "rsi_min": 0,
            "rsi_max": 100,
            "industry": "全部",
        },
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "regime": None,
    }


def _runtime_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _runtime_config(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_runtime_config(child) for child in value]
    if isinstance(value, str):
        try:
            return float(Decimal(value))
        except Exception:  # noqa: BLE001
            return value
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_json_object(value: str, field_name: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field_name} 必須是 JSON object")
    return dict(payload)


def _snapshot_cohort_from_payload(payload: Mapping[str, Any]) -> SnapshotCohort:
    coverage_payload = payload.get("coverage_by_symbol")
    if not isinstance(coverage_payload, Mapping):
        raise ValueError("snapshot_cohort.coverage_by_symbol 必須是 object")
    coverage = {
        str(symbol): SnapshotCohortCoverage(
            status=row.get("status"),
            quality=row.get("quality"),
            stage=row.get("stage"),
            reason_codes=tuple(row.get("reason_codes") or ()),
            warnings=tuple(row.get("warnings") or ()),
        )
        for symbol, row in coverage_payload.items()
        if isinstance(row, Mapping)
    }
    if len(coverage) != len(coverage_payload):
        raise ValueError("snapshot_cohort.coverage_by_symbol 包含無效列")
    return SnapshotCohort(
        cohort_hash=str(payload["cohort_hash"]),
        requested_symbols=tuple(payload["requested_symbols"]),
        eligible_symbols=tuple(payload["eligible_symbols"]),
        missing_symbols=tuple(payload["missing_symbols"]),
        degraded_symbols=tuple(payload["degraded_symbols"]),
        excluded_symbols=tuple(payload["excluded_symbols"]),
        requested_count=payload["requested_count"],
        eligible_count=payload["eligible_count"],
        missing_count=payload["missing_count"],
        degraded_count=payload["degraded_count"],
        excluded_count=payload["excluded_count"],
        coverage_status=SnapshotCohortCoverageStatus(payload["coverage_status"]),
        coverage_by_symbol=coverage,
        eligible_definition=payload["eligible_definition"],
        missing_definition=payload["missing_definition"],
        degraded_definition=payload["degraded_definition"],
        excluded_definition=payload["excluded_definition"],
        schema_version=payload["schema_version"],
    )


def _execution_capture_summary(
    execution: RecommendationExecution,
) -> dict[str, Any]:
    """從已保存 execution 的 typed assessments 投影排程用負面證據。"""

    if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
        raise ValueError("scheduled execution 缺少 completed DecisionBatch")
    return project_canonical_negative_evidence(
        execution.decision,
        allow_empty=True,
    ).as_scheduled_summary()


def _required_identity_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"scheduled 同次 execution 缺少 {field_name}")
    return value


def _build_scheduled_postprocess_callback(
    *,
    caller_config: Mapping[str, Any],
    decision_date: str,
    max_stocks: int,
    top_n: int,
):
    """從 execute 同步 private capture 建立 scheduled post-run facts。"""

    def capture(input_value: RecommendationPostprocessInput) -> RecommendationPostprocessFacts:
        strategy = input_value.context.strategy_identity
        universe = input_value.context.universe_identity
        if strategy is None or universe is None or universe.policy is None or universe.snapshot is None:
            raise ValueError("scheduled execution 缺少同次 strategy/universe identity")

        raw_context = input_value.context.raw_context
        body_result = input_value.body_result
        typed_context = body_result.context
        typed_evidence = typed_context.evidence_identity
        if typed_evidence is None:
            raise ValueError("scheduled execution 缺少同次 typed evidence identity")
        evidence = RecommendationRunEvidenceIdentity(
            cost_model_id=typed_evidence.cost_model_id,
            benchmark_id=typed_evidence.benchmark_id,
            industry_benchmark_id=typed_evidence.industry_benchmark_id,
            horizon_days=typed_evidence.horizon_days,
            evidence_tier="forward",
            return_basis=typed_evidence.return_basis or DEFAULT_RETURN_BASIS,
        )
        legacy_evidence = RecommendationRunEvidenceIdentity(
            cost_model_id=raw_context.get("cost_model_id"),
            benchmark_id=raw_context.get("benchmark_id"),
            industry_benchmark_id=raw_context.get("industry_benchmark_id"),
            horizon_days=raw_context.get("horizon_days"),
            evidence_tier="forward",
            return_basis=raw_context.get("return_basis") or DEFAULT_RETURN_BASIS,
        )
        if evidence != legacy_evidence:
            raise ValueError("legacy/typed scheduled evidence identity parity mismatch")
        legacy_cohort_payload = _build_snapshot_cohort(
            screening_matrix=[dict(row) for row in input_value.screening_matrix],
            recommendations=list(input_value.recommendations),
        )
        cohort_payload = snapshot_cohort_payload_from_body_result(body_result)
        if _canonical_json(legacy_cohort_payload) != _canonical_json(cohort_payload):
            raise ValueError("legacy/typed snapshot cohort v1 parity mismatch")
        cohort = snapshot_cohort_from_body_result(body_result)

        typed_temporal_values = {
            "data_as_of_date": typed_context.as_of_date,
            "temporal_mode": typed_context.temporal_mode,
            "cutoff_selection": typed_context.cutoff_selection,
            "cutoff_policy": typed_context.cutoff_policy,
        }
        for key, expected in typed_temporal_values.items():
            if key in caller_config and caller_config[key] != expected:
                raise ValueError(
                    f"scheduled caller config {key} 與同次 typed BodyResult 不一致"
                )

        result_config = deepcopy(dict(caller_config))
        result_config.update(
            {
                "scheduled_snapshot": True,
                "research_only": True,
                "decision_date": decision_date,
                "date_semantics_schema": "scheduled-recommendation-date-roles.v1",
                "decision_timezone": "Asia/Taipei",
                "market_cutoff_date": typed_context.as_of_date,
                **typed_temporal_values,
                "max_stocks": max_stocks,
                "top_n": top_n,
                "profile_id": "scheduled_daily_research_default_v1",
                "profile_name": "Scheduled daily research default v1",
                "look_ahead_check": "uses latest available data at scheduled run time only",
                "snapshot_cohort": cohort_payload,
                "safety_boundary": {
                    "confirm": False,
                    "writes_evidence_db": False,
                    "auto_trading": False,
                    "lifecycle_action": False,
                },
                "strategy_version_id": _required_identity_text(
                    strategy.strategy_version_id, "strategy_version_id"
                ),
                "strategy_config_id": _required_identity_text(
                    strategy.strategy_config_id, "strategy_config_id"
                ),
                "strategy_config_hash": _required_identity_text(
                    strategy.strategy_config_hash, "strategy_config_hash"
                ),
                "strategy_config_schema": _required_identity_text(
                    strategy.strategy_config_schema, "strategy_config_schema"
                ),
                "strategy_config_spec": _load_json_object(
                    _required_identity_text(
                        strategy.strategy_config_spec_json,
                        "strategy_config_spec_json",
                    ),
                    "strategy_config_spec",
                ),
                "universe_id": _required_identity_text(
                    universe.universe_id, "universe_id"
                ),
                "universe_hash": _required_identity_text(
                    universe.universe_hash, "universe_hash"
                ),
                "universe_identity_schema": _required_identity_text(
                    universe.universe_identity_schema,
                    "universe_identity_schema",
                ),
                "universe_policy_id": _required_identity_text(
                    universe.policy.universe_policy_id,
                    "universe_policy_id",
                ),
                "universe_policy_hash": _required_identity_text(
                    universe.policy.universe_policy_hash,
                    "universe_policy_hash",
                ),
                "universe_policy_schema": _required_identity_text(
                    universe.policy.universe_policy_schema,
                    "universe_policy_schema",
                ),
                "universe_policy_spec": _load_json_object(
                    _required_identity_text(
                        universe.policy.universe_policy_spec_json,
                        "universe_policy_spec_json",
                    ),
                    "universe_policy_spec",
                ),
                "universe_snapshot_id": _required_identity_text(
                    universe.snapshot.universe_snapshot_id,
                    "universe_snapshot_id",
                ),
                "universe_snapshot_hash": _required_identity_text(
                    universe.snapshot.universe_snapshot_hash,
                    "universe_snapshot_hash",
                ),
                "universe_snapshot_schema": _required_identity_text(
                    universe.snapshot.universe_snapshot_schema,
                    "universe_snapshot_schema",
                ),
                "universe_snapshot_source_provider_id": _required_identity_text(
                    universe.snapshot.universe_snapshot_source_provider_id,
                    "universe_snapshot_source_provider_id",
                ),
                "universe_snapshot_selected_codes_hash": _required_identity_text(
                    universe.snapshot.universe_snapshot_selected_codes_hash,
                    "universe_snapshot_selected_codes_hash",
                ),
                "universe_snapshot_spec": _load_json_object(
                    _required_identity_text(
                        universe.snapshot.universe_snapshot_spec_json,
                        "universe_snapshot_spec_json",
                    ),
                    "universe_snapshot_spec",
                ),
                "cost_model_id": _required_identity_text(
                    evidence.cost_model_id, "cost_model_id"
                ),
                "benchmark_id": _required_identity_text(
                    evidence.benchmark_id, "benchmark_id"
                ),
                "horizon_days": evidence.horizon_days,
                "evidence_tier": _required_identity_text(
                    evidence.evidence_tier, "evidence_tier"
                ),
                "return_basis": _required_identity_text(
                    evidence.return_basis, "return_basis"
                ),
            }
        )
        if evidence.industry_benchmark_id is not None:
            result_config["industry_benchmark_id"] = evidence.industry_benchmark_id

        raw_result_config = _canonical_json(result_config)
        result_config_snapshot = RecommendationResultConfigSnapshot(
            raw_result_config_json=raw_result_config,
            config_sha256=_canonical_json_sha256(result_config),
        )
        return RecommendationPostprocessFacts(
            result_id=body_result.result_id,
            invocation_id=body_result.invocation_id,
            created_at=input_value.context.created_at,
            snapshot_cohort=cohort,
            evidence_identity=evidence,
            result_config_snapshot=result_config_snapshot,
        )

    return capture


def _symbol_from_value(value: Any) -> str:
    if isinstance(value, dict):
        value = (
            value.get("stock_code")
            or value.get("symbol")
            or value.get("code")
            or value.get("證券代號")
        )
    else:
        value = getattr(value, "stock_code", value)
    return str(value or "").strip()


def _build_snapshot_cohort(
    *,
    screening_matrix: list[dict[str, Any]],
    recommendations: list[Any],
) -> dict[str, Any]:
    """Persist the actual scheduled cohort, including non-selected gaps.

    The recommendation DTO only contains the selected top-N rows.  The
    screening matrix is the authoritative record of the bounded requested
    cohort, so learning can capture eligible rows without silently losing
    missing/degraded source coverage or top-N exclusions.
    """

    rows_by_symbol: dict[str, dict[str, Any]] = {}
    for row in screening_matrix:
        if not isinstance(row, dict):
            continue
        symbol = _symbol_from_value(row)
        if symbol:
            rows_by_symbol[symbol] = row

    eligible_symbols = sorted(
        {
            symbol
            for symbol in (_symbol_from_value(item) for item in recommendations)
            if symbol
        }
    )
    requested_symbols = sorted(set(rows_by_symbol) | set(eligible_symbols))
    missing_symbols = sorted(
        {
            symbol
            for symbol, row in rows_by_symbol.items()
            if str(row.get("quality") or "").lower() == "missing"
        }
    )
    degraded_symbols = sorted(
        {
            symbol
            for symbol, row in rows_by_symbol.items()
            if str(row.get("quality") or "").lower() == "degraded"
            and symbol not in set(missing_symbols)
        }
    )
    excluded_symbols = sorted(
        set(requested_symbols)
        - set(eligible_symbols)
        - set(missing_symbols)
        - set(degraded_symbols)
    )
    coverage_by_symbol = {
        symbol: {
            "status": row.get("status"),
            "quality": row.get("quality"),
            "stage": row.get("stage"),
            "reason_codes": list(row.get("reason_codes") or []),
            "warnings": list(row.get("warnings") or []),
        }
        for symbol, row in sorted(rows_by_symbol.items())
    }
    body = {
        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
        "requested_symbols": requested_symbols,
        "eligible_symbols": eligible_symbols,
        "missing_symbols": missing_symbols,
        "degraded_symbols": degraded_symbols,
        "excluded_symbols": excluded_symbols,
        "requested_count": len(requested_symbols),
        "eligible_count": len(eligible_symbols),
        "missing_count": len(missing_symbols),
        "degraded_count": len(degraded_symbols),
        "excluded_count": len(excluded_symbols),
        "coverage_status": (
            "partial"
            if missing_symbols
            else "degraded"
            if degraded_symbols
            else "complete"
        ),
        "coverage_by_symbol": coverage_by_symbol,
        "eligible_definition": "final scheduled recommendation DTO rows",
        "missing_definition": "screening rows with quality=missing; same-day retry candidates",
        "degraded_definition": "screening rows with quality=degraded; visible but not source-missing",
        "excluded_definition": "requested rows not selected and not missing/degraded",
    }
    body["cohort_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return body


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value[7:]
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True


def _read_json_mapping(path: Path, *, field_name: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field_name}_invalid_json") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field_name}_must_be_object")
    return dict(payload), "sha256:" + hashlib.sha256(raw).hexdigest()


def _parse_aware_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name}_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _calendar_year_from_cache(path: Path, *, fallback: int) -> int:
    """Read the cache's declared year without selecting another cache file."""

    try:
        payload, _ = _read_json_mapping(path, field_name="forward_calendar_cache")
    except (OSError, ValueError):
        return fallback
    year = payload.get("calendar_year")
    if isinstance(year, bool) or not isinstance(year, int):
        return fallback
    return year


def _verify_calendar_observation(
    *,
    path: Path,
    calendar_year: int,
    observed_at: datetime,
    decision_at: datetime,
    expected_file_sha256: str | None = None,
) -> tuple[str, dict[str, Any]]:
    resolved = path.expanduser().resolve()
    actual_file_sha256 = _sha256_file(resolved)
    if expected_file_sha256 is not None and actual_file_sha256 != expected_file_sha256:
        raise ValueError("forward_calendar_refresh_selected_cache_hash_mismatch")
    verified = load_verified_twse_calendar_cache(
        resolved,
        calendar_year=calendar_year,
        observed_at=observed_at.astimezone(timezone.utc),
    )
    evidence = dict(verified.evidence)
    evidence_path = Path(str(evidence.get("path") or "")).expanduser().resolve()
    if evidence_path != resolved:
        raise ValueError("forward_calendar_refresh_verified_path_mismatch")
    if evidence.get("cache_file_sha256") != actual_file_sha256:
        raise ValueError("forward_calendar_refresh_verified_hash_mismatch")
    captured_at = _parse_aware_timestamp(
        evidence.get("captured_at"),
        "forward_calendar_observation_captured_at",
    )
    if captured_at > decision_at.astimezone(timezone.utc):
        raise ValueError(
            "forward_calendar_observation_captured_after_decision_at"
        )
    return actual_file_sha256, evidence


def _refresh_calendar_nodes(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Collect the selected cache shape from either refresh terminal status."""

    nodes: list[Mapping[str, Any]] = []
    inspection = payload.get("inspection")
    if isinstance(inspection, Mapping):
        selected = inspection.get("selected")
        if isinstance(selected, Mapping):
            nodes.append(selected)
    inspections = payload.get("inspections")
    if isinstance(inspections, Mapping):
        for item in inspections.values():
            if not isinstance(item, Mapping):
                continue
            selected = item.get("selected")
            if isinstance(selected, Mapping):
                nodes.append(selected)
    refresh_verification = payload.get("refresh_verification")
    if isinstance(refresh_verification, Mapping):
        nodes.append(refresh_verification)
    refresh = payload.get("refresh")
    if isinstance(refresh, Mapping):
        verified = refresh.get("verified")
        if isinstance(verified, Mapping):
            nodes.append(verified)
        nodes.append(refresh)
    return nodes


def _resolve_forward_calendar_cache(
    *,
    explicit_path: str | Path | None,
    refresh_status_path: str | Path | None,
    observed_at: datetime,
    decision_at: datetime | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    """Resolve the exact current calendar selected by the refresh receipt.

    The approved policy's ``calendar_cache_path`` is an immutable historical
    pin.  The scheduled refresh owns a separate current observation.  This
    resolver only reads that receipt and revalidates the selected file; it
    never scans a directory or silently chooses an older cache.
    """

    observed_utc = observed_at.astimezone(timezone.utc)
    decision_utc = (
        observed_utc
        if decision_at is None
        else decision_at.astimezone(timezone.utc)
    )
    if decision_utc > observed_utc:
        return None, {
            "status": "blocked",
            "selection_source": "forward_calendar_observation",
            "blocker": "forward_calendar_observation_decision_at_in_future",
        }

    if explicit_path is not None and str(explicit_path).strip():
        resolved = Path(explicit_path).expanduser().resolve()
        try:
            calendar_year = _calendar_year_from_cache(
                resolved,
                fallback=decision_utc.astimezone(TAIPEI).year,
            )
            actual_file_sha256, evidence = _verify_calendar_observation(
                path=resolved,
                calendar_year=calendar_year,
                observed_at=observed_utc,
                decision_at=decision_utc,
            )
            return resolved, {
                "status": "explicit_path_verified",
                "selection_source": "forward_calendar_cache_path_argument",
                "calendar_year": calendar_year,
                "path": str(resolved),
                "file_sha256": actual_file_sha256,
                "content_sha256": evidence.get("cache_content_sha256"),
                "captured_at": evidence.get("captured_at"),
                "expires_at": evidence.get("expires_at"),
            }
        except (OSError, TypeError, ValueError, OfficialCalendarCacheError) as error:
            return None, {
                "status": "blocked",
                "selection_source": "forward_calendar_cache_path_argument",
                "path": str(resolved),
                "blocker": (
                    "forward_calendar_observation_unusable:"
                    f"{type(error).__name__}:{error}"
                ),
            }

    env_status_root = os.environ.get("ML_FORWARD_CALENDAR_REFRESH_STATUS_ROOT")
    status_path = (
        Path(refresh_status_path).expanduser().resolve()
        if refresh_status_path is not None
        else (
            Path(env_status_root).expanduser().resolve() / "latest_status.json"
            if isinstance(env_status_root, str) and env_status_root.strip()
            else DEFAULT_FORWARD_CALENDAR_REFRESH_STATUS_PATH
        )
    )
    try:
        payload, status_file_sha256 = _read_json_mapping(
            status_path,
            field_name="forward_calendar_refresh_status",
        )
        if payload.get("schema_version") != FORWARD_CALENDAR_REFRESH_SCHEMA_VERSION:
            raise ValueError("forward_calendar_refresh_status_schema_invalid")
        refresh_status = payload.get("status")
        if refresh_status not in FORWARD_CALENDAR_REFRESH_SUCCESS_STATUSES:
            raise ValueError(
                f"forward_calendar_refresh_status_not_usable:{refresh_status}"
            )
        for field, expected in (
            ("candidate_only", True),
            ("read_only", True),
            ("forward_child_started", False),
            ("forward_credit_granted", False),
            ("production_action_allowed", False),
            ("broker_order_allowed", False),
        ):
            if payload.get(field) is not expected:
                raise ValueError(f"forward_calendar_refresh_{field}_boundary_invalid")
        cache_root_value = payload.get("cache_root")
        if not isinstance(cache_root_value, str) or not cache_root_value.strip():
            raise ValueError("forward_calendar_refresh_cache_root_missing")
        cache_root = Path(cache_root_value).expanduser().resolve()

        selected: Mapping[str, Any] | None = None
        for node in _refresh_calendar_nodes(payload):
            path_value = node.get("path") or node.get("capture_path")
            hash_value = node.get("file_sha256") or node.get("cache_file_sha256")
            if (
                isinstance(path_value, str)
                and path_value.strip()
                and _is_sha256(hash_value)
            ):
                selected = node
                break
        if selected is None:
            raise ValueError("forward_calendar_refresh_selected_cache_missing")

        path_value = selected.get("path") or selected.get("capture_path")
        expected_file_sha256 = selected.get("file_sha256") or selected.get(
            "cache_file_sha256"
        )
        year_value = selected.get("calendar_year", payload.get("calendar_year"))
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("forward_calendar_refresh_selected_cache_path_invalid")
        if not _is_sha256(expected_file_sha256):
            raise ValueError("forward_calendar_refresh_selected_cache_hash_invalid")
        if isinstance(year_value, bool) or not isinstance(year_value, int):
            raise ValueError("forward_calendar_refresh_selected_cache_year_invalid")
        selected_path = Path(path_value).expanduser().resolve()
        try:
            selected_path.relative_to(cache_root)
        except ValueError as error:
            raise ValueError(
                "forward_calendar_refresh_selected_cache_root_mismatch"
            ) from error
        actual_file_sha256 = _sha256_file(selected_path)
        if actual_file_sha256 != expected_file_sha256:
            raise ValueError("forward_calendar_refresh_selected_cache_hash_mismatch")
        actual_file_sha256, evidence = _verify_calendar_observation(
            path=selected_path,
            calendar_year=year_value,
            observed_at=observed_utc,
            decision_at=decision_utc,
            expected_file_sha256=expected_file_sha256,
        )
        return selected_path, {
            "status": "verified_refresh_receipt",
            "selection_source": "official_calendar_refresh_latest_status",
            "refresh_status": refresh_status,
            "refresh_status_path": str(status_path),
            "refresh_status_file_sha256": status_file_sha256,
            "calendar_year": year_value,
            "path": str(selected_path),
            "file_sha256": actual_file_sha256,
            "content_sha256": evidence.get("cache_content_sha256"),
            "captured_at": evidence.get("captured_at"),
            "expires_at": evidence.get("expires_at"),
        }
    except (OSError, TypeError, ValueError, OfficialCalendarCacheError) as error:
        return None, {
            "status": "blocked",
            "selection_source": "official_calendar_refresh_latest_status",
            "refresh_status_path": str(status_path),
            "blocker": f"forward_calendar_refresh_unusable:{type(error).__name__}:{error}",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scheduled research-only recommendation snapshot wrapper.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--current-fundamental-source-root",
        type=Path,
        default=None,
        help=(
            "canonical output root containing current official valuation and "
            "MOPS monthly captures; independent of recommendation artifact output-root"
        ),
    )
    parser.add_argument("--max-stocks", type=int, default=200)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument(
        "--forward-candidate-output-root",
        help="repository-isolated output for forward thesis candidate packets",
    )
    parser.add_argument(
        "--forward-thesis-policy-path",
        help="optional explicit versioned invalidation/horizon policy JSON",
    )
    parser.add_argument(
        "--forward-calendar-cache-path",
        help="optional official calendar cache path used by the policy validator",
    )
    parser.add_argument(
        "--forward-calendar-refresh-status-path",
        help="optional latest official-calendar refresh receipt used to select the current cache",
    )
    parser.add_argument(
        "--export-paper-frozen-source",
        action="store_true",
        help="選擇輸出當日 Paper 專用 create-only 研究來源",
    )
    return parser


def _resolve_current_fundamental_source_root(
    *,
    data_root: Path,
    explicit_root: Path | None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve current PE/monthly source root independently of snapshot output."""

    if explicit_root is not None:
        return explicit_root.expanduser().resolve()
    env = os.environ if environ is None else environ
    configured_root = str(env.get("CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT", "")).strip()
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    # Recreate the normal TWStockConfig output-root resolution without using
    # this CLI's artifact --output-root override.
    canonical_config = TWStockConfig(data_root=data_root)
    return Path(canonical_config.output_root).expanduser().resolve()


def _payload_base(
    *,
    output_root: Path,
    decision_date: str,
    status_path: Path,
    log_path: Path,
    checked_at: str,
) -> dict[str, Any]:
    return {
        "task": TASK_NAME,
        "status": "running",
        "decision_date": decision_date,
        "checked_at": checked_at,
        "status_path": str(status_path),
        "log_path": str(log_path),
        "output_root": str(output_root),
        "confirm": False,
        "writes_recommendation_result": False,
        "writes_evidence_db": False,
        "auto_trading": False,
        "lifecycle_action": False,
    }


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _recommendation_decision_at(path: Path) -> datetime:
    payload, _ = _read_json_mapping(path, field_name="recommendation_result")
    run_context = payload.get("run_context")
    if not isinstance(run_context, Mapping):
        raise ValueError("recommendation_run_context_missing")
    return _parse_aware_timestamp(
        run_context.get("decision_at"),
        "recommendation_decision_at",
    )


def _write_blocked_forward_candidate_receipt(
    *,
    output_root: str | Path,
    source_path: Path,
    result_id: str,
    decision_date: str,
    decision_at: datetime | None,
    calendar_observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist a zero-candidate receipt without starting the producer.

    This is deliberately kept in the scheduled caller: a blocked calendar
    observation must not instantiate the candidate producer, whose optional
    policy path could otherwise validate an older pinned calendar.
    """

    resolved_root = Path(output_root).expanduser().resolve()
    source_hash: str | None
    try:
        source_hash = _sha256_file(source_path)
    except OSError:
        source_hash = None
    observation = dict(calendar_observation)
    blocker = str(
        observation.get("blocker")
        or "forward_calendar_observation_unusable"
    )
    receipt: dict[str, Any] = {
        "schema_version": FORWARD_CANDIDATE_SCHEMA_VERSION,
        "operation": "produce",
        "status": "blocked",
        "result_id": result_id,
        "decision_date": decision_date,
        "decision_at": (
            None if decision_at is None else decision_at.astimezone(timezone.utc).isoformat()
        ),
        "recommendation_source": {
            "path": str(source_path),
            "file_sha256": source_hash,
        },
        "candidate_count": 0,
        "candidates": [],
        "warnings": [],
        "blockers": [f"forward_calendar_observation_blocked:{blocker}"],
        "calendar_observation": observation,
        "candidate_only": True,
        "human_approval_required": True,
        "auto_action_allowed": False,
        "research_only": True,
        "writes_paper_state": False,
        "writes_formal_state": False,
        "writes_broker": False,
        "producer_started": False,
    }
    receipt_root = resolved_root / "receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt_hash = hashlib.sha256(encoded).hexdigest()[:20]
    target = receipt_root / f"blocked_{decision_date.replace('-', '')}_{receipt_hash}.json"
    if not target.exists():
        target.write_bytes(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            + b"\n"
        )
    latest = dict(receipt)
    latest["receipt_path"] = str(target)
    _write_status(resolved_root / "latest_status.json", latest)
    return latest


def _read_verified_saved_execution(
    *,
    composition: Any,
    execution: Any,
    receipt: Any,
) -> Any:
    """要求同一 execution 的 create-only receipt 與 canonical query readback 完全一致。"""

    if execution.status is not ExecutionStatus.COMPLETED:
        raise RuntimeError(
            f"recommendation_execution_not_completed:{execution.status.value}"
        )
    if receipt.result_id != execution.result_id:
        raise ValueError("recommendation_save_receipt_result_id_mismatch")
    if receipt.index_status is not IndexStatus.INDEXED:
        raise ValueError("recommendation_execution_save_not_indexed")
    if not receipt.artifact_location:
        raise ValueError("recommendation_execution_save_artifact_location_missing")

    read_model = composition.queries.get(execution.result_id)
    if read_model is None:
        raise ValueError("recommendation_execution_query_readback_missing")
    if read_model.execution is None or read_model.legacy_result is not None:
        raise ValueError("recommendation_execution_query_readback_not_canonical")
    saved = read_model.execution
    if saved != execution:
        raise ValueError("recommendation_execution_query_readback_payload_mismatch")
    if read_model.result_id != receipt.result_id:
        raise ValueError("recommendation_execution_query_result_id_mismatch")
    if read_model.payload_hash != receipt.payload_hash:
        raise ValueError("recommendation_execution_query_payload_hash_mismatch")
    if read_model.artifact_location != receipt.artifact_location:
        raise ValueError("recommendation_execution_query_artifact_location_mismatch")
    if read_model.integrity_basis != "canonical_payload_and_index_verified":
        raise ValueError("recommendation_execution_query_integrity_not_verified")

    request_snapshot = saved.request.config_snapshot
    if request_snapshot is None or execution.request.config_snapshot is None:
        raise ValueError("recommendation_execution_caller_config_snapshot_missing")
    if request_snapshot != execution.request.config_snapshot:
        raise ValueError("recommendation_execution_caller_config_snapshot_changed")
    result_config_snapshot = saved.context.result_config_snapshot
    if result_config_snapshot is None:
        raise ValueError("recommendation_execution_result_config_snapshot_missing")
    if result_config_snapshot != execution.context.result_config_snapshot:
        raise ValueError("recommendation_execution_result_config_snapshot_changed")
    if saved.context.decision_at != execution.context.decision_at:
        raise ValueError("recommendation_execution_decision_clock_changed")
    if saved.context.available_at != execution.context.available_at:
        raise ValueError("recommendation_execution_available_clock_changed")
    return read_model


def _strict_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name}_invalid_sha256")
    return value


def _aware_source_clock(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name}_missing_or_naive")
    return value


def _paper_frozen_result_id_component(result_id: object) -> str:
    if (
        not isinstance(result_id, str)
        or not result_id
        or len(result_id) > 160
        or result_id in {".", ".."}
        or result_id[-1] in {".", " "}
        or any(
            not character.isascii()
            or not (character.isalnum() or character in "._-")
            for character in result_id
        )
    ):
        raise ValueError("paper_frozen_result_id_is_not_safe_for_filename")
    return result_id


def _paper_decimal_text(value: object, field_name: str) -> str:
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError(f"paper_frozen_{field_name}_not_finite")
        return str(value)
    if type(value) is int:
        return str(value)
    raise ValueError(f"paper_frozen_{field_name}_missing_or_untyped")


def _build_paper_frozen_source_payload(
    *,
    read_model: Any,
    receipt: Any,
    raw_artifact: bytes,
    artifact_location: str,
    exported_at: datetime,
    calendar_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """從已驗證的 canonical execution 建立 Paper 專用唯讀來源投影。"""

    execution = read_model.execution
    if (
        read_model.integrity_basis != "canonical_payload_and_index_verified"
        or execution is None
        or read_model.legacy_result is not None
        or execution.status is not ExecutionStatus.COMPLETED
        or execution.decision is None
    ):
        raise ValueError("paper_frozen_source_must_be_verified_completed_canonical")
    result_id = _required_identity_text(execution.result_id, "result_id")
    if receipt.result_id != result_id or read_model.result_id != result_id:
        raise ValueError("paper_frozen_source_result_id_mismatch")
    if receipt.index_status is not IndexStatus.INDEXED:
        raise ValueError("paper_frozen_source_not_indexed")
    if receipt.artifact_location != artifact_location:
        raise ValueError("paper_frozen_source_artifact_location_mismatch")
    source_payload_hash = _strict_sha256(receipt.payload_hash, "source_payload_hash")
    if _strict_sha256(read_model.payload_hash, "read_model_payload_hash") != source_payload_hash:
        raise ValueError("paper_frozen_source_payload_hash_mismatch")
    source_artifact_hash = "sha256:" + hashlib.sha256(raw_artifact).hexdigest()
    if (
        _strict_sha256(read_model.raw_artifact_sha256, "read_model_artifact_hash")
        != source_artifact_hash
    ):
        raise ValueError("paper_frozen_source_artifact_hash_mismatch")
    decoded = decode_artifact(raw_artifact, expected_sha256=source_artifact_hash)
    if not isinstance(decoded, RecommendationExecution) or decoded != execution:
        raise ValueError("paper_frozen_source_artifact_execution_mismatch")

    context = execution.context
    source_created_at = _aware_source_clock(context.created_at, "source_created_at")
    decision_at = _aware_source_clock(context.decision_at, "source_decision_at")
    available_at = _aware_source_clock(context.available_at, "source_available_at")
    observed_at = _aware_source_clock(exported_at, "paper_frozen_exported_at")
    if source_created_at > observed_at:
        raise ValueError("paper_frozen_source_created_after_export_observation")
    if available_at > observed_at:
        raise ValueError("paper_frozen_source_available_after_export_observation")
    if available_at > decision_at:
        raise ValueError("paper_frozen_source_available_after_decision")
    if decision_at > observed_at:
        raise ValueError("paper_frozen_source_decision_after_export_observation")

    result_config_snapshot = context.result_config_snapshot
    if result_config_snapshot is None:
        raise ValueError("paper_frozen_source_result_config_missing")
    result_config = _load_json_object(
        result_config_snapshot.raw_result_config_json,
        "paper_frozen_source_result_config",
    )
    if _canonical_json_sha256(result_config) != result_config_snapshot.config_sha256:
        raise ValueError("paper_frozen_source_result_config_hash_mismatch")
    if result_config.get("scheduled_snapshot") is not True:
        raise ValueError("paper_frozen_source_not_scheduled_snapshot")
    if result_config.get("research_only") is not True:
        raise ValueError("paper_frozen_source_not_research_only")
    safety_boundary = result_config.get("safety_boundary")
    if not isinstance(safety_boundary, Mapping) or any(
        safety_boundary.get(field_name) is not False
        for field_name in PAPER_FROZEN_SAFETY_FIELDS
    ):
        raise ValueError("paper_frozen_source_safety_boundary_invalid")

    decision_date_value = result_config.get("decision_date")
    if not isinstance(decision_date_value, str):
        raise ValueError("paper_frozen_source_decision_date_missing")
    try:
        decision_date = date.fromisoformat(decision_date_value)
    except ValueError as exc:
        raise ValueError("paper_frozen_source_decision_date_invalid") from exc
    if decision_date.isoformat() != decision_date_value:
        raise ValueError("paper_frozen_source_decision_date_not_canonical")
    if (
        decision_at.astimezone(TAIPEI).date() != decision_date
        or observed_at.astimezone(TAIPEI).date() != decision_date
    ):
        raise ValueError("paper_frozen_source_taipei_natural_date_mismatch")

    as_of_date = context.as_of_date
    if type(as_of_date) is not date:
        raise ValueError("paper_frozen_source_as_of_date_missing")
    if as_of_date > decision_date:
        raise ValueError("paper_frozen_source_as_of_date_after_decision_date")
    top_n = result_config.get("top_n")
    if type(top_n) is not int or top_n <= 0:
        raise ValueError("paper_frozen_source_top_n_invalid")
    profile_id = result_config.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("paper_frozen_source_profile_id_missing")

    items = execution.decision.items
    if not items:
        raise ValueError("paper_frozen_source_has_no_recommendation_rows")
    rows: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for item in items:
        symbol = _required_identity_text(item.stock_code, "recommendation_stock_code")
        if (
            not symbol.isdigit()
            or not 2 <= len(symbol) <= 6
            or symbol in seen_symbols
        ):
            raise ValueError("paper_frozen_source_stock_code_invalid_or_duplicated")
        seen_symbols.add(symbol)
        eligible_date = item.eligible_universe_date
        if type(eligible_date) is not date or eligible_date != decision_date:
            raise ValueError("paper_frozen_source_eligible_date_mismatch")
        score_text = _paper_decimal_text(item.rule_score, "rule_score")
        score = Decimal(score_text)
        if score < 0 or score > 100:
            raise ValueError("paper_frozen_source_rule_score_outside_0_100")
        close_price_text = _paper_decimal_text(item.close_price, "close_price")
        if Decimal(close_price_text) <= 0:
            raise ValueError("paper_frozen_source_close_price_not_positive")
        for optional_text, field_name in (
            (item.stock_name, "stock_name"),
            (item.industry, "industry"),
        ):
            if optional_text is not None and not isinstance(optional_text, str):
                raise ValueError(f"paper_frozen_source_{field_name}_invalid")
        rows.append(
            {
                "證券代號": symbol,
                "證券名稱": item.stock_name or symbol,
                "產業": item.industry or "",
                "總分": score_text,
                "收盤價": close_price_text,
                "eligible_universe_date": eligible_date.isoformat(),
            }
        )

    artifact_relative_path = f"execution_artifacts/{artifact_location}"
    schema_version = read_model.schema_version
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise ValueError("paper_frozen_source_schema_version_missing")
    schema_revision = read_model.schema_revision
    if type(schema_revision) is not int or schema_revision <= 0:
        raise ValueError("paper_frozen_source_schema_revision_invalid")
    return {
        "schema_version": PAPER_FROZEN_SCHEMA_VERSION,
        "purpose": PAPER_FROZEN_PURPOSE,
        "result_id": result_id,
        # Paper 的 created_at 是凍結決策時鐘；保留 canonical decision_at 原值。
        "created_at": decision_at.isoformat(),
        "decision_at": decision_at.isoformat(),
        "available_at": available_at.isoformat(),
        "decision_date": decision_date.isoformat(),
        "data_as_of_date": as_of_date.isoformat(),
        "source_created_at": source_created_at.isoformat(),
        "exported_at": observed_at.isoformat(),
        "config": {
            "research_only": True,
            "portfolio_id": PAPER_FROZEN_PORTFOLIO_ID,
            "profile_id": profile_id,
            "decision_date": decision_date.isoformat(),
            "top_n": top_n,
            "formal_credit": False,
            "safety_boundary": {field: False for field in PAPER_FROZEN_SAFETY_FIELDS},
        },
        "recommendations": rows,
        "source": {
            "task": TASK_NAME,
            "result_id": result_id,
            "status": execution.status.value,
            "artifact_path": artifact_relative_path,
            "artifact_sha256": source_artifact_hash,
            "canonical_payload_hash": source_payload_hash,
            "schema_version": schema_version,
            "schema_revision": schema_revision,
            "source_created_at": source_created_at.isoformat(),
            "decision_at": decision_at.isoformat(),
            "available_at": available_at.isoformat(),
            "data_as_of_date": as_of_date.isoformat(),
        },
        "calendar": dict(calendar_identity),
        "provenance": {
            "producer": "run_scheduled_recommendation_snapshot",
            "contract": "canonical_execution_to_paper_frozen_source.v1",
            "source_result_id": result_id,
            "source_artifact_path": artifact_relative_path,
            "source_artifact_sha256": source_artifact_hash,
            "source_canonical_payload_hash": source_payload_hash,
            "source_created_at": source_created_at.isoformat(),
            "source_available_at": available_at.isoformat(),
            "export_observation": "current_scheduled_clock",
            "official_annual_calendar": dict(calendar_identity),
            "research_only": True,
            "formal_credit": False,
        },
    }


def _paper_frozen_json_bytes(payload: Mapping[str, Any]) -> bytes:
    raw = (_canonical_json(payload) + "\n").encode("utf-8")
    if len(raw) > PAPER_FROZEN_EXPORT_MAX_BYTES:
        raise ValueError("paper_frozen_export_exceeds_size_limit")
    return raw


def _verified_paper_calendar_observation(
    *,
    calendar_path: Path | None,
    calendar_observation: Mapping[str, Any] | None,
    decision_date: date,
    observed_at: datetime,
) -> tuple[bool | None, dict[str, Any]]:
    """重驗既有 resolver 選出的官方年表，回傳排定開市／休市或阻塞。"""

    if not isinstance(calendar_observation, Mapping):
        return None, {
            "status": "blocked",
            "reason": "paper_frozen_official_calendar_observation_missing",
        }
    observation_status = calendar_observation.get("status")
    if observation_status not in {
        "explicit_path_verified",
        "verified_refresh_receipt",
    }:
        return None, {
            "status": "blocked",
            "reason": "paper_frozen_official_calendar_observation_unverified",
            "observation_status": observation_status,
            "blocker": calendar_observation.get("blocker"),
        }
    if calendar_path is None:
        return None, {
            "status": "blocked",
            "reason": "paper_frozen_official_calendar_path_missing",
            "blocker": calendar_observation.get("blocker"),
        }
    expected_year = calendar_observation.get("calendar_year")
    expected_file_hash = calendar_observation.get("file_sha256")
    expected_path = calendar_observation.get("path")
    if (
        isinstance(expected_year, bool)
        or not isinstance(expected_year, int)
        or expected_year != decision_date.year
        or not isinstance(expected_file_hash, str)
        or not _is_sha256(expected_file_hash)
        or not isinstance(expected_path, str)
        or not expected_path.strip()
    ):
        return None, {
            "status": "blocked",
            "reason": "paper_frozen_official_calendar_identity_invalid",
        }
    try:
        selected_path = Path(calendar_path).expanduser().resolve(strict=True)
        observed_path = Path(expected_path).expanduser().resolve(strict=True)
        if selected_path != observed_path:
            raise ValueError("paper_frozen_official_calendar_path_mismatch")
        verified = load_verified_twse_calendar_cache(
            selected_path,
            calendar_year=decision_date.year,
            observed_at=observed_at,
        )
        evidence = verified.evidence
        actual_file_hash = evidence.get("cache_file_sha256")
        if (
            verified.calendar_year != decision_date.year
            or actual_file_hash != expected_file_hash
            or evidence.get("path") != str(selected_path)
        ):
            raise ValueError("paper_frozen_official_calendar_readback_mismatch")
        is_open = _normalized_flag(decision_date, verified.schedule)
    except (OSError, TypeError, ValueError, OfficialCalendarCacheError) as error:
        return None, {
            "status": "blocked",
            "reason": (
                "paper_frozen_official_calendar_revalidation_failed:"
                f"{type(error).__name__}:{error}"
            ),
            "path": str(calendar_path),
            "file_sha256": expected_file_hash,
        }
    return is_open, {
        "status": "verified",
        "calendar_year": verified.calendar_year,
        "path": str(selected_path),
        "file_sha256": actual_file_hash,
        "content_sha256": evidence.get("cache_content_sha256"),
        "captured_at": evidence.get("captured_at"),
        "expires_at": evidence.get("expires_at"),
        "observation_status": observation_status,
    }


def _validate_existing_paper_frozen_export(
    *,
    raw: bytes,
    expected_payload: Mapping[str, Any],
    observed_at: datetime,
) -> tuple[dict[str, Any], datetime]:
    try:
        existing_value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("paper_frozen_existing_export_invalid_json") from exc
    if not isinstance(existing_value, Mapping):
        raise ValueError("paper_frozen_existing_export_not_object")
    existing = dict(existing_value)
    if existing.get("schema_version") != PAPER_FROZEN_SCHEMA_VERSION:
        raise ValueError("paper_frozen_existing_export_schema_mismatch")
    if existing.get("purpose") != PAPER_FROZEN_PURPOSE:
        raise ValueError("paper_frozen_existing_export_purpose_mismatch")
    existing_config = existing.get("config")
    if not isinstance(existing_config, Mapping):
        raise ValueError("paper_frozen_existing_export_config_missing")
    existing_safety = existing_config.get("safety_boundary")
    if (
        existing_config.get("research_only") is not True
        or existing_config.get("portfolio_id") != PAPER_FROZEN_PORTFOLIO_ID
        or not isinstance(existing_safety, Mapping)
        or any(existing_safety.get(field_name) is not False for field_name in PAPER_FROZEN_SAFETY_FIELDS)
    ):
        raise ValueError("paper_frozen_existing_export_safety_invalid")
    if any(
        existing.get(field_name) != expected_payload.get(field_name)
        for field_name in (
            "result_id",
            "created_at",
            "decision_at",
            "available_at",
            "decision_date",
            "data_as_of_date",
            "source_created_at",
            "config",
            "recommendations",
            "source",
            "calendar",
            "provenance",
        )
    ):
        raise ValueError("paper_frozen_existing_export_source_or_projection_mismatch")
    existing_exported_value = existing.get("exported_at")
    if not isinstance(existing_exported_value, str) or not existing_exported_value.strip():
        raise ValueError("paper_frozen_existing_exported_at_missing")
    try:
        existing_exported_at = datetime.fromisoformat(
            existing_exported_value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("paper_frozen_existing_exported_at_invalid") from exc
    if existing_exported_at.tzinfo is None or existing_exported_at.utcoffset() is None:
        raise ValueError("paper_frozen_existing_exported_at_must_be_aware")
    source_available_at = _parse_aware_timestamp(
        expected_payload.get("available_at"),
        "paper_frozen_source_available_at",
    )
    source_decision_at = _parse_aware_timestamp(
        expected_payload.get("decision_at"),
        "paper_frozen_source_decision_at",
    )
    decision_date = date.fromisoformat(str(expected_payload.get("decision_date")))
    if (
        existing_exported_at < source_available_at
        or existing_exported_at < source_decision_at
        or existing_exported_at > observed_at
        or existing_exported_at.astimezone(TAIPEI).date() != decision_date
        or observed_at.astimezone(TAIPEI).date() != decision_date
    ):
        raise ValueError("paper_frozen_existing_export_clock_invalid")
    expected = dict(expected_payload)
    expected["exported_at"] = existing_exported_at.isoformat()
    if _paper_frozen_json_bytes(expected) != raw:
        raise ValueError("paper_frozen_existing_export_bytes_conflict")
    return existing, existing_exported_at


def _export_paper_frozen_source(
    *,
    composition: Any,
    read_model: Any,
    receipt: Any,
    observed_at: datetime,
    calendar_path: Path | None,
    calendar_observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """只將已保存完成的 canonical 結果 create-only 輸出至 Paper 專用檔。"""

    observed = _aware_source_clock(observed_at, "paper_frozen_export_observed_at")
    execution = read_model.execution
    if execution is None or execution.context.result_config_snapshot is None:
        return {
            "status": "blocked",
            "reason": "paper_frozen_source_result_config_missing",
        }
    result_config = _load_json_object(
        execution.context.result_config_snapshot.raw_result_config_json,
        "paper_frozen_source_result_config",
    )
    if _canonical_json_sha256(result_config) != execution.context.result_config_snapshot.config_sha256:
        return {
            "status": "blocked",
            "reason": "paper_frozen_source_result_config_hash_mismatch",
        }
    decision_date_value = result_config.get("decision_date")
    if not isinstance(decision_date_value, str):
        return {
            "status": "blocked",
            "reason": "paper_frozen_source_decision_date_missing",
        }
    try:
        decision_date = date.fromisoformat(decision_date_value)
    except (TypeError, ValueError):
        return {
            "status": "blocked",
            "reason": "paper_frozen_source_decision_date_invalid",
        }
    if decision_date.isoformat() != decision_date_value:
        return {
            "status": "blocked",
            "reason": "paper_frozen_source_decision_date_not_canonical",
        }
    is_planned_open, calendar_identity = _verified_paper_calendar_observation(
        calendar_path=calendar_path,
        calendar_observation=calendar_observation,
        decision_date=decision_date,
        observed_at=observed,
    )
    if is_planned_open is None:
        return {
            "status": "blocked",
            "reason": calendar_identity.get("reason", "paper_frozen_calendar_blocked"),
            "calendar": calendar_identity,
        }
    if not is_planned_open:
        return {
            "status": "skipped_non_trading_day",
            "decision_date": decision_date.isoformat(),
            "calendar": calendar_identity,
            "reason": "official_annual_calendar_confirms_non_trading_day",
        }
    store = composition.store
    if not store._ensure_layout():
        raise ValueError("paper_frozen_recommendation_runs_root_missing")
    runs_root = Path(os.path.abspath(composition.runs_dir))
    if (
        Path(os.path.abspath(store.artifact_root.parent)) != runs_root
        or Path(os.path.abspath(store.database_path.parent)) != runs_root
    ):
        raise ValueError("paper_frozen_source_store_root_mismatch")
    if store._is_symlink_or_reparse(runs_root):
        raise ValueError("paper_frozen_recommendation_runs_root_is_reparse")
    try:
        if Path(os.path.abspath(runs_root.resolve(strict=True))) != runs_root:
            raise ValueError("paper_frozen_recommendation_runs_root_not_canonical")
    except OSError as exc:
        raise ValueError("paper_frozen_recommendation_runs_root_unavailable") from exc

    result_id = _required_identity_text(read_model.result_id, "result_id")
    artifact_location = receipt.artifact_location
    expected_location = store.artifact_name_for(result_id)
    if (
        not isinstance(artifact_location, str)
        or artifact_location != expected_location
        or Path(artifact_location).name != artifact_location
    ):
        raise ValueError("paper_frozen_source_artifact_location_invalid")
    artifact_path = store.artifact_root / artifact_location
    raw_artifact = _read_regular_file_no_follow(
        artifact_path,
        Path(os.path.abspath(store.artifact_root)),
        max_bytes=PAPER_FROZEN_ARTIFACT_MAX_BYTES,
    )
    payload = _build_paper_frozen_source_payload(
        read_model=read_model,
        receipt=receipt,
        raw_artifact=raw_artifact,
        artifact_location=artifact_location,
        exported_at=observed,
        calendar_identity=calendar_identity,
    )
    target_name = f"paper_frozen_{_paper_frozen_result_id_component(result_id)}.json"
    target_path = runs_root / target_name
    if target_path.parent != runs_root:
        raise ValueError("paper_frozen_export_target_outside_runs_root")
    payload_bytes = _paper_frozen_json_bytes(payload)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".paper-frozen-",
            suffix=".tmp",
            dir=runs_root,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, target_path, follow_symlinks=False)
        except FileExistsError:
            existing_raw = _read_regular_file_no_follow(
                target_path,
                runs_root,
                max_bytes=PAPER_FROZEN_EXPORT_MAX_BYTES,
            )
            existing_payload, existing_exported_at = _validate_existing_paper_frozen_export(
                raw=existing_raw,
                expected_payload=payload,
                observed_at=observed,
            )
            return {
                "status": "reused",
                "result_id": result_id,
                "path": str(target_path),
                "source_artifact_sha256": payload["source"]["artifact_sha256"],
                "canonical_payload_hash": payload["source"]["canonical_payload_hash"],
                "paper_file_sha256": "sha256:" + hashlib.sha256(existing_raw).hexdigest(),
                "exported_at": existing_exported_at.isoformat(),
                "calendar": dict(calendar_identity),
            }
        published_raw = _read_regular_file_no_follow(
            target_path,
            runs_root,
            max_bytes=PAPER_FROZEN_EXPORT_MAX_BYTES,
        )
        if published_raw != payload_bytes:
            raise ValueError("paper_frozen_created_export_readback_bytes_mismatch")
        published_hash = "sha256:" + hashlib.sha256(published_raw).hexdigest()
        if os.name != "nt":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            directory_fd = os.open(runs_root, flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return {
        "status": "created",
        "result_id": result_id,
        "path": str(target_path),
        "source_artifact_sha256": payload["source"]["artifact_sha256"],
        "canonical_payload_hash": payload["source"]["canonical_payload_hash"],
        "paper_file_sha256": published_hash,
        "exported_at": payload["exported_at"],
        "calendar": dict(calendar_identity),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.output_root)
    data_root = Path(args.data_root).expanduser().resolve()
    run_root = output_root / "scheduled" / "recommendation_snapshot"
    run_root.mkdir(parents=True, exist_ok=True)

    now = scheduled_now()
    decision_date = now.astimezone(TAIPEI).date().isoformat()
    today_key = decision_date.replace("-", "")
    status_path = run_root / "latest_status.json"
    log_path = run_root / f"{today_key}_recommendation_snapshot.log"
    checked_at = now.isoformat(timespec="seconds")

    payload = _payload_base(
        output_root=output_root,
        decision_date=decision_date,
        status_path=status_path,
        log_path=log_path,
        checked_at=checked_at,
    )

    try:
        current_fundamental_source_root = _resolve_current_fundamental_source_root(
            data_root=data_root,
            explicit_root=args.current_fundamental_source_root,
        )
        payload["current_fundamental_source_root"] = str(
            current_fundamental_source_root
        )
        config = TWStockConfig(data_root=data_root, output_root=output_root)
        recommendation_config = _scheduled_default_config()
        runtime_config = _runtime_config(recommendation_config)
        raw_caller_config = _canonical_json(recommendation_config)
        request_config_snapshot = RecommendationConfigSnapshot(
            raw_config_json=raw_caller_config,
            raw_json_sha256="sha256:"
            + hashlib.sha256(raw_caller_config.encode("utf-8")).hexdigest(),
        )
        service = RecommendationService(
            config,
            input_preparer=build_default_recommendation_input_preparer(
                config,
                current_fundamental_source_root=current_fundamental_source_root,
            ),
            regime_service=RegimeService(config, use_persistent_history=True),
        )
        execution = service.execute_recommendation(
            runtime_config=runtime_config,
            max_stocks=args.max_stocks,
            top_n=args.top_n,
            request_config_snapshot=request_config_snapshot,
            postprocess_callback=_build_scheduled_postprocess_callback(
                caller_config=recommendation_config,
                decision_date=decision_date,
                max_stocks=args.max_stocks,
                top_n=args.top_n,
            ),
            created_at=datetime.fromisoformat(checked_at),
        )
        if execution.status is not ExecutionStatus.COMPLETED:
            raise RuntimeError(
                f"recommendation_execution_not_completed:{execution.status.value}"
            )

        composition = build_recommendation_composition(config)
        result_name = f"Scheduled recommendation snapshot {decision_date}"
        receipt = composition.save_service.save_execution(
            execution,
            label=result_name,
            notes="Research-only scheduled snapshot; not trading advice.",
        )
        read_model = _read_verified_saved_execution(
            composition=composition,
            execution=execution,
            receipt=receipt,
        )
        saved_execution = read_model.execution
        assert saved_execution is not None
        result_id = saved_execution.result_id
        payload["result_id"] = result_id
        payload["writes_recommendation_result"] = True
        result_config_snapshot = saved_execution.context.result_config_snapshot
        if result_config_snapshot is None:
            raise ValueError("recommendation_execution_result_config_snapshot_missing")
        result_config = _load_json_object(
            result_config_snapshot.raw_result_config_json,
            "raw_result_config_json",
        )
        if _canonical_json_sha256(result_config) != result_config_snapshot.config_sha256:
            raise ValueError("recommendation_execution_result_config_hash_mismatch")
        snapshot_cohort = result_config.get("snapshot_cohort")
        if not isinstance(snapshot_cohort, Mapping):
            raise ValueError("recommendation_execution_snapshot_cohort_missing")
        cohort_from_result = _snapshot_cohort_from_payload(snapshot_cohort)
        if cohort_from_result != saved_execution.context.snapshot_cohort:
            raise ValueError("recommendation_execution_snapshot_cohort_mismatch")
        capture_summary = _execution_capture_summary(saved_execution)
        recommendations = saved_execution.decision.items if saved_execution.decision else ()
        warnings = []
        if not recommendations:
            warnings.append("no_recommendations_returned")
        paper_frozen_export: dict[str, Any] | None = None
        if snapshot_cohort.get("missing_symbols"):
            warnings.append("snapshot_cohort_partial_source_coverage")
        elif snapshot_cohort.get("degraded_symbols"):
            warnings.append("snapshot_cohort_degraded_screening_quality")

        forward_candidate: dict[str, Any] | None = None
        forward_calendar_observation: dict[str, Any] | None = None
        forward_calendar_path: Path | None = None
        calendar_observed_at: datetime | None = None
        source_path = composition.store.artifact_root / str(receipt.artifact_location)
        if args.forward_candidate_output_root or args.export_paper_frozen_source:
            if source_path.is_file():
                try:
                    actual_decision_at = saved_execution.context.decision_at
                    if actual_decision_at is None:
                        raise ValueError("recommendation_decision_at_missing")
                    # 持久化後重新讀取同一個現在時鐘，供 forward 與 Paper 年表觀察共用。
                    calendar_observed_at = scheduled_now()
                    forward_calendar_path, forward_calendar_observation = (
                        _resolve_forward_calendar_cache(
                            explicit_path=args.forward_calendar_cache_path,
                            refresh_status_path=args.forward_calendar_refresh_status_path,
                            observed_at=calendar_observed_at,
                            decision_at=actual_decision_at,
                        )
                    )
                except (OSError, TypeError, ValueError) as error:
                    actual_decision_at = None
                    forward_calendar_path = None
                    forward_calendar_observation = {
                        "status": "blocked",
                        "selection_source": "forward_calendar_observation",
                        "blocker": (
                            "forward_calendar_observation_source_invalid:"
                            f"{type(error).__name__}:{error}"
                        ),
                    }
            else:
                forward_calendar_observation = {
                    "status": "blocked",
                    "selection_source": "forward_calendar_observation",
                    "blocker": "recommendation_result_file_missing_after_save",
                }

        if args.export_paper_frozen_source:
            if calendar_observed_at is None:
                paper_frozen_export = {
                    "status": "blocked",
                    "reason": "paper_frozen_source_artifact_missing_after_save",
                }
            else:
                try:
                    paper_frozen_export = _export_paper_frozen_source(
                        composition=composition,
                        read_model=read_model,
                        receipt=receipt,
                        observed_at=calendar_observed_at,
                        calendar_path=forward_calendar_path,
                        calendar_observation=forward_calendar_observation,
                    )
                except Exception as error:
                    paper_frozen_export = {
                        "status": "blocked",
                        "reason": (
                            "paper_frozen_export_error:"
                            f"{type(error).__name__}:{error}"
                        ),
                    }
            if paper_frozen_export.get("status") == "blocked":
                warnings.append("paper_frozen_source_export_blocked")
        payload.update(
            {
                "result_id": result_id,
                "forward_calendar_observation": forward_calendar_observation,
                "paper_frozen_source_export": paper_frozen_export,
                "warnings": list(warnings),
            }
        )

        if args.forward_candidate_output_root:
            if not source_path.is_file():
                forward_candidate = {
                    "status": "skipped_source_missing",
                    "source_path": str(source_path),
                    "candidate_count": 0,
                    "warnings": ["recommendation_result_file_missing_after_save"],
                    "blockers": [],
                }
                warnings.append("forward_position_thesis_source_missing")
            elif (
                forward_calendar_observation is not None
                and forward_calendar_observation.get("status") == "blocked"
            ):
                forward_candidate = _write_blocked_forward_candidate_receipt(
                    output_root=args.forward_candidate_output_root,
                    source_path=source_path,
                    result_id=result_id,
                    decision_date=decision_date,
                    decision_at=actual_decision_at,
                    calendar_observation=forward_calendar_observation,
                )
                warnings.append("forward_calendar_observation_blocked")
            else:
                forward_candidate = ForwardPositionThesisCandidateProducer(
                    args.forward_candidate_output_root,
                    calendar_cache_path=str(forward_calendar_path),
                ).produce_verified_read(
                    read_model,
                    receipt,
                    source_artifact_path=source_path,
                    policy_path=args.forward_thesis_policy_path,
                )
                if str(forward_candidate.get("status")) == "blocked":
                    warnings.append("forward_position_thesis_candidate_blocked")
                elif str(forward_candidate.get("status")) == "degraded":
                    warnings.append("forward_position_thesis_candidate_degraded")

        paper_export_blocked = (
            args.export_paper_frozen_source
            and paper_frozen_export is not None
            and paper_frozen_export.get("status") == "blocked"
        )
        terminal_status = "blocked" if paper_export_blocked else "passed"
        terminal_exit_code = 2 if paper_export_blocked else 0
        payload.update(
            {
                "status": terminal_status,
                "exit_code": terminal_exit_code,
                "result_id": result_id,
                "result_name": result_name,
                "recommendations_count": len(recommendations),
                "screening_matrix_rows": len(capture_summary["screening_matrix"]),
                "snapshot_cohort": dict(snapshot_cohort),
                "excluded_candidates_rows": len(capture_summary["excluded_candidates"]),
                "why_not_payload_rows": len(capture_summary["why_not_payload"]),
                "liquidity_gate_payload_rows": len(capture_summary["liquidity_gate_payload"]),
                "exclusion_quality": capture_summary["exclusion_quality"],
                "exclusion_warnings": list(capture_summary["exclusion_warnings"]),
                "warnings": warnings,
                "forward_position_thesis": forward_candidate,
                "forward_calendar_observation": forward_calendar_observation,
                "paper_frozen_source_export": paper_frozen_export,
                "db_path": str(composition.store.database_path),
                "runs_dir": str(composition.runs_dir),
                "writes_recommendation_result": True,
                "writes_evidence_db": False,
                "auto_trading": False,
                "lifecycle_action": False,
                "confirm": False,
                "evidence_identity": {
                    key: result_config[key]
                    for key in (
                        "strategy_version_id",
                        "strategy_config_id",
                        "strategy_config_hash",
                        "universe_id",
                        "universe_hash",
                        "universe_identity_schema",
                        "universe_policy_id",
                        "universe_policy_hash",
                        "universe_policy_schema",
                        "universe_snapshot_id",
                        "universe_snapshot_hash",
                        "universe_snapshot_schema",
                        "universe_snapshot_source_provider_id",
                        "universe_snapshot_selected_codes_hash",
                        "cost_model_id",
                        "benchmark_id",
                        "industry_benchmark_id",
                        "horizon_days",
                        "evidence_tier",
                        "return_basis",
                    )
                    if key in result_config and str(result_config[key]).strip()
                },
            }
        )
        log_path.write_text(
            "\n".join(
                [
                    f"status={terminal_status}",
                    f"exit_code={terminal_exit_code}",
                    f"decision_date={decision_date}",
                    f"result_id={result_id}",
                    f"recommendations_count={len(recommendations)}",
                    f"screening_matrix_rows={len(capture_summary['screening_matrix'])}",
                    "writes_evidence_db=false",
                    "auto_trading=false",
                    "lifecycle_action=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        _write_status(status_path, payload)
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
        return terminal_exit_code
    except Exception as exc:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "writes_recommendation_result": bool(payload.get("result_id")),
                "writes_evidence_db": False,
                "auto_trading": False,
                "lifecycle_action": False,
                "confirm": False,
            }
        )
        log_path.write_text(f"status=failed\nerror_type={type(exc).__name__}\nerror={exc}\n", encoding="utf-8")
        _write_status(status_path, payload)
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
