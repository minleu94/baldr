"""歷史卡 Widget 的隔離 DTO 呈現測試；不呼叫 Registry 或 reader。"""

from __future__ import annotations

import json
import hashlib
import os
from dataclasses import replace
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app_module.research_history_lookup import ResearchHistoryEntry
from app_module.strategy_historical_performance_read_service import (
    HistoricalComparabilityState,
    HistoricalMetricsState,
    HistoricalPerformanceSummary,
    HistoricalQualificationState,
    HistoricalReadState,
    HistoricalRunCard,
    HistoricalRunDetails,
    HistoricalRunIdentity,
    HistoricalRunProvenance,
    HistoricalTableReference,
)
from ui_qt.widgets.historical_performance_widget import HistoricalPerformanceWidget


_PAYLOAD_HASH = "sha256:p08b-fixture-payload"
_CONTEXT_SHA = "b" * 64
_EQUITY_SHA = "sha256:" + "c" * 64
_TRADES_SHA = "sha256:" + "d" * 64
_METADATA_LIMIT = 64 * 1024


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _entry(
    *,
    run_id: str = "run-p08b-01",
    run_name: str = "歷史結果 A",
    stock_code: str = "2330",
    payload_hash: str = _PAYLOAD_HASH,
    padding: str = "",
    execution_price: str = "close",
    execution_contract: str | None = "close-to-close",
    universe: tuple[str, ...] | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> ResearchHistoryEntry:
    data_manifest = {
        "source_label": "isolated-widget-fixture",
        "fixture_padding": padding,
    }
    if execution_contract is not None:
        data_manifest["execution_contract"] = execution_contract
    metadata = {
        "run_id": run_id,
        "run_name": run_name,
        "run_type": "single_backtest",
        "strategy_id": "strategy-p08b",
        "strategy_version": "version-1",
        "parameter_contract_version": "parameters.v1",
        "original_input": {},
        "normalized_params": {"entry": "fixture"},
        "fallback_reason": {},
        "universe": list(universe) if universe is not None else [stock_code],
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "data_cutoff_date": "2026-01-31",
        "data_fingerprint": "saved-fingerprint",
        "fingerprint_algorithm": "sha256",
        "data_manifest": data_manifest,
        "capital_cents": 10000000,
        "fee_bp_x100": 15,
        "slippage_bp_x100": 0,
        "stop_loss_bp": None,
        "take_profit_bp": None,
        "execution_price": execution_price,
        "sizing_mode": "all-in",
        "metrics": {},
        "regime_breakdown": {},
        "benchmark_results": {},
        "payload_hash": payload_hash,
        "equity_path": "isolated/equity.parquet",
        "equity_parquet_hash": _EQUITY_SHA,
        "trades_path": "isolated/trades.parquet",
        "trades_parquet_hash": _TRADES_SHA,
        "is_archived": False,
        "promoted_version_id": None,
        "promotion_reconciliation_status": "none",
        "created_at": "2026-02-01T00:00:00+00:00",
    }
    if metadata_overrides is not None:
        metadata.update(metadata_overrides)
    metadata_json = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    metadata_sha = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
    selected_universe = metadata["universe"]
    assert type(selected_universe) is list
    return ResearchHistoryEntry(
        source_kind="registry",
        run_type=metadata["run_type"],
        run_id=metadata["run_id"],
        run_name=metadata["run_name"],
        stock_code=selected_universe[0] if len(selected_universe) == 1 else "",
        start_date=metadata["start_date"],
        end_date=metadata["end_date"],
        created_at=metadata["created_at"],
        metadata_sha256=metadata_sha,
        context_sha256=_CONTEXT_SHA,
        metadata_json=metadata_json,
        result_supported=True,
        unsupported_reason="",
    )


def _table(
    artifact_name: str,
    artifact_sha256: str,
    *,
    row_count: int = 2,
    column_count: int = 2,
    columns: tuple[str, ...] = ("date", "value"),
    preview_rows: tuple[tuple[str, ...], ...] = (
        ("2026-01-02", "100"),
        ("2026-01-05", "101"),
    ),
    rows_truncated: bool = False,
    columns_truncated: bool = False,
    column_text_truncated: bool = False,
    cell_text_truncated: bool = False,
) -> HistoricalTableReference:
    return HistoricalTableReference(
        artifact_name=artifact_name,
        artifact_sha256=artifact_sha256,
        row_count=row_count,
        column_count=column_count,
        columns=columns,
        preview_rows=preview_rows,
        rows_truncated=rows_truncated,
        columns_truncated=columns_truncated,
        column_text_truncated=column_text_truncated,
        cell_text_truncated=cell_text_truncated,
    )


def _card(
    entry: ResearchHistoryEntry,
    *,
    equity: HistoricalTableReference | None = None,
    trades: HistoricalTableReference | None = None,
    cell_text: str = "101",
) -> HistoricalRunCard:
    metadata_bytes = entry.metadata_json.encode("utf-8")
    metadata_visible = len(metadata_bytes) <= _METADATA_LIMIT
    metadata = json.loads(entry.metadata_json)
    universe = metadata["universe"]
    universe_tuple = tuple(universe) if all(type(value) is str for value in universe) else None
    universe_json = json.dumps(
        universe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest = metadata["data_manifest"]
    declared_contract = manifest.get("execution_contract")
    execution_price = metadata["execution_price"]
    execution_contract = (
        str(declared_contract)
        if declared_contract
        else execution_price if ".v" in execution_price else "unversioned"
    )
    equity_table = equity or _table(
        "equity",
        metadata["equity_parquet_hash"],
        preview_rows=(("2026-01-02", "100"), ("2026-01-05", cell_text)),
    )
    trades_table = trades or _table("trades", metadata["trades_parquet_hash"])
    return HistoricalRunCard(
        read_state=HistoricalReadState.VERIFIED,
        metrics_state=HistoricalMetricsState.UNVERSIONED,
        metrics_reason="historical_metrics_schema_unversioned",
        comparability_state=HistoricalComparabilityState.NOT_ASSESSED,
        qualification_state=HistoricalQualificationState.UNKNOWN,
        summary=HistoricalPerformanceSummary(),
        identity=HistoricalRunIdentity(
            source_kind=entry.source_kind,
            run_type=entry.run_type,
            run_id=entry.run_id,
            run_name=entry.run_name,
            strategy_id=metadata["strategy_id"],
            strategy_version=metadata["strategy_version"],
            universe=universe_tuple,
            universe_json=universe_json,
            start_date=metadata["start_date"],
            end_date=metadata["end_date"],
            data_cutoff_date=metadata["data_cutoff_date"],
            data_fingerprint=metadata["data_fingerprint"],
            fingerprint_algorithm=metadata["fingerprint_algorithm"],
            capital_cents=metadata["capital_cents"],
            fee_bp_x100=metadata["fee_bp_x100"],
            slippage_bp_x100=metadata["slippage_bp_x100"],
            stop_loss_bp=metadata["stop_loss_bp"],
            take_profit_bp=metadata["take_profit_bp"],
            execution_price=execution_price,
            execution_contract=execution_contract,
            sizing_mode=metadata["sizing_mode"],
        ),
        provenance=HistoricalRunProvenance(
            source_kind=entry.source_kind,
            metadata_sha256=entry.metadata_sha256,
            context_sha256=entry.context_sha256,
            payload_hash=metadata["payload_hash"],
            equity_parquet_sha256=metadata["equity_parquet_hash"],
            trades_parquet_sha256=metadata["trades_parquet_hash"],
            integrity_state="verified_by_exact_registry_read",
        ),
        details=HistoricalRunDetails(
            metadata_json=entry.metadata_json if metadata_visible else None,
            metadata_json_sha256=entry.metadata_sha256,
            metadata_json_byte_length=len(metadata_bytes),
            metadata_json_state=(
                "available_exact_saved_metadata"
                if metadata_visible
                else "omitted_above_display_bound"
            ),
            equity=equity_table,
            trades=trades_table,
        ),
        reason=None,
    )


def _texts(widget: HistoricalPerformanceWidget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_selection_change_and_clear_reject_late_generation(app: QApplication):
    widget = HistoricalPerformanceWidget()
    first = _entry(run_id="run-first")
    first_generation = widget.begin_selection(first)
    assert widget.present_card(first_generation, first, _card(first)) is True
    assert "run-first" in _texts(widget)

    second = _entry(run_id="run-second")
    second_generation = widget.begin_selection(second)
    assert second_generation > first_generation
    assert "run-first" not in _texts(widget)
    assert widget.present_card(first_generation, first, _card(first)) is False
    assert "run-first" not in _texts(widget)
    assert "run-second" in _texts(widget)

    cleared_generation = widget.clear_selection()
    assert cleared_generation > second_generation
    assert widget.present_card(second_generation, second, _card(second)) is False
    assert widget._identity_label.text() == ""
    assert widget._details_label.text() == ""


def test_valid_card_renders_opaque_payload_and_plain_text(app: QApplication):
    entry = _entry(run_name="<b>保存結果</b>")
    card = _card(entry, cell_text="<img src=x onerror=1>")
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, card) is True
    rendered = _texts(widget)
    assert "<b>保存結果</b>" in rendered
    assert "<img src=x onerror=1>" in rendered
    assert _PAYLOAD_HASH in rendered
    assert "10000000 分" in rendered
    assert "15 bp×100" in rendered
    assert "historical_metrics_schema_unversioned" in rendered
    for label in (
        "股票數",
        "訊號數",
        "已完成交易",
        "平均單筆報酬",
        "總報酬",
        "年化報酬",
        "CAGR",
        "最大回撤",
        "勝率",
        "Sharpe",
        "期望值",
        "獲利因子",
    ):
        assert f"{label}：未提供" in rendered
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in widget.findChildren(QLabel))


def test_full_selected_entry_equality_is_required(app: QApplication):
    entry = _entry()
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    changed_entries = (
        replace(entry, source_kind="legacy"),
        replace(entry, run_type="batch_backtest_stock"),
        replace(entry, run_id="run-other"),
        replace(entry, run_name="other name"),
        replace(entry, stock_code="2317"),
        replace(entry, start_date="2026-01-02"),
        replace(entry, end_date="2026-01-30"),
        replace(entry, created_at="2026-02-02T00:00:00+00:00"),
        replace(entry, metadata_sha256="e" * 64),
        replace(entry, context_sha256="f" * 64),
        replace(entry, metadata_json=entry.metadata_json + " "),
        replace(entry, result_supported=False),
        replace(entry, unsupported_reason="changed"),
    )
    for changed_entry in changed_entries:
        assert widget.present_card(generation, changed_entry, _card(entry)) is False
        assert widget._identity_label.text() == ""
        assert "selected_entry_changed" in widget._status_label.text()

    card = _card(entry)
    changed_identity = replace(card.identity, run_name="other name")
    assert widget.present_card(generation, entry, replace(card, identity=changed_identity)) is False
    assert widget._identity_label.text() == ""
    for field_name, value in (
        ("metadata_sha256", "e" * 64),
        ("context_sha256", "f" * 64),
        ("equity_parquet_sha256", "e" * 64),
        ("trades_parquet_sha256", "f" * 64),
        ("integrity_state", "unverified"),
    ):
        altered_provenance = replace(card.provenance, **{field_name: value})
        assert widget.present_card(generation, entry, replace(card, provenance=altered_provenance)) is False
        assert widget._details_label.text() == ""


def test_current_blocked_card_clears_existing_identity_and_details(app: QApplication):
    entry = _entry()
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    assert widget.present_card(generation, entry, _card(entry)) is True
    blocked_with_residue = replace(_card(entry), read_state=HistoricalReadState.BLOCKED, reason="registry_read_rejected")

    assert widget.present_card(generation, entry, blocked_with_residue) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert "registry_read_rejected" in widget._status_label.text()


def test_payload_hash_is_opaque_but_must_match_selected_metadata(app: QApplication):
    entry = _entry(payload_hash="sha256:p08b-fixture-payload")
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    card = _card(entry)
    assert widget.present_card(generation, entry, card) is True
    assert "sha256:p08b-fixture-payload" in _texts(widget)

    widget.begin_selection(entry)
    wrong_payload = replace(
        _card(entry),
        provenance=replace(_card(entry).provenance, payload_hash="sha256:other-run"),
    )
    assert widget.present_card(widget.generation, entry, wrong_payload) is False
    assert widget._identity_label.text() == ""
    assert "historical_payload_hash_not_bound_to_selected_metadata" in widget._status_label.text()

    non_finite_json = entry.metadata_json.replace(
        '"source_label":"isolated-widget-fixture"',
        '"source_label":NaN',
    )
    non_finite_entry = replace(
        entry,
        metadata_json=non_finite_json,
        metadata_sha256=hashlib.sha256(non_finite_json.encode("utf-8")).hexdigest(),
    )
    generation = widget.begin_selection(non_finite_entry)
    assert widget.present_card(generation, non_finite_entry, _card(non_finite_entry)) is False
    assert widget._details_label.text() == ""


def test_unversioned_summary_values_or_reason_are_rejected(app: QApplication):
    entry = _entry()
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    value_card = replace(
        _card(entry),
        summary=replace(HistoricalPerformanceSummary(), total_return=0),
    )
    assert widget.present_card(generation, entry, value_card) is False
    assert widget._identity_label.text() == ""

    generation = widget.begin_selection(entry)
    wrong_reason_card = replace(_card(entry), metrics_reason="metrics_unversioned")
    assert widget.present_card(generation, entry, wrong_reason_card) is False
    assert widget._metrics_label.text() == ""


def test_large_metadata_is_omitted_and_bounded_preview_flags_are_checked(app: QApplication):
    entry = _entry(padding="x" * _METADATA_LIMIT)
    columns = ("y" * 511 + "…",) + tuple(f"column-{index}" for index in range(1, 32))
    first_row = ("z" * 511 + "…",) + tuple(str(index) for index in range(1, 32))
    rows = (first_row,) + tuple(
        (f"row-{row_index}",) + tuple(str(column_index) for column_index in range(1, 32))
        for row_index in range(1, 20)
    )
    equity = _table(
        "equity",
        _EQUITY_SHA,
        row_count=21,
        column_count=33,
        columns=columns,
        preview_rows=rows,
        rows_truncated=True,
        columns_truncated=True,
        column_text_truncated=True,
        cell_text_truncated=True,
    )
    card = _card(entry, equity=equity)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, card) is True
    rendered = _texts(widget)
    assert "omitted_above_display_bound" in rendered
    assert str(len(entry.metadata_json.encode("utf-8"))) in rendered
    assert "原始列數 21，欄數 33" in rendered
    assert "欄名文字截斷 True" in rendered
    assert "儲存格文字截斷 True" in rendered
    assert "x" * 128 not in rendered
    assert len(equity.columns) == 32
    assert len(equity.preview_rows) == 20
    assert all(len(column) <= 512 for column in equity.columns)
    assert all(len(cell) <= 512 for row in equity.preview_rows for cell in row)


