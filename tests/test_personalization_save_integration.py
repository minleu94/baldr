from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

import pytest

from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_payload_hash,
)
from app_module.personalization_projection import PersonalizationProjectionService
from app_module.personalization_save_adapter import (
    PersonalizationSaveAdapterError,
    PersonalizationRecommendationSaveAdapter,
)
from app_module.recommendation_repository import (
    RecommendationRepository,
    _make_json_serializable,
)
from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationExecution,
    Request,
)
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem


RESULT_ID = "rec_personalization_save_001"
STOCK_CODE = "2330"
SCOPE_ID = "local_research_scope_v1"
DELIVERY_ID = "delivery_personalization_save_001"
PREDICTION_ID = "00000000-0000-0000-0000-000000000010"
DATASET_HASH = "sha256:" + ("d" * 64)
COST_SCENARIO_HASH = "sha256:" + ("b" * 64)
UNIVERSE_POLICY_HASH = "sha256:" + ("e" * 64)
LABEL_CONTRACT_ID = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


class _TempConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path


class _CountingRecommendationRepository(RecommendationRepository):
    def __init__(self, config: _TempConfig) -> None:
        self.save_calls = 0
        self.create_only_calls = 0
        super().__init__(config)

    def save_result(self, result, result_name=None) -> str:  # type: ignore[no-untyped-def]
        self.save_calls += 1
        return super().save_result(result, result_name=result_name)

    def save_result_create_only(self, result, result_name=None) -> str:  # type: ignore[no-untyped-def]
        self.save_calls += 1
        self.create_only_calls += 1
        return super().save_result_create_only(result, result_name=result_name)


class _BarrierRecommendationRepository(_CountingRecommendationRepository):
    def __init__(self, config: _TempConfig) -> None:
        self._initial_load_barrier = Barrier(2)
        self._initial_load_results_barrier = Barrier(2)
        self._load_lock = Lock()
        self._load_calls = 0
        super().__init__(config)

    def load_result(self, result_id: str):
        with self._load_lock:
            self._load_calls += 1
            load_number = self._load_calls
        if load_number <= 2:
            self._initial_load_barrier.wait(timeout=10)
        loaded = super().load_result(result_id)
        if load_number <= 2:
            # Return both initial empty reads before either thread can enter
            # the create-only write.  Without this second rendezvous, the
            # first thread can observe the other thread's newly-created row
            # and the test becomes a scheduler-dependent false negative.
            self._initial_load_results_barrier.wait(timeout=10)
        return loaded


class _PersonalWinsLegacyRaceRepository(_CountingRecommendationRepository):
    """Force the coordinator read/legacy write gap around a personal create."""

    def __init__(self, config: _TempConfig) -> None:
        self.first_load_returned = Event()
        self.release_first_load = Event()
        self.personal_create_finished = Event()
        self._load_lock = Lock()
        self._load_calls = 0
        super().__init__(config)

    def load_result(self, result_id: str):
        with self._load_lock:
            self._load_calls += 1
            load_number = self._load_calls
        loaded = super().load_result(result_id)
        if load_number == 1:
            self.first_load_returned.set()
            if not self.release_first_load.wait(timeout=10):
                raise RuntimeError("mixed-race test barrier timed out")
        return loaded

    def save_result_create_only(self, result, result_name=None):  # type: ignore[no-untyped-def]
        saved_id = super().save_result_create_only(result, result_name=result_name)
        self.personal_create_finished.set()
        self.release_first_load.set()
        return saved_id


class _FailingRepository:
    def load_result(self, result_id: str):
        return None

    def save_result(self, result):  # type: ignore[no-untyped-def]
        raise RuntimeError("repository save failed")


