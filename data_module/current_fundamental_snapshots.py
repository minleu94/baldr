"""官方基本面現況快照；抓取時間不是歷史公告時間，不供 PIT 因子使用。"""

from __future__ import annotations

import csv
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
import sqlite3

from utils.monthly_revenue_identity import (
    MONTHLY_NORMALIZER_VERSION,
    MONTHLY_SNAPSHOT_SOURCE,
    MONTHLY_YOY_COMPARATOR_VERSION,
    OPENAPI_MONTHLY_NORMALIZER_VERSION,
    OPENAPI_MONTHLY_SOURCE_IDS,
    derived_monthly_source_version as _derived_monthly_source_version,
    derived_monthly_yoy_comparator_version as _derived_monthly_yoy_comparator_version,
    is_monthly_derived_source_version as _is_monthly_derived_source_version,
    is_monthly_source_version as _is_monthly_source_version,
    is_monthly_yoy_comparator_source_version as _is_monthly_yoy_comparator_source_version,
    monthly_source_available_at as _monthly_source_available_at,
    monthly_source_version_parts as _monthly_source_version_parts,
    parse_utc_timestamp as _parse_utc_timestamp,
)


TABLE = "fundamental_current_observations"
PERIOD_BASES = frozenset(
    {"unknown", "monthly_flow", "year_to_date_cumulative", "period_end"}
)
MONTHLY_YOY_COMPARATOR_ITEM_CODE = "revenue_yoy_comparator"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    stock_code TEXT NOT NULL,
    kind TEXT NOT NULL,
    period TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    market TEXT NOT NULL,
    period_basis TEXT NOT NULL DEFAULT 'unknown'
        CHECK (period_basis IN ('unknown', 'monthly_flow', 'year_to_date_cumulative', 'period_end')),
    basis_verified INTEGER NOT NULL DEFAULT 0 CHECK (basis_verified IN (0, 1)),
    aggregate_feature_eligible INTEGER NOT NULL DEFAULT 0
        CHECK (aggregate_feature_eligible IN (0, 1)),
    source_available_at TEXT,
    PRIMARY KEY(stock_code, kind, period, item_code, source_version)
);
"""
COLUMNS = (
    "stock_code",
    "kind",
    "period",
    "as_of_date",
    "item_code",
    "item_name",
    "value",
    "unit",
    "observed_at",
    "source",
    "source_version",
    "market",
    "period_basis",
    "basis_verified",
    "aggregate_feature_eligible",
    "source_available_at",
)


def ensure_current_observation_schema(connection: sqlite3.Connection) -> None:
    """在受控寫入交易內新增或相容升級現況表，舊列一律預設未驗證。"""
    connection.execute(SCHEMA)
    existing = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({TABLE})").fetchall()
    }
    additions = (
        (
            "period_basis",
            "TEXT NOT NULL DEFAULT 'unknown' "
            "CHECK (period_basis IN ('unknown', 'monthly_flow', "
            "'year_to_date_cumulative', 'period_end'))",
        ),
        (
            "basis_verified",
            "INTEGER NOT NULL DEFAULT 0 CHECK (basis_verified IN (0, 1))",
        ),
        (
            "aggregate_feature_eligible",
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (aggregate_feature_eligible IN (0, 1))",
        ),
        ("source_available_at", "TEXT"),
    )
    for name, declaration in additions:
        if name not in existing:
            connection.execute(
                f"ALTER TABLE {TABLE} ADD COLUMN {name} {declaration}"
            )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_current_fundamental_lookup "
        f"ON {TABLE}(stock_code, kind, period DESC, observed_at DESC)"
    )


def monthly_snapshot_rows(
    path: Path,
    *,
    verified_source_versions: frozenset[str] | set[str] = frozenset(),
) -> list[dict[str, str]]:
    """將月營收轉成 Decimal 新台幣；只有 CSV 與官方 HTML 逐列及雜湊相符才標明月流量基礎。"""
    records: list[dict[str, str]] = []
    keys: set[tuple[str, str]] = set()
    verified_at = datetime.now(timezone.utc).isoformat()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            code, period = row["stock_code"], row["period"]
            if not re.fullmatch(r"\d{4,6}", code) or not re.fullmatch(
                r"\d{4}-\d{2}", period
            ):
                raise ValueError("invalid monthly snapshot identity")
            year, month = map(int, period.split("-"))
            end = date(year, month, monthrange(year, month)[1])
            observed = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
            if observed.tzinfo is None or observed > datetime.now(timezone.utc):
                raise ValueError("snapshot observation must be timezone-aware and not future")
            if end > observed.date():
                raise ValueError("monthly period ends after observation")
            amount = Decimal(row["current_month_revenue"].replace(",", ""))
            if not amount.is_finite():
                raise ValueError("non-finite revenue")
            key = (code, period)
            if key in keys:
                raise ValueError(f"duplicate monthly snapshot key: {key}")
            keys.add(key)
            version = row["source_version"].strip()
            market = row["market"]
            source = row["source"]
            if not version or market not in {"twse", "tpex"}:
                raise ValueError("missing source version or unknown market")
            if source in OPENAPI_MONTHLY_SOURCE_IDS.values() and source != OPENAPI_MONTHLY_SOURCE_IDS[market]:
                raise ValueError("OpenData source identity does not match market")

            verified = (
                version in verified_source_versions
                and source in {MONTHLY_SNAPSHOT_SOURCE, *OPENAPI_MONTHLY_SOURCE_IDS.values()}
                and _is_monthly_source_version(version, market=market, period=period)
            )
            if source in OPENAPI_MONTHLY_SOURCE_IDS.values():
                raise ValueError(
                    "OpenData 月營收須由具名 batch adapter 與可信單位 proof 正規化"
                )
            source_available_at = (
                _monthly_source_available_at(version, market=market, period=period)
                if verified
                else ""
            )
            normalized_value = str(amount * Decimal(1000))
            derived_version = (
                _derived_monthly_source_version(
                    version,
                    stock_code=code,
                    period=period,
                    value=normalized_value,
                    unit="TWD",
                    source_available_at=source_available_at,
                )
                if verified
                else version
            )
            records.append(
                {
                    "stock_code": code,
                    "kind": "monthly_revenue",
                    "period": period,
                    "as_of_date": end.isoformat(),
                    "item_code": "revenue",
                    "item_name": "月營收:單月",
                    "value": normalized_value,
                    "unit": "TWD",
                    "observed_at": verified_at,
                    "source": source,
                    "source_version": derived_version,
                    "market": market,
                    "period_basis": "monthly_flow" if verified else "unknown",
                    "basis_verified": "1" if verified else "0",
                    "aggregate_feature_eligible": "0",
                    "source_available_at": source_available_at,
                }
            )
            # Keep MOPS' same-report prior-year value as a current-observation
            # comparator; it is never a historical publication or PIT row.
            if verified:
                prior_raw_text = str(row.get("previous_year_month_revenue") or "").strip()
                if prior_raw_text:
                    prior_amount = Decimal(prior_raw_text.replace(",", ""))
                    if not prior_amount.is_finite():
                        raise ValueError("non-finite prior-year comparator")
                    if prior_amount > 0:
                        prior_period = f"{year - 1:04d}-{month:02d}"
                        prior_end = date(
                            year - 1,
                            month,
                            monthrange(year - 1, month)[1],
                        )
                        prior_value = str(prior_amount * Decimal(1000))
                        records.append(
                            {
                                "stock_code": code,
                                "kind": "monthly_revenue",
                                "period": prior_period,
                                "as_of_date": prior_end.isoformat(),
                                "item_code": MONTHLY_YOY_COMPARATOR_ITEM_CODE,
                                "item_name": "same-report prior-year monthly revenue comparator",
                                "value": prior_value,
                                "unit": "TWD",
                                "observed_at": verified_at,
                                "source": source,
                                "source_version": _derived_monthly_yoy_comparator_version(
                                    version,
                                    stock_code=code,
                                    source_period=period,
                                    comparator_period=prior_period,
                                    value=prior_value,
                                    unit="TWD",
                                    source_available_at=source_available_at,
                                ),
                                "market": market,
                                "period_basis": "monthly_flow",
                                "basis_verified": "1",
                                "aggregate_feature_eligible": "0",
                                "source_available_at": source_available_at,
                            }
                        )
    if not records:
        raise ValueError("empty monthly snapshot")
    return records


def insert_observations(
    connection: sqlite3.Connection, records: list[dict[str, str]]
) -> int:
    """Append immutable current observations; never promotes them to PIT."""
    normalized_records = [normalize_current_observation(row) for row in records]
    if not normalized_records:
        return 0
    ensure_current_observation_schema(connection)
    before = connection.total_changes
    immutable_columns = tuple(column for column in COLUMNS if column != "observed_at")
    for row in normalized_records:
        existing = connection.execute(
            f"SELECT {','.join(immutable_columns)} FROM {TABLE} "
            "WHERE stock_code=? AND kind=? AND period=? AND item_code=? AND source_version=?",
            tuple(
                row[column]
                for column in (
                    "stock_code",
                    "kind",
                    "period",
                    "item_code",
                    "source_version",
                )
            ),
        ).fetchone()
        expected = tuple(
            int(row[column])
            if column in {"basis_verified", "aggregate_feature_eligible"}
            else row[column]
            for column in immutable_columns
        )
        if existing is not None:
            existing = tuple(
                "" if column == "source_available_at" and value is None else value
                for column, value in zip(immutable_columns, existing)
            )
        if existing is not None and tuple(existing) != expected:
            raise ValueError("same source version contains conflicting observation values")
    connection.executemany(
        f"INSERT OR IGNORE INTO {TABLE} ({','.join(COLUMNS)}) "
        f"VALUES ({','.join('?' for _ in COLUMNS)})",
        [
            tuple(
                None if column == "source_available_at" and row[column] == "" else row[column]
                for column in COLUMNS
            )
            for row in normalized_records
        ],
    )
    return connection.total_changes - before


def normalize_current_observation(row: dict[str, str]) -> dict[str, str]:
    """以保守預設正規化欄位，並核對期間基礎宣告與來源版本。"""
    normalized = {column: str(row.get(column, "")) for column in COLUMNS}
    normalized["period_basis"] = str(row.get("period_basis") or "unknown")
    normalized["basis_verified"] = str(row.get("basis_verified", "0"))
    normalized["aggregate_feature_eligible"] = str(
        row.get("aggregate_feature_eligible", "0")
    )
    normalized["source_available_at"] = str(row.get("source_available_at") or "")
    if normalized["period_basis"] not in PERIOD_BASES:
        raise ValueError("unknown current-observation period_basis")
    if normalized["basis_verified"] not in {"0", "1"}:
        raise ValueError("basis_verified must be exactly 0 or 1")
    if normalized["aggregate_feature_eligible"] not in {"0", "1"}:
        raise ValueError("aggregate_feature_eligible must be exactly 0 or 1")
    if normalized["aggregate_feature_eligible"] == "1" and normalized[
        "basis_verified"
    ] != "1":
        raise ValueError("aggregate eligibility requires verified period basis")
    source_available_at = normalized["source_available_at"]
    if source_available_at:
        source_time = _parse_utc_timestamp(source_available_at, "source_available_at")
        observed_time = _parse_utc_timestamp(normalized["observed_at"], "observed_at")
        if source_time > observed_time:
            raise ValueError("source_available_at cannot be after local observed_at")
        if source_time > datetime.now(timezone.utc):
            raise ValueError("source_available_at cannot be in the future")
    if normalized["basis_verified"] == "1":
        _validate_verified_basis_source(normalized)
    return normalized


def _validate_verified_basis_source(row: dict[str, str]) -> None:
    source = row["source"]
    version = row["source_version"]
    if source in {MONTHLY_SNAPSHOT_SOURCE, *OPENAPI_MONTHLY_SOURCE_IDS.values()}:
        raw_version = version
        derived_match = re.fullmatch(
            r"(?:mops-current-revenue-normalizer\.v2|"
            r"twse-tpex-openapi-monthly-revenue-parser\.v1):"
            r"(?:twse|tpex):\d{4}-\d{2}:raw:(.+):derived:sha256:[0-9a-f]{64}",
            version,
        )
        if derived_match is not None:
            raw_version = derived_match.group(1)
        if source in OPENAPI_MONTHLY_SOURCE_IDS.values():
            if (
                source != OPENAPI_MONTHLY_SOURCE_IDS.get(row["market"])
                or not raw_version.startswith(f"{source}.v1:{row['market']}:")
            ):
                raise ValueError("OpenData verified basis source and market do not match")
        elif raw_version.startswith(tuple(f"{item}.v1:" for item in OPENAPI_MONTHLY_SOURCE_IDS.values())):
            raise ValueError("MOPS verified basis cannot bind an OpenData raw source")
        common_valid = (
            row["kind"] == "monthly_revenue"
            and row["period_basis"] == "monthly_flow"
            and row["aggregate_feature_eligible"] == "0"
            and row["unit"] == "TWD"
        )
        if row["item_code"] == "revenue":
            valid = common_valid and _is_monthly_derived_source_version(
                version,
                market=row["market"],
                period=row["period"],
                stock_code=row["stock_code"],
                value=row["value"],
                unit=row["unit"],
                source_available_at=row["source_available_at"],
            )
        elif row["item_code"] == MONTHLY_YOY_COMPARATOR_ITEM_CODE:
            valid = common_valid and _is_monthly_yoy_comparator_source_version(
                version,
                market=row["market"],
                comparator_period=row["period"],
                stock_code=row["stock_code"],
                value=row["value"],
                unit=row["unit"],
                source_available_at=row["source_available_at"],
            )
        else:
            valid = False
        if not valid:
            raise ValueError("月流量基礎需要相符的官方原始雜湊與正規化版本")
        return

    statement = source.removeprefix("mops.current_statement_html.")
    match = re.fullmatch(
        r"mops-current-statement-html\.v3:(twse|tpex):"
        r"(income|balance|cashflow):sha256:[0-9a-f]{64}:captured_at:(.+)",
        version,
    )
    if not source.startswith("mops.current_statement_html.") or match is None:
        raise ValueError("verified basis requires a recognized, hashed MOPS source")
    if match.group(1) != row["market"] or match.group(2) != statement:
        raise ValueError("verified basis source does not match market or statement")
    capture_marker = match.group(3)
    if capture_marker == "unknown":
        if row["source_available_at"]:
            raise ValueError("unknown source capture time must remain unavailable")
    elif (
        not row["source_available_at"]
        or _parse_utc_timestamp(capture_marker, "version capture time").isoformat()
        != row["source_available_at"]
    ):
        raise ValueError("MOPS source version capture time differs from source_available_at")
    expected = {
        "income": "year_to_date_cumulative",
        "balance": "period_end",
    }.get(statement)
    if (
        expected is None
        or row["kind"] != "statement_item"
        or not row["item_code"].startswith(
            "income_statement:" if statement == "income" else "balance_sheet:"
        )
        or row["period_basis"] != expected
        or row["aggregate_feature_eligible"] != "0"
    ):
        raise ValueError("MOPS statement basis claim is inconsistent with source type")
