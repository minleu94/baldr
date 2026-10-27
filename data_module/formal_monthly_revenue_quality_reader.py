"""唯讀彙總正式月營收公告日期品質，按資料期別呈現。"""

from __future__ import annotations

import re
import sqlite3
import stat
from pathlib import Path
from typing import Any


FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA = "baldr.formal_monthly_revenue_quality_by_period.v2"
FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA = (
    "baldr.formal_monthly_revenue_quality_rows.v2"
)
TABLE_NAME = "fundamental_monthly_revenues"
_REQUIRED_COLUMNS = frozenset(
    {"stock_code", "period", "announced_date", "source", "source_version"}
)
_REPORT_LEVEL_DATE_SOURCE_IDS = frozenset(
    {
        "mops.monthly_revenue_static_report",
        "mops.monthly_revenue_static_snapshot",
    }
)
_PERIOD_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])\Z")
DEFAULT_DETAIL_PAGE_SIZE = 100
MAX_DETAIL_PAGE_SIZE = 200
MAX_DETAIL_OFFSET = 1_000_000


def read_formal_monthly_revenue_quality_by_period(
    database_path: Path,
    availability_mapping_path: Path | None = None,
) -> dict[str, Any]:
    """唯讀回傳正式月營收資料按 period 分組的公告日期品質摘要。

    摘要只計正式表內列數、公告日期缺漏、尚未由精確正式 availability mapping
    核實的報表層級日期、公司數與來源版本數；不讀取營收值，也不執行修復、回填
    或資格判定。Mapping 無法讀取或有診斷時，相關日期維持待核實。
    """

    try:
        verified_mapping, _ = _load_verified_mops_snapshot_mappings(
            availability_mapping_path
        )
        rows = _read_period_aggregates(database_path, verified_mapping)
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return _unavailable("formal_monthly_revenue_database_or_schema_unavailable")

    return {
        "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA,
        "status": "observed",
        "periods": rows,
        "blockers": [],
        "scope": "formal_monthly_revenue_rows_grouped_by_period",
        "formal_db_write": False,
        "financial_values_returned": False,
    }