class _FailingAckJournal:
    def list_personalization_delivery_acks(
        self,
        result_id: str,
        stock_code: str,
        delivery_id: str = "",
    ) -> list[Any]:
        return []

    def record_personalization_delivery_acks(
        self,
        acknowledgements,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        raise RuntimeError("journal append failed")


def _receipt() -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-projection-receipt.v1",
        "result_id": RESULT_ID,
        "decision_date": "2025-02-10",
        "candidate_identity": {"candidate_id": "model_001"},
        "model_id": "model_001",
        "dataset_id": "dataset_001",
        "dataset_hash": DATASET_HASH,
        "label_contract_id": LABEL_CONTRACT_ID,
        "return_basis": RETURN_BASIS,
        "universe_policy_hash": UNIVERSE_POLICY_HASH,
        "source_id": "recommendation_service",
        "selection_contract": {
            "authority": "rule_top_n",
            "score_kind": "rule_total_score",
            "percentile_kind": "rule_percentile",
            "model_ranking_kind": "model_return_bp",
            "top_n_changed_by_model": False,
        },
        "projections": [
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_001",
                "dataset_version": "dataset_001",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": COST_SCENARIO_HASH,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT_ID,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_POLICY_HASH,
                "calibrated_probability_bp": 5200,
                "status": "active_candidate",
            }
        ],
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "shadow_only": True,
    }
    return {**body, "receipt_hash": canonical_payload_hash(body)}


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="local",
        delivery_id=DELIVERY_ID,
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
        source="recommendation_service",
    )


def _recommendation() -> RecommendationDTO:
    return RecommendationDTO(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=Decimal("100.00"),
        price_change=1,
        total_score=80,
        indicator_score=80,
        pattern_score=80,
        volume_score=80,
        recommendation_reasons="integration",
        industry="半導體",
        regime_match=True,
    )


def _qt_manual_execution(*, score: Decimal = Decimal("80")) -> RecommendationExecution:
    from ui_qt.views.recommendation.execution_coordinator import (
        RecommendationExecutionRequest,
    )

    request_snapshot = RecommendationExecutionRequest(
        {
            "patterns": {"selected": ["W底"]},
            "signals": {"technical_indicators": ["trend"]},
            "filters": {"mode": "ui-manual"},
        }
    ).config_snapshot
    decision_date = date(2025, 2, 10)
    decision_at = datetime(2025, 2, 10, 9, 0, tzinfo=timezone.utc)
    item = RecommendationItem(
        stock_code=STOCK_CODE,
        stock_name="台積電",
        close_price=Decimal("100.00"),
        price_change=Decimal("1"),
        rule_score=score,
        indicator_score=Decimal("80"),
        pattern_score=Decimal("80"),
        volume_score=Decimal("80"),
        reason_text="Qt manual save integration",
        industry="半導體",
        regime_match=True,
        rank=1,
    )
    return RecommendationExecution(
        result_id=RESULT_ID,
        request=Request(
            as_of_date=decision_date,
            config_snapshot=request_snapshot,
            max_stocks=200,
            top_n=50,
        ),
        context=Context(
            as_of_date=decision_date,
            decision_at=decision_at,
            available_at=decision_at,
            created_at=decision_at,
        ),
        status=ExecutionStatus.COMPLETED,
        decision=DecisionBatch(items=(item,), regime="Trend"),
    )


def _context() -> dict[str, Any]:
    receipt = _receipt()
    scope = _scope()
    return {
        "schema_version": "recommendation-context.v1",
        "result_id": RESULT_ID,
        "as_of_date": "2025-02-10",
        "data_date": "2025-02-10",
        "run_started_at": "2025-02-10T08:49:00+00:00",
        "personalization_scope_declared_at": scope.declared_at,
        "available_at": scope.available_at,
        "captured_at": scope.captured_at,
        "decision_at": scope.decision_at,
        "calibration_projection_receipt_created_at": scope.receipt_created_at,
        "temporal_contract": "recommendation-producer-clock.v1",
        "temporal_mode": "natural_producer_clock",
        "cutoff_selection": "producer_selected_latest_available_cutoff",
        "cutoff_policy": "source_latest_available_exact",
        "decision_clock_timezone": "UTC",
        "market_calendar_timezone": "Asia/Taipei",
        "prediction_decision_anchor": "actual_producer_decision_at",
        "horizon_anchor": "immutable_projection_receipt",
        "calibration_projection_receipt": receipt,
        "calibration_projection_receipt_metadata": {
            "result_id": RESULT_ID,
            "receipt_hash": receipt["receipt_hash"],
            "receipt_created_at": scope.receipt_created_at,
        },
        "calibration_projection_rows": {
            STOCK_CODE: dict(receipt["projections"][0]),
        },
        "personalization_scope": scope.to_dict(),
        "personalization_delivery_scope": scope.to_dict(),
    }