def test_truncation_flags_must_match_bounded_preview_shape(app: QApplication):
    entry = _entry()
    valid = _card(entry)
    invalid_equity = replace(valid.details.equity, cell_text_truncated=True)
    invalid_details = replace(valid.details, equity=invalid_equity)
    invalid_card = replace(valid, details=invalid_details)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, invalid_card) is False
    assert widget._details_label.text() == ""
    assert "historical_equity_preview_invalid" in widget._status_label.text()


def test_identity_fields_are_bound_to_selected_metadata(app: QApplication):
    entry = _entry()
    valid = _card(entry)
    changed_cards = (
        replace(valid, identity=replace(valid.identity, strategy_id="other-strategy")),
        replace(valid, identity=replace(valid.identity, strategy_version="version-2")),
        replace(valid, identity=replace(valid.identity, fee_bp_x100=16)),
        replace(valid, identity=replace(valid.identity, universe=("2317",))),
        replace(valid, identity=replace(valid.identity, universe_json='["2317"]')),
        replace(valid, identity=replace(valid.identity, execution_contract="other-contract")),
    )
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    for changed in changed_cards:
        assert widget.present_card(generation, entry, changed) is False
        assert widget._identity_label.text() == ""
        assert widget._metrics_label.text() == ""
        assert widget._details_label.text() == ""
        assert "historical_identity_not_bound_to_selected_metadata" in widget._status_label.text()


