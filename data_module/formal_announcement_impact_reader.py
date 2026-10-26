"""以唯讀聚合讀取公告候選對正式季報鍵的有限影響。"""

from __future__ import annotations

import re
import sqlite3
import stat
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from data_module.open_data_quarterly_announcement_crosswalk import (
    AUDIT_SCHEMA as QUARTERLY_CROSSWALK_SCHEMA,
    _STATEMENT_BY_ITEM,
    _normalize_period,
)


FORMAL_IMPACT_SCHEMA = "baldr.quarterly_announcement_formal_impact.v1"
TABLE_NAME = "fundamental_statement_items"
MAX_CANDIDATE_KEYS = 20_000
MAX_CANDIDATE_RESOURCES = 256
MAX_PERIOD_REPORT_GROUPS = 24
MAX_CODES_PER_GROUP = 10_000
SQL_CODE_BATCH_SIZE = 250
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_STATEMENT_TYPES = frozenset(_STATEMENT_BY_ITEM.values())
_REQUIRED_COLUMNS = frozenset(
    {
        "stock_code",
        "statement_type",
        "period",
        "announced_date",
        "source_version",
        "item_code",
    }
)


def read_quarterly_announcement_formal_impact(
    *, crosswalk: Mapping[str, Any], database_path: Path | None
) -> dict[str, Any]:
    """讀取公告候選對正式季報鍵的有限聚合，不推定版本或授予資格。

    crosswalk 的唯一公告事件目前沒有數值內容 source_version/hash bridge；因此
    exact version links 與 rows cleared 只能為 0。正式表也沒有 market 欄，故
    company/report/period 命中僅表示 identity-only overlap。
    """

    try:
        candidate_keys = _unique_candidate_keys(crosswalk)
    except ValueError as exc:
        return _unavailable(str(exc))
    except (TypeError, KeyError):
        return _unavailable("crosswalk_identity_invalid")

    crosswalk_status = crosswalk.get("status")
    if crosswalk_status not in {"available", "partial"}:
        return _unavailable("quarterly_crosswalk_not_available")

    if database_path is None:
        return _unavailable("formal_database_path_not_configured")

    if not candidate_keys:
        return {
            "schema_version": FORMAL_IMPACT_SCHEMA,
            "status": "not_evaluated",
            "candidate_unique_keys": 0,
            "formal_identity_overlap": None,
            "formal_version_count": None,
            "formal_item_rows": None,
            "missing_announcement_date_rows": None,
            "exact_version_links": None,
            "rows_cleared": None,
            "blockers": ["no_unique_announcement_candidate_keys"],
            "identity_scope": "identity_only",
            "financial_values_returned": False,
            "formal_db_write": False,
        }

    if len(candidate_keys) > MAX_CANDIDATE_KEYS:
        return _unavailable("candidate_identity_scope_exceeded")

    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for _market, stock_code, statement_type, period in candidate_keys:
        groups[(statement_type, period)].add(stock_code)
    if len(groups) > MAX_PERIOD_REPORT_GROUPS or any(
        len(codes) > MAX_CODES_PER_GROUP for codes in groups.values()
    ):
        return _unavailable("formal_query_scope_exceeded")

    try:
        formal_by_key = _read_formal_aggregates(database_path, groups)
    except (OSError, sqlite3.Error, ValueError):
        return _unavailable("formal_database_or_schema_unavailable")

    # formal 表沒有 market 欄；計算唯一 code/report/period 三元組的 identity
    # overlap，避免同一資料列因候選 market 不同而重複計數。
    candidate_business_keys = {
        (stock_code, statement_type, period)
        for _market, stock_code, statement_type, period in candidate_keys
    }
    overlapping_keys = candidate_business_keys.intersection(formal_by_key)
    version_count = sum(
        formal_by_key[key]["version_count"] for key in overlapping_keys
    )
    item_rows = sum(formal_by_key[key]["item_rows"] for key in overlapping_keys)
    missing_rows = sum(
        formal_by_key[key]["missing_announcement_date_rows"]
        for key in overlapping_keys
    )

    blockers = [
        "formal_table_has_no_market_column_identity_only_overlap",
        "candidate_event_to_content_version_bridge_missing",
    ]
    if crosswalk_status == "partial":
        blockers.append("quarterly_crosswalk_scope_partial")
    return {
        "schema_version": FORMAL_IMPACT_SCHEMA,
        "status": "observed",
        "candidate_unique_keys": len(candidate_keys),
        "formal_identity_overlap": len(overlapping_keys),
        "formal_version_count": version_count,
        "formal_item_rows": item_rows,
        "missing_announcement_date_rows": missing_rows,
        "exact_version_links": 0,
        "rows_cleared": 0,
        "blockers": blockers,
        "identity_scope": "identity_only",
        "market_identity_available": False,
        "content_version_bridge_available": False,
        "financial_values_returned": False,
        "formal_db_write": False,
    }


