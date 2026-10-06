"""以明確注入來源發布個人推薦的成熟自然結果。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Sequence

from app_module.recommendation.persistence import RecommendationExecutionPersistence
from app_module.recommendation.personal_prediction_capture import (
    MAX_PERSONAL_CAPTURE_FILE_BYTES,
    PersonalPredictionCaptureError,
    _canonical_json_bytes as _capture_canonical_json_bytes,
    read_personal_prediction_capture,
    capture_personal_daily_results,
    project_personal_capture_h20_gross,
)
from app_module.recommendation.queries import RecommendationExecutionQueries
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
from data_module.result_artifact_store import ResultArtifactStore
from ml_module.recommendation_calibration_evidence import (
    verify_natural_maturity_session_proof,
)
from ml_module.recommendation_natural_outcome_service import (
    PersonalNaturalOutcomeProjection,
    RecommendationNaturalOutcomeService,
)


PERSONAL_NATURAL_OUTCOME_DAILY_SCHEMA_V1 = "personal-recommendation-natural-outcome-daily.v1"
PERSONAL_NATURAL_OUTCOME_SCHEMA_V1 = "personal-recommendation-natural-outcome.v1"
PERSONAL_NATURAL_OUTCOME_SCHEMA_V2 = "personal-recommendation-natural-outcome.v2"
MAX_CAPTURE_PATHS = 500
MAX_CAPTURE_ROWS = 500
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REPARSE_POINT = 0x400


class PersonalNaturalOutcomeDailyError(ValueError):
    """日常個人自然結果輸入或來源不符合明確契約。"""


class PersonalNaturalOutcomeConflict(PersonalNaturalOutcomeDailyError):
    """同一個人結果身分已有不同 bytes；拒絕覆寫。"""


@dataclass(frozen=True, slots=True)
class PersonalNaturalOutcomeDailyReceiptV1:
    """一次隔離批次的摘要與 create-only 發布結果。"""

    status: str
    summary_path: Path
    summary_sha256: str
    summary_idempotent: bool
    outcome_paths: tuple[Path, ...]
    outcome_sha256s: tuple[str, ...]
    idempotent_outcomes: tuple[bool, ...]
    capture_statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PreparedCapture:
    path: Path
    capture_id: str | None
    result_id: str | None
    status: str
    reason: str
    projection: dict[str, Any] | None
    outcome_payload: dict[str, Any] | None
    outcome_path: Path | None
    session_calendar_status: str | None


def run_personal_natural_outcome_daily(
    *,
    canonical_recommendation_output_root: str | Path,
    capture_paths: Sequence[str | Path],
    personal_capture_root: str | Path,
    market_source_db: str | Path,
    calendar_cache_path: str | Path,
    evaluation_at: datetime,
    isolated_output_root: str | Path,
    temporary_closure_cache_path: str | Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PersonalNaturalOutcomeDailyReceiptV1:
    """逐一重驗明確選取的 capture，再發布完整成熟的個人 outcome。

    ``canonical_recommendation_output_root`` 是原產品 OUTPUT_ROOT，內含
    ``recommendation/runs``；個人 capture、行情 DB、官方年曆與輸出根目錄均
    由 caller 明確注入。此入口不讀環境設定、不掃描「最新」檔，也不呼叫
    global evidence builder 或 promotion writer。
    """

    evaluation = _aware_utc(evaluation_at)
    canonical_root = _absolute_path(
        canonical_recommendation_output_root,
        "canonical_recommendation_output_root",
    )
    capture_root = _absolute_path(personal_capture_root, "personal_capture_root")
    market_db = _absolute_path(market_source_db, "market_source_db")
    calendar_root = _absolute_path(calendar_cache_path, "calendar_cache_path")
    isolated_root = _absolute_path(isolated_output_root, "isolated_output_root")
    closure_root = (
        None
        if temporary_closure_cache_path is None
        else _absolute_path(temporary_closure_cache_path, "temporary_closure_cache_path")
    )

    selected_paths = _validate_capture_paths(capture_paths, capture_root)
    runs_dir = canonical_root / "recommendation" / "runs"
    canonical_db = runs_dir / "recommendation_runs.db"
    canonical_artifacts = runs_dir / "execution_artifacts"
    _require_plain_directory(canonical_root, "canonical_recommendation_output_root")
    _require_plain_directory(runs_dir, "canonical recommendation runs directory")
    _require_plain_file(canonical_db, "canonical recommendation index")
    _require_plain_directory(canonical_artifacts, "canonical recommendation artifacts")
    _require_plain_directory(capture_root, "personal_capture_root")
    _require_plain_directory(capture_root / "captures", "personal capture directory")
    _require_plain_file(market_db, "market_source_db")
    _validate_optional_source_path(calendar_root, "calendar_cache_path")
    if closure_root is not None:
        _validate_optional_source_path(closure_root, "temporary_closure_cache_path")

    input_paths = [canonical_root, capture_root, market_db, calendar_root]
    if closure_root is not None:
        input_paths.append(closure_root)
    _require_disjoint_output_root(isolated_root, input_paths)

    provider = MLHistoricalSnapshotProvider(market_db)
    resolver = NaturalMaturitySessionResolver(
        db_path=market_db,
        calendar_cache_path=calendar_root,
        temporary_closure_path=closure_root,
    )
    outcome_service = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=market_db,
        session_resolver=resolver,
        evaluation_at=evaluation,
    )
    store = ResultArtifactStore(
        artifact_root=canonical_artifacts,
        database_path=canonical_db,
    )
    queries = RecommendationExecutionQueries(RecommendationExecutionPersistence(store))

    market_before = _source_stat(market_db)
    output_base = isolated_root / "personal_natural_outcomes"
    prepared: list[_PreparedCapture] = []
    for capture_path in selected_paths:
        if cancelled is not None and cancelled():
            raise InterruptedError("personal_daily_cancelled")
        prepared.append(
            _prepare_capture(
                capture_path,
                capture_root=capture_root,
                queries=queries,
                resolver=resolver,
                outcome_service=outcome_service,
                market_db=market_db,
                evaluation_at=evaluation,
                outcome_root=output_base,
            )
        )
    market_after = _source_stat(market_db)

    if market_before != market_after:
        prepared = [
            _PreparedCapture(
                path=item.path,
                capture_id=item.capture_id,
                result_id=item.result_id,
                status="unknown",
                reason="market_source_changed_during_batch",
                projection=None,
                outcome_payload=None,
                outcome_path=None,
                session_calendar_status=item.session_calendar_status,
            )
            if item.outcome_payload is not None
            else item
            for item in prepared
        ]

    outcome_items = [item for item in prepared if item.outcome_payload is not None]
    outcome_targets = [item.outcome_path for item in outcome_items]
    if any(target is None for target in outcome_targets):
        raise PersonalNaturalOutcomeDailyError("成熟結果缺少個人輸出目標")

    # 發布前先檢查所有既有 identity，避免已知衝突造成部分批次新增。
    for item in outcome_items:
        assert item.outcome_path is not None and item.outcome_payload is not None
        _check_create_only_target(item.outcome_path, item.outcome_payload, output_base)

    published: list[tuple[Path, str, bool]] = []
    for item in outcome_items:
        assert item.outcome_path is not None and item.outcome_payload is not None
        if cancelled is not None and cancelled():
            raise InterruptedError("personal_daily_cancelled")
        payload_sha256, idempotent = _publish_create_only(
            item.outcome_path,
            item.outcome_payload,
            output_base,
        )
        published.append((item.outcome_path, payload_sha256, idempotent))

    summary_body = _summary_body(
        canonical_root=canonical_root,
        capture_root=capture_root,
        selected_paths=selected_paths,
        market_db=market_db,
        market_before=market_before,
        market_after=market_after,
        calendar_root=calendar_root,
        closure_root=closure_root,
        evaluation_at=evaluation,
        prepared=prepared,
        published=published,
    )
    summary_path = output_base / "runs" / f"{_payload_hash(summary_body)[7:]}.json"
    summary_hash, summary_idempotent = _publish_create_only(
        summary_path,
        summary_body,
        output_base,
    )
    statuses = tuple(item.status for item in prepared)
    status = (
        "completed_with_unknown"
        if "unknown" in statuses
        else "completed_with_pending"
        if "pending" in statuses
        else "completed"
    )
    return PersonalNaturalOutcomeDailyReceiptV1(
        status=status,
        summary_path=summary_path,
        summary_sha256=summary_hash,
        summary_idempotent=summary_idempotent,
        outcome_paths=tuple(item[0] for item in published),
        outcome_sha256s=tuple(item[1] for item in published),
        idempotent_outcomes=tuple(item[2] for item in published),
        capture_statuses=statuses,
    )


def _prepare_capture(
    capture_path: Path,
    *,
    capture_root: Path,
    queries: RecommendationExecutionQueries,
    resolver: NaturalMaturitySessionResolver,
    outcome_service: RecommendationNaturalOutcomeService,
    market_db: Path,
    evaluation_at: datetime,
    outcome_root: Path,
) -> _PreparedCapture:
    capture_id: str | None = None
    result_id: str | None = None
    calendar_status: str | None = None
    try:
        # 第一次 public read 取得待核身分；第二次以該身分明確綁定並確認 bytes 穩定。
        first = read_personal_prediction_capture(capture_path, queries, capture_root)
        result_id_value = first.get("result_id")
        if type(result_id_value) is not str or not result_id_value.strip():
            raise PersonalPredictionCaptureError("capture 缺少有效 result_id")
        result_id = result_id_value
        capture = read_personal_prediction_capture(
            capture_path,
            queries,
            capture_root,
            expected_result_id=result_id,
        )
        if capture != first:
            raise PersonalPredictionCaptureError("capture 兩次嚴格讀回內容不同")
        capture_id_value = capture.get("capture_id")
        if type(capture_id_value) is not str or not capture_id_value.startswith("sha256:"):
            raise PersonalPredictionCaptureError("capture 缺少有效 capture_id")
        capture_id = capture_id_value
        binding = capture.get("receipt_binding")
        if not isinstance(binding, dict):
            raise PersonalPredictionCaptureError("capture receipt binding 格式無效")
        capture_date = binding.get("decision_date")
        if type(capture_date) is not str:
            raise PersonalPredictionCaptureError("capture decision date 缺失")

        resolution = resolver.resolve_personal_prediction_horizon(
            capture_date,
            evaluation_at,
        )
        calendar_status = (
            str(resolution.proof.get("calendar", {}).get("status"))
            if isinstance(resolution.proof, dict)
            and isinstance(resolution.proof.get("calendar"), dict)
            else None
        )
        verified_proof: dict[str, Any] | None = None
        if resolution.status == "ready" and isinstance(resolution.proof, dict):
            if resolution.endpoint_date is None:
                raise PersonalNaturalOutcomeDailyError("ready session resolution 缺少 endpoint")
            verified_proof = dict(
                verify_natural_maturity_session_proof(
                    resolution.proof,
                    capture_date=capture_date,
                    label_end_date=resolution.endpoint_date,
                    evaluation_at=evaluation_at,
                    expected_db_path=market_db,
                )
            )

        projection = outcome_service.project_personal_prediction_outcomes(
            capture,
            evaluation_at=evaluation_at,
            max_rows=MAX_CAPTURE_ROWS,
        )
        projection_payload = projection.to_dict()
        _check_projection_identity(projection, capture, evaluation_at)
        if projection.status != "matured":
            return _PreparedCapture(
                path=capture_path,
                capture_id=capture_id,
                result_id=result_id,
                status="pending",
                reason=_safe_reason(projection.reason),
                projection=projection_payload,
                outcome_payload=None,
                outcome_path=None,
                session_calendar_status=calendar_status,
            )
        if verified_proof is None:
            raise PersonalNaturalOutcomeDailyError(
                "投影已成熟但獨立 official-session proof 未能核驗"
            )
        outcome_payload = _build_outcome_payload(
            capture=capture,
            projection=projection,
            verified_proof=verified_proof,
            calendar_status=calendar_status,
            market_db=market_db,
        )
        evaluation_identity = {
            "capture_id": capture_id,
            "evaluation_at": projection.evaluation_at,
        }
        if capture.get("schema_version") == "recommendation-personal-prediction-capture.v3":
            # v3 之前可能已有 v1 outcome；使用不同 create-only 身分保留舊 bytes。
            evaluation_identity["outcome_schema_version"] = PERSONAL_NATURAL_OUTCOME_SCHEMA_V2
        evaluation_key = _payload_hash(evaluation_identity)[7:]
        outcome_path = outcome_root / "outcomes" / f"{evaluation_key}.json"
        return _PreparedCapture(
            path=capture_path,
            capture_id=capture_id,
            result_id=result_id,
            status="matured",
            reason=projection.reason,
            projection=projection_payload,
            outcome_payload=outcome_payload,
            outcome_path=outcome_path,
            session_calendar_status=calendar_status,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _PreparedCapture(
            path=capture_path,
            capture_id=capture_id,
            result_id=result_id,
            status="unknown",
            reason=f"validation_failed:{type(exc).__name__}",
            projection=None,
            outcome_payload=None,
            outcome_path=None,
            session_calendar_status=calendar_status,
        )


def _build_outcome_payload(
    *,
    capture: dict[str, Any],
    projection: PersonalNaturalOutcomeProjection,
    verified_proof: dict[str, Any],
    calendar_status: str | None,
    market_db: Path,
) -> dict[str, Any]:
    delivered = capture.get("delivered_rows")
    if not isinstance(delivered, list) or not delivered or len(delivered) > MAX_CAPTURE_ROWS:
        raise PersonalNaturalOutcomeDailyError("capture delivered rows 缺失或超過上限")
    expected_rows: list[tuple[str, int]] = []
    for row in delivered:
        if not isinstance(row, dict):
            raise PersonalNaturalOutcomeDailyError("capture delivered row 型別錯誤")
        symbol, rank = row.get("stock_code"), row.get("rank")
        if type(symbol) is not str or not symbol or type(rank) is not int or rank < 0:
            raise PersonalNaturalOutcomeDailyError("capture stock/rank identity 無效")
        expected_rows.append((symbol, rank))
    if len(set(expected_rows)) != len(expected_rows):
        raise PersonalNaturalOutcomeDailyError("capture stock/rank identity 重複")

    capture_schema = capture.get("schema_version")
    is_v3_capture = capture_schema == "recommendation-personal-prediction-capture.v3"
    baseline_snapshot: dict[str, Any] | None = None
    active_codes: tuple[str, ...] = ()
    fallback_codes: tuple[str, ...] = ()
    binding_value = capture.get("receipt_binding")
    if not isinstance(binding_value, dict):
        raise PersonalNaturalOutcomeDailyError("receipt binding 無效")
    if is_v3_capture:
        baseline_value = capture.get("probability_baseline_snapshot")
        if not isinstance(baseline_value, dict):
            raise PersonalNaturalOutcomeDailyError("v3 capture baseline snapshot 無效")
        baseline_snapshot = baseline_value
        baseline_hash = baseline_snapshot.get("snapshot_sha256")
        baseline_body = {
            key: value
            for key, value in baseline_snapshot.items()
            if key != "snapshot_sha256"
        }
        if (
            baseline_snapshot.get("schema_version")
            != "recommendation-personal-probability-baseline-snapshot.v2"
            or type(baseline_hash) is not str
            or not _SHA256_RE.fullmatch(baseline_hash)
            or (
                "sha256:"
                + hashlib.sha256(_capture_canonical_json_bytes(baseline_body)).hexdigest()
            )
            != baseline_hash
        ):
            raise PersonalNaturalOutcomeDailyError("v3 baseline snapshot hash/schema 無效")
        delivered_codes = baseline_snapshot.get("delivered_stock_codes")
        active_value = baseline_snapshot.get("model_active_stock_codes")
        fallback_value = baseline_snapshot.get("rule_only_fallback_stock_codes")
        projected_codes = binding_value.get("projected_stock_codes")
        capture_codes = [symbol for symbol, _rank in expected_rows]
        if (
            type(delivered_codes) is not list
            or type(active_value) is not list
            or type(fallback_value) is not list
            or any(type(code) is not str or not code for code in (*delivered_codes, *active_value, *fallback_value))
            or len(set(delivered_codes)) != len(delivered_codes)
            or len(set(active_value)) != len(active_value)
            or len(set(fallback_value)) != len(fallback_value)
            or not set(active_value).isdisjoint(fallback_value)
            or set(active_value) | set(fallback_value) != set(delivered_codes)
            or delivered_codes != capture_codes
            or type(projected_codes) is not list
            or projected_codes != baseline_snapshot.get("projected_stock_codes")
            or not set(active_value)
            or type(baseline_snapshot.get("delivered_count")) is not int
            or baseline_snapshot.get("delivered_count") != len(delivered_codes)
            or type(baseline_snapshot.get("model_active_count")) is not int
            or baseline_snapshot.get("model_active_count") != len(active_value)
            or type(baseline_snapshot.get("fallback_count")) is not int
            or baseline_snapshot.get("fallback_count") != len(fallback_value)
            or type(baseline_snapshot.get("model_coverage_bp")) is not int
            or baseline_snapshot.get("model_coverage_bp")
            != len(active_value) * 10_000 // len(delivered_codes)
        ):
            raise PersonalNaturalOutcomeDailyError("v3 capture active/fallback partition 無效")
        active_codes = tuple(active_value)
        fallback_codes = tuple(fallback_value)

    outcome_rows = projection.outcomes
    actual_rows: list[tuple[str, int]] = []
    proof_hash = verified_proof.get("proof_hash")
    endpoint = verified_proof.get("endpoint_date")
    binding = binding_value
    cost_hash = binding.get("cost_scenario_hash")
    if type(proof_hash) is not str or not _SHA256_RE.fullmatch(proof_hash):
        raise PersonalNaturalOutcomeDailyError("verified session proof hash 無效")
    if type(endpoint) is not str or not endpoint:
        raise PersonalNaturalOutcomeDailyError("verified session proof endpoint 缺失")
    projection_payload = projection.to_dict()
    if projection_payload.get("horizon_sessions") != 20:
        raise PersonalNaturalOutcomeDailyError("自然成熟 horizon 不是 20 sessions")
    if projection.status != "matured" or projection.pending_sample_count != 0:
        raise PersonalNaturalOutcomeDailyError("部分成熟投影不得發布 outcome rows")
    projected_expected_rows = (
        [row for row in expected_rows if row[0] in set(active_codes)]
        if is_v3_capture
        else expected_rows
    )
    if (
        projection.matured_sample_count != len(projected_expected_rows)
        or len(outcome_rows) != len(projected_expected_rows)
    ):
        raise PersonalNaturalOutcomeDailyError("成熟 outcome rows 未完整覆蓋預期模型列")
    if is_v3_capture:
        metrics = projection_payload.get("metrics")
        if not isinstance(metrics, dict) or any(
            metrics.get(key) != expected
            for key, expected in {
                "delivered_universe_count": len(expected_rows),
                "model_active_count": len(active_codes),
                "rule_only_fallback_count": len(fallback_codes),
                "model_coverage_bp": len(active_codes) * 10_000 // len(expected_rows),
            }.items()
        ):
            raise PersonalNaturalOutcomeDailyError("v3 投影 coverage 與 capture partition 不符")
        if (
            baseline_snapshot is None
            or baseline_snapshot.get("upside_baseline_kind") != "fixed_null_benchmark_50pct"
            or baseline_snapshot.get("upside_baseline_id") != "null_benchmark_50pct_v1"
        ):
            raise PersonalNaturalOutcomeDailyError("v3 固定 null benchmark identity 無效")
    delivered_by_code = {
        symbol: row for (symbol, _rank), row in zip(expected_rows, delivered)
    }
    for row in outcome_rows:
        if not isinstance(row, dict):
            raise PersonalNaturalOutcomeDailyError("outcome row 型別錯誤")
        symbol, rank = row.get("stock_code"), row.get("rank")
        if type(symbol) is not str or type(rank) is not int:
            raise PersonalNaturalOutcomeDailyError("outcome row stock/rank 無效")
        actual_rows.append((symbol, rank))
        if (
            row.get("session_proof_hash") != proof_hash
            or row.get("label_end_date") != endpoint
            or row.get("label_available_date") != endpoint
            or row.get("cost_scenario_hash") != cost_hash
        ):
            raise PersonalNaturalOutcomeDailyError(
                "outcome row 未綁定同次 verified session/cost evidence"
            )
        if is_v3_capture:
            assert baseline_snapshot is not None
            delivered_row = delivered_by_code.get(symbol)
            delivered_projection = (
                delivered_row.get("projection") if isinstance(delivered_row, dict) else None
            )
            upside_map = baseline_snapshot.get("upside_probability_bp_by_symbol")
            after_cost_map = baseline_snapshot.get("after_cost_probability_bp_by_symbol")
            if (
                not isinstance(delivered_projection, dict)
                or row.get("calibrated_probability_bp")
                != delivered_projection.get("calibrated_probability_bp")
                or type(upside_map) is not dict
                or row.get("upside_baseline_probability_bp") != upside_map.get(symbol)
                or type(after_cost_map) is not dict
                or row.get("after_cost_baseline_probability_bp") != after_cost_map.get(symbol)
            ):
                raise PersonalNaturalOutcomeDailyError(
                    "v3 outcome row 與原始模型機率、基準或 forward-date 語意不符"
                )
    if actual_rows != projected_expected_rows:
        raise PersonalNaturalOutcomeDailyError("outcome rows 與已保存模型列順序/身份不同")
    if (
        projection_payload.get("global_natural_evidence_created") is not False
        or projection_payload.get("promotion_credit_created") is not False
    ):
        raise PersonalNaturalOutcomeDailyError("個人投影不得建立 global evidence/promotion credit")

    interpretation = (
        "gross_only_after_cost_pending"
        if projection.after_cost_status == "pending_cost_or_liquidity_evidence"
        else "projection_status_preserved"
    )
    if is_v3_capture:
        assert baseline_snapshot is not None
        decision_at = capture.get("decision_at")
        if type(decision_at) is not str or not decision_at:
            raise PersonalNaturalOutcomeDailyError("v3 capture decision_at 缺失")
        v3_outcome_rows = [
            {
                **dict(row),
                "return_basis": "close_to_close_event_date",
                "return_start_date": str(binding["decision_date"]),
                "return_end_date": str(endpoint),
                "is_execution_pnl": False,
            }
            for row in outcome_rows
        ]
        v3_projection_payload = {**projection_payload, "outcomes": v3_outcome_rows}
        return {
            "schema_version": PERSONAL_NATURAL_OUTCOME_SCHEMA_V2,
            "lane": "personal_only",
            "capture_binding": {
                "capture_id": capture["capture_id"],
                "result_id": capture["result_id"],
                "policy_sha256": capture["policy_event"]["policy_snapshot"]["policy_sha256"],
                "candidate_id": binding["candidate_id"],
                "receipt_hash": binding["receipt_hash"],
                "projection_rows_sha256": binding["projection_rows_sha256"],
                "cost_scenario_hash": cost_hash,
                "decision_at": decision_at,
                "probability_baseline_snapshot_sha256": baseline_snapshot[
                    "snapshot_sha256"
                ],
                "decision_date": binding["decision_date"],
            },
            "delivered_universe": [
                {
                    "stock_code": symbol,
                    "rank": rank,
                    "model_status": (
                        "active_model" if symbol in set(active_codes) else "rule_only_fallback"
                    ),
                }
                for symbol, rank in expected_rows
            ],
            "model_scope": {
                "delivered_count": len(expected_rows),
                "model_active_count": len(active_codes),
                "rule_only_fallback_count": len(fallback_codes),
                "model_coverage_bp": len(active_codes) * 10_000 // len(expected_rows),
                "model_active_stock_codes": list(active_codes),
                "rule_only_fallback_stock_codes": list(fallback_codes),
                "fallback_rows_have_model_probability": False,
            },
            "baseline": {
                "schema_version": baseline_snapshot["schema_version"],
                "snapshot_sha256": baseline_snapshot["snapshot_sha256"],
                "upside_baseline_kind": baseline_snapshot["upside_baseline_kind"],
                "upside_baseline_id": baseline_snapshot["upside_baseline_id"],
            },
            "source": {
                "market_source_db": str(market_db),
                "session_calendar_status": calendar_status,
                "session_proof": verified_proof,
            },
            "projection": v3_projection_payload,
            "return_semantics": {
                "basis": "close_to_close_event_date",
                "start_date": str(binding["decision_date"]),
                "end_date": str(endpoint),
                "is_execution_pnl": False,
            },
            "after_cost_interpretation": interpretation,
            "global_natural_evidence_created": False,
            "promotion_credit_created": False,
        }
    return {
        "schema_version": PERSONAL_NATURAL_OUTCOME_SCHEMA_V1,
        "lane": "personal_only",
        "capture_binding": {
            "capture_id": capture["capture_id"],
            "result_id": capture["result_id"],
            "policy_sha256": capture["policy_event"]["policy_snapshot"]["policy_sha256"],
            "candidate_id": binding["candidate_id"],
            "receipt_hash": binding["receipt_hash"],
            "cost_scenario_hash": cost_hash,
        },
        "source": {
            "market_source_db": str(market_db),
            "session_calendar_status": calendar_status,
            "session_proof": verified_proof,
        },
        "projection": projection_payload,
        "after_cost_interpretation": interpretation,
        "global_natural_evidence_created": False,
        "promotion_credit_created": False,
    }


def _check_projection_identity(
    projection: PersonalNaturalOutcomeProjection,
    capture: dict[str, Any],
    evaluation_at: datetime,
) -> None:
    binding = capture.get("receipt_binding")
    event = capture.get("policy_event")
    snapshot = event.get("policy_snapshot") if isinstance(event, dict) else None
    if not isinstance(binding, dict) or not isinstance(snapshot, dict):
        raise PersonalNaturalOutcomeDailyError("capture policy/receipt identity 缺失")
    expected = {
        "capture_id": capture.get("capture_id"),
        "result_id": capture.get("result_id"),
        "policy_sha256": snapshot.get("policy_sha256"),
        "candidate_id": binding.get("candidate_id"),
        "receipt_hash": binding.get("receipt_hash"),
        "cost_scenario_hash": binding.get("cost_scenario_hash"),
        "evaluation_at": _utc_text(evaluation_at),
    }
    for field, value in expected.items():
        if getattr(projection, field, None) != value:
            raise PersonalNaturalOutcomeDailyError(f"projection {field} 與 capture 不符")


def _summary_body(
    *,
    canonical_root: Path,
    capture_root: Path,
    selected_paths: tuple[Path, ...],
    market_db: Path,
    market_before: dict[str, int],
    market_after: dict[str, int],
    calendar_root: Path,
    closure_root: Path | None,
    evaluation_at: datetime,
    prepared: list[_PreparedCapture],
    published: list[tuple[Path, str, bool]],
) -> dict[str, Any]:
    published_by_path = {str(path): digest for path, digest, _ in published}
    capture_rows = []
    for item in prepared:
        capture_rows.append(
            {
                "capture_path": str(item.path),
                "capture_id": item.capture_id,
                "result_id": item.result_id,
                "status": item.status,
                "reason": item.reason,
                "projection_status": (
                    item.projection.get("status") if item.projection is not None else None
                ),
                "projection_reason": (
                    item.projection.get("reason") if item.projection is not None else None
                ),
                "matured_sample_count": (
                    item.projection.get("matured_sample_count")
                    if item.projection is not None
                    else 0
                ),
                "pending_sample_count": (
                    item.projection.get("pending_sample_count")
                    if item.projection is not None
                    else None
                ),
                "session_calendar_status": item.session_calendar_status,
                "outcome_artifact": (
                    {
                        "path": str(item.outcome_path),
                        "payload_sha256": published_by_path.get(str(item.outcome_path)),
                    }
                    if item.outcome_path is not None
                    else None
                ),
            }
        )
    status_values = [item.status for item in prepared]
    status = (
        "completed_with_unknown"
        if "unknown" in status_values
        else "completed_with_pending"
        if "pending" in status_values
        else "completed"
    )
    return {
        "schema_version": PERSONAL_NATURAL_OUTCOME_DAILY_SCHEMA_V1,
        "status": status,
        "evaluation_at": _utc_text(evaluation_at),
        "selected_capture_count": len(selected_paths),
        "published_outcome_count": len(published),
        "captures": capture_rows,
        "sources": {
            "canonical_recommendation_output_root": str(canonical_root),
            "personal_capture_root": str(capture_root),
            "market_source_db": str(market_db),
            "market_source_db_before": market_before,
            "market_source_db_after": market_after,
            "calendar_cache_path": str(calendar_root),
            "temporary_closure_cache_path": (
                None if closure_root is None else str(closure_root)
            ),
            "calendar_scope_without_temporary_cache": (
                "annual_plan_only" if closure_root is None else None
            ),
        },
        "global_natural_evidence_created": False,
        "promotion_credit_created": False,
    }


def _validate_capture_paths(
    capture_paths: Sequence[str | Path],
    capture_root: Path,
) -> tuple[Path, ...]:
    if isinstance(capture_paths, (str, bytes)) or not isinstance(capture_paths, Sequence):
        raise PersonalNaturalOutcomeDailyError("capture_paths 必須是明確的路徑序列")
    if not 1 <= len(capture_paths) <= MAX_CAPTURE_PATHS:
        raise PersonalNaturalOutcomeDailyError(
            f"capture_paths 數量必須介於 1 與 {MAX_CAPTURE_PATHS}"
        )
    expected_dir = capture_root / "captures"
    result: list[Path] = []
    seen: set[str] = set()
    for index, value in enumerate(capture_paths):
        path = _absolute_path(value, f"capture_paths[{index}]")
        _require_plain_file(path, f"capture_paths[{index}]")
        if path.parent != expected_dir or path.suffix.casefold() != ".json":
            raise PersonalNaturalOutcomeDailyError(
                "每個 capture 必須是 personal_capture_root/captures 的直屬 JSON 檔"
            )
        stat_result = path.stat()
        if stat_result.st_size > MAX_PERSONAL_CAPTURE_FILE_BYTES:
            raise PersonalNaturalOutcomeDailyError("capture 超過既有讀取大小上限")
        key = os.path.normcase(str(path))
        if key in seen:
            raise PersonalNaturalOutcomeDailyError("capture_paths 不可重複")
        seen.add(key)
        result.append(path)
    return tuple(result)


def _absolute_path(value: str | Path, field_name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 必須是絕對路徑")
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 必須是正規絕對路徑")
    _assert_existing_components_plain(path)
    return Path(os.path.abspath(path))


def _assert_existing_components_plain(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if _is_link_or_reparse(metadata):
            raise PersonalNaturalOutcomeDailyError("路徑不可包含 symlink/reparse point")


def _require_plain_directory(path: Path, field_name: str) -> None:
    _assert_existing_components_plain(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 不存在或無法讀取") from exc
    if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 必須是一般目錄")


def _require_plain_file(path: Path, field_name: str) -> None:
    _assert_existing_components_plain(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 不存在或無法讀取") from exc
    if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 必須是一般檔案")


def _validate_optional_source_path(path: Path, field_name: str) -> None:
    _assert_existing_components_plain(path)
    if not path.exists():
        return
    metadata = path.lstat()
    if _is_link_or_reparse(metadata) or not (
        stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
    ):
        raise PersonalNaturalOutcomeDailyError(f"{field_name} 必須是一般目錄或一般檔案")


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _require_disjoint_output_root(output_root: Path, inputs: list[Path]) -> None:
    for input_path in inputs:
        if _paths_overlap(output_root, input_path):
            raise PersonalNaturalOutcomeDailyError(
                "isolated_output_root 必須與所有 canonical/capture/source 路徑樹分離"
            )


def _paths_overlap(left: Path, right: Path) -> bool:
    left_norm = Path(os.path.normcase(os.path.abspath(left)))
    right_norm = Path(os.path.normcase(os.path.abspath(right)))
    return (
        left_norm == right_norm
        or left_norm in right_norm.parents
        or right_norm in left_norm.parents
    )


def _source_stat(path: Path) -> dict[str, int]:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise PersonalNaturalOutcomeDailyError("market source DB 不再是一般檔案")
    return {
        "size": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
    }


def _aware_utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PersonalNaturalOutcomeDailyError("evaluation_at 必須是含時區的 datetime")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _payload_hash(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "payload_sha256"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _publish_create_only(
    path: Path,
    payload: dict[str, Any],
    output_root: Path,
) -> tuple[str, bool]:
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    digest = _payload_hash(body)
    encoded = _canonical_bytes({**body, "payload_sha256": digest})
    if len(encoded) > 64 * 1024 * 1024:
        raise PersonalNaturalOutcomeDailyError("create-only payload 超過 64 MiB 上限")
    _ensure_plain_directory_tree(path.parent, output_root)
    existing = _read_plain_optional(path, output_root)
    if existing is not None:
        if existing != encoded:
            raise PersonalNaturalOutcomeConflict(
                "同一 capture/evaluation identity 已有不同 bytes；拒絕覆寫"
            )
        return digest, True

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".pno-", suffix=".tmp", dir=path.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _assert_existing_components_plain(path.parent)
        try:
            os.link(temporary, path)
        except FileExistsError:
            existing = _read_plain_optional(path, output_root)
            if existing == encoded:
                return digest, True
            raise PersonalNaturalOutcomeConflict(
                "create-only 發布時發現同一 identity 的不同 bytes"
            ) from None
        published = _read_plain_optional(path, output_root)
        if published != encoded:
            raise PersonalNaturalOutcomeDailyError("outcome 發布後 bytes 讀回不一致")
        return digest, False
    except PersonalNaturalOutcomeDailyError:
        raise
    except OSError as exc:
        raise PersonalNaturalOutcomeDailyError(
            f"無法 create-only 發布個人 outcome：{type(exc).__name__}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise PersonalNaturalOutcomeDailyError(
                    "outcome 暫存檔無法清理；已發布內容保持不變"
                ) from exc


def _check_create_only_target(path: Path, payload: dict[str, Any], output_root: Path) -> None:
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    encoded = _canonical_bytes({**body, "payload_sha256": _payload_hash(body)})
    existing = _read_plain_optional(path, output_root)
    if existing is not None and existing != encoded:
        raise PersonalNaturalOutcomeConflict(
            "同一 capture/evaluation identity 已有不同 bytes；拒絕覆寫"
        )


def _ensure_plain_directory_tree(path: Path, root: Path) -> None:
    normalized_root = Path(os.path.abspath(root))
    normalized_path = Path(os.path.abspath(path))
    try:
        normalized_path.relative_to(normalized_root)
    except ValueError as exc:
        raise PersonalNaturalOutcomeDailyError("輸出路徑超出 isolated_output_root") from exc
    _assert_existing_components_plain(normalized_root)
    if normalized_root.exists():
        _require_plain_directory(normalized_root, "isolated_output_root")
    else:
        _mkdir_plain_path(normalized_root, stop_at=None)
    relative = normalized_path.relative_to(normalized_root)
    current = normalized_root
    for component in relative.parts:
        current = current / component
        try:
            current.mkdir()
        except FileExistsError:
            pass
        metadata = current.lstat()
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise PersonalNaturalOutcomeDailyError("isolated outcome 目錄含 symlink/reparse")


def _mkdir_plain_path(path: Path, *, stop_at: Path | None) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        if stop_at is not None and current == stop_at:
            continue
        try:
            current.mkdir()
        except FileExistsError:
            pass
        metadata = current.lstat()
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise PersonalNaturalOutcomeDailyError("isolated output 路徑含 symlink/reparse")


def _read_plain_optional(path: Path, root: Path) -> bytes | None:
    _assert_existing_components_plain(path)
    try:
        descriptor = _open_regular_file_no_follow(path)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PersonalNaturalOutcomeDailyError("個人 outcome 必須是一般檔案")
        if metadata.st_size > 64 * 1024 * 1024:
            raise PersonalNaturalOutcomeDailyError("既有個人 outcome 超過 64 MiB 上限")
        normalized_root = Path(os.path.abspath(root))
        try:
            path.resolve(strict=True).relative_to(normalized_root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise PersonalNaturalOutcomeDailyError("個人 outcome 實際路徑超出輸出根") from exc
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            chunks: list[bytes] = []
            total = 0
            while total <= 64 * 1024 * 1024:
                chunk = handle.read(min(1024 * 1024, 64 * 1024 * 1024 + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > 64 * 1024 * 1024:
                raise PersonalNaturalOutcomeDailyError("既有個人 outcome 超過 64 MiB 上限")
            after = os.fstat(handle.fileno())
            if (
                total != metadata.st_size
                or (metadata.st_size, metadata.st_mtime_ns)
                != (after.st_size, after.st_mtime_ns)
            ):
                raise PersonalNaturalOutcomeDailyError("既有個人 outcome 讀取期間 bytes 改變")
            try:
                named_after = path.lstat()
            except OSError as exc:
                raise PersonalNaturalOutcomeDailyError(
                    "既有個人 outcome 讀取期間路徑消失或無法核對"
                ) from exc
            if (
                _is_link_or_reparse(named_after)
                or not stat.S_ISREG(named_after.st_mode)
                or (named_after.st_dev, named_after.st_ino)
                != (after.st_dev, after.st_ino)
            ):
                raise PersonalNaturalOutcomeDailyError(
                    "既有個人 outcome 讀取期間路徑已被替換"
                )
            return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_regular_file_no_follow(path: Path) -> int:
    if os.name == "nt":
        opener = getattr(ResultArtifactStore, "_windows_open_no_follow", None)
        if not callable(opener):
            raise PersonalNaturalOutcomeDailyError(
                "Windows no-follow file handle 不可用；拒絕讀取 outcome"
            )
        try:
            return int(opener(path, directory=False))
        except OSError as exc:
            if getattr(exc, "winerror", None) in (2, 3) or getattr(exc, "errno", None) in (2, 3):
                raise FileNotFoundError(str(path)) from exc
            raise PersonalNaturalOutcomeDailyError(
                "無法以 Windows no-follow handle 讀取 outcome"
            ) from exc
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise PersonalNaturalOutcomeDailyError("平台不支援 no-follow file open")
    try:
        return os.open(path, os.O_RDONLY | no_follow | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise PersonalNaturalOutcomeDailyError("無法以 no-follow handle 讀取 outcome") from exc


def _safe_reason(value: object) -> str:
    if type(value) is str and value and len(value) <= 240:
        return value
    return "personal_outcome_projection_pending"


PERSONAL_MODEL_DAILY_REQUEST_V1 = "personal-model-daily-request.v1"
PERSONAL_MODEL_DAILY_RECEIPT_V1 = "personal-model-daily-receipt.v1"


def _daily_queries(canonical_root: Path) -> RecommendationExecutionQueries:
    runs = canonical_root / "recommendation" / "runs"
    _require_plain_file(runs / "recommendation_runs.db", "canonical recommendation index")
    _require_plain_directory(runs / "execution_artifacts", "canonical recommendation artifacts")
    return RecommendationExecutionQueries(RecommendationExecutionPersistence(ResultArtifactStore(
        artifact_root=runs / "execution_artifacts", database_path=runs / "recommendation_runs.db",
    )))


def _daily_verify_pins(pins: list[dict[str, str]]) -> None:
    for pin in pins:
        path = _absolute_path(pin["path"], "source pin path")
        _require_plain_file(path, "source pin")
        if path.stat().st_nlink != 1:
            raise PersonalNaturalOutcomeDailyError("source pin 不接受 hardlink 別名")
        descriptor = _open_regular_file_no_follow(path)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        named = path.lstat()
        if (before.st_size, before.st_mtime_ns, before.st_dev, before.st_ino) != (after.st_size, after.st_mtime_ns, named.st_dev, named.st_ino) or after.st_nlink != 1 or _is_link_or_reparse(named):
            raise PersonalNaturalOutcomeDailyError("source pin 讀取期間變更")
        if "sha256:" + digest.hexdigest() != pin["sha256"]:
            raise PersonalNaturalOutcomeDailyError("source pin bytes 已變更或缺失")


def _daily_validate_request(request: dict[str, Any], root: Path) -> dict[str, Path]:
    required = {"schema_version", "canonical_recommendation_output_root", "personal_capture_root",
                "isolated_outcome_root", "market_source_db", "calendar_cache_path", "evaluation_at",
                "result_ids", "capture_paths", "source_pins"}
    optional = {"generation_argv", "timeout_seconds", "temporary_closure_cache_path", "gross_model_contract_hash"}
    if type(request) is not dict or not required <= request.keys() or request.keys() - required - optional:
        raise PersonalNaturalOutcomeDailyError("daily request 欄位不符合 schema")
    if request["schema_version"] != PERSONAL_MODEL_DAILY_REQUEST_V1:
        raise PersonalNaturalOutcomeDailyError("daily request schema 不支持")
    gross_hash = request.get("gross_model_contract_hash")
    if gross_hash is not None and (type(gross_hash) is not str or _SHA256_RE.fullmatch(gross_hash) is None):
        raise PersonalNaturalOutcomeDailyError("gross_model_contract_hash 無效")
    paths = {name: _absolute_path(request[name], name) for name in required if name.endswith("root") or name.endswith("path") or name == "market_source_db"}
    if request.get("temporary_closure_cache_path") is not None:
        paths["temporary_closure_cache_path"] = _absolute_path(request["temporary_closure_cache_path"], "closure cache")
    _require_disjoint_output_root(root, list(paths.values()))
    _require_disjoint_output_root(paths["isolated_outcome_root"], [value for name, value in paths.items() if name != "isolated_outcome_root"])
    if _paths_overlap(paths["canonical_recommendation_output_root"], paths["personal_capture_root"]):
        raise PersonalNaturalOutcomeDailyError("canonical 與 capture root 必須分離")
    for name in ("result_ids", "capture_paths"):
        values = request[name]
        if (type(values) is not list or len(values) > MAX_CAPTURE_PATHS
                or any(type(value) is not str or not value.strip() for value in values)
                or len(set(values)) != len(values)):
            raise PersonalNaturalOutcomeDailyError(f"{name} 必須是有界、不重複的明示序列")
    if len(request["result_ids"]) + len(request["capture_paths"]) > MAX_CAPTURE_PATHS:
        raise PersonalNaturalOutcomeDailyError("每日 result/capture 明列總數超過 500")
    for value in request["capture_paths"]:
        path = _absolute_path(value, "capture_path")
        if path.parent != paths["personal_capture_root"] / "captures" or path.suffix != ".json":
            raise PersonalNaturalOutcomeDailyError("capture_path 必須位於精確 capture root")
    evaluation = datetime.fromisoformat(request["evaluation_at"].replace("Z", "+00:00"))
    _aware_utc(evaluation)
    if not request["result_ids"] and not request["capture_paths"]:
        raise PersonalNaturalOutcomeDailyError("daily request 至少須明列一個 result 或 capture")
    pins = request["source_pins"]
    if type(pins) is not list or not 1 <= len(pins) <= 1000:
        raise PersonalNaturalOutcomeDailyError("source_pins 必須明示且有界")
    seen: set[str] = set()
    for pin in pins:
        if type(pin) is not dict or set(pin) != {"path", "sha256"} or type(pin["sha256"]) is not str or _SHA256_RE.fullmatch(pin["sha256"]) is None:
            raise PersonalNaturalOutcomeDailyError("source pin schema/hash 無效")
        path = _absolute_path(pin["path"], "pin path")
        normalized = os.path.normcase(str(path))
        if normalized in seen:
            raise PersonalNaturalOutcomeDailyError("source pin 不可重複")
        seen.add(normalized)
        _require_disjoint_output_root(root, [path])
        _require_disjoint_output_root(paths["isolated_outcome_root"], [path])
    if os.path.normcase(str(paths["market_source_db"])) not in seen:
        raise PersonalNaturalOutcomeDailyError("market_source_db 缺少 raw bytes pin")
    for name in ("calendar_cache_path", "temporary_closure_cache_path"):
        if name not in paths:
            continue
        cache = paths[name]
        _validate_optional_source_path(cache, name)
        # 缺官方年曆仍可收集每日預測；outcome 保持 unknown，不補平日。
        if cache.is_file() and os.path.normcase(str(cache)) not in seen:
            raise PersonalNaturalOutcomeDailyError("calendar cache 缺少 raw bytes pin")
        if cache.is_dir():
            for index, item in enumerate(cache.rglob("*")):
                if index >= 1000:
                    raise PersonalNaturalOutcomeDailyError("calendar cache inventory 超限")
                _assert_existing_components_plain(item)
                if item.is_file() and os.path.normcase(str(item)) not in seen:
                    raise PersonalNaturalOutcomeDailyError("calendar cache inventory 未完整 pin")
    timeout = request.get("timeout_seconds", 300)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise PersonalNaturalOutcomeDailyError("timeout_seconds 必須是 1–3600 整數")
    argv = request.get("generation_argv", [])
    if type(argv) is not list or len(argv) > 256 or any(type(value) is not str for value in argv):
        raise PersonalNaturalOutcomeDailyError("generation_argv 無效")
    if argv:
        from scripts.run_personalization_recommendation import _parser
        try:
            args = _parser().parse_args(argv)
        except SystemExit as exc:
            raise PersonalNaturalOutcomeDailyError("generation_argv 不符合既有 producer API") from exc
        if (args.historical_research or args.profile != "prod"
                or args.result_id not in request["result_ids"]
                or _absolute_path(args.output_root, "producer output") != paths["canonical_recommendation_output_root"]):
            raise PersonalNaturalOutcomeDailyError("每日 producer 的 result/root/profile/replay 不相容")
        config_path = _absolute_path(args.config_json, "config-json")
        if os.path.normcase(str(config_path)) not in seen:
            raise PersonalNaturalOutcomeDailyError("producer config 缺少 raw bytes pin")
        if not args.journal_path:
            raise PersonalNaturalOutcomeDailyError("producer journal_path 必須明示")
        journal = _absolute_path(args.journal_path, "journal-path")
        journal_protected = [value for name, value in paths.items() if name not in {"canonical_recommendation_output_root", "personal_capture_root"}]
        journal_protected.extend([paths["personal_capture_root"] / "captures", root])
        if journal.suffix.casefold() != ".jsonl" or any(_paths_overlap(journal, value) for value in journal_protected):
            raise PersonalNaturalOutcomeDailyError("producer journal 必須是獨立 JSONL 路徑")
        data_root = _absolute_path(args.data_root, "producer data root")
        if paths["market_source_db"] != data_root / "sqlite" / "twstock.db":
            raise PersonalNaturalOutcomeDailyError("producer data root 與 TWStockConfig 行情 DB 路由不符")
        if args.current_fundamental_source_root is None:
            raise PersonalNaturalOutcomeDailyError("producer current_fundamental_source_root 必須明示")
        _absolute_path(args.current_fundamental_source_root, "producer fundamental source root")
    _daily_verify_pins(pins)
    return paths


def _daily_produce(argv: list[str], timeout: int, cancelled: Callable[[], bool],
                   process_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """只啟動原 producer；取消與逾時只終止本次 child，保留其 partial artifacts。"""
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_personalization_recommendation.py"
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child_environment = dict(os.environ)
        child_environment["PYTHONIOENCODING"] = "utf-8"
        executable = sys.executable
        if os.name == "nt":
            # Windows venv launcher 另生 runtime；直接使用同一 base runtime，
            # 保留原 pyvenv 身份，使 terminate/kill 對應真正執行的程序。
            executable = getattr(sys, "_base_executable", "")
            if not executable:
                raise PersonalNaturalOutcomeDailyError("Windows Python runtime identity 不可用")
            _require_plain_file(_absolute_path(executable, "Python base runtime"), "Python base runtime")
            child_environment["__PYVENV_LAUNCHER__"] = sys.executable
        child = subprocess.Popen([executable, "-m", "scripts.run_personalization_recommendation", *argv], stdout=stdout, stderr=stderr,
                                 cwd=script.parents[1], env=child_environment)
        if process_receipt is not None:
            process_receipt.update(launcher_pid=child.pid, launched_at=_utc_text(datetime.now(timezone.utc)), status="started")
        started = time.monotonic()
        try:
            while child.poll() is None:
                if cancelled():
                    raise InterruptedError("personal_daily_cancelled")
                if time.monotonic() - started >= timeout:
                    raise TimeoutError("personal_daily_producer_timeout")
                if os.fstat(stdout.fileno()).st_size > 2 * 1024 * 1024 or os.fstat(stderr.fileno()).st_size > 64 * 1024:
                    raise PersonalNaturalOutcomeDailyError("producer output 超限")
                time.sleep(0.05)
        except BaseException:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            raise
        finally:
            if process_receipt is not None:
                process_receipt.update(exit_code=child.poll(), status="exited")
        stdout.seek(0)
        raw = stdout.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024 or os.fstat(stderr.fileno()).st_size > 64 * 1024:
            raise PersonalNaturalOutcomeDailyError("producer output 超限")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise PersonalNaturalOutcomeDailyError("producer stdout 沒有唯一 JSON receipt") from exc
        if child.returncode != 0 or not isinstance(payload, dict) or payload.get("ok") is not True:
            raise PersonalNaturalOutcomeDailyError("原每日 producer 未完成；partial 原樣保留")
        return {**(process_receipt or {}), "launcher_pid": child.pid, "exit_code": child.returncode, "receipt": payload}


def _daily_artifact(path: Path) -> dict[str, str]:
    raw = _read_plain_optional(path, path.parent)
    if raw is None:
        raise PersonalNaturalOutcomeDailyError("daily artifact 讀回缺失")
    return {"path": str(path), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}


def run_personal_model_daily(
    *, request: dict[str, Any], receipt_root: str | Path,
    cancelled: Callable[[], bool] | None = None,
    gross_contract: Any = None, lineage_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """明示 pins 串原每日推論／immutable capture／H20 自然結果，沒有自動 fit。"""
    root = _absolute_path(receipt_root, "receipt_root")
    # 深拷貝 JSON 值，caller 在 child 執行期間不能變更本次 identity。
    request = json.loads(_canonical_bytes(request))
    if len(_canonical_bytes(request)) > 1024 * 1024:
        raise PersonalNaturalOutcomeDailyError("daily request 超過 1 MiB 上限")
    paths = _daily_validate_request(request, root)
    if gross_contract is not None and request.get("gross_model_contract_hash") != getattr(gross_contract, "contract_hash", None):
        raise PersonalNaturalOutcomeDailyError("daily request 與注入 gross contract hash 不符")
    request_hash = _payload_hash(request)
    terminal = root / "runs" / f"{request_hash[7:]}.json"
    stop = cancelled if cancelled is not None else lambda: False
    existing = _read_plain_optional(terminal, root)
    if existing is not None:
        prior = json.loads(existing)
        if prior.get("request_sha256") != request_hash or prior.get("payload_sha256") != _payload_hash(prior):
            raise PersonalNaturalOutcomeConflict("每日原收據 identity/hash 不符")
        _daily_verify_pins(prior["artifacts"])
        queries = _daily_queries(paths["canonical_recommendation_output_root"])
        for item in prior["predictions"]:
            read_personal_prediction_capture(item["path"], queries, paths["personal_capture_root"], expected_result_id=item["result_id"])
        return {**prior, "receipt_path": str(terminal), "idempotent": True,
                "readback_process_identity": {"pid": os.getpid(), "observed_at": _utc_text(datetime.now(timezone.utc))}}
    _ensure_plain_directory_tree(root, root)
    lock = root / ".personal-model-daily.lock"
    _assert_existing_components_plain(lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PersonalNaturalOutcomeDailyError("personal daily busy；不移除另一 writer lock") from exc
    identity = {"pid": os.getpid(), "started_at": _utc_text(datetime.now(timezone.utc)), "nonce": uuid.uuid4().hex}
    body: dict[str, Any] = {
        "schema_version": PERSONAL_MODEL_DAILY_RECEIPT_V1, "request_sha256": request_hash,
        "process_identity": identity, "evaluation_at": request["evaluation_at"],
        "predictions": [], "outcome": None, "producer": None, "artifacts": [],
        "global_natural_evidence_created": False, "promotion_credit_created": False,
        "auto_fit_performed": False, "formal_order_allowed": False,
    }
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(identity))
            handle.flush()
            os.fsync(handle.fileno())
        # 第二個 writer 可能剛完成；鎖取得後再核 terminal，避免重跑 producer。
        if terminal.exists():
            raise PersonalNaturalOutcomeDailyError("daily receipt 已由另一 writer 完成；請重新讀回")
        if stop():
            raise InterruptedError("personal_daily_cancelled")
        _daily_verify_pins(request["source_pins"])
        if request.get("generation_argv"):
            body["producer"] = {}
            body["producer"] = _daily_produce(request["generation_argv"], request.get("timeout_seconds", 300), stop, body["producer"])
        _daily_verify_pins(request["source_pins"])
        if stop():
            raise InterruptedError("personal_daily_cancelled")
        queries = _daily_queries(paths["canonical_recommendation_output_root"])
        receipts = (capture_personal_daily_results(tuple(request["result_ids"]), queries, paths["personal_capture_root"])
                    if request["result_ids"] else ())
        capture_paths = [Path(value) for value in request["capture_paths"]]
        for receipt in receipts:
            if receipt.path not in capture_paths:
                capture_paths.append(receipt.path)
        for path in capture_paths:
            capture = read_personal_prediction_capture(path, queries, paths["personal_capture_root"])
            gross_view = (project_personal_capture_h20_gross(path, queries, paths["personal_capture_root"],
                          contract=gross_contract, lineage_reader=lineage_reader)
                          if gross_contract is not None else {
                              "status": "h20_gross_unavailable", "rows": [],
                              "blockers": ["controlled_gross_contract_not_injected"],
                          })
            body["predictions"].append({
                "path": str(path), "capture_id": capture["capture_id"], "result_id": capture["result_id"],
                "receipt_binding": capture["receipt_binding"], "decision_at": capture["decision_at"],
                "capture_sha256": _daily_artifact(path)["sha256"],
                "gross_view": gross_view,
            })
            body["artifacts"].append(_daily_artifact(path))
        if stop():
            raise InterruptedError("personal_daily_cancelled")
        outcome = run_personal_natural_outcome_daily(
            canonical_recommendation_output_root=paths["canonical_recommendation_output_root"],
            capture_paths=capture_paths, personal_capture_root=paths["personal_capture_root"],
            market_source_db=paths["market_source_db"], calendar_cache_path=paths["calendar_cache_path"],
            evaluation_at=datetime.fromisoformat(request["evaluation_at"].replace("Z", "+00:00")),
            isolated_output_root=paths["isolated_outcome_root"],
            temporary_closure_cache_path=paths.get("temporary_closure_cache_path"),
            cancelled=stop,
        )
        body["outcome"] = {"summary_path": str(outcome.summary_path), "summary_sha256": outcome.summary_sha256,
                           "capture_statuses": list(outcome.capture_statuses), "outcome_paths": [str(p) for p in outcome.outcome_paths]}
        body["artifacts"].extend(_daily_artifact(path) for path in (outcome.summary_path, *outcome.outcome_paths))
        _daily_verify_pins(request["source_pins"])
        body["status"] = outcome.status
        destination = terminal
    except (InterruptedError, KeyboardInterrupt) as exc:
        body.update(status="cancelled", error_type=type(exc).__name__, reason="personal_daily_cancelled")
        destination = root / "attempts" / f"{request_hash[7:]}-{identity['nonce']}.json"
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        body.update(status="failed", error_type=type(exc).__name__, reason=str(exc)[:500])
        destination = root / "attempts" / f"{request_hash[7:]}-{identity['nonce']}.json"
    finally:
        try:
            if "destination" in locals():
                digest, idempotent = _publish_create_only(destination, body, root)
        finally:
            # 只移除本程序以 EXCL 建立的協調 lock；不清原資料或其他 attempt。
            if _read_plain_optional(lock, root) == _canonical_bytes(identity):
                lock.unlink()
    return {**body, "payload_sha256": digest, "receipt_path": str(destination), "idempotent": idempotent}


__all__ = (
    "run_personal_model_daily",
    "MAX_CAPTURE_PATHS",
    "PERSONAL_NATURAL_OUTCOME_DAILY_SCHEMA_V1",
    "PERSONAL_NATURAL_OUTCOME_SCHEMA_V1",
    "PERSONAL_NATURAL_OUTCOME_SCHEMA_V2",
    "PersonalNaturalOutcomeConflict",
    "PersonalNaturalOutcomeDailyError",
    "PersonalNaturalOutcomeDailyReceiptV1",
    "run_personal_natural_outcome_daily",
)
