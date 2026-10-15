"""個股研究的官方注意公告固定版本接點；缺件只隔離此區塊。"""

from __future__ import annotations

from datetime import date, datetime, time
import os
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from app_module.official_attention_snapshot import OfficialAttentionSnapshotPin, read_official_attention_snapshot
from app_module.stock_research_report_dtos import StockOfficialAttentionDTO, StockOfficialAttentionRowDTO

_TAIPEI = ZoneInfo("Asia/Taipei")
_LIMITATIONS = (
    "僅明示TWSE公告日的原公告；未判定TPEx或其他日期。",
    "注意公告與處置措施分開；不據此產生交易限制或建議。",
    "累計次數、收盤價與本益比保留官方原字串；未授來源用途接受或歷史PIT資格。",
)


class OfficialAttentionReportProvider:
    def __init__(self, pin: OfficialAttentionSnapshotPin | None = None, *, configuration_error: str = "") -> None:
        self.pin = pin
        self.configuration_error = configuration_error

    @classmethod
    def from_environment(cls) -> OfficialAttentionReportProvider:
        names = ("OFFICIAL_ATTENTION_SNAPSHOT_DIRECTORY", "OFFICIAL_ATTENTION_MANIFEST_SHA256", "OFFICIAL_ATTENTION_RECEIPT_SHA256")
        values = tuple(os.environ.get(name, "").strip() for name in names)
        if not any(values):
            return cls()
        try:
            if not all(values):
                raise ValueError("官方注意公告須同時明示目錄及manifest／receipt雙SHA")
            return cls(OfficialAttentionSnapshotPin(Path(values[0]), values[1], values[2]))
        except (ValueError, OSError) as exc:
            return cls(configuration_error=str(exc))

    def read(self, stock_code: str, *, as_of_date: date, observed_at: datetime,
             cancel_callback: Callable[[], bool] | None = None) -> StockOfficialAttentionDTO:
        if self.pin is None:
            return StockOfficialAttentionDTO(limitations=(self.configuration_error or "未明選已保存的官方注意公告版本。",) + _LIMITATIONS)
        try:
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("注意公告觀測時鐘缺時區")
            actual = observed_at.astimezone(_TAIPEI)
            if as_of_date > actual.date():
                raise ValueError("不得以未來報告日讀取注意公告")
            cutoff = min(actual, datetime.combine(as_of_date, time.max, _TAIPEI))
            result = read_official_attention_snapshot(self.pin, stock_code=stock_code, decision_cutoff=cutoff,
                                                       check_cancel=cancel_callback)
            if date.fromisoformat(result.query_date) > as_of_date:
                raise ValueError("注意公告日期晚於報告日")
            rows = tuple(StockOfficialAttentionRowDTO(
                row.stock_code, row.stock_name, row.official_date_original_text, row.announcement_count_original_text,
                row.reason_text, row.closing_price_original_text, row.pe_original_text) for row in result.rows)
            return StockOfficialAttentionDTO("available", result.query_date, result.source_url, rows,
                self.pin.manifest_sha256, self.pin.receipt_sha256, result.available_hour.isoformat(),
                result.availability_basis, _LIMITATIONS)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return StockOfficialAttentionDTO(limitations=("官方注意公告版本不可用：" + str(exc),) + _LIMITATIONS)
