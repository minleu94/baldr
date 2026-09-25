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
from app_module.recommendation.contracts import (
    ExecutionStatus,
    IndexStatus,
    RecommendationConfigSnapshot,
    RecommendationResultConfigSnapshot,
    RecommendationRunEvidenceIdentity,
    SnapshotCohort,
    SnapshotCohortCoverage,
    SnapshotCohortCoverageStatus,
)
from app_module.recommendation.execute import (
    RecommendationPostprocessFacts,
    RecommendationPostprocessInput,
)
from app_module.recommendation.body_result import (
    snapshot_cohort_from_body_result,
    snapshot_cohort_payload_from_body_result,
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


def _execution_capture_summary(execution: Any) -> dict[str, Any]:
    """讀取 execution 已封存的同次 legacy evidence 摘要。"""

    event = next(
        (
            item
            for item in execution.events
            if item.event_type == "legacy_negative_evidence_capture"
        ),
        None,
    )
    details = event.details if event is not None else {}
    return {
        "screening_matrix": tuple(details.get("screening_matrix", ())),
        "excluded_candidates": tuple(details.get("excluded_candidates", ())),
        "why_not_payload": tuple(details.get("why_not_payload", ())),
        "liquidity_gate_payload": tuple(details.get("liquidity_gate_payload", ())),
        "exclusion_quality": str(details.get("exclusion_quality", "unknown")),
        "exclusion_warnings": tuple(details.get("exclusion_warnings", ())),
    }


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
    return parser


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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.output_root)
    run_root = output_root / "scheduled" / "recommendation_snapshot"
    run_root.mkdir(parents=True, exist_ok=True)

    now = scheduled_now()
    decision_date = now.date().isoformat()
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
        config = TWStockConfig(data_root=Path(args.data_root), output_root=output_root)
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
            input_preparer=build_default_recommendation_input_preparer(config),
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
        if snapshot_cohort.get("missing_symbols"):
            warnings.append("snapshot_cohort_partial_source_coverage")
        elif snapshot_cohort.get("degraded_symbols"):
            warnings.append("snapshot_cohort_degraded_screening_quality")

        forward_candidate: dict[str, Any] | None = None
        forward_calendar_observation: dict[str, Any] | None = None
        if args.forward_candidate_output_root:
            source_path = composition.store.artifact_root / str(receipt.artifact_location)
            if source_path.is_file():
                try:
                    actual_decision_at = saved_execution.context.decision_at
                    if actual_decision_at is None:
                        raise ValueError("recommendation_decision_at_missing")
                    # The recommendation service records its decision clock
                    # after the wrapper's initial ``checked_at``.  Re-read
                    # the wall clock after persistence so a normal, slightly
                    # longer run is not mistaken for a future decision.
                    forward_observed_at = scheduled_now()
                    forward_calendar_path, forward_calendar_observation = (
                        _resolve_forward_calendar_cache(
                            explicit_path=args.forward_calendar_cache_path,
                            refresh_status_path=args.forward_calendar_refresh_status_path,
                            observed_at=forward_observed_at,
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
                if forward_calendar_observation.get("status") == "blocked":
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
            else:
                forward_candidate = {
                    "status": "skipped_source_missing",
                    "source_path": str(source_path),
                    "candidate_count": 0,
                    "warnings": ["recommendation_result_file_missing_after_save"],
                    "blockers": [],
                }
                warnings.append("forward_position_thesis_source_missing")

        payload.update(
            {
                "status": "passed",
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
                    f"status=passed",
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
        return 0
    except Exception as exc:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "writes_recommendation_result": False,
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
    raise SystemExit(main())