def _unique_candidate_keys(
    crosswalk: Mapping[str, Any],
) -> set[tuple[str, str, str, str]]:
    expected_boundary = {
        "schema_version": QUARTERLY_CROSSWALK_SCHEMA,
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
    }
    if any(crosswalk.get(key) != value for key, value in expected_boundary.items()):
        raise ValueError("quarterly_crosswalk_boundary_invalid")
    resources = crosswalk.get("resources")
    if not isinstance(resources, list) or len(resources) > MAX_CANDIDATE_RESOURCES:
        raise ValueError("quarterly_crosswalk_resources_invalid")

    result: set[tuple[str, str, str, str]] = set()
    for resource in resources:
        if not isinstance(resource, Mapping):
            raise ValueError("quarterly_crosswalk_resource_invalid")
        market = resource.get("market")
        statement_type = resource.get("statement")
        rows = resource.get("rows")
        if (
            market not in {"TWSE", "TPEx"}
            or statement_type not in _STATEMENT_TYPES
            or not isinstance(rows, list)
        ):
            raise ValueError("quarterly_crosswalk_resource_identity_invalid")
        if len(rows) + len(result) > MAX_CANDIDATE_KEYS:
            raise ValueError("candidate_identity_scope_exceeded")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("quarterly_crosswalk_row_invalid")
            if row.get("status") != "one_announcement_candidate":
                continue
            candidates = row.get("announcement_candidates")
            if (
                type(row.get("announcement_count")) is not int
                or row["announcement_count"] != 1
                or row.get("announcement_timestamp_resolution")
                != "unique_candidate_timestamp"
                or not isinstance(candidates, list)
                or len(candidates) != 1
            ):
                raise ValueError("unique_announcement_candidate_identity_invalid")
            event = candidates[0]
            if not isinstance(event, Mapping):
                raise ValueError("unique_announcement_candidate_event_invalid")
            event_hash = event.get("event_sha256")
            response_hash = event.get("source_sha256")
            announcement_at = event.get("announcement_at")
            try:
                parsed_timestamp = (
                    datetime.fromisoformat(announcement_at.replace("Z", "+00:00"))
                    if isinstance(announcement_at, str)
                    else None
                )
            except ValueError:
                parsed_timestamp = None
            if (
                parsed_timestamp is None
                or parsed_timestamp.tzinfo is None
                or parsed_timestamp.utcoffset() is None
                or not isinstance(event_hash, str)
                or _SHA256_RE.fullmatch(event_hash) is None
                or not isinstance(response_hash, str)
                or _SHA256_RE.fullmatch(response_hash) is None
            ):
                raise ValueError("unique_announcement_candidate_event_hash_invalid")
            stock_code = row.get("issuer_code")
            period = _normalize_period(row.get("fiscal_period"))
            if (
                not isinstance(stock_code, str)
                or not stock_code.isdigit()
                or not 4 <= len(stock_code) <= 6
                or period is None
            ):
                raise ValueError("unique_announcement_candidate_key_invalid")
            result.add((str(market), stock_code, str(statement_type), period))
            if len(result) > MAX_CANDIDATE_KEYS:
                raise ValueError("candidate_identity_scope_exceeded")
    return result


