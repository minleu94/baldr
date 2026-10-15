"""以隔離的 Registry 真實保存與精確讀回驗證歷史卡；不使用 mocked reader。"""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

from app_module.research_history_lookup import (
    ResearchHistoryEntry,
    ResearchHistoryLookup,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO, canonical_json
from app_module.research_run_service import ResearchRunService
from app_module.strategy_historical_performance_read_service import (
    HistoricalComparabilityState,
    HistoricalMetricsState,
    HistoricalQualificationState,
    HistoricalReadState,
    StrategyHistoricalPerformanceReadService,
)
from data_module.config import TWStockConfig


_ARTIFACT_LIMIT = 64 * 1024 * 1024
_TOTAL_LIMIT = 256 * 1024 * 1024
_OLD_ZERO_METRICS = {
    "total_return": 0.0,
    "annual_return": 0.0,
    "max_drawdown": 0.0,
    "win_rate": 0.0,
    "total_trades": 0,
    "expectancy": 0.0,
    "profit_factor": 0.0,
}


def _saved_registry_case(
    tmp_path: Path,
    run_type: str = "single_backtest",
    *,
    metrics: dict | None = None,
    equity_override: pd.DataFrame | None = None,
):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )
    metadata = ResearchRunMetadataDTO(
        run_id="p08b-" + run_type,
        run_name="隔離歷史回測",
        run_type=run_type,
        strategy_id="breakout",
        strategy_version="v1",
        parameter_contract_version="params.v1",
        normalized_params={"entry": "breakout", "exit": "time_stop"},
        universe=["2330", "2317"],
        start_date="2026-01-02",
        end_date="2026-01-05",
        data_cutoff_date="2026-01-05",
        data_fingerprint="fixture-fingerprint",
        fingerprint_algorithm="fixture-sha256-v1",
        data_manifest={
            "run_status": "completed",
            "execution_contract": "next-session-open.v2",
            "source_label": "isolated-synthetic-fixture",
        },
        capital_cents=100000000,
        fee_bp_x100=1425,
        slippage_bp_x100=500,
        execution_price="next-session-open.v2",
        sizing_mode="fixed",
        metrics=dict(_OLD_ZERO_METRICS if metrics is None else metrics),
        payload_hash="sha256:p08b-fixture-payload",
        created_at="2026-10-13T12:00:00",
    )
    equity = equity_override if equity_override is not None else pd.DataFrame(
        {
            "日期": ["2026-01-02", "2026-01-05"],
            "portfolio_value": [100000000, 101000000],
        }
    )
    trades = pd.DataFrame(
        {
            "日期": ["2026-01-05"],
            "stock_code": ["2330"],
            "side": ["buy"],
            "quantity": [100],
        }
    )

    writer = ResearchRunService(config)
    saved = writer.save_run(metadata, equity, trades)
    del writer

    lookup = ResearchHistoryLookup(registry=ResearchRunService(config))
    page = lookup.list_entries(limit=100)
    entry = next(row for row in page.entries if row.run_id == saved.run_id)
    return config, saved, lookup, entry


def _inventory(root: Path) -> tuple[tuple[str, str, int], ...]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        raw = path.read_bytes()
        rows.append(
            (
                str(path.relative_to(root)),
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            )
        )
    return tuple(rows)


def _assert_blocked_and_empty(card) -> None:
    assert card.read_state is HistoricalReadState.BLOCKED
    assert card.metrics_state is HistoricalMetricsState.NOT_READ
    assert card.comparability_state is HistoricalComparabilityState.NOT_ASSESSED
    assert card.qualification_state is HistoricalQualificationState.UNKNOWN
    assert card.summary.stock_count is None
    assert card.summary.signal_count is None
    assert card.summary.total_return is None
    assert card.summary.annual_return is None
    assert card.summary.cagr is None
    assert card.summary.average_trade_return is None
    assert card.summary.max_drawdown is None
    assert card.summary.win_rate is None
    assert card.summary.completed_trades is None
    assert card.summary.sharpe_ratio is None
    assert card.summary.expectancy is None
    assert card.summary.profit_factor is None
    assert card.identity is None
    assert card.provenance is None
    assert card.details is None