def test_artifact_hashes_cannot_be_replaced_with_matching_card_tables(app: QApplication):
    entry = _entry()
    card = _card(entry)
    changed_equity_sha = "sha256:" + "e" * 64
    changed_trades_sha = "sha256:" + "f" * 64
    changed_provenance = replace(
        card.provenance,
        equity_parquet_sha256=changed_equity_sha,
        trades_parquet_sha256=changed_trades_sha,
    )
    changed_details = replace(
        card.details,
        equity=replace(card.details.equity, artifact_sha256=changed_equity_sha),
        trades=replace(card.details.trades, artifact_sha256=changed_trades_sha),
    )
    changed_card = replace(card, provenance=changed_provenance, details=changed_details)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)

    assert widget.present_card(generation, entry, changed_card) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert "historical_artifact_hash_not_bound_to_selected_metadata" in widget._status_label.text()


def test_artifact_digest_requires_formal_prefix_and_metadata_hashes_remain_bare(app: QApplication):
    entry = _entry()
    card = _card(entry)
    assert len(entry.metadata_sha256) == 64
    assert len(entry.context_sha256) == 64
    assert not entry.metadata_sha256.startswith("sha256:")
    assert not entry.context_sha256.startswith("sha256:")
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    assert widget.present_card(generation, entry, card) is True
    assert _EQUITY_SHA == "sha256:" + "c" * 64
    assert _TRADES_SHA == "sha256:" + "d" * 64
    provenance = card.provenance
    details = card.details
    assert provenance is not None
    assert details is not None

    invalid_digests = ("c" * 64, "sha256:" + "C" * 64, "sha-256:" + "c" * 64)
    for attribute, table_attribute in (
        ("equity_parquet_sha256", "equity"),
        ("trades_parquet_sha256", "trades"),
    ):
        for invalid_digest in invalid_digests:
            generation = widget.begin_selection(entry)
            invalid_provenance = replace(
                provenance,
                **{attribute: invalid_digest},
            )
            invalid_table = replace(
                getattr(details, table_attribute),
                artifact_sha256=invalid_digest,
            )
            invalid_details = replace(
                details,
                **{table_attribute: invalid_table},
            )
            invalid_card = replace(
                card,
                provenance=invalid_provenance,
                details=invalid_details,
            )
            assert widget.present_card(generation, entry, invalid_card) is False
            assert widget._identity_label.text() == ""
            assert "historical_artifact_hash_invalid" in widget._status_label.text()


