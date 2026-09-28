"""封存個人模式已保存推薦的原始模型投影，不重算推論。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app_module.personalization_action_recorder import (
    PersonalizationDecisionRecorder,
    PersonalizationDecisionRecorderError,
)
from app_module.personalization_contract import (
    read_personal_use_policy_snapshot_event,
)
from app_module.recommendation.contracts import (
    ExecutionStatus,
    RecommendationExecution,
    ReferenceKind,
)
from app_module.recommendation.personal_use_policy import (
    validate_personal_use_policy_snapshot,
)
from app_module.recommendation.queries import (
    RecommendationExecutionQueries,
    RecommendationExecutionReadModel,
    _read_regular_file_no_follow,
)
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
from ml_module.recommendation_cost_scenario import (
    RecommendationCostScenarioError,
    cost_scenario_from_metadata,
)


PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1 = "recommendation-personal-prediction-capture.v1"
PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2 = "recommendation-personal-prediction-capture.v2"
PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3 = "recommendation-personal-prediction-capture.v3"
PERSONAL_PREDICTION_CAPTURE_ORIGIN = "personal_saved_result"
PERSONAL_PROBABILITY_BASELINE_EVENT = "personal_probability_baseline_snapshot"
PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V1 = (
    "recommendation-personal-probability-baseline-event.v1"
)
PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2 = (
    "recommendation-personal-probability-baseline-event.v2"
)
PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V1 = (
    "recommendation-personal-probability-baseline-snapshot.v1"
)
PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2 = (
    "recommendation-personal-probability-baseline-snapshot.v2"
)
PERSONAL_FIXED_NULL_BENCHMARK_KIND = "fixed_null_benchmark_50pct"
PERSONAL_FIXED_NULL_BENCHMARK_ID = "null_benchmark_50pct_v1"
MAX_PERSONAL_CAPTURE_RECEIPT_BYTES = 32 * 1024 * 1024
MAX_PERSONAL_CAPTURE_FILE_BYTES = 64 * 1024 * 1024
MAX_PERSONAL_CAPTURE_PROJECTION_ROWS = 500
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REPARSE_POINT = 0x400
_MARKET_TIMEZONE = ZoneInfo("Asia/Taipei")


class PersonalPredictionCaptureError(ValueError):
    """已保存結果或個人捕獲資料無法安全驗證。"""


class PersonalPredictionCaptureConflict(PersonalPredictionCaptureError):
    """相同個人捕獲位置已存在不同內容；不覆寫既有 bytes。"""


@dataclass(frozen=True, slots=True)
class PersonalPredictionCaptureReceiptV1:
    capture_id: str
    path: Path
    payload_sha256: str
    result_id: str
    persisted_at: str
    decision_at: str
    capture_written_at: str
    idempotent: bool


def capture_personal_saved_result(
    result_id: str,
    queries: RecommendationExecutionQueries,
    personal_root: str | Path,
) -> PersonalPredictionCaptureReceiptV1:
    """從 canonical query readback create-only 封存個人模型已交付結果。"""

    if type(result_id) is not str or not result_id.strip():
        raise PersonalPredictionCaptureError("result_id 必須是非空字串")

    # 先以既有 read-side 取得 canonical/index/receipt 驗證結果；此流程不重算模型。
    read_model = queries.get(
        result_id,
        max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
    )
    if read_model is None:
        raise PersonalPredictionCaptureError("找不到已保存的 canonical 推薦結果")
    source = _source_snapshot(read_model, expected_result_id=result_id)

    root = _absolute_path(personal_root, "personal_root")
    _ensure_personal_root_separate(root, Path(source["receipt_binding"]["learning_root"]))
    _ensure_plain_directory(root)
    capture_directory = root / "captures"
    _ensure_plain_directory(capture_directory)

    capture_written_at = _utc_now_text()
    _require_time_order(
        source["decision_at"],
        source["receipt_binding"]["receipt_created_at"],
        source["persisted_at"],
        capture_written_at,
    )
    baseline_snapshot = source.get("probability_baseline_snapshot")
    snapshot_schema = (
        baseline_snapshot.get("schema_version")
        if isinstance(baseline_snapshot, Mapping)
        else None
    )
    schema_version = (
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3
        if snapshot_schema == PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2
        else (
            PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2
            if baseline_snapshot is not None
            else PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1
        )
    )
    body = {
        **source,
        "schema_version": schema_version,
        "capture_origin": PERSONAL_PREDICTION_CAPTURE_ORIGIN,
        "capture_written_at": capture_written_at,
    }
    capture_id = _capture_id(body)
    body["capture_id"] = capture_id
    body["payload_sha256"] = _payload_hash(body)
    encoded = _canonical_json_bytes(body)
    if len(encoded) > MAX_PERSONAL_CAPTURE_FILE_BYTES:
        raise PersonalPredictionCaptureError("個人捕獲超過檔案大小上限")

    destination = capture_directory / f"{capture_id[7:]}.json"
    _assert_path_chain_plain(destination.parent, require_final_directory=True)
    if destination.exists() or _is_link_or_reparse(destination):
        existing = _read_capture_file(destination, root=root)
        if _stable_capture_identity(existing) != _stable_capture_identity(body):
            raise PersonalPredictionCaptureConflict(
                "相同 result identity 已有不同個人捕獲；拒絕覆寫"
            )
        return _receipt_from_payload(destination, existing, idempotent=True)

    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".personal-prediction-", suffix=".tmp", dir=capture_directory
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _assert_path_chain_plain(destination.parent, require_final_directory=True)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            existing = _read_capture_file(destination, root=root)
            if _stable_capture_identity(existing) != _stable_capture_identity(body):
                raise PersonalPredictionCaptureConflict(
                    "相同 result identity 已有不同個人捕獲；拒絕覆寫"
                )
            return _receipt_from_payload(destination, existing, idempotent=True)
        published = _read_capture_file(destination, root=root)
        if published != body:
            raise PersonalPredictionCaptureError("個人捕獲發布後讀回不一致")
        return _receipt_from_payload(destination, published, idempotent=False)
    except PersonalPredictionCaptureError:
        raise
    except OSError as exc:
        raise PersonalPredictionCaptureError(
            f"無法 create-only 發布個人捕獲：{type(exc).__name__}"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise PersonalPredictionCaptureError(
                    "個人捕獲暫存檔無法清理；已發布內容保持不變"
                ) from exc


def read_personal_prediction_capture(
    capture_path: str | Path,
    queries: RecommendationExecutionQueries,
    personal_root: str | Path,
    *,
    expected_result_id: str | None = None,
) -> dict[str, Any]:
    """重驗個人捕獲 bytes，並以 canonical query 確認原保存結果仍完全相符。"""

    root = _absolute_path(personal_root, "personal_root")
    path = _absolute_path(capture_path, "capture_path")
    _assert_path_chain_plain(path, require_final_file=True)
    expected_directory = root / "captures"
    if path.parent != expected_directory or path.suffix.lower() != ".json":
        raise PersonalPredictionCaptureError("捕獲檔必須是 personal_root/captures 的直接子檔")
    payload = _read_capture_file(path, root=root)
    result_id = payload["result_id"]
    if expected_result_id is not None and result_id != expected_result_id:
        raise PersonalPredictionCaptureError("個人捕獲 result_id 不符")

    # readback 使用當前 canonical index/receipt；不可用今日政策補註舊結果。
    read_model = queries.get(
        result_id,
        max_receipt_bytes=MAX_PERSONAL_CAPTURE_RECEIPT_BYTES,
    )
    if read_model is None:
        raise PersonalPredictionCaptureError("原 canonical 推薦結果已不可讀")
    source = _source_snapshot(read_model, expected_result_id=result_id)
    _ensure_personal_root_separate(root, Path(source["receipt_binding"]["learning_root"]))
    expected_payload = _with_capture_identity_fields(source)
    if _stable_capture_identity(payload) != _stable_capture_identity(expected_payload):
        raise PersonalPredictionCaptureError(
            "個人捕獲與 canonical execution/receipt readback 不一致"
        )
    _require_time_order(
        payload["decision_at"],
        payload["receipt_binding"]["receipt_created_at"],
        payload["persisted_at"],
        payload["capture_written_at"],
    )
    return payload


def _source_snapshot(
    read_model: RecommendationExecutionReadModel,
    *,
    expected_result_id: str,
) -> dict[str, Any]:
    if not isinstance(read_model, RecommendationExecutionReadModel):
        raise PersonalPredictionCaptureError("query 未回傳 canonical read model")
    execution = read_model.execution
    if type(execution) is not RecommendationExecution:
        raise PersonalPredictionCaptureError("個人捕獲只接受 canonical execution，不接受 legacy 結果")
    if execution.result_id != expected_result_id or read_model.result_id != expected_result_id:
        raise PersonalPredictionCaptureError("canonical result identity 不一致")
    if (
        read_model.integrity_basis != "canonical_payload_and_index_verified"
        or not _is_sha256(read_model.payload_hash)
        or not _is_sha256(read_model.raw_artifact_sha256)
        or type(read_model.schema_version) is not str
        or type(read_model.schema_revision) is not int
        or read_model.persisted_at is None
    ):
        raise PersonalPredictionCaptureError("canonical index/artifact identity 未完整驗證")
    if execution.status is not ExecutionStatus.COMPLETED or execution.decision is None:
        raise PersonalPredictionCaptureError("只有已完成且已交付的推薦可建立個人捕獲")

    try:
        policy_event = read_personal_use_policy_snapshot_event(
            execution, expected_result_id=expected_result_id
        )
    except (TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("保存結果缺少有效個人政策快照") from exc
    if (
        policy_event["requested_mode"] != "personal_calibrated_probability"
        or policy_event["effective_mode"] != "personal_calibrated_probability"
    ):
        raise PersonalPredictionCaptureError("保存結果不是實際個人模型模式")
    try:
        policy_snapshot = validate_personal_use_policy_snapshot(
            policy_event["policy_snapshot"]
        )
    except (TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人政策 snapshot 無效") from exc
    candidate = policy_snapshot.get("candidate")
    if not isinstance(candidate, Mapping):
        raise PersonalPredictionCaptureError("個人政策沒有 pinned candidate")

    receipt_events = tuple(
        event
        for event in execution.events
        if event.event_type == "ml_projection_receipt_capture"
    )
    if len(receipt_events) != 1:
        raise PersonalPredictionCaptureError("保存結果沒有唯一的 ML receipt capture event")
    receipt_event = _json_mapping(receipt_events[0].details, "receipt event")
    expected_event_fields = {
        "attempted",
        "persisted",
        "readback_verified",
        "identity_verified",
        "path",
        "receipt_hash",
        "receipt_created_at",
        "error",
        "result_id",
        "decision_date",
        "candidate_id",
        "candidate_identity",
        "cost_scenario_hash",
        "cost_scenario_id",
        "projected_stock_codes",
        "projection_rows_sha256",
        "inference_source_hash",
        "inference_pit_hash",
        "feature_rows_sha256",
        "receipt_body_hash_verified",
    }
    if set(receipt_event) != expected_event_fields:
        raise PersonalPredictionCaptureError("ML receipt event 欄位不符合既有 schema")
    for flag in (
        "attempted",
        "persisted",
        "readback_verified",
        "identity_verified",
        "receipt_body_hash_verified",
    ):
        if receipt_event.get(flag) is not True:
            raise PersonalPredictionCaptureError(f"ML receipt event 尚未驗證：{flag}")
    if receipt_event.get("error") != "":
        raise PersonalPredictionCaptureError("ML receipt event 記錄了發布錯誤")
    if receipt_event.get("result_id") != expected_result_id:
        raise PersonalPredictionCaptureError("ML receipt event result identity 不符")

    bindings = tuple(execution.ml_receipt_refs)
    projection_refs = tuple(execution.ml_projection_refs)
    if len(bindings) != 1 or len(projection_refs) != 1:
        raise PersonalPredictionCaptureError("個人捕獲要求唯一 receipt 與 projection binding")
    binding = bindings[0]
    decision_at = policy_event["decision_at"]
    try:
        decision_datetime = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
        receipt_created_at = _canonical_utc(
            receipt_event.get("receipt_created_at"), "receipt_created_at"
        )
        persisted_at = _canonical_utc(read_model.persisted_at, "persisted_at")
    except (AttributeError, TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲的決策/保存時鐘無效") from exc
    decision_date = execution.context.as_of_date
    if (
        type(decision_date) is not date
        or binding.decision_date != decision_date
        or _taipei_decision_date(decision_datetime) != decision_date
        or execution.request.as_of_date != decision_date
    ):
        raise PersonalPredictionCaptureError("個人政策、Request、Context 與 receipt 日期不一致")
    if (
        binding.result_id != expected_result_id
        or binding.model_candidate_id != candidate.get("candidate_id")
        or receipt_event.get("decision_date") != decision_date.isoformat()
        or receipt_event.get("candidate_id") != binding.model_candidate_id
        or receipt_event.get("receipt_hash") != binding.receipt_hash
        or receipt_event.get("cost_scenario_hash") != binding.cost_scenario_hash
        or receipt_event.get("projection_rows_sha256") != projection_refs[0].reference_id
        or tuple(receipt_event.get("projected_stock_codes", ()))
        != binding.projected_stock_codes
    ):
        raise PersonalPredictionCaptureError("ML receipt event 與 canonical binding 不一致")
    if not all(
        _is_sha256(receipt_event.get(field))
        for field in (
            "receipt_hash",
            "projection_rows_sha256",
            "inference_source_hash",
            "inference_pit_hash",
            "feature_rows_sha256",
        )
    ):
        raise PersonalPredictionCaptureError("ML receipt event 缺少有效內容 hash")

    receipt_path = _absolute_path(receipt_event.get("path"), "receipt path")
    binding_path = _absolute_path(binding.receipt_ref.reference_id, "receipt binding path")
    if os.path.normcase(os.path.normpath(str(receipt_path))) != os.path.normcase(
        os.path.normpath(str(binding_path))
    ):
        raise PersonalPredictionCaptureError("ML receipt event 路徑與 binding 不一致")
    learning_root = _receipt_learning_root(
        receipt_path,
        expected_day=decision_date.isoformat(),
        expected_candidate_id=binding.model_candidate_id,
        expected_receipt_hash=binding.receipt_hash,
    )
    _assert_path_chain_plain(receipt_path, require_final_file=True)
    try:
        receipt_size = receipt_path.stat().st_size
    except OSError as exc:
        raise PersonalPredictionCaptureError("ML receipt 無法讀取") from exc
    if receipt_size > MAX_PERSONAL_CAPTURE_RECEIPT_BYTES:
        raise PersonalPredictionCaptureError("ML receipt 超過個人捕獲讀回上限")

    if read_model.ml_read_status != "verified":
        raise PersonalPredictionCaptureError("canonical query 的 ML receipt readback 未驗證")
    projection_rows = tuple(_json_mapping(row, "projection row") for row in read_model.ml_projection_rows)
    if not projection_rows or len(projection_rows) > MAX_PERSONAL_CAPTURE_PROJECTION_ROWS:
        raise PersonalPredictionCaptureError("模型 projection row 數量超出個人捕獲範圍")
    row_by_code: dict[str, dict[str, Any]] = {}
    for row in projection_rows:
        stock_code = row.get("stock_code")
        if type(stock_code) is not str or not stock_code.strip() or stock_code in row_by_code:
            raise PersonalPredictionCaptureError("receipt projection stock identity 重複或無效")
        row_by_code[stock_code] = row

    decision_items = tuple(execution.decision.items)
    if not decision_items or len(decision_items) > MAX_PERSONAL_CAPTURE_PROJECTION_ROWS:
        raise PersonalPredictionCaptureError("已交付推薦列數超出個人捕獲範圍")
    delivered_codes = tuple(item.stock_code for item in decision_items)
    if len(set(delivered_codes)) != len(delivered_codes):
        raise PersonalPredictionCaptureError("canonical delivered stock identity 重複")
    if any(code not in row_by_code for code in delivered_codes):
        raise PersonalPredictionCaptureError("receipt 沒有逐一對應 canonical delivered stocks")

    active_codes = tuple(
        code for code in delivered_codes if row_by_code[code].get("status") == "active_candidate"
    )
    fallback_codes = tuple(
        code for code in delivered_codes if row_by_code[code].get("status") == "rule_only"
    )
    if not active_codes:
        raise PersonalPredictionCaptureError("個人模型沒有影響任何已交付推薦列")
    if len(active_codes) + len(fallback_codes) != len(delivered_codes):
        raise PersonalPredictionCaptureError("已交付列含未分類的模型／規則投影")
    try:
        model_evidence = PersonalizationDecisionRecorder.validate_selected_stock_model_evidence(
            read_model=read_model,
            execution=execution,
            stock_code=active_codes[0],
            decision_date=decision_date.isoformat(),
            policy_snapshot=policy_snapshot,
            requested_mode=policy_event["requested_mode"],
            event_effective_mode=policy_event["effective_mode"],
        )
    except (TypeError, ValueError, PersonalizationDecisionRecorderError) as exc:
        raise PersonalPredictionCaptureError("原 inference receipt 與個人候選無法精確對列") from exc
    if model_evidence is None:
        raise PersonalPredictionCaptureError("已交付模型列沒有 active calibrated evidence")

    delivered_rows: list[dict[str, Any]] = []
    for item in decision_items:
        row = row_by_code[item.stock_code]
        if row.get("status") == "active_candidate":
            probability = row.get("calibrated_probability_bp")
            if (
                isinstance(probability, bool)
                or type(probability) is not int
                or not 0 <= probability <= 10_000
                or row.get("calibrated_probability_status") != "active_effective"
                or row.get("model_version") != binding.model_candidate_id
            ):
                raise PersonalPredictionCaptureError("已交付模型列 probability/version 無效")
        else:
            if (
                row.get("calibrated_probability_status") != "unavailable"
                or row.get("calibrated_probability_bp") is not None
                or row.get("after_cost_profit_probability_bp") is not None
                or bool(str(row.get("model_version") or "").strip())
            ):
                raise PersonalPredictionCaptureError(
                    "rule-only fallback 不可攜帶模型機率或模型版本"
                )
        delivered_rows.append(
            {
                "stock_code": item.stock_code,
                "rank": item.rank,
                "rule_score": _decimal_text(item.rule_score),
                "projection": row,
            }
        )

    receipt_binding = {
        "path": str(receipt_path),
        "learning_root": str(learning_root),
        "receipt_hash": binding.receipt_hash,
        "receipt_created_at": receipt_created_at,
        "decision_date": decision_date.isoformat(),
        "candidate_id": binding.model_candidate_id,
        "candidate_identity": _candidate_identity_pins(
            receipt_event.get("candidate_identity"), candidate
        ),
        "cost_scenario_hash": binding.cost_scenario_hash,
        "projected_stock_codes": list(binding.projected_stock_codes),
        "projection_rows_sha256": projection_refs[0].reference_id,
        "inference_source_hash": receipt_event["inference_source_hash"],
        "inference_pit_hash": receipt_event["inference_pit_hash"],
        "feature_rows_sha256": receipt_event["feature_rows_sha256"],
    }
    baseline_events = tuple(
        event
        for event in execution.events
        if event.event_type == PERSONAL_PROBABILITY_BASELINE_EVENT
    )
    if len(baseline_events) > 1:
        raise PersonalPredictionCaptureError(
            "保存結果包含重複的個人機率基準事件"
        )
    baseline_snapshot: dict[str, Any] | None = None
    if baseline_events:
        details = _json_mapping(
            baseline_events[0].details, "personal probability baseline event"
        )
        if set(details) != {"schema_version", "result_id", "decision_at", "snapshot"}:
            raise PersonalPredictionCaptureError(
                "個人機率基準事件欄位不符合 schema"
            )
        canonical_decision_at = _canonical_utc(decision_datetime, "decision_at")
        if (
            details.get("schema_version")
            not in {
                PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V1,
                PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2,
            }
            or details.get("result_id") != expected_result_id
            or details.get("decision_at") != canonical_decision_at
            or baseline_events[0].occurred_at != decision_datetime
        ):
            raise PersonalPredictionCaptureError(
                "個人機率基準事件的結果或決策時間不一致"
            )
        expected_snapshot_schema = (
            PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2
            if details.get("schema_version")
            == PERSONAL_PROBABILITY_BASELINE_EVENT_SCHEMA_V2
            else PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V1
        )
        snapshot_value = details.get("snapshot")
        if (
            not isinstance(snapshot_value, Mapping)
            or snapshot_value.get("schema_version") != expected_snapshot_schema
        ):
            raise PersonalPredictionCaptureError(
                "個人機率基準 event/snapshot 版本不相符"
            )
        try:
            baseline_snapshot = _validate_probability_baseline_snapshot(
                snapshot_value,
                result_id=expected_result_id,
                decision_at=canonical_decision_at,
                decision_date=decision_date.isoformat(),
                receipt_binding=receipt_binding,
                delivered_rows=delivered_rows,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalPredictionCaptureError(
                "個人機率基準事件與 canonical receipt 不一致"
            ) from exc

    captured_policy_event = {
        "schema_version": policy_event["schema_version"],
        "result_id": policy_event["result_id"],
        "decision_at": _canonical_utc(decision_datetime, "decision_at"),
        "policy_snapshot": policy_snapshot,
        "requested_mode": policy_event["requested_mode"],
        "effective_mode": policy_event["effective_mode"],
    }
    if policy_event["schema_version"] == (
        "recommendation-personal-use-policy-snapshot.v2"
    ):
        for marker in (
            "source_time_basis",
            "research_only",
            "official_historical_pit_verified",
        ):
            captured_policy_event[marker] = policy_event[marker]
    source_snapshot = {
        "result_id": expected_result_id,
        "canonical": {
            "payload_hash": read_model.payload_hash,
            "raw_artifact_sha256": read_model.raw_artifact_sha256,
            "schema_version": read_model.schema_version,
            "schema_revision": read_model.schema_revision,
            "integrity_basis": read_model.integrity_basis,
        },
        "decision_at": _canonical_utc(decision_datetime, "decision_at"),
        "persisted_at": persisted_at,
        "policy_event": captured_policy_event,
        "receipt_binding": receipt_binding,
        "delivered_rows": delivered_rows,
    }
    if baseline_snapshot is not None:
        source_snapshot["probability_baseline_snapshot"] = baseline_snapshot
    return source_snapshot


def _validate_probability_baseline_snapshot(
    value: object,
    *,
    result_id: str,
    decision_at: str,
    decision_date: str,
    receipt_binding: Mapping[str, Any],
    delivered_rows: object | None = None,
) -> dict[str, Any]:
    snapshot = _json_mapping(value, "personal probability baseline snapshot")
    common_fields = {
        "schema_version",
        "result_id",
        "decision_at",
        "decision_date",
        "receipt_hash",
        "projection_rows_sha256",
        "cost_scenario_hash",
        "projected_stock_codes",
        "upside_baseline_kind",
        "upside_baseline_id",
        "upside_probability_bp_by_symbol",
        "after_cost_baseline_status",
        "after_cost_baseline_id",
        "after_cost_probability_bp_by_symbol",
        "snapshot_sha256",
    }
    schema_version = snapshot.get("schema_version")
    required = set(common_fields)
    if schema_version == PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2:
        required.update(
            {
                "delivered_stock_codes",
                "model_active_stock_codes",
                "rule_only_fallback_stock_codes",
                "delivered_count",
                "model_active_count",
                "fallback_count",
                "model_coverage_bp",
                "cost_scenario",
            }
        )
    if set(snapshot) != required:
        raise ValueError("personal probability baseline snapshot fields are invalid")
    if (
        schema_version
        not in {
            PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V1,
            PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2,
        }
        or snapshot.get("result_id") != result_id
        or snapshot.get("decision_at") != decision_at
        or snapshot.get("decision_date") != decision_date
        or _canonical_utc(snapshot.get("decision_at"), "baseline decision_at")
        != decision_at
    ):
        raise ValueError("personal probability baseline result/clock identity mismatch")
    for field in (
        "receipt_hash",
        "projection_rows_sha256",
        "cost_scenario_hash",
    ):
        if not _is_sha256(snapshot.get(field)):
            raise ValueError(f"personal probability baseline {field} is invalid")
    if (
        snapshot.get("receipt_hash") != receipt_binding.get("receipt_hash")
        or snapshot.get("projection_rows_sha256")
        != receipt_binding.get("projection_rows_sha256")
        or snapshot.get("cost_scenario_hash")
        != receipt_binding.get("cost_scenario_hash")
    ):
        raise ValueError("personal probability baseline receipt binding mismatch")
    stock_codes = snapshot.get("projected_stock_codes")
    receipt_codes = receipt_binding.get("projected_stock_codes")
    if (
        type(stock_codes) is not list
        or not stock_codes
        or len(stock_codes) > MAX_PERSONAL_CAPTURE_PROJECTION_ROWS
        or any(type(code) is not str or not code.strip() for code in stock_codes)
        or len(set(stock_codes)) != len(stock_codes)
        or type(receipt_codes) is not list
        or stock_codes != receipt_codes
    ):
        raise ValueError("personal probability baseline projected stock set mismatch")
    active_codes = stock_codes
    fallback_codes: list[str] = []
    if schema_version == PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2:
        delivered_codes = snapshot.get("delivered_stock_codes")
        active_value = snapshot.get("model_active_stock_codes")
        fallback_value = snapshot.get("rule_only_fallback_stock_codes")
        if (
            type(delivered_codes) is not list
            or type(active_value) is not list
            or type(fallback_value) is not list
            or delivered_codes != stock_codes
            or not active_value
            or any(type(code) is not str or not code.strip() for code in delivered_codes)
            or any(type(code) is not str or not code.strip() for code in active_value)
            or any(type(code) is not str or not code.strip() for code in fallback_value)
            or len(set(delivered_codes)) != len(delivered_codes)
            or len(set(active_value)) != len(active_value)
            or len(set(fallback_value)) != len(fallback_value)
            or set(active_value).isdisjoint(fallback_value) is False
            or set(active_value) | set(fallback_value) != set(delivered_codes)
            or type(snapshot.get("delivered_count")) is not int
            or snapshot.get("delivered_count") != len(delivered_codes)
            or type(snapshot.get("model_active_count")) is not int
            or snapshot.get("model_active_count") != len(active_value)
            or type(snapshot.get("fallback_count")) is not int
            or snapshot.get("fallback_count") != len(fallback_value)
            or type(snapshot.get("model_coverage_bp")) is not int
            or snapshot.get("model_coverage_bp")
            != len(active_value) * 10_000 // len(delivered_codes)
        ):
            raise ValueError("personal baseline active/fallback partition is invalid")
        active_codes = active_value
        fallback_codes = fallback_value
        if delivered_rows is None or type(delivered_rows) is not list:
            raise ValueError("personal baseline requires the canonical delivered rows")
        if {str(row.get("stock_code")) for row in delivered_rows if isinstance(row, Mapping)} != set(
            delivered_codes
        ):
            raise ValueError("personal baseline delivered rows differ from its partition")
        delivered_by_code = {
            str(row["stock_code"]): row
            for row in delivered_rows
            if isinstance(row, Mapping)
        }
        for code in active_codes:
            row = delivered_by_code[code]
            projection = row.get("projection")
            if (
                not isinstance(projection, Mapping)
                or projection.get("status") != "active_candidate"
                or projection.get("calibrated_probability_status") != "active_effective"
                or projection.get("model_version") != receipt_binding.get("candidate_id")
            ):
                raise ValueError("personal baseline active row does not match its receipt")
        for code in fallback_codes:
            row = delivered_by_code[code]
            projection = row.get("projection")
            if (
                not isinstance(projection, Mapping)
                or projection.get("status") != "rule_only"
                or projection.get("calibrated_probability_status") != "unavailable"
                or projection.get("calibrated_probability_bp") is not None
                or projection.get("after_cost_profit_probability_bp") is not None
                or bool(str(projection.get("model_version") or "").strip())
            ):
                raise ValueError("personal baseline fallback row contains model output")
        try:
            scenario_value = snapshot.get("cost_scenario")
            scenario = cost_scenario_from_metadata(
                {
                    "cost_scenario": scenario_value,
                    "cost_scenario_hash": snapshot.get("cost_scenario_hash"),
                }
            )
        except (KeyError, TypeError, ValueError, RecommendationCostScenarioError) as exc:
            raise ValueError("personal baseline cost scenario is invalid") from exc
        if (
            not isinstance(scenario_value, Mapping)
            or scenario.to_dict(include_hash=True) != dict(scenario_value)
            or scenario.scenario_hash != snapshot.get("cost_scenario_hash")
            or scenario.scenario_hash != receipt_binding.get("cost_scenario_hash")
        ):
            raise ValueError("personal baseline cost scenario/receipt mismatch")
        for code in active_codes:
            projection = delivered_by_code[code]["projection"]
            scenario_projection_fields = {
                "cost_scenario_id": scenario.scenario_id,
                "cost_scenario_version": scenario.scenario_version,
                "cost_scenario_hash": scenario.scenario_hash,
                "cost_basis_bp": scenario.fixed_round_trip_cost_bp,
                "cost_policy_id": scenario.policy_id,
                "cost_policy_version": scenario.policy_version,
                "policy_estimate_date": scenario.policy_estimate_date,
                "research_order_amount_twd": scenario.to_dict(include_hash=True)[
                    "research_order_amount_twd"
                ],
                "research_order_quantity_shares": scenario.research_order_quantity_shares,
                "lot_type": scenario.lot_type,
                "instrument_type": scenario.instrument_type,
            }
            if (
                type(projection.get("cost_basis")) is not str
                or not projection.get("cost_basis")
                or any(
                    projection.get(field) != expected
                    for field, expected in scenario_projection_fields.items()
                )
            ):
                raise ValueError("personal baseline projection cost scenario mismatch")
        for code in fallback_codes:
            projection = delivered_by_code[code]["projection"]
            projection_hash = projection.get("cost_scenario_hash")
            if projection_hash is not None and projection_hash != scenario.scenario_hash:
                raise ValueError("personal fallback cost scenario conflicts with receipt")
    if (
        snapshot.get("upside_baseline_kind") != PERSONAL_FIXED_NULL_BENCHMARK_KIND
        or snapshot.get("upside_baseline_id") != PERSONAL_FIXED_NULL_BENCHMARK_ID
    ):
        raise ValueError("personal upside baseline must be the fixed null benchmark")
    upside_values = snapshot.get("upside_probability_bp_by_symbol")
    after_cost_values = snapshot.get("after_cost_probability_bp_by_symbol")
    if (
        not isinstance(upside_values, Mapping)
        or set(upside_values) != set(active_codes)
        or any(type(value) is not int or value != 5_000 for value in upside_values.values())
        or not isinstance(after_cost_values, Mapping)
        or set(after_cost_values) != set(active_codes)
    ):
        raise ValueError("personal probability baseline probability maps are invalid")
    after_cost_status = snapshot.get("after_cost_baseline_status")
    after_cost_id = snapshot.get("after_cost_baseline_id")
    if after_cost_status == "available":
        if type(after_cost_id) is not str or not after_cost_id.strip():
            raise ValueError("available after-cost baseline has no identity")
        if any(
            type(value) is not int or isinstance(value, bool) or not 0 <= value <= 10_000
            for value in after_cost_values.values()
        ):
            raise ValueError("available after-cost baseline has invalid probabilities")
    elif after_cost_status == "unavailable":
        if after_cost_id is not None or any(
            value is not None for value in after_cost_values.values()
        ):
            raise ValueError("unavailable after-cost baseline must remain null")
    else:
        raise ValueError("after-cost baseline availability is invalid")
    declared_hash = snapshot.get("snapshot_sha256")
    if not _is_sha256(declared_hash):
        raise ValueError("personal probability baseline snapshot hash format is invalid")
    body = {key: item for key, item in snapshot.items() if key != "snapshot_sha256"}
    if _payload_hash(body) != declared_hash:
        raise ValueError("personal probability baseline snapshot hash mismatch")
    return snapshot


def _candidate_identity_pins(value: object, candidate: Mapping[str, Any]) -> dict[str, str]:
    identity = _json_mapping(value, "receipt candidate identity")
    fields = (
        "candidate_id",
        "candidate_root",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
    )
    expected = {name: candidate.get(name) for name in fields}
    for name, expected_value in expected.items():
        actual = identity.get(name)
        if type(expected_value) is not str or type(actual) is not str:
            raise PersonalPredictionCaptureError(f"receipt candidate pin {name} 缺失")
        if name == "candidate_root":
            if _normalized_path(actual) != _normalized_path(expected_value):
                raise PersonalPredictionCaptureError("receipt candidate root 與 policy 不一致")
        elif actual != expected_value:
            raise PersonalPredictionCaptureError(f"receipt candidate pin {name} 與 policy 不一致")
    for optional_name in ("candidate_json_sha256", "personal_candidate_json_sha256"):
        actual = identity.get(optional_name)
        if actual is not None and actual != candidate.get("candidate_json_sha256"):
            raise PersonalPredictionCaptureError("receipt candidate JSON hash 與 policy 不一致")
    return {name: str(identity[name]) for name in fields}


def _capture_id(source: Mapping[str, Any]) -> str:
    canonical = source.get("canonical")
    policy_event = source.get("policy_event")
    receipt = source.get("receipt_binding")
    if not isinstance(canonical, Mapping) or not isinstance(policy_event, Mapping) or not isinstance(receipt, Mapping):
        raise PersonalPredictionCaptureError("capture identity 欄位不完整")
    identity = {
        "result_id": source.get("result_id"),
        "payload_hash": canonical.get("payload_hash"),
        "receipt_hash": receipt.get("receipt_hash"),
        "policy_sha256": _mapping_get(policy_event.get("policy_snapshot"), "policy_sha256"),
    }
    schema_version = source.get("schema_version", PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1)
    if schema_version in {
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
    }:
        baseline_snapshot = source.get("probability_baseline_snapshot")
        if not isinstance(baseline_snapshot, Mapping) or not _is_sha256(
            baseline_snapshot.get("snapshot_sha256")
        ):
            raise PersonalPredictionCaptureError("v2 capture 缺少 baseline snapshot identity")
        identity.update(
            {
                "capture_schema_version": schema_version,
                "probability_baseline_snapshot_sha256": baseline_snapshot[
                    "snapshot_sha256"
                ],
            }
        )
    elif schema_version != PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1:
        raise PersonalPredictionCaptureError("個人捕獲 schema version 不支援")
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def _with_capture_identity_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    baseline_snapshot = source.get("probability_baseline_snapshot")
    schema_version = (
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3
        if isinstance(baseline_snapshot, Mapping)
        and baseline_snapshot.get("schema_version")
        == PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2
        else (
            PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2
            if baseline_snapshot is not None
            else PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1
        )
    )
    expected = {
        **dict(source),
        "schema_version": schema_version,
        "capture_origin": PERSONAL_PREDICTION_CAPTURE_ORIGIN,
    }
    expected["capture_id"] = _capture_id(expected)
    return expected


def _stable_capture_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"capture_written_at", "payload_sha256"}
    }


def _read_capture_file(path: Path, *, root: Path) -> dict[str, Any]:
    absolute_root = _absolute_path(root, "personal_root")
    absolute_path = _absolute_path(path, "capture path")
    if absolute_root not in absolute_path.parents:
        raise PersonalPredictionCaptureError("個人捕獲檔超出 personal_root")
    try:
        identity_before = _capture_file_path_identity(
            absolute_path,
            root=absolute_root,
        )
        if identity_before[-1][1][4] > MAX_PERSONAL_CAPTURE_FILE_BYTES:
            raise PersonalPredictionCaptureError("個人捕獲檔超過大小上限")
        raw = _read_regular_file_no_follow(
            absolute_path,
            absolute_root,
            max_bytes=MAX_PERSONAL_CAPTURE_FILE_BYTES,
        )
        identity_after = _capture_file_path_identity(
            absolute_path,
            root=absolute_root,
        )
        if identity_after != identity_before:
            raise PersonalPredictionCaptureError("個人捕獲檔在讀取期間路徑身份改變")
    except PersonalPredictionCaptureError:
        raise
    except ExecutionArtifactIntegrityError as exc:
        if "超過讀取大小上限" in str(exc):
            raise PersonalPredictionCaptureError("個人捕獲檔超過大小上限") from exc
        raise PersonalPredictionCaptureError("個人捕獲檔無法安全穩定讀取") from exc
    except (OSError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲檔無法安全讀取") from exc
    if len(raw) > MAX_PERSONAL_CAPTURE_FILE_BYTES:
        raise PersonalPredictionCaptureError("個人捕獲檔超過大小上限")
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲不是有效 strict JSON") from exc
    if type(payload) is not dict:
        raise PersonalPredictionCaptureError("個人捕獲根節點必須是 object")
    base_required = {
        "schema_version",
        "capture_origin",
        "capture_id",
        "result_id",
        "canonical",
        "decision_at",
        "persisted_at",
        "policy_event",
        "receipt_binding",
        "delivered_rows",
        "capture_written_at",
        "payload_sha256",
    }
    schema_version = payload.get("schema_version")
    required = set(base_required)
    if schema_version in {
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
    }:
        required.add("probability_baseline_snapshot")
    if set(payload) != required:
        raise PersonalPredictionCaptureError("個人捕獲欄位不符合 schema")
    if (
        schema_version
        not in {
            PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1,
            PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
            PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
        }
        or payload.get("capture_origin") != PERSONAL_PREDICTION_CAPTURE_ORIGIN
        or type(payload.get("result_id")) is not str
    ):
        raise PersonalPredictionCaptureError("個人捕獲 schema/origin/result identity 無效")
    digest = payload.get("payload_sha256")
    if not _is_sha256(digest):
        raise PersonalPredictionCaptureError("個人捕獲 self-hash 格式無效")
    body = dict(payload)
    body.pop("payload_sha256", None)
    if _payload_hash(body) != digest:
        raise PersonalPredictionCaptureError("個人捕獲 self-hash 不符")
    if payload.get("capture_id") != _capture_id(payload):
        raise PersonalPredictionCaptureError("個人捕獲 identity 不符")
    if path.stem != str(payload["capture_id"])[7:]:
        raise PersonalPredictionCaptureError("個人捕獲檔名與 identity 不符")
    _validate_capture_nested_payload(payload)
    return payload


def _capture_file_path_identity(
    path: Path,
    *,
    root: Path,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """擷取 capture 路徑的 no-follow 身份，供讀取前後比較。"""

    absolute_path = _absolute_path(path, "capture path")
    absolute_root = _absolute_path(root, "personal_root")
    if absolute_root not in absolute_path.parents:
        raise PersonalPredictionCaptureError("個人捕獲檔超出 personal_root")
    _assert_path_chain_plain(absolute_path, require_final_file=True)
    current = Path(absolute_path.anchor)
    identities: list[tuple[str, tuple[int, ...]]] = []
    parts = absolute_path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        metadata = current.lstat()
        base = (
            int(metadata.st_dev),
            int(metadata.st_ino),
            int(metadata.st_mode),
            int(getattr(metadata, "st_file_attributes", 0)),
        )
        key: tuple[int, ...]
        if index == len(parts) - 1:
            key = (
                *base,
                int(metadata.st_size),
                int(metadata.st_mtime_ns),
                int(metadata.st_ctime_ns),
            )
        else:
            key = base
        identities.append((str(current), key))
    return tuple(identities)


def _validate_capture_nested_payload(payload: Mapping[str, Any]) -> None:
    schema_version = payload.get("schema_version")
    if schema_version not in {
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1,
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
    }:
        raise PersonalPredictionCaptureError("個人捕獲 schema version 不支援")
    has_snapshot = "probability_baseline_snapshot" in payload
    if (schema_version == PERSONAL_PREDICTION_CAPTURE_SCHEMA_V1) == has_snapshot:
        raise PersonalPredictionCaptureError("個人捕獲 schema 與 baseline 欄位不一致")
    if schema_version == PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2:
        baseline = payload.get("probability_baseline_snapshot")
        if not isinstance(baseline, Mapping) or baseline.get("schema_version") != PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V1:
            raise PersonalPredictionCaptureError("v2 capture 必須保留 v1 baseline snapshot")
    if schema_version == PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3:
        baseline = payload.get("probability_baseline_snapshot")
        if not isinstance(baseline, Mapping) or baseline.get("schema_version") != PERSONAL_PROBABILITY_BASELINE_SNAPSHOT_SCHEMA_V2:
            raise PersonalPredictionCaptureError("v3 capture 必須使用 v2 baseline snapshot")
    canonical = payload.get("canonical")
    if not isinstance(canonical, Mapping) or set(canonical) != {
        "payload_hash",
        "raw_artifact_sha256",
        "schema_version",
        "schema_revision",
        "integrity_basis",
    }:
        raise PersonalPredictionCaptureError("個人捕獲 canonical identity 欄位無效")
    if (
        not _is_sha256(canonical.get("payload_hash"))
        or not _is_sha256(canonical.get("raw_artifact_sha256"))
        or canonical.get("integrity_basis") != "canonical_payload_and_index_verified"
        or type(canonical.get("schema_version")) is not str
        or type(canonical.get("schema_revision")) is not int
    ):
        raise PersonalPredictionCaptureError("個人捕獲 canonical identity 無效")
    policy_event = payload.get("policy_event")
    v1_policy_event_fields = {
        "schema_version",
        "result_id",
        "decision_at",
        "policy_snapshot",
        "requested_mode",
        "effective_mode",
    }
    v2_source_markers = {
        "source_time_basis",
        "research_only",
        "official_historical_pit_verified",
    }
    if not isinstance(policy_event, Mapping):
        raise PersonalPredictionCaptureError("個人捕獲政策事件欄位無效")
    policy_event_schema = policy_event.get("schema_version")
    if policy_event_schema == "recommendation-personal-use-policy-snapshot.v1":
        expected_policy_event_fields = v1_policy_event_fields
    elif policy_event_schema == "recommendation-personal-use-policy-snapshot.v2":
        expected_policy_event_fields = v1_policy_event_fields | v2_source_markers
    else:
        raise PersonalPredictionCaptureError("個人捕獲政策事件版本不支援")
    if set(policy_event) != expected_policy_event_fields:
        raise PersonalPredictionCaptureError("個人捕獲政策事件欄位無效")
    if (
        policy_event.get("result_id") != payload.get("result_id")
        or policy_event.get("decision_at") != payload.get("decision_at")
        or policy_event.get("requested_mode") != "personal_calibrated_probability"
        or policy_event.get("effective_mode") != "personal_calibrated_probability"
    ):
        raise PersonalPredictionCaptureError("個人捕獲政策事件 identity/mode 無效")
    try:
        policy_snapshot = validate_personal_use_policy_snapshot(
            _json_mapping(policy_event.get("policy_snapshot"), "policy snapshot")
        )
        _canonical_utc(policy_event.get("decision_at"), "policy decision_at")
        _canonical_utc(payload.get("decision_at"), "decision_at")
        _canonical_utc(payload.get("persisted_at"), "persisted_at")
        _canonical_utc(payload.get("capture_written_at"), "capture_written_at")
    except (TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲 policy/time 驗證失敗") from exc
    if policy_snapshot.get("mode") != "personal_calibrated_probability":
        raise PersonalPredictionCaptureError("個人捕獲 policy 不是 model mode")
    if policy_event_schema == "recommendation-personal-use-policy-snapshot.v1":
        if policy_snapshot.get("schema_version") != "recommendation-personal-use-policy.v1":
            raise PersonalPredictionCaptureError("V1 個人政策事件的 snapshot schema 不一致")
    else:
        source_time_trust = policy_snapshot.get("source_time_trust")
        if (
            policy_snapshot.get("schema_version")
            != "recommendation-personal-use-policy.v2"
            or not isinstance(source_time_trust, Mapping)
            or not source_time_trust
            or policy_event.get("source_time_basis") != "user_declared_source_time"
            or type(policy_event.get("research_only")) is not bool
            or policy_event.get("research_only") is not True
            or type(policy_event.get("official_historical_pit_verified")) is not bool
            or policy_event.get("official_historical_pit_verified") is not False
            or source_time_trust.get("basis") != policy_event.get("source_time_basis")
            or type(source_time_trust.get("research_only")) is not bool
            or source_time_trust.get("research_only") is not policy_event.get("research_only")
            or type(source_time_trust.get("official_historical_pit_verified")) is not bool
            or source_time_trust.get("official_historical_pit_verified")
            is not policy_event.get("official_historical_pit_verified")
        ):
            raise PersonalPredictionCaptureError(
                "V2 個人捕獲來源時間標記與已保存 trust 不一致"
            )

    receipt = payload.get("receipt_binding")
    receipt_fields = {
        "path",
        "learning_root",
        "receipt_hash",
        "receipt_created_at",
        "decision_date",
        "candidate_id",
        "candidate_identity",
        "cost_scenario_hash",
        "projected_stock_codes",
        "projection_rows_sha256",
        "inference_source_hash",
        "inference_pit_hash",
        "feature_rows_sha256",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != receipt_fields:
        raise PersonalPredictionCaptureError("個人捕獲 receipt binding 欄位無效")
    for field in (
        "receipt_hash",
        "projection_rows_sha256",
        "inference_source_hash",
        "inference_pit_hash",
        "feature_rows_sha256",
    ):
        if not _is_sha256(receipt.get(field)):
            raise PersonalPredictionCaptureError(f"個人捕獲 {field} 無效")
    try:
        _canonical_utc(receipt.get("receipt_created_at"), "receipt_created_at")
        _absolute_path(receipt.get("path"), "receipt path")
        _absolute_path(receipt.get("learning_root"), "learning_root")
    except (TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲 receipt path/time 無效") from exc
    candidate = _json_mapping(policy_snapshot.get("candidate"), "policy candidate")
    candidate_identity = _json_mapping(receipt.get("candidate_identity"), "candidate identity")
    for field in (
        "candidate_id",
        "candidate_root",
        "candidate_manifest_hash",
        "candidate_artifact_hash",
        "candidate_freeze_hash",
        "dataset_hash",
    ):
        if candidate_identity.get(field) != candidate.get(field):
            raise PersonalPredictionCaptureError("個人捕獲 receipt candidate pins 與 policy 不符")
    rows = payload.get("delivered_rows")
    codes = receipt.get("projected_stock_codes")
    if (
        type(rows) is not list
        or not rows
        or len(rows) > MAX_PERSONAL_CAPTURE_PROJECTION_ROWS
        or type(codes) is not list
        or not codes
        or len(codes) > MAX_PERSONAL_CAPTURE_PROJECTION_ROWS
    ):
        raise PersonalPredictionCaptureError("個人捕獲 delivered/projection row 數量無效")
    delivered_codes: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "stock_code",
            "rank",
            "rule_score",
            "projection",
        }:
            raise PersonalPredictionCaptureError("個人捕獲 delivered row 欄位無效")
        stock_code = row.get("stock_code")
        rank = row.get("rank")
        if type(stock_code) is not str or not stock_code.strip():
            raise PersonalPredictionCaptureError("個人捕獲 stock_code 無效")
        if rank is not None and (isinstance(rank, bool) or type(rank) is not int):
            raise PersonalPredictionCaptureError("個人捕獲 rank 型別無效")
        projection = _json_mapping(row.get("projection"), "delivered projection")
        if projection.get("stock_code") != stock_code:
            raise PersonalPredictionCaptureError("個人捕獲 projection stock identity 不符")
        delivered_codes.append(stock_code)
    if len(set(delivered_codes)) != len(delivered_codes) or not set(delivered_codes).issubset(set(codes)):
        raise PersonalPredictionCaptureError("個人捕獲 delivered/projection stock identity 不符")
    try:
        decision_clock = datetime.fromisoformat(
            str(payload.get("decision_at", "")).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise PersonalPredictionCaptureError("個人捕獲 decision_at 無效") from exc
    if receipt.get("decision_date") != _taipei_decision_date(decision_clock).isoformat():
        raise PersonalPredictionCaptureError("個人捕獲 receipt decision date 與 decision clock 不符")
    if schema_version in {
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V2,
        PERSONAL_PREDICTION_CAPTURE_SCHEMA_V3,
    }:
        try:
            _validate_probability_baseline_snapshot(
                payload.get("probability_baseline_snapshot"),
                result_id=str(payload.get("result_id") or ""),
                decision_at=_canonical_utc(decision_clock, "decision_at"),
                decision_date=str(receipt.get("decision_date") or ""),
                receipt_binding=receipt,
                delivered_rows=rows,
            )
        except (TypeError, ValueError) as exc:
            raise PersonalPredictionCaptureError(
                "v2 個人捕獲 baseline snapshot 驗證失敗"
            ) from exc


def _receipt_learning_root(
    receipt_path: Path,
    *,
    expected_day: str,
    expected_candidate_id: str,
    expected_receipt_hash: str,
) -> Path:
    digest = expected_receipt_hash[7:]
    if (
        not _is_sha256(expected_receipt_hash)
        or receipt_path.name != f"{digest}.json"
        or receipt_path.parent.name != expected_candidate_id
        or receipt_path.parent.parent.name != expected_day
        or receipt_path.parent.parent.parent.name != "inference_projection"
    ):
        raise PersonalPredictionCaptureError("receipt path 不符合既有 inference projection layout")
    return receipt_path.parents[3]


def _ensure_personal_root_separate(personal_root: Path, learning_root: Path) -> None:
    if _paths_overlap(personal_root, learning_root):
        raise PersonalPredictionCaptureError(
            "personal_root 必須與 recommendation_learning root 完全分離"
        )


def _paths_overlap(left: Path, right: Path) -> bool:
    left_text = os.path.normcase(os.path.normpath(str(left)))
    right_text = os.path.normcase(os.path.normpath(str(right)))
    try:
        normalized_left = Path(left_text)
        normalized_right = Path(right_text)
        return (
            normalized_left == normalized_right
            or normalized_left in normalized_right.parents
            or normalized_right in normalized_left.parents
        )
    except (OSError, ValueError):
        return True


def _ensure_plain_directory(path: Path) -> None:
    absolute = _absolute_path(path, "directory")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise PersonalPredictionCaptureError("無法建立個人捕獲目錄") from exc
            try:
                metadata = current.lstat()
            except OSError as exc:
                raise PersonalPredictionCaptureError("個人捕獲目錄無法安全讀回") from exc
        except OSError as exc:
            raise PersonalPredictionCaptureError("個人捕獲路徑無法檢查") from exc
        if not stat.S_ISDIR(metadata.st_mode) or _metadata_is_reparse(metadata):
            raise PersonalPredictionCaptureError("個人捕獲目錄不得包含 symlink/reparse point")


def _assert_path_chain_plain(
    path: Path,
    *,
    require_final_directory: bool = False,
    require_final_file: bool = False,
) -> None:
    absolute = _absolute_path(path, "path")
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:]):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise PersonalPredictionCaptureError("個人捕獲路徑元件不存在或不可讀") from exc
        if stat.S_ISLNK(metadata.st_mode) or _metadata_is_reparse(metadata):
            raise PersonalPredictionCaptureError("個人捕獲路徑不得包含 symlink/reparse point")
        final = index == len(absolute.parts[1:]) - 1
        if final and require_final_directory and not stat.S_ISDIR(metadata.st_mode):
            raise PersonalPredictionCaptureError("個人捕獲目錄型別無效")
        if final and require_final_file and not stat.S_ISREG(metadata.st_mode):
            raise PersonalPredictionCaptureError("個人捕獲檔必須是一般檔案")
        if not final and not stat.S_ISDIR(metadata.st_mode):
            raise PersonalPredictionCaptureError("個人捕獲路徑中間元件不是目錄")


def _metadata_is_reparse(metadata: os.stat_result) -> bool:
    return bool(int(getattr(metadata, "st_file_attributes", 0)) & _REPARSE_POINT)


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or _metadata_is_reparse(metadata)


def _absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise PersonalPredictionCaptureError(f"{field} 必須是非空路徑")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise PersonalPredictionCaptureError(f"{field} 必須是絕對路徑")
    return Path(os.path.abspath(path))


def _normalized_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(_absolute_path(value, "candidate path"))))


def _json_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PersonalPredictionCaptureError(f"{field} 必須是 JSON object")
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if type(key) is not str:
            raise PersonalPredictionCaptureError(f"{field} JSON key 必須是字串")
        copied[key] = _json_value(item, f"{field}.{key}")
    return copied


def _json_value(value: Any, field: str) -> Any:
    if isinstance(value, Mapping):
        return _json_mapping(value, field)
    if type(value) in (tuple, list):
        return [_json_value(item, f"{field}[]") for item in value]
    if type(value) is float:
        if not math.isfinite(value):
            raise PersonalPredictionCaptureError(f"{field} 不能是非有限數值")
        return value
    if value is None or type(value) in (str, int, bool):
        return value
    raise PersonalPredictionCaptureError(f"{field} 含非 JSON 值 {type(value).__name__}")


def _decimal_text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is Decimal:
        if not value.is_finite():
            raise PersonalPredictionCaptureError("rule_score Decimal 必須有限")
        return str(value)
    if type(value) is int:
        return str(value)
    raise PersonalPredictionCaptureError("rule_score 只接受既有 Decimal/integer contract")


def _canonical_utc(value: object, field: str) -> str:
    if type(value) is datetime:
        parsed = value
    elif type(value) is str:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise PersonalPredictionCaptureError(f"{field} 必須是 ISO datetime") from exc
    else:
        raise PersonalPredictionCaptureError(f"{field} 必須是 aware datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PersonalPredictionCaptureError(f"{field} 必須含時區")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _taipei_decision_date(value: datetime) -> date:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PersonalPredictionCaptureError("decision_at 必須是含時區的 datetime")
    return value.astimezone(_MARKET_TIMEZONE).date()


def _require_time_order(*values: object) -> None:
    parsed = tuple(
        datetime.fromisoformat(_canonical_utc(value, "capture timestamp").replace("Z", "+00:00"))
        for value in values
    )
    if any(later < earlier for earlier, later in zip(parsed, parsed[1:])):
        raise PersonalPredictionCaptureError(
            "decision_at、receipt_created_at、persisted_at、capture_written_at 時序不合理"
        )


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _payload_hash(source: Mapping[str, Any]) -> str:
    body = dict(source)
    body.pop("payload_sha256", None)
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(body)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonalPredictionCaptureError("個人捕獲內容不是有限 canonical JSON") from exc


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("個人捕獲 JSON 含重複 object key")
        output[key] = value
    return output


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"個人捕獲 JSON 不接受 {value}")


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _mapping_get(value: object, key: str) -> object:
    if isinstance(value, Mapping):
        return value.get(key)
    return None


def _receipt_from_payload(
    path: Path,
    payload: Mapping[str, Any],
    *,
    idempotent: bool,
) -> PersonalPredictionCaptureReceiptV1:
    return PersonalPredictionCaptureReceiptV1(
        capture_id=str(payload["capture_id"]),
        path=path,
        payload_sha256=str(payload["payload_sha256"]),
        result_id=str(payload["result_id"]),
        persisted_at=str(payload["persisted_at"]),
        decision_at=str(payload["decision_at"]),
        capture_written_at=str(payload["capture_written_at"]),
        idempotent=idempotent,
    )
