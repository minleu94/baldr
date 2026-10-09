from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import scripts.refresh_current_market_status_observation as capture_module
import tests.test_selection_market_assignments as market_test_helpers

from app_module.selection_current_source_pair import (
    CurrentSelectionSourcePairError,
    open_current_selection_source_pair,
    publish_current_selection_bundle,
    publish_completed_technical_selection_bundle,
    produce_current_selection_bundle,
)
from data_module.selection_official_events import CurrentOfficialDisposalReader
from data_module.selection_market_assignments import CurrentMarketAssignmentError
from tests.test_selection_market_assignments import _create_capture
from tests.test_daily_market_technical_official_disposition_bundle_v1 import _FrozenDateTime


def test_same_capture_pair_remains_exact_after_pointer_advances(tmp_path: Path) -> None:
    pointer = _create_capture(tmp_path)
    cutoff = datetime.now(timezone.utc)
    pair = open_current_selection_source_pair(pointer, cutoff_at=cutoff)
    _create_capture(tmp_path)
    old_disposal = CurrentOfficialDisposalReader.from_exact(pair.disposal.source_pin, cutoff_at=cutoff)
    assert old_disposal.source_pin == pair.disposal.source_pin
    assert pair.market.get("1101").state == "assigned_twse"
    assert pair.market.source_pin.run_id == pair.disposal.source_pin.run_id
    assert pair.market.get("1101").historical_pit_eligible is False
    assert pair.disposal.source_pin.historical_pit_eligible is False


def test_interleaved_pointer_update_is_rejected_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _create_capture(tmp_path)
    first_pointer = pointer.read_bytes()
    _create_capture(tmp_path)
    second_pointer = pointer.read_bytes()
    pointer.write_bytes(first_pointer)
    real_open = CurrentOfficialDisposalReader.from_pointer

    def advance_then_open(path: str | Path, *, cutoff_at: datetime) -> CurrentOfficialDisposalReader:
        pointer.write_bytes(second_pointer)
        return real_open(path, cutoff_at=cutoff_at)

    monkeypatch.setattr(CurrentOfficialDisposalReader, "from_pointer", advance_then_open)
    with pytest.raises(CurrentSelectionSourcePairError, match="version_mismatch"):
        open_current_selection_source_pair(pointer, cutoff_at=datetime.now(timezone.utc))


@pytest.mark.parametrize("cancelled", [True, 1])
def test_cancel_and_non_boolean_result_do_not_open_source(
    tmp_path: Path, cancelled: Any,
) -> None:
    with pytest.raises(CurrentSelectionSourcePairError, match="cancel"):
        open_current_selection_source_pair(
            tmp_path / "missing.json", cutoff_at=datetime.now(timezone.utc),
            cancel_callback=lambda: cancelled,
        )


def test_naive_cutoff_is_rejected_before_source_io(tmp_path: Path) -> None:
    with pytest.raises(CurrentSelectionSourcePairError, match="aware_cutoff"):
        open_current_selection_source_pair(tmp_path / "missing.json", cutoff_at=datetime(2026, 10, 7))


def test_adapter_passes_original_typed_pins_to_existing_writer(tmp_path: Path) -> None:
    pointer = _create_capture(tmp_path)
    writer = Mock()
    result = publish_current_selection_bundle(
        writer, pointer_path=pointer, cutoff_at=datetime.now(timezone.utc),
        store_output_root=tmp_path / "store", generation_identity_sha256="a" * 64,
        plan_identity_sha256="b" * 64, expected_plan_sha256="c" * 64,
        receipt_identity_sha256="d" * 64, expected_receipt_sha256="e" * 64,
    )
    assert result is writer.create_from_pins.return_value
    kwargs = writer.create_from_pins.call_args.kwargs
    assert kwargs["market_assignment_source_pin"].run_id == kwargs["official_disposal_source_pin"].run_id
    assert kwargs["expected_receipt_sha256"] == "e" * 64
    assert kwargs["store_output_root"] == tmp_path / "store"
    # 此案例只驗 delegation；真正 writer 的 source／cutoff／publication gate 未被替代。


def test_cancel_after_pair_open_never_calls_writer(tmp_path: Path) -> None:
    pointer = _create_capture(tmp_path)
    writer = Mock()
    cancellations = iter((False, False, False, True))
    with pytest.raises(CurrentSelectionSourcePairError, match="cancelled"):
        publish_current_selection_bundle(
            writer, pointer_path=pointer, cutoff_at=datetime.now(timezone.utc),
            store_output_root=tmp_path / "store", generation_identity_sha256="a" * 64,
            plan_identity_sha256="b" * 64, expected_plan_sha256="c" * 64,
            receipt_identity_sha256="d" * 64, expected_receipt_sha256="e" * 64,
            cancel_callback=lambda: next(cancellations),
        )
    writer.create_from_pins.assert_not_called()


def test_capture_published_after_decision_is_rejected(tmp_path: Path) -> None:
    cutoff = datetime.now(timezone.utc)
    pointer = _create_capture(tmp_path)
    with pytest.raises(CurrentMarketAssignmentError, match="pointer_after_cutoff"):
        open_current_selection_source_pair(pointer, cutoff_at=cutoff)


def test_zero_microsecond_same_capture_is_not_mistaken_for_mixed_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_FrozenDateTime, "fixed_now", datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=2))
    monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(market_test_helpers, "datetime", _FrozenDateTime)
    pointer = _create_capture(tmp_path)
    pair = open_current_selection_source_pair(pointer, cutoff_at=datetime.now(timezone.utc))
    assert pair.market.source_pin.pointer_published_at != pair.disposal.source_pin.pointer_published_at
    assert datetime.fromisoformat(pair.market.source_pin.pointer_published_at) == datetime.fromisoformat(pair.disposal.source_pin.pointer_published_at)


@pytest.mark.parametrize("status", ["cancelled", "failed", "complete"])
def test_incomplete_production_never_opens_sources_or_publishes(
    tmp_path: Path, status: Any,
) -> None:
    from app_module.daily_market_technical_universe_v4_producer import (
        DailyMarketTechnicalUniverseV4ProductionResult,
    )
    result = DailyMarketTechnicalUniverseV4ProductionResult(
        status=status, step="fixture", plan=None, receipt=None,
        error_code=None, cause_code=None, resumed=False,
        calculation_identity_sha256=None, completed_segment_indices=(),
        missing_data_stock_codes=(),
    )
    writer = Mock()
    with pytest.raises(CurrentSelectionSourcePairError, match="result_incomplete"):
        publish_completed_technical_selection_bundle(
            writer, production_result=result, pointer_path=tmp_path / "missing.json",
            store_output_root=tmp_path / "missing_store",
        )
    writer.create_from_pins.assert_not_called()


@pytest.mark.parametrize("use_fixed_pair", [False, True])
def test_real_complete_producer_preserves_original_cutoff_and_exact_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    use_fixed_pair: bool,
) -> None:
    import app_module.selection_current_source_pair as adapter
    from app_module.daily_market_technical_universe_v4_producer import (
        produce_daily_market_technical_universe_v4,
    )
    from tests.test_daily_market_technical_universe_v4_producer import (
        _write_source, _scope_and_store_root, _cohort, _request,
    )
    database = tmp_path / "synthetic.sqlite"
    _write_source(database, ("1101",))
    scope, store_root = _scope_and_store_root(tmp_path, database)
    result = produce_daily_market_technical_universe_v4(
        _request(database, _cohort(("1101",)), store_root, scope)
    )
    assert result.status == "complete"
    assert result.plan is not None and result.receipt is not None
    if use_fixed_pair:
        original_cutoff = result.plan.source_clock.decision_cutoff
        monkeypatch.setattr(_FrozenDateTime, "fixed_now", original_cutoff - timedelta(seconds=2))
        monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
        monkeypatch.setattr(market_test_helpers, "datetime", _FrozenDateTime)
        capture_root = tmp_path / "capture"
        capture_root.mkdir()
        pointer = _create_capture(capture_root)
        pair = open_current_selection_source_pair(pointer, cutoff_at=original_cutoff)
        # 新版發布日在原 cutoff 後，若重新讀 pointer 會被拒絕；固定來源仍可沿原件轉交。
        monkeypatch.setattr(_FrozenDateTime, "fixed_now", original_cutoff + timedelta(seconds=2))
        _create_capture(capture_root)
        with pytest.raises(CurrentMarketAssignmentError, match="pointer_after_cutoff"):
            open_current_selection_source_pair(pointer, cutoff_at=original_cutoff)
        writer = Mock()
        published = publish_completed_technical_selection_bundle(
            writer, production_result=result, source_pair=pair, store_output_root=store_root,
        )
        assert published is writer.create_from_pins.return_value
        args = writer.create_from_pins.call_args.kwargs
        assert args["market_assignment_source_pin"] == pair.market.source_pin
        assert args["official_disposal_source_pin"] == pair.disposal.source_pin
        from dataclasses import replace
        new_disposal = CurrentOfficialDisposalReader.from_pointer(
            pointer, cutoff_at=original_cutoff + timedelta(seconds=3),
        )
        with pytest.raises(CurrentSelectionSourcePairError, match="version_mismatch"):
            replace(pair, disposal=new_disposal)
        with pytest.raises(CurrentSelectionSourcePairError, match="cutoff_mismatch"):
            publish_completed_technical_selection_bundle(
                writer, production_result=result, store_output_root=store_root,
                source_pair=replace(pair, cutoff_at=original_cutoff + timedelta(seconds=1)),
            )
        assert writer.create_from_pins.call_count == 1
        with pytest.raises(CurrentSelectionSourcePairError, match="exactly_one"):
            publish_completed_technical_selection_bundle(
                writer, production_result=result, store_output_root=store_root,
                source_pair=pair, pointer_path=pointer,
            )
        assert writer.create_from_pins.call_count == 1
        return
    delegated = Mock()
    monkeypatch.setattr(adapter, "publish_current_selection_bundle", delegated)
    writer = Mock()
    published = publish_completed_technical_selection_bundle(
        writer, production_result=result, pointer_path=tmp_path / "pointer.json",
        store_output_root=store_root,
    )
    assert published is delegated.return_value
    args = delegated.call_args.kwargs
    assert args["cutoff_at"] == result.plan.source_clock.decision_cutoff
    assert args["expected_plan_sha256"] == result.plan_sha256
    assert args["expected_receipt_sha256"] == result.receipt.content_sha256
    assert args["generation_identity_sha256"] == result.plan.generation_identity_sha256
    # 真產製器＋轉交契約；此案例不宣稱後續 bundle writer 或 UI 已接受。


