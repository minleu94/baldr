"""隔離的 H20 保存來源 UI 路徑；合成契約邊界明確標示。

當下觀測來源保管、capture writer/readers、SQLite 報告服務、cohort manifest
與 UI workers 均使用實際實作。契約 fixture 為合成資料，不含訓練模型，並由原始
bytes 與 lineage 驗證；不代表正式 fit receipt 或已啟用的正式模型。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import MethodType, SimpleNamespace
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QTabWidget, QVBoxLayout, QWidget

from app_module.recommendation.personal_current_observed_h20_capture import (
    capture_personal_current_observed_h20_prediction,
    digest,
    encoded,
)
from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation,
    publish_personal_h20_activation,
)
from app_module.recommendation.personal_h20_product_evidence import (
    publish_personal_h20_product_reference,
    save_personal_h20_daily_manifest,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ui_qt.main import MainWindow
from ui_qt.views.stock_research_workspace import StockResearchWorkspace


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = "2026-10-06"
SOURCE_DATE = "2026-10-05"
FEATURE_DATE = "2026-10-02"
OBSERVED_AT = "2026-10-06T12:00:00+00:00"


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _install_source_fixture_for_2382(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """使用專案實際的快照保管 fixture 與來源驗證器。"""
    import test_current_observed_capacity_replay as replay_fixture
    import test_current_observed_learning_capture as context_fixture
    import data_module.config as config_module
    from scripts.scheduled.run_personal_current_observed_h20_daily import _source_port

    original_populate = replay_fixture._populate_frozen_snapshot

    def populate_2382(database: Path) -> None:
        original_populate(database)
        connection = sqlite3.connect(database)
        try:
            connection.execute('UPDATE daily_prices SET "證券代號" = ?', ("2382",))
            connection.execute('UPDATE technical_indicators SET "證券代號" = ?', ("2382",))
            connection.commit()
        finally:
            connection.close()

    monkeypatch.setattr(replay_fixture, "_populate_frozen_snapshot", populate_2382)
    custody = context_fixture._write_pinned_context_fixture(tmp_path, monkeypatch)
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal_path = Path(str(custody["cycle_terminal"]))
    replay_fixture._install_pinned_context_and_capacity(
        fixture=custody,
        research_root=research_root,
        formal_root=tmp_path / "FA_Data" / "output",
        raw_run_id="raw-run-20261005",
        source_date=SOURCE_DATE,
        terminal_path=terminal_path,
    )

    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["current_symbols"] = ["2382"]
    terminal_sha = replay_fixture._write_json(terminal_path, terminal)
    pins = dict(terminal["same_run_pins"])
    pins.update(
        {
            "cycle_id": terminal["cycle_id"],
            "raw_run_id": terminal["raw_run_id"],
            "cycle_source_date": terminal["source_date"],
            "cycle_terminal_path": str(terminal_path.resolve()),
            "cycle_terminal_sha256": terminal_sha,
            "observed_at": OBSERVED_AT,
        }
    )

    snapshot_database = Path(pins["snapshot_database_path"])
    pinned_snapshot_sha256 = str(pins["snapshot_database_sha256"])
    snapshot_stat_before = snapshot_database.stat()
    snapshot_sha_before = _sha256_file(snapshot_database)
    assert snapshot_sha_before == pinned_snapshot_sha256, (
        "隔離 fixture 在來源讀取前已偏離資料庫 pin："
        f"path={snapshot_database}; expected={pinned_snapshot_sha256}; "
        f"actual={snapshot_sha_before}; size={snapshot_stat_before.st_size}; "
        f"mtime_ns={snapshot_stat_before.st_mtime_ns}"
    )

    market_root = tmp_path / "FA_Data"
    market_root.mkdir(parents=True, exist_ok=True)

    @dataclass
    class IsolatedTWStockConfig:
        data_root: Path = field(default_factory=lambda: market_root)
        output_root: Path = field(default_factory=lambda: market_root / "output")

    # 實際來源組合會要求路徑等於 TWStockConfig.data_root。
    # 測試只把這個設定值指向隔離根目錄。
    monkeypatch.setattr(config_module, "TWStockConfig", IsolatedTWStockConfig)
    binding: dict[str, Any] = {
        "cycle_id": terminal["cycle_id"],
        "cycle_terminal_sha256": terminal_sha,
        "pins": pins,
        "decision_date": DECISION_DATE,
        "data_root": str(market_root),
        "history_start_date": "2026-06-01",
        "feature_as_of_date": FEATURE_DATE,
        "symbols": ["2382"],
    }
    source = dict(_source_port(binding))
    snapshot_stat_after = snapshot_database.stat()
    snapshot_sha_after = _sha256_file(snapshot_database)
    assert snapshot_sha_after == snapshot_sha_before and (
        snapshot_stat_after.st_size,
        snapshot_stat_after.st_mtime_ns,
    ) == (snapshot_stat_before.st_size, snapshot_stat_before.st_mtime_ns), (
        "公開來源驗證期間隔離資料庫發生變動："
        f"before=({snapshot_sha_before}, {snapshot_stat_before.st_size}, "
        f"{snapshot_stat_before.st_mtime_ns}); after=({snapshot_sha_after}, "
        f"{snapshot_stat_after.st_size}, {snapshot_stat_after.st_mtime_ns})"
    )
    row = source["feature_rows_by_symbol"]["2382"]
    schema = tuple(tuple(item) for item in CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_schema)
    assert tuple(item[0] for item in schema) == tuple(item[0] for item in row["values"])
    assert row["feature_as_of_date"] == FEATURE_DATE
    assert source["decision_date"] == DECISION_DATE
    assert pins["cycle_source_date"] == SOURCE_DATE
    assert len({DECISION_DATE, SOURCE_DATE, row["feature_as_of_date"]}) == 3
    assert Path(pins["snapshot_database_path"]).is_file()
    return {
        "market_root": market_root,
        "snapshot_database": Path(pins["snapshot_database_path"]),
        "source_binding": source,
        "source_verifier": _source_port,
        "feature_schema": schema,
    }


def _synthetic_contract_fixture(
    tmp_path: Path,
    *,
    feature_schema: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    """建立有 hash pin 的合成 artifact／lineage，不執行模型訓練。"""
    import joblib
    from app_module.recommendation.personal_current_observed_h20_capture import encoded as capture_encoded
    from ml_module.model_artifact_manifest import ModelArtifactManifest
    from ml_module.personal_h20_gross_model_contract import H20GrossModelContract
    from ml_module.recommendation_calibration_training import (
        RecommendationCalibrationSample,
        recommendation_label_registry_hash,
    )
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
    from ml_module.recommendation_training_lineage import (
        build_recommendation_training_lineage,
        recommendation_training_dataset_hash,
        read_recommendation_training_lineage,
    )

    artifact_root = tmp_path / "synthetic_h20_contract" / "candidate"
    artifact_root.mkdir(parents=True)
    artifact_path = artifact_root / "model.joblib"
    # 保存有效序列化 fixture bytes，但不反序列化或用於推論。
    joblib.dump({"synthetic_fixture": True, "fit_performed": False}, artifact_path)
    artifact_hash = _sha256_file(artifact_path)
    candidate_id = "synthetic-ui-h20-candidate"
    model_id = "synthetic-ui-h20-model"
    dataset_id = "synthetic-ui-h20-dataset"
    model_family = "synthetic-ui-h20-gross"
    training_as_of = "2026-09-30"
    label_hash = recommendation_label_registry_hash()
    feature_hash = CORE_LONG_HISTORY_FEATURE_REGISTRY.registry_hash
    hyperparameters_hash = digest(capture_encoded({"synthetic": True, "fit_performed": False}))
    manifest = ModelArtifactManifest.create(
        model_id=model_id,
        dataset_id=dataset_id,
        created_run_id="synthetic-ui-h20-run",
        created_at="2026-09-30T10:00:00+08:00",
        model_family=model_family,
        feature_registry_hash=feature_hash,
        label_registry_hash=label_hash,
        feature_schema=feature_schema,
        training_as_of=training_as_of,
        hyperparameters_hash=hyperparameters_hash,
        library_versions={"joblib": joblib.__version__},
        serialization_format="joblib",
        artifact_filename=artifact_path.name,
        artifact_hash=artifact_hash,
    )
    manifest_path = artifact_root / "manifest.json"
    manifest_raw_sha256 = _write_json(manifest_path, manifest.to_dict())

    sample = RecommendationCalibrationSample.from_forward_return(
        row_id="historical-replay:synthetic-ui-h20-fixture",
        symbol="2382",
        decision_date="2026-07-01",
        feature_as_of_date="2026-06-30",
        feature_available_date="2026-06-30",
        label_end_date="2026-07-29",
        label_available_date="2026-07-29",
        feature_values=tuple(0 for _ in feature_schema),
        stock_return_bp=125,
        benchmark_return_bp=25,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=20,
        rule_probability_bp=5000,
    )
    dataset_hash = recommendation_training_dataset_hash((sample,))
    cost_scenario = build_legacy_cost_scenario(50)
    lineage = build_recommendation_training_lineage(
        learning_root=artifact_root / "lineage-source",
        run_id="synthetic-ui-h20-lineage",
        run_scope="synthetic-no-fit-ui-journey",
        decision_date="2026-08-01",
        training_as_of=training_as_of,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        samples=(sample,),
        feature_schema=feature_schema,
        feature_registry_hash=feature_hash,
        fixed_round_trip_cost_bp=50,
        cost_scenario=cost_scenario,
        dataset_quality={
            "research_only": True,
            "training_semantics": "historical_research_only",
            "synthetic_fixture": True,
            "fit_performed": False,
        },
        candidate_id=candidate_id,
        candidate_manifest_hash=manifest.manifest_hash,
        candidate_artifact_hash=artifact_hash,
        source_groups={"replay": (sample,)},
    )
    lineage_path = artifact_root / "lineage.json"
    lineage_raw_sha256 = _write_json(lineage_path, lineage.to_dict())
    candidate = {
        "schema_version": "synthetic-h20-ui-contract-fixture.v1",
        "candidate_id": candidate_id,
        "model_id": model_id,
        "model_version": model_id,
        "dataset_id": dataset_id,
        "dataset_hash": dataset_hash,
        "model_family": model_family,
        "feature_schema": [list(item) for item in feature_schema],
        "feature_registry_hash": feature_hash,
        "label_registry_hash": label_hash,
        "manifest_hash": manifest.manifest_hash,
        "artifact_hash": artifact_hash,
        "lineage_hash": lineage.manifest_hash,
        "training_source_hash": lineage.payload["training_source_hash"],
        "training_pit_hash": lineage.payload["training_pit_hash"],
        "training_as_of": training_as_of,
        "candidate_blockers": ["synthetic_fixture_no_model_fit_or_activation"],
        "fit_performed": False,
        "production_action_allowed": False,
    }
    candidate_path = artifact_root / "candidate.json"
    candidate_raw_sha256 = _write_json(candidate_path, candidate)
    contract = H20GrossModelContract(
        artifact_root=str(artifact_root.resolve()),
        lineage_path=str(lineage_path.resolve()),
        model_id=model_id,
        model_version=model_id,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        candidate_id=candidate_id,
        model_family=model_family,
        feature_schema=feature_schema,
        feature_registry_hash=feature_hash,
        label_registry_hash=label_hash,
        manifest_hash=manifest.manifest_hash,
        manifest_raw_sha256=manifest_raw_sha256,
        artifact_hash=artifact_hash,
        candidate_raw_sha256=candidate_raw_sha256,
        lineage_hash=lineage.manifest_hash,
        lineage_raw_sha256=lineage_raw_sha256,
        training_source_hash=str(lineage.payload["training_source_hash"]),
        training_pit_hash=str(lineage.payload["training_pit_hash"]),
        training_as_of=training_as_of,
        installed_library_versions={"joblib": joblib.__version__},
    )
    marker_path = artifact_root.parent / "synthetic_contract_fixture.json"
    marker_hash = _write_json(
        marker_path,
        {
            "schema": "synthetic-h20-ui-contract-fixture.v1",
            "fit_performed": False,
            "production_activation": False,
            "note": "This marker is not a production fit receipt.",
        },
    )
    binding = {
        "candidate_id": contract.candidate_id,
        "contract_hash": contract.contract_hash,
        "artifact_hash": contract.artifact_hash,
        "lineage_hash": contract.lineage_hash,
        "fit_receipt_sha256": marker_hash,
        "model_id": contract.model_id,
        "model_version": contract.model_version,
        "fit_receipt_path": str(marker_path.resolve()),
        "artifact_root": str(artifact_root.resolve()),
        "feature_schema": [list(item) for item in feature_schema],
    }

    def verify_synthetic_contract(value: Mapping[str, Any]) -> Mapping[str, Any]:
        if dict(value) != binding:
            raise ValueError("synthetic_contract_identity_mismatch")
        if _sha256_file(marker_path) != marker_hash:
            raise ValueError("synthetic_contract_marker_pin_mismatch")
        if _sha256_file(artifact_path) != contract.artifact_hash:
            raise ValueError("synthetic_contract_artifact_pin_mismatch")
        if _sha256_file(manifest_path) != contract.manifest_raw_sha256:
            raise ValueError("synthetic_contract_manifest_pin_mismatch")
        if _sha256_file(candidate_path) != contract.candidate_raw_sha256:
            raise ValueError("synthetic_contract_candidate_pin_mismatch")
        if _sha256_file(lineage_path) != contract.lineage_raw_sha256:
            raise ValueError("synthetic_contract_lineage_pin_mismatch")
        manifest_body = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_body = json.loads(candidate_path.read_text(encoding="utf-8"))
        if (
            manifest_body.get("manifest_hash") != contract.manifest_hash
            or manifest_body.get("artifact_hash") != contract.artifact_hash
            or candidate_body.get("candidate_id") != contract.candidate_id
            or candidate_body.get("manifest_hash") != contract.manifest_hash
            or candidate_body.get("lineage_hash") != contract.lineage_hash
        ):
            raise ValueError("synthetic_contract_artifact_identity_mismatch")
        verified_lineage = read_recommendation_training_lineage(
            lineage_path,
            expected_manifest_hash=contract.lineage_hash,
            expected_dataset_hash=contract.dataset_hash,
            expected_candidate_id=contract.candidate_id,
        )
        if (
            verified_lineage.payload.get("training_source_hash") != contract.training_source_hash
            or verified_lineage.payload.get("training_pit_hash") != contract.training_pit_hash
        ):
            raise ValueError("synthetic_contract_lineage_identity_mismatch")
        return deepcopy(binding)

    return {
        "contract": contract,
        "binding": binding,
        "verifier": verify_synthetic_contract,
        "marker_path": marker_path,
        "marker_hash": marker_hash,
    }


def _build_saved_h20_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    import scripts.scheduled.run_personal_current_observed_h20_daily as daily_runner
    import scripts.scheduled.personal_h20_daily_hook as daily_hook
    import app_module.recommendation.personal_current_observed_h20_capture as capture_module

    # 保留 2026-10-05 的來源 pins，在下一個決策日觀測，並保留更早的特徵截止日。
    class FixtureDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            fixed = datetime.fromisoformat(OBSERVED_AT)
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(capture_module, "datetime", FixtureDateTime)
    source_fixture = _install_source_fixture_for_2382(tmp_path, monkeypatch)
    contract_fixture = _synthetic_contract_fixture(
        tmp_path,
        feature_schema=source_fixture["feature_schema"],
    )
    market_root = Path(source_fixture["market_root"])
    personal_root = market_root / "personal" / "recommendation_h20"
    contract = contract_fixture["contract"]
    activation = PersonalH20Activation(
        revision=1,
        enabled=True,
        scope_id="ui-h20-saved-source-journey",
        market_root=str(market_root),
        personal_root=str(personal_root),
        fit_receipt=str(contract_fixture["marker_path"]),
        fit_receipt_sha256=str(contract_fixture["marker_hash"]),
        candidate_id=contract.candidate_id,
        model_id=contract.model_id,
        model_contract_hash=contract.contract_hash,
        history_start_date="2026-06-01",
    )
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)

    ports = {
        "source_verifier": source_fixture["source_verifier"],
        "contract_verifier": contract_fixture["verifier"],
    }
    monkeypatch.setattr(daily_runner, "personal_current_observed_h20_read_ports", lambda: ports)
    row = source_fixture["source_binding"]["feature_rows_by_symbol"]["2382"]
    request = {
        "symbol": "2382",
        "decision_date": DECISION_DATE,
        "feature_as_of_date": row["feature_as_of_date"],
        "feature_available_date": DECISION_DATE,
        "feature_schema": contract_fixture["binding"]["feature_schema"],
        "feature_values": [value for _, value in row["values"]],
        "feature_snapshot_hash": row["row_sha256"],
        "feature_source_hash": source_fixture["source_binding"]["source_fingerprint"],
        "model_contract_hash": contract.contract_hash,
    }
    prediction_id = "personal-h20:" + digest(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )[7:]
    prediction = {
        "request": request,
        "status": "h20_gross_available",
        "predicted_gross_return_bp": 1234,
        "model_id": contract.model_id,
        "model_version": contract.model_version,
        "model_contract_hash": contract.contract_hash,
        "artifact_hash": contract.artifact_hash,
        "lineage_hash": contract.lineage_hash,
        "blockers": [],
        "target": "absolute_forward_stock_return_bp",
        "horizon_trading_days": 20,
        "price_basis": "close_to_close_event_date",
        "cost_basis": "no_cost_gross",
        "contract_version": "personal-h20-gross.v1",
        "formal_eligible": False,
        "natural_evidence_eligible": False,
        "production_action_allowed": False,
        "prediction_id": prediction_id,
    }
    saved_capture = capture_personal_current_observed_h20_prediction(
        root=personal_root,
        source_binding=source_fixture["source_binding"],
        contract_binding=contract_fixture["binding"],
        symbol="2382",
        source_verifier=source_fixture["source_verifier"],
        contract_verifier=contract_fixture["verifier"],
        predictor=lambda: deepcopy(prediction),
    )
    manifest_path, manifest_sha256, manifest = save_personal_h20_daily_manifest(
        activation,
        {
            "status": "completed",
            "candidate_id": activation.candidate_id,
            "contract_hash": activation.model_contract_hash,
            "cycle_id": source_fixture["source_binding"]["cycle_id"],
            "captures": [saved_capture],
        },
        expected_symbols=["2382"],
        prediction_reader=daily_hook.read_personal_h20_prediction,
    )
    publish_personal_h20_product_reference(
        activation,
        receipt_path=str(manifest_path),
        receipt_sha256=manifest_sha256,
        decision_date=DECISION_DATE,
        cycle_id=source_fixture["source_binding"]["cycle_id"],
    )
    # 確保 activation 使用一般 market-root 路徑，不受環境變數覆寫。
    monkeypatch.delenv("PERSONAL_H20_ACTIVATION_CONFIG", raising=False)
    return {
        **source_fixture,
        "activation": activation,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "saved_capture": saved_capture,
        "contract_fixture": contract_fixture,
    }


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _wait_until(predicate: Any, *, timeout_ms: int = 12_000) -> None:
    app = _app()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        # 保留 Qt 事件泵並讓出 GIL，避免背景 Python worker 被 qWait 飢餓。
        time.sleep(0.01)
    assert predicate(), "timed out waiting for the real Qt worker route"


def _saved_h20_diagnostic(window: Any, report_view: Any, reader_calls: object) -> str:
    """輸出隔離 UI journey 的原始來源、worker 與證據狀態。"""

    worker = getattr(window, "_personal_h20_worker", None)
    try:
        worker_state = None if worker is None else {
            "running": worker.isRunning(),
            "finished": worker.isFinished(),
            "cancelled": worker.is_cancel_requested(),
        }
    except RuntimeError as exc:
        worker_state = f"deleted:{exc}"
    workspace = window.stock_research_workspace
    workspace_evidence = getattr(workspace, "personal_h20_saved_evidence", None)
    cached_evidence = getattr(window, "_personal_h20_saved_evidence", None)
    context = getattr(report_view, "context", None)
    try:
        resolved_origin = window._personal_h20_saved_origin_for_context(context)
    except Exception as exc:
        resolved_origin = f"error:{type(exc).__name__}:{exc}"
    return (
        f"reader_calls={reader_calls!r}; context={context!r}; "
        f"origin={getattr(window, '_personal_h20_research_origin', None)!r}; "
        f"resolved_origin={resolved_origin!r}; "
        f"saved_context={getattr(window, '_personal_h20_saved_context', None)!r}; "
        f"saved_reference={getattr(window, '_personal_h20_saved_reference', None)!r}; "
        f"workspace_evidence={workspace_evidence!r}; "
        f"workspace_reason={getattr(workspace_evidence, 'reason', None)!r}; "
        f"cached_evidence={cached_evidence!r}; "
        f"cached_reason={getattr(cached_evidence, 'reason', None)!r}; "
        f"raw_tooltip={workspace.personal_h20_saved_summary.toolTip()!r}; "
        f"summary={workspace.personal_h20_saved_summary.text()!r}; "
        f"worker={worker_state!r}; busy={workspace.personal_h20_saved_busy}; "
        f"generation={getattr(window, '_personal_h20_generation', None)!r}; "
        f"current_pins={tuple(getattr(context, name, None) for name in ('stock_code', 'decision_date', 'data_date', 'source_id', 'source_snapshot_id', 'source_snapshot_hash', 'profile_id', 'source_version', 'source_kind', 'source_workspace'))!r}"
    )


def _wait_for_saved_h20_read(
    window: Any,
    report_view: Any,
    reader_calls: object,
    predicate: Any,
    *,
    timeout_ms: int = 45_000,
) -> None:
    try:
        _wait_until(predicate, timeout_ms=timeout_ms)
    except AssertionError as exc:
        raise AssertionError(
            f"{exc}; {_saved_h20_diagnostic(window, report_view, reader_calls)}"
        ) from exc


def _trace_saved_h20_route(
    window: Any,
    report_view: Any,
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loaded: list[Any],
    failed: list[str],
) -> Any:
    """保存完整 UI 路徑的階段、Qt 執行緒與 H20 發布診斷。"""

    trace_path = tmp_path / "h20_saved_route_thread_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    trace_started = time.monotonic()

    def trace(stage: str, detail: str = "") -> None:
        event = {
            "elapsed_seconds": round(time.monotonic() - trace_started, 6),
            "stage": stage,
            "thread_id": threading.get_ident(),
            "qt_gui_thread": QThread.currentThread() == app.thread(),
            "detail": detail[:500],
        }
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def capture_report_loaded(report: object) -> None:
        trace("report_loaded", str(getattr(report, "stock_code", "")))
        loaded.append(report)

    def capture_report_failed(message: str) -> None:
        trace("report_failed", message)
        failed.append(message)

    report_view.reportLoaded.connect(capture_report_loaded)
    report_view.reportFailed.connect(capture_report_failed)

    import ui_qt.workers.task_worker as worker_module

    original_worker_type = worker_module.TaskWorker

    class TracedTaskWorker(original_worker_type):
        def __init__(self, task_function: Any, *args: Any, **kwargs: Any) -> None:
            super().__init__(task_function, *args, **kwargs)
            task_name = getattr(task_function, "__name__", type(task_function).__name__)
            if task_name in {"read_personal_h20_product_for_stock", "read_personal_h20_product_for_stock_with_session"}:
                trace("worker_created", task_name)
                self.finished.connect(lambda result: trace(
                    "worker_result_signal", str(getattr(result, "status", "unknown"))
                ))
                self.error.connect(lambda message: trace("worker_error_signal", message))
                self.native_thread_finished.connect(
                    lambda: trace("native_thread_finished", task_name)
                )

        def start(self, *args: Any, **kwargs: Any) -> None:
            task_name = getattr(self.task_function, "__name__", type(self.task_function).__name__)
            if task_name in {"read_personal_h20_product_for_stock", "read_personal_h20_product_for_stock_with_session"}:
                trace("worker_start", task_name)
            super().start(*args, **kwargs)

    monkeypatch.setattr(worker_module, "TaskWorker", TracedTaskWorker)

    origin_check = window._personal_h20_saved_origin_for_context

    @wraps(origin_check)
    def trace_origin_check(context: object) -> Any:
        trace("pin_check_enter", str(getattr(context, "stock_code", "")))
        result = origin_check(context)
        trace("pin_check_return", "matched" if result is not None else "mismatch")
        return result

    monkeypatch.setattr(window, "_personal_h20_saved_origin_for_context", trace_origin_check)

    workspace = window.stock_research_workspace
    saved_summary = workspace.personal_h20_saved_summary
    original_summary_set_text = saved_summary.setText

    def trace_summary_set_text(value: str) -> None:
        trace("summary_setText_enter", value)
        try:
            original_summary_set_text(value)
        finally:
            trace("summary_setText_return", value)

    monkeypatch.setattr(saved_summary, "setText", trace_summary_set_text)

    original_workspace_set_evidence = workspace.set_personal_h20_saved_evidence

    def trace_workspace_set_evidence(
        evidence: object, *, context: object = None, retry_allowed: bool = True
    ) -> None:
        trace("publish_enter", str(getattr(evidence, "status", "invalid")))
        try:
            original_workspace_set_evidence(
                evidence, context=context, retry_allowed=retry_allowed
            )
        finally:
            trace("publish_return", str(getattr(evidence, "status", "invalid")))

    monkeypatch.setattr(workspace, "set_personal_h20_saved_evidence", trace_workspace_set_evidence)
    return trace


class _MainWindowJourneyHarness(QMainWindow):
    """在最小隔離 host 中呼叫 MainWindow 實際方法，不替換使用者路徑。"""

    def __init__(self, market_root: Path, service: StockResearchReportReadService) -> None:
        super().__init__()
        for name in (
            "_clear_personal_h20_product",
            "_handle_personal_h20_context_changed",
            "_personal_h20_saved_origin_for_context",
            "_personal_h20_saved_feature_date",
            "_start_personal_h20_saved_product_read",
            "_recheck_personal_h20_saved_evidence",
            "_load_personal_h20_product",
            "_mount_personal_h20_research",
            "_open_stock_research_context",
            "_personal_h20_configuration",
            "_refresh_personal_h20_cohort",
            "_request_personal_h20_research",
            "_coerce_stock_research_context",
            "_stock_codes_for_research_context",
        ):
            setattr(self, name, MethodType(getattr(MainWindow, name), self))
        self.config = SimpleNamespace(data_root=market_root)
        self.stock_research_report_service = service
        self._shutdown_close_requested = False
        self._personal_h20_generation = 0
        self.research_session_store = None

        self.stack = QStackedWidget(self)
        self.recommendation_view = QWidget(self.stack)
        recommendation_layout = QVBoxLayout(self.recommendation_view)
        self.recommendation_view.result_source_tabs = QTabWidget(self.recommendation_view)
        self.recommendation_view.result_source_tabs.addTab(QWidget(), "其他推薦來源")
        recommendation_layout.addWidget(self.recommendation_view.result_source_tabs)
        self.stack.addWidget(self.recommendation_view)
        self.stock_research_workspace = StockResearchWorkspace(service, parent=self.stack)
        self.stack.addWidget(self.stock_research_workspace)
        self.setCentralWidget(self.stack)
        self._selected_workspace = "recommendation"
        self._select_main_workspace = self._select_workspace

        report_view = self.stock_research_workspace.report_view
        report_view.activeContextChanged.connect(self._handle_personal_h20_context_changed)
        report_view.reportLoaded.connect(self._load_personal_h20_product)
        self.stock_research_workspace.personalH20SavedRecheckRequested.connect(
            self._recheck_personal_h20_saved_evidence
        )
        self._mount_personal_h20_research(self.recommendation_view)

    def _select_workspace(self, name: str) -> None:
        self._selected_workspace = name
        if name == "stock_research":
            self.stack.setCurrentWidget(self.stock_research_workspace)
        else:
            self.stack.setCurrentWidget(self.recommendation_view)


def test_changed_saved_h20_reference_preserves_original_cohort_and_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下鑽或返回時若保存 pointer 已改變，保留原列表與選取。"""

    from app_module.recommendation.personal_h20_research_cohort import (
        PersonalH20ResearchCohort,
        PersonalH20ResearchRow,
        PersonalH20ResearchSelection,
    )
    import ui_qt.workers.task_worker as worker_module

    def row(symbol: str, gross_return_bp: int) -> PersonalH20ResearchRow:
        return PersonalH20ResearchRow(
            symbol=symbol,
            status="available",
            reason="",
            gross_return_bp=gross_return_bp,
            decision_date=DECISION_DATE,
            source_date=SOURCE_DATE,
            feature_as_of_date=FEATURE_DATE,
            sample_id=f"sample-{symbol}",
            prediction_id=f"prediction-{symbol}",
            capture_path=str(tmp_path / f"capture-{symbol}.json"),
            capture_sha256="sha256:" + ("a" if symbol == "2382" else "b") * 64,
        )

    def cohort(
        manifest_hash: str,
        symbols_and_returns: tuple[tuple[str, int], ...],
    ) -> PersonalH20ResearchCohort:
        rows = tuple(row(symbol, gross_return_bp) for symbol, gross_return_bp in symbols_and_returns)
        symbols = tuple(sorted(item.symbol for item in rows))
        return PersonalH20ResearchCohort(
            manifest_path=str(tmp_path / "manifest.json"),
            manifest_sha256=manifest_hash,
            candidate_id="saved-candidate",
            contract_hash="sha256:" + "c" * 64,
            cycle_id="saved-cycle",
            decision_date=DECISION_DATE,
            symbols=symbols,
            rows=rows,
        )

    class Signal:
        def __init__(self) -> None:
            self.callbacks: list[Any] = []

        def connect(self, callback: Any) -> None:
            self.callbacks.append(callback)

        def emit(self, *args: Any) -> None:
            for callback in tuple(self.callbacks):
                callback(*args)

    class CapturedWorker:
        latest: "CapturedWorker | None" = None

        def __init__(self, _function: Any, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self.finished = Signal()
            self.error = Signal()
            self.progress = Signal()
            self.native_thread_finished = Signal()
            type(self).latest = self

        def start(self) -> None:
            return None

        def isRunning(self) -> bool:
            return False

        def cancel(self, **_kwargs: Any) -> None:
            return None

        def deleteLater(self) -> None:
            return None

    monkeypatch.setattr(worker_module, "TaskWorker", CapturedWorker)
    app = _app()
    old_cohort = cohort("sha256:" + "1" * 64, (("2330", 500), ("2382", 1234)))
    selected_row = next(item for item in old_cohort.rows if item.symbol == "2382")
    selection = PersonalH20ResearchSelection(
        manifest_sha256=old_cohort.manifest_sha256,
        candidate_id=old_cohort.candidate_id,
        contract_hash=old_cohort.contract_hash,
        cycle_id=old_cohort.cycle_id,
        symbol=selected_row.symbol,
        sample_id=selected_row.sample_id,
        prediction_id=selected_row.prediction_id,
        capture_sha256=selected_row.capture_sha256,
    )
    old_reference = object()
    changed_reference = object()
    changed_cohort = cohort("sha256:" + "2" * 64, (("2454", 900),))
    window = _MainWindowJourneyHarness(
        tmp_path,
        _real_report_service(tmp_path / "unused-report.sqlite", tmp_path / "report-output"),
    )
    widget = window.personal_h20_research_widget
    window._personal_h20_cohort_reference = old_reference
    window._personal_h20_research_origin = (object(), selection, old_reference)
    widget.set_cohort(old_cohort)
    assert widget.restore_selection(selection)
    before_symbols = tuple(widget.table.item(index, 0).text() for index in range(widget.table.rowCount()))
    before_current_row = widget.table.currentRow()
    before_selected_rows = tuple(index.row() for index in widget.table.selectionModel().selectedRows())

    try:
        window._refresh_personal_h20_cohort(selection, open_research=True)
        worker = CapturedWorker.latest
        assert worker is not None
        worker.finished.emit((changed_reference, changed_cohort))
        worker.native_thread_finished.emit()

        assert widget._cohort is old_cohort
        assert window._personal_h20_cohort_reference is old_reference
        assert tuple(widget.table.item(index, 0).text() for index in range(widget.table.rowCount())) == before_symbols
        assert widget.table.currentRow() == before_current_row
        assert tuple(index.row() for index in widget.table.selectionModel().selectedRows()) == before_selected_rows
        assert widget.research_button.isEnabled()
        assert widget.isEnabled()
        assert "版本已變動" in widget.summary_label.text()
        assert "未以新版本替代" in window.statusBar().currentMessage()
    finally:
        window.close()
        app.processEvents()


def _real_report_service(database: Path, output_root: Path, *, fail_clock: bool = False) -> StockResearchReportReadService:
    def clock() -> datetime:
        if fail_clock:
            raise RuntimeError("fixture_report_service_clock_failure")
        return datetime.fromisoformat(DECISION_DATE + "T15:00:00+08:00")

    return StockResearchReportReadService(
        SimpleNamespace(db_file=database, output_root=output_root),
        clock=clock,
    )


def _start_real_user_route(window: _MainWindowJourneyHarness) -> None:
    tabs = window.recommendation_view.result_source_tabs
    tabs.setCurrentIndex(0)
    tabs.setCurrentWidget(window.personal_h20_research_panel)
    widget = window.personal_h20_research_widget
    try:
        _wait_until(
            lambda: getattr(window, "_personal_h20_cohort_worker", None) is None
            and (
                widget._cohort is not None
                or widget.summary_label.text().startswith("模型名單待核驗／目前不可用：")
            ),
            timeout_ms=90_000,
        )
    except AssertionError as exc:
        worker = getattr(window, "_personal_h20_cohort_worker", None)
        running = worker.isRunning() if worker is not None else None
        raise AssertionError(
            f"{exc}; cohort={widget._cohort!r}; worker_running={running}; "
            f"summary={widget.summary_label.text()!r}; "
            f"current_tab={tabs.currentIndex()}"
        ) from exc
    assert widget._cohort is not None, widget.summary_label.text()
    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "2382"
    widget.table.selectRow(0)
    assert widget.research_button.isEnabled(), (
        f"row={widget._cohort.rows[0]!r}; cohort={widget._cohort!r}; "
        f"summary={widget.summary_label.text()!r}; current_row={widget.table.currentRow()}; "
        f"selected_rows={[item.row() for item in widget.table.selectedItems()]!r}; "
        f"origin={getattr(window, '_personal_h20_research_origin', None)!r}"
    )
    widget.research_button.click()


def _close_harness(window: _MainWindowJourneyHarness) -> None:
    window._shutdown_close_requested = True
    window.stock_research_workspace.request_close()
    worker = getattr(window, "_personal_h20_worker", None)
    if worker is not None:
        try:
            if worker.isRunning():
                worker.cancel(wait=False)
        except RuntimeError:
            pass
        _wait_until(
            lambda: getattr(window, "_personal_h20_worker", None) is None,
            timeout_ms=30_000,
        )
    window.close()
    _app().processEvents()


def test_h20_saved_source_2382_drilldown_reportloaded_worker_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    service = _real_report_service(
        saved["snapshot_database"],
        tmp_path / "isolated-report-output",
    )
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    report_view = window.stock_research_workspace.report_view
    loaded: list[Any] = []
    failed: list[str] = []
    trace = _trace_saved_h20_route(
        window, report_view, app, tmp_path, monkeypatch, loaded, failed
    )

    import app_module.recommendation.personal_h20_product_evidence as product_module

    product_reader_calls: list[str] = []
    call_lock = threading.Lock()
    original_product_reader = product_module.read_personal_h20_product_for_stock

    @wraps(original_product_reader)
    def observe_product_reader(*args: Any, **kwargs: Any) -> Any:
        trace("reader_enter", str(kwargs["stock_code"]))
        with call_lock:
            product_reader_calls.append(str(kwargs["stock_code"]))
        try:
            result = original_product_reader(*args, **kwargs)
        except BaseException as exc:
            trace("reader_error", f"{type(exc).__name__}: {exc}")
            raise
        trace("reader_return", str(getattr(result, "status", "unknown")))
        return result

    monkeypatch.setattr(product_module, "read_personal_h20_product_for_stock", observe_product_reader)
    window.show()
    app.processEvents()
    try:
        _start_real_user_route(window)
        _wait_until(lambda: bool(loaded) or bool(failed), timeout_ms=90_000)
        assert loaded and not failed, failed[-1] if failed else "report_not_loaded"
        _wait_for_saved_h20_read(
            window,
            report_view,
            product_reader_calls,
            lambda: bool(product_reader_calls)
            and report_view._personal_h20_evidence is not None
            and getattr(window, "_personal_h20_worker", None) is None,
            timeout_ms=45_000,
        )

        context = report_view._loaded_request_context
        report = report_view._loaded_report
        evidence = report_view._personal_h20_evidence
        assert report is loaded[-1]
        assert report.stock_code == "2382"
        assert report.as_of == DECISION_DATE
        # 保存來源 context 不把目前 SQLite 價格拼入 H20 報告；下方另驗原保存 H20 證據。
        assert context is not None
        assert context.stock_code == "2382"
        assert context.source_kind == "personal_h20_saved_cohort"
        assert (context.decision_date, context.data_date) == (DECISION_DATE, SOURCE_DATE)
        assert evidence is not None
        assert evidence.status == "available", (
            f"{evidence!r}; label={report_view.personal_h20_label.text()!r}"
        )
        assert (evidence.decision_date, evidence.source_date, evidence.feature_date) == (
            DECISION_DATE,
            SOURCE_DATE,
            FEATURE_DATE,
        )
        assert evidence.gross_return_bp == 1234
        assert product_reader_calls == ["2382"]
        assert not failed
        assert context.data_date == evidence.source_date
        conclusion = report_view.summary_focus.conclusion_label
        assert conclusion.isVisible()
        assert "+12.34%" in conclusion.text()
        assert "保存的預測值，不代表實際結果" in conclusion.text()
        assert report_view.summary_focus.risk_label.isVisible()
        assert "未扣成本" in report_view.summary_focus.risk_label.text()
        visible_h20_text = report_view.personal_h20_label.text()
        assert "未扣成本的20交易日預測" in visible_h20_text
        assert "預測日 2026-10-06｜來源日 2026-10-05｜特徵截至 2026-10-02" in visible_h20_text
        assert "自然結果待核驗" in visible_h20_text
        visible_limitations = report_view._find_widget("stockResearchLimitations")
        assert visible_limitations.isVisible()
        assert "20 個交易日、未扣成本" in visible_limitations.text()
        assert "自然結果：預測可讀不代表結果已成熟" in visible_limitations.text()
        assert report_view.summary_focus.isVisible()
        assert window._selected_workspace == "stock_research"
        saved_panel = window.stock_research_workspace.personal_h20_saved_group
        saved_summary = window.stock_research_workspace.personal_h20_saved_summary
        assert saved_panel.isVisible()
        assert "2382｜保存的個人 H20 研究預測（未扣成本）：+12.34%" in saved_summary.text()
        assert "預測日 2026-10-06｜來源日 2026-10-05｜特徵截至 2026-10-02" in saved_summary.text()
        assert "實際結果：目前尚無已核驗結果；預測不等於實際報酬。" in saved_summary.text()
        assert "candidate" not in saved_summary.text().lower()
        assert "1234 bp" not in saved_summary.text()
        assert evidence.candidate_id in saved_summary.toolTip()
    finally:
        _close_harness(window)


def test_report_service_failure_keeps_error_and_independently_shows_saved_h20(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    service = _real_report_service(
        saved["snapshot_database"],
        tmp_path / "isolated-report-output",
        fail_clock=True,
    )
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    report_view = window.stock_research_workspace.report_view
    loaded: list[Any] = []
    failed: list[str] = []
    trace = _trace_saved_h20_route(
        window, report_view, app, tmp_path, monkeypatch, loaded, failed
    )

    import app_module.recommendation.personal_h20_product_evidence as product_module

    product_reader_calls: list[str] = []
    original_product_reader = product_module.read_personal_h20_product_for_stock

    @wraps(original_product_reader)
    def observe_product_reader(*args: Any, **kwargs: Any) -> Any:
        trace("reader_enter", str(kwargs["stock_code"]))
        product_reader_calls.append(str(kwargs["stock_code"]))
        try:
            result = original_product_reader(*args, **kwargs)
        except BaseException as exc:
            trace("reader_error", f"{type(exc).__name__}: {exc}")
            raise
        trace("reader_return", str(getattr(result, "status", "unknown")))
        return result

    monkeypatch.setattr(product_module, "read_personal_h20_product_for_stock", observe_product_reader)
    window.show()
    app.processEvents()
    try:
        _start_real_user_route(window)
        _wait_until(lambda: bool(failed), timeout_ms=90_000)

        assert not loaded
        assert "fixture_report_service_clock_failure" in failed[-1]
        _wait_for_saved_h20_read(
            window,
            report_view,
            product_reader_calls,
            lambda: bool(product_reader_calls)
            and window.stock_research_workspace.personal_h20_saved_evidence is not None
            and getattr(window, "_personal_h20_worker", None) is None,
            timeout_ms=45_000,
        )
        assert product_reader_calls == ["2382"]
        assert report_view.status_label.text().startswith("報告讀取失敗：")
        assert "fixture_report_service_clock_failure" in report_view.status_label.text()
        assert report_view.summary_focus.conclusion_label.text() == "結論：目前沒有可閱讀的個股報告。"
        assert "fixture_report_service_clock_failure" in report_view.summary_focus.reasons_label.text()
        assert "目前無法核驗本股" in report_view.personal_h20_label.text()
        assert "fixture_report_service_clock_failure" in report_view.summary_limitations_detail_label.text()
        saved_panel = window.stock_research_workspace.personal_h20_saved_group
        saved_summary = window.stock_research_workspace.personal_h20_saved_summary
        assert saved_panel.isVisible()
        assert "2382｜保存的個人 H20 研究預測（未扣成本）：+12.34%" in saved_summary.text(), (
            f"saved_evidence={window.stock_research_workspace.personal_h20_saved_evidence!r}; "
            f"raw_tooltip={saved_summary.toolTip()!r}; summary={saved_summary.text()!r}"
        )
        assert "預測日 2026-10-06｜來源日 2026-10-05｜特徵截至 2026-10-02" in saved_summary.text()
        assert "實際結果：目前尚無已核驗結果；預測不等於實際報酬。" in saved_summary.text()
        assert "fixture_report_service_clock_failure" not in saved_summary.text()
    finally:
        _close_harness(window)


def test_saved_h20_worker_result_is_cancelled_and_stale_after_source_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    service = _real_report_service(
        saved["snapshot_database"],
        tmp_path / "isolated-report-output",
        fail_clock=True,
    )
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    report_view = window.stock_research_workspace.report_view

    import app_module.recommendation.personal_h20_product_evidence as product_module

    entered = threading.Event()
    release = threading.Event()
    original_product_reader = product_module.read_personal_h20_product_for_stock
    calls: list[str] = []

    @wraps(original_product_reader)
    def blocking_product_reader(*args: Any, **kwargs: Any) -> Any:
        calls.append(str(kwargs["stock_code"]))
        entered.set()
        if not release.wait(30):
            raise RuntimeError("test_reader_release_timeout")
        return original_product_reader(*args, **kwargs)

    monkeypatch.setattr(product_module, "read_personal_h20_product_for_stock", blocking_product_reader)
    window.show()
    app.processEvents()
    try:
        _start_real_user_route(window)
        _wait_until(entered.is_set, timeout_ms=90_000)
        assert window.stock_research_workspace.personal_h20_saved_group.isVisible()
        loading_text = window.stock_research_workspace.personal_h20_saved_summary.text()
        assert "2382｜正在核驗原保存的 H20 預測" in loading_text
        assert "預測日 2026-10-06｜來源日 2026-10-05｜特徵截至 2026-10-02" in loading_text
        assert "保存的個人 H20 研究預測（未扣成本）：" not in loading_text
        assert window.stock_research_workspace.is_busy()

        old_context = report_view.context
        assert old_context is not None
        new_context = replace(
            old_context,
            source_kind="explicit_latest_stock_research",
            source_workspace="stock_research",
            source_label="明確另開研究",
        )
        report_view.context = new_context
        report_view.activeContextChanged.emit(new_context)
        assert not window.stock_research_workspace.personal_h20_saved_group.isVisible()
        assert not window.stock_research_workspace.personal_h20_saved_busy
        assert getattr(window, "_personal_h20_saved_evidence", None) is None
        worker = getattr(window, "_personal_h20_worker", None)
        assert worker is not None and worker.is_cancel_requested()

        release.set()
        _wait_until(lambda: getattr(window, "_personal_h20_worker", None) is None, timeout_ms=30_000)
        app.processEvents()
        assert calls == ["2382"]
        assert not window.stock_research_workspace.personal_h20_saved_group.isVisible()
        assert getattr(window, "_personal_h20_saved_evidence", None) is None
    finally:
        release.set()
        _close_harness(window)




def test_saved_h20_reader_error_requires_explicit_retry_and_reuses_exact_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app()
    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    service = _real_report_service(
        saved["snapshot_database"],
        tmp_path / "isolated-report-output",
        fail_clock=True,
    )
    window = _MainWindowJourneyHarness(saved["market_root"], service)
    report_view = window.stock_research_workspace.report_view

    import app_module.recommendation.personal_h20_product_evidence as product_module

    original_product_reader = product_module.read_personal_h20_product_for_stock
    calls: list[dict[str, Any]] = []

    @wraps(original_product_reader)
    def fail_once_then_read(*args: Any, **kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise RuntimeError("fixture_transient_h20_reader_failure")
        return original_product_reader(*args, **kwargs)

    monkeypatch.setattr(product_module, "read_personal_h20_product_for_stock", fail_once_then_read)
    window.show()
    app.processEvents()
    try:
        _start_real_user_route(window)
        _wait_until(
            lambda: len(calls) == 1
            and window.stock_research_workspace.personal_h20_saved_evidence is not None
            and getattr(window, "_personal_h20_worker", None) is None,
            timeout_ms=90_000,
        )
        assert report_view.status_label.text().startswith("報告讀取失敗：")
        assert "fixture_report_service_clock_failure" in report_view.status_label.text()
        panel = window.stock_research_workspace
        assert panel.personal_h20_saved_evidence.status == "unavailable"
        assert "保存來源讀取失敗" in panel.personal_h20_saved_summary.text()
        assert "fixture_transient_h20_reader_failure" in panel.personal_h20_saved_summary.toolTip()
        assert panel.personal_h20_saved_recheck_button.isEnabled()
        first_reference = calls[0]["expected_reference"]

        panel.personal_h20_saved_recheck_button.click()
        assert panel.is_busy()
        assert not panel.personal_h20_saved_recheck_button.isEnabled()
        _wait_until(
            lambda: len(calls) == 2
            and panel.personal_h20_saved_evidence is not None
            and panel.personal_h20_saved_evidence.status == "available"
            and getattr(window, "_personal_h20_worker", None) is None,
            timeout_ms=90_000,
        )
        assert calls[1]["expected_reference"] == first_reference
        assert all(call["stock_code"] == "2382" for call in calls)
        assert report_view.status_label.text().startswith("報告讀取失敗：")
        assert "fixture_report_service_clock_failure" in report_view.status_label.text()
        assert "2382｜保存的個人 H20 研究預測（未扣成本）：+12.34%" in panel.personal_h20_saved_summary.text()
        assert panel.personal_h20_saved_recheck_button.isEnabled()
    finally:
        _close_harness(window)