def test_verified_card_requires_a_supported_registry_entry(app: QApplication):
    selected = _entry()
    widget = HistoricalPerformanceWidget()

    for unsupported in (
        replace(selected, source_kind="legacy"),
        replace(selected, result_supported=False),
        replace(selected, run_type="research_forward"),
    ):
        generation = widget.begin_selection(unsupported)
        assert widget.present_card(generation, unsupported, _card(unsupported)) is False
        assert widget._identity_label.text() == ""
        assert widget._metrics_label.text() == ""
        assert widget._details_label.text() == ""
        assert "historical_entry_not_supported" in widget._status_label.text()


def test_metadata_hash_mismatch_and_duplicate_keys_are_rejected(app: QApplication):
    entry = _entry()
    widget = HistoricalPerformanceWidget()
    changed_metadata = replace(entry, metadata_json=entry.metadata_json + " ")
    generation = widget.begin_selection(changed_metadata)
    assert widget.present_card(generation, changed_metadata, _card(changed_metadata)) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert "historical_selected_metadata_invalid_or_hash_changed" in widget._status_label.text()

    noncanonical_json = entry.metadata_json + " "
    noncanonical_entry = replace(
        entry,
        metadata_json=noncanonical_json,
        metadata_sha256=hashlib.sha256(noncanonical_json.encode("utf-8")).hexdigest(),
    )
    generation = widget.begin_selection(noncanonical_entry)
    assert widget.present_card(generation, noncanonical_entry, _card(noncanonical_entry)) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert "historical_selected_metadata_invalid_or_hash_changed" in widget._status_label.text()

    duplicate_json = entry.metadata_json[:-1] + ',"run_id":"run-p08b-01"}'
    duplicate_entry = replace(
        entry,
        metadata_json=duplicate_json,
        metadata_sha256=hashlib.sha256(duplicate_json.encode("utf-8")).hexdigest(),
    )
    generation = widget.begin_selection(duplicate_entry)
    assert widget.present_card(generation, duplicate_entry, _card(duplicate_entry)) is False
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert "historical_selected_metadata_invalid_or_hash_changed" in widget._status_label.text()


