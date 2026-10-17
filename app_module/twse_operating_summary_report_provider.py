"""將明選且具名接受的營益原件投影至原個股基本面DTO。"""

from __future__ import annotations

from datetime import datetime
from dataclasses import replace
import os
from pathlib import Path

from app_module.stock_research_report_dtos import (
    StockFundamentalObservationDTO, StockFundamentalComparisonDTO, StockReportSourceDTO,
)
from app_module.twse_operating_summary_snapshot import (
    ATTRIBUTION, LIMITATIONS, OperatingSummaryPin, read_operating_summary_snapshot,
)
from app_module.twse_operating_summary_reviewed import (
    SCHEMA as REVIEWED_SCHEMA, LIMITATIONS as REVIEWED_LIMITATIONS, REVIEWED_COMPANIES,
    ReviewedOperatingSummaryPin, read_reviewed_operating_summary_snapshot,
    COMPARATIVE_SCHEMA, COMPARATIVE_LIMITATIONS, ComparativeOperatingSummaryPin,
    read_comparative_operating_summary_snapshot,
)


class OperatingSummaryReportProvider:
    def __init__(self, pin: OperatingSummaryPin | None = None, *, configuration_error: str = "", policy_schema: str = "") -> None:
        self.pin = pin
        self.configuration_error = configuration_error
        self.policy_schema = policy_schema or (COMPARATIVE_SCHEMA if type(pin) is ComparativeOperatingSummaryPin
            else REVIEWED_SCHEMA if type(pin) is ReviewedOperatingSummaryPin else "")

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
            if policy not in ("", REVIEWED_SCHEMA, COMPARATIVE_SCHEMA):
                raise ValueError("營益研究用途schema不可用")
            pin_type = ComparativeOperatingSummaryPin if policy == COMPARATIVE_SCHEMA else ReviewedOperatingSummaryPin if policy else OperatingSummaryPin
            return cls(pin_type(Path(values[0]), values[1], values[2]), policy_schema=policy)
        except (ValueError, OSError, TypeError) as error:
            return cls(configuration_error=str(error), policy_schema=policy)

    def read(self, stock_code: str, *, observed_at: datetime) -> tuple[
        tuple[StockFundamentalObservationDTO, ...], tuple[StockReportSourceDTO, ...],
    ]:
        if self.policy_schema == COMPARATIVE_SCHEMA:
            if stock_code not in (*REVIEWED_COMPANIES, "2382"):
                return (), ()
            try:
                if stock_code == "2382":
                    raise ValueError("2382的發行人財報下載導向驗證頁，期間／單位用途尚未接受")
                if type(self.pin) is not ComparativeOperatingSummaryPin:
                    raise ValueError(self.configuration_error or "財報比較需要對應版本pin")
                comparison = read_comparative_operating_summary_snapshot(self.pin, stock_code=stock_code, cutoff_at=observed_at)
                rows, sources = OperatingSummaryReportProvider(comparison.current.pin, policy_schema=REVIEWED_SCHEMA).read(stock_code, observed_at=observed_at)
                contextual_limits = (ATTRIBUTION,
                    "當期仍取原TWSE CSV，營收精度0.01百萬元、比率0.01%；不以PDF提高當期精度。",
                    REVIEWED_LIMITATIONS[1],
                    "此CSV只供具名三公司當期五欄；前期由另列的財報比較版本供應。其他公司、歷史PIT、聚合特徵、策略及ML資格未接受。")
                return rows, tuple(replace(source, source_label=source.source_label + "（當期CSV）", limitations=contextual_limits) for source in sources)
            except (ValueError, OSError, KeyError, TypeError) as error:
                return OperatingSummaryReportProvider(configuration_error=str(error), policy_schema=REVIEWED_SCHEMA).read(stock_code, observed_at=observed_at)
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

    def read_comparisons(self, stock_code: str, *, observed_at: datetime) -> tuple[
        tuple[StockFundamentalComparisonDTO, ...], tuple[StockReportSourceDTO, ...],
    ]:
        """新增選用比較投影，原read兩段回傳與當期欄位保持。"""
        if self.policy_schema != COMPARATIVE_SCHEMA or stock_code not in (*REVIEWED_COMPANIES, "2382"):
            return (), ()
        source_id = "official.issuer.financial_comparison." + stock_code + ".2026h1"
        label = "發行人半年財報：" + stock_code + "／去年同期比較（目前研究）"
        try:
            if stock_code == "2382":
                raise ValueError("2382發行人財報下載轉驗證頁，前期比較缺件")
            if type(self.pin) is not ComparativeOperatingSummaryPin:
                raise ValueError(self.configuration_error or "財報比較需要對應版本pin")
            result = read_comparative_operating_summary_snapshot(self.pin, stock_code=stock_code, cutoff_at=observed_at)
            if result.status != "available":
                raise ValueError("尚未到比較版本成功保存的台北可用小時：" + result.available_hour.isoformat())
            current_id = "official.twse.operating_summary." + stock_code + ".2026h1"
            current_version = "twse.t187ap17_L:" + result.current.raw_sha256 + ":" + result.current.pin.manifest_sha256
            version = COMPARATIVE_SCHEMA + ":" + self.pin.manifest_sha256
            pairs = tuple(StockFundamentalComparisonDTO(stock_code=stock_code, metric_name=value.metric_name, label=value.label,
                current_period="2026-H1", prior_period="2025-H1", current_value=value.current_value, prior_value=value.prior_value,
                value_unit=value.unit, change_value=value.change_value, change_unit=value.change_unit,
                current_source_id=current_id, current_source_version=current_version, source_id=source_id, source_version=version,
                source_snapshot_hash=result.facts_sha256, available_at=result.available_hour.isoformat(), note=value.note) for value in result.values)
            return pairs, (StockReportSourceDTO(source_id=source_id, source_label=label, data_as_of="2026-06-30",
                available_at=result.available_hour.isoformat(), observed_at=observed_at.isoformat(), version=version,
                row_count=len(pairs), limitations=COMPARATIVE_LIMITATIONS, current_observed_only=True, historical_pit_eligible=False),)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return (), (StockReportSourceDTO(source_id=source_id, source_label=label, status="unavailable", quality="unavailable",
                row_count=0, limitations=(str(error),) + COMPARATIVE_LIMITATIONS, current_observed_only=True, historical_pit_eligible=False),)
