"""將明選且具名接受的營益原件投影至原個股基本面DTO。"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from app_module.stock_research_report_dtos import (
    StockFundamentalObservationDTO, StockReportSourceDTO,
)
from app_module.twse_operating_summary_snapshot import (
    ATTRIBUTION, LIMITATIONS, OperatingSummaryPin, read_operating_summary_snapshot,
)


class OperatingSummaryReportProvider:
    def __init__(self, pin: OperatingSummaryPin | None = None, *, configuration_error: str = "") -> None:
        self.pin = pin
        self.configuration_error = configuration_error

    @classmethod
    def from_environment(cls) -> OperatingSummaryReportProvider:
        values = tuple(os.environ.get(name, "").strip() for name in (
            "OPERATING_SUMMARY_SNAPSHOT_DIRECTORY", "OPERATING_SUMMARY_MANIFEST_SHA256", "OPERATING_SUMMARY_RECEIPT_SHA256",
        ))
        if not any(values):
            return cls()
        try:
            if not all(values):
                raise ValueError("營益研究需要同時明選目錄及manifest／receipt雙SHA")
            return cls(OperatingSummaryPin(Path(values[0]), values[1], values[2]))
        except (ValueError, OSError, TypeError) as error:
            return cls(configuration_error=str(error))

    def read(self, stock_code: str, *, observed_at: datetime) -> tuple[
        tuple[StockFundamentalObservationDTO, ...], tuple[StockReportSourceDTO, ...],
    ]:
        if stock_code != "2330" or (self.pin is None and not self.configuration_error):
            return (), ()
        source_id = "official.twse.operating_summary.2330.2026h1"
        try:
            if self.pin is None:
                raise ValueError(self.configuration_error)
            result = read_operating_summary_snapshot(self.pin, cutoff_at=observed_at)
            version = "twse.t187ap17_L:" + result.raw_sha256 + ":" + self.pin.manifest_sha256
            observations = tuple(StockFundamentalObservationDTO(
                kind="statement_item", label=label, metric_name=metric, market="twse",
                period=result.period, as_of_date="2026-06-30", announced_date="",
                available_at=result.available_hour.isoformat(), observed_at=observed_at.isoformat(),
                value=value, unit=unit, source_id=source_id, source_version=version,
                source_snapshot_hash=result.raw_sha256, period_basis=result.period_basis,
                basis_verified=True, aggregate_feature_eligible=False, formal_pit_eligible=False,
            ) for metric, label, value, unit in result.values)
            return observations, (StockReportSourceDTO(
                source_id=source_id, source_label="TWSE營益分析：2330／2026上半年（固定版本）",
                data_as_of="2026-06-30", available_at=result.available_hour.isoformat(),
                version=version, row_count=len(observations), limitations=(ATTRIBUTION,) + LIMITATIONS,
                observed_at=observed_at.isoformat(), current_observed_only=True, historical_pit_eligible=False,
            ),)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return (), (StockReportSourceDTO(
                source_id=source_id, source_label="TWSE營益分析：2330／2026上半年（固定版本）",
                status="unavailable", quality="unavailable", row_count=0,
                limitations=("營益固定版本不可用：" + str(error), ATTRIBUTION) + LIMITATIONS,
                current_observed_only=True, historical_pit_eligible=False,
            ),)