def test_saved_registry_run_projects_identity_hashes_and_unversioned_zero_details(tmp_path):
    _, saved, lookup, entry = _saved_registry_case(tmp_path)
    before = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    assert card.read_state is HistoricalReadState.VERIFIED
    assert card.metrics_state is HistoricalMetricsState.UNVERSIONED
    assert card.metrics_reason == "historical_metrics_schema_unversioned"
    assert card.comparability_state is HistoricalComparabilityState.NOT_ASSESSED
    assert card.qualification_state is HistoricalQualificationState.UNKNOWN
    assert card.identity is not None
    assert card.identity.run_id == saved.run_id
    assert card.identity.run_type == "single_backtest"
    assert card.identity.strategy_id == "breakout"
    assert card.identity.strategy_version == "v1"
    assert card.identity.universe == ("2330", "2317")
    assert card.identity.start_date == "2026-01-02"
    assert card.identity.end_date == "2026-01-05"
    assert card.identity.data_cutoff_date == "2026-01-05"
    assert card.identity.capital_cents == 100000000
    assert card.identity.fee_bp_x100 == 1425
    assert card.identity.slippage_bp_x100 == 500
    assert card.identity.execution_contract == "next-session-open.v2"

    assert card.provenance is not None
    assert card.provenance.metadata_sha256 == entry.metadata_sha256
    assert card.provenance.context_sha256 == entry.context_sha256
    assert card.provenance.payload_hash == saved.payload_hash
    assert card.provenance.equity_parquet_sha256 == saved.equity_parquet_hash
    assert card.provenance.trades_parquet_sha256 == saved.trades_parquet_hash
    assert card.provenance.integrity_state == "verified_by_exact_registry_read"

    assert card.summary.stock_count is None
    assert card.summary.signal_count is None
    assert card.summary.completed_trades is None
    assert card.summary.average_trade_return is None
    assert card.summary.total_return is None
    assert card.summary.annual_return is None
    assert card.summary.cagr is None
    assert card.summary.max_drawdown is None
    assert card.summary.win_rate is None
    assert card.summary.sharpe_ratio is None
    assert card.summary.expectancy is None
    assert card.summary.profit_factor is None

    assert card.details is not None
    assert card.details.metadata_json_state == "available_exact_saved_metadata"
    assert card.details.metadata_json is not None
    saved_metadata = json.loads(card.details.metadata_json)
    assert saved_metadata["metrics"]["total_return"] == 0.0
    assert saved_metadata["metrics"]["total_trades"] == 0
    assert "metrics_schema" not in saved_metadata
    assert "schema_version" not in saved_metadata["metrics"]
    assert "historical_metrics_schema" not in saved_metadata["data_manifest"]
    assert card.details.equity.artifact_sha256 == saved.equity_parquet_hash
    assert card.details.trades.artifact_sha256 == saved.trades_parquet_hash
    assert card.details.equity.row_count == 2
    assert card.details.trades.row_count == 1
    assert card.details.equity.preview_rows[0][0] == "2026-01-02"
    assert card.details.trades.preview_rows[0][1] == "2330"
    assert _inventory(tmp_path) == before


def test_cancel_wrong_source_and_changed_selection_clear_previous_card(tmp_path):
    _, _, lookup, entry = _saved_registry_case(tmp_path)
    service = StrategyHistoricalPerformanceReadService(lookup)
    verified = service.read_selected(entry)
    assert verified.read_state is HistoricalReadState.VERIFIED
    before = _inventory(tmp_path)

    calls = 0

    def cancel_during_public_resolve() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    cancelled = service.read_selected(entry, check_cancel=cancel_during_public_resolve)
    _assert_blocked_and_empty(cancelled)
    assert cancelled.reason == "read_cancelled"
    assert calls >= 3

    wrong_source = service.read_selected(
        replace(entry, source_kind="legacy_backtest")
    )
    _assert_blocked_and_empty(wrong_source)
    assert wrong_source.reason == "source_kind_unsupported"

    changed_hash = service.read_selected(
        replace(entry, metadata_sha256="0" * 64)
    )
    _assert_blocked_and_empty(changed_hash)
    assert changed_hash.reason == "selected_source_changed"
    assert _inventory(tmp_path) == before