def test_coordinator_freezes_sources_before_real_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.daily_market_technical_universe_v4_producer as producer
    from tests.test_daily_market_technical_universe_v4_producer import (
        _write_source, _scope_and_store_root, _cohort, _request,
    )
    database = tmp_path / "synthetic.sqlite"
    _write_source(database, ("1101",))
    scope, store_root = _scope_and_store_root(tmp_path, database)
    request = _request(database, _cohort(("1101",)), store_root, scope)
    monkeypatch.setattr(_FrozenDateTime, "fixed_now", request.decision_cutoff - timedelta(seconds=2))
    monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(market_test_helpers, "datetime", _FrozenDateTime)
    capture_root = tmp_path / "capture"
    capture_root.mkdir()
    pointer = _create_capture(capture_root)
    pair = open_current_selection_source_pair(pointer, cutoff_at=request.decision_cutoff)
    real_produce = producer.produce_daily_market_technical_universe_v4

    def advance_then_produce(received: Any) -> Any:
        assert received is request
        monkeypatch.setattr(_FrozenDateTime, "fixed_now", request.decision_cutoff + timedelta(seconds=2))
        _create_capture(capture_root)
        return real_produce(received)

    monkeypatch.setattr(producer, "produce_daily_market_technical_universe_v4", advance_then_produce)
    writer = Mock()
    outcome = produce_current_selection_bundle(writer, production_request=request, pointer_path=pointer)
    assert outcome.technical_result.status == "complete"
    assert outcome.bundle_reference is writer.create_from_pins.return_value
    assert writer.create_from_pins.call_args.kwargs["market_assignment_source_pin"] == pair.market.source_pin
    assert writer.create_from_pins.call_args.kwargs["official_disposal_source_pin"] == pair.disposal.source_pin
    with pytest.raises(CurrentMarketAssignmentError, match="pointer_after_cutoff"):
        open_current_selection_source_pair(pointer, cutoff_at=request.decision_cutoff)


@pytest.mark.parametrize("status", ["failed", "cancelled", "complete"])
def test_coordinator_incomplete_production_preserves_result_without_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: Any,
) -> None:
    import app_module.daily_market_technical_universe_v4_producer as producer
    from tests.test_daily_market_technical_universe_v4_producer import (
        _write_source, _scope_and_store_root, _cohort, _request,
    )
    database = tmp_path / "synthetic.sqlite"
    _write_source(database, ("1101",))
    scope, store_root = _scope_and_store_root(tmp_path, database)
    request = _request(database, _cohort(("1101",)), store_root, scope)
    monkeypatch.setattr(_FrozenDateTime, "fixed_now", request.decision_cutoff - timedelta(seconds=2))
    monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(market_test_helpers, "datetime", _FrozenDateTime)
    pointer = _create_capture(tmp_path)
    incomplete = producer.DailyMarketTechnicalUniverseV4ProductionResult(
        status=status, step="fixture", plan=None, receipt=None, error_code=None,
        cause_code=None, resumed=False, calculation_identity_sha256=None,
        completed_segment_indices=(), missing_data_stock_codes=(),
    )
    run = Mock(return_value=incomplete)
    monkeypatch.setattr(producer, "produce_daily_market_technical_universe_v4", run)
    writer = Mock()
    outcome = produce_current_selection_bundle(writer, production_request=request, pointer_path=pointer)
    assert outcome.technical_result is incomplete
    assert outcome.bundle_reference is None
    writer.create_from_pins.assert_not_called()
    run.assert_called_once_with(request)


def test_coordinator_rejects_late_capture_before_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.daily_market_technical_universe_v4_producer as producer
    from tests.test_daily_market_technical_universe_v4_producer import (
        _write_source, _scope_and_store_root, _cohort, _request,
    )
    database = tmp_path / "synthetic.sqlite"
    _write_source(database, ("1101",))
    scope, store_root = _scope_and_store_root(tmp_path, database)
    request = _request(database, _cohort(("1101",)), store_root, scope)
    monkeypatch.setattr(_FrozenDateTime, "fixed_now", request.decision_cutoff + timedelta(seconds=2))
    monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(market_test_helpers, "datetime", _FrozenDateTime)
    pointer = _create_capture(tmp_path)
    run = Mock()
    monkeypatch.setattr(producer, "produce_daily_market_technical_universe_v4", run)
    writer = Mock()
    with pytest.raises(CurrentMarketAssignmentError, match="pointer_after_cutoff"):
        produce_current_selection_bundle(writer, production_request=request, pointer_path=pointer)
    run.assert_not_called()
    writer.create_from_pins.assert_not_called()
