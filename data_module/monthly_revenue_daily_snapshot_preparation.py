"""以明確傳輸原件建立月營收每日快照候選；不抓取、不寫 DB、不授權用途。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import re

from bs4 import BeautifulSoup

from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DailySourceBatchValidation,
    DailySourceSnapshotError,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseScope,
    DailySourceValidationCheck,
)
from data_module.monthly_revenue_snapshot_harvester import (
    _snapshot_source_version,
    parse_mops_monthly_revenue_snapshot_html,
)


@dataclass(frozen=True)
class PreparedDailyMonthlyRevenue:
    """完整來源報表的候選；不推論市場 universe 或歷史報送完整性。"""

    transport_capture: DailySourceTransportCapture
    canonical_source_bytes: bytes
    source_version: str
    _source_rows: tuple[tuple[tuple[str, str], ...], ...]
    records: tuple[DailySourceSnapshotRecord, ...]
    validation: DailySourceBatchValidation
    source_unit: str = "TWD-thousand"

    @property
    def rows(self) -> tuple[dict[str, str], ...]:
        """交付原始千元列的副本；既有 normalizer 才乘 Decimal(1000)。"""
        return tuple(dict(row) for row in self._source_rows)


def prepare_daily_monthly_revenue_capture(
    *,
    capture: DailySourceTransportCapture,
    scope: DailySourceUseScope,
    period: str,
    validation_id: str,
) -> PreparedDailyMonthlyRevenue:
    """重用 parser，先拒絕錯標題、單位、漏列、重複列及無限／缺值。

    不推論官方發布小時；這個來源頁缺版本發布時間時，writer 以成功批次
    完成小時處理。來源月份與 body-completion clock 仍分別保存。
    """
    if not isinstance(capture, DailySourceTransportCapture):
        raise DailySourceSnapshotError("monthly_preparation_capture_type_invalid")
    if (
        scope.dataset_id != DAILY_SOURCE_SNAPSHOT_DATASET_ID
        or scope.source_id != DAILY_SOURCE_SNAPSHOT_SOURCE_ID
        or scope.market not in {"twse", "tpex"}
        or scope.unit != "TWD"
        or scope.parser_version != "mops-current-revenue-normalizer.v2"
        or scope.source_schema_version != "mops-static-snapshot.v2"
    ):
        raise DailySourceSnapshotError("monthly_preparation_scope_mismatch")
    if not re.fullmatch(r"\d{4}-\d{2}", period):
        raise DailySourceSnapshotError("monthly_preparation_period_invalid")
    year, month = map(int, period.split("-"))
    try:
        month_start = date(year, month, 1)
    except ValueError as exc:
        raise DailySourceSnapshotError("monthly_preparation_period_invalid") from exc
    if month_start >= capture.body_completed_at.date().replace(day=1):
        raise DailySourceSnapshotError("monthly_preparation_period_not_completed")
    html = capture.decoded_html
    payload = capture.canonical_source_bytes
    if not re.search(r"</html>\s*$", html, re.IGNORECASE):
        raise DailySourceSnapshotError("monthly_preparation_report_end_missing")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    title = re.match(r"(上市|上櫃)公司(\d{2,3})年(\d{1,2})月份", text)
    if (
        title is None
        or title[1] != ("上市" if scope.market == "twse" else "上櫃")
        or int(title[2]) + 1911 != year
        or int(title[3]) != month
    ):
        raise DailySourceSnapshotError("monthly_preparation_title_mismatch")
    if not re.search(r"單位\s*[:：]\s*(?:新[臺台]幣\s*)?[千仟]元", text):
        raise DailySourceSnapshotError("monthly_preparation_unit_not_explicit")

    # 舊 parser 會略過同股票的第二列。用實體 tr 的直接子 cell 獨立清點，
    # 避免重複股票、截短列或巢狀表格被靜默吞掉後仍宣稱完整分區。
    source_codes: list[str] = []
    table_headers: dict[int, list[str]] = {}
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        texts = [cell.get_text("", strip=True).replace("\xa0", " ").strip() for cell in cells]
        headers = [re.sub(r"\s+", "", value).replace("％", "%") for value in texts]
        table = tr.find_parent("table")
        if table is None:
            continue
        if "公司代號" in headers:
            if table.find_parent("table") is not None:
                raise DailySourceSnapshotError("monthly_preparation_nested_source_table_not_supported")
            if len(headers) != len(set(headers)) or headers[0] != "公司代號":
                raise DailySourceSnapshotError("monthly_preparation_header_ambiguous")
            table_headers[id(table)] = headers
            continue
        code = texts[0]
        if re.fullmatch(r"\d{4,6}", code):
            if table.find_parent("table") is not None:
                raise DailySourceSnapshotError("monthly_preparation_nested_source_table_not_supported")
            header = table_headers.get(id(table))
            if header is None or len(cells) != len(header) or any(cell.find("table") is not None for cell in cells):
                raise DailySourceSnapshotError("monthly_preparation_data_row_width_or_nesting_invalid")
            source_codes.append(code)
    if not source_codes or len(source_codes) != len(set(source_codes)):
        raise DailySourceSnapshotError("monthly_preparation_missing_or_duplicate_source_rows")
    captured_at = capture.body_completed_at.isoformat()
    source_version = _snapshot_source_version(
        market=scope.market, period=period, html=html, captured_at=captured_at
    )
    rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
        html,
        market=scope.market,
        period=period,
        fetched_at=captured_at,
        source_version=source_version,
    )
    if diagnostics or {row["stock_code"] for row in rows} != set(source_codes) or len(rows) != len(source_codes):
        raise DailySourceSnapshotError("monthly_preparation_schema_or_row_count_mismatch")
    money_columns = (
        "current_month_revenue", "previous_month_revenue", "previous_year_month_revenue",
        "cumulative_revenue", "previous_year_cumulative_revenue",
    )
    for row in rows:
        if not row["company_name"]:
            raise DailySourceSnapshotError("monthly_preparation_company_name_missing")
        for column in money_columns:
            try:
                value = Decimal(row[column])
            except (InvalidOperation, ValueError) as exc:
                raise DailySourceSnapshotError(f"monthly_preparation_value_missing_or_invalid:{column}") from exc
            if not value.is_finite():
                raise DailySourceSnapshotError(f"monthly_preparation_value_not_finite:{column}")
    digest = hashlib.sha256(payload).hexdigest()
    records = tuple(
        DailySourceSnapshotRecord(
            stock_code=row["stock_code"], market=scope.market, period=period,
            source_version=source_version, raw_source_sha256=digest, unit="TWD",
        )
        for row in sorted(rows, key=lambda item: item["stock_code"])
    )
    def passed(check_id: str, reason: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", reason)
    # 這是該份完整 response 中的報表列，不是獨立市場 universe 清冊。
    partition = f"{scope.market}:{period}:source_report_rows"
    validation = DailySourceBatchValidation(
        validation_id=validation_id,
        expected_partition_ids=(partition,), successful_partition_ids=(partition,),
        failed_partition_ids=(), expected_record_count=len(source_codes), actual_record_count=len(records),
        source_status_check=passed("source_status", "http_200_eof_length_and_report_structure_verified"),
        raw_source_hash_check=passed("raw_source_hash", "transport_and_canonical_sha256_bound"),
        schema_check=passed("schema", "title_schema_source_rows_exact_match"),
        unit_check=passed("unit", "explicit_thousand_twd_decimal_normalization_required"),
        finite_values_check=passed("finite_values", "all_source_money_columns_finite_decimal"),
        missing_values_check=passed("missing_values", "all_source_money_columns_and_company_names_present"),
        prior_period_required_check=passed("prior_period_required", "same_report_prior_year_value_finite_not_historical_pit"),
        official_timestamp_parse_check=DailySourceValidationCheck(
            "official_timestamp_parse", "not_required", "official_timestamp_not_provided"
        ),
    )
    frozen_rows = tuple(tuple(row.items()) for row in rows)
    return PreparedDailyMonthlyRevenue(capture, payload, source_version, frozen_rows, records, validation)
