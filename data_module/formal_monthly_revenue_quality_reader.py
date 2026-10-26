"""唯讀彙總正式月營收公告日期品質，按資料期別呈現。"""

from __future__ import annotations

import re
import sqlite3
import stat
from pathlib import Path
from typing import Any


FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA = "baldr.formal_monthly_revenue_quality_by_period.v1"
TABLE_NAME = "fundamental_monthly_revenues"
_REQUIRED_COLUMNS = frozenset(
    {"stock_code", "period", "announced_date", "source_version"}
)
_PERIOD_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])\Z")


def read_formal_monthly_revenue_quality_by_period(
    database_path: Path,
) -> dict[str, Any]:
    """唯讀回傳正式月營收資料按 period 分組的公告日期品質摘要。

    摘要只計正式表內列數、公告日期缺漏、公司數與來源版本數；不讀取營收值，
    不載入 availability mapping，也不執行修復、回填或資格判定。
    """

    try:
        rows = _read_period_aggregates(database_path)
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


def _read_period_aggregates(database_path: Path) -> list[dict[str, int | str]]:
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
            'COUNT(DISTINCT "stock_code") AS distinct_stock_code_count, '
            'COUNT(DISTINCT "source_version") AS distinct_source_version_count, '
            'SUM(CASE WHEN typeof("stock_code") != \'text\' '
            'OR typeof("period") != \'text\' '
            'OR typeof("source_version") != \'text\' '
            'OR ("announced_date" IS NOT NULL '
            'AND typeof("announced_date") != \'text\') '
            'OR TRIM("stock_code") = \'\' '
            'OR TRIM("source_version") = \'\' THEN 1 ELSE 0 END) '
            'AS invalid_row_count '
            'FROM "fundamental_monthly_revenues" GROUP BY "period" '
            'ORDER BY "period" ASC'
        ).fetchall()

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


__all__ = (
    "FORMAL_MONTHLY_REVENUE_QUALITY_SCHEMA",
    "read_formal_monthly_revenue_quality_by_period",
)
