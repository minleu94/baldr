"""把明選廣達月營收版本投影至既有個股基本面頁，不接策略輸入。"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime
import os
from pathlib import Path

from app_module.quanta_monthly_sales_snapshot import (
    ATTRIBUTION, LIMITATIONS, PARSER, QuantaMonthlySalesPin, read_quanta_monthly_sales,
)
from app_module.stock_research_report_dtos import StockFundamentalObservationDTO, StockReportSourceDTO


class QuantaMonthlySalesReportProvider:
    def __init__(self, pin: QuantaMonthlySalesPin | None = None, *, configuration_error: str = "") -> None:
        self.pin = pin
        self.configuration_error = configuration_error

    @classmethod
    def from_environment(cls) -> QuantaMonthlySalesReportProvider:
        values = tuple(os.getenv(name, "").strip() for name in (
            "QUANTA_MONTHLY_SALES_DIRECTORY", "QUANTA_MONTHLY_SALES_MANIFEST_SHA256", "QUANTA_MONTHLY_SALES_RECEIPT_SHA256"))
        if not any(values):
            return cls()
        try:
            if not all(values):
                raise ValueError("月營收研究需要同時明選目錄及manifest／receipt雙SHA")
            return cls(QuantaMonthlySalesPin(Path(values[0]), values[1], values[2]))
        except (ValueError, OSError, TypeError) as error:
            return cls(configuration_error=str(error))

    def read(self, stock_code: str, *, observed_at: datetime) -> tuple[
            tuple[StockFundamentalObservationDTO, ...], tuple[StockReportSourceDTO, ...]]:
        if stock_code != "2382" or (self.pin is None and not self.configuration_error):
            return (), ()
        source_id = "official.issuer.quanta.monthly_sales.2382.2026"
        label = "廣達月營收：官方2026固定版本（目前研究）"
        try:
            if self.pin is None:
                raise ValueError(self.configuration_error)
            period, values, available = read_quanta_monthly_sales(self.pin, cutoff_at=observed_at)
            month_index = int(period[:4]) * 12 + int(period[5:]) - 2
            previous_period = f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
            prior_year = f"{int(period[:4]) - 1:04d}-{period[5:]}"
            version = PARSER + ":" + self.pin.manifest_sha256
            metrics = (("revenue", "月營收（調整後合併）", period, "百萬元（TWD）"),
                ("previous_month_revenue", "前月營收（同表口徑）", previous_period, "百萬元（TWD）"),
                ("previous_year_revenue", "去年同月營收（同表口徑）", prior_year, "百萬元（TWD）"),
                ("mom_pct", "月增率（官方披露）", period, "%"),
                ("yoy_pct", "年增率（官方披露）", period, "%"))
            observations = tuple(StockFundamentalObservationDTO(
                kind="monthly_revenue", label=name, metric_name=metric, market="twse", period=row_period,
                as_of_date=row_period + f"-{monthrange(int(row_period[:4]), int(row_period[5:]))[1]:02d}",
                announced_date="", available_at=available.isoformat(), observed_at=observed_at.isoformat(),
                value=value, unit=unit, value_text="原披露百萬元整數" if index < 3 else "原披露0.1%，不以推算值替換",
                source_id=source_id, source_version=version, source_snapshot_hash=self.pin.manifest_sha256,
                period_basis="monthly_flow" if index < 3 else "monthly_growth_rate",
                basis_verified=True, aggregate_feature_eligible=False, formal_pit_eligible=False,
            ) for index, ((metric, name, row_period, unit), value) in enumerate(zip(metrics, values)))
            return observations, (StockReportSourceDTO(
                source_id=source_id, source_label=label, status="available", quality="observed",
                data_as_of=observations[0].as_of_date, available_at=available.isoformat(), version=version,
                row_count=len(observations), limitations=(ATTRIBUTION, *LIMITATIONS), frequency="monthly",
                observed_at=observed_at.isoformat(), current_observed_only=True, historical_pit_eligible=False,
            ),)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return (), (StockReportSourceDTO(source_id=source_id, source_label=label,
                status="unavailable", quality="unavailable", row_count=0,
                limitations=("月營收固定版本不可用：" + str(error), ATTRIBUTION, *LIMITATIONS),
                current_observed_only=True, historical_pit_eligible=False),)
