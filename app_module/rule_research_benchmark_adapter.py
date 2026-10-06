"""UX21 forward outcome 使用的明示、唯讀市場基準來源。

Adapter 將呼叫者宣告的研究契約綁定至 ``market_indices`` 精確資料列；
不授予歷史 PIT、正式、訓練或交易資格。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable

from app_module.rule_research_forward_outcome import (
    BenchmarkSpec,
    ForwardOutcomeError,
    PricePoint,
)
from app_module.daily_market_snapshot_source import _source_pin
from app_module.sqlite_read_only import (
    ReadOperationCancelled,
    check_read_cancelled,
    connect_read_only_sqlite,
    cooperative_read_cancellation,
)


ADAPTER_VERSION = "ux21-explicit-market-benchmark.v1"
QUALIFICATION_SCOPE = "caller_declared_research_only"
_UNKNOWN_MARKERS = {
    "unknown", "unavailable", "none", "null", "n/a", "na", "not available",
    "未知", "不明", "未確認", "未提供",
}
_DATE_FORMATS = (
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{4}/\d{2}/\d{2}$"), "%Y/%m/%d"),
    (re.compile(r"^\d{8}$"), "%Y%m%d"),
)
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("指數名稱", "index_name"),
    "date": ("日期", "trade_date", "date"),
    "close_index": ("收盤指數", "close_index"),
    "close_price": ("收盤價", "close_price"),
    "currency": ("currency", "幣別", "貨幣", "交易幣別"),
    "unit": ("unit", "單位"),
    "price_basis": ("price_basis", "價格基礎", "價格基準", "調整基礎"),
    "corporate_action_basis": (
        "corporate_action_basis", "corp_action_basis", "公司行動基礎", "公司行動調整基礎"
    ),
    "available_date": ("available_date", "availability_date", "可得日", "資料可得日"),
}


@dataclass(frozen=True, slots=True)
class ExplicitBenchmarkRequest:
    """呼叫者選定的基準、精確日期與研究比較契約。"""

    database_path: str | Path
    source_identity: str
    benchmark_name: str
    decision_date: str
    endpoint_dates: Sequence[str]
    as_of_date: str
    currency: str | None
    unit: str | None
    price_basis: str | None
    corporate_action_basis: str | None
    availability_by_date: Mapping[str, str | None] = field(default_factory=dict)
    target_currency: str | None = None
    target_price_basis: str | None = None
    target_corporate_action_basis: str | None = None
    expected_rowset_sha256: str | None = None
    expected_decision_row_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ExplicitBenchmarkResult:
    """明示基準請求的結果；資格旗標固定為 false。"""

    status: str
    reason_codes: tuple[str, ...]
    benchmark: BenchmarkSpec | None = None
    prices: tuple[PricePoint, ...] = ()
    observed_rowset_sha256: str | None = None
    observed_decision_row_sha256: str | None = None
    source_contract_sha256: str | None = None
    source_contract_json: str | None = None
    observed_at_utc: str | None = None
    qualification_scope: str = QUALIFICATION_SCOPE
    historical_pit_eligible: bool = False
    formal_eligible: bool = False
    training_eligible: bool = False
    trading_eligible: bool = False
    execution_eligible: bool = False
    natural_authority: bool = False


class _AdapterIssue(ValueError):
    def __init__(self, status: str, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(code)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _date(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise _AdapterIssue("rejected", f"{field_name}_invalid")
    text = value.strip()
    for pattern, date_format in _DATE_FORMATS:
        if pattern.fullmatch(text):
            try:
                return datetime.strptime(text, date_format).date().isoformat()
            except ValueError as error:
                raise _AdapterIssue("rejected", f"{field_name}_invalid") from error
    raise _AdapterIssue("rejected", f"{field_name}_invalid")


def _date_aliases(iso_date: str) -> tuple[str, str, str]:
    parsed = date.fromisoformat(iso_date)
    return (
        parsed.isoformat(),
        parsed.strftime("%Y/%m/%d"),
        parsed.strftime("%Y%m%d"),
    )


def _declared_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _AdapterIssue("rejected", f"{field_name}_invalid")
    result = value.strip()
    if not result or result.casefold() in _UNKNOWN_MARKERS:
        return None
    if len(result) > 512:
        raise _AdapterIssue("rejected", f"{field_name}_too_long")
    return result


def _hash_pin(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise _AdapterIssue("rejected", f"{field_name}_invalid")
    return value.lower()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _find_columns(columns: Sequence[str], semantic: str) -> tuple[str, ...]:
    aliases = {item.casefold() for item in _COLUMN_ALIASES[semantic]}
    return tuple(column for column in columns if column.casefold() in aliases)


def _one_column(columns: Sequence[str], semantic: str) -> str | None:
    found = _find_columns(columns, semantic)
    if len(found) > 1:
        raise _AdapterIssue("rejected", f"schema_{semantic}_ambiguous")
    return found[0] if found else None


def _raw_row_json(row: Mapping[str, Any]) -> str:
    return _canonical_json(dict(row))


def _row_value(row: Mapping[str, Any], column: str | None) -> str | None:
    if column is None:
        return None
    value = row.get(column)
    return value if isinstance(value, str) else None


def _source_metadata_matches(
    row: Mapping[str, Any],
    metadata_columns: Mapping[str, tuple[str, ...]],
    declared: Mapping[str, str | None],
    availability: str | None,
    trade_date: str,
    as_of_date: str,
    unknown_codes: list[str],
) -> None:
    for field_name in ("currency", "unit", "price_basis", "corporate_action_basis"):
        expected = declared[field_name]
        if expected is None:
            continue
        for column in metadata_columns[field_name]:
            observed = _row_value(row, column)
            if observed is None or observed.strip().casefold() in _UNKNOWN_MARKERS:
                unknown_codes.append(f"source_{field_name}_unknown")
            elif observed.strip() != expected:
                raise _AdapterIssue("rejected", f"source_{field_name}_mismatch")

    for column in metadata_columns["available_date"]:
        observed = _row_value(row, column)
        if observed is None or observed.strip().casefold() in _UNKNOWN_MARKERS:
            unknown_codes.append("source_availability_unknown")
            continue
        parsed = _date(observed, "source_available_date")
        if parsed < trade_date:
            raise _AdapterIssue("rejected", "source_available_before_trade_date")
        if availability is not None and parsed != availability:
            raise _AdapterIssue("rejected", "source_availability_mismatch")
        if parsed > as_of_date:
            unknown_codes.append("source_availability_after_as_of")


def _price_from_row(
    row: Mapping[str, Any],
    price_columns: Sequence[str],
) -> Decimal:
    values: list[Decimal] = []
    for column in price_columns:
        raw = row.get(column)
        if raw is None:
            continue
        if not isinstance(raw, str) or len(raw.strip()) > 256:
            raise _AdapterIssue("rejected", "benchmark_price_text_too_long_or_invalid")
        try:
            value = Decimal(raw.strip())
        except (InvalidOperation, ValueError) as error:
            raise _AdapterIssue("rejected", "benchmark_price_invalid") from error
        if not value.is_finite() or value <= 0:
            raise _AdapterIssue("rejected", "benchmark_price_invalid")
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or len(value.as_tuple().digits) > 64 or abs(exponent) > 64:
            raise _AdapterIssue("rejected", "benchmark_price_precision_bound")
        values.append(value)
    if not values:
        raise _AdapterIssue("unknown", "benchmark_price_missing")
    if any(value != values[0] for value in values[1:]):
        raise _AdapterIssue("rejected", "benchmark_close_columns_conflict")
    return values[0]


def _result(
    status: str,
    codes: Sequence[str],
    *,
    rowset_sha256: str | None = None,
    decision_row_sha256: str | None = None,
    contract_sha256: str | None = None,
    contract_json: str | None = None,
    observed_at: str | None = None,
    benchmark: BenchmarkSpec | None = None,
    prices: Sequence[PricePoint] = (),
) -> ExplicitBenchmarkResult:
    return ExplicitBenchmarkResult(
        status=status,
        reason_codes=tuple(dict.fromkeys(codes)),
        benchmark=benchmark,
        prices=tuple(prices),
        observed_rowset_sha256=rowset_sha256,
        observed_decision_row_sha256=decision_row_sha256,
        source_contract_sha256=contract_sha256,
        source_contract_json=contract_json,
        observed_at_utc=observed_at,
    )


def load_explicit_market_benchmark(
    request: ExplicitBenchmarkRequest,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    observed_at: datetime | None = None,
) -> ExplicitBenchmarkResult:
    """透過 query-only transaction 讀取呼叫者指定的市場指數與精確日期。

    首次呼叫若未提供兩個 expected hash，會回傳 ``unknown`` 與觀測 pin。
    呼叫者可明示 pin 後重試；只有契約完整且 pin 相符的研究請求才會取得
    ``benchmark`` 與 ``prices``。
    """

    observed_rowset_sha256: str | None = None
    observed_decision_row_sha256: str | None = None
    source_contract_sha256: str | None = None
    source_contract_json: str | None = None
    observed_at_text: str | None = None
    try:
        if not isinstance(request, ExplicitBenchmarkRequest):
            raise _AdapterIssue("rejected", "request_type_invalid")

        # I/O 與 identity 計算前，先複製可變的 request 容器。
        if isinstance(request.endpoint_dates, (str, bytes)) or not isinstance(request.endpoint_dates, Sequence):
            raise _AdapterIssue("rejected", "endpoint_dates_invalid")
        raw_endpoints = tuple(request.endpoint_dates)
        if not isinstance(request.availability_by_date, Mapping):
            raise _AdapterIssue("unknown", "availability_mapping_unknown")
        raw_availability = tuple(request.availability_by_date.items())

        source_identity = _declared_text(request.source_identity, "source_identity")
        benchmark_name = _declared_text(request.benchmark_name, "benchmark_name")
        if source_identity is None:
            raise _AdapterIssue("unknown", "source_identity_unknown")
        if benchmark_name is None:
            raise _AdapterIssue("rejected", "benchmark_name_required")
        if re.fullmatch(r"\d{4,6}", benchmark_name):
            raise _AdapterIssue("rejected", "benchmark_name_stock_code_collision")

        decision = _date(request.decision_date, "decision_date")
        as_of = _date(request.as_of_date, "as_of_date")
        if decision > as_of:
            raise _AdapterIssue("rejected", "as_of_before_decision")

        now = datetime.now(timezone.utc)
        if observed_at is None:
            clock = now
        elif (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise _AdapterIssue("rejected", "observed_at_timezone_required")
        else:
            clock = observed_at.astimezone(timezone.utc)
            if clock > now:
                raise _AdapterIssue("rejected", "observed_at_in_future")
        observed_at_text = clock.isoformat().replace("+00:00", "Z")
        if date.fromisoformat(as_of) > min(now.date(), clock.date()):
            raise _AdapterIssue("rejected", "as_of_date_in_future")

        if not 1 <= len(raw_endpoints) <= 4:
            raise _AdapterIssue("rejected", "endpoint_count_invalid")
        endpoints = tuple(_date(item, "endpoint_date") for item in raw_endpoints)
        if len(set(endpoints)) != len(endpoints):
            raise _AdapterIssue("rejected", "endpoint_date_duplicate")
        if decision not in endpoints:
            raise _AdapterIssue("rejected", "decision_endpoint_required")

        availability: dict[str, str | None] = {}
        for raw_day, raw_value in raw_availability:
            day = _date(raw_day, "availability_endpoint_date")
            if day in availability:
                raise _AdapterIssue("rejected", "availability_endpoint_duplicate")
            if raw_value is None:
                availability[day] = None
            else:
                availability[day] = _date(raw_value, "available_date")
        if set(availability) - set(endpoints):
            raise _AdapterIssue("rejected", "availability_endpoint_unrequested")

        declared: dict[str, str | None] = {
            "currency": _declared_text(request.currency, "currency"),
            "unit": _declared_text(request.unit, "unit"),
            "price_basis": _declared_text(request.price_basis, "price_basis"),
            "corporate_action_basis": _declared_text(
                request.corporate_action_basis, "corporate_action_basis"
            ),
        }
        target = {
            "currency": _declared_text(request.target_currency, "target_currency"),
            "price_basis": _declared_text(request.target_price_basis, "target_price_basis"),
            "corporate_action_basis": _declared_text(
                request.target_corporate_action_basis, "target_corporate_action_basis"
            ),
        }
        for field_name, expected in (
            ("currency", target["currency"]),
            ("price_basis", target["price_basis"]),
            ("corporate_action_basis", target["corporate_action_basis"]),
        ):
            if declared[field_name] is not None and expected is not None and declared[field_name] != expected:
                raise _AdapterIssue("rejected", f"target_{field_name}_mismatch")

        expected_rowset = _hash_pin(request.expected_rowset_sha256, "expected_rowset_sha256")
        expected_decision = _hash_pin(
            request.expected_decision_row_sha256, "expected_decision_row_sha256"
        )
        unknown_codes: list[str] = []
        for field_name, value in declared.items():
            if value is None:
                unknown_codes.append(f"{field_name}_unknown")
        for field_name, value in target.items():
            if value is None:
                unknown_codes.append(f"target_{field_name}_unknown")
        if expected_rowset is None:
            unknown_codes.append("rowset_pin_required")
        if expected_decision is None:
            unknown_codes.append("decision_row_pin_required")
        for day in endpoints:
            if day not in availability:
                unknown_codes.append(f"availability_{day}_unknown")
                continue
            available = availability[day]
            if available is None:
                unknown_codes.append(f"availability_{day}_unknown")
            elif available < day:
                raise _AdapterIssue("rejected", "available_before_trade_date")
            elif day > as_of or available > as_of:
                unknown_codes.append(f"availability_{day}_after_as_of")

        readable_dates: list[str] = []
        for day in endpoints:
            available = availability.get(day)
            if day <= as_of and available is not None and available <= as_of:
                readable_dates.append(day)
        read_dates = tuple(sorted(readable_dates))
        if not isinstance(request.database_path, (str, Path)):
            raise _AdapterIssue("rejected", "database_path_invalid")
        db_path = Path(request.database_path)
        resolved_db_path = str(db_path.resolve())
        if not db_path.is_file():
            raise _AdapterIssue("unknown", "source_database_missing")

        schema_columns: list[dict[str, Any]] = []
        rows_by_date: dict[str, list[dict[str, Any]]] = {day: [] for day in read_dates}
        table_name = "market_indices"
        source_pin: object | None = _source_pin(db_path.resolve())

        def check_source_stable() -> None:
            if source_pin is not None and _source_pin(db_path.resolve()) != source_pin:
                raise _AdapterIssue("rejected", "source_changed_during_read")

        with cooperative_read_cancellation(cancel_callback):
            connection = connect_read_only_sqlite(db_path)
            try:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or query_only[0] != 1:
                    raise _AdapterIssue("rejected", "sqlite_query_only_required")
                connection.execute("BEGIN")
                check_source_stable()
                check_read_cancelled()
                table_rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
                    (table_name,),
                ).fetchall()
                if len(table_rows) != 1:
                    raise _AdapterIssue("unknown", "market_indices_table_missing")
                table_name = str(table_rows[0][0])
                info = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
                if not info:
                    raise _AdapterIssue("unknown", "market_indices_schema_missing")
                schema_columns = [
                    {
                        "cid": int(item[0]),
                        "name": str(item[1]),
                        "type": str(item[2] or ""),
                        "notnull": int(item[3]),
                        "default": None if item[4] is None else str(item[4]),
                        "primary_key_position": int(item[5]),
                    }
                    for item in info
                ]
                if len(schema_columns) > 128:
                    raise _AdapterIssue("unknown", "market_indices_schema_too_wide")
                check_source_stable()
                columns = tuple(item["name"] for item in schema_columns)
                if {"__sqlite_types__", "__sqlite_real_identities__"} & set(columns):
                    raise _AdapterIssue("rejected", "market_indices_reserved_column_collision")
                name_column = _one_column(columns, "name")
                date_column = _one_column(columns, "date")
                price_columns = tuple(
                    column for semantic in ("close_index", "close_price")
                    for column in _find_columns(columns, semantic)
                )
                if name_column is None or date_column is None or not price_columns:
                    raise _AdapterIssue("unknown", "market_indices_required_schema_missing")
                metadata_columns = {
                    field_name: _find_columns(columns, field_name)
                    for field_name in (
                        "currency", "unit", "price_basis", "corporate_action_basis", "available_date"
                    )
                }
                if read_dates:
                    raw_dates = tuple(dict.fromkeys(alias for day in read_dates for alias in _date_aliases(day)))
                    selected = ", ".join(
                        f"typeof({_quote_identifier(column)}) AS t{index}, "
                        f"substr(CAST({_quote_identifier(column)} AS TEXT), 1, 4097) AS v{index}, "
                        f"CASE WHEN typeof({_quote_identifier(column)})='real' "
                        f"THEN printf('%!.26g', {_quote_identifier(column)}) END AS r{index}"
                        for index, column in enumerate(columns)
                    )
                    placeholders = ", ".join("?" for _ in raw_dates)
                    sql = (
                        f"SELECT {selected} FROM {_quote_identifier(table_name)} "
                        f"WHERE CAST({_quote_identifier(name_column)} AS TEXT)=? "
                        f"AND CAST({_quote_identifier(date_column)} AS TEXT) IN ({placeholders}) "
                        "LIMIT ?"
                    )
                    fetched = connection.execute(
                        sql, (benchmark_name, *raw_dates, len(read_dates) + 1)
                    ).fetchall()
                    check_read_cancelled()
                    for fetched_row in fetched:
                        values: dict[str, str | None] = {}
                        sqlite_types: dict[str, str] = {}
                        sqlite_real_identities: dict[str, str | None] = {}
                        for index, column in enumerate(columns):
                            offset = index * 3
                            sqlite_types[column] = str(fetched_row[offset] or "")
                            value = fetched_row[offset + 1]
                            if isinstance(value, str) and len(value) > 4096:
                                raise _AdapterIssue("rejected", "source_row_value_too_long")
                            values[column] = value
                            real_identity = fetched_row[offset + 2]
                            if sqlite_types[column] == "real":
                                sqlite_real_identities[column] = str(real_identity)
                        row: dict[str, Any] = {
                            **values,
                            "__sqlite_types__": sqlite_types,
                            "__sqlite_real_identities__": sqlite_real_identities,
                        }
                        observed_name = row[name_column]
                        if observed_name is None or observed_name.strip() != benchmark_name:
                            raise _AdapterIssue("rejected", "benchmark_name_exact_match_failed")
                        observed_day = _date(row[date_column], "source_trade_date")
                        if observed_day not in rows_by_date:
                            raise _AdapterIssue("rejected", "source_date_outside_exact_request")
                        rows_by_date[observed_day].append(row)
                    if len(fetched) > len(read_dates):
                        raise _AdapterIssue("rejected", "benchmark_endpoint_duplicate")
                    check_source_stable()
            finally:
                try:
                    connection.rollback()
                finally:
                    connection.close()
        check_source_stable()

        schema_sha256 = _sha256(schema_columns)
        rowset_material = {
            "adapter_version": ADAPTER_VERSION,
            "database_path": resolved_db_path,
            "source_identity": source_identity,
            "table": table_name,
            "schema_sha256": schema_sha256,
            "benchmark_name": benchmark_name,
            "typed_rows": sorted(
                (row for day_rows in rows_by_date.values() for row in day_rows),
                key=_raw_row_json,
            ),
        }
        observed_rowset_sha256 = _sha256(rowset_material)
        decision_rows = rows_by_date.get(decision, [])
        if len(decision_rows) == 1:
            observed_decision_row_sha256 = _sha256(
                {
                    "database_path": resolved_db_path,
                    "source_identity": source_identity,
                    "table": table_name,
                    "schema_sha256": schema_sha256,
                    "benchmark_name": benchmark_name,
                    "decision_date": decision,
                    "row": decision_rows[0],
                }
            )

        contract = {
            "adapter_version": ADAPTER_VERSION,
            "qualification_scope": QUALIFICATION_SCOPE,
            "database_path": resolved_db_path,
            "caller_source_identity": source_identity,
            "table": table_name,
            "schema_sha256": schema_sha256,
            "observed_rowset_sha256": observed_rowset_sha256,
            "observed_decision_row_sha256": observed_decision_row_sha256,
            "benchmark_name": benchmark_name,
            "decision_date": decision,
            "endpoint_dates": sorted(endpoints),
            "as_of_date": as_of,
            "source_metadata": declared,
            "target_metadata": target,
            "availability_by_date": {day: availability.get(day) for day in sorted(endpoints)},
            "historical_pit_eligible": False,
            "formal_eligible": False,
            "training_eligible": False,
            "trading_eligible": False,
            "execution_eligible": False,
            "natural_authority": False,
        }
        source_contract_json = _canonical_json(contract)
        source_contract_sha256 = hashlib.sha256(source_contract_json.encode("utf-8")).hexdigest()

        if expected_rowset is not None and expected_rowset != observed_rowset_sha256:
            raise _AdapterIssue("rejected", "rowset_revision_mismatch")
        if expected_decision is not None:
            if decision not in read_dates:
                unknown_codes.append("decision_row_not_observed")
            elif observed_decision_row_sha256 is None or expected_decision != observed_decision_row_sha256:
                raise _AdapterIssue("rejected", "decision_row_revision_mismatch")
        elif decision in read_dates and len(decision_rows) != 1:
            unknown_codes.append("decision_row_missing_or_duplicate")

        benchmark_prices: list[PricePoint] = []
        for day in sorted(endpoints):
            if day not in read_dates:
                continue
            found = rows_by_date.get(day, [])
            if not found:
                unknown_codes.append(f"benchmark_row_{day}_missing")
                continue
            if len(found) != 1:
                raise _AdapterIssue("rejected", f"benchmark_row_{day}_duplicate")
            row = found[0]
            _source_metadata_matches(
                row,
                metadata_columns,
                declared,
                availability.get(day),
                day,
                as_of,
                unknown_codes,
            )
            if any(value is None for value in declared.values()):
                # Metadata 缺件時仍驗查精確價格，但不建立可用 PricePoint。
                _price_from_row(row, price_columns)
                continue
            try:
                price = _price_from_row(row, price_columns)
                currency = declared["currency"]
                unit = declared["unit"]
                price_basis = declared["price_basis"]
                corporate_action_basis = declared["corporate_action_basis"]
                assert currency is not None and unit is not None
                assert price_basis is not None and corporate_action_basis is not None
                point = PricePoint(
                    instrument_id=f"market_indices.{benchmark_name}",
                    trade_date=day,
                    state="available",
                    price=price,
                    source_identity=f"{ADAPTER_VERSION}:{source_contract_sha256}",
                    currency=currency,
                    unit=unit,
                    price_basis=price_basis,
                    corporate_action_basis=corporate_action_basis,
                    available_date=availability.get(day),
                )
            except ForwardOutcomeError as error:
                raise _AdapterIssue("rejected", f"price_point_{error.code}") from error
            except TypeError as error:
                raise _AdapterIssue("unknown", "benchmark_metadata_incomplete") from error
            benchmark_prices.append(point)

        if len(decision_rows) != 1 and decision in read_dates:
            unknown_codes.append("decision_row_missing_or_duplicate")
        if expected_rowset is None:
            # 即使觀測資料完整，也要求呼叫者以第二次請求明示 pin。
            if "rowset_pin_required" not in unknown_codes:
                unknown_codes.append("rowset_pin_required")
        if expected_decision is None and "decision_row_pin_required" not in unknown_codes:
            unknown_codes.append("decision_row_pin_required")

        # 呼叫者宣告的 metadata 必須完整且可比較，才輸出基準與價格點。
        if unknown_codes:
            check_source_stable()
            return _result(
                "unknown", unknown_codes,
                rowset_sha256=observed_rowset_sha256,
                decision_row_sha256=observed_decision_row_sha256,
                contract_sha256=source_contract_sha256,
                contract_json=source_contract_json,
                observed_at=observed_at_text,
            )

        check_source_stable()
        currency = declared["currency"]
        unit = declared["unit"]
        price_basis = declared["price_basis"]
        corporate_action_basis = declared["corporate_action_basis"]
        assert currency is not None and unit is not None
        assert price_basis is not None and corporate_action_basis is not None
        spec = BenchmarkSpec(
            instrument_id=f"market_indices.{benchmark_name}",
            currency=currency,
            unit=unit,
            price_basis=price_basis,
            corporate_action_basis=corporate_action_basis,
            source_identity=f"{ADAPTER_VERSION}:{source_contract_sha256}",
        )
        return _result(
            "qualified_research", (),
            rowset_sha256=observed_rowset_sha256,
            decision_row_sha256=observed_decision_row_sha256,
            contract_sha256=source_contract_sha256,
            contract_json=source_contract_json,
            observed_at=observed_at_text,
            benchmark=spec,
            prices=benchmark_prices,
        )
    except _AdapterIssue as error:
        return _result(
            error.status,
            (error.code,),
            rowset_sha256=observed_rowset_sha256,
            decision_row_sha256=observed_decision_row_sha256,
            contract_sha256=source_contract_sha256,
            contract_json=source_contract_json,
            observed_at=observed_at_text,
        )
    except (FileNotFoundError, sqlite3.Error, ReadOperationCancelled) as error:
        code = "cancelled" if isinstance(error, ReadOperationCancelled) else "source_read_unavailable"
        return _result(
            "unknown",
            (code,),
            rowset_sha256=observed_rowset_sha256,
            decision_row_sha256=observed_decision_row_sha256,
            contract_sha256=source_contract_sha256,
            contract_json=source_contract_json,
            observed_at=observed_at_text,
        )