def _read_formal_aggregates(
    database_path: Path, groups: Mapping[tuple[str, str], set[str]]
) -> dict[tuple[str, str, str], dict[str, int]]:
    requested_path = Path(database_path).expanduser()
    requested_stat = requested_path.lstat()
    if stat.S_ISLNK(requested_stat.st_mode) or getattr(
        requested_stat, "st_file_attributes", 0
    ) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError("formal_database_reparse_point")
    # 不呼叫 Windows realpath/GetFinalPathNameByHandle；受控資料路徑可能
    # 無法解析最終路徑，但 lstat 已確認指定 DB 本身存在且不是連結。
    path = requested_path.absolute()
    file_stat = path.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError("formal_database_not_regular_file")

    uri = path.as_uri() + "?mode=ro"
    result: dict[tuple[str, str, str], dict[str, int]] = {}
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise ValueError("formal_database_query_only_readback_failed")
        table_info = connection.execute(
            'PRAGMA table_info("fundamental_statement_items")'
        ).fetchall()
        columns = {str(row[1]): row for row in table_info}
        if not _REQUIRED_COLUMNS.issubset(columns):
            raise ValueError("formal_statement_schema_mismatch")
        if any(str(columns[name][2]).upper() != "TEXT" for name in _REQUIRED_COLUMNS):
            raise ValueError("formal_statement_schema_mismatch")
        if any(
            int(columns[name][3]) != 1
            for name in ("stock_code", "statement_type", "period", "source_version", "item_code")
        ):
            raise ValueError("formal_statement_schema_mismatch")

        for (statement_type, period), codes in sorted(groups.items()):
            sorted_codes = sorted(codes)
            for offset in range(0, len(sorted_codes), SQL_CODE_BATCH_SIZE):
                batch = sorted_codes[offset : offset + SQL_CODE_BATCH_SIZE]
                placeholders = ",".join("?" for _ in batch)
                query = (
                    'SELECT "stock_code", '
                    'COUNT(DISTINCT "source_version") AS version_count, '
                    'COUNT(*) AS item_rows, '
                    'SUM(CASE WHEN "announced_date" IS NULL '
                    'OR TRIM("announced_date") = \'\' THEN 1 ELSE 0 END) '
                    'AS missing_announcement_date_rows '
                    'FROM "fundamental_statement_items" '
                    f'WHERE "stock_code" IN ({placeholders}) '
                    'AND "statement_type" = ? AND "period" = ? '
                    'GROUP BY "stock_code"'
                )
                parameters: tuple[str, ...] = (
                    *batch,
                    statement_type,
                    period,
                )
                for row in connection.execute(query, parameters):
                    key = (str(row["stock_code"]), statement_type, period)
                    if key in result:
                        raise ValueError("formal_aggregate_duplicate_identity")
                    result[key] = {
                        "version_count": int(row["version_count"]),
                        "item_rows": int(row["item_rows"]),
                        "missing_announcement_date_rows": int(
                            row["missing_announcement_date_rows"] or 0
                        ),
                    }
    return result


def _unavailable(blocker: str) -> dict[str, Any]:
    return {
        "schema_version": FORMAL_IMPACT_SCHEMA,
        "status": "unavailable",
        "candidate_unique_keys": None,
        "formal_identity_overlap": None,
        "formal_version_count": None,
        "formal_item_rows": None,
        "missing_announcement_date_rows": None,
        "exact_version_links": None,
        "rows_cleared": None,
        "blockers": [blocker],
        "identity_scope": "unknown",
        "financial_values_returned": False,
        "formal_db_write": False,
    }


__all__ = (
    "FORMAL_IMPACT_SCHEMA",
    "read_quarterly_announcement_formal_impact",
)
