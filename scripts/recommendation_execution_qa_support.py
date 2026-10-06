"""隔離推薦 QA CLI 的 sealed execution/save/readback 共用接線。"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.contracts import (
    ExecutionStatus,
    IndexStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    SaveReceipt,
)
from app_module.recommendation.execute import execute_recommendation
from app_module.recommendation.queries import RecommendationExecutionReadModel


def require_isolated_test_environment() -> None:
    """拒絕 QA CLI 在非 test profile 或 TEMP 外的資料／輸出根執行。"""

    if os.environ.get("PROFILE") != "test":
        raise RuntimeError("recommendation_qa_requires_PROFILE_test")
    temp_root = Path(tempfile.gettempdir()).resolve()
    for variable in ("DATA_ROOT", "OUTPUT_ROOT"):
        value = os.environ.get(variable)
        if not value or not Path(value).expanduser().resolve().is_relative_to(temp_root):
            raise RuntimeError(f"recommendation_qa_{variable}_must_be_under_TEMP")


def execute_and_readback(
    service: Any,
    config: Mapping[str, Any],
    *,
    max_stocks: int,
    top_n: int,
    as_of_date: str | date | None = None,
    capture_sink: MutableMapping[str, Any] | None = None,
) -> tuple[RecommendationExecution, RecommendationExecutionReadModel, SaveReceipt]:
    """用既有 engine、create-only writer 與 verified query 執行一個 QA run。"""

    require_isolated_test_environment()
    if getattr(service.config, "profile", None) != "test":
        raise RuntimeError("recommendation_qa_requires_PROFILE_test")
    raw_config_json = json.dumps(
        dict(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    request_config_snapshot = RecommendationConfigSnapshot(
        raw_config_json=raw_config_json,
        raw_json_sha256=(
            "sha256:" + hashlib.sha256(raw_config_json.encode("utf-8")).hexdigest()
        ),
    )
    execution = execute_recommendation(
        service,
        config,
        max_stocks=max_stocks,
        top_n=top_n,
        as_of_date=as_of_date,
        request_config_snapshot=request_config_snapshot,
        capture_sink=capture_sink,
    )
    if execution.status is not ExecutionStatus.COMPLETED:
        raise RuntimeError(
            f"qa_recommendation_execution_not_completed:{execution.status.value}"
        )

    composition = build_recommendation_composition(service.config)
    receipt = composition.save_service.save_execution(
        execution,
        label="Recommendation QA execution",
        notes="Isolated QA result; no production action.",
    )
    if receipt.result_id != execution.result_id or receipt.index_status is not IndexStatus.INDEXED:
        raise ValueError("qa_recommendation_save_receipt_mismatch")
    read_model = composition.queries.get(execution.result_id)
    if read_model is None or read_model.execution is None or read_model.legacy_result is not None:
        raise ValueError("qa_recommendation_verified_readback_missing")
    if (
        read_model.execution != execution
        or read_model.result_id != receipt.result_id
        or read_model.payload_hash != receipt.payload_hash
        or read_model.artifact_location != receipt.artifact_location
        or read_model.integrity_basis != "canonical_payload_and_index_verified"
    ):
        raise ValueError("qa_recommendation_verified_readback_mismatch")
    return execution, read_model, receipt


__all__ = ("execute_and_readback", "require_isolated_test_environment")
