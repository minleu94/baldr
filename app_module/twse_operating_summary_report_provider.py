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
from app_module.twse_operating_summary_reviewed import (
    SCHEMA as REVIEWED_SCHEMA, LIMITATIONS as REVIEWED_LIMITATIONS, REVIEWED_COMPANIES,
    ReviewedOperatingSummaryPin, read_reviewed_operating_summary_snapshot,
)


class OperatingSummaryReportProvider:
    def __init__(self, pin: OperatingSummaryPin | None = None, *, configuration_error: str = "", policy_schema: str = "") -> None:
        self.pin = pin
        self.configuration_error = configuration_error
        self.policy_schema = policy_schema or (REVIEWED_SCHEMA if type(pin) is ReviewedOperatingSummaryPin else "")

    @classmethod
    def from_environment(cls) -> OperatingSummaryReportProvider:
        values = tuple(os.environ.get(name, "").strip() for name in (
            "OPERATING_SUMMARY_SNAPSHOT_DIRECTORY", "OPERATING_SUMMARY_MANIFEST_SHA256", "OPERATING_SUMMARY_RECEIPT_SHA256",
        ))
        policy = os.environ.get("OPERATING_SUMMARY_POLICY_SCHEMA", "").strip()
        if not any(values) and not policy:
            return cls()
        try:
            if not all(values):
                raise ValueError("營益研究需要同時明選目錄及manifest／receipt雙SHA")
            if policy not in ("", REVIEWED_SCHEMA):
                raise ValueError("營益研究用途schema不可用")
            pin_type = ReviewedOperatingSummaryPin if policy else OperatingSummaryPin
            return cls(pin_type(Path(values[0]), values[1], values[2]), policy_schema=policy)
        except (ValueError, OSError, TypeError) as error:
            return cls(configuration_error=str(error), policy_schema=policy)

    def read(self, stock_code: str, *, observed_at: datetime) -> tuple[
        tuple[StockFundamentalObservationDTO, ...], tuple[StockReportSourceDTO, ...],
    ]:
        reviewed = self.policy_schema == REVIEWED_SCHEMA
        candidates = (*REVIEWED_COMPANIES, "2382") if reviewed else ("2330",)
        if stock_code not in candidates or (self.pin is None and not self.configuration_error):
            return (), ()
        source_id = "official.twse.operating_summary." + stock_code + ".2026h1"
        source_label = "TWSE營益分析：" + stock_code + "／2026上半年（固定版本）"
        limitations = REVIEWED_LIMITATIONS if reviewed else LIMITATIONS
        try:
            if self.pin is None:
                raise ValueError(self.configuration_error)
            if reviewed:
                if stock_code not in REVIEWED_COMPANIES:
                    raise ValueError("2382的發行人財報下載導向驗證頁，期間／單位用途尚未接受")
                if type(self.pin) is not ReviewedOperatingSummaryPin:
                    raise ValueError("具名三公司用途需要對應版本pin")
                result = read_reviewed_operating_summary_snapshot(self.pin, stock_code=stock_code, cutoff_at=observed_at)
            else:
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
                source_id=source_id, source_label=source_label,
                data_as_of="2026-06-30", available_at=result.available_hour.isoformat(),
                version=version, row_count=len(observations), limitations=(ATTRIBUTION,) + limitations,
                observed_at=observed_at.isoformat(), current_observed_only=True, historical_pit_eligible=False,
            ),)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return (), (StockReportSourceDTO(
                source_id=source_id, source_label=source_label,
                status="unavailable", quality="unavailable", row_count=0,
                limitations=("營益固定版本不可用：" + str(error), ATTRIBUTION) + limitations,
                current_observed_only=True, historical_pit_eligible=False,
            ),)