def _request(context: dict[str, Any] | None = None) -> RecommendationResultDTO:
    result = RecommendationResultDTO(
        result_id=RESULT_ID,
        result_name="personalization save integration",
        config={"strategy_config": {"mode": "test"}},
        recommendations=[_recommendation()],
        created_at="2025-02-10T09:02:00+00:00",
        run_context=deepcopy(context or _context()),
    )
    bound, captures = PersonalizationRecommendationSaveAdapter().bind_result(
        result,
        request_id="request_personalization_save_001",
    )
    assert bool(captures) == bool(
        result.run_context.get("personalization_scope")
        or result.run_context.get("personalization_delivery_scope")
    )
    return bound


def _persist(
    request: RecommendationResultDTO,
    repository: Any,
) -> Any:
    adapter = PersonalizationRecommendationSaveAdapter()
    captures = adapter.captures_from_result(request)
    if not captures:
        existing = adapter.load_existing_for_retry(
            repository,
            result_id=request.result_id,
        )
        if existing is not None and adapter.captures_from_result(existing):
            raise RuntimeError("recommendation save would downgrade an existing personal capture")
        result_id = str(repository.save_result(request))
        return SimpleNamespace(
            result_id=result_id,
            personalization_capture_hashes=(),
            personalization_delivery_statuses=(),
            personalization_captures=(),
            personalization_persisted_at=None,
        )
    existing = adapter.load_existing_for_retry(
        repository,
        result_id=request.result_id,
    )
    if existing is None:
        saved = adapter.save_and_readback(
            recommendation_repository=repository,
            result=request,
            captures=captures,
        )
        saved_captures = adapter.captures_from_result(saved)
    else:
        saved, saved_captures = adapter.merge_existing_retry(
            candidate_result=request,
            existing_result=existing,
            candidate_captures=captures,
        )
    persisted_at = "2025-02-10T09:02:00.000000+00:00"
    persisted = tuple(
        adapter.capture_service.mark_persisted(
            capture,
            persisted_at=persisted_at,
        )
        if capture.status == "generated"
        else capture
        for capture in saved_captures
    )
    return SimpleNamespace(
        result_id=saved.result_id,
        personalization_capture_hashes=tuple(item.capture_hash for item in saved_captures),
        personalization_delivery_statuses=tuple(item.status for item in persisted),
        personalization_captures=persisted,
        personalization_scope_id=persisted[0].scope.scope_id if persisted else None,
        personalization_delivery_id=persisted[0].delivery_id if persisted else None,
        personalization_persisted_at=persisted[0].persisted_at if persisted else None,
    )


def _later(value: str, seconds: int = 1) -> str:
    return (
        datetime.fromisoformat(value) + timedelta(seconds=seconds)
    ).astimezone(timezone.utc).isoformat(timespec="microseconds")


def _ack(
    request: RecommendationResultDTO,
    repository: Any,
    journal: Any,
    outcome: Any,
    *,
    scope_id: str = SCOPE_ID,
    delivery_id: str = DELIVERY_ID,
    expected_hash: str | None = None,
    delivered_at: str | None = None,
) -> Any:
    return PersonalizationRecommendationSaveAdapter().acknowledge_delivery(
        recommendation_repository=repository,
        journal_service=journal,
        result_id=request.result_id,
        scope_id=scope_id,
        delivery_id=delivery_id,
        persisted_at=outcome.personalization_persisted_at,
        delivered_at=delivered_at or _later(outcome.personalization_persisted_at),
        recorded_at=delivered_at or _later(outcome.personalization_persisted_at),
        expected_capture_hashes={
            STOCK_CODE: expected_hash
            if expected_hash is not None
            else outcome.personalization_capture_hashes[0]
        },
    )


def test_save_readback_retry_keeps_generated_result_immutable(tmp_path: Path) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    request = _request()

    first = _persist(request, repository)
    result_file = repository.runs_dir / f"{RESULT_ID}.json"
    before_bytes = result_file.read_bytes()
    saved = repository.load_result(RESULT_ID)
    assert saved is not None
    saved_capture = PersonalizationRecommendationSaveAdapter().captures_from_result(saved)[0]

    assert repository.save_calls == 1
    assert first.personalization_delivery_statuses == ("persisted",)
    assert first.personalization_captures[0].status == "persisted"
    assert first.personalization_capture_hashes == (saved_capture.capture_hash,)
    assert saved_capture.status == "generated"
    assert saved.run_context["calibration_projection_receipt"] == _receipt()
    assert saved.recommendations[0].calibration_provenance[
        "personalization_delivery_capture"
    ]["capture_hash"] == saved_capture.capture_hash

    second = _persist(request, repository)

    assert repository.save_calls == 1
    assert second.personalization_capture_hashes == first.personalization_capture_hashes
    assert second.personalization_captures[0].status == "persisted"
    assert result_file.read_bytes() == before_bytes
    assert repository.load_result(RESULT_ID).to_dict() == saved.to_dict()


