"""P08a 唯讀投影隔離測試；checkpoint 由現行 public writer 真實建立。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
import json
import sqlite3

import pytest

from app_module.personal_paper_store_paths import PersonalStoreCustody
from app_module.strategy_paper_account_service import (
    StrategyPaperAccountBinding,
    file_sha256,
)
from app_module.strategy_performance_read_service import (
    PaperCheckpointCard,
    PaperCheckpointSelector,
    QualificationStatus,
    ReadStatus,
    SourceAvailabilityStatus,
    StrategyPerformanceReadService,
)
from test_strategy_paper_account_daily import (
    _create_account,
    _fill_call,
    _seed_account,
    _writer,
    _write_json,
    _zero_fill_call,
)


_CONFIG = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}


def _selector(binding: object, result: object) -> PaperCheckpointSelector:
    return PaperCheckpointSelector(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        decision_cutoff=datetime.now(timezone.utc),
    )


def _assert_blocked_card_has_no_partial_account_data(
    card: PaperCheckpointCard,
) -> None:
    assert card.read_status is ReadStatus.BLOCKED
    assert card.account_status is None
    assert card.binding is None
    assert card.decision_date is None
    assert card.cash is None
    assert card.nav is None
    assert card.zero_fill is None
    assert card.ledger_marker is None
    assert card.availability is None
    assert card.row_provenance is None
    assert card.positions == ()
    assert card.fills == ()
    assert card.qualification is QualificationStatus.UNKNOWN
    assert card.source_available_at is None
    assert card.official_session is None
    assert all(cell.value is None for _, cell in card.metrics)

@pytest.mark.parametrize("filled", [False, True])
def test_read_model_projects_exact_checkpoint_without_writing(
    tmp_path, monkeypatch, filled: bool
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(
        service, paths, manifest, monkeypatch
    )
    result_id = "p08a-filled" if filled else "p08a-zero"
    writer = _writer(service, paths, result_id, _CONFIG)
    result = (
        _fill_call(writer, binding, prior, result_id=result_id)
        if filled
        else _zero_fill_call(writer, binding, prior, result_id=result_id)
    )
    state_before = store_paths.state_db.read_bytes()
    ledger_before = store_paths.cost_ledger_db.read_bytes()

    with localcontext(Context(prec=3)):
        card = StrategyPerformanceReadService(
            account_service=service
        ).read_paper_checkpoint(_selector(binding, result))

    assert card.account_status.value == "ready"
    assert card.read_status is ReadStatus.VERIFIED
    assert card.qualification is QualificationStatus.NOT_QUALIFIED
    assert card.binding is not None
    assert card.binding.policy_id == binding.policy_id
    assert card.binding.policy_version == binding.policy_version
    assert card.binding.policy_sha256 == binding.policy_sha256
    assert card.binding.cost_model_sha256 == binding.cost_model_sha256
    assert card.binding.benchmark_sha256 == binding.benchmark_sha256
    assert card.binding.initial_capital == "500000"
    assert card.binding.start_date == "2026-08-01"
    assert card.cash == (Decimal("399884.98") if filled else Decimal("500000.00"))
    assert card.nav == (
        Decimal("501884.98") if filled else Decimal("500000.00")
    )
    assert card.zero_fill is (not filled)
    assert card.ledger_marker is not None
    assert card.availability is not None
    assert card.row_provenance is not None
    assert card.ledger_marker.operation_id == result.operation_id
    assert card.ledger_marker.portfolio_id == binding.portfolio_id
    assert card.ledger_marker.expected_rowset_hash
    assert card.ledger_marker.rowset_hash_after
    assert card.ledger_marker.fill_batch_sha256
    assert card.ledger_marker.operation_sha256
    assert card.ledger_marker.marker_sha256
    assert card.operation_sha256
    assert card.operation_sha256 != card.ledger_marker.operation_sha256
    assert card.availability.receipt_sha256 == result.availability_sha256
    assert card.availability.operation_id == result.operation_id
    assert card.availability.snapshot_id == result.snapshot_id
    assert card.availability.portfolio_id == binding.portfolio_id
    assert card.availability.account_namespace == binding.account_namespace
    assert card.availability.binding_sha256 == binding.binding_sha256
    assert card.availability.base_receipt_sha256 == result.receipt_sha256
    assert card.availability.persisted_at == result.persisted_at
    assert card.availability.available_at == result.available_at
    assert card.row_provenance.source_result_id == result_id
    assert card.row_provenance.operation_sha256
    assert card.row_provenance.operation_sha256 == card.operation_sha256
    assert card.row_provenance.ledger_operation_sha256
    assert (
        card.row_provenance.ledger_operation_sha256
        == card.ledger_marker.operation_sha256
    )
    assert card.row_provenance.snapshot_sha256
    assert card.source_availability_status is SourceAvailabilityStatus.UNVERIFIED
    assert card.source_available_at is None
    assert card.official_session is None
    assert card.period_curve_status == "unavailable"
    assert all(cell.value is None and cell.reason for _, cell in card.metrics)
    assert card.qualification_reasons
    if filled:
        assert len(card.fills) == 1
        fill = card.fills[0]
        assert fill.fill_id == "daily-fill-20260803-2330"
        assert fill.order_id == "daily-order-20260803-2330"
        assert fill.portfolio_id == binding.portfolio_id
        assert fill.event_date == "2026-08-03"
        assert fill.stock_code == "2330"
        assert fill.side == "buy"
        assert fill.requested_quantity == 1000
        assert fill.filled_quantity == 1000
        assert fill.source_event_id == "daily-event-20260803-2330"
        assert fill.reference_price == Decimal("100.00")
        assert fill.fill_price == Decimal("100.10")
        assert fill.commission == Decimal("15.02")
        assert fill.tax == Decimal("0.00")
        assert fill.slippage_cost == Decimal("100.00")
        assert fill.turnover_bp == 2002
        assert fill.execution_gap_bp == 10
        assert fill.status == "filled"
        assert fill.override_reason is None
        assert fill.source_type == "paper_simulation"
        assert fill.research_only is True
        assert fill.broker_order_allowed is False
        assert fill.auto_rebalance_allowed is False
        assert card.ledger_marker.ordered_fill_ids == (fill.fill_id,)
        assert card.ledger_marker.zero_fill is False
        assert card.ledger_marker.transition_id == "daily-transition-20260803"
        assert card.ledger_marker.transition_sha256
        assert card.row_provenance.source_event_ids == (fill.source_event_id,)
        assert len(card.positions) == 1
        assert card.positions[0].stock_code == "2330"
        assert card.positions[0].quantity == 1000
        assert card.positions[0].mark_price == Decimal("102.00")
        assert card.positions[0].market_value == Decimal("102000.00")
    else:
        assert card.fills == ()
        assert card.positions == ()
        assert card.ledger_marker.ordered_fill_ids == ()
        assert card.ledger_marker.zero_fill is True
        assert card.ledger_marker.transition_id is None
        assert card.ledger_marker.transition_sha256 is None
        assert card.row_provenance.source_event_ids == ()
    assert store_paths.state_db.read_bytes() == state_before
    assert store_paths.cost_ledger_db.read_bytes() == ledger_before


def test_cutoff_before_base_checkpoint_is_blocked_without_fallback(
    tmp_path, monkeypatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(
        service, paths, manifest, monkeypatch
    )
    result_id = "p08a-early-cutoff"
    result = _zero_fill_call(
        _writer(service, paths, result_id, _CONFIG),
        binding,
        prior,
        result_id=result_id,
    )
    state_before = store_paths.state_db.read_bytes()
    ledger_before = store_paths.cost_ledger_db.read_bytes()
    selector = replace(
        _selector(binding, result),
        decision_cutoff=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )

    card = StrategyPerformanceReadService(
        account_service=service
    ).read_paper_checkpoint(selector)
    _assert_blocked_card_has_no_partial_account_data(card)

    assert card.read_status is ReadStatus.BLOCKED
    assert card.reason == "checkpoint_read_decision_before_base_cutoff"
    assert card.binding is None
    assert card.fills == ()
    assert card.row_provenance is None
    assert card.qualification is QualificationStatus.UNKNOWN
    assert store_paths.state_db.read_bytes() == state_before
    assert store_paths.cost_ledger_db.read_bytes() == ledger_before


@pytest.mark.parametrize(
    "changed",
    [
        {"strategy_id": "wrong-strategy"},
        {"strategy_version_id": "wrong-version"},
        {"account_namespace": "wrong-namespace"},
        {"operation_id": "wrong-operation"},
        {"snapshot_id": "wrong-snapshot"},
    ],
)
def test_exact_identity_mismatch_is_blocked(
    tmp_path, monkeypatch, changed: dict[str, str]
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(
        service, paths, manifest, monkeypatch
    )
    result_id = "p08a-exact-mismatch"
    result = _zero_fill_call(
        _writer(service, paths, result_id, _CONFIG),
        binding,
        prior,
        result_id=result_id,
    )
    state_before = store_paths.state_db.read_bytes()
    ledger_before = store_paths.cost_ledger_db.read_bytes()
    selector = replace(_selector(binding, result), **changed)

    card = StrategyPerformanceReadService(
        account_service=service
    ).read_paper_checkpoint(selector)
    _assert_blocked_card_has_no_partial_account_data(card)

    assert card.read_status is ReadStatus.BLOCKED
    assert card.account_status is None
    assert card.binding is None
    assert card.row_provenance is None
    assert card.qualification is QualificationStatus.UNKNOWN
    assert store_paths.state_db.read_bytes() == state_before
    assert store_paths.cost_ledger_db.read_bytes() == ledger_before


def test_changed_ledger_is_rejected_by_public_reader(
    tmp_path, monkeypatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(
        service, paths, manifest, monkeypatch
    )
    result_id = "p08a-ledger-change"
    result = _fill_call(
        _writer(service, paths, result_id, _CONFIG),
        binding,
        prior,
        result_id=result_id,
    )
    selected = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    )
    assert selected.route is not None
    ledger_path = PersonalStoreCustody(
        selected.route, paths
    ).io(store_paths.cost_ledger_db)
    connection = sqlite3.connect(ledger_path)
    try:
        connection.execute("PRAGMA journal_mode=MEMORY")
        connection.execute(
            "UPDATE paper_trade_ledger SET commission='999.99' WHERE fill_id=?",
            ("daily-fill-20260803-2330",),
        )
        connection.commit()
    finally:
        connection.close()
    state_before = store_paths.state_db.read_bytes()
    ledger_before = store_paths.cost_ledger_db.read_bytes()

    card = StrategyPerformanceReadService(
        account_service=service
    ).read_paper_checkpoint(_selector(binding, result))
    _assert_blocked_card_has_no_partial_account_data(card)

    assert card.read_status is ReadStatus.BLOCKED
    assert card.reason == "checkpoint_read_ledger_append_chain_mismatch"
    assert card.fills == ()
    assert card.row_provenance is None
    assert store_paths.state_db.read_bytes() == state_before
    assert store_paths.cost_ledger_db.read_bytes() == ledger_before


def test_same_source_event_reads_independently_in_two_exact_accounts(
    tmp_path, monkeypatch
) -> None:
    service, paths, first_manifest = _create_account(tmp_path)
    first_prior, first_store_paths, first_binding = _seed_account(
        service, paths, first_manifest, monkeypatch
    )
    first_result_id = "p08a-two-account-first"
    first_result = _fill_call(
        _writer(service, paths, first_result_id, _CONFIG),
        first_binding,
        first_prior,
        result_id=first_result_id,
    )
    first_state_after_fill = first_store_paths.state_db.read_bytes()
    first_ledger_after_fill = first_store_paths.cost_ledger_db.read_bytes()

    second_version_id = "version-daily-second"
    second_strategy_id = "strategy-daily-second"
    second_source_run_id = "run-version-daily-second"
    first_strategy_path = (
        service.strategy_versions_root / f"{first_binding.strategy_version_id}.json"
    )
    strategy_payload = json.loads(first_strategy_path.read_text(encoding="utf-8"))
    strategy_payload.update(
        {
            "version_id": second_version_id,
            "strategy_id": second_strategy_id,
            "strategy_version": "2.0.0",
            "source_run_id": second_source_run_id,
        }
    )
    strategy_raw = json.dumps(
        strategy_payload, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    (service.strategy_versions_root / f"{second_version_id}.json").write_bytes(
        strategy_raw
    )
    binding_fields = {
        key: value
        for key, value in first_manifest.items()
        if key
        not in {
            "schema_version",
            "binding_sha256",
            "account_namespace",
            "portfolio_id",
        }
    }
    binding_fields.update(
        {
            "strategy_version_id": second_version_id,
            "strategy_id": second_strategy_id,
            "strategy_version": "2.0.0",
            "source_run_id": second_source_run_id,
            "strategy_artifact_sha256": file_sha256(strategy_raw),
        }
    )
    second_manifest = StrategyPaperAccountBinding.create_manifest_payload(
        **binding_fields
    )
    second_manifest_path = (
        paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(second_manifest["account_namespace"])
        / "account_binding.json"
    )
    _write_json(second_manifest_path, second_manifest)

    second_prior, second_store_paths, second_binding = _seed_account(
        service, paths, second_manifest, monkeypatch
    )
    assert first_store_paths.state_db != second_store_paths.state_db
    assert first_store_paths.cost_ledger_db != second_store_paths.cost_ledger_db
    second_result_id = "p08a-two-account-second"
    second_result = _fill_call(
        _writer(
            service,
            paths,
            second_result_id,
            _CONFIG,
            strategy_version_id=second_version_id,
        ),
        second_binding,
        second_prior,
        result_id=second_result_id,
    )
    assert first_store_paths.state_db.read_bytes() == first_state_after_fill
    assert first_store_paths.cost_ledger_db.read_bytes() == first_ledger_after_fill

    reader = StrategyPerformanceReadService(account_service=service)
    first_card = reader.read_paper_checkpoint(_selector(first_binding, first_result))
    second_card = reader.read_paper_checkpoint(
        _selector(second_binding, second_result)
    )

    assert first_binding.account_namespace != second_binding.account_namespace
    assert first_binding.portfolio_id != second_binding.portfolio_id
    assert first_card.read_status is ReadStatus.VERIFIED
    assert second_card.read_status is ReadStatus.VERIFIED
    assert first_card.cash == Decimal("399884.98")
    assert second_card.cash == Decimal("399884.98")
    assert first_card.nav == Decimal("501884.98")
    assert second_card.nav == Decimal("501884.98")
    assert first_card.fills[0].portfolio_id == first_binding.portfolio_id
    assert second_card.fills[0].portfolio_id == second_binding.portfolio_id
    assert first_card.fills[0].commission == Decimal("15.02")
    assert second_card.fills[0].commission == Decimal("15.02")
    assert first_card.zero_fill is False
    assert second_card.zero_fill is False
    assert first_card.ledger_marker.ordered_fill_ids == (
        first_card.fills[0].fill_id,
    )
    assert second_card.ledger_marker.ordered_fill_ids == (
        second_card.fills[0].fill_id,
    )
    assert first_card.fills[0].source_event_id == "daily-event-20260803-2330"
    assert second_card.fills[0].source_event_id == "daily-event-20260803-2330"
    assert first_card.row_provenance.account_namespace == first_binding.account_namespace
    assert second_card.row_provenance.account_namespace == second_binding.account_namespace
    assert first_card.row_provenance.source_event_ids == (
        "daily-event-20260803-2330",
    )
    assert second_card.row_provenance.source_event_ids == (
        "daily-event-20260803-2330",
    )
    assert (
        first_card.row_provenance.source_event_ids
        == second_card.row_provenance.source_event_ids
    )
    assert first_card.row_provenance.portfolio_id != second_card.row_provenance.portfolio_id
    assert first_card.qualification is QualificationStatus.NOT_QUALIFIED
    assert second_card.qualification is QualificationStatus.NOT_QUALIFIED
