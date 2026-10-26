from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PACIFIC = ZoneInfo("America/Los_Angeles")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.evidence_weekly_collection_repository import EvidenceWeeklyCollectionRepository
from data_module.official_daily_price_custody import MAX_RESPONSE_BYTES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect V2.2 weekly evidence into an append-only sidecar for human review."
    )
    parser.add_argument("--source-db-path", required=True)
    parser.add_argument("--sidecar-db-path", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--period-end")
    parser.add_argument("--json-output", action="store_true")
    return parser.parse_args()


def _period_bounds(period_end_value: str | None) -> tuple[str, str]:
    if period_end_value:
        period_end = date.fromisoformat(period_end_value)
    else:
        # 週排程為週日 Pacific；該時刻台北已是週一，故固定取最近已結束週日。
        local_today = datetime.now(PACIFIC).date()
        days_since_sunday = (local_today.weekday() + 1) % 7
        period_end = local_today - timedelta(days=days_since_sunday)
    period_start = period_end - timedelta(days=period_end.weekday())
    return period_start.isoformat(), period_end.isoformat()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _indexed_date_range_predicate(date_column: str) -> str:
    """用原始日期欄做範圍篩選，讓 SQLite 可使用既有日期索引。"""

    return (
        f"({date_column} BETWEEN ? AND ? OR "
        f"{date_column} BETWEEN ? AND ?)"
    )


def _verified_twse_daily_rows(
    source_db_path: Path,
    *,
    period_start: str,
    period_end: str,
    target_symbols: set[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """讀取並驗證同日 TWSE 原始封存；封存缺件或互相矛盾時不猜。"""

    if not target_symbols:
        return {}
    resolved_source = source_db_path.resolve()
    if resolved_source.parent.name.casefold() == "sqlite":
        data_root = resolved_source.parent.parent
    else:
        data_root = resolved_source.parent
    custody_root = (
        data_root
        / "output"
        / "scheduled"
        / "daily_price_source_custody"
        / "twse"
    )
    result: dict[tuple[str, str], dict[str, Any]] = {}
    current_day = date.fromisoformat(period_start)
    last_day = date.fromisoformat(period_end)
    while current_day <= last_day:
        date_key = current_day.strftime("%Y%m%d")
        day_directory = custody_root / date_key
        current_day += timedelta(days=1)
        if not day_directory.is_dir():
            continue
        receipts: dict[str, tuple[Path, dict[str, Any]]] = {}
        try:
            receipt_paths = tuple(day_directory.glob("*/receipt.json"))
        except OSError:
            continue
        for receipt_path in receipt_paths:
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("source_id") != "twse.mi_index.daily_price"
                    or receipt.get("source_authority") != "twse"
                    or receipt.get("source_date") != f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                ):
                    continue
                response = receipt.get("response")
                if not isinstance(response, dict) or response.get("http_status") != 200:
                    continue
                receipt_body = {
                    key: value for key, value in receipt.items() if key != "content_sha256"
                }
                receipt_content_hash = "sha256:" + hashlib.sha256(
                    json.dumps(
                        receipt_body,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if receipt.get("content_sha256") != receipt_content_hash:
                    continue
                raw_path = receipt_path.parent / "raw_response.bin"
                if raw_path.stat().st_size > MAX_RESPONSE_BYTES:
                    continue
                raw_bytes = raw_path.read_bytes()
                digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
                if (
                    receipt.get("raw_response_sha256") != digest
                    or receipt.get("raw_response_bytes") != len(raw_bytes)
                    or not raw_bytes
                ):
                    continue
                payload = json.loads(raw_bytes.decode("utf-8-sig"))
                if not isinstance(payload, dict) or not isinstance(payload.get("tables"), list):
                    continue
                selected: dict[tuple[str, str], dict[str, Any]] = {}
                for table in payload["tables"]:
                    if not isinstance(table, dict):
                        continue
                    fields = table.get("fields")
                    table_rows = table.get("data")
                    if (
                        not isinstance(fields, list)
                        or not isinstance(table_rows, list)
                        or not {"證券代號", "開盤價", "最高價", "最低價", "收盤價"}.issubset(fields)
                    ):
                        continue
                    indexes = {str(field): index for index, field in enumerate(fields)}
                    for source_row in table_rows:
                        if not isinstance(source_row, list) or len(source_row) < len(fields):
                            continue
                        symbol = str(source_row[indexes["證券代號"]]).strip()
                        if not symbol or symbol not in target_symbols:
                            continue
                        selected[(date_key, symbol)] = {
                            field: str(source_row[indexes[field]]).strip()
                            for field in ("開盤價", "最高價", "最低價", "收盤價")
                        }
                receipts[digest] = (receipt_path, selected)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                continue
        # 同一交易日若有不同官方 response，必須另行調查，不能挑一份當權威。
        if len(receipts) != 1:
            continue
        digest, (receipt_path, rows) = next(iter(receipts.items()))
        for key, official_values in rows.items():
            result[key] = {
                "ohlc": official_values,
                "receipt_sha256": digest,
                "receipt_path": str(receipt_path.resolve()),
            }
    return result


def _read_weekly_source_coverage(
    source_db_path: Path,
    *,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    """Capture observed daily-price coverage without inferring a denominator."""

    source_uri = f"{source_db_path.resolve().as_uri()}?mode=ro"
    period_start_key = period_start.replace("-", "")
    period_end_key = period_end.replace("-", "")
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.execute("PRAGMA query_only = ON")
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(daily_prices)").fetchall()
        }
        missing_identity = sorted({"日期", "證券代號"} - columns)
        if missing_identity:
            raise ValueError(
                "daily_prices missing required identity columns: "
                + ", ".join(missing_identity)
            )

        date_column = _quote_identifier("日期")
        symbol_column = _quote_identifier("證券代號")
        date_expression = f"REPLACE(TRIM(CAST({date_column} AS TEXT)), '-', '')"
        date_range_predicate = _indexed_date_range_predicate(date_column)
        date_range_parameters = (
            period_start_key,
            period_end_key,
            period_start,
            period_end,
        )
        symbol_expression = f"TRIM(CAST({symbol_column} AS TEXT))"
        required_value_fields = ("開盤價", "最高價", "最低價", "收盤價")
        activity_fields = ("成交股數", "成交筆數", "成交金額")
        available_activity_fields = [field for field in activity_fields if field in columns]
        available_value_fields = [
            field for field in required_value_fields if field in columns
        ]
        missing_value_fields = [
            field for field in required_value_fields if field not in columns
        ]
        null_count_expressions = [
            "SUM(CASE WHEN "
            f"{_quote_identifier(field)} IS NULL OR "
            f"TRIM(CAST({_quote_identifier(field)} AS TEXT)) = '' "
            "THEN 1 ELSE 0 END) "
            f"AS {_quote_identifier('missing_' + field)}"
            for field in available_value_fields
        ]
        null_count_sql = (
            ", " + ", ".join(null_count_expressions)
            if null_count_expressions
            else ""
        )
        rows = connection.execute(
            f"""
            SELECT {date_expression} AS trading_date,
                   COUNT(*) AS row_count,
                   COUNT(DISTINCT {symbol_expression}) AS symbol_count
                   {null_count_sql}
            FROM daily_prices
            WHERE {date_range_predicate}
            GROUP BY {date_expression}
            ORDER BY {date_expression}
            """,
            date_range_parameters,
        ).fetchall()
        value_columns = [
            _quote_identifier(field) for field in available_value_fields
        ]
        incomplete_rows: list[tuple[Any, ...]] = []
        if available_value_fields:
            missing_value_predicates = [
                f"{_quote_identifier(field)} IS NULL OR "
                f"TRIM(CAST({_quote_identifier(field)} AS TEXT)) = ''"
                for field in available_value_fields
            ]
            incomplete_rows = connection.execute(
                f"""
                SELECT {date_expression}, {symbol_expression},
                       {", ".join(value_columns)}
                FROM daily_prices
                WHERE {date_range_predicate}
                  AND ({" OR ".join(missing_value_predicates)})
                ORDER BY {date_expression}, {symbol_expression}
                """,
                date_range_parameters,
            ).fetchall()
        incomplete_activity: dict[tuple[str, str], dict[str, Any]] = {}
        if available_value_fields and available_activity_fields:
            selected_activity_columns = ", ".join(
                _quote_identifier(field) for field in available_activity_fields
            )
            incomplete_activity_rows = connection.execute(
                f"""
                SELECT {date_expression}, {symbol_expression}, {selected_activity_columns}
                FROM daily_prices
                WHERE {date_range_predicate}
                  AND ({" OR ".join(missing_value_predicates)})
                ORDER BY {date_expression}, {symbol_expression}
                """,
                date_range_parameters,
            ).fetchall()
            for activity_row in incomplete_activity_rows:
                incomplete_activity[(str(activity_row[0]), str(activity_row[1]).strip())] = {
                    field: activity_row[index + 2]
                    for index, field in enumerate(available_activity_fields)
                }
        observed_symbol_count = int(
            connection.execute(
                f"""
                SELECT COUNT(DISTINCT {symbol_expression})
                FROM daily_prices
                WHERE {date_range_predicate}
                  AND {symbol_expression} <> ''
                """,
                date_range_parameters,
            ).fetchone()[0]
        )

    verified_twse_rows = _verified_twse_daily_rows(
        source_db_path,
        period_start=period_start,
        period_end=period_end,
        target_symbols={str(row[1] or "").strip() for row in incomplete_rows},
    )

    if not rows:
        raise ValueError(
            f"no daily_prices trading date inside {period_start}..{period_end}"
        )

    trading_days: list[dict[str, Any]] = []
    missing_value_counts = {field: 0 for field in available_value_fields}
    duplicate_symbol_rows = 0
    total_row_count = 0
    for row in rows:
        date_key = str(row[0] or "")
        if len(date_key) != 8 or not date_key.isdigit():
            raise ValueError(f"unsupported daily_prices date value: {date_key}")
        row_count = int(row[1])
        symbol_count = int(row[2])
        missing_values = {
            field: int(row[index + 3] or 0)
            for index, field in enumerate(available_value_fields)
        }
        for field, count in missing_values.items():
            missing_value_counts[field] += count
        day_duplicates = max(0, row_count - symbol_count)
        duplicate_symbol_rows += day_duplicates
        total_row_count += row_count
        trading_days.append(
            {
                "date": f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}",
                "row_count": row_count,
                "symbol_count": symbol_count,
                "duplicate_symbol_rows": day_duplicates,
                "missing_required_value_rows": missing_values,
            }
        )

    findings: list[str] = []
    if missing_value_fields:
        findings.append(
            "required_price_columns_missing:" + ",".join(missing_value_fields)
        )
    if duplicate_symbol_rows:
        findings.append("duplicate_symbol_rows_observed")
    if any(missing_value_counts.values()):
        findings.append("required_price_values_missing")
    integrity_examples = []
    integrity_classification_counts: dict[str, int] = {}
    for row in incomplete_rows:
        date_key = str(row[0] or "")
        symbol = str(row[1] or "").strip()
        missing_fields = [
            field
            for index, field in enumerate(available_value_fields)
            if row[index + 2] is None or str(row[index + 2]).strip() == ""
        ]
        official_row = verified_twse_rows.get((date_key, symbol))
        official_ohlc = official_row.get("ohlc", {}) if official_row else {}
        official_missing_fields = [
            field
            for field in missing_fields
            if official_ohlc.get(field) == "--"
        ]
        official_present_fields = [
            field
            for field in missing_fields
            if official_ohlc.get(field) not in (None, "", "--")
        ]
        if official_missing_fields and len(official_missing_fields) == len(missing_fields):
            classification = "official_source_reports_missing_values"
        elif official_present_fields:
            classification = "local_projection_missing_official_value"
        elif any(
            _positive_numeric(incomplete_activity.get((date_key, symbol), {}).get(field))
            for field in ("成交股數", "成交筆數", "成交金額")
        ):
            classification = "ohlc_missing_with_trade_activity_cause_unverified"
        else:
            classification = "ohlc_missing_source_cause_unverified"
        integrity_classification_counts[classification] = (
            integrity_classification_counts.get(classification, 0) + 1
        )
        if len(integrity_examples) >= 50:
            continue
        integrity_examples.append(
            {
                "date": (
                    f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                    if len(date_key) == 8 and date_key.isdigit()
                    else date_key
                ),
                "symbol": symbol,
                "missing_fields": missing_fields,
                "activity": incomplete_activity.get((date_key, symbol), {}),
                "classification": classification,
                "official_ohlc": official_ohlc,
                "official_receipt_sha256": (
                    official_row.get("receipt_sha256") if official_row else None
                ),
                "official_receipt_path": (
                    official_row.get("receipt_path") if official_row else None
                ),
            }
        )
    return {
        "status": "degraded" if findings else "observed_no_basic_integrity_gaps",
        "period_start": period_start,
        "period_end": period_end,
        "trading_day_count": len(trading_days),
        "last_trading_date": trading_days[-1]["date"],
        "observed_row_count": total_row_count,
        "observed_symbol_count": observed_symbol_count,
        "duplicate_symbol_rows": duplicate_symbol_rows,
        "available_required_price_columns": available_value_fields,
        "available_activity_columns": available_activity_fields,
        "missing_required_price_columns": missing_value_fields,
        "missing_required_price_values": missing_value_counts,
        "incomplete_row_count": len(incomplete_rows),
        "official_source_missing_value_rows": integrity_classification_counts.get(
            "official_source_reports_missing_values", 0
        ),
        "local_projection_missing_official_value_rows": integrity_classification_counts.get(
            "local_projection_missing_official_value", 0
        ),
        "unverified_missing_value_rows": (
            integrity_classification_counts.get(
                "ohlc_missing_with_trade_activity_cause_unverified", 0
            )
            + integrity_classification_counts.get(
                "ohlc_missing_source_cause_unverified", 0
            )
        ),
        "integrity_examples": integrity_examples,
        "integrity_examples_truncated": len(incomplete_rows) > len(integrity_examples),
        "verified_official_twse_dates": sorted(
            {
                key[0]
                for key in verified_twse_rows
            }
        ),
        "trading_days": trading_days,
        "coverage_basis": "observed_daily_prices_rows_only",
        "expected_universe_count": None,
        "full_coverage_claimed": False,
        "quality_findings": findings,
        "limitations": [
            "Observed row counts do not establish full-market or frozen-universe coverage.",
            "Official publication/available time and source license are not verified by this query.",
            "Missing OHLC is never repaired; without a verified same-date official response its source cause remains unknown.",
        ],
    }


def _positive_numeric(value: Any) -> bool:
    if value is None:
        return False
    try:
        return Decimal(str(value).replace(",", "").strip()) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _report_paths(output_root: Path, *, period_end: str) -> tuple[Path, Path]:
    report_directory = output_root / "scheduled" / "v2_2_weekly_collection"
    report_directory.mkdir(parents=True, exist_ok=True)
    suffix = period_end.replace("-", "")
    return (
        report_directory / f"v2_2_weekly_collection_{suffix}.json",
        report_directory / f"v2_2_weekly_collection_{suffix}.md",
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# V2.2 Weekly Evidence Collection",
        "",
        f"- Collection status: `{payload['collection_status']}`",
        f"- Period: `{payload['period_start']}` to `{payload['period_end']}`",
        f"- Last trading date: `{payload.get('last_trading_date', '')}`",
        "- Source access: `SQLite mode=ro`",
        "- Human approval required: `true`",
        "- Write intent: `false`",
        f"- Automatic revalidation: `{str(payload.get('automatic_revalidation', False)).lower()}`",
        f"- Gate credit status: `{payload.get('gate_credit_status', '')}`",
    ]
    coverage = payload.get("source_coverage")
    if isinstance(coverage, dict):
        lines.extend(
            [
                "",
                "## Observed source coverage (not full-universe coverage)",
                "",
                f"- Status: `{coverage.get('status', 'unknown')}`",
                f"- Trading dates: `{coverage.get('trading_day_count', 0)}`",
                f"- Observed rows: `{coverage.get('observed_row_count', 0)}`",
                f"- Duplicate symbol rows: `{coverage.get('duplicate_symbol_rows', 0)}`",
                f"- Expected universe count: `{coverage.get('expected_universe_count')}`",
                f"- Full coverage claimed: `{str(coverage.get('full_coverage_claimed', False)).lower()}`",
                f"- Official source reports missing OHLC: `{coverage.get('official_source_missing_value_rows', 'unknown')}`",
                f"- Local rows missing values present in official response: `{coverage.get('local_projection_missing_official_value_rows', 'unknown')}`",
                f"- Missing-value cause unverified: `{coverage.get('unverified_missing_value_rows', 'unknown')}`",
            ]
        )
        findings = coverage.get("quality_findings", [])
        if findings:
            lines.extend(["- Quality findings:", *[f"  - `{item}`" for item in findings]])
        examples = coverage.get("integrity_examples", [])
        if examples:
            lines.extend(["- Incomplete rows (date / symbol / missing fields):"])
            for item in examples:
                lines.append(
                    "  - `{date}` / `{symbol}` / `{fields}` / `{classification}` / official `{official}` / receipt `{receipt}` / activity `{activity}`".format(
                        date=item.get("date", "unknown"),
                        symbol=item.get("symbol", "unknown"),
                        fields=", ".join(item.get("missing_fields", [])) or "unknown",
                        classification=item.get("classification", "unknown"),
                        official=json.dumps(item.get("official_ohlc", {}), ensure_ascii=False, sort_keys=True),
                        receipt=item.get("official_receipt_sha256") or "unverified",
                        activity=json.dumps(item.get("activity", {}), ensure_ascii=False, sort_keys=True),
                    )
                )
            if coverage.get("integrity_examples_truncated"):
                lines.append("  - Additional incomplete rows were omitted; inspect the JSON artifact.")
        for limitation in coverage.get("limitations", []):
            lines.append(f"- Limitation: {limitation}")
    if payload.get("error"):
        error = payload["error"]
        lines.extend(["", "## Error", "", f"- Type: `{error['type']}`", f"- Message: {error['message']}"])
    return "\n".join(lines) + "\n"


def _write_reports(output_root: Path, payload: dict[str, Any]) -> None:
    json_path, markdown_path = _report_paths(output_root, period_end=str(payload["period_end"]))
    json_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")


def _base_payload(*, period_start: str, period_end: str, source_db_path: Path) -> dict[str, Any]:
    return {
        "period_start": period_start,
        "period_end": period_end,
        "source_db_path": str(source_db_path),
        "source_access": "sqlite_uri_mode_ro",
        "human_approval_required": True,
        "automatic_revalidation": False,
        "gate_credit_status": "pending_human_review",
        "source_write_allowed": False,
        "sidecar_append_allowed": True,
        "write_intent": False,
    }


def main() -> int:
    args = parse_args()
    source_db_path = Path(args.source_db_path)
    output_root = Path(args.output_root)
    repository = EvidenceWeeklyCollectionRepository(
        source_db_path,
        sidecar_path=Path(args.sidecar_db_path),
    )
    try:
        period_start, period_end = _period_bounds(args.period_end)
    except ValueError as error:
        period_start = str(args.period_end or date.today().isoformat())
        period_end = period_start
        payload = _base_payload(
            period_start=period_start,
            period_end=period_end,
            source_db_path=source_db_path,
        )
        payload.update(
            {
                "collection_status": "collection_failed",
                "error": {"type": type(error).__name__, "message": str(error)},
            }
        )
        record = repository.save_failed(
            period_start=period_start,
            period_end=period_end,
            payload_json=payload,
            error=error,
        )
        payload["collection_record"] = record.to_dict()
        _write_reports(output_root, payload)
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(_render_markdown(payload), end="")
        return 1

    payload = _base_payload(
        period_start=period_start,
        period_end=period_end,
        source_db_path=source_db_path,
    )
    pending_payload: dict[str, Any] | None = None
    try:
        source_coverage = _read_weekly_source_coverage(
            source_db_path,
            period_start=period_start,
            period_end=period_end,
        )
        payload["source_coverage"] = source_coverage
        payload["last_trading_date"] = str(source_coverage["last_trading_date"])
        pending_payload = dict(payload)
        record = repository.save_pending(
            period_start=period_start,
            period_end=period_end,
            payload_json=pending_payload,
        )
        payload["collection_status"] = record.status
        payload["storage_status"] = record.status
        payload["collection_record"] = record.to_dict()
        _write_reports(output_root, payload)
        exit_code = 0
    except Exception as error:
        payload["error"] = {"type": type(error).__name__, "message": str(error)}
        payload["collection_status"] = "collection_failed"
        record = repository.save_failed(
            period_start=period_start,
            period_end=period_end,
            payload_json=pending_payload if pending_payload is not None else payload,
            error=error,
        )
        payload["collection_status"] = record.status
        payload["collection_record"] = record.to_dict()
        exit_code = 1

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(_render_markdown(payload), end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
