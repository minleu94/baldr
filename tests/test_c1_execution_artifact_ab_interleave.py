"""C1 AB-P/N：同次 capture 經 create-only save 與 U4 readback 隔離。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
from threading import Barrier, Event, Lock, local
from types import SimpleNamespace
from typing import Any, Mapping

import pandas as pd
import pytest
from unittest.mock import MagicMock

from app_module.forward_position_thesis_candidate_producer import _sha256_json
from app_module.recommendation.contracts import (
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
from app_module.recommendation.ml_postcalibration_handoff import (
    CalibrationProjectionStatusV1,
    CalibrationReceiptEventFactsV1,
    CalibrationReceiptStatusV1,
    RecommendationPostCalibrationHandoffSinkV1,
    RecommendationPostCalibrationHandoffV1,
    encode_candidate_identity_event_json_v1,
)
from app_module.recommendation.persistence import (
    ExecutionIdentityConflict,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.queries import RecommendationExecutionQueries
from app_module.recommendation.save import RecommendationSaveService
from app_module.recommendation.codec import decode_execution_envelope
from app_module.recommendation_service import RecommendationService
from recommendation_test_support import build_recommendation_test_preparer
from data_module.result_artifact_store import ResultArtifactStore
from ml_module.recommendation_inference_provenance import (
    build_inference_projection_receipt,
    persist_inference_projection_receipt,
    read_inference_projection_receipt,
    validate_provenance_compatibility,
)
from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID
from scripts.scheduled.scheduled_clock import SCHEDULE_TIMEZONE


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "c1_cross_boundary"
SCENARIOS_PATH = FIXTURE_ROOT / "ab_interleave_scenarios.json"
SCENARIOS_RAW_SHA256 = "sha256:5112d36aafb67e323bb14759e7cfbda6b5d448cc8a008fd764d2ae63a7d500e3"
SCENARIOS_BYTE_LENGTH = 1_480
_IDENTITY_CONFIG_FIELDS = (
    "strategy_config_id",
    "strategy_config_hash",
    "strategy_config_schema",
    "strategy_config_spec",
    "universe_id",
    "universe_hash",
    "universe_identity_schema",
    "universe_policy_id",
    "universe_policy_hash",
    "universe_policy_schema",
    "universe_policy_spec",
    "universe_snapshot_id",
    "universe_snapshot_hash",
    "universe_snapshot_schema",
    "universe_snapshot_source_provider_id",
    "universe_snapshot_selected_codes_hash",
    "universe_snapshot_spec",
)


def _load_scenarios() -> dict[str, Any]:
    raw = SCENARIOS_PATH.read_bytes()
    assert len(raw) == SCENARIOS_BYTE_LENGTH
    assert "sha256:" + hashlib.sha256(raw).hexdigest() == SCENARIOS_RAW_SHA256
    return json.loads(raw.decode("utf-8"))


def _load_synthetic_training_builder():
    source = Path(__file__).with_name("test_recommendation_training_lineage.py")
    spec = importlib.util.spec_from_file_location(
        "c1_cross_boundary_synthetic_training_fixture", source
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("無法載入既有 synthetic training provenance fixture")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_verified_training_fixture


def _synthetic_receipts(
    tmp_path: Path,
    scenarios: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """用既有 synthetic provenance 建 immutable receipt；不執行模型推論。"""

    training, inference, cost_hash = _load_synthetic_training_builder()(
        tmp_path / "training-provenance"
    )
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=cost_hash,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    candidate_id = str(scenarios["receipt_candidate_id"])
    result: dict[str, dict[str, Any]] = {}
    for item in scenarios["runs"]:
        run = dict(item)
        receipt = build_inference_projection_receipt(
            decision_date=str(scenarios["decision_date"]),
            result_id=str(run["result_id"]),
            candidate_identity={"candidate_id": candidate_id},
            training_provenance=training,
            inference_provenance=inference,
            compatibility=compatibility,
            projections=(
                {
                    "stock_code": str(run["stock_code"]),
                    "status": "active_candidate",
                    "model_version": candidate_id,
                    "ranking_score_bp": run["receipt_ranking_score_bp"],
                    "ranking_percentile_bp": 8_200,
                    "cost_scenario_hash": cost_hash,
                },
            ),
        )
        path = persist_inference_projection_receipt(
            tmp_path / "synthetic-receipts", receipt
        )
        verified = read_inference_projection_receipt(
            path,
            expected_receipt_hash=receipt.receipt_hash,
            expected_decision_date=str(scenarios["decision_date"]),
            expected_candidate_id=candidate_id,
            expected_result_id=str(run["result_id"]),
            expected_stock_code=str(run["stock_code"]),
            expected_cost_scenario_hash=cost_hash,
        )
        assert verified.receipt_hash == receipt.receipt_hash
        result[str(run["result_id"])] = {
            "path": str(path),
            "receipt_hash": verified.receipt_hash,
            "payload": dict(verified.payload),
            "cost_scenario_hash": cost_hash,
        }
    assert len({item["receipt_hash"] for item in result.values()}) == 2
    assert len({item["payload"]["projection_rows_sha256"] for item in result.values()}) == 2
    return result


class _FrameProvider:
    def __init__(
        self,
        frames: dict[str, pd.DataFrame],
        *,
        barrier: Barrier,
    ) -> None:
        self.frames = frames
        self.barrier = barrier
        self.invocation = local()

    def __call__(self) -> pd.DataFrame:
        run_key = self.invocation.run_key
        self.barrier.wait(timeout=10)
        return self.frames[run_key].copy(deep=True)


class _ThreadClock(datetime):
    invocation = local()
    bases: dict[str, datetime] = {}

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        run_key = cls.invocation.run_key
        tick = getattr(cls.invocation, "tick", 0)
        cls.invocation.tick = tick + 1
        value = cls.bases[run_key] + timedelta(seconds=10 * tick)
        return value if tz is None else value.astimezone(tz)


def _market_frame(
    scenario: Mapping[str, Any],
    *,
    code: str | None = None,
    start: date = date(2025, 4, 1),
    close_price: str | None = None,
) -> pd.DataFrame:
    stock_code = code or str(scenario["stock_code"])
    close = Decimal(str(close_price or scenario["close_price"]))
    return pd.DataFrame(
        [
            {
                "日期": start + timedelta(days=offset),
                "available_date": start + timedelta(days=offset),
                "證券代號": stock_code,
                "證券名稱": str(scenario["stock_name"]),
                "收盤價": close,
                "成交股數": 1_000,
            }
            for offset in range(20)
        ]
    )


def _expected_market_data_fingerprint(frame: pd.DataFrame, cutoff: str) -> str:
    """依固定 fixture rows 獨立計算 service context 的 cutoff-bound source digest。"""

    source = frame.copy(deep=True)
    source["日期"] = pd.to_datetime(source["日期"], errors="coerce")
    source = source[source["日期"].notna()].copy()
    decision_limit = pd.Timestamp(cutoff)
    source = source[source["日期"] <= decision_limit].copy()
    if "available_date" in source:
        available = pd.to_datetime(source["available_date"], errors="coerce")
        source = source[
            available.notna() & (available <= decision_limit)
        ].copy()
        source["available_date"] = available.loc[source.index]
        source = source.sort_values("available_date", kind="stable").drop_duplicates(
            ["證券代號", "日期"], keep="last"
        )
    source["證券代號"] = source["證券代號"].astype(str)
    canonical = source.sort_values(
        ["證券代號", "日期"], kind="stable"
    ).reindex(sorted(source.columns), axis=1)
    fingerprint_payload = canonical.astype(str).to_dict("records")
    return hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _caller_config(scenario: Mapping[str, Any]) -> dict[str, Any]:
    run_key = str(scenario["run_key"])
    return {
        "profile_id": f"c1-cross-boundary-profile-{run_key}",
        "profile_version": "1",
        "strategy_version_id": "c1-cross-boundary-strategy-v1",
        "cost_model_id": "c1-cross-boundary-cost-v1",
        "benchmark_id": "TAIEX",
        "horizon_days": 20,
        "evidence_tier": "forward",
        "return_basis": "close_to_close_event_date",
        "as_of_date": str(scenario["as_of_date"]),
        "decision_date": "2025-05-02",
        "max_stocks": 1,
        "top_n": 1,
        "research_only": True,
        "profile_name": f"C1 synthetic run {run_key}",
        "look_ahead_check": "synthetic fixture uses only cutoff-bounded rows",
        "safety_boundary": {
            "confirm": False,
            "writes_evidence_db": False,
            "auto_trading": False,
            "lifecycle_action": False,
        },
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "numeric_text": str(scenario["numeric_text"]),
        "run_marker": run_key,
        "scheduled_snapshot": True,
    }


def _config_snapshot(config: dict[str, Any]) -> RecommendationConfigSnapshot:
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return RecommendationConfigSnapshot(
        raw_config_json=raw,
        raw_json_sha256="sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _typed_cohort(
    postprocess_input: RecommendationPostprocessInput,
) -> tuple[dict[str, Any], SnapshotCohort]:
    from scripts.scheduled.run_scheduled_recommendation_snapshot import (
        _build_snapshot_cohort,
    )

    raw = _build_snapshot_cohort(
        screening_matrix=[dict(row) for row in postprocess_input.screening_matrix],
        recommendations=list(postprocess_input.recommendations),
    )
    typed = SnapshotCohort(
        cohort_hash=raw["cohort_hash"],
        requested_symbols=tuple(raw["requested_symbols"]),
        eligible_symbols=tuple(raw["eligible_symbols"]),
        missing_symbols=tuple(raw["missing_symbols"]),
        degraded_symbols=tuple(raw["degraded_symbols"]),
        excluded_symbols=tuple(raw["excluded_symbols"]),
        requested_count=raw["requested_count"],
        eligible_count=raw["eligible_count"],
        missing_count=raw["missing_count"],
        degraded_count=raw["degraded_count"],
        excluded_count=raw["excluded_count"],
        coverage_status=SnapshotCohortCoverageStatus(raw["coverage_status"]),
        coverage_by_symbol={
            symbol: SnapshotCohortCoverage(
                status=row["status"],
                quality=row["quality"],
                stage=row["stage"],
                reason_codes=tuple(row["reason_codes"]),
                warnings=tuple(row["warnings"]),
            )
            for symbol, row in raw["coverage_by_symbol"].items()
        },
        eligible_definition=raw["eligible_definition"],
        missing_definition=raw["missing_definition"],
        degraded_definition=raw["degraded_definition"],
        excluded_definition=raw["excluded_definition"],
        schema_version=raw["schema_version"],
    )
    return raw, typed


def _postprocess(
    postprocess_input: RecommendationPostprocessInput,
) -> RecommendationPostprocessFacts:
    raw_cohort, cohort = _typed_cohort(postprocess_input)
    result_config = json.loads(
        postprocess_input.request.config_snapshot.raw_config_json
    )
    body_context = postprocess_input.body_result.context
    created_at = postprocess_input.context.created_at
    assert created_at is not None
    result_config["snapshot_cohort"] = raw_cohort
    result_config.update(
        {
            "data_as_of_date": body_context.as_of_date,
            "temporal_mode": body_context.temporal_mode,
            "cutoff_selection": body_context.cutoff_selection,
            "cutoff_policy": body_context.cutoff_policy,
            "decision_date": (
                created_at.astimezone(SCHEDULE_TIMEZONE).date().isoformat()
            ),
        }
    )
    for field in _IDENTITY_CONFIG_FIELDS:
        result_config[field] = deepcopy(postprocess_input.context.raw_context[field])
    evidence_identity = RecommendationRunEvidenceIdentity(
        cost_model_id=result_config["cost_model_id"],
        benchmark_id=result_config["benchmark_id"],
        industry_benchmark_id=result_config.get("industry_benchmark_id"),
        horizon_days=result_config["horizon_days"],
        evidence_tier=result_config["evidence_tier"],
        return_basis=result_config["return_basis"],
    )
    raw_result_config = json.dumps(
        result_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    result_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=raw_result_config,
        config_sha256=_sha256_json(result_config),
    )
    return RecommendationPostprocessFacts(
        result_id=postprocess_input.body_result.result_id,
        invocation_id=postprocess_input.body_result.invocation_id,
        created_at=postprocess_input.context.created_at,
        snapshot_cohort=cohort,
        evidence_identity=evidence_identity,
        result_config_snapshot=result_snapshot,
    )


def _stack(tmp_path: Path) -> tuple[
    ResultArtifactStore,
    RecommendationExecutionPersistence,
    RecommendationSaveService,
    RecommendationExecutionQueries,
]:
    runs_dir = tmp_path / "output" / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return (
        store,
        persistence,
        RecommendationSaveService(persistence),
        RecommendationExecutionQueries(persistence),
    )


@pytest.mark.parametrize("order_case", (0, 1), ids=("A-then-B", "B-then-A"))
def test_c1_ab_capture_create_only_save_and_single_readback_keep_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    order_case: int,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    scenarios = _load_scenarios()
    case = scenarios["save_order_cases"][order_case]
    run_by_key = {item["run_key"]: dict(item) for item in scenarios["runs"]}
    # Synthetic A/B invocations straddle local midnight while both use the same
    # market cutoff day. This makes the persisted scheduled date identify the
    # invocation that supplied each execution, independently of decision_at.
    run_by_key["A"].update(
        {
            "created_at": datetime(
                2025, 4, 30, 23, 59, tzinfo=SCHEDULE_TIMEZONE
            ).isoformat(),
            "service_run_started_at": datetime(
                2025, 5, 1, 0, 0, tzinfo=SCHEDULE_TIMEZONE
            ).isoformat(),
        }
    )
    run_by_key["B"].update(
        {
            "created_at": datetime(
                2025, 5, 1, 0, 1, tzinfo=SCHEDULE_TIMEZONE
            ).isoformat(),
            "service_run_started_at": datetime(
                2025, 5, 1, 0, 2, tzinfo=SCHEDULE_TIMEZONE
            ).isoformat(),
        }
    )
    expected_scheduled_dates = {"A": "2025-04-30", "B": "2025-05-01"}
    assert {
        run_key: datetime.fromisoformat(str(item["created_at"]))
        .astimezone(SCHEDULE_TIMEZONE)
        .date()
        .isoformat()
        for run_key, item in run_by_key.items()
    } == expected_scheduled_dates
    first_key, second_key = case
    first_id = str(run_by_key[first_key]["result_id"])
    second_id = str(run_by_key[second_key]["result_id"])
    synthetic_receipts = _synthetic_receipts(tmp_path, scenarios)
    run_by_stock_code = {
        str(item["stock_code"]): item for item in run_by_key.values()
    }
    original_frames = {
        key: _market_frame(item) for key, item in run_by_key.items()
    }
    updated_frames = {
        key: _market_frame(
            item,
            code=str(item["source_update_code"]),
            start=date.fromisoformat(str(scenarios["source_update_start_date"])),
            close_price=str(item["source_update_close_price"]),
        )
        for key, item in run_by_key.items()
    }
    expected_original_fingerprints = {
        key: _expected_market_data_fingerprint(
            frame, str(run_by_key[key]["as_of_date"])
        )
        for key, frame in original_frames.items()
    }
    expected_updated_fingerprints = {
        key: _expected_market_data_fingerprint(
            frame, str(run_by_key[key]["as_of_date"])
        )
        for key, frame in updated_frames.items()
    }
    assert all(
        expected_original_fingerprints[key] != expected_updated_fingerprints[key]
        for key in run_by_key
    )

    provider = _FrameProvider(
        {key: frame.copy(deep=True) for key, frame in original_frames.items()},
        barrier=Barrier(2),
    )
    config = SimpleNamespace(
        db_file=tmp_path / "missing-synthetic-source.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
        output_root=tmp_path / "synthetic-output",
        data_root=tmp_path / "synthetic-data",
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=provider
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = "合成 A/B 推薦理由"

    def generate_recommendations(
        frame: pd.DataFrame, _config: dict[str, Any]
    ) -> pd.DataFrame:
        assert not frame.empty
        source_code = str(frame["證券代號"].iloc[0])
        row = run_by_stock_code[source_code]
        source_last_row = frame.sort_values("日期", kind="stable").iloc[-1]
        source_close = Decimal(str(source_last_row["收盤價"]))
        assert source_close == Decimal(str(row["close_price"]))
        return pd.DataFrame(
            {
                "FinalScore": [Decimal(str(row["rule_score"]))],
                "TotalScore": [Decimal(str(row["rule_score"]))],
                "IndicatorScore": [Decimal(str(row["indicator_score"]))],
                "PatternScore": [Decimal(str(row["pattern_score"]))],
                "VolumeScore": [Decimal(str(row["volume_score"]))],
                "收盤價": [source_close],
            }
        )

    service.strategy_configurator.generate_recommendations = generate_recommendations

    def capture_synthetic_receipt(
        invocation_service: RecommendationService,
        _recommendations: list[Any],
        *,
        decision_date: str,
        **_kwargs: Any,
    ) -> None:
        # Key the synthetic receipt by this call's thread-local invocation, never shared last_*.
        run_key = str(provider.invocation.run_key)
        assert run_key in run_by_key
        result_id = str(run_by_key[run_key]["result_id"])
        receipt = synthetic_receipts[result_id]
        assert decision_date == str(scenarios["decision_date"])
        payload = receipt["payload"]
        candidate = payload["candidate_identity"]
        inference = payload["inference_provenance"]
        projections = payload["projections"]
        assert isinstance(candidate, Mapping)
        assert isinstance(inference, Mapping)
        assert isinstance(projections, list)
        handoff_sink = getattr(
            invocation_service,
            "_r026_post_calibration_handoff_sink",
            None,
        )
        assert isinstance(handoff_sink, RecommendationPostCalibrationHandoffSinkV1)
        handoff_sink.publish(
            RecommendationPostCalibrationHandoffV1(
                consumer_configured=(
                    getattr(invocation_service, "calibration_consumer", None)
                    is not None
                ),
                attempted=True,
                projection_status=CalibrationProjectionStatusV1.ACTIVE_CANDIDATE,
                receipt_status=CalibrationReceiptStatusV1.PERSISTED,
                receipt_event=CalibrationReceiptEventFactsV1(
                    payload_present=True,
                    attempted=True,
                    persisted=True,
                    readback_verified=True,
                    identity_verified=True,
                    path=str(receipt["path"]),
                    receipt_hash=str(receipt["receipt_hash"]),
                    result_id=str(payload.get("result_id") or ""),
                    decision_date=str(payload.get("decision_date") or ""),
                    candidate_id=str(candidate.get("candidate_id") or ""),
                    candidate_identity_json=encode_candidate_identity_event_json_v1(
                        candidate
                    ),
                    cost_scenario_hash=str(
                        payload.get("cost_scenario_hash") or ""
                    ),
                    cost_scenario_id=str(
                        inference.get("cost_scenario_id") or ""
                    ),
                    projected_stock_codes=tuple(
                        str(row.get("stock_code") or "")
                        for row in projections
                        if isinstance(row, Mapping)
                    ),
                    projection_rows_sha256=str(
                        payload.get("projection_rows_sha256") or ""
                    ),
                    inference_source_hash=str(
                        inference.get("inference_source_hash") or ""
                    ),
                    inference_pit_hash=str(
                        inference.get("inference_pit_hash") or ""
                    ),
                    feature_rows_sha256=str(
                        inference.get("feature_rows_sha256") or ""
                    ),
                ),
            )
        )
        invocation_service.last_run_context.update(
            {
                "calibration_projection_status": "active_candidate",
                "calibration_projection_receipt_status": "persisted",
                "calibration_projection_receipt": {
                    "path": receipt["path"],
                    "receipt_hash": receipt["receipt_hash"],
                },
            }
        )

    monkeypatch.setattr(
        RecommendationService,
        "_apply_recommendation_calibration",
        capture_synthetic_receipt,
    )
    _ThreadClock.bases = {
        key: datetime.fromisoformat(str(row["service_run_started_at"]))
        for key, row in run_by_key.items()
    }
    monkeypatch.setattr(recommendation_service_module, "datetime", _ThreadClock)

    callback_inputs: dict[str, RecommendationPostprocessInput] = {}
    callback_lock = Lock()
    both_callbacks = Event()
    first_release = Event()
    second_release = Event()
    first_returned = Event()

    def ordered_postprocess(
        postprocess_input: RecommendationPostprocessInput,
    ) -> RecommendationPostprocessFacts:
        with callback_lock:
            callback_inputs[postprocess_input.result_id] = postprocess_input
            if len(callback_inputs) == 2:
                both_callbacks.set()
        if postprocess_input.result_id == first_id:
            if not first_release.wait(timeout=10):
                raise TimeoutError("第一個 synthetic callback 未獲釋放")
            facts = _postprocess(postprocess_input)
            first_returned.set()
            return facts
        if not first_returned.wait(timeout=10):
            raise TimeoutError("第二個 synthetic callback 提前越過第一個")
        if not second_release.wait(timeout=10):
            raise TimeoutError("第二個 synthetic callback 未獲釋放")
        return _postprocess(postprocess_input)

    def invoke(run_key: str):
        item = run_by_key[run_key]
        provider.invocation.run_key = run_key
        _ThreadClock.invocation.run_key = run_key
        _ThreadClock.invocation.tick = 0
        caller_config = _caller_config(item)
        return service.execute_recommendation(
            caller_config,
            max_stocks=1,
            top_n=1,
            request_config_snapshot=_config_snapshot(caller_config),
            postprocess_callback=ordered_postprocess,
            created_at=datetime.fromisoformat(str(item["created_at"])),
            result_id=str(item["result_id"]),
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="c1-ab-cross-boundary") as pool:
        future_a = pool.submit(invoke, "A")
        future_b = pool.submit(invoke, "B")
        if not both_callbacks.wait(timeout=10):
            worker_errors: list[str] = []
            for run_key, future in (("A", future_a), ("B", future_b)):
                try:
                    error = future.exception(timeout=1)
                except TimeoutError:
                    continue
                if error is not None:
                    worker_errors.append(f"{run_key}: {type(error).__name__}: {error}")
            pytest.fail(
                "兩次 execution 未同時進入 postprocess callback；"
                f"worker errors={worker_errors}"
            )

        # 在兩份 private capture 已到達 callback 後改變 shared last_* 與 source provider。
        service.last_run_context = {
            "result_id": "shared-mutated",
            "config_sha256": "sha256:" + ("f" * 64),
        }
        service.last_screening_matrix = [{"stock_code": "SHARED_MUTATED"}]
        service.last_calibration_projections = {"SHARED_MUTATED": {"status": "wrong"}}

        provider.frames[first_key] = updated_frames[first_key].copy(deep=True)
        first_release.set()
        assert first_returned.wait(timeout=10), "第一份 capture 未完成封存"

        provider.frames[second_key] = updated_frames[second_key].copy(deep=True)
        second_release.set()
        execution_by_key = {
            "A": future_a.result(timeout=15),
            "B": future_b.result(timeout=15),
        }

    assert service.last_run_context["result_id"] == "shared-mutated"
    assert service.last_screening_matrix == [{"stock_code": "SHARED_MUTATED"}]
    assert service.last_calibration_projections == {
        "SHARED_MUTATED": {"status": "wrong"}
    }
    assert callback_inputs[first_id].recommendations[0].stock_code == str(
        run_by_key[first_key]["stock_code"]
    )
    assert callback_inputs[second_id].recommendations[0].stock_code == str(
        run_by_key[second_key]["stock_code"]
    )

    store, _, save, queries = _stack(tmp_path / "saved-runs")
    save_receipts: dict[str, Any] = {}
    readback_query_counts: dict[str, int] = {first_id: 0, second_id: 0}
    query_get = queries.get

    def counted_get(result_id: str):
        readback_query_counts[result_id] += 1
        return query_get(result_id)

    monkeypatch.setattr(queries, "get", counted_get)
    for run_key in case:
        execution = execution_by_key[run_key]
        scenario = run_by_key[run_key]
        assert execution.result_id == scenario["result_id"]
        legacy_context_event = next(
            event
            for event in execution.events
            if event.event_type == "legacy_invocation_context"
        )
        assert legacy_context_event.details["result_id"] == execution.result_id
        assert legacy_context_event.details["market_data_fingerprint"] == (
            expected_original_fingerprints[run_key]
        )
        assert legacy_context_event.details["market_data_fingerprint"] != (
            expected_updated_fingerprints[run_key]
        )
        assert execution.request.config_snapshot is not None
        assert f'"numeric_text":"{scenario["numeric_text"]}"' in (
            execution.request.config_snapshot.raw_config_json
        )
        assert execution.request.max_stocks == 1
        assert execution.request.top_n == 1
        assert execution.context.as_of_date == date.fromisoformat(
            str(scenario["as_of_date"])
        )
        assert execution.context.created_at == datetime.fromisoformat(
            str(scenario["created_at"])
        )
        clock_event = next(
            event
            for event in execution.events
            if event.event_type == "recommendation_invocation_clock_capture"
        )
        clock_details = clock_event.details
        service_started_at = datetime.fromisoformat(
            str(scenario["service_run_started_at"])
        )
        assert clock_details["created_at"] == execution.context.created_at
        assert clock_details["service_run_started_at"] == service_started_at
        assert clock_details["available_at"] == execution.context.available_at
        assert clock_details["decision_at"] == execution.context.decision_at
        assert execution.context.available_at is not None
        assert execution.context.available_at == service_started_at + timedelta(
            seconds=10
        )
        assert execution.context.decision_at is not None
        assert execution.context.available_at <= execution.context.decision_at
        assert execution.context.available_at.date().isoformat() == str(
            scenario["as_of_date"]
        )
        assert execution.context.result_config_snapshot is not None
        result_config = json.loads(
            execution.context.result_config_snapshot.raw_result_config_json
        )
        assert result_config["run_marker"] == run_key
        assert result_config["numeric_text"] == scenario["numeric_text"]
        assert result_config["decision_date"] == expected_scheduled_dates[run_key]
        assert result_config["snapshot_cohort"]["eligible_symbols"] == [
            scenario["stock_code"]
        ]
        assert execution.context.snapshot_cohort is not None
        assert execution.context.snapshot_cohort.eligible_symbols == (
            scenario["stock_code"],
        )
        assert execution.items[0].stock_code == scenario["stock_code"]
        assert execution.items[0].rule_score == Decimal(str(scenario["rule_score"]))
        assert execution.items[0].close_price == Decimal(str(scenario["close_price"]))
        assert execution.items[0].indicator_score == Decimal(
            str(scenario["indicator_score"])
        )
        assert execution.items[0].pattern_score == Decimal(
            str(scenario["pattern_score"])
        )
        assert execution.items[0].volume_score == Decimal(
            str(scenario["volume_score"])
        )
        assert len(execution.ml_receipt_refs) == 1
        assert execution.ml_receipt_refs[0].result_id == execution.result_id
        assert (
            execution.ml_receipt_refs[0].model_candidate_id
            == scenarios["receipt_candidate_id"]
        )
        assert execution.ml_receipt_refs[0].decision_date.isoformat() == str(
            scenarios["decision_date"]
        )
        assert execution.ml_receipt_refs[0].projected_stock_codes == (
            scenario["stock_code"],
        )
        assert execution.ml_receipt_refs[0].receipt_hash == synthetic_receipts[
            execution.result_id
        ]["receipt_hash"]

        save_receipts[run_key] = save.save_execution(
            execution,
            label=f"C1 synthetic {run_key}",
            notes="sealed capture A/B cross-boundary fixture",
            now=lambda: datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
        )
        stored_bytes = store.read_artifact(execution.result_id)
        assert stored_bytes is not None
        envelope = decode_execution_envelope(stored_bytes)
        assert envelope.schema_revision == 2
        assert envelope.execution == execution
        assert envelope.payload_hash == save_receipts[run_key].payload_hash

        # 唯一 U4 query seam 讀回此結果；沒有 post-save live reconstruction。
        loaded = queries.get(execution.result_id)
        assert loaded is not None
        assert loaded.execution == execution
        assert loaded.result_id == execution.result_id
        assert loaded.schema_revision == 2
        assert loaded.payload_hash == save_receipts[run_key].payload_hash
        assert loaded.raw_artifact_sha256 == "sha256:" + hashlib.sha256(
            stored_bytes
        ).hexdigest()
        assert loaded.ml_read_status == "verified"
        assert loaded.execution is not None
        assert loaded.execution.ml_receipt_refs == execution.ml_receipt_refs
        readback_legacy_context_event = next(
            event
            for event in loaded.execution.events
            if event.event_type == "legacy_invocation_context"
        )
        assert readback_legacy_context_event == legacy_context_event
        assert (
            readback_legacy_context_event.details["market_data_fingerprint"]
            == expected_original_fingerprints[run_key]
        )
        assert store.read_artifact(execution.result_id) == stored_bytes
        assert (
            store.artifact_root / store.artifact_name_for(execution.result_id)
        ).read_bytes() == stored_bytes
        assert len(loaded.ml_projection_rows) == 1
        assert loaded.ml_projection_rows[0]["stock_code"] == scenario["stock_code"]
        assert (
            loaded.ml_projection_rows[0]["model_version"]
            == scenarios["receipt_candidate_id"]
        )
        assert loaded.ml_projection_rows[0]["ranking_score_bp"] == scenario[
            "receipt_ranking_score_bp"
        ]
        assert (
            loaded.ml_projection_rows[0]["cost_scenario_hash"]
            == execution.ml_receipt_refs[0].cost_scenario_hash
        )
    assert readback_query_counts == {first_id: 1, second_id: 1}

    # 交換 result ID 後以同一 create-only store 儲存必須衝突，原 B artifact 保持完整。
    execution_a = execution_by_key["A"]
    execution_b = execution_by_key["B"]
    binding_a_for_b = replace(
        execution_a.ml_receipt_refs[0], result_id=execution_b.result_id
    )
    swapped_id = replace(
        execution_a,
        result_id=execution_b.result_id,
        ml_receipt_refs=(binding_a_for_b,),
    )
    with pytest.raises(ExecutionIdentityConflict):
        save.save_execution(swapped_id)
    preserved_b = queries.get(execution_b.result_id)
    assert preserved_b is not None
    assert preserved_b.execution == execution_b
    assert preserved_b.ml_read_status == "verified"

    # 將 A 的 saved execution 指向 B receipt/hash；獨立 query 只能回 unavailable，不能跨綁 rows。
    binding_b = execution_b.ml_receipt_refs[0]
    cross_receipt_cases = (
        (
            "receipt-identity-cross-link",
            replace(
                execution_a.ml_receipt_refs[0],
                receipt_ref=binding_b.receipt_ref,
                receipt_hash=binding_b.receipt_hash,
            ),
        ),
        (
            "receipt-hash-cross-link",
            replace(
                execution_a.ml_receipt_refs[0],
                receipt_hash=binding_b.receipt_hash,
            ),
        ),
    )
    for case_name, crossed_binding in cross_receipt_cases:
        cross_execution_a = replace(execution_a, ml_receipt_refs=(crossed_binding,))
        _, cross_persistence, cross_save, cross_queries = _stack(
            tmp_path / case_name
        )
        cross_save.save_execution(cross_execution_a)
        cross_readback = cross_queries.get(cross_execution_a.result_id)
        assert cross_readback is not None
        assert cross_readback.execution == cross_execution_a
        assert cross_readback.ml_read_status == "unavailable"
        assert cross_readback.ml_projection_rows == ()
        assert cross_readback.diagnostics
        assert cross_readback.diagnostics[0].startswith(
            "ml_receipt_validation_failed:"
        )
        assert (
            cross_persistence.read_verified(cross_execution_a.result_id)[1]
            == cross_execution_a
        )