def read_formal_monthly_revenue_quality_missing_rows(
    database_path: Path,
    period: str,
    offset: int = 0,
    limit: int = DEFAULT_DETAIL_PAGE_SIZE,
    availability_mapping_path: Path | None = None,
) -> dict[str, Any]:
    """唯讀分頁列出公告日缺漏及報表日期待核實的公司與來源版本。

    僅回傳識別欄位、正式儲存日期及 MOPS mapping 的精確版本對照；不讀取營收值、
    不寫入正式資料庫。Mapping 缺失、讀取失敗或含診斷時維持 unknown，不推論為無匹配。
    """

    if (
        not isinstance(period, str)
        or _PERIOD_RE.fullmatch(period) is None
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or limit > MAX_DETAIL_PAGE_SIZE
        or isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or offset > MAX_DETAIL_OFFSET
    ):
        return _detail_unavailable("formal_monthly_revenue_quality_query_invalid")

    try:
        verified_mapping, mapping_status = _load_verified_mops_snapshot_mappings(
            availability_mapping_path
        )
        total_count, rows = _read_missing_details(
            database_path,
            period=period,
            limit=limit,
            offset=offset,
            verified_mops_mappings=verified_mapping,
            mapping_status=mapping_status,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return _detail_unavailable(
            "formal_monthly_revenue_database_or_schema_unavailable",
            period=period,
            limit=limit,
            offset=offset,
        )

    return {
        "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
        "status": "observed",
        "period": period,
        "rows": rows,
        "mapping_status": mapping_status,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total_count,
        "blockers": [],
        "scope": "formal_monthly_revenue_announcement_quality_identity_page",
        "formal_db_write": False,
        "financial_values_returned": False,
    }


def _read_missing_details(
    database_path: Path,
    *,
    period: str,
    limit: int,
    offset: int,
    verified_mops_mappings: dict[tuple[str, str, str], str],
    mapping_status: str,
) -> tuple[int, list[dict[str, Any]]]:
    requested_path = Path(database_path).expanduser()
    requested_stat = requested_path.lstat()
    if stat.S_ISLNK(requested_stat.st_mode) or getattr(
        requested_stat, "st_file_attributes", 0
    ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError("formal_database_reparse_point")
    path = requested_path.absolute()
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("formal_database_not_regular_file")

    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise ValueError("formal_database_query_only_readback_failed")

        table_type = connection.execute(
            'SELECT "type" FROM "sqlite_master" WHERE "name" = ?',
            (TABLE_NAME,),
        ).fetchone()
        if table_type is None or str(table_type[0]).lower() != "table":
            raise ValueError("formal_monthly_revenue_table_missing_or_not_table")

        table_info = connection.execute(f'PRAGMA table_info("{TABLE_NAME}")').fetchall()
        columns = {str(row[1]): row for row in table_info}
        if not _REQUIRED_COLUMNS.issubset(columns):
            raise ValueError("formal_monthly_revenue_schema_mismatch")
        if any(str(columns[name][2]).upper() != "TEXT" for name in _REQUIRED_COLUMNS):
            raise ValueError("formal_monthly_revenue_schema_mismatch")
        if any(
            int(columns[name][3]) != 1
            for name in ("stock_code", "period", "source_version")
        ):
            raise ValueError("formal_monthly_revenue_schema_mismatch")

        count_row = connection.execute(
            'SELECT COUNT(*) FROM "fundamental_monthly_revenues" '
            'WHERE "period" = ? AND (("announced_date" IS NULL '
            'OR TRIM("announced_date") = \'\') OR ("source" IN (?, ?) '
            'AND "announced_date" IS NOT NULL AND TRIM("announced_date") != \'\'))',
            (period, *tuple(sorted(_REPORT_LEVEL_DATE_SOURCE_IDS))),
        ).fetchone()
        total_count = int(count_row[0]) if count_row is not None else 0
        raw_rows = connection.execute(
            'SELECT "stock_code", "source", "source_version", "announced_date" '
            'FROM "fundamental_monthly_revenues" '
            'WHERE "period" = ? AND (("announced_date" IS NULL '
            'OR TRIM("announced_date") = \'\') OR ("source" IN (?, ?) '
            'AND "announced_date" IS NOT NULL AND TRIM("announced_date") != \'\')) '
            'ORDER BY "stock_code" ASC, "source" ASC, "source_version" ASC '
            'LIMIT ? OFFSET ?',
            (period, *tuple(sorted(_REPORT_LEVEL_DATE_SOURCE_IDS)), limit, offset),
        ).fetchall()

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        stock_code = row["stock_code"]
        source = row["source"]
        source_version = row["source_version"]
        stored_announced_date = row["announced_date"]
        if (
            not isinstance(stock_code, str)
            or not stock_code.strip()
            or not isinstance(source, str)
            or not source.strip()
            or not isinstance(source_version, str)
            or not source_version.strip()
            or (
                stored_announced_date is not None
                and not isinstance(stored_announced_date, str)
            )
        ):
            raise ValueError("formal_monthly_revenue_identity_invalid")
        is_report_level_date = (
            source in _REPORT_LEVEL_DATE_SOURCE_IDS
            and isinstance(stored_announced_date, str)
            and bool(stored_announced_date.strip())
        )
        announced_date = verified_mops_mappings.get(
            (stock_code, period, source_version)
        )
        if mapping_status != "verified":
            match_state = "unknown"
            announced_date = None
        elif announced_date is not None:
            if is_report_level_date:
                match_state = (
                    "exact_mapping_date_matches"
                    if announced_date == stored_announced_date
                    else "exact_mapping_date_differs"
                )
            else:
                match_state = "exact_version_mapping_present"
        else:
            match_state = "no_exact_version_mapping"
        rows.append(
            {
                "stock_code": stock_code,
                "source": source,
                "source_version": source_version,
                "stored_announced_date": stored_announced_date,
                "mapping_match_state": match_state,
                "mapping_announced_date": announced_date,
            }
        )
    return total_count, rows


def _load_verified_mops_snapshot_mappings(
    availability_mapping_path: Path | None,
) -> tuple[dict[tuple[str, str, str], str], str]:
    if availability_mapping_path is None:
        return {}, "not_configured"

    path = Path(availability_mapping_path)
    if not path.is_file():
        return {}, "unavailable"

    try:
        from data_module.fundamental_availability_sources import (
            load_monthly_revenue_availability_overrides_csv,
        )

        loaded = load_monthly_revenue_availability_overrides_csv(
            path
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}, "unavailable"
    if loaded.diagnostics:
        return {}, "invalid"

    result: dict[tuple[str, str, str], str] = {}
    for override in loaded.overrides.values():
        if (
            override.source != "mops.monthly_revenue_announcement"
            or override.provenance_mode != "formal_v2"
            or override.evidence_class != "official_announcement"
            or not override.source_hash.startswith("sha256:")
            or override.announced_date is None
            or override.target_source_version is None
        ):
            continue
        key = (
            override.stock_code,
            override.period,
            override.target_source_version,
        )
        announced_date = override.announced_date.isoformat()
        previous_date = result.get(key)
        if previous_date is not None and previous_date != announced_date:
            return {}, "invalid"
        result[key] = announced_date
    return result, "verified"


def _read_period_aggregates(
    database_path: Path,
    verified_mops_mappings: dict[tuple[str, str, str], str],
) -> list[dict[str, int | str]]:
    requested_path = Path(database_path).expanduser()
    requested_stat = requested_path.lstat()
    if stat.S_ISLNK(requested_stat.st_mode) or getattr(
        requested_stat, "st_file_attributes", 0
    ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError("formal_database_reparse_point")
    path = requested_path.absolute()
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("formal_database_not_regular_file")

    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise ValueError("formal_database_query_only_readback_failed")

        table_type = connection.execute(
            'SELECT "type" FROM "sqlite_master" WHERE "name" = ?',
            (TABLE_NAME,),
        ).fetchone()
        if table_type is None or str(table_type[0]).lower() != "table":
            raise ValueError("formal_monthly_revenue_table_missing_or_not_table")

        table_info = connection.execute(
            f'PRAGMA table_info("{TABLE_NAME}")'
        ).fetchall()
        columns = {str(row[1]): row for row in table_info}
        if not _REQUIRED_COLUMNS.issubset(columns):
            raise ValueError("formal_monthly_revenue_schema_mismatch")
        if any(str(columns[name][2]).upper() != "TEXT" for name in _REQUIRED_COLUMNS):
            raise ValueError("formal_monthly_revenue_schema_mismatch")
        if any(
            int(columns[name][3]) != 1
            for name in ("stock_code", "period", "source_version")
        ):
            raise ValueError("formal_monthly_revenue_schema_mismatch")

        raw_rows = connection.execute(
            'SELECT "period", COUNT(*) AS formal_row_count, '
            'SUM(CASE WHEN "announced_date" IS NULL '
            'OR TRIM("announced_date") = \'\' THEN 1 ELSE 0 END) '
            'AS missing_announcement_date_row_count, '
            'SUM(CASE WHEN "source" IN (?, ?) AND "announced_date" IS NOT NULL '
            'AND TRIM("announced_date") != \'\' THEN 1 ELSE 0 END) '
            'AS report_level_date_unverified_row_count, '
            'COUNT(DISTINCT "stock_code") AS distinct_stock_code_count, '
            'COUNT(DISTINCT "source_version") AS distinct_source_version_count, '
            'SUM(CASE WHEN typeof("stock_code") != \'text\' '
            'OR typeof("period") != \'text\' '
            'OR typeof("source") != \'text\' '
            'OR typeof("source_version") != \'text\' '
            'OR ("announced_date" IS NOT NULL '
            'AND typeof("announced_date") != \'text\') '
            'OR TRIM("stock_code") = \'\' '
            'OR TRIM("source") = \'\' '
            'OR TRIM("source_version") = \'\' THEN 1 ELSE 0 END) '
            'AS invalid_row_count '
            'FROM "fundamental_monthly_revenues" GROUP BY "period" '
            'ORDER BY "period" ASC',
            tuple(sorted(_REPORT_LEVEL_DATE_SOURCE_IDS)),
        ).fetchall()

        verified_by_period: dict[str, int] = {}
        if verified_mops_mappings:
            static_rows = connection.execute(
                'SELECT "stock_code", "period", "source_version", "announced_date" '
                'FROM "fundamental_monthly_revenues" '
                'WHERE "source" IN (?, ?) AND "announced_date" IS NOT NULL '
                'AND TRIM("announced_date") != \'\'',
                tuple(sorted(_REPORT_LEVEL_DATE_SOURCE_IDS)),
            ).fetchall()
            for item in static_rows:
                identity = (
                    str(item["stock_code"]),
                    str(item["period"]),
                    str(item["source_version"]),
                )
                if verified_mops_mappings.get(identity) == str(
                    item["announced_date"]
                ):
                    period_key = str(item["period"])
                    verified_by_period[period_key] = (
                        verified_by_period.get(period_key, 0) + 1
                    )

    result: list[dict[str, int | str]] = []
    for row in raw_rows:
        period = row["period"]
        if not isinstance(period, str) or _PERIOD_RE.fullmatch(period) is None:
            raise ValueError("formal_monthly_revenue_period_invalid")
        if int(row["invalid_row_count"] or 0) != 0:
            raise ValueError("formal_monthly_revenue_row_type_invalid")
        result.append(
            {
                "period": period,
                "formal_row_count": int(row["formal_row_count"]),
                "missing_announcement_date_row_count": int(
                    row["missing_announcement_date_row_count"] or 0
                ),
                "report_level_date_unverified_row_count": int(
                    max(
                        0,
                        int(row["report_level_date_unverified_row_count"] or 0)
                        - verified_by_period.get(period, 0),
                    )
                ),
                "distinct_stock_code_count": int(row["distinct_stock_code_count"]),
                "distinct_source_version_count": int(
                    row["distinct_source_version_count"]
                ),
            }
        )
    return result


def _unavailable(blocker: str) -> dict[str, Any]:
    return {
        "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA,
        "status": "unavailable",
        "periods": None,
        "blockers": [blocker],
        "scope": "unknown",
        "formal_db_write": False,
        "financial_values_returned": False,
    }


def _detail_unavailable(
    blocker: str,
    *,
    period: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA,
        "status": "unavailable",
        "period": period,
        "rows": None,
        "mapping_status": "unknown",
        "total_count": None,
        "limit": limit,
        "offset": offset,
        "has_more": None,
        "blockers": [blocker],
        "scope": "unknown",
        "formal_db_write": False,
        "financial_values_returned": False,
    }


__all__ = (
    "FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA",
    "FORMAL_MONTHLY_REVENUE_QUALITY_DETAIL_SCHEMA",
    "DEFAULT_DETAIL_PAGE_SIZE",
    "MAX_DETAIL_PAGE_SIZE",
    "MAX_DETAIL_OFFSET",
    "read_formal_monthly_revenue_quality_by_period",
    "read_formal_monthly_revenue_quality_missing_rows",
)