def test_missing_scope_retry_cannot_downgrade_existing_personal_result(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    first = _persist(_request(), repository)
    result_file = repository.runs_dir / f"{RESULT_ID}.json"
    before_bytes = result_file.read_bytes()

    missing_scope_context = _context()
    missing_scope_context.pop("personalization_scope")
    missing_scope_context.pop("personalization_delivery_scope")
    with pytest.raises(RuntimeError, match="downgrade"):
        _persist(_request(missing_scope_context), repository)

    assert first.result_id == RESULT_ID
    assert repository.save_calls == 1
    assert repository.create_only_calls == 1
    assert result_file.read_bytes() == before_bytes
    saved = repository.load_result(RESULT_ID)
    assert saved is not None
    saved_capture = PersonalizationRecommendationSaveAdapter().captures_from_result(saved)[0]
    assert saved_capture.status == "generated"


def test_legacy_save_preserves_orphan_and_create_only_recovers_identical_bytes(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    result = _request()
    result_file = repository.runs_dir / f"{RESULT_ID}.json"
    serialized = json.dumps(
        _make_json_serializable(result.to_dict()),
        ensure_ascii=False,
        indent=2,
    )
    result_file.write_text(serialized, encoding="utf-8")
    before_bytes = result_file.read_bytes()

    legacy_result = _request()
    with pytest.raises(RuntimeError, match="without metadata"):
        repository.save_result(legacy_result)
    assert result_file.read_bytes() == before_bytes
    assert repository.load_result(RESULT_ID) is None

    assert repository.save_result_create_only(result) == RESULT_ID
    assert result_file.read_bytes() == before_bytes
    assert repository.load_result(RESULT_ID) is not None


def test_legacy_save_refuses_unknown_existing_bytes_and_preserves_them(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    result = _request()
    result.run_context.pop("personalization_delivery_captures", None)
    repository.save_result(result)
    result_file = repository.runs_dir / f"{RESULT_ID}.json"
    corrupt_bytes = b"{not-json"
    result_file.write_bytes(corrupt_bytes)

    with pytest.raises(RuntimeError, match="cannot classify"):
        repository.save_result(result)
    assert result_file.read_bytes() == corrupt_bytes


def test_concurrent_personal_create_only_save_never_replaces_first_result(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _BarrierRecommendationRepository(config)
    requests = (_request(), _request())

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda item: _persist(item, repository),
                requests,
            )
        )

    assert [outcome.result_id for outcome in outcomes] == [RESULT_ID, RESULT_ID]
    assert all(
        outcome.personalization_delivery_statuses == ("persisted",)
        for outcome in outcomes
    )
    assert repository.create_only_calls == 2
    saved = repository.load_result(RESULT_ID)
    assert saved is not None
    saved_capture = PersonalizationRecommendationSaveAdapter().captures_from_result(saved)[0]
    assert saved_capture.status == "generated"
    assert repository.load_result(RESULT_ID).to_dict() == saved.to_dict()


def test_personal_create_cannot_be_overwritten_by_racing_legacy_save(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _PersonalWinsLegacyRaceRepository(config)
    missing_scope_context = _context()
    missing_scope_context.pop("personalization_scope")
    missing_scope_context.pop("personalization_delivery_scope")

    with ThreadPoolExecutor(max_workers=2) as executor:
        legacy_future = executor.submit(_persist, _request(missing_scope_context), repository)
        assert repository.first_load_returned.wait(timeout=10)
        personal_future = executor.submit(_persist, _request(), repository)
        personal_outcome = personal_future.result(timeout=10)
        assert repository.personal_create_finished.is_set()
        with pytest.raises(RuntimeError, match="immutable personal capture"):
            legacy_future.result(timeout=10)

    assert personal_outcome.personalization_capture_hashes
    result_file = repository.runs_dir / f"{RESULT_ID}.json"
    saved = repository.load_result(RESULT_ID)
    assert saved is not None
    saved_capture = PersonalizationRecommendationSaveAdapter().captures_from_result(saved)[0]
    assert saved_capture.status == "generated"
    assert saved_capture.capture_hash == personal_outcome.personalization_capture_hashes[0]
    assert saved_capture.capture_hash in result_file.read_text(encoding="utf-8")


def test_qt_manual_save_without_personal_scope_does_not_ack(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    from app_module.recommendation.composition import build_recommendation_composition
    from ui_qt.views import recommendation_view as module

    config = _TempConfig(tmp_path / "output")
    journal = JournalService(config)  # type: ignore[arg-type]
    composition = build_recommendation_composition(config)
    execution = _qt_manual_execution()
    messages: list[str] = []
    monkeypatch.setattr(
        module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("UI integration save", True),
    )
    monkeypatch.setattr(
        module.QMessageBox,
        "information",
        lambda *args: messages.append(str(args[-1])),
    )
    monkeypatch.setattr(
        module.QMessageBox,
        "critical",
        lambda *args: pytest.fail(str(args[-1])),
    )
    monkeypatch.setattr(module, "PandasTableModel", lambda _frame: object())

    class _Table:
        def setModel(self, _model):  # type: ignore[no-untyped-def]
            return None

        def selectionModel(self):  # type: ignore[no-untyped-def]
            return None

    view = SimpleNamespace(
        current_execution=execution,
        current_result_id="",
        current_read_model=None,
        current_save_receipt=None,
        _pending_save_receipt=None,
        _pending_save_metadata=None,
        _verified_saved_result_id=lambda: "",
        _get_recommendation_composition=lambda: composition,
        _selected_stock_code=lambda: "",
        _current_table_rows=lambda: [],
        _update_detail_text=lambda: None,
        current_config={"filters": {"mode": "ui-manual"}},
        current_profile=None,
        current_regime=None,
        profiles={},
        universe_service=None,
        results_table=_Table(),
        journal_service=journal,
    )

    module.RecommendationView._save_recommendation_result(view)

    loaded = composition.queries.get(RESULT_ID)
    assert loaded is not None and loaded.execution == execution
    assert PersonalizationRecommendationSaveAdapter().captures_from_execution(execution) == ()
    assert journal.list_personalization_delivery_acks(RESULT_ID, STOCK_CODE, DELIVERY_ID) == []
    assert messages and "推薦結果已保存" in messages[0]
    assert composition.store.read_artifact(RESULT_ID) is not None


def test_main_window_host_integration_manual_save_does_not_ack(
    tmp_path: Path, monkeypatch
) -> None:
    """Host-level integration guard; the full process probe is separate."""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMainWindow

    import ui_qt.main as main_module
    from ui_qt.views import recommendation_view as view_module
    from ui_qt.workers.task_worker import running_task_workers

    application = QApplication.instance() or QApplication([])
    config = _TempConfig(tmp_path / "output")
    journal = JournalService(config)  # type: ignore[arg-type]
    execution = _qt_manual_execution()

    class _EmptyProfileService:
        def list_profiles(self):  # type: ignore[no-untyped-def]
            return []

    main_window = main_module.MainWindow.__new__(main_module.MainWindow)
    QMainWindow.__init__(main_window)
    main_window.journal_service = journal
    monkeypatch.setattr(
        view_module.RecommendationView,
        "_load_current_regime",
        lambda self: None,
    )
    view = view_module.RecommendationView(
        recommendation_service=SimpleNamespace(),
        regime_service=SimpleNamespace(),
        watchlist_service=None,
        config=config,  # type: ignore[arg-type]
        universe_service=SimpleNamespace(save_watchlist=lambda **kwargs: None),
        profile_service=_EmptyProfileService(),  # type: ignore[arg-type]
        journal_service=main_window.journal_service,
        parent=main_window,
    )
    main_window.recommendation_view = view
    assert main_window.recommendation_view.journal_service is main_window.journal_service

    messages: list[str] = []
    monkeypatch.setattr(
        view_module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("MainWindow integration save", True),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "information",
        lambda *args: messages.append(str(args[-1])),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "critical",
        lambda *args: pytest.fail(str(args[-1])),
    )
    view.current_execution = execution
    view.current_config = view._execution_config(execution)
    view.current_result_id = ""
    view._save_recommendation_result()

    loaded = view.current_read_model
    assert loaded is not None and loaded.execution == execution
    history = main_window.journal_service.list_personalization_delivery_acks(
        RESULT_ID, STOCK_CODE, DELIVERY_ID
    )
    assert history == []
    assert messages and "推薦結果已保存" in messages[0]
    assert PersonalizationRecommendationSaveAdapter().captures_from_execution(execution) == ()
    composition = view._get_recommendation_composition()
    artifact_bytes = composition.store.read_artifact(RESULT_ID)
    assert artifact_bytes is not None
    assert composition.queries.get(RESULT_ID) == loaded
    assert main_window.journal_service.list_journal_history() == []
    main_window.close()
    application.processEvents()
    assert running_task_workers() == ()


def test_qt_watchlist_failure_is_soft_after_canonical_save(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A legacy watchlist failure must not undo canonical save/readback."""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMainWindow

    import ui_qt.main as main_module
    from app_module.recommendation.composition import build_recommendation_composition
    from ui_qt.views import recommendation_view as view_module
    from ui_qt.workers.task_worker import running_task_workers

    application = QApplication.instance() or QApplication([])
    config = _TempConfig(tmp_path / "output")
    journal = JournalService(config)  # type: ignore[arg-type]
    execution = _qt_manual_execution()

    class _EmptyProfileService:
        def list_profiles(self):  # type: ignore[no-untyped-def]
            return []

    composition = build_recommendation_composition(config)
    artifact_observed_by_watchlist: list[bytes | None] = []

    def fail_watchlist(**_kwargs: Any) -> None:
        artifact_observed_by_watchlist.append(
            composition.store.read_artifact(execution.result_id)
        )
        raise RuntimeError("injected watchlist failure")

    main_window = main_module.MainWindow.__new__(main_module.MainWindow)
    QMainWindow.__init__(main_window)
    main_window.journal_service = journal
    monkeypatch.setattr(
        view_module.RecommendationView,
        "_load_current_regime",
        lambda self: None,
    )
    view = view_module.RecommendationView(
        recommendation_service=SimpleNamespace(),
        regime_service=SimpleNamespace(),
        watchlist_service=None,
        config=config,  # type: ignore[arg-type]
        universe_service=SimpleNamespace(save_watchlist=fail_watchlist),
        profile_service=_EmptyProfileService(),  # type: ignore[arg-type]
        journal_service=main_window.journal_service,
        parent=main_window,
    )
    main_window.recommendation_view = view
    view.recommendation_composition = composition

    messages: list[str] = []
    monkeypatch.setattr(
        view_module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Canonical watchlist failure", True),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "information",
        lambda *args: messages.append(str(args[-1])),
    )
    monkeypatch.setattr(
        view_module.QMessageBox,
        "critical",
        lambda *args: pytest.fail(str(args[-1])),
    )
    view.current_execution = execution
    view.current_config = view._execution_config(execution)
    view.current_result_id = ""
    view._save_recommendation_result()

    saved_bytes = composition.store.read_artifact(execution.result_id)
    loaded = composition.queries.get(execution.result_id)
    assert saved_bytes is not None
    assert artifact_observed_by_watchlist == [saved_bytes]
    assert loaded is not None and loaded.execution == execution
    assert composition.store.read_artifact(execution.result_id) == saved_bytes
    assert view.current_result_id == execution.result_id
    assert journal.list_personalization_delivery_acks(
        execution.result_id,
        STOCK_CODE,
        DELIVERY_ID,
    ) == []
    assert messages and "已保存" in messages[0]
    assert "自動選股清單未建立：injected watchlist failure" in messages[0]
    assert running_task_workers() == ()
    main_window.close()
    application.processEvents()


def test_real_main_window_process_save_readback_probe(tmp_path: Path) -> None:
    """Run the production MainWindow constructor in a separate process."""

    root = Path(__file__).resolve().parents[1]
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    receipt_path = tmp_path / "personalization_mainwindow_save_readback.json"
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONIOENCODING": "utf-8",
            "DATA_ROOT": str(data_root),
            "OUTPUT_ROOT": str(output_root),
            "PROFILE": "prod",
            "FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE": str(
                output_root / ".missing-formal-runtime-binding.json"
            ),
        }
    )
    for name in (
        "FORMAL_DAILY_RUNTIME_CONFIG",
        "FORMAL_DAILY_RUNTIME_CONFIG_ROOT",
        "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE",
        "FORMAL_DAILY_PORTFOLIO_CLOCK_MANIFEST",
    ):
        environment.pop(name, None)

    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "qa_personalization_mainwindow_save_readback.py"),
            "--data-root",
            str(data_root),
            "--output-root",
            str(output_root),
            "--receipt",
            str(receipt_path),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=False,
        check=False,
        timeout=45,
    )
    if completed.returncode != 0:
        diagnostics = (completed.stderr or b"").decode("utf-8", errors="replace")
        stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
        raise AssertionError(
            f"real MainWindow save/readback probe failed\nstdout:\n{stdout}\nstderr:\n{diagnostics}"
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["process_id"] > 0
    assert payload["data_root"] == str(data_root.resolve())
    assert payload["output_root"] == str(output_root.resolve())
    assert payload["main_window_constructed"] is True
    assert payload["real_recommendation_view"] is True
    assert payload["window_journal_owned"] is True
    assert payload["view_journal_is_window_journal"] is True
    assert payload["real_canonical_composition"] is True
    assert payload["fixture_execution_bound"] is True
    assert payload["normal_save_entry_clicked"] is True
    assert payload["result_readback"] is True
    assert payload["personal_scope_present"] is False
    assert payload["personal_ack_count"] == 0
    assert payload["no_personal_ack_readback"] is True
    assert payload["exact_query_readback"] is True
    assert payload["result_artifact_unchanged_after_query"] is True
    assert payload["close_requests"] == 1
    assert payload["watchdog_fired"] is False
    assert payload["window_hidden_after_exec"] is True
    assert payload["remaining_workers_after_exec"] == 0
    assert payload["app_exec_returncode"] == 0
    assert payload["process_exit_code"] == 0
    assert "error" not in payload, payload.get("error")


def test_qt_save_writer_failure_preserves_artifact_and_does_not_ack(
    tmp_path: Path, monkeypatch
) -> None:
    import pandas as pd

    from app_module.recommendation.composition import build_recommendation_composition
    from ui_qt.views import recommendation_view as module

    config = _TempConfig(tmp_path / "output")
    journal = JournalService(config)  # type: ignore[arg-type]
    composition = build_recommendation_composition(config)
    baseline = _qt_manual_execution()
    composition.save_service.save_execution(baseline, label="original", notes="original")
    before_bytes = composition.store.read_artifact(RESULT_ID)
    assert before_bytes is not None
    attempted = _qt_manual_execution(score=Decimal("81"))
    messages: list[str] = []
    monkeypatch.setattr(
        module.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("UI failed save", True),
    )
    monkeypatch.setattr(
        module.QMessageBox,
        "critical",
        lambda *args: messages.append(str(args[-1])),
    )
    monkeypatch.setattr(module, "PandasTableModel", lambda _frame: object())

    class _FailingSave:
        def save_execution(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("canonical writer rejected changed hash")

    class _Table:
        def setModel(self, _model):  # type: ignore[no-untyped-def]
            return None

        def selectionModel(self):  # type: ignore[no-untyped-def]
            return None

    view = SimpleNamespace(
        current_execution=attempted,
        current_result_id="",
        current_read_model=None,
        current_save_receipt=None,
        _pending_save_receipt=None,
        _pending_save_metadata=None,
        _verified_saved_result_id=lambda: "",
        _get_recommendation_composition=lambda: SimpleNamespace(
            save_service=_FailingSave(),
            queries=composition.queries,
        ),
        _selected_stock_code=lambda: "",
        _current_table_rows=lambda: [],
        _update_detail_text=lambda: None,
        current_config={"filters": {"mode": "ui-manual"}},
        current_profile=None,
        current_regime=None,
        profiles={},
        universe_service=None,
        results_table=_Table(),
        journal_service=journal,
    )

    module.RecommendationView._save_recommendation_result(view)

    assert composition.store.read_artifact(RESULT_ID) == before_bytes
    assert journal.list_personalization_delivery_acks(RESULT_ID, STOCK_CODE, DELIVERY_ID) == []
    assert len(messages) == 1
    assert "保存或 verified readback 失敗" in messages[0]


def test_ack_retry_scope_cas_and_writer_failure_do_not_mutate_result(tmp_path: Path) -> None:
    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    journal = JournalService(config)  # type: ignore[arg-type]
    request = _request()
    outcome = _persist(request, repository)
    before_bytes = (repository.runs_dir / f"{RESULT_ID}.json").read_bytes()
    before_result = repository.load_result(RESULT_ID)
    assert before_result is not None

    with pytest.raises(PersonalizationSaveAdapterError, match="capture hash"):
        _ack(
            request,
            repository,
            journal,
            outcome,
            expected_hash="sha256:" + ("f" * 64),
        )
    assert journal.list_journal_history() == []

    with pytest.raises(PersonalizationSaveAdapterError, match="scope identity"):
        _ack(request, repository, journal, outcome, scope_id="scope_other")
    assert journal.list_journal_history() == []

    delivered_at = _later(outcome.personalization_persisted_at)
    first_ack = _ack(
        request,
        repository,
        journal,
        outcome,
        delivered_at=delivered_at,
    )
    history_after_first = journal.list_journal_history()
    retry_ack = _ack(
        request,
        repository,
        journal,
        outcome,
        delivered_at=delivered_at,
    )
    assert first_ack.status == "delivered"
    assert retry_ack.status == "already_delivered"
    assert journal.list_journal_history() == history_after_first

    with pytest.raises(PersonalizationSaveAdapterError, match="timestamp conflict"):
        _ack(
            request,
            repository,
            journal,
            outcome,
            delivered_at=_later(outcome.personalization_persisted_at, 2),
        )
    with pytest.raises(PersonalizationSaveAdapterError, match="append failed"):
        _ack(
            request,
            repository,
            _FailingAckJournal(),
            outcome,
            delivered_at=_later(outcome.personalization_persisted_at),
        )
    assert (repository.runs_dir / f"{RESULT_ID}.json").read_bytes() == before_bytes
    assert repository.load_result(RESULT_ID).to_dict() == before_result.to_dict()


def test_save_error_does_not_emit_delivery_ack_and_missing_ack_is_not_delivered(
    tmp_path: Path,
) -> None:
    request = _request()
    with pytest.raises(RuntimeError, match="repository save failed"):
        _persist(request, _FailingRepository())

    config = _TempConfig(tmp_path / "output")
    repository = _CountingRecommendationRepository(config)
    journal = JournalService(config)  # type: ignore[arg-type]
    outcome = _persist(request, repository)
    loaded = repository.load_result(RESULT_ID)
    assert loaded is not None
    projection = PersonalizationProjectionService(
        delivery_reader=journal.list_personalization_delivery_acks,
    ).build_for_candidate(
        result_id=RESULT_ID,
        stock_code=STOCK_CODE,
        personalization_scope_id=SCOPE_ID,
        result=loaded,
        projection_receipt=_receipt(),
    )
    assert outcome.personalization_delivery_statuses == ("persisted",)
    assert projection.status == "not_delivered"
    assert projection.delivery_status == "generated"
    assert journal.list_journal_history() == []


def test_journal_delivery_ack_stream_cas_rejects_stale_history_without_append(
    tmp_path: Path,
) -> None:
    config = _TempConfig(tmp_path / "output")
    journal = JournalService(config)  # type: ignore[arg-type]
    capture = PersonalizationRecommendationSaveAdapter()
    request = _request()
    repository = _CountingRecommendationRepository(config)
    outcome = _persist(request, repository)
    saved = repository.load_result(RESULT_ID)
    assert saved is not None
    saved_capture = capture.captures_from_result(saved)[0]
    persisted_at = outcome.personalization_persisted_at
    delivered_at = _later(persisted_at)
    acknowledgement = {
        "result_id": RESULT_ID,
        "stock_code": STOCK_CODE,
        "personalization_scope_id": SCOPE_ID,
        "scope_envelope_hash": saved_capture.scope.envelope_hash,
        "delivery_id": DELIVERY_ID,
        "capture_hash": saved_capture.capture_hash,
        "request_id": saved_capture.request_id,
        "persisted_at": persisted_at,
        "delivered_at": delivered_at,
        "recorded_at": delivered_at,
        "revision_id": "personalization-delivery-ack:cas:2330",
    }

    with pytest.raises(RuntimeError, match="stream_conflict"):
        journal.record_personalization_delivery_acks(
            [acknowledgement],
            expected_history_token="stale-history-token",
        )
    assert journal.list_journal_history() == []
