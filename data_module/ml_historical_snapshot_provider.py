"""Read-only SQLite provider for causal historical ML feature snapshots."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterable, Iterator, Mapping, cast
from zoneinfo import ZoneInfo

from data_module.ml_daily_price_revision_gate import (
    VerifiedCurrentRestatedSourceContext,
    check_daily_price_source_revision,
)


_SOURCE_TABLES = (
    "daily_prices",
    "technical_indicators",
    "market_indices",
    "industry_indices",
)
_REQUIRED_COLUMNS = {
    "daily_prices": frozenset(
        {"日期", "證券代號", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"}
    ),
    "technical_indicators": frozenset({"日期", "證券代號", "RSI", "MACD", "ADX"}),
    "market_indices": frozenset({"日期", "收盤指數", "收盤價"}),
    "industry_indices": frozenset({"日期", "指數名稱", "收盤指數"}),
}
_VALIDATED_SCHEMA_CONTRACT = "historical-sqlite-schema.v1"
HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1 = (
    "twstock-historical-sqlite-four-table.v1"
)
_DAILY_PRICE_DATE_COLUMN = "\u65e5\u671f"
_DAILY_PRICE_SYMBOL_COLUMN = "\u8b49\u5238\u4ee3\u865f"


def _schema_digest(table_columns: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    payload = {
        "contract": _VALIDATED_SCHEMA_CONTRACT,
        "tables": [
            {"name": table, "columns": list(columns)}
            for table, columns in table_columns
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


@dataclass(frozen=True, slots=True)
class ValidatedHistoricalSchemaEvidenceV1:
    """同次唯讀載入已驗證的四表欄位；不代表資料修訂版或 durable generation。"""

    table_columns: tuple[tuple[str, tuple[str, ...]], ...]
    schema_sha256: str

    def __post_init__(self) -> None:
        if type(self.table_columns) is not tuple:
            raise TypeError("validated schema table_columns 必須是 tuple")
        if len(self.table_columns) != len(_SOURCE_TABLES):
            raise ValueError("validated schema 必須涵蓋完整 source table whitelist")
        for expected_table, record in zip(_SOURCE_TABLES, self.table_columns):
            if type(record) is not tuple or len(record) != 2:
                raise TypeError("validated schema table record 格式錯誤")
            table, columns = record
            if type(table) is not str or table != expected_table:
                raise ValueError("validated schema table 順序/名稱不符 whitelist")
            if type(columns) is not tuple or any(type(column) is not str for column in columns):
                raise TypeError("validated schema columns 必須是 immutable text tuple")
            if len(set(columns)) != len(columns):
                raise ValueError("validated schema columns 不可重複")
            if not _REQUIRED_COLUMNS[table].issubset(columns):
                raise ValueError(f"validated schema 缺少 {table} 必要欄位")
        if type(self.schema_sha256) is not str or len(self.schema_sha256) != 64:
            raise ValueError("validated schema digest 必須是 64 位小寫 SHA-256")
        if any(character not in "0123456789abcdef" for character in self.schema_sha256):
            raise ValueError("validated schema digest 必須是 64 位小寫 SHA-256")
        if self.schema_sha256 != _schema_digest(self.table_columns):
            raise ValueError("validated schema digest 與欄位內容不符")

    @classmethod
    def from_validated_columns(
        cls, schema: dict[str, tuple[str, ...]]
    ) -> "ValidatedHistoricalSchemaEvidenceV1":
        if type(schema) is not dict or set(schema) != set(_SOURCE_TABLES):
            raise ValueError("validated schema source table set 不符 whitelist")
        table_columns = tuple((table, tuple(schema[table])) for table in _SOURCE_TABLES)
        return cls(table_columns=table_columns, schema_sha256=_schema_digest(table_columns))

    @property
    def schema_version(self) -> str:
        return f"{_VALIDATED_SCHEMA_CONTRACT}:sha256:{self.schema_sha256}"


@dataclass(frozen=True, slots=True)
class ValidatedHistoricalLoadScopeV1:
    """同次 provider load 正規化後的選取參數；不含推測的來源身分。"""

    decision_date: str
    history_start_date: str
    symbols: tuple[str, ...]
    industry_index_names: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, value in (
            ("decision_date", self.decision_date),
            ("history_start_date", self.history_start_date),
        ):
            if type(value) is not str:
                raise TypeError(f"{name} 必須是 str")
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} 必須是 canonical ISO date") from exc
            if parsed.isoformat() != value:
                raise ValueError(f"{name} 必須是 canonical ISO date")
        if type(self.symbols) is not tuple or not self.symbols:
            raise ValueError("validated query symbols 必須是非空 tuple")
        if any(type(value) is not str or not value or value != value.strip() for value in self.symbols):
            raise ValueError("validated query symbols 必須是正規化文字")
        if tuple(sorted(set(self.symbols))) != self.symbols:
            raise ValueError("validated query symbols 必須排序且唯一")
        if type(self.industry_index_names) is not tuple:
            raise TypeError("validated query industry names 必須是 tuple")
        if any(
            type(value) is not str or not value or value != value.strip()
            for value in self.industry_index_names
        ):
            raise ValueError("validated query industry names 必須是正規化文字")
        if tuple(sorted(set(self.industry_index_names))) != self.industry_index_names:
            raise ValueError("validated query industry names 必須排序且唯一")


@dataclass(frozen=True)
class HistoricalPriceObservation:
    symbol: str
    trading_date: str
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    volume: int | None
    turnover_amount_minor: int | None


@dataclass(frozen=True)
class HistoricalTechnicalObservation:
    symbol: str
    trading_date: str
    rsi: Decimal | None
    macd: Decimal | None
    adx: Decimal | None


@dataclass(frozen=True)
class HistoricalIndexObservation:
    index_name: str
    trading_date: str
    close_value: Decimal | None


@dataclass(frozen=True)
class HistoricalRawSnapshot:
    decision_date: str
    feature_as_of_date: str
    prices: tuple[HistoricalPriceObservation, ...]
    technicals: tuple[HistoricalTechnicalObservation, ...]
    market: tuple[HistoricalIndexObservation, ...]
    industries: tuple[HistoricalIndexObservation, ...]
    source_fingerprint: str
    query_count: int
    source_tables: tuple[str, ...] = _SOURCE_TABLES
    query_only: bool = True
    shadow_only: bool = True
    production_action_allowed: bool = False
    validated_schema: ValidatedHistoricalSchemaEvidenceV1 | None = field(
        default=None, compare=False, repr=False
    )
    validated_query_scope: ValidatedHistoricalLoadScopeV1 | None = field(
        default=None, compare=False, repr=False
    )
    provider_contract_id: str | None = field(
        default=None, compare=False, repr=False, kw_only=True
    )

    def __post_init__(self) -> None:
        if date.fromisoformat(self.feature_as_of_date) >= date.fromisoformat(self.decision_date):
            raise ValueError("feature_as_of_date must be before decision_date")
        if self.source_tables != _SOURCE_TABLES:
            raise ValueError("historical ML snapshot source whitelist mismatch")
        if not self.query_only or not self.shadow_only or self.production_action_allowed:
            raise ValueError("historical ML snapshot must remain read-only and shadow-only")
        if self.validated_schema is not None and type(self.validated_schema) is not ValidatedHistoricalSchemaEvidenceV1:
            raise TypeError("validated_schema must be provider-issued schema evidence")
        if self.validated_query_scope is not None and type(self.validated_query_scope) is not ValidatedHistoricalLoadScopeV1:
            raise TypeError("validated_query_scope must be provider-issued query evidence")
        if self.provider_contract_id is not None and (
            type(self.provider_contract_id) is not str
            or self.provider_contract_id
            != HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1
        ):
            raise ValueError("historical snapshot provider contract ID is unsupported")


@dataclass(frozen=True)
class CurrentObservedRawSnapshot:
    """Exact current-restated query result, explicitly outside historical PIT."""

    decision_date: str
    feature_as_of_date: str
    prices: tuple[HistoricalPriceObservation, ...]
    technicals: tuple[HistoricalTechnicalObservation, ...]
    market: tuple[HistoricalIndexObservation, ...]
    industries: tuple[HistoricalIndexObservation, ...]
    source_fingerprint: str
    query_count: int
    local_current_observed_at: datetime
    source_context: VerifiedCurrentRestatedSourceContext
    snapshot_database_path: str
    snapshot_database_sha256: str
    snapshot_receipt_path: str
    snapshot_receipt_sha256: str
    source_rows_sha256_by_table: Mapping[str, str]
    requested_symbols: tuple[str, ...]
    cycle_id: str
    cycle_terminal_path: str
    cycle_terminal_sha256: str
    source_context_envelope_path: str
    source_context_envelope_sha256: str
    source_tables: tuple[str, ...] = _SOURCE_TABLES
    query_only: bool = True
    shadow_only: bool = True
    production_action_allowed: bool = False
    current_restated: bool = True
    historical_pit_eligible: bool = False
    formal_training_allowed: bool = False
    research_only: bool = True

    def __post_init__(self) -> None:
        if self.local_current_observed_at.tzinfo is None or self.local_current_observed_at.utcoffset() is None:
            raise ValueError("local_current_observed_at must be timezone-aware")
        if (
            self.current_restated is not True
            or self.historical_pit_eligible is not False
            or self.formal_training_allowed is not False
            or self.research_only is not True
            or self.query_only is not True
            or self.shadow_only is not True
            or self.production_action_allowed is not False
        ):
            raise ValueError("current-observed snapshot eligibility flags are invalid")
        if self.source_tables != _SOURCE_TABLES:
            raise ValueError("current-observed snapshot source whitelist mismatch")
        if (
            not self.requested_symbols
            or self.requested_symbols != tuple(sorted(set(self.requested_symbols)))
            or len(self.requested_symbols) > 16
        ):
            raise ValueError("current-observed symbol scope is invalid")
        if not self.cycle_id.strip() or not self.cycle_terminal_path.strip():
            raise ValueError("current-observed cycle identity is required")
        if not self.source_context_envelope_path.strip():
            raise ValueError("current-observed source-context envelope path is required")
        if (
            Path(self.source_context.snapshot_database_path).resolve()
            != Path(self.snapshot_database_path).resolve()
            or str(self.source_context.snapshot_database_sha256)
            != self.snapshot_database_sha256
            or Path(self.source_context.snapshot_receipt_path).resolve()
            != Path(self.snapshot_receipt_path).resolve()
            or str(self.source_context.snapshot_receipt_sha256)
            != self.snapshot_receipt_sha256
        ):
            raise ValueError("current-observed snapshot pins differ from verified context")
        for label, value in (
            ("cycle_terminal_sha256", self.cycle_terminal_sha256),
            ("source_context_envelope_sha256", self.source_context_envelope_sha256),
            ("snapshot_database_sha256", self.snapshot_database_sha256),
            ("snapshot_receipt_sha256", self.snapshot_receipt_sha256),
        ):
            if not _is_sha256_text(value):
                raise ValueError(f"current-observed {label} is invalid")
        if _iso_date(self.feature_as_of_date) >= _iso_date(self.decision_date):
            raise ValueError("current-observed feature date must precede decision date")
        if set(self.source_rows_sha256_by_table) != set(_SOURCE_TABLES):
            raise ValueError("current-observed snapshot must pin all four input tables")
        if any(
            not _is_sha256_text(value)
            for value in self.source_rows_sha256_by_table.values()
        ):
            raise ValueError("current-observed source row hash is invalid")


@dataclass(frozen=True)
class HistoricalForwardPriceWindow:
    """Read-only raw close window used only after a feature decision cutoff."""

    start_date: str
    end_date: str
    prices: tuple[HistoricalPriceObservation, ...]
    market: tuple[HistoricalIndexObservation, ...]
    source_fingerprint: str
    query_count: int
    source_tables: tuple[str, ...] = ("daily_prices", "market_indices")
    query_only: bool = True
    shadow_only: bool = True
    production_action_allowed: bool = False

    def __post_init__(self) -> None:
        if self.source_tables != ("daily_prices", "market_indices"):
            raise ValueError("historical forward window source whitelist mismatch")
        if not self.query_only or not self.shadow_only or self.production_action_allowed:
            raise ValueError("historical forward window must remain read-only and shadow-only")


class MLHistoricalSnapshotProvider:
    """Loads bounded price/technical/market/industry history without write access."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).resolve()
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def open_read_lease(self) -> "MLHistoricalSnapshotReadLease":
        """Open a same-connection observation lease without holding a read transaction."""

        return MLHistoricalSnapshotReadLease(self)

    def load(
        self,
        *,
        decision_date: str,
        history_start_date: str,
        symbols: tuple[str, ...],
        industry_index_names: tuple[str, ...] = (),
    ) -> HistoricalRawSnapshot:
        connection = self._connect()
        with closing(connection):
            snapshot = self._load_on_connection(
                connection,
                decision_date=decision_date,
                history_start_date=history_start_date,
                symbols=symbols,
                industry_index_names=industry_index_names,
            )
        if type(snapshot) is not HistoricalRawSnapshot:
            raise RuntimeError("historical provider returned a non-historical snapshot")
        return snapshot

    def load_current_observed(
        self,
        *,
        decision_date: str,
        history_start_date: str,
        symbols: tuple[str, ...],
        source_context: VerifiedCurrentRestatedSourceContext,
        local_current_observed_at: datetime | str,
        expected_feature_as_of_date: str,
        cycle_id: str,
        cycle_terminal_path: str | Path,
        cycle_terminal_sha256: str,
        source_context_envelope_path: str | Path,
        source_context_envelope_sha256: str,
        industry_index_names: tuple[str, ...] = (),
    ) -> CurrentObservedRawSnapshot:
        """Read a bounded current-restated vector from an exact frozen snapshot.

        The ordinary :meth:`load` remains revision-gated for historical PIT.
        This explicit lane accepts only a source-context object for this exact
        snapshot and records local observation time separately from source
        availability.  It is research-only and can never qualify historical
        training or OOS evidence.
        """

        if type(source_context) is not VerifiedCurrentRestatedSourceContext:
            raise TypeError("source_context must be verifier-issued current-restated context")
        if source_context.current_restated is not True or source_context.historical_pit_eligible is not False:
            raise ValueError("source_context is not current-restated research-only evidence")
        if Path(source_context.snapshot_database_path).resolve() != self.database_path:
            raise ValueError("source context snapshot path differs from this provider")
        if not isinstance(expected_feature_as_of_date, str):
            raise TypeError("expected_feature_as_of_date must be ISO date text")
        expected_as_of = _iso_date(expected_feature_as_of_date)
        try:
            decision = date.fromisoformat(decision_date[:10])
        except (TypeError, ValueError) as exc:
            raise ValueError("decision_date must be ISO date text") from exc
        if decision.isoformat() != decision_date[:10]:
            raise ValueError("decision_date must be canonical ISO date text")
        if isinstance(local_current_observed_at, datetime):
            observed_at = local_current_observed_at
        elif isinstance(local_current_observed_at, str):
            try:
                observed_at = datetime.fromisoformat(
                    local_current_observed_at.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("local_current_observed_at must be ISO datetime text") from exc
        else:
            raise TypeError("local_current_observed_at must be an aware datetime or ISO text")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("local_current_observed_at must be timezone-aware")
        observed_utc = observed_at.astimezone(timezone.utc)
        if observed_utc < source_context.training_as_of.astimezone(timezone.utc):
            raise ValueError("local observation predates its verified frozen snapshot")
        if observed_at.astimezone(ZoneInfo("Asia/Taipei")).date() != decision:
            raise ValueError("current-observed decision date differs from Taipei observation date")
        if expected_as_of >= decision.isoformat():
            raise ValueError("G9 current-observed feature date must precede decision date")
        database_sha_before = _sha256_path(self.database_path)
        expected_snapshot_sha = str(source_context.snapshot_database_sha256)
        if database_sha_before != expected_snapshot_sha.removeprefix("sha256:"):
            raise ValueError("current-observed snapshot bytes differ from source context")

        normalized_symbols = _normalized_texts(symbols, field_name="symbols")
        if not normalized_symbols or len(normalized_symbols) > 16:
            raise ValueError("current-observed symbol scope must contain 1..16 symbols")
        if tuple(sorted(set(normalized_symbols))) != normalized_symbols:
            raise ValueError("current-observed symbol scope must be unique and sorted")
        connection = self._connect()
        with closing(connection):
            current_snapshot = self._load_on_connection(
                connection,
                decision_date=decision.isoformat(),
                history_start_date=history_start_date,
                symbols=normalized_symbols,
                industry_index_names=industry_index_names,
                current_restated_context=source_context,
                current_feature_as_of_date=expected_as_of,
                cycle_id=cycle_id,
                cycle_terminal_path=str(Path(cycle_terminal_path).resolve()),
                cycle_terminal_sha256=cycle_terminal_sha256,
                source_context_envelope_path=str(Path(source_context_envelope_path).resolve()),
                source_context_envelope_sha256=source_context_envelope_sha256,
            )
        database_sha_after = _sha256_path(self.database_path)
        if database_sha_after != database_sha_before:
            raise RuntimeError("frozen current-observed snapshot changed during vector load")
        if not isinstance(current_snapshot, CurrentObservedRawSnapshot):
            raise RuntimeError("current-observed reader did not return its typed current snapshot")
        if current_snapshot.feature_as_of_date != expected_as_of:
            raise ValueError(
                "current-observed source date differs from exact cycle terminal: "
                f"{current_snapshot.feature_as_of_date}!={expected_as_of}"
            )
        return replace(current_snapshot, local_current_observed_at=observed_at)

    def _load_on_connection(
        self,
        connection: sqlite3.Connection,
        *,
        decision_date: str,
        history_start_date: str,
        symbols: tuple[str, ...],
        industry_index_names: tuple[str, ...] = (),
        current_restated_context: VerifiedCurrentRestatedSourceContext | None = None,
        current_feature_as_of_date: str | None = None,
        cycle_id: str | None = None,
        cycle_terminal_path: str | None = None,
        cycle_terminal_sha256: str | None = None,
        source_context_envelope_path: str | None = None,
        source_context_envelope_sha256: str | None = None,
    ) -> HistoricalRawSnapshot | CurrentObservedRawSnapshot:
        decision = _compact_date(decision_date)
        history_start = _compact_date(history_start_date)
        normalized_symbols = _normalized_texts(symbols, field_name="symbols")
        normalized_industries = tuple(sorted({str(value).strip() for value in industry_index_names if str(value).strip()}))
        query_count = 0
        with self._read_snapshot_transaction(
            connection,
            before_begin=(
                None
                if current_restated_context is not None
                else lambda: check_daily_price_source_revision(
                    database_path=self.database_path,
                    decision_date=decision,
                    symbols=normalized_symbols,
                )
            ),
            changed_message="historical SQLite source changed during snapshot load",
        ) as source_stat_before:
            schema = self._validate_schema(connection)
            symbol_clause = _placeholders(normalized_symbols)
            if current_restated_context is not None:
                if current_feature_as_of_date is None:
                    raise ValueError("current-observed feature date is required")
                cutoff = _compact_date(current_feature_as_of_date)
                cutoff_rows = connection.execute(
                    f'SELECT "{_DAILY_PRICE_SYMBOL_COLUMN}", '
                    f'MAX("{_DAILY_PRICE_DATE_COLUMN}") FROM daily_prices '
                    f'WHERE "{_DAILY_PRICE_DATE_COLUMN}" <= ? '
                    f'AND "{_DAILY_PRICE_SYMBOL_COLUMN}" IN ({symbol_clause}) '
                    f'GROUP BY "{_DAILY_PRICE_SYMBOL_COLUMN}"',
                    (cutoff, *normalized_symbols),
                ).fetchall()
                query_count += 1
                observed_dates = {
                    str(row[0]).strip(): (_iso_date(row[1]) if row[1] else None)
                    for row in cutoff_rows
                }
                missing_or_stale = tuple(
                    symbol
                    for symbol in normalized_symbols
                    if observed_dates.get(symbol) != _iso_date(cutoff)
                )
                if missing_or_stale:
                    raise ValueError(
                        "current-observed snapshot lacks exact expected source date "
                        f"for symbols={','.join(missing_or_stale)}"
                    )
            else:
                cutoff_row = connection.execute(
                    f'SELECT MAX("日期") FROM daily_prices '
                    f'WHERE "日期" < ? AND "證券代號" IN ({symbol_clause})',
                    (decision, *normalized_symbols),
                ).fetchone()
                query_count += 1
                if cutoff_row is None or cutoff_row[0] is None:
                    raise ValueError("no previous trading day is available for the requested symbols")
                cutoff = str(cutoff_row[0])

            prices = tuple(
                HistoricalPriceObservation(
                    symbol=str(row[0]).strip(), trading_date=_iso_date(row[1]),
                    volume=_integer(row[2]), turnover_amount_minor=_integer(row[3]),
                    open_price=_decimal(row[4]), high_price=_decimal(row[5]),
                    low_price=_decimal(row[6]), close_price=_decimal(row[7]),
                )
                for row in connection.execute(
                    f'SELECT "證券代號", "日期", "成交股數", "成交金額", '
                    f'CAST("開盤價" AS TEXT), CAST("最高價" AS TEXT), '
                    f'CAST("最低價" AS TEXT), CAST("收盤價" AS TEXT) '
                    f'FROM daily_prices WHERE "日期" BETWEEN ? AND ? '
                    f'AND "證券代號" IN ({symbol_clause}) ORDER BY "證券代號", "日期"',
                    (history_start, cutoff, *normalized_symbols),
                )
            )
            query_count += 1
            technicals = tuple(
                HistoricalTechnicalObservation(
                    symbol=str(row[0]).strip(), trading_date=_iso_date(row[1]),
                    rsi=_decimal(row[2]), macd=_decimal(row[3]), adx=_decimal(row[4]),
                )
                for row in connection.execute(
                    f'SELECT "證券代號", "日期", CAST("RSI" AS TEXT), '
                    f'CAST("MACD" AS TEXT), CAST("ADX" AS TEXT) '
                    f'FROM technical_indicators WHERE "日期" BETWEEN ? AND ? '
                    f'AND "證券代號" IN ({symbol_clause}) ORDER BY "證券代號", "日期"',
                    (history_start, cutoff, *normalized_symbols),
                )
            )
            query_count += 1
            market = tuple(
                HistoricalIndexObservation(
                    index_name="market", trading_date=_iso_date(row[0]), close_value=_decimal(row[1])
                )
                for row in connection.execute(
                    'SELECT "日期", CAST(COALESCE("收盤價", "收盤指數") AS TEXT) '
                    'FROM market_indices WHERE "日期" BETWEEN ? AND ? ORDER BY "日期"',
                    (history_start, cutoff),
                )
            )
            query_count += 1
            industries: tuple[HistoricalIndexObservation, ...] = ()
            if normalized_industries:
                industry_clause = _placeholders(normalized_industries)
                industries = tuple(
                    HistoricalIndexObservation(
                        index_name=str(row[0]), trading_date=_iso_date(row[1]), close_value=_decimal(row[2])
                    )
                    for row in connection.execute(
                        f'SELECT "指數名稱", "日期", CAST("收盤指數" AS TEXT) '
                        f'FROM industry_indices WHERE "日期" BETWEEN ? AND ? '
                        f'AND "指數名稱" IN ({industry_clause}) ORDER BY "指數名稱", "日期"',
                        (history_start, cutoff, *normalized_industries),
                    )
                )
            else:
                # Keep a stable batch-query audit count without broad-reading all industries.
                connection.execute('SELECT 1 FROM industry_indices WHERE 0').fetchall()
            query_count += 1

        source_stat_after = self.database_path.stat()
        if (
            source_stat_after.st_size,
            source_stat_after.st_mtime_ns,
        ) != (
            source_stat_before.st_size,
            source_stat_before.st_mtime_ns,
        ):
            raise RuntimeError("historical SQLite source changed during snapshot load")
        if current_restated_context is not None:
            if (
                not cycle_id
                or not cycle_terminal_path
                or not cycle_terminal_sha256
                or not source_context_envelope_path
                or not source_context_envelope_sha256
            ):
                raise ValueError("current-observed exact cycle pins are required")
            row_sets = {
                "daily_prices": prices,
                "technical_indicators": technicals,
                "market_indices": market,
                "industry_indices": industries,
            }
            return CurrentObservedRawSnapshot(
                decision_date=_iso_date(decision),
                feature_as_of_date=_iso_date(cutoff),
                prices=prices,
                technicals=technicals,
                market=market,
                industries=industries,
                source_fingerprint=(
                    "sha256:"
                    + current_restated_context.snapshot_database_sha256.removeprefix("sha256:")
                ),
                query_count=query_count,
                local_current_observed_at=datetime.now(timezone.utc),
                source_context=current_restated_context,
                snapshot_database_path=str(Path(current_restated_context.snapshot_database_path).resolve()),
                snapshot_database_sha256=str(current_restated_context.snapshot_database_sha256),
                snapshot_receipt_path=str(Path(current_restated_context.snapshot_receipt_path).resolve()),
                snapshot_receipt_sha256=str(current_restated_context.snapshot_receipt_sha256),
                source_rows_sha256_by_table=_current_observation_row_hashes(row_sets),
                requested_symbols=normalized_symbols,
                cycle_id=cycle_id,
                cycle_terminal_path=cycle_terminal_path,
                cycle_terminal_sha256=cycle_terminal_sha256,
                source_context_envelope_path=source_context_envelope_path,
                source_context_envelope_sha256=source_context_envelope_sha256,
            )
        return HistoricalRawSnapshot(
            decision_date=_iso_date(decision), feature_as_of_date=_iso_date(cutoff),
            prices=prices, technicals=technicals, market=market, industries=industries,
            source_fingerprint=self._fingerprint(schema, source_stat_before), query_count=query_count,
            validated_schema=ValidatedHistoricalSchemaEvidenceV1.from_validated_columns(schema),
            validated_query_scope=ValidatedHistoricalLoadScopeV1(
                decision_date=_iso_date(decision),
                history_start_date=_iso_date(history_start),
                symbols=normalized_symbols,
                industry_index_names=normalized_industries,
            ),
            provider_contract_id=HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
        )

    def list_trading_dates(
        self,
        *,
        start_date: str,
        end_date: str,
        symbols: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Return bounded stock trading dates without discovering a universe."""

        start = _compact_date(start_date)
        end = _compact_date(end_date)
        normalized_symbols = _normalized_texts(symbols, field_name="symbols")
        connection = self._connect()
        with closing(connection), self._read_snapshot_transaction(
            connection,
            changed_message="historical SQLite source changed during trading-date load",
        ) as source_stat_before:
            self._validate_schema(connection)
            symbol_clause = _placeholders(normalized_symbols)
            rows = connection.execute(
                f'SELECT DISTINCT "日期" FROM daily_prices '
                f'WHERE "日期" BETWEEN ? AND ? AND "證券代號" IN ({symbol_clause}) '
                f'ORDER BY "日期"',
                (start, end, *normalized_symbols),
            ).fetchall()
        source_stat_after = self.database_path.stat()
        if (source_stat_before.st_size, source_stat_before.st_mtime_ns) != (
            source_stat_after.st_size,
            source_stat_after.st_mtime_ns,
        ):
            raise RuntimeError("historical SQLite source changed during trading-date load")
        return tuple(_iso_date(row[0]) for row in rows)

    def load_forward_price_window(
        self,
        *,
        start_date: str,
        end_date: str,
        symbols: tuple[str, ...],
    ) -> HistoricalForwardPriceWindow:
        """Load raw prices and benchmark rows for labels, in SQLite read-only mode."""

        start = _compact_date(start_date)
        end = _compact_date(end_date)
        normalized_symbols = _normalized_texts(symbols, field_name="symbols")
        query_count = 0
        connection = self._connect()
        with closing(connection), self._read_snapshot_transaction(
            connection,
            before_begin=lambda: check_daily_price_source_revision(
                database_path=self.database_path,
                decision_date=end,
                symbols=normalized_symbols,
            ),
            changed_message="historical SQLite source changed during forward window load",
        ) as source_stat_before:
            schema = self._validate_schema(connection)
            symbol_clause = _placeholders(normalized_symbols)
            prices = tuple(
                HistoricalPriceObservation(
                    symbol=str(row[0]).strip(),
                    trading_date=_iso_date(row[1]),
                    volume=_integer(row[2]),
                    turnover_amount_minor=_integer(row[3]),
                    open_price=_decimal(row[4]),
                    high_price=_decimal(row[5]),
                    low_price=_decimal(row[6]),
                    close_price=_decimal(row[7]),
                )
                for row in connection.execute(
                    f'SELECT "證券代號", "日期", "成交股數", "成交金額", '
                    f'CAST("開盤價" AS TEXT), CAST("最高價" AS TEXT), '
                    f'CAST("最低價" AS TEXT), CAST("收盤價" AS TEXT) '
                    f'FROM daily_prices WHERE "日期" BETWEEN ? AND ? '
                    f'AND "證券代號" IN ({symbol_clause}) ORDER BY "證券代號", "日期"',
                    (start, end, *normalized_symbols),
                )
            )
            query_count += 1
            market = tuple(
                HistoricalIndexObservation(
                    index_name="market",
                    trading_date=_iso_date(row[0]),
                    close_value=_decimal(row[1]),
                )
                for row in connection.execute(
                    'SELECT "日期", CAST(COALESCE("收盤價", "收盤指數") AS TEXT) '
                    'FROM market_indices WHERE "日期" BETWEEN ? AND ? ORDER BY "日期"',
                    (start, end),
                )
            )
            query_count += 1
        source_stat_after = self.database_path.stat()
        if (source_stat_before.st_size, source_stat_before.st_mtime_ns) != (
            source_stat_after.st_size,
            source_stat_after.st_mtime_ns,
        ):
            raise RuntimeError("historical SQLite source changed during forward window load")
        return HistoricalForwardPriceWindow(
            start_date=_iso_date(start),
            end_date=_iso_date(end),
            prices=prices,
            market=market,
            source_fingerprint=self._fingerprint(schema, source_stat_before),
            query_count=query_count,
        )

    @contextmanager
    def _read_snapshot_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        changed_message: str,
        before_begin: Callable[[], object] | None = None,
    ) -> Iterator[os.stat_result]:
        """Run provider reads against one SQLite snapshot and detect other commits."""

        data_version_before = self._data_version(connection)
        source_stat_before = self.database_path.stat()
        if before_begin is not None:
            before_begin()

        connection.execute("BEGIN")
        try:
            yield source_stat_before
            connection.commit()
            if self._data_version(connection) != data_version_before:
                raise RuntimeError(changed_message)
        finally:
            if connection.in_transaction:
                connection.rollback()

    @staticmethod
    def _data_version(connection: sqlite3.Connection) -> int:
        row = connection.execute("PRAGMA data_version").fetchone()
        if row is None or len(row) != 1:
            raise RuntimeError("SQLite data_version is unavailable")
        try:
            return int(row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("SQLite data_version is invalid") from exc

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.database_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")
        enabled = connection.execute("PRAGMA query_only").fetchone()
        if enabled != (1,):
            connection.close()
            raise RuntimeError("SQLite query_only could not be enabled")
        return connection

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
        schema: dict[str, tuple[str, ...]] = {}
        existing = {str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for table in _SOURCE_TABLES:
            if table not in existing:
                raise ValueError(f"required table is missing: {table}")
            columns = tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))
            missing = _REQUIRED_COLUMNS[table] - set(columns)
            if missing:
                raise ValueError(f"required columns are missing from {table}: {sorted(missing)}")
            schema[table] = columns
        return schema

    def _fingerprint(
        self, schema: dict[str, tuple[str, ...]], stat: object
    ) -> str:
        payload = {
            "path": str(self.database_path), "size": getattr(stat, "st_size"),
            "mtime_ns": getattr(stat, "st_mtime_ns"), "schema": schema,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return f"sha256:{digest}"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_observation_row_hashes(
    rows_by_table: Mapping[str, tuple[object, ...]],
) -> dict[str, str]:
    if set(rows_by_table) != set(_SOURCE_TABLES):
        raise ValueError("current-observed row hash requires every whitelisted table")
    output: dict[str, str] = {}
    for table, rows in rows_by_table.items():
        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            item: dict[str, object] = {}
            for row_field in fields(cast(Any, row)):
                value = getattr(row, row_field.name)
                if isinstance(value, Decimal):
                    item[row_field.name] = format(value, "f")
                else:
                    item[row_field.name] = value
            normalized_rows.append(item)
        payload = json.dumps(
            normalized_rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        output[table] = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    return output


class MLHistoricalSnapshotReadLease:
    """Keep one read-only connection open for a bounded same-connection check.

    The lease does not keep a SQLite transaction open after ``load``. Its
    ``data_version`` comparison is meaningful only on this connection and for
    this object's lifetime; it is not a durable or cross-connection generation
    identifier.
    """

    def __init__(self, provider: MLHistoricalSnapshotProvider) -> None:
        self._provider = provider
        self._connection: sqlite3.Connection | None = None
        self._baseline_data_version: int | None = None
        self._baseline_stat: os.stat_result | None = None
        self._load_attempted = False
        self._load_completed = False

    def __enter__(self) -> "MLHistoricalSnapshotReadLease":
        if self._connection is not None:
            raise RuntimeError("SQLite read lease is already open")
        if self._load_attempted or self._load_completed:
            raise RuntimeError("SQLite read lease has already been used")
        connection = self._provider._connect()
        try:
            baseline_data_version = self._provider._data_version(connection)
            baseline_stat = self._provider.database_path.stat()
        except BaseException:
            connection.close()
            raise
        self._connection = connection
        self._baseline_data_version = baseline_data_version
        self._baseline_stat = baseline_stat
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        self._baseline_data_version = None
        self._baseline_stat = None
        if connection is not None:
            try:
                if connection.in_transaction:
                    connection.rollback()
            finally:
                connection.close()

    def load(
        self,
        *,
        decision_date: str,
        history_start_date: str,
        symbols: tuple[str, ...],
        industry_index_names: tuple[str, ...] = (),
    ) -> HistoricalRawSnapshot:
        connection = self._require_connection()
        if self._load_attempted:
            raise RuntimeError("SQLite read lease already loaded a snapshot")
        self._assert_same_source_observation()
        self._load_attempted = True
        snapshot = self._provider._load_on_connection(
            connection,
            decision_date=decision_date,
            history_start_date=history_start_date,
            symbols=symbols,
            industry_index_names=industry_index_names,
        )
        self._load_completed = True
        return cast(HistoricalRawSnapshot, snapshot)

    def assert_unchanged(self) -> None:
        self._require_connection()
        if not self._load_completed:
            raise RuntimeError("SQLite read lease has no completed snapshot")
        self.assert_observation_unchanged()

    def assert_observation_unchanged(self) -> None:
        """Check the same-connection source observation, with or without load().

        This is an observation boundary only. It does not hold a SQLite read
        transaction open or provide a durable generation identifier.
        """

        self._require_connection()
        self._assert_same_source_observation()

    def _assert_same_source_observation(self) -> None:
        connection = self._require_connection()
        baseline_data_version = self._baseline_data_version
        baseline_stat = self._baseline_stat
        if baseline_data_version is None or baseline_stat is None:
            raise RuntimeError("SQLite read lease baseline is unavailable")
        if self._provider._data_version(connection) != baseline_data_version:
            raise RuntimeError("historical SQLite source changed during read lease")
        try:
            current_stat = self._provider.database_path.stat()
        except OSError as exc:
            raise RuntimeError("historical SQLite source path changed during read lease") from exc
        if (current_stat.st_size, current_stat.st_mtime_ns) != (
            baseline_stat.st_size,
            baseline_stat.st_mtime_ns,
        ):
            raise RuntimeError("historical SQLite source changed during read lease")

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise RuntimeError("SQLite read lease is closed")
        return connection


def _normalized_texts(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    result = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _placeholders(values: tuple[str, ...]) -> str:
    return ",".join("?" for _ in values)


def _compact_date(value: str) -> str:
    return date.fromisoformat(value[:10]).strftime("%Y%m%d")


def _iso_date(value: object) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    return date.fromisoformat(text[:10]).isoformat()


def _decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() in {"", "--", "-"}:
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return None


def _integer(value: object) -> int | None:
    if value is None or str(value).strip() in {"", "--", "-"}:
        return None
    try:
        return int(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return None
