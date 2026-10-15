"""Registry 歷史績效卡的唯讀投影；不計算績效、不寫回 Registry。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
import math
import re
import sqlite3
from typing import Callable

import pandas as pd

from app_module.research_history_lookup import (
    REGISTRY_RESULT_TYPES,
    ResearchHistoryEntry,
    ResearchHistoryLookup,
    ResearchHistoryReadBudget,
    ResearchHistoryResult,
    ResearchHistoryUnavailable,
)
from app_module.research_run_dtos import (
    canonical_json,
    normalize_research_run_json_value,
)
from app_module.research_run_repository import ResearchRunRepositoryError
from app_module.research_run_service import (
    ResearchRunData,
    ResearchRunServiceError,
)
from app_module.saved_strategy_rule_card import metadata_sha256
from app_module.single_backtest_metrics_contract import decode_single_backtest_metrics_contract, validate_single_backtest_metrics_tables


ARTIFACT_BUDGET_BYTES = 64 * 1024 * 1024
TOTAL_BUDGET_BYTES = 256 * 1024 * 1024
MAX_METADATA_DETAIL_BYTES = 64 * 1024
MAX_PREVIEW_ROWS = 20
MAX_PREVIEW_COLUMNS = 32
MAX_CELL_TEXT = 512


class HistoricalReadState(str, Enum):
    VERIFIED = "read_verified"
    BLOCKED = "blocked"


class HistoricalMetricsState(str, Enum):
    NOT_READ = "not_read"
    UNVERSIONED = "metrics_unversioned"
    DECLARED = "saved_metrics_schema_observed"


class HistoricalComparabilityState(str, Enum):
    NOT_ASSESSED = "not_assessed"


class HistoricalQualificationState(str, Enum):
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HistoricalRunIdentity:
    source_kind: str
    run_type: str
    run_id: str
    run_name: str
    strategy_id: str
    strategy_version: str
    universe: tuple[str, ...] | None
    universe_json: str
    start_date: str
    end_date: str
    data_cutoff_date: str
    data_fingerprint: str
    fingerprint_algorithm: str
    capital_cents: int
    fee_bp_x100: int
    slippage_bp_x100: int
    stop_loss_bp: int | None
    take_profit_bp: int | None
    execution_price: str
    execution_contract: str
    sizing_mode: str


@dataclass(frozen=True, slots=True)
class HistoricalRunProvenance:
    source_kind: str
    metadata_sha256: str
    context_sha256: str
    payload_hash: str
    equity_parquet_sha256: str
    trades_parquet_sha256: str
    integrity_state: str


@dataclass(frozen=True, slots=True)
class HistoricalPerformanceSummary:
    stock_count: int | None = None
    signal_count: int | None = None
    completed_trades: int | None = None
    average_trade_return: Decimal | None = None
    total_return: Decimal | None = None
    annual_return: Decimal | None = None
    cagr: Decimal | None = None
    max_drawdown: Decimal | None = None
    win_rate: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    expectancy: Decimal | None = None
    profit_factor: Decimal | None = None


@dataclass(frozen=True, slots=True)
class HistoricalTableReference:
    artifact_name: str
    artifact_sha256: str
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    preview_rows: tuple[tuple[str, ...], ...]
    rows_truncated: bool
    columns_truncated: bool
    column_text_truncated: bool
    cell_text_truncated: bool


@dataclass(frozen=True, slots=True)
class HistoricalRunDetails:
    metadata_json: str | None
    metadata_json_sha256: str
    metadata_json_byte_length: int
    metadata_json_state: str
    equity: HistoricalTableReference
    trades: HistoricalTableReference


@dataclass(frozen=True, slots=True)
class HistoricalRunCard:
    read_state: HistoricalReadState
    metrics_state: HistoricalMetricsState
    metrics_reason: str
    comparability_state: HistoricalComparabilityState
    qualification_state: HistoricalQualificationState
    summary: HistoricalPerformanceSummary
    identity: HistoricalRunIdentity | None
    provenance: HistoricalRunProvenance | None
    details: HistoricalRunDetails | None
    reason: str | None


def _sha256_text(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _artifact_sha256_text(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _contains_non_finite_number(value: object) -> bool:
    # 遞迴檢查整個 metadata tree，不把 Decimal 或大整數轉成 float。
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Decimal):
        return not value.is_finite()
    if isinstance(value, dict):
        return any(
            _contains_non_finite_number(key) or _contains_non_finite_number(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite_number(item) for item in value)
    return False


def _summary_without_schema() -> HistoricalPerformanceSummary:
    # 舊 metrics 欄位沒有共用 schema；不從名稱或 equity/trades 猜績效。
    return HistoricalPerformanceSummary()


def _blocked(reason: str) -> HistoricalRunCard:
    return HistoricalRunCard(
        read_state=HistoricalReadState.BLOCKED,
        metrics_state=HistoricalMetricsState.NOT_READ,
        metrics_reason="source_not_verified",
        comparability_state=HistoricalComparabilityState.NOT_ASSESSED,
        qualification_state=HistoricalQualificationState.UNKNOWN,
        summary=_summary_without_schema(),
        identity=None,
        provenance=None,
        details=None,
        reason=reason,
    )


def _failure_reason(exc: Exception) -> str:
    message = str(exc)
    if "read_cancelled" in message:
        return "read_cancelled"
    if "selected_source_changed" in message:
        return "selected_source_changed"
    if isinstance(exc, ResearchHistoryUnavailable):
        return "registry_read_rejected"
    if isinstance(exc, ResearchRunServiceError):
        return "registry_integrity_rejected"
    if isinstance(exc, (ResearchRunRepositoryError, sqlite3.Error)):
        return "registry_read_rejected"
    if isinstance(exc, OSError):
        return "registry_artifact_unavailable"
    return "registry_read_rejected"


def _identity(entry: ResearchHistoryEntry, data: ResearchRunData) -> HistoricalRunIdentity:
    metadata = data.metadata
    universe_json = canonical_json(normalize_research_run_json_value(metadata.universe))
    universe = (
        tuple(metadata.universe)
        if all(isinstance(item, str) for item in metadata.universe)
        else None
    )
    return HistoricalRunIdentity(
        source_kind=entry.source_kind,
        run_type=metadata.run_type,
        run_id=metadata.run_id,
        run_name=metadata.run_name,
        strategy_id=metadata.strategy_id,
        strategy_version=metadata.strategy_version,
        universe=universe,
        universe_json=universe_json,
        start_date=metadata.start_date,
        end_date=metadata.end_date,
        data_cutoff_date=metadata.data_cutoff_date,
        data_fingerprint=metadata.data_fingerprint,
        fingerprint_algorithm=metadata.fingerprint_algorithm,
        capital_cents=metadata.capital_cents,
        fee_bp_x100=metadata.fee_bp_x100,
        slippage_bp_x100=metadata.slippage_bp_x100,
        stop_loss_bp=metadata.stop_loss_bp,
        take_profit_bp=metadata.take_profit_bp,
        execution_price=metadata.execution_price,
        execution_contract=metadata.execution_contract,
        sizing_mode=metadata.sizing_mode,
    )


def _table_reference(
    artifact_name: str,
    artifact_sha256: str,
    frame: pd.DataFrame,
) -> HistoricalTableReference:
    # 先切出預覽視窗，再轉欄名或建立 row iterator，避免掃描完整寬表。
    preview_frame = frame.iloc[:MAX_PREVIEW_ROWS, :MAX_PREVIEW_COLUMNS]
    columns_list: list[str] = []
    column_text_truncated = False
    for column in preview_frame.columns:
        text = str(column)
        if len(text) > MAX_CELL_TEXT:
            text = text[: MAX_CELL_TEXT - 1] + "…"
            column_text_truncated = True
        columns_list.append(text)
    columns = tuple(columns_list)
    preview: list[tuple[str, ...]] = []
    cell_text_truncated = False
    for row in preview_frame.itertuples(index=False, name=None):
        cells: list[str] = []
        for value in row[:MAX_PREVIEW_COLUMNS]:
            text = str(value)
            if len(text) > MAX_CELL_TEXT:
                text = text[: MAX_CELL_TEXT - 1] + "…"
                cell_text_truncated = True
            cells.append(text)
        preview.append(tuple(cells))
    row_count = len(frame)
    return HistoricalTableReference(
        artifact_name=artifact_name,
        artifact_sha256=artifact_sha256,
        row_count=row_count,
        column_count=len(frame.columns),
        columns=columns,
        preview_rows=tuple(preview),
        rows_truncated=row_count > MAX_PREVIEW_ROWS,
        columns_truncated=len(frame.columns) > MAX_PREVIEW_COLUMNS,
        column_text_truncated=column_text_truncated,
        cell_text_truncated=cell_text_truncated,
    )


def _details(entry: ResearchHistoryEntry, data: ResearchRunData) -> HistoricalRunDetails:
    metadata_bytes = entry.metadata_json.encode("utf-8")
    if len(metadata_bytes) <= MAX_METADATA_DETAIL_BYTES:
        metadata_text = entry.metadata_json
        metadata_state = "available_exact_saved_metadata"
    else:
        metadata_text = None
        metadata_state = "omitted_above_display_bound"
    metadata = data.metadata
    return HistoricalRunDetails(
        metadata_json=metadata_text,
        metadata_json_sha256=entry.metadata_sha256,
        metadata_json_byte_length=len(metadata_bytes),
        metadata_json_state=metadata_state,
        equity=_table_reference(
            "equity",
            metadata.equity_parquet_hash,
            data.equity,
        ),
        trades=_table_reference(
            "trades",
            metadata.trades_parquet_hash,
            data.trades,
        ),
    )


class StrategyHistoricalPerformanceReadService:
    """只解析 caller 選定的 Registry entry；不列 latest、不寫回或算績效。"""

    def __init__(self, history_lookup: ResearchHistoryLookup):
        if not isinstance(history_lookup, ResearchHistoryLookup):
            raise TypeError("history_lookup 必須是既有 ResearchHistoryLookup")
        self._history_lookup = history_lookup

    def read_selected(
        self,
        selected: ResearchHistoryEntry,
        *,
        check_cancel: Callable[[], bool] | None = None,
    ) -> HistoricalRunCard:
        if not isinstance(selected, ResearchHistoryEntry):
            return _blocked("selected_entry_invalid")
        if selected.source_kind != "registry":
            return _blocked("source_kind_unsupported")
        if (
            selected.run_type not in REGISTRY_RESULT_TYPES
            or selected.result_supported is not True
        ):
            return _blocked("unsupported_registry_run_type")
        if not selected.run_id or not _sha256_text(selected.metadata_sha256):
            return _blocked("selected_identity_or_hash_invalid")
        if not _sha256_text(selected.context_sha256):
            return _blocked("selected_context_hash_invalid")
        if check_cancel is not None and check_cancel():
            return _blocked("read_cancelled")

        try:
            resolved = self._history_lookup.resolve(
                selected,
                read_budget=ResearchHistoryReadBudget(
                    max_artifact_bytes=ARTIFACT_BUDGET_BYTES,
                    max_total_bytes=TOTAL_BUDGET_BYTES,
                ),
                check_cancel=check_cancel,
            )
            if check_cancel is not None and check_cancel():
                return _blocked("read_cancelled")
            if not isinstance(resolved, ResearchHistoryResult) or resolved.entry != selected:
                return _blocked("selected_entry_changed")
            if not isinstance(resolved.result, ResearchRunData):
                return _blocked("registry_result_type_changed")
            data = resolved.result
            metadata = data.metadata
            metadata_tree = asdict(metadata)
            if _contains_non_finite_number(metadata_tree):
                return _blocked("metadata_non_finite_numeric")
            snapshot_json = canonical_json(
                normalize_research_run_json_value(metadata_tree)
            )
            if (
                metadata.run_id != selected.run_id
                or metadata.run_type != selected.run_type
                or snapshot_json != selected.metadata_json
                or metadata_sha256(metadata) != selected.metadata_sha256
            ):
                return _blocked("selected_metadata_or_hash_changed")
            if (
                not _artifact_sha256_text(metadata.equity_parquet_hash)
                or not _artifact_sha256_text(metadata.trades_parquet_hash)
            ):
                return _blocked("saved_artifact_hash_invalid")
            if check_cancel is not None and check_cancel():
                return _blocked("read_cancelled")

            detail = _details(selected, data)
            if check_cancel is not None and check_cancel():
                return _blocked("read_cancelled")
            provenance = HistoricalRunProvenance(
                source_kind=selected.source_kind,
                metadata_sha256=selected.metadata_sha256,
                context_sha256=selected.context_sha256,
                payload_hash=metadata.payload_hash,
                equity_parquet_sha256=metadata.equity_parquet_hash,
                trades_parquet_sha256=metadata.trades_parquet_hash,
                integrity_state="verified_by_exact_registry_read",
            )
            summary_values = decode_single_backtest_metrics_contract(
                metadata.data_manifest, metadata.metrics, run_type=metadata.run_type, universe=metadata.universe,
            )
            if summary_values is not None:
                validate_single_backtest_metrics_tables(metadata.data_manifest, equity=data.equity, trades=data.trades)
            return HistoricalRunCard(
                read_state=HistoricalReadState.VERIFIED,
                metrics_state=HistoricalMetricsState.UNVERSIONED if summary_values is None else HistoricalMetricsState.DECLARED,
                metrics_reason=("historical_metrics_schema_unversioned" if summary_values is None
                                else "saved_original_analytics_not_performance_qualification"),
                comparability_state=HistoricalComparabilityState.NOT_ASSESSED,
                qualification_state=HistoricalQualificationState.UNKNOWN,
                summary=_summary_without_schema() if summary_values is None else HistoricalPerformanceSummary(**summary_values),
                identity=_identity(selected, data),
                provenance=provenance,
                details=detail,
                reason=None,
            )
        except (
            ResearchHistoryUnavailable,
            ResearchRunServiceError,
            ResearchRunRepositoryError,
            sqlite3.Error,
            OSError,
            ValueError,
            TypeError,
        ) as exc:
            return _blocked(_failure_reason(exc))
