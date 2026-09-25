"""Source I/O and persistence for controlled P/E valuation backfill."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from data_module.backup_retention import (
    create_sqlite_retained_backup,
    restore_sqlite_backup,
)
from data_module.contracts.fundamental import (
    SourceDiagnostic,
    SourceDiagnosticKind,
    parse_legacy_quality_wire_value,
)
from data_module.contracts.valuation import (
    ValuationBackfillSourceRow,
    ValuationMetricRecord,
)


@dataclass(frozen=True)
class ValuationMetricsBackfillSourcePlan:
    records: tuple[ValuationBackfillSourceRow, ...]
    diagnostics: tuple[SourceDiagnostic, ...]
    source_row_count: int
    as_of_date: date | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True)
class ValuationMetricsBackfillApplyResult:
    applied: bool
    inserted_count: int
    backup_file: Path | None


def load_industry_by_stock_from_companies(companies_file: Path) -> dict[str, str]:
    """Load the existing companies.csv stock-to-latest-primary-industry mapping."""

    companies_file = Path(companies_file)
    if not companies_file.exists():
        return {}

    selected: dict[str, tuple[str, str, str]] = {}
    with companies_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stock_code = str(row.get("stock_id", "")).strip()
            industry = str(row.get("industry_category", "")).strip()
            if not stock_code or not industry:
                continue
            sort_key = (
                _companies_sort_date(row.get("date", "")),
                str(row.get("download_time", "")).strip(),
                industry,
            )
            if stock_code not in selected or sort_key > selected[stock_code]:
                selected[stock_code] = sort_key
    return {stock_code: industry for stock_code, (_, _, industry) in selected.items()}


def read_valuation_metrics_backfill_source(
    *,
    db_file: Path,
    as_of_date: str | date | None,
) -> ValuationMetricsBackfillSourcePlan:
    """Read P/E source rows; do not apply industry, percentile, or quality policy."""

    db_file = Path(db_file)
    try:
        target_date = _resolve_as_of_date(db_file, as_of_date)
        if target_date is None:
            return ValuationMetricsBackfillSourcePlan(
                records=(),
                diagnostics=(
                    _source_diagnostic(
                        code="valuation_backfill.no_source_date",
                        stock_code="",
                        message="daily_prices has no P/E source date available",
                    ),
                ),
                source_row_count=0,
                as_of_date=None,
            )
        source_rows = _load_daily_pe_rows(db_file, target_date)
    except sqlite3.Error as exc:
        return ValuationMetricsBackfillSourcePlan(
            records=(),
            diagnostics=(
                _source_diagnostic(
                    code="valuation_backfill.source_query_failed",
                    stock_code="",
                    message=str(exc),
                ),
            ),
            source_row_count=0,
            as_of_date=None,
        )

    if not source_rows:
        return ValuationMetricsBackfillSourcePlan(
            records=(),
            diagnostics=(
                _source_diagnostic(
                    code="valuation_backfill.no_source_rows",
                    stock_code="",
                    message=f"daily_prices has no P/E rows for {target_date.isoformat()}",
                ),
            ),
            source_row_count=0,
            as_of_date=target_date,
        )

    records: list[ValuationBackfillSourceRow] = []
    for stock_code, pe_value in source_rows:
        try:
            value = Decimal(str(pe_value))
            if not value.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            records.append(
                ValuationBackfillSourceRow(
                    stock_code=stock_code,
                    metric_value=None,
                    diagnostic=_source_diagnostic(
                        code="valuation_backfill.invalid_pe",
                        stock_code=stock_code,
                        message="daily_prices P/E value is not numeric",
                    ),
                )
            )
            continue
        records.append(
            ValuationBackfillSourceRow(stock_code=stock_code, metric_value=value)
        )

    return ValuationMetricsBackfillSourcePlan(
        records=tuple(records),
        diagnostics=(),
        source_row_count=len(source_rows),
        as_of_date=target_date,
    )


def apply_valuation_metrics_backfill(
    *,
    db_file: Path,
    backup_dir: Path,
    records: tuple[ValuationMetricRecord, ...],
) -> ValuationMetricsBackfillApplyResult:
    """Persist already interpreted source records using their unchanged wire fields."""

    records = tuple(records)
    if not records:
        return ValuationMetricsBackfillApplyResult(
            applied=False,
            inserted_count=0,
            backup_file=None,
        )
    quality_wire_values = tuple(
        parse_legacy_quality_wire_value(record.legacy_quality_wire_value)
        for record in records
    )

    db_file = Path(db_file)
    backup_file = create_sqlite_retained_backup(
        db_file,
        Path(backup_dir),
        label="valuation_metrics_backfill",
    )
    if backup_file is None:
        raise FileNotFoundError(db_file)

    conn = sqlite3.connect(db_file)
    try:
        inserted_count = _insert_valuation_metric_records(
            conn,
            records,
            quality_wire_values,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        restore_sqlite_backup(backup_file, db_file)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return ValuationMetricsBackfillApplyResult(
        applied=True,
        inserted_count=inserted_count,
        backup_file=backup_file,
    )


def _source_diagnostic(code: str, stock_code: str, message: str) -> SourceDiagnostic:
    return SourceDiagnostic(
        code=code,
        stock_code=stock_code,
        message=message,
        kind=SourceDiagnosticKind.VALUATION,
        metric_name="pe",
    )


def _resolve_as_of_date(db_file: Path, as_of_date: str | date | None) -> date | None:
    if isinstance(as_of_date, date):
        return as_of_date
    if isinstance(as_of_date, str) and as_of_date.strip():
        return _parse_date(as_of_date)

    with sqlite3.connect(db_file) as conn:
        row = conn.execute(
            'SELECT MAX("日期") FROM daily_prices WHERE "本益比" IS NOT NULL'
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return _parse_date(str(row[0]))


def _load_daily_pe_rows(db_file: Path, target_date: date) -> list[tuple[str, object]]:
    db_date = target_date.strftime("%Y%m%d")
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            """
            SELECT "證券代號", "本益比"
            FROM daily_prices
            WHERE "日期" = ? AND "本益比" IS NOT NULL
            ORDER BY "證券代號"
            """,
            (db_date,),
        ).fetchall()
    return [(str(stock_code).strip(), pe_value) for stock_code, pe_value in rows]


def _insert_valuation_metric_records(
    conn: sqlite3.Connection,
    records: tuple[ValuationMetricRecord, ...],
    quality_wire_values: tuple[str, ...],
) -> int:
    if len(records) != len(quality_wire_values):
        raise ValueError("valuation quality projection count does not match records")
    conn.executemany(
        """
        INSERT OR REPLACE INTO fundamental_valuation_metrics(
            stock_code, as_of_date, available_date, metric_name, value,
            industry, industry_percentile_bp, source, source_version, quality
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.stock_code,
                record.as_of_date.isoformat(),
                record.available_date.isoformat(),
                record.metric_name,
                str(record.metric_value),
                record.industry,
                record.industry_percentile_bp,
                record.source,
                record.source_version,
                quality_wire_value,
            )
            for record, quality_wire_value in zip(records, quality_wire_values)
        ],
    )
    return len(records)


def _parse_date(value: str) -> date:
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _companies_sort_date(value: str) -> str:
    value = str(value).strip()
    if not value:
        return ""
    if len(value) == 8 and value.isdigit():
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        return value