def test_execution_contract_uses_metadata_property_precedence(app: QApplication):
    cases = (
        ("close", "declared.v3", "declared.v3"),
        ("close.v2", None, "close.v2"),
        ("close", None, "unversioned"),
        ("close.v2", "", "close.v2"),
    )
    widget = HistoricalPerformanceWidget()
    for execution_price, declared_contract, expected in cases:
        entry = _entry(
            execution_price=execution_price,
            execution_contract=declared_contract,
        )
        generation = widget.begin_selection(entry)
        card = _card(entry)
        assert card.identity.execution_contract == expected
        assert widget.present_card(generation, entry, card) is True
        assert expected in _texts(widget)


def test_large_valid_display_fields_are_bounded_without_mutating_selected_source(app: QApplication):
    long_value = "x" * 700
    selection_probe = _entry(
        run_id=long_value,
        run_name=long_value,
        metadata_overrides={"run_type": long_value},
    )
    probe_widget = HistoricalPerformanceWidget()
    probe_widget.begin_selection(selection_probe)
    probe_lines = probe_widget._selection_label.text().splitlines()
    assert all(len(line) <= 512 for line in probe_lines)
    for label in ("結果名稱：", "結果類型：", "Run ID："):
        line = next(item for item in probe_lines if item.startswith(label))
        assert len(line) == 512 and line.endswith("…")

    entry = _entry(
        run_id=long_value,
        run_name=long_value,
        payload_hash=long_value,
        execution_price=long_value,
        execution_contract=long_value,
        universe=("u" * 320, "v" * 320),
        metadata_overrides={
            "strategy_id": long_value,
            "strategy_version": long_value,
            "start_date": long_value,
            "end_date": long_value,
            "data_cutoff_date": long_value,
            "data_fingerprint": long_value,
            "fingerprint_algorithm": long_value,
            "capital_cents": 10**600,
            "fee_bp_x100": 10**600,
            "slippage_bp_x100": 10**600,
            "stop_loss_bp": 10**600,
            "take_profit_bp": 10**600,
            "sizing_mode": long_value,
            "created_at": long_value,
        },
    )
    source_before = (entry, entry.metadata_json, entry.metadata_sha256)
    assert len(entry.metadata_json.encode("utf-8")) < _METADATA_LIMIT
    widget = HistoricalPerformanceWidget()

    generation = widget.begin_selection(entry)
    selection_lines = widget._selection_label.text().splitlines()
    assert all(len(line) <= 512 for line in selection_lines)
    for label in ("結果名稱：", "Run ID："):
        line = next(item for item in selection_lines if item.startswith(label))
        assert len(line) == 512 and line.endswith("…")

    assert widget.present_card(generation, entry, _card(entry)) is True
    assert (entry, entry.metadata_json, entry.metadata_sha256) == source_before
    identity_lines = widget._identity_label.text().splitlines()
    assert all(len(line) <= 512 for line in identity_lines)
    for label in (
        "策略識別碼：",
        "策略版本：",
        "Run 名稱：",
        "Run ID：",
        "Universe JSON：",
        "資料指紋：",
        "指紋演算法：",
        "資料 cutoff：",
        "本金：",
        "手續費：",
        "滑價：",
        "停損：",
        "停利：",
        "成交價：",
        "成交契約：",
        "Sizing：",
    ):
        line = next(item for item in identity_lines if item.startswith(label))
        assert len(line) == 512 and line.endswith("…")
    details_text = widget._details_label.text()
    for label in ("Entry 建立時間：", "Payload hash（原字串）："):
        line = next(item for item in details_text.splitlines() if item.startswith(label))
        assert len(line) == 512 and line.endswith("…")
    assert f"原始 Metadata JSON（PlainText）：\n{entry.metadata_json}" in details_text
    assert entry.metadata_sha256 in details_text


def test_large_blocked_reason_is_bounded_and_clears_the_card(app: QApplication):
    entry = _entry()
    source_before = (entry, entry.metadata_json, entry.metadata_sha256)
    widget = HistoricalPerformanceWidget()
    generation = widget.begin_selection(entry)
    assert widget.present_card(generation, entry, _card(entry)) is True
    assert "停損：未提供" in widget._identity_label.text()
    assert "停利：未提供" in widget._identity_label.text()

    reason = "blocked-" + ("r" * 700)
    blocked_card = replace(
        _card(entry),
        read_state=HistoricalReadState.BLOCKED,
        reason=reason,
    )
    assert widget.present_card(generation, entry, blocked_card) is False
    assert (entry, entry.metadata_json, entry.metadata_sha256) == source_before
    assert widget._identity_label.text() == ""
    assert widget._metrics_label.text() == ""
    assert widget._details_label.text() == ""
    assert len(widget._status_label.text()) <= 512
    assert widget._status_label.text().endswith("…")

