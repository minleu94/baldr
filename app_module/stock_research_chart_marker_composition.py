"""中央選定原 JSONL 的有界唯讀 custody 與圖表 marker 組合。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any

from app_module.personal_data_paths import _absolute, to_internal_io_path
from app_module.stock_research_chart_marker_reader import (
    StockChartMarkerReadRequest, StockChartMarkerReadResult, StockChartMarkerRecordSource,
    StockResearchChartMarkerReader, stock_chart_saved_record_sha256,
)
from app_module.stock_research_report_dtos import StockResearchReportDTO
from app_module.stock_research_chart_markers import StockChartMarkerDTO, StockChartMarkerIdentityDTO


@dataclass(frozen=True)
class ChartMarkerSource:
    path: Path
    record_source: StockChartMarkerRecordSource
    guard: Callable[[Path], Path] | None = None


def _stamp(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino


def _read_original_rows(source: ChartMarkerSource, cancelled: Callable[[], bool]) -> tuple[Mapping[str, Any], ...]:
    """讀原保存 bytes 後才產 row pins；不開 writer、不 mkdir／lock。"""
    path = source.path
    def guarded() -> str:
        if cancelled():
            raise RuntimeError("cancelled")
        if source.guard is not None and source.guard(path) != path:
            raise ValueError("source_guard_path_mismatch")
        if _absolute(path) != path:
            raise ValueError("source_path_alias")
        return to_internal_io_path(path)
    io_path = guarded()
    try:
        before = os.stat(io_path, follow_symlinks=False)
    except FileNotFoundError:
        return ()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("source_alias_or_type")
    # UI reader resource budget, separate from saved-record capacity policy.
    if before.st_size > 16 * 1024 * 1024:
        raise ValueError("source_byte_budget_exceeded")
    chunks: list[bytes] = []
    total = 0
    with open(guarded(), "rb") as handle:
        if _stamp(os.fstat(handle.fileno())) != _stamp(before):
            raise ValueError("source_changed")
        while True:
            if cancelled():
                raise RuntimeError("cancelled")
            chunk = handle.read(min(64 * 1024, before.st_size - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > before.st_size:
                raise ValueError("source_changed")
            chunks.append(chunk)
        if total != before.st_size or _stamp(os.fstat(handle.fileno())) != _stamp(before):
            raise ValueError("source_changed")
    if _stamp(os.stat(guarded(), follow_symlinks=False)) != _stamp(before):
        raise ValueError("source_changed")
    lines = b"".join(chunks).splitlines()
    if len(lines) > 5000:
        raise ValueError("source_record_budget_exceeded")
    rows: list[Mapping[str, Any]] = []
    for line in lines:
        if cancelled():
            raise RuntimeError("cancelled")
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("source_record_invalid")
        rows.append(row)
    if _stamp(os.stat(guarded(), follow_symlinks=False)) != _stamp(before):
        raise ValueError("source_changed")
    return tuple(rows)


def compose_saved_chart_markers(
    report: StockResearchReportDTO, *, cutoff_date: str, account_id: str,
    expected_source_id: str, sources: tuple[ChartMarkerSource, ...],
    cancel_callback: Callable[[], bool] | None = None,
) -> StockChartMarkerReadResult:
    """trusted loaded context 選 source/account；原 row 不反向決定這些資格。"""
    cancelled = cancel_callback or (lambda: False)
    context = dict(report.research_context)
    required = ("stock_code", "result_id", "decision_date", "source_snapshot_id", "source_snapshot_hash")
    if (not account_id or not expected_source_id or any(not context.get(k) for k in required)
            or context["stock_code"] != report.stock_code
            or (context.get("source_id") and context["source_id"] != expected_source_id)):
        return StockChartMarkerReadResult(diagnostics=("selected_context_identity_missing_or_conflicting",))
    if len(sources) > 2 or len({s.record_source for s in sources}) != len(sources):
        return StockChartMarkerReadResult(diagnostics=("selected_sources_ambiguous",))
    candidates: list[StockChartMarkerDTO] = []
    identities: list[StockChartMarkerIdentityDTO] = []
    diagnostics: list[str] = []
    for source in sources:
        if cancelled():
            return StockChartMarkerReadResult(diagnostics=("cancelled",))
        try:
            rows = _read_original_rows(source, cancelled)
            key = "trade_id" if source.record_source is StockChartMarkerRecordSource.ACTUAL_TRADES else "revision_id"
            selected = tuple(row for row in rows if row.get("stock_code") == report.stock_code
                             and row.get("portfolio_id") == account_id
                             and row.get("source_id") == expected_source_id and isinstance(row.get(key), str))
            pins = tuple((str(row[key]), stock_chart_saved_record_sha256(row)) for row in selected)
            if len(pins) > 128:
                diagnostics.append(source.record_source.value + ":selected_record_pin_budget_exceeded")
                continue
            if not pins:
                diagnostics.append(source.record_source.value + ":saved_record_missing")
                continue
            request = StockChartMarkerReadRequest(source.record_source, report.stock_code, cutoff_date,
                account_id, expected_source_id, context["result_id"], context["decision_date"],
                context["source_snapshot_id"], context["source_snapshot_hash"], tuple(sorted(context.items())), pins)
            # Callback is a detached projection of the same guarded original bytes;
            # no second path read can replace the pinned rows during marker construction.
            reader = StockResearchChartMarkerReader(
                **{"trade_records" if key == "trade_id" else "confirmation_records": lambda: rows})
            result = reader.read(request, price_points=report.price_points, cancelled=cancelled)
            candidates.extend(result.candidates)
            identities.extend(result.identities)
            diagnostics.extend(result.diagnostics)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            diagnostics.append(source.record_source.value + ":" + str(exc))
    if cancelled():
        return StockChartMarkerReadResult(diagnostics=("cancelled",))
    return StockChartMarkerReadResult(tuple(candidates), tuple(identities), tuple(diagnostics))


class SelectedPortfolioTradeReadAdapter:
    """已選定 trades route 的每次唯讀來源守衛，維持原 Journey port。"""

    def __init__(self, source: ChartMarkerSource, *, account_id: str) -> None:
        if source.record_source is not StockChartMarkerRecordSource.ACTUAL_TRADES or not account_id:
            raise ValueError("selected_trade_identity_required")
        self.source = source
        self.path = source.path
        self.account_id = account_id

    def list_trades(self) -> tuple[Mapping[str, Any], ...]:
        rows = _read_original_rows(self.source, lambda: False)
        if any(row.get("portfolio_id") != self.account_id for row in rows):
            raise ValueError("trades_identity_mismatch")
        return rows


# Existing Journey projection/as-of semantics stay in the original adapter.
from app_module.decision_outcome_journey import JsonlJournalReadAdapter
from app_module.personal_journal_paths import PersonalJournalPaths, validate_personal_journal_record


class SelectedJournalReadAdapter(JsonlJournalReadAdapter):
    def __init__(self, source: ChartMarkerSource, *, journal_paths: PersonalJournalPaths,
                 legacy_read_only: bool) -> None:
        if source.record_source is not StockChartMarkerRecordSource.RECOMMENDATION_CONFIRMATIONS:
            raise ValueError("selected_journal_source_required")
        self.source = source
        self.path = source.path
        self.journal_paths = journal_paths
        self.legacy_read_only = legacy_read_only

    def _records(self) -> tuple[Mapping[str, Any], ...]:
        if self.journal_paths is None:
            raise ValueError("personal_journal_paths_required")
        self.journal_paths.assert_selected(self.path, legacy_read_only=self.legacy_read_only)
        rows = _read_original_rows(self.source, lambda: False)
        for row in rows:
            validate_personal_journal_record(row)
        return rows