def test_unsupported_registry_result_type_is_not_opened_or_projected(tmp_path):
    _, _, lookup, entry = _saved_registry_case(
        tmp_path,
        run_type="research_forward",
    )
    before = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    _assert_blocked_and_empty(card)
    assert card.reason == "unsupported_registry_run_type"
    assert _inventory(tmp_path) == before


def test_tampered_saved_artifact_is_blocked_without_further_writes(tmp_path):
    _, saved, lookup, entry = _saved_registry_case(tmp_path)
    path = Path(saved.equity_path)
    with path.open("ab") as stream:
        stream.write(b"test-only-tamper")
    after_tamper = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    _assert_blocked_and_empty(card)
    assert card.reason == "registry_integrity_rejected"
    assert _inventory(tmp_path) == after_tamper


def test_non_finite_registry_metadata_is_blocked_without_projection(tmp_path):
    for index, value in enumerate((float("nan"), float("inf"), float("-inf"))):
        case_root = tmp_path / f"non-finite-{index}"
        metrics = dict(_OLD_ZERO_METRICS)
        metrics["total_return"] = value
        _, _, lookup, entry = _saved_registry_case(
            case_root,
            metrics=metrics,
        )
        before = _inventory(case_root)

        card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

        _assert_blocked_and_empty(card)
        assert card.reason == "metadata_non_finite_numeric"
        assert _inventory(case_root) == before


def test_registry_metadata_changed_after_selection_is_rejected(tmp_path):
    config, saved, lookup, entry = _saved_registry_case(tmp_path)
    with closing(sqlite3.connect(config.research_run_db_file)) as connection:
        with connection:
            row = connection.execute(
                "SELECT metrics_json FROM research_runs WHERE run_id = ?",
                (saved.run_id,),
            ).fetchone()
            assert row is not None
            original_metrics_json = row[0]
            changed_metrics = json.loads(original_metrics_json)
            changed_metrics["total_return"] = 0.125
            cursor = connection.execute(
                "UPDATE research_runs SET metrics_json = ? "
                "WHERE run_id = ? AND metrics_json = ?",
                (canonical_json(changed_metrics), saved.run_id, original_metrics_json),
            )
            assert cursor.rowcount == 1
    after_metadata_change = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    _assert_blocked_and_empty(card)
    assert card.reason == "selected_source_changed"
    assert _inventory(tmp_path) == after_metadata_change


def test_table_preview_slices_rows_columns_and_bounds_column_labels(tmp_path):
    long_column_name = "equity-" + ("x" * 520)
    long_cell_text = "cell-" + ("y" * 520)
    first_column_values = [long_cell_text, *[f"row-{index}" for index in range(1, 21)]]
    equity = pd.DataFrame(
        {
            long_column_name: first_column_values,
            **{f"column_{index}": list(range(21)) for index in range(1, 33)},
        }
    )
    _, _, lookup, entry = _saved_registry_case(
        tmp_path,
        equity_override=equity,
    )
    before = _inventory(tmp_path)

    card = StrategyHistoricalPerformanceReadService(lookup).read_selected(entry)

    assert card.read_state is HistoricalReadState.VERIFIED
    assert card.details is not None
    preview = card.details.equity
    assert preview.row_count == 21
    assert preview.column_count == 33
    assert len(preview.columns) == 32
    assert len(preview.preview_rows) == 20
    assert all(len(row) == 32 for row in preview.preview_rows)
    assert all(len(column) <= 512 for column in preview.columns)
    assert all(len(cell) <= 512 for row in preview.preview_rows for cell in row)
    assert len(preview.columns[0]) <= 512
    assert preview.columns[0].endswith("…")
    assert preview.rows_truncated is True
    assert preview.columns_truncated is True
    assert preview.column_text_truncated is True
    assert len(preview.preview_rows[0][0]) == 512
    assert preview.preview_rows[0][0].endswith("…")
    assert preview.cell_text_truncated is True
    assert _inventory(tmp_path) == before
