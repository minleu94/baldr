"""P08a checkpoint 候選目錄的隔離 read-only 契約測試。"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

import app_module.strategy_paper_account_availability as availability_module
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailabilityError,
    list_strategy_paper_account_checkpoint_candidates,
    read_exact_strategy_paper_account_checkpoint,
)
from test_strategy_paper_account_daily import (
    _create_account,
    _seed_account,
    _writer,
    _zero_fill_call,
)

_TABLE = "strategy_paper_account_availability_v1"
_CONFIG = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}


def _real_checkpoint(tmp_path, monkeypatch):
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    result_id = "catalogue-real-writer-checkpoint"
    result = _zero_fill_call(
        _writer(service, paths, result_id, _CONFIG),
        binding,
        prior,
        result_id=result_id,
    )
    return service, paths, store_paths, binding, result


def _list(service, binding, *, cutoff=None):
    return list_strategy_paper_account_checkpoint_candidates(
        service,
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        decision_cutoff=cutoff or datetime.now(timezone.utc),
    )


def _write_state(state_path, statement, parameters=()):
    with closing(sqlite3.connect(state_path)) as connection:
        with connection:
            connection.execute(statement, parameters)


def test_real_daily_writer_checkpoint_is_only_a_candidate_until_exact_read(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 1
    candidate = catalogue.rows[0]
    assert candidate.operation_id == result.operation_id
    assert candidate.snapshot_id == result.snapshot_id
    assert candidate.row_state == "candidate_pending_exact_reader"
    assert candidate.exact_reader_required is True
    assert candidate.checkpoint_verified is False
    assert candidate.performance_eligible is False
    assert catalogue.checkpoint_verified is False
    assert catalogue.performance_eligible is False
    readback = read_exact_strategy_paper_account_checkpoint(
        service,
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        operation_id=candidate.operation_id,
        snapshot_id=candidate.snapshot_id,
        decision_cutoff=catalogue.decision_cutoff,
    )
    assert readback.snapshot.snapshot_id == candidate.snapshot_id
    assert store_paths.state_db.read_bytes() == before


def test_empty_availability_catalogue_is_explicit_and_does_not_write(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'DELETE FROM "{_TABLE}" WHERE snapshot_id = ?',
        (result.snapshot_id,),
    )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert catalogue.rows == ()
    assert catalogue.complete is True
    assert catalogue.truncated is False
    assert store_paths.state_db.read_bytes() == before


def test_missing_availability_table_fails_closed(tmp_path, monkeypatch):
    service, _, store_paths, binding, _ = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(store_paths.state_db, f'DROP TABLE "{_TABLE}"')

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_clock_unknown",
    ):
        _list(service, binding)


def test_missing_clock_is_retained_as_blocked_row(tmp_path, monkeypatch):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET available_at_utc = NULL WHERE snapshot_id = ?',
        (result.snapshot_id,),
    )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 1
    assert catalogue.rows[0].row_state == "blocked"
    assert "availability_clock_unknown" in catalogue.rows[0].blockers
    assert catalogue.rows[0].checkpoint_verified is False
    assert store_paths.state_db.read_bytes() == before


def test_requested_namespace_and_version_never_fall_back(tmp_path, monkeypatch):
    service, _, _, binding, _ = _real_checkpoint(tmp_path, monkeypatch)
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_exact_binding_unavailable",
    ):
        list_strategy_paper_account_checkpoint_candidates(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id="version-not-selected",
            account_namespace=binding.account_namespace,
            decision_cutoff=datetime.now(timezone.utc),
        )
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_exact_binding_unavailable",
    ):
        list_strategy_paper_account_checkpoint_candidates(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace="acct-" + "f" * 64,
            decision_cutoff=datetime.now(timezone.utc),
        )


def test_naive_and_future_query_cutoffs_are_rejected(tmp_path, monkeypatch):
    service, _, _, binding, _ = _real_checkpoint(tmp_path, monkeypatch)
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_decision_cutoff_timezone_unknown",
    ):
        _list(service, binding, cutoff=datetime(2026, 10, 13, 12, 0))
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_decision_cutoff_in_future",
    ):
        _list(service, binding, cutoff=datetime.now(timezone.utc) + timedelta(days=1))


def test_late_and_future_source_clocks_are_blocked_not_filtered(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET persisted_at_utc = ?, available_at_utc = ? '
        "WHERE snapshot_id = ?",
        ("2026-08-02T08:25:00+00:00", "2026-08-02T08:30:00+00:00", result.snapshot_id),
    )
    late = _list(
        service,
        binding,
        cutoff=datetime(2026, 8, 2, 8, 29, tzinfo=timezone.utc),
    )
    assert len(late.rows) == 1
    assert late.rows[0].row_state == "blocked"
    assert "availability_after_decision_cutoff" in late.rows[0].blockers

    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET persisted_at_utc = ?, available_at_utc = ? '
        "WHERE snapshot_id = ?",
        ("2026-10-13T13:00:00+00:00", "2026-10-13T13:01:00+00:00", result.snapshot_id),
    )
    fixed_now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(availability_module, "_utc_now", lambda: fixed_now)
    future = _list(service, binding, cutoff=fixed_now)
    assert len(future.rows) == 1
    assert future.rows[0].row_state == "blocked"
    assert "availability_clock_in_future" in future.rows[0].blockers


def test_row_schema_and_binding_drift_are_visible_not_candidates(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET schema_version = ?, binding_sha256 = ?, '
        'receipt_sha256 = ? WHERE snapshot_id = ?',
        ("future-schema", "sha256:" + "d" * 64, "invalid-hash", result.snapshot_id),
    )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 1
    assert catalogue.rows[0].row_state == "blocked"
    assert "availability_schema_version_mismatch" in catalogue.rows[0].blockers
    assert "binding_sha256_binding_mismatch" in catalogue.rows[0].blockers
    assert "receipt_sha256_invalid" in catalogue.rows[0].blockers
    assert store_paths.state_db.read_bytes() == before


def test_sql_type_drift_is_rejected_before_identity_or_clock_acceptance(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET available_at_utc = ? WHERE snapshot_id = ?',
        (sqlite3.Binary(b"42"), result.snapshot_id),
    )

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_sql_type_invalid:available_at_utc",
    ):
        _list(service, binding)


def test_text_clock_without_timezone_is_retained_as_blocked(tmp_path, monkeypatch):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET available_at_utc = ? WHERE snapshot_id = ?',
        ("2026-08-02T08:30:00", result.snapshot_id),
    )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 1
    assert catalogue.rows[0].row_state == "blocked"
    assert "availability_clock_invalid_or_timezone_unknown" in catalogue.rows[0].blockers
    assert store_paths.state_db.read_bytes() == before


def test_oversized_identity_is_rejected_without_truncation(tmp_path, monkeypatch):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    _write_state(
        store_paths.state_db,
        f'UPDATE "{_TABLE}" SET snapshot_id = ? WHERE snapshot_id = ?',
        ("s" * 513, result.snapshot_id),
    )

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_catalogue_text_size_invalid:snapshot_id",
    ):
        _list(service, binding)


def test_201_rows_are_stably_bounded_and_never_qualified(tmp_path, monkeypatch):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    columns = (
        "schema_version, snapshot_id, operation_id, portfolio_id, account_namespace, "
        "binding_sha256, snapshot_sha256, base_receipt_sha256, persisted_at_utc, "
        "available_at_utc, receipt_json, receipt_sha256"
    )
    with closing(sqlite3.connect(store_paths.state_db)) as connection:
        with connection:
            source = connection.execute(
                f'SELECT {columns} FROM "{_TABLE}" WHERE snapshot_id = ?',
                (result.snapshot_id,),
            ).fetchone()
            assert source is not None
            for index in range(1, 201):
                clone = list(source)
                clone[1] = f"0-catalogue-snapshot-{index:03d}"
                clone[2] = f"catalogue-operation-{index:03d}"
                connection.execute(
                    f'INSERT INTO "{_TABLE}" ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    tuple(clone),
                )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 200
    assert catalogue.truncated is True
    assert catalogue.complete is False
    assert [row.snapshot_id for row in catalogue.rows] == sorted(
        row.snapshot_id for row in catalogue.rows
    )
    assert all(row.row_state == "candidate_pending_exact_reader" for row in catalogue.rows)
    assert all(row.exact_reader_required for row in catalogue.rows)
    assert all(row.checkpoint_verified is False for row in catalogue.rows)
    assert all(row.performance_eligible is False for row in catalogue.rows)
    assert store_paths.state_db.read_bytes() == before
    selected_clone = catalogue.rows[0]
    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="checkpoint_read_operation_missing",
    ):
        read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            operation_id=selected_clone.operation_id,
            snapshot_id=selected_clone.snapshot_id,
            decision_cutoff=catalogue.decision_cutoff,
        )

def test_other_portfolio_and_namespace_rows_do_not_contaminate_exact_catalogue(
    tmp_path, monkeypatch
):
    service, _, store_paths, binding, result = _real_checkpoint(tmp_path, monkeypatch)
    columns = (
        "schema_version, snapshot_id, operation_id, portfolio_id, account_namespace, "
        "binding_sha256, snapshot_sha256, base_receipt_sha256, persisted_at_utc, "
        "available_at_utc, receipt_json, receipt_sha256"
    )
    with closing(sqlite3.connect(store_paths.state_db)) as connection:
        with connection:
            source = connection.execute(
                f'SELECT {columns} FROM "{_TABLE}" WHERE snapshot_id = ?',
                (result.snapshot_id,),
            ).fetchone()
            assert source is not None
            foreign_scopes = (
                ("catalogue-foreign-portfolio", binding.account_namespace),
                (binding.portfolio_id, "catalogue-foreign-namespace"),
            )
            for index, (portfolio_id, account_namespace) in enumerate(foreign_scopes, start=1):
                clone = list(source)
                clone[1] = f"catalogue-foreign-snapshot-{index}"
                clone[2] = f"catalogue-foreign-operation-{index}"
                clone[3] = portfolio_id
                clone[4] = account_namespace
                connection.execute(
                    f'INSERT INTO "{_TABLE}" ({columns}) '
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(clone),
                )
    before = store_paths.state_db.read_bytes()

    catalogue = _list(service, binding)

    assert len(catalogue.rows) == 1
    candidate = catalogue.rows[0]
    assert candidate.operation_id == result.operation_id
    assert candidate.snapshot_id == result.snapshot_id
    assert candidate.observed_portfolio_id == binding.portfolio_id
    assert candidate.observed_account_namespace == binding.account_namespace
    assert candidate.observed_binding_sha256 == binding.binding_sha256
    assert candidate.row_state == "candidate_pending_exact_reader"
    assert catalogue.truncated is False
    assert catalogue.complete is True
    assert store_paths.state_db.read_bytes() == before