"""唯讀、有限查詢的個股研究報告 read service。

每個 section 都在自己的 query boundary 內失敗隔離；呼叫端可以在單一
SQLite table 缺資料、來源過期或 optional owner 尚未接入時，仍取得其他
可用內容。這個 service 不寫 SQLite、不重跑推薦、不建立交易動作。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import inspect
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app_module.advice_composer import AdviceComposer
from app_module.advice_dtos import AdviceMode
from app_module.advice_policy import AdvicePolicy
from app_module.position_health_service import PositionHealthService
from app_module.twse_operating_summary_report_provider import OperatingSummaryReportProvider
from app_module.research_result_presentation import is_research_data_limitation
from app_module.portfolio_condition_monitor import (
    PortfolioConditionMonitor,
    PortfolioConditionResult,
    PortfolioCurrentSnapshot,
)
from app_module.price_change_direction import (
    change_sign_columns as _change_sign_columns,
    normalize_change_sign as _normalize_change_sign,
    resolve_signed_change as _resolve_signed_change,
)
from app_module.sqlite_read_only import ReadOnlySQLiteManager
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from app_module.portfolio_research_stock_projection import (
    PortfolioScenarioStockProjection, PortfolioScenarioStockReference, project_saved_scenario_stock,
)
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    DailyMarketFeatureSnapshotService,
    daily_market_feature_input_fingerprint,
    feature_contract_for_version,
)
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotVerificationError
from app_module.daily_market_snapshot_source import daily_snapshot_schema_identity, daily_snapshot_scope_identity
from data_module.current_official_valuation import CurrentOfficialValuationReadProvider
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from app_module.stock_research_report_dtos import (
    ReportFreshness,
    ReportQuality,
    ReportSectionStatus,
    StockAdviceSnapshotDTO,
    StockSavedSourceOptionDTO,
    StockEvidenceEventDTO,
    StockFlowObservationDTO,
    StockFundamentalObservationDTO,
    StockFundamentalComparisonDTO,
    StockMetricDTO,
    StockMLSnapshotDTO,
    StockOutcomeDTO,
    StockPositionSnapshotDTO,
    StockMarketStatusEvidenceDTO,
    StockMarketStatusSnapshotDTO,
    StockTradingRestrictionDTO,
    StockPricePointDTO,
    StockReportSectionDTO,
    StockReportSourceDTO,
    StockResearchReportDTO,
    StockOriginalRankingReportDTO,
    StockTechnicalSnapshotDTO,
    StockTechnicalHistoryRowDTO,
    stock_technical_history_row_fingerprint_sha256,
    technical_history_saved_scope_limitation,
)
from app_module.stock_research_report_provider_adapters import (
    PortfolioExitReadProvider,
    _validated_target_costs,
    stock_price_row_fingerprint_sha256,
)
from app_module.watchlist_analysis_service import WatchlistAnalysisDTO, WatchlistAnalysisService
from app_module.research_session import ResearchRankContextDTO
from data_module.current_market_status_observation import CurrentMarketStatusReader
from app_module.official_attention_report_provider import OfficialAttentionReportProvider


class StockResearchReportCancelled(RuntimeError):
    """報告讀取被 UI worker 合作式取消。"""


_TAIPEI = ZoneInfo("Asia/Taipei")
_DAILY_MARKET_RESEARCH_SOURCE_KIND = "daily_market_research_snapshot"
_PRICE_LIMIT = 120
_FLOW_LIMIT = 120
_FUNDAMENTAL_LIMIT = 24
_EVENT_LIMIT = 24
_FRESHNESS_MAX_BYTES = 4 * 1024 * 1024

# 報告 service 只讀 freshness probe 的既有出口。這些 alias 讓 SQLite
# read model 與 probe 的 upstream source id 對齊，不能以資料日重新推導月／季 cadence。
_FRESHNESS_SOURCE_ALIASES = {
    "sqlite.daily_prices": "sqlite.daily_prices",
    "sqlite.technical_indicators": "sqlite.technical_indicators",
    "sqlite.market_indices": "sqlite.market_indices",
    "sqlite.industry_indices": "sqlite.industry_indices",
    "sqlite.broker_flows": "sqlite.broker_flows",
    "sqlite.fundamental_monthly_revenues": "fundamental.monthly_revenues",
    "sqlite.fundamental_statement_items": "fundamental.quarterly_statements",
    "sqlite.institutional_flows": "institutional_flows",
    "sqlite.credit_transactions": "credit_transactions",
    "sqlite.tdcc_shareholding": "tdcc_shareholding",
}
_FRESHNESS_STATUS_VALUES = {
    "current",
    "expected_wait",
    "stale",
    "failed",
    "partial",
    "not_applicable",
    "unknown",
}


class StockResearchReportReadService:
    """組合單一股票的既有研究來源，維持 PIT 與 read-only 邊界。"""

    def __init__(
        self,
        config: object,
        *,
        portfolio_service: object | None = None,
        portfolio_research_workspace: PortfolioResearchScenarioWorkspace | None = None,
        watchlist_analysis_service: WatchlistAnalysisService | None = None,
        condition_monitor: PortfolioConditionMonitor | None = None,
        position_health_service: PositionHealthService | None = None,
        exit_provider: Callable[..., object] | None = None,
        ml_provider: Callable[..., object] | None = None,
        valuation_provider: object | None = None,
        market_status_provider: Callable[[str], object] | None = None,
        official_attention_provider: OfficialAttentionReportProvider | None = None,
        clock: Callable[[], datetime] | None = None,
        freshness_status_path: Path | str | None = None,
        candidate_db_file: Path | None = None,
        current_ownership_capture_root: Path | str | None = None,
        daily_market_snapshot_root: Path | str | None = None,
        daily_market_snapshot_cohort_id: str | None = None,
        operating_summary_provider: OperatingSummaryReportProvider | None = None,
    ) -> None:
        self.config = config
        self.portfolio_service = portfolio_service
        self.portfolio_research_workspace = portfolio_research_workspace
        self.watchlist_analysis_service = watchlist_analysis_service
        if self.watchlist_analysis_service is None and getattr(config, "output_root", None) is not None:
            self.watchlist_analysis_service = WatchlistAnalysisService(config)
        self.condition_monitor = condition_monitor
        self.position_health_service = position_health_service or PositionHealthService()
        self.exit_provider = exit_provider or PortfolioExitReadProvider()
        self.ml_provider = ml_provider
        output_root = getattr(config, "output_root", None)
        self.valuation_provider = valuation_provider or (
            CurrentOfficialValuationReadProvider(Path(output_root))
            if output_root is not None
            else None
        )
        self.market_status_provider = market_status_provider
        self.official_attention_provider = official_attention_provider or OfficialAttentionReportProvider.from_environment()
        self.operating_summary_provider = operating_summary_provider or OperatingSummaryReportProvider.from_environment()
        self.market_status_pointer_path = (
            Path(output_root) / "release_v4" / "current_market_status" / "current_market_status_pointer.json"
            if output_root is not None
            else None
        )
        self.clock = clock or (lambda: datetime.now(_TAIPEI))
        self.daily_market_feature_snapshot_service = DailyMarketFeatureSnapshotService(
            max_entries=4
        )
        if (daily_market_snapshot_root is None) != (daily_market_snapshot_cohort_id is None):
            raise ValueError("daily_market_snapshot_root 與 cohort_id 必須一起明示")
        self.daily_market_snapshot_repository = (
            DailyMarketSnapshotRepository(Path(daily_market_snapshot_root))
            if daily_market_snapshot_root is not None else None
        )
        self.daily_market_snapshot_cohort_id = daily_market_snapshot_cohort_id
        self.freshness_status_path = _resolve_freshness_status_path(config, freshness_status_path)
        self.candidate_db_file = Path(candidate_db_file) if candidate_db_file is not None else None
        self.current_ownership_capture_root = (
            Path(current_ownership_capture_root)
            if current_ownership_capture_root is not None
            else Path(output_root) / "current_observed_market_ownership"
            if output_root is not None
            else None
        )
        # Worker 可能同時讀取不同股票；以 context-local snapshot 避免較慢的舊請求
        # 讀到新請求的 freshness receipt。每次 read_report 都會重新載入一次 bounded bytes。
        self._freshness_statuses: ContextVar[
            Mapping[str, Mapping[str, object]]
        ] = ContextVar("stock_research_report_freshness_statuses", default={})
        db_file = getattr(config, "db_file", None) or getattr(config, "sqlite_db_file", None)
        self.db = ReadOnlySQLiteManager(Path(db_file)) if db_file else None
        self._column_cache: dict[str, tuple[str, ...]] = {}

    def read_report(
        self,
        stock_code: str,
        *,
        as_of_date: date | str | None = None,
        context: object | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> StockResearchReportDTO:
        """讀取一份完整投影；每一個資料區塊都有限制筆數且可被取消。"""

        code = _normalize_stock_code(stock_code)
        context_map = _context_map(context)
        scenario_ref = context.get("portfolio_scenario_ref") if isinstance(context, Mapping) else getattr(context, "portfolio_scenario_ref", None)
        if scenario_ref is not None:
            exact_ref = scenario_ref if type(scenario_ref) is PortfolioScenarioStockReference else PortfolioScenarioStockReference.from_mapping(scenario_ref)
            if context_map.get("source_kind") != "portfolio_research_scenario" or context_map.get("source_snapshot_id") != exact_ref.artifact_id:
                raise ValueError("配置封存參照與來源種類或artifact不符，不讀其他帳本")
        rank_context = _rank_context_from(context)
        is_rank_research_context = (
            context_map.get("source_kind")
            in {"original_stock_ranking", "original_stock_ranking_bookmark"}
            or rank_context is not None
        )
        is_daily_research_snapshot = (
            context_map.get("source_kind") == _DAILY_MARKET_RESEARCH_SOURCE_KIND
        )
        # 更新器可能剛建立現況表／observed_at 欄；重新載入報告應立即看見。
        self._column_cache.clear()
        actual_clock = self.clock()
        if actual_clock.tzinfo is None or actual_clock.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        current_date = actual_clock.astimezone(_TAIPEI).date()
        requested_cutoff = _coerce_date(as_of_date)
        context_cutoff = (
            _coerce_date(
                getattr(rank_context, "decision_date", "")
                or context_map.get("decision_date")
            )
            if is_rank_research_context
            else _coerce_date(context_map.get("decision_date"))
            if is_daily_research_snapshot or context_map.get("source_kind") == "portfolio_research_scenario"
            else None
        )
        has_pinned_research_context = (is_daily_research_snapshot or is_rank_research_context
                                       or context_map.get("source_kind") == "portfolio_research_scenario")
        pinned_context_date_invalid = has_pinned_research_context and context_cutoff is None
        pinned_context_date_mismatch = (
            has_pinned_research_context
            and requested_cutoff is not None
            and context_cutoff is not None
            and requested_cutoff != context_cutoff
        )
        cutoff = (
            context_cutoff
            if has_pinned_research_context and context_cutoff is not None
            else requested_cutoff or current_date
        )
        if cutoff > current_date:
            return self._future_cutoff_report(code, cutoff, context, actual_clock)
        cutoff_text = cutoff.isoformat()
        self._freshness_statuses.set(
            self._load_freshness_statuses(cutoff, report_at=actual_clock)
        )
        sources: list[StockReportSourceDTO] = []
        sections: list[StockReportSectionDTO] = []
        limitations: list[str] = []
        errors: list[str] = []
        original_ranking = (
            _read_original_rank_report(
                rank_context,
                db_path=getattr(self.config, "db_file", None)
                or getattr(self.config, "sqlite_db_file", None),
                expected_stock_code=code,
                date_mismatch=pinned_context_date_invalid or pinned_context_date_mismatch,
                source_context_present=is_rank_research_context,
            )
            if is_rank_research_context
            else None
        )
        if original_ranking is not None and original_ranking.status == "unknown":
            limitations.append(
                "原始排名來源未知；名次不以現況、其他模式或最新研究回填。原因："
                + (original_ranking.reason or "來源尚未核驗。")
            )
        context_code = context_map.get("stock_code", "")
        name = (
            context_map.get("stock_name", "")
            if not context_code or context_code == code
            else ""
        )
        industry = ""

        market_status, market_status_source = self._read_market_status(code, cutoff)
        official_attention = self.official_attention_provider.read(
            code, as_of_date=cutoff, observed_at=actual_clock, cancel_callback=cancel_callback,
        )
        if official_attention.status == "available":
            self._register_source(sources, StockReportSourceDTO(
                "twse.official_attention", "TWSE單日官方注意公告", data_as_of=official_attention.query_date,
                available_at=official_attention.available_hour, version=official_attention.manifest_sha256,
                row_count=len(official_attention.rows), limitations=official_attention.limitations,
                candidate_only=True, historical_pit_eligible=False,
            ))
        if market_status_source is not None:
            self._register_source(sources, market_status_source)
        limitations.extend(market_status.limitations)
        sections.append(
            self._data_section(
                "market_status",
                "上市／交易狀態（當下註記）",
                1 if market_status.status in {"available", "partial"} else 0,
                market_status_source,
                missing_reason="沒有可用的官方當下上市／交易狀態證據；unknown 不代表停牌或下市。",
            )
        )

        price_points: tuple[StockPricePointDTO, ...] = ()
        saved_chart = None
        saved_chart_json = ""
        saved_scope_limitation = technical_history_saved_scope_limitation(context_map)
        personal_h20_saved_scope = (
            context_map.get("source_kind")
            in {"personal_h20_saved_cohort", "personal_h20_research_bookmark"}
            and saved_scope_limitation is not None
        )
        saved_chart_scope = (
            saved_scope_limitation is not None
            or context_map.get("source_kind") == "recommendation"
        )
        saved_chart_missing_reason = (
            "這筆個人 H20 保存結果未綁定同版本價格／技術圖表；本報告不以另一份行情來源補入。"
            if personal_h20_saved_scope
            else "找不到不晚於查詢日的價格資料；請從「數據更新」檢查行情來源。"
        )
        saved_technical_missing_reason = (
            "這筆個人 H20 保存結果未綁定同版本技術資料；本報告不以另一份行情來源補入。"
            if personal_h20_saved_scope
            else "找不到不晚於查詢日的技術指標；請先更新技術資料。"
        )
        if is_daily_research_snapshot or is_rank_research_context:
            try:
                self._check_cancel(cancel_callback)
                if is_daily_research_snapshot:
                    root = context_map.get("daily_snapshot_root", "")
                    cohort = context_map.get("daily_snapshot_cohort_id", "")
                    pin = context_map.get("source_snapshot_hash", "")
                    identity = context_map.get("source_snapshot_id", "")
                    if pinned_context_date_invalid or pinned_context_date_mismatch:
                        raise ValueError("saved_chart_context_date_mismatch")
                else:
                    if rank_context is None or rank_context.selected_stock_code != code:
                        raise ValueError("saved_chart_rank_context_mismatch")
                    root, cohort = rank_context.snapshot_root, rank_context.parent_cohort_id
                    pin, identity = rank_context.parent_snapshot_hash, rank_context.parent_snapshot_id
                pinned = DailyMarketSnapshotRepository(Path(root)).load_manifest(pin, cohort, cutoff)
                if pinned.manifest_identity_sha256 != identity:
                    raise ValueError("saved_chart_manifest_identity_mismatch")
                sealed_stock = pinned.stock_snapshots.get(code)
                if (context_map.get("data_date") and isinstance(sealed_stock, Mapping)
                        and context_map["data_date"] != sealed_stock.get("market_date")):
                    raise ValueError("saved_chart_context_data_date_mismatch")
                if isinstance(sealed_stock, Mapping) and "saved_technical_chart" in sealed_stock:
                    from app_module.saved_stock_technical_chart import read_saved_technical_chart, canonical
                    saved_chart = read_saved_technical_chart(
                        sealed_stock["saved_technical_chart"], stock_code=code, decision_date=cutoff,
                        scope_identity=str(sealed_stock["scope_identity"]),
                        input_fingerprint_sha256=str(sealed_stock["input_fingerprint_sha256"]),
                    )
                    saved_chart_json = canonical(sealed_stock["saved_technical_chart"]).decode("utf-8")
                    if saved_chart.price_points:
                        context_map["data_date"] = saved_chart.price_points[-1].data_date
            except StockResearchReportCancelled:
                raise
            except Exception as exc:
                limitations.append("原保存圖表無法核驗，不以最新資料補圖：" + str(exc))
        elif context_map.get("source_kind") == "recommendation" and saved_chart_scope:
            try:
                from app_module.saved_recommendation_queries import (
                    build_recommendation_execution_queries, canonical_scheduled_decision_date,
                    execution_result_config,
                )
                from app_module.recommendation_saved_chart import read_recommendation_chart_capture
                from app_module.saved_stock_technical_chart import canonical

                self._check_cancel(cancel_callback)
                result_id = context_map.get("result_id", "")
                result = build_recommendation_execution_queries(self.config).get(result_id)
                execution = result.execution if result is not None else None
                if result is None or execution is None or execution.result_id != result_id or execution.context.as_of_date is None:
                    raise ValueError("recommendation_chart_execution_missing")
                display_day = (canonical_scheduled_decision_date(result)
                               if execution_result_config(execution).get("scheduled_snapshot") is True
                               else execution.context.as_of_date.isoformat())
                if (not display_day or display_day != cutoff.isoformat()
                        or context_map.get("decision_date", display_day) != display_day
                        or context_map.get("stock_code", code) != code):
                    raise ValueError("recommendation_chart_context_mismatch")
                captures = [event.details for event in execution.events
                            if event.event_type == "recommendation_saved_technical_charts"]
                provenance = [event.details for event in execution.events
                              if event.event_type == "legacy_invocation_context"]
                if len(captures) != 1 or len(provenance) != 1:
                    raise ValueError("recommendation_chart_capture_missing_or_duplicate")
                capture, origin = captures[0], provenance[0]
                if not isinstance(capture, Mapping) or not isinstance(origin, Mapping):
                    raise ValueError("recommendation_chart_capture_invalid")
                captured_codes = capture.get("stock_codes", ())
                if (not isinstance(captured_codes, (tuple, list))
                        or tuple(captured_codes) != tuple(item.stock_code for item in execution.items)):
                    raise ValueError("recommendation_chart_selected_population_mismatch")
                provider = str(origin.get("source_id", ""))
                market_version = str(origin.get("market_data_fingerprint", ""))
                if context_map.get("source_id", result_id) not in {result_id, provider}:
                    raise ValueError("recommendation_chart_source_mismatch")
                chart_cutoff = datetime.combine(execution.context.as_of_date, datetime.max.time(), tzinfo=_TAIPEI)
                if chart_cutoff.date() > cutoff:
                    raise ValueError("recommendation_chart_future_cutoff")
                self._check_cancel(cancel_callback)
                saved_chart = read_recommendation_chart_capture(
                    capture, stock_code=code, result_id=result_id, source_id=provider,
                    market_data_fingerprint=market_version, decision_cutoff=chart_cutoff,
                )
                if saved_chart is None:
                    missing = capture.get("missing", {})
                    reason = missing.get(code, "stock_not_captured") if isinstance(missing, Mapping) else "capture_missing"
                    limitations.append("原推薦缺少保存圖表，不借今天資料：" + str(reason))
                else:
                    charts = capture["charts"]
                    if not isinstance(charts, Mapping) or not isinstance(charts.get(code), Mapping):
                        raise ValueError("recommendation_chart_envelope_missing")
                    saved_chart_json = canonical(dict(charts[code])).decode("utf-8")
                    if context_map.get("data_date") and context_map["data_date"] != saved_chart.price_points[-1].data_date:
                        saved_chart = None
                        saved_chart_json = ""
                        raise ValueError("recommendation_chart_data_date_mismatch")
                    context_map["data_date"] = saved_chart.price_points[-1].data_date
                    context_map["saved_chart_cutoff"] = saved_chart.decision_cutoff
                    context_map["saved_chart_scope_identity"] = saved_chart.scope_identity
            except StockResearchReportCancelled:
                raise
            except Exception as exc:
                saved_chart = None
                saved_chart_json = ""
                limitations.append("原推薦圖表無法核驗，不借今天資料：" + str(exc))
        price_source: StockReportSourceDTO | None = None
        try:
            self._check_cancel(cancel_callback)
            if saved_chart is not None:
                price_points = saved_chart.price_points
                price_source = StockReportSourceDTO(
                    saved_chart.price_points[0].source_id if saved_chart.price_points else "sqlite.daily_prices", "同版保存價格", status="available" if price_points else "missing",
                    data_as_of=price_points[-1].data_date if price_points else "", row_count=len(price_points),
                    version="stock-research-saved-technical-chart.v1", historical_pit_eligible=False,
                )
                discovered_name = ""
            elif saved_chart_scope:
                discovered_name = ""
            else:
                price_points, price_source, discovered_name = self._read_prices(code, cutoff)
            name = name or discovered_name
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("價格", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("price", "價格", error))
        else:
            if price_source is not None:
                self._register_source(sources, price_source)
            sections.append(
                self._data_section(
                    "price",
                    "價格",
                    len(price_points),
                    price_source,
                    missing_reason=saved_chart_missing_reason,
                )
            )

        technical: StockTechnicalSnapshotDTO | None = None
        technical_history: tuple[StockTechnicalHistoryRowDTO, ...] = ()
        technical_source: StockReportSourceDTO | None = None
        try:
            self._check_cancel(cancel_callback)
            if saved_chart is not None:
                technical_source = StockReportSourceDTO(
                    saved_chart.technical_history[0].source_id if saved_chart.technical_history else "sqlite.technical_indicators", "同版保存MA20／MA60", status="available",
                    data_as_of=saved_chart.technical_history[-1].data_date if saved_chart.technical_history else "",
                    row_count=len(saved_chart.technical_history), historical_pit_eligible=False,
                )
                if saved_chart.technical_history:
                    row = saved_chart.technical_history[-1]
                    technical = StockTechnicalSnapshotDTO(
                        data_date=row.data_date, source_id=row.source_id, available_at=row.available_at,
                        indicators=tuple(StockMetricDTO(key=key, label=key, value=value, unit="TWD/share", data_as_of=row.data_date)
                                         for key, value in (("MA20", row.ma20), ("MA60", row.ma60))),
                    )
            elif not saved_chart_scope:
                technical, technical_source = self._read_technical(code, cutoff)
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("技術指標", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("technical", "技術指標", error))
        else:
            if technical_source is not None:
                self._register_source(sources, technical_source)
            sections.append(
                self._data_section(
                    "technical",
                    "技術指標",
                    len(technical.indicators) if technical is not None else 0,
                    technical_source,
                    missing_reason=saved_technical_missing_reason,
                )
            )

        saved_history_limitation = (
            "這筆個人 H20 保存結果未綁定同版本技術歷史；本報告不以另一份行情來源補入。"
            if personal_h20_saved_scope
            else saved_scope_limitation
        )
        if saved_chart is not None:
            technical_history = saved_chart.technical_history
        elif saved_chart_scope:
            limitations.append(saved_history_limitation or "原推薦缺少同版MA歷史，不以最新資料補圖。")
        else:
            try:
                self._check_cancel(cancel_callback)
                technical_history = self._read_technical_history(
                    code,
                    cutoff,
                    price_points,
                )
            except StockResearchReportCancelled:
                raise
            except Exception as exc:
                limitations.append(_error_text("技術歷史", exc))

        shared_daily_features: Mapping[str, Any] = {}
        try:
            self._check_cancel(cancel_callback)
            if is_daily_research_snapshot:
                if pinned_context_date_invalid or pinned_context_date_mismatch:
                    raise DailyMarketSnapshotVerificationError(
                        "snapshot_context_decision_date_mismatch",
                        "個股研究決策日與 pinned 快照日期不符；請從每日研究名單重新載入。",
                    )
                snapshot_root = context_map.get("daily_snapshot_root", "").strip()
                cohort_id = context_map.get("daily_snapshot_cohort_id", "").strip()
                manifest_sha256 = context_map.get("source_snapshot_hash", "").strip()
                manifest_identity = context_map.get("source_snapshot_id", "").strip()
                raw_condition_keys = context_map.get(
                    "daily_snapshot_condition_keys", ""
                )
                condition_keys = tuple(
                    value.strip()
                    for value in raw_condition_keys.split(",")
                    if value.strip()
                )
                combine_mode = context_map.get("daily_snapshot_combine_mode", "")
                if (
                    not snapshot_root
                    or not cohort_id
                    or not manifest_sha256
                    or not manifest_identity
                ):
                    raise DailyMarketSnapshotVerificationError(
                        "snapshot_context_incomplete",
                        "每日研究來源缺少快照路徑、cohort 或 hash；請重新載入名單。",
                    )
                db_path = Path(getattr(self.config, "db_file", None) or getattr(self.config, "sqlite_db_file"))
                schema_identity = daily_snapshot_schema_identity(
                    self._columns("daily_prices"), self._columns("technical_indicators")
                )
                scope_identity = daily_snapshot_scope_identity(db_path, code, schema_identity)
                # feature契約仍獨立核對來源；只用於驗證，不交給保存圖表補洞。
                legacy_points, _legacy_price_source, _legacy_name = self._read_prices(code, cutoff)
                pinned_repository = DailyMarketSnapshotRepository(Path(snapshot_root))
                verified = pinned_repository.load_manifest(
                    manifest_sha256, cohort_id=cohort_id, decision_date=cutoff,
                )
                contract = feature_contract_for_version(str(verified.manifest["feature_contract_version"]))
                if contract.version == DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER:
                    legacy_technical, _legacy_technical_source = self._read_technical(
                        code, cutoff, include_bbands30_upper=True,
                    )
                else:
                    legacy_technical, _legacy_technical_source = self._read_technical(code, cutoff)
                expected_hash = daily_market_feature_input_fingerprint(
                    code, cutoff, scope_identity, legacy_points, legacy_technical,
                    contract_version=contract.version,
                )
                verified = pinned_repository.load_manifest(
                    manifest_sha256, cohort_id=cohort_id, decision_date=cutoff,
                    expected_input_hashes={code: expected_hash},
                )
                if verified.manifest_identity_sha256 != manifest_identity:
                    raise DailyMarketSnapshotVerificationError(
                        "snapshot_manifest_identity_mismatch",
                        "每日研究來源的 manifest identity 不符；請重新載入名單。",
                    )
                shared_daily_features = dict(verified.stock_snapshots[code])
                context_data_date = _coerce_date(context_map.get("data_date"))
                payload_market_date = str(
                    shared_daily_features.get("market_date") or ""
                )
                if (
                    context_map.get("data_date", "").strip()
                    and (
                        context_data_date is None
                        or context_data_date.isoformat() != payload_market_date
                    )
                ):
                    raise DailyMarketSnapshotVerificationError(
                        "snapshot_context_data_date_mismatch",
                        "個股研究行情日與快照內行情日不符；請重新載入名單。",
                    )
                from app_module.daily_market_research_screener import (
                    evaluate_daily_market_conditions,
                )

                evaluation = evaluate_daily_market_conditions(
                    shared_daily_features.get("conditions", {}),
                    condition_keys,
                    combine_mode,
                    expected_decision_date=cutoff,
                )
                shared_daily_features["readback"] = {
                    "mode": "verified_pinned_daily_market_research_snapshot",
                    "manifest_sha256": verified.manifest_sha256,
                    "manifest_identity_sha256": verified.manifest_identity_sha256,
                    "source_snapshot_hash": verified.manifest_sha256,
                    "source_snapshot_id": verified.manifest_identity_sha256,
                    "completeness": verified.completeness,
                    "cohort_id": cohort_id,
                    "stock_code": code,
                    "data_date": payload_market_date,
                    "input_fingerprint_sha256": shared_daily_features.get(
                        "input_fingerprint_sha256", ""
                    ),
                    "snapshot_identity_sha256": shared_daily_features.get(
                        "snapshot_identity_sha256", ""
                    ),
                    "usage": shared_daily_features.get("policy", {}).get(
                        "usage", "current_observed_research_only"
                    ),
                    "historical_pit_eligible": False,
                    "filter_evaluation": {
                        "condition_keys": list(evaluation.condition_keys),
                        "combine_mode": evaluation.combine_mode,
                        "combined_state": evaluation.combined_state,
                        "conditions": [
                            item.to_dict() for item in evaluation.conditions
                        ],
                        "why": list(evaluation.why),
                        "why_not": list(evaluation.why_not),
                    },
                }
            elif is_rank_research_context:
                # 只從 rank context 所指向的同一 parent snapshot 讀 feature row；
                # 不用 Daily latest 或重新投影補缺。
                if rank_context is None or original_ranking is None or original_ranking.status != "available":
                    shared_daily_features = {
                        "projection_status": "unknown",
                        "projection_reason": (
                            original_ranking.reason
                            if original_ranking is not None
                            else "rank_context_missing"
                        ),
                        "readback": {
                            "mode": "refused_pinned_original_rank_parent_feature",
                            "historical_pit_eligible": False,
                        },
                    }
                else:
                    try:
                        from app_module.original_stock_ranking import (
                            load_original_stock_ranking_from_context,
                        )

                        pinned_snapshot, _pinned_ranking = (
                            load_original_stock_ranking_from_context(
                                rank_context,
                                db_path=Path(
                                    str(
                                        getattr(self.config, "db_file", None)
                                        or getattr(self.config, "sqlite_db_file")
                                    )
                                ),
                            )
                        )
                        pinned_feature = pinned_snapshot.stock_snapshots.get(code)
                        if not isinstance(pinned_feature, Mapping):
                            raise ValueError("ranking_context_parent_feature_missing")
                        shared_daily_features = dict(pinned_feature)
                        shared_daily_features["readback"] = {
                            "mode": "verified_pinned_original_rank_parent_feature",
                            "manifest_sha256": pinned_snapshot.manifest_sha256,
                            "manifest_identity_sha256": pinned_snapshot.manifest_identity_sha256,
                            "parent_manifest_sha256": pinned_snapshot.manifest_sha256,
                            "parent_manifest_identity_sha256": pinned_snapshot.manifest_identity_sha256,
                            "parent_cohort_id": pinned_snapshot.cohort_id,
                            "parent_decision_date": pinned_snapshot.decision_date.isoformat(),
                            "rank_manifest_sha256": rank_context.source_hash,
                            "rank_manifest_identity_sha256": rank_context.rank_snapshot_id,
                            "stock_code": code,
                            "data_date": rank_context.latest_date,
                            "input_fingerprint_sha256": pinned_feature.get(
                                "input_fingerprint_sha256", ""
                            ),
                            "snapshot_identity_sha256": pinned_feature.get(
                                "snapshot_identity_sha256", ""
                            ),
                            "usage": pinned_feature.get("policy", {}).get(
                                "usage", "current_observed_research_only"
                            ),
                            "historical_pit_eligible": False,
                        }
                    except Exception as exc:
                        rank_error_code = str(getattr(exc, "code", "") or "").strip()
                        rank_error = str(exc).splitlines()[0].strip() or type(exc).__name__
                        rank_reason = (
                            f"{rank_error_code}: {rank_error}"
                            if rank_error_code
                            else rank_error
                        )
                        limitations.append(
                            "原始排名父快照 feature row 無法由 pinned source 讀回；"
                            "原排名與其 feature context 都保持未知，不改讀最新來源。原因："
                            + rank_reason
                        )
                        errors.append(rank_reason)
                        original_ranking = replace(
                            original_ranking,
                            status="unknown",
                            reason=rank_reason,
                            rank=None,
                            native_score_label="",
                        )
                        shared_daily_features = {
                            "projection_status": "failed",
                            "projection_error": rank_reason,
                            "readback": {
                                "mode": "refused_pinned_original_rank_parent_feature",
                                "parent_manifest_sha256": rank_context.parent_snapshot_hash,
                                "parent_manifest_identity_sha256": rank_context.parent_snapshot_id,
                                "rank_manifest_sha256": rank_context.source_hash,
                                "rank_manifest_identity_sha256": rank_context.rank_snapshot_id,
                                "historical_pit_eligible": False,
                            },
                        }
            elif self.daily_market_snapshot_repository is not None:
                db_path = Path(getattr(self.config, "db_file", None) or getattr(self.config, "sqlite_db_file"))
                schema_identity = daily_snapshot_schema_identity(
                    self._columns("daily_prices"), self._columns("technical_indicators")
                )
                scope_identity = daily_snapshot_scope_identity(db_path, code, schema_identity)
                verified = self.daily_market_snapshot_repository.load_latest(
                    cohort_id=str(self.daily_market_snapshot_cohort_id),
                    decision_date=cutoff,
                )
                contract = feature_contract_for_version(str(verified.manifest["feature_contract_version"]))
                fingerprint_technical = technical
                if contract.version == DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER:
                    fingerprint_technical, _fingerprint_source = self._read_technical(
                        code, cutoff, include_bbands30_upper=True,
                    )
                expected_hash = daily_market_feature_input_fingerprint(
                    code, cutoff, scope_identity, price_points, fingerprint_technical,
                    contract_version=contract.version,
                )
                # Revalidate the exact selected manifest, not a newly advanced latest pointer.
                verified = self.daily_market_snapshot_repository.load_manifest(
                    verified.manifest_sha256,
                    cohort_id=str(self.daily_market_snapshot_cohort_id),
                    decision_date=cutoff,
                    expected_input_hashes={code: expected_hash},
                )
                shared_daily_features = dict(verified.stock_snapshots[code])
                shared_daily_features["readback"] = {
                    "mode": "verified_published_research_snapshot",
                    "manifest_sha256": verified.manifest_sha256,
                    "manifest_identity_sha256": verified.manifest_identity_sha256,
                    "completeness": verified.completeness,
                    "cohort_id": self.daily_market_snapshot_cohort_id,
                }
            else:
                shared_feature_snapshot = self.daily_market_feature_snapshot_service.project(
                    stock_code=code,
                    decision_date=cutoff,
                    scope_identity=f"stock-report-symbol:{code}",
                    price_points=price_points,
                    technical=technical,
                )
                shared_daily_features = shared_feature_snapshot.to_dict()
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("共用每日特徵", exc)
            errors.append(error)
            limitations.append(error)
            # 即使投影器發生意外錯誤，也不能回退成另一套 close/MA 比較。
            # 明確保留未知條件，讓報告與下游呈現都能顯示失敗原因。
            shared_daily_features = {
                "projection_status": "failed",
                "projection_error": error,
                "projection_error_code": str(getattr(exc, "code", "") or ""),
                "conditions": {
                    "close_above_ma20": {
                        "state": "unknown",
                        "relation": "unknown",
                        "reason": "shared_daily_feature_projection_failed",
                        "detail": error,
                    },
                    "close_above_ma60": {
                        "state": "unknown",
                        "relation": "unknown",
                        "reason": "shared_daily_feature_projection_failed",
                        "detail": error,
                    },
                },
            }

        fundamentals: tuple[StockFundamentalObservationDTO, ...] = ()
        fundamental_comparisons: tuple[StockFundamentalComparisonDTO, ...] = ()
        fundamental_sources: tuple[StockReportSourceDTO, ...] = ()
        try:
            self._check_cancel(cancel_callback)
            fundamentals, fundamental_sources, discovered_industry = self._read_fundamentals(
                code,
                cutoff,
                include_current=as_of_date is None,
                expected_market_date=(
                    _coerce_date(price_points[-1].data_date) if price_points else None
                ),
                price_freshness=(
                    price_source.freshness
                    if price_source is not None
                    else ReportFreshness.UNKNOWN.value
                ),
            )
            # 目前財報比較不得混入明選歷史日或原封存研究的時點。
            if (as_of_date is None and not has_pinned_research_context and cutoff == self.clock().astimezone(_TAIPEI).date()
                    and isinstance(self.operating_summary_provider, OperatingSummaryReportProvider)):
                self._check_cancel(cancel_callback)
                fundamental_comparisons, comparison_sources = self.operating_summary_provider.read_comparisons(code, observed_at=self.clock())
                fundamental_sources += comparison_sources
            industry = discovered_industry
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("基本面", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("fundamental", "基本面", error))
        else:
            for source in fundamental_sources:
                self._register_source(sources, source)
            sections.append(
                self._data_section(
                    "fundamental",
                    "基本面／營收財報",
                    len(fundamentals),
                    fundamental_sources,
                    missing_reason="沒有可用的公告／可得日基本面資料；不以缺資料推論利空。",
                )
            )

        flows: tuple[StockFlowObservationDTO, ...] = ()
        flow_source: StockReportSourceDTO | None = None
        try:
            self._check_cancel(cancel_callback)
            flows, flow_source = self._read_flows(code, cutoff)
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("籌碼／分點", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("flows", "籌碼／法人分點", error))
        else:
            if flow_source is not None:
                self._register_source(sources, flow_source)
            sections.append(
                self._data_section(
                    "flows",
                    "籌碼／法人分點",
                    len(flows),
                    flow_source,
                    missing_reason="找不到不晚於查詢日的分點資料；請從「數據更新」檢查籌碼來源。",
                )
            )

        institutional: tuple[StockMetricDTO, ...] = ()
        credit: tuple[StockMetricDTO, ...] = ()
        shareholding: tuple[StockMetricDTO, ...] = ()
        market_sources: tuple[StockReportSourceDTO, ...] = ()
        try:
            self._check_cancel(cancel_callback)
            institutional, credit, shareholding, market_sources = self._read_market_ownership(
                code, cutoff, include_current=as_of_date is None,
                observed_at=actual_clock,
                readback_clock=lambda: self.clock(),
            )
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("法人／信用／集保", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("ownership", "法人／信用／集保", error))
        else:
            for source in market_sources:
                self._register_source(sources, source)
            ownership_count = len(institutional) + len(credit) + len(shareholding)
            sections.append(
                self._data_section(
                    "ownership",
                    "法人／信用／集保",
                    ownership_count,
                    market_sources,
                    missing_reason="此股票目前沒有可用的法人、信用或集保 row；不以空白補零。",
                )
            )

        events: tuple[StockEvidenceEventDTO, ...] = ()
        evidence_source: StockReportSourceDTO | None = None
        try:
            self._check_cancel(cancel_callback)
            events, evidence_source = self._read_events(code, cutoff)
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("產業／事件／歷史結果", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("events", "產業／事件／歷史結果", error))
        else:
            if evidence_source is not None:
                self._register_source(sources, evidence_source)
            sections.append(
                self._data_section(
                    "events",
                    "產業／事件／歷史建議結果",
                    len(events),
                    evidence_source,
                    missing_reason="沒有可追溯的事件或後續結果；不把空白當成中性績效證據。",
                )
            )
            if not industry:
                industry = _first_non_empty(*(event.event_family for event in events))

        position: StockPositionSnapshotDTO | None = None
        portfolio_scenario: PortfolioScenarioStockProjection | None = None
        position_source: StockReportSourceDTO | None = None
        try:
            self._check_cancel(cancel_callback)
            if context_map.get("source_kind") == "portfolio_research_scenario":
                if pinned_context_date_invalid or pinned_context_date_mismatch:
                    raise ValueError("配置封存日期與明示查詢範圍不符")
                portfolio_scenario = self._read_scenario_position(code, cutoff, context, context_map, cancel_callback)
                position_source = self._source(
                    "portfolio.scenario." + portfolio_scenario.reference.artifact_id,
                    "已保存配置研究（舊證據假設）", row_count=1,
                    data_as_of=portfolio_scenario.account_as_of_date,
                    available_at=portfolio_scenario.account_available_at,
                    quality=ReportQuality.OBSERVED.value, cutoff=cutoff,
                    limitations=("原封存事實與假設，不是今日帳本或新核行情；不授交易或歷史PIT。",),
                )
            else:
                position, position_source = self._read_position(
                    code, cutoff, context_map, price_points=price_points, price_source=price_source,
                )
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("持倉／Health／Exit", exc)
            errors.append(error)
            limitations.append(error)
            sections.append(self._error_section("position", "持倉／Health／Exit", error))
        else:
            if position_source is not None:
                self._register_source(sources, position_source)
            sections.append(
                self._data_section(
                    "position",
                    "持倉／Health／Exit",
                    1 if portfolio_scenario is not None or (position is not None and position.is_holding) else 0,
                    position_source,
                    missing_reason="此股票目前不在持倉；Health／Exit 只對現有持倉提供判讀。",
                )
            )
            if position is not None:
                limitations.extend(position.limitations)

        advice = StockAdviceSnapshotDTO()
        try:
            self._check_cancel(cancel_callback)
            advice, advice_source = self._read_advice(code, cutoff, context_map)
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("Advice", exc)
            errors.append(error)
            limitations.append(error)
            advice = StockAdviceSnapshotDTO(
                status=ReportQuality.UNAVAILABLE.value,
                limitations=(error,),
            )
            advice_source = None
            sections.append(self._error_section("advice", "既有建議與依據", error))
        else:
            if advice_source is not None:
                self._register_source(sources, advice_source)
            limitations.extend(advice.limitations)
            sections.append(
                self._data_section(
                    "advice",
                    "既有建議與依據",
                    1 if advice.recommendation is not None else 0,
                    advice_source,
                    missing_reason="沒有可用的已保存 Advice／推薦契約；請從推薦分析保存研究結果。",
                )
            )

        source_options = []
        if self.watchlist_analysis_service is not None:
            try:
                for option in self.watchlist_analysis_service.list_saved_sources(code)[:30]:
                    self._check_cancel(cancel_callback)
                    selected = self.watchlist_analysis_service.fetch(code, option["result_id"], cutoff)
                    if selected.status == "saved" or (selected.status == "not_in_result" and selected.reasons):
                        source_options.append(StockSavedSourceOptionDTO(option["result_id"], option.get("result_name") or option["result_id"], selected.decision_date, selected.data_date))
            except StockResearchReportCancelled:
                raise
            except Exception as exc:
                limitations.append(_error_text("保存來源選擇", exc))

        ml_error = ""
        try:
            self._check_cancel(cancel_callback)
            ml_context = dict(context_map)
            ml_context["stock_code"] = code
            ml_context["current_event_date"] = price_points[-1].data_date if price_points else ""
            ml_context["current_price_row_fingerprint_sha256"] = (
                price_points[-1].source_snapshot_hash if price_points else ""
            )
            saved_analysis = advice.saved_analysis
            if saved_analysis is not None and saved_analysis.status == "saved":
                for field_name in (
                    "result_id", "source_snapshot_id", "source_snapshot_hash",
                    "decision_date", "data_date", "profile_id", "profile_version",
                    "source_id", "source_kind",
                ):
                    value = str(getattr(saved_analysis, field_name, "") or "").strip()
                    if value:
                        ml_context[field_name] = value
            ml = self._read_ml(code, cutoff, ml_context)
        except StockResearchReportCancelled:
            raise
        except Exception as exc:
            error = _error_text("ML", exc)
            errors.append(error)
            limitations.append(error)
            ml = StockMLSnapshotDTO(
                status=ReportQuality.UNAVAILABLE.value,
                limitations=(error,),
            )
            ml_error = error
        limitations.extend(ml.limitations)
        if ml_error:
            sections.append(self._error_section("ml", "ML 研究結果", ml_error))
        else:
            sections.append(
                self._data_section(
                    "ml",
                    "ML 研究結果",
                    1 if ml.status not in {ReportQuality.UNAVAILABLE.value, ReportQuality.MISSING.value} else 0,
                    self._ml_source(ml, cutoff),
                    missing_reason="尚未接入合格的個股 ML read model；不顯示機率、目標價或勝率。",
                )
            )

        rule_reasons = _dedupe(
            (
                *_technical_rule_observations(
                    technical, shared_daily_features
                ),
                *advice.rule_reasons,
            )
            + tuple(
                reason
                for event in events
                for reason in (*event.reasons, *event.why_not_reasons, *event.risk_reasons)
            )
        )
        ml_reasons = tuple(ml.explanations)
        if (
            ml.status not in {ReportQuality.UNAVAILABLE.value, ReportQuality.MISSING.value}
            and ml.scope_mode == "selected_saved_decision"
        ):
            advice = _with_advice_agreement(advice, rule_reasons, ml_reasons)

        if self.db is None:
            limitations.append("未配置 SQLite；此報告只顯示可由外部 provider 提供的資料。")
        limitations.extend(errors)
        if position is not None:
            limitations.extend(reason for reason in (*position.health_reasons, *position.exit_reasons)
                               if is_research_data_limitation(reason))
        if advice.recommendation is not None:
            limitations.extend(reason for reason in advice.recommendation.risk_reasons
                               if is_research_data_limitation(reason))
        limitations = list(_dedupe(limitations))
        attention_reasons = _attention_reasons(price_points, fundamentals, flows, sections, advice, position)
        key_risks = _key_risks(advice, events, position, limitations, as_of_date=cutoff_text)
        available_modules = tuple(
            module
            for module, available in (
                ("market_status", market_status.status in {"available", "partial"}),
                ("price", bool(price_points)),
                ("technical", technical is not None and bool(technical.indicators)),
                ("fundamental", bool(fundamentals)),
                ("flows", bool(flows)),
                ("ownership", bool(institutional or credit or shareholding)),
                ("industry_events", bool(events)),
                ("history", bool(events)),
                ("official_attention", official_attention.status == "available"),
                ("position", portfolio_scenario is not None or (position is not None and position.is_holding)),
                ("health", (portfolio_scenario is not None and portfolio_scenario.health_known)
                 or (position is not None and bool(position.health_status))),
                ("advice", advice.recommendation is not None),
                ("ml", ml.status not in {ReportQuality.UNAVAILABLE.value, ReportQuality.MISSING.value}),
            )
            if available
        )

        return StockResearchReportDTO(
            stock_code=code,
            stock_name=name,
            market="台股",
            industry=industry,
            as_of=cutoff_text,
            generated_at=self.clock().isoformat(timespec="seconds"),
            sources=tuple(sources),
            sections=tuple(sections),
            available_modules=available_modules,
            attention_reasons=attention_reasons,
            key_risks=key_risks,
            limitations=tuple(limitations),
            price_points=price_points,
            technical=technical,
            fundamentals=fundamentals,
            flows=flows,
            institutional=institutional,
            credit=credit,
            shareholding=shareholding,
            events=events,
            position=position,
            market_status=market_status,
            advice=advice,
            ml=ml,
            rule_reasons=rule_reasons,
            saved_source_options=tuple(source_options),
            shared_daily_features=shared_daily_features,
            research_context=context_map,
            original_ranking=original_ranking,
            technical_history=technical_history,
            saved_technical_chart_json=saved_chart_json,
            portfolio_scenario=portfolio_scenario,
            official_attention=official_attention,
            fundamental_comparisons=fundamental_comparisons,
        )

    def _read_prices(
        self,
        code: str,
        cutoff: date,
    ) -> tuple[tuple[StockPricePointDTO, ...], StockReportSourceDTO | None, str]:
        table = "daily_prices"
        columns = self._columns(table)
        if not columns:
            return (), None, ""
        date_col = _pick(columns, "日期", "Date")
        code_col = _pick(columns, "證券代號", "stock_code", "Code")
        if date_col is None or code_col is None:
            raise ValueError("daily_prices 缺少股票代號／日期欄位")
        change_sign_columns = _change_sign_columns(columns)
        select_columns = [
            _select_column(columns, ("日期", "Date"), "data_date"),
            _select_column(columns, ("證券名稱", "stock_name"), "stock_name"),
            _select_column(columns, ("開盤價", "Open"), "open_price"),
            _select_column(columns, ("最高價", "High"), "high_price"),
            _select_column(columns, ("最低價", "Low"), "low_price"),
            _select_column(columns, ("收盤價", "Close"), "close_price"),
            _select_column(columns, ("成交股數", "Volume"), "volume"),
            _select_column(columns, ("成交金額",), "turnover"),
            _select_column(columns, ("漲跌價差",), "change_value"),
        ]
        select_columns.extend(
            f"{_quote(column)} AS {_quote(f'change_sign_{index}')}"
            for index, column in enumerate(change_sign_columns)
        )
        sql = f"""
            SELECT {", ".join(select_columns)}
            FROM {self._table(table)}
            WHERE {_quote(code_col)} = ?
              AND {_non_empty_expr(date_col)}
              AND {_date_key_expr(date_col)} <= ?
            ORDER BY {_date_key_expr(date_col)} DESC
            LIMIT ?
        """
        rows = self._query(sql, (code, _date_key(cutoff), _PRICE_LIMIT))
        points: list[StockPricePointDTO] = []
        change_limitations: set[str] = set()
        for row in reversed(rows):
            data_date = _iso_date(row["data_date"])
            if not data_date:
                continue
            change, change_limitation = _resolve_signed_change(
                row["change_value"],
                tuple(row[f"change_sign_{index}"] for index in range(len(change_sign_columns))),
            )
            if change_limitation:
                change_limitations.add(change_limitation)
            points.append(
                StockPricePointDTO(
                    data_date=data_date,
                    open_price=_decimal(row["open_price"]),
                    high_price=_decimal(row["high_price"]),
                    low_price=_decimal(row["low_price"]),
                    close_price=_decimal(row["close_price"]),
                    volume=_integer(row["volume"]),
                    turnover=_decimal(row["turnover"]),
                    change=change,
                    source_id="sqlite.daily_prices",
                    source_snapshot_hash=_price_row_fingerprint(
                        code=code,
                        data_date=data_date,
                        open_price=_decimal(row["open_price"]),
                        high_price=_decimal(row["high_price"]),
                        low_price=_decimal(row["low_price"]),
                        close_price=_decimal(row["close_price"]),
                        volume=_integer(row["volume"]),
                        turnover=_decimal(row["turnover"]),
                    ),
                    quality=ReportQuality.OBSERVED.value,
                )
            )
        latest = points[-1] if points else None
        name = str(rows[0]["stock_name"] or "").strip() if rows else ""
        source_limitations = ["來源未提供 available_at；資料可得時間沿用來源契約外資訊。"]
        if change_limitations:
            source_limitations.append("部分價格列沒有可驗證的漲跌方向；未將無號價差當作上漲。")
        source = self._source(
            "sqlite.daily_prices",
            "SQLite 日價格",
            row_count=len(points),
            data_as_of=latest.data_date if latest else "",
            quality=ReportQuality.OBSERVED.value if points else ReportQuality.MISSING.value,
            cutoff=cutoff,
            limitations=tuple(source_limitations),
        )
        return tuple(points), source, name

    def _read_technical(
        self,
        code: str,
        cutoff: date,
        *,
        include_bbands30_upper: bool = False,
    ) -> tuple[StockTechnicalSnapshotDTO | None, StockReportSourceDTO | None]:
        if not isinstance(include_bbands30_upper, bool):
            raise TypeError("include_bbands30_upper 必須是 bool")
        table = "technical_indicators"
        columns = self._columns(table)
        if not columns:
            return None, None
        date_col = _pick(columns, "日期", "Date")
        code_col = _pick(columns, "證券代號", "stock_code", "Code")
        if date_col is None or code_col is None:
            raise ValueError("technical_indicators 缺少股票代號／日期欄位")
        indicator_columns = (
            ("RSI", "RSI"),
            ("MACD", "MACD"),
            ("MACD_signal", "MACD signal"),
            ("MACD_hist", "MACD histogram"),
            ("MA5", "MA5"),
            ("MA10", "MA10"),
            ("MA20", "MA20"),
            ("MA60", "MA60"),
            ("ATR", "ATR"),
            ("ADX", "ADX"),
        )
        select = [_select_column(columns, ("日期", "Date"), "data_date")]
        select.extend(_select_column(columns, (key,), key) for key, _label in indicator_columns)
        bbands_upper_column = (
            _pick(columns, "BB_Upper", "upperband")
            if include_bbands30_upper
            else None
        )
        if bbands_upper_column is not None:
            select.append(
                _select_column(columns, (bbands_upper_column,), "BB_Upper")
            )
        sql = f"""
            SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(code_col)} = ?
              AND {_non_empty_expr(date_col)}
              AND {_date_key_expr(date_col)} <= ?
            ORDER BY {_date_key_expr(date_col)} DESC
            LIMIT 1
        """
        rows = self._query(sql, (code, _date_key(cutoff)))
        if not rows:
            source = self._source(
                "sqlite.technical_indicators",
                "SQLite 技術指標",
                row_count=0,
                data_as_of="",
                quality=ReportQuality.MISSING.value,
                cutoff=cutoff,
            )
            return None, source
        row = rows[0]
        data_date = _iso_date(row["data_date"])
        indicators = tuple(
            StockMetricDTO(
                key=key,
                label=label,
                value=_decimal(row[key]),
                data_as_of=data_date,
                source_id="sqlite.technical_indicators",
                quality=ReportQuality.OBSERVED.value,
            )
            for key, label in indicator_columns
            if _decimal(row[key]) is not None
        )
        if bbands_upper_column is not None and _decimal(row["BB_Upper"]) is not None:
            indicators = (
                *indicators,
                StockMetricDTO(
                    key="BB_Upper",
                    label="BB_Upper",
                    value=_decimal(row["BB_Upper"]),
                    unit="TWD/share",
                    data_as_of=data_date,
                    source_id="sqlite.technical_indicators",
                    quality=ReportQuality.OBSERVED.value,
                ),
            )
        technical = StockTechnicalSnapshotDTO(
            data_date=data_date,
            indicators=indicators,
            source_id="sqlite.technical_indicators",
            quality=ReportQuality.OBSERVED.value if indicators else ReportQuality.DEGRADED.value,
            limitations=("來源未提供 available_at。",) if indicators else ("最新 row 沒有可呈現的指標欄位。",),
        )
        source = self._source(
            "sqlite.technical_indicators",
            "SQLite 技術指標",
            row_count=1 if indicators else 0,
            data_as_of=data_date,
            quality=technical.quality,
            cutoff=cutoff,
            limitations=technical.limitations,
        )
        return technical, source

    def _read_technical_history(
        self,
        code: str,
        cutoff: date,
        price_points: Sequence[StockPricePointDTO],
    ) -> tuple[StockTechnicalHistoryRowDTO, ...]:
        """只讀價格投影日期交集內既有 MA20/MA60 列，沿用價格列數上限。"""

        table = "technical_indicators"
        columns = self._columns(table)
        if not columns or not price_points:
            return ()
        date_col = _pick(columns, "日期", "Date")
        code_col = _pick(columns, "證券代號", "stock_code", "Code")
        if date_col is None or code_col is None:
            raise ValueError("technical_indicators 缺少日期或股票代號欄位")

        price_dates: set[str] = set()
        for point in price_points:
            parsed = _coerce_date(point.data_date)
            if parsed is not None and parsed <= cutoff:
                price_dates.add(_date_key(parsed))
        bounded_dates = tuple(sorted(price_dates, reverse=True)[:_PRICE_LIMIT])
        if not bounded_dates:
            return ()

        availability_col = _pick(columns, "available_at", "available_date")
        select = [
            _select_column(columns, ("日期", "Date"), "data_date"),
            _select_column(columns, ("MA20",), "ma20"),
            _select_column(columns, ("MA60",), "ma60"),
            _select_column(
                columns,
                (availability_col,) if availability_col is not None else (),
                "available_at",
            ),
        ]
        date_placeholders = ", ".join("?" for _ in bounded_dates)
        sql = f"""
            SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(code_col)} = ?
              AND {_non_empty_expr(date_col)}
              AND {_date_key_expr(date_col)} <= ?
              AND {_date_key_expr(date_col)} IN ({date_placeholders})
            ORDER BY {_date_key_expr(date_col)} DESC
            LIMIT ?
        """
        rows = self._query(
            sql,
            (code, _date_key(cutoff), *bounded_dates, _PRICE_LIMIT),
        )
        history: list[StockTechnicalHistoryRowDTO] = []
        for row in rows:
            data_date = _iso_date(row["data_date"])
            if not data_date:
                continue
            ma20 = _decimal(row["ma20"])
            ma60 = _decimal(row["ma60"])
            available_at = str(row["available_at"] or "").strip()
            source_id = "sqlite.technical_indicators"
            source_row_hash = stock_technical_history_row_fingerprint_sha256(
                stock_code=code,
                source_id=source_id,
                data_date=data_date,
                ma20=ma20,
                ma60=ma60,
                available_at=available_at,
            )
            history.append(
                StockTechnicalHistoryRowDTO(
                    stock_code=code,
                    source_id=source_id,
                    data_date=data_date,
                    source_row_hash=source_row_hash,
                    ma20=ma20,
                    ma60=ma60,
                    available_at=available_at,
                )
            )
        return tuple(sorted(history, key=lambda row: row.data_date))

    def _read_fundamentals(
        self,
        code: str,
        cutoff: date,
        *,
        include_current: bool = False,
        expected_market_date: date | None = None,
        price_freshness: str = ReportFreshness.UNKNOWN.value,
    ) -> tuple[
        tuple[StockFundamentalObservationDTO, ...],
        tuple[StockReportSourceDTO, ...],
        str,
    ]:
        observations: list[StockFundamentalObservationDTO] = []
        sources: list[StockReportSourceDTO] = []
        industry = ""
        configurations = (
            (
                "fundamental_monthly_revenues",
                "SQLite 月營收",
                "monthly_revenue",
                "月營收",
                ("revenue",),
                _FUNDAMENTAL_LIMIT,
            ),
            (
                "fundamental_statement_items",
                "SQLite 財報項目",
                "statement_item",
                "財報項目",
                ("value",),
                _FUNDAMENTAL_LIMIT,
            ),
            (
                "fundamental_valuation_metrics",
                "SQLite 估值指標",
                "valuation",
                "估值",
                ("value",),
                12,
            ),
        )
        for table, label, kind, default_label, value_candidates, limit in configurations:
            columns = self._columns(table)
            if not columns:
                continue
            code_col = _pick(columns, "stock_code", "證券代號")
            available_col = _pick(columns, "available_date", "available_at")
            if code_col is None or available_col is None:
                raise ValueError(f"{table} 缺少 stock_code／available_date 欄位")
            select: tuple[str, ...]
            if table == "fundamental_monthly_revenues":
                select = (
                    _select_column(columns, ("period",), "period"),
                    _select_column(columns, ("as_of_date",), "as_of_date"),
                    _select_column(columns, ("announced_date",), "announced_date"),
                    _select_column(columns, ("available_date", "available_at"), "available_at"),
                    _select_column(columns, ("revenue",), "value"),
                    _select_column(columns, ("source",), "source"),
                    _select_column(columns, ("source_version",), "source_version"),
                    _select_column(columns, ("quality",), "quality"),
                    "NULL AS item_label",
                    "NULL AS industry",
                )
            elif table == "fundamental_statement_items":
                select = (
                    _select_column(columns, ("period",), "period"),
                    _select_column(columns, ("as_of_date",), "as_of_date"),
                    _select_column(columns, ("announced_date",), "announced_date"),
                    _select_column(columns, ("available_date", "available_at"), "available_at"),
                    _select_column(columns, value_candidates, "value"),
                    _select_column(columns, ("source",), "source"),
                    _select_column(columns, ("source_version",), "source_version"),
                    _select_column(columns, ("quality",), "quality"),
                    _select_column(columns, ("item_name",), "item_label"),
                    "NULL AS industry",
                )
            else:
                select = (
                    "NULL AS period",
                    _select_column(columns, ("as_of_date",), "as_of_date"),
                    "NULL AS announced_date",
                    _select_column(columns, ("available_date", "available_at"), "available_at"),
                    _select_column(columns, value_candidates, "value"),
                    _select_column(columns, ("source",), "source"),
                    _select_column(columns, ("source_version",), "source_version"),
                    _select_column(columns, ("quality",), "quality"),
                    _select_column(columns, ("metric_name",), "item_label"),
                    _select_column(columns, ("industry",), "industry"),
                )
            select += (
                _select_column(columns, ("metric_name",), "metric_name"),
                _select_column(columns, ("market",), "market"),
                _select_column(columns, ("period_basis",), "period_basis"),
                _select_column(columns, ("basis_verified",), "basis_verified"),
                _select_column(columns, ("aggregate_feature_eligible",), "aggregate_feature_eligible"),
                _select_column(columns, ("formal_pit_eligible",), "formal_pit_eligible"),
                _select_column(columns, ("source_snapshot_hash", "raw_response_sha256"), "source_snapshot_hash"),
            )
            period_col = _pick(columns, "period")
            as_of_col = _pick(columns, "as_of_date")
            period_fallback = (
                f"TRIM(CAST({_quote(period_col)} AS TEXT))"
                if period_col is not None
                else "''"
            )
            if as_of_col is not None and period_col is not None:
                # 所有基本面表都有 as_of_date；period 只作缺少 as_of
                # 時的 fallback，避免比較 2024-Q1／2024Q1 等字串格式。
                report_period_order = (
                    f"CASE WHEN {_non_empty_expr(as_of_col)} "
                    f"THEN {_date_key_expr(as_of_col)} "
                    f"ELSE {period_fallback} END"
                )
            elif as_of_col is not None:
                report_period_order = _date_key_expr(as_of_col)
            elif period_col is not None:
                report_period_order = period_fallback
            else:
                report_period_order = "''"
            # 先選最新公告 period／as_of，再在同一期內選較晚可得版本；
            # 不讓歷史 row 因為 available_date 較晚而擠掉最新報告期。
            sql = f"""
                SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(code_col)} = ?
                  AND {_non_empty_expr(available_col)}
                  AND {_date_key_expr(available_col)} <= ?
                ORDER BY {report_period_order} DESC,
                         {_date_key_expr(available_col)} DESC
                LIMIT ?
            """
            rows = self._query(sql, (code, _date_key(cutoff), limit))
            source_id = f"sqlite.{table}"
            unusable_monthly_amount_rows = 0
            unverified_legacy_unit_rows = 0
            for row in rows:
                available_at = _iso_date(row["available_at"])
                data_as_of = _iso_date(row["as_of_date"]) or _iso_date(row["period"])
                quality = _quality(row["quality"])
                raw_value = _decimal(row["value"])
                value = raw_value
                value_text = "" if raw_value is not None else str(row["value"] or "")
                unit = ""
                aggregate_eligible = _db_bool(row["aggregate_feature_eligible"])
                formal_pit_eligible = _db_bool(row["formal_pit_eligible"])
                if kind == "monthly_revenue":
                    if str(row["source"]) == "mops.monthly_revenue_static_snapshot" and raw_value is not None:
                        # 既有 MOPS 契約的原件單位為千元，報告 DTO 才換成 TWD。
                        value = raw_value * Decimal(1000)
                        unit = "TWD"
                    else:
                        # 其他來源未在此讀取契約證明金額單位；不把原值標成 TWD。
                        unusable_monthly_amount_rows += 1
                        value = None
                        value_text = (
                            "來源單位未核實；金額不可用，原件保留。"
                            if str(row["source"]) != "mops.monthly_revenue_static_snapshot"
                            else "來源金額無法解析；金額不可用，原件保留。"
                        )
                        quality = _worst_quality((quality, ReportQuality.DEGRADED.value))
                        aggregate_eligible = False
                        formal_pit_eligible = False
                elif kind in {"statement_item", "valuation"}:
                    # 舊表沒有單位／欄位基準欄，也無法由來源名稱推定金額、
                    # 每股值或比率。原 row 留在庫內；報告只保留來源與期間。
                    unverified_legacy_unit_rows += 1
                    value = None
                    value_text = "舊來源未保存可核對的單位與欄位基準；數值不可用，原件保留。"
                    quality = _worst_quality((quality, ReportQuality.DEGRADED.value))
                    aggregate_eligible = False
                    formal_pit_eligible = False
                observations.append(
                    StockFundamentalObservationDTO(
                        kind=kind,
                        label=str(row["item_label"] or default_label),
                        period=str(row["period"] or ""),
                        as_of_date=data_as_of,
                        announced_date=_iso_date(row["announced_date"]),
                        available_at=available_at,
                        value=value,
                        value_text=value_text,
                        unit=unit,
                        source_id=source_id,
                        source_version=str(row["source_version"] or ""),
                        metric_name=str(row["metric_name"] or row["item_label"] or ""),
                        market=str(row["market"] or ""),
                        source_snapshot_hash=str(row["source_snapshot_hash"] or ""),
                        quality=quality,
                        period_basis=str(row["period_basis"] or "unknown"),
                        basis_verified=_db_bool(row["basis_verified"]),
                        aggregate_feature_eligible=aggregate_eligible,
                        formal_pit_eligible=formal_pit_eligible,
                    )
                )
                industry = industry or str(row["industry"] or "").strip()
            source = self._source(
                source_id,
                label,
                row_count=len(rows),
                data_as_of=_latest_text(_iso_date(row["as_of_date"]) for row in rows),
                # 月／季的 freshness period 必須使用公告 period，不能把
                # available_at／as_of_date 當成 period 與 probe 比對。
                period=_latest_text(str(row["period"] or "") for row in rows),
                available_at=_latest_text(_iso_date(row["available_at"]) for row in rows),
                version=_latest_text(str(row["source_version"] or "") for row in rows),
                quality=_worst_quality(
                    [_quality(row["quality"]) for row in rows]
                    + ([ReportQuality.DEGRADED.value] if unusable_monthly_amount_rows or unverified_legacy_unit_rows else [])
                ),
                cutoff=cutoff,
                limitations=(
                    "只接受 available_date 不晚於查詢日的 row。",
                    *((
                        f"{unusable_monthly_amount_rows} 列月營收來源單位未核實或金額無法解析；值欄不可用，原件未改。",
                    ) if unusable_monthly_amount_rows else ()),
                    *((
                        f"{unverified_legacy_unit_rows} 列舊財報／估值缺可核對的單位與欄位基準；值欄不可用，原件未改。",
                    ) if unverified_legacy_unit_rows else ()),
                ),
            )
            sources.append(source)
        # 即時研究使用已實際觀測的官方快照；它沒有歷史公告日，不能回流 PIT。
        # 只有當下日期可讀此路徑，且逐列檢查完整 timestamp，歷史查詢仍使用上方契約。
        now = self.clock()
        current_table = "fundamental_current_observations"
        current_columns = self._columns(current_table)
        current_source_available_col = _pick(current_columns, "source_available_at")
        current_source_available_filter = (
            f"AND (NULLIF(TRIM({_quote(current_source_available_col)}), '') IS NULL OR "
            f"(julianday({_quote(current_source_available_col)}) IS NOT NULL AND "
            f"julianday({_quote(current_source_available_col)}) <= julianday(?)))"
            if current_source_available_col is not None
            else ""
        )
        current_source_available_sort = (
            f"CASE WHEN {_non_empty_expr(current_source_available_col)} THEN 0 ELSE 1 END, "
            f"{_quote(current_source_available_col)} DESC, "
            if current_source_available_col is not None
            else ""
        )
        if include_current and cutoff == now.astimezone(_TAIPEI).date() and current_columns:
            current_rows = self._query(
                f"""SELECT * FROM {self._table(current_table)}
                WHERE stock_code = ? AND julianday(observed_at) <= julianday(?)
                  AND as_of_date <= ? {current_source_available_filter}
                ORDER BY period DESC, {current_source_available_sort} observed_at DESC LIMIT 500""",
                (code, now.isoformat(), cutoff.isoformat(), *((now.isoformat(),) if current_source_available_col is not None else ())),
            )
            seen: set[tuple[str, str, str]] = set()
            fresh: list[StockFundamentalObservationDTO] = []
            for row in current_rows:
                key = (str(row["kind"]), str(row["period"]), str(row["item_code"]))
                if key in seen:
                    continue
                seen.add(key)
                source_version = str(row["source_version"] or "")
                basis_verified = _db_bool(
                    row["basis_verified"] if "basis_verified" in row.keys() else None
                )
                raw_value = _decimal(row["value"])
                unverified_openapi_value = (
                    source_version.startswith("official-openapi-statement-endpoints.v1:")
                    and not basis_verified
                )
                fresh.append(StockFundamentalObservationDTO(
                    kind=key[0], label=str(row["item_name"]), period=key[1],
                    as_of_date=str(row["as_of_date"]), announced_date="",
                    available_at=(str(row["source_available_at"] or "")
                                  if "source_available_at" in row.keys() else ""),
                    observed_at=str(row["observed_at"]),
                    value=None if unverified_openapi_value else raw_value,
                    value_text=(
                        f"原始值 {row['value']}；來源單位契約尚未驗證，欄位基準未知，不作數值解讀。"
                        if unverified_openapi_value
                        else "" if raw_value is not None
                        else "來源原始值無法轉成 Decimal；不推算。"
                    ),
                    unit="" if unverified_openapi_value else str(row["unit"] or "unknown"),
                    source_id=f"sqlite.{current_table}",
                    source_version=source_version,
                    quality=(ReportQuality.OBSERVED.value
                             if basis_verified
                             else ReportQuality.DEGRADED.value),
                    metric_name=str(row["item_code"] or ""),
                    market=str(row["market"] or "") if "market" in row.keys() else "",
                    source_snapshot_hash=(str(row["source_snapshot_hash"] or "")
                                          if "source_snapshot_hash" in row.keys() else ""),
                    period_basis=(str(row["period_basis"] or "unknown")
                                  if "period_basis" in row.keys() else "unknown"),
                    basis_verified=_db_bool(row["basis_verified"] if "basis_verified" in row.keys() else None),
                    aggregate_feature_eligible=_db_bool(
                        row["aggregate_feature_eligible"]
                        if "aggregate_feature_eligible" in row.keys() else None
                    ),
                    formal_pit_eligible=_db_bool(
                        row["formal_pit_eligible"] if "formal_pit_eligible" in row.keys() else None
                    ),
                ))
            if fresh:
                covered = {(r.kind, r.period, r.label) for r in fresh}
                observations = fresh + [r for r in observations if (r.kind, r.period, r.label) not in covered]
                sources.append(self._source(
                    f"sqlite.{current_table}", "官方基本面現況快照（非歷史公告證據）",
                    row_count=len(fresh), data_as_of=max(r.as_of_date for r in fresh),
                    available_at=max(r.available_at for r in fresh),
                    quality=ReportQuality.OBSERVED.value, cutoff=cutoff,
                    limitations=("依實際觀測時間供目前研究；沒有原公告日，不供歷史回測或 ML PIT 訓練。",),
                ))
        if include_current and cutoff == now.astimezone(_TAIPEI).date() and self.valuation_provider is not None:
            try:
                read_valuation = getattr(self.valuation_provider, "read_current", None)
                if not callable(read_valuation):
                    raise TypeError("official valuation provider does not expose read_current")
                expected_market_session, session_reason = (
                    self._latest_completed_official_session(now)
                )
                valuation_result = read_valuation(
                    code, expected_market_date=expected_market_date
                )
                valuation_rows, valuation_sources = self._current_valuation_observations(
                    code,
                    cutoff,
                    valuation_result,
                    expected_market_date,
                    expected_market_session=expected_market_session,
                    price_freshness=price_freshness,
                    session_reason=session_reason,
                )
                observations.extend(valuation_rows)
                sources.extend(valuation_sources)
            except Exception as exc:
                reason = f"current official valuation read failed:{type(exc).__name__}:{str(exc).splitlines()[0]}"
                sources.append(self._source(
                    "official.current_valuation",
                    "official current valuation",
                    row_count=0,
                    data_as_of="",
                    quality=ReportQuality.UNAVAILABLE.value,
                    cutoff=cutoff,
                    limitations=(reason,),
                ))
        if include_current and cutoff == now.astimezone(_TAIPEI).date():
            summary_rows, summary_sources = self.operating_summary_provider.read(code, observed_at=now)
            observations.extend(summary_rows)
            sources.extend(summary_sources)
        observations.sort(key=lambda item: item.period, reverse=True)
        observations.sort(key=lambda item: {"monthly_revenue": 0, "statement_item": 1, "valuation": 2}.get(item.kind, 3))
        return tuple(observations), tuple(sources), industry

    def _latest_completed_official_session(
        self, cutoff_at: datetime
    ) -> tuple[date | None, str]:
        """沿用推薦現況資料供應器的官方日曆，不以固定天數猜行情日期。"""

        db_file = getattr(self.config, "db_file", None) or getattr(
            self.config, "sqlite_db_file", None
        )
        if db_file is None:
            return None, "official_trading_calendar_database_unavailable"
        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            output_root = Path(db_file).expanduser().resolve(strict=False).parent
        try:
            provider = RecommendationCurrentFundamentalProvider(
                db_file=Path(db_file),
                output_root=Path(output_root),
            )
            return provider._latest_official_session(cutoff_at)
        except Exception as exc:
            return None, f"official_trading_calendar_unavailable:{type(exc).__name__}"

    def _current_valuation_observations(
        self,
        code: str,
        cutoff: date,
        result: object,
        expected_market_date: date | None = None,
        *,
        expected_market_session: date | None = None,
        price_freshness: str = ReportFreshness.UNKNOWN.value,
        session_reason: str = "",
    ) -> tuple[tuple[StockFundamentalObservationDTO, ...], tuple[StockReportSourceDTO, ...]]:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        report_date = now.astimezone(_TAIPEI).date()
        result_status = _object_text(result, "status")
        if (
            _object_text(result, "stock_code") != code
            or _coerce_date(_object_text(result, "report_date")) != report_date
            or cutoff != report_date
            or result_status not in {
                "ready", "partial", "stale", "out_of_sync", "freshness_unverified",
                "unavailable", "blocked_ambiguous_market",
            }
            or _object_value(result, "formal_pit_eligible") is not False
        ):
            return (), ()

        values_are_current = (
            result_status in {"ready", "partial"}
            and price_freshness == ReportFreshness.FRESH.value
            and expected_market_date is not None
            and expected_market_session is not None
            and expected_market_date == expected_market_session
        )

        observations: list[StockFundamentalObservationDTO] = []
        valid_by_market: dict[str, list[object]] = {"twse": [], "tpex": []}
        coverage = _object_value(result, "market_coverage")
        coverage_by_market = {
            _object_text(item, "market"): item
            for item in coverage
            if _object_text(item, "market") in {"twse", "tpex"}
        } if isinstance(coverage, Sequence) else {}
        for item in getattr(result, "observations", ()):
            if (
                result_status in {"unavailable", "blocked_ambiguous_market"}
                or
                _object_text(item, "stock_code") != code
                or _object_text(item, "market") not in valid_by_market
                or _object_text(item, "metric_name") not in {"pe", "pb", "dividend_yield"}
                or _object_value(item, "formal_pit_eligible") is not False
            ):
                continue
            as_of = _coerce_date(_object_text(item, "as_of_date"))
            if as_of is None or as_of > cutoff:
                continue
            raw_available = getattr(item, "available_at", None)
            if not isinstance(raw_available, datetime) or raw_available.tzinfo is None:
                continue
            available_at = raw_available.astimezone(now.tzinfo)
            if available_at > now:
                continue
            raw_hash = _object_text(item, "raw_response_sha256", "source_snapshot_hash")
            if not _is_sha256(raw_hash):
                continue
            source_version = _object_text(item, "source_version")
            if raw_hash.lower() not in source_version.lower():
                continue
            value = _decimal(getattr(item, "value", None))
            if value is None:
                continue
            metric = _object_text(item, "metric_name")
            unit = _object_text(item, "unit")
            expected_unit = "percent" if metric == "dividend_yield" else "ratio"
            if unit != expected_unit:
                continue
            market = _object_text(item, "market")
            source_id = _object_text(item, "source")
            if not source_id or not source_version:
                continue
            market_coverage = coverage_by_market.get(market)
            coverage_status = _object_text(market_coverage, "status")
            freshness_note = ""
            item_is_current = (
                values_are_current
                and coverage_status == "ready"
                and as_of == expected_market_session
            )
            if not item_is_current:
                if result_status not in {"ready", "partial"}:
                    freshness_note = (
                        f"官方估值整體狀態為 {result_status or 'unknown'}；"
                        "此列只保留日期註記，不標示為當下可用。"
                    )
                elif expected_market_session is None:
                    freshness_note = (
                        f"最新官方交易日未核實（{session_reason or '無日曆證據'}）；"
                        "此估值只保留日期註記，不標示為當下可用。"
                    )
                elif price_freshness != ReportFreshness.FRESH.value:
                    freshness_note = (
                        f"行情來源 freshness 為 {price_freshness}；估值只保留日期註記，"
                        "不標示為當下可用。"
                    )
                else:
                    expected_text = (
                        expected_market_session.isoformat()
                        if expected_market_session is not None
                        else "未核實"
                    )
                    price_text = expected_market_date.isoformat() if expected_market_date else "未提供"
                    freshness_note = (
                        f"估值日期／報告行情日需符合最新官方交易日 {expected_text}；"
                        f"估值資料日 {as_of.isoformat()}、報告行情日 {price_text}，不標示為當下可用。"
                    )
            valid_by_market[market].append(item)
            observations.append(StockFundamentalObservationDTO(
                kind="valuation",
                label=metric,
                metric_name=metric,
                market=market,
                period=as_of.isoformat(),
                as_of_date=as_of.isoformat(),
                available_at=available_at.isoformat(),
                value=value,
                value_text=freshness_note,
                unit=unit,
                source_id=f"official.current_valuation.{market}",
                source_version=source_version,
                source_snapshot_hash=raw_hash.lower(),
                quality=(ReportQuality.OBSERVED.value if item_is_current
                         else ReportQuality.DEGRADED.value),
                period_basis="unknown",
                basis_verified=False,
                aggregate_feature_eligible=False,
                formal_pit_eligible=False,
            ))

        sources: list[StockReportSourceDTO] = []
        coverage = _object_value(result, "market_coverage")
        coverage_rows = coverage if isinstance(coverage, Sequence) else ()
        raw_diagnostics = getattr(result, "diagnostics", ())
        diagnostics = (
            tuple(str(item) for item in raw_diagnostics if str(item))
            if isinstance(raw_diagnostics, Sequence) and not isinstance(raw_diagnostics, (str, bytes))
            else ()
        )
        for market in ("twse", "tpex"):
            market_coverage = next(
                (item for item in coverage_rows if _object_text(item, "market") == market), None
            )
            market_items = valid_by_market[market]
            if market_coverage is None and not market_items and result_status not in {
                "unavailable", "blocked_ambiguous_market"
            }:
                continue
            coverage_status = _object_text(market_coverage, "status") if market_coverage else "missing"
            coverage_date = _coerce_date(_object_text(market_coverage, "as_of_date")) if market_coverage else None
            market_coverage_is_current = bool(
                result_status in {"ready", "partial"}
                and coverage_status == "ready"
                and expected_market_session is not None
                and coverage_date == expected_market_session
            )
            source_version = _object_text(market_coverage, "source_version") if market_coverage else ""
            coverage_available = getattr(market_coverage, "available_at", None) if market_coverage else None
            available_text = (
                coverage_available.isoformat()
                if isinstance(coverage_available, datetime) and coverage_available.tzinfo is not None
                else _latest_text(item.available_at for item in observations if item.market == market)
            )
            limitations = list(diagnostics)
            if result_status not in {"ready", "partial"}:
                limitations.append(f"官方估值整體狀態為 {result_status or 'unknown'}。")
            market_diagnostic = _object_text(market_coverage, "diagnostic") if market_coverage else ""
            if market_diagnostic:
                limitations.append(f"{market} 官方估值 coverage：{market_diagnostic}")
            if coverage_status != "ready":
                limitations.append(
                    f"{market} 官方估值來源狀態為 {coverage_status}；保留 coverage 診斷，"
                    "不將缺少估值列解讀為零值或正常。"
                )
            if not values_are_current:
                if price_freshness != ReportFreshness.FRESH.value:
                    limitations.append(
                        f"報告行情 freshness 為 {price_freshness}；此市場估值不標示為當下可用。"
                    )
                elif expected_market_session is None:
                    limitations.append(
                        f"最新官方交易日未核實（{session_reason or '無日曆證據'}）；"
                        "此市場估值不標示為當下可用。"
                    )
                elif expected_market_date != expected_market_session:
                    limitations.append(
                        f"報告行情日 {expected_market_date or '未提供'} 不等於最新官方交易日 "
                        f"{expected_market_session.isoformat()}；此市場估值不標示為當下可用。"
                    )
            if not market_items and market_coverage_is_current:
                limitations.append(
                    f"{market} 擷取已完成，但沒有此股估值列；不跨市場補值，也不視為來源擷取失敗。"
                )
            elif not market_items and market_coverage is None:
                limitations.append(f"缺少 {market} 市場 coverage 記錄；狀態保持未知。")
            sources.append(self._source(
                f"official.current_valuation.{market}",
                f"official current valuation ({market})",
                row_count=len(market_items),
                data_as_of=(coverage_date.isoformat() if coverage_date and coverage_date <= cutoff
                            else _latest_text(item.as_of_date for item in observations if item.market == market)),
                available_at=available_text,
                version=source_version or _latest_text(item.source_version for item in observations if item.market == market),
                quality=(
                    ReportQuality.OBSERVED.value
                    if coverage_status == "ready" and values_are_current
                    else ReportQuality.OBSERVED.value
                    if market_coverage_is_current and not market_items
                    else ReportQuality.DEGRADED.value
                ),
                cutoff=cutoff,
                limitations=tuple(_dedupe(limitations)),
                coverage_status=coverage_status,
                status_override=(
                    "not_applicable"
                    if market_coverage_is_current and not market_items
                    else ReportSectionStatus.AVAILABLE.value
                    if market_coverage_is_current and market_items and values_are_current
                    else None
                ),
                preserve_source_quality=True,
            ))
        return tuple(observations), tuple(sources)

    def _read_flows(
        self,
        code: str,
        cutoff: date,
    ) -> tuple[tuple[StockFlowObservationDTO, ...], StockReportSourceDTO | None]:
        table = "broker_flows"
        columns = self._columns(table)
        if not columns:
            return (), None
        date_col = _pick(columns, "日期", "data_date")
        code_col = _pick(columns, "證券代號", "stock_code")
        if date_col is None or code_col is None:
            raise ValueError("broker_flows 缺少股票代號／日期欄位")
        select = (
            _select_column(columns, ("日期", "data_date"), "data_date"),
            _select_column(columns, ("分點名稱", "branch_name"), "branch_name"),
            _select_column(columns, ("買進股數", "buy_shares"), "buy_shares"),
            _select_column(columns, ("賣出股數", "sell_shares"), "sell_shares"),
            _select_column(columns, ("買賣超股數", "net_shares"), "net_shares"),
            _select_column(columns, ("買進金額千元", "buy_amount_thousand"), "buy_amount_thousand"),
            _select_column(columns, ("賣出金額千元", "sell_amount_thousand"), "sell_amount_thousand"),
            _select_column(columns, ("買賣超金額千元", "net_amount_thousand"), "net_amount_thousand"),
            _select_column(columns, ("trade_type",), "trade_type"),
            _select_column(columns, ("lots_observed",), "lots_observed"),
            _select_column(columns, ("amount_observed",), "amount_observed"),
        )
        sql = f"""
            SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(code_col)} = ?
              AND {_non_empty_expr(date_col)}
              AND {_date_key_expr(date_col)} <= ?
            ORDER BY {_date_key_expr(date_col)} DESC,
                     ABS(COALESCE({_select_raw(columns, ("買賣超股數", "net_shares"))}, 0)) DESC
            LIMIT ?
        """
        rows = self._query(sql, (code, _date_key(cutoff), _FLOW_LIMIT))
        flows: list[StockFlowObservationDTO] = []
        for row in rows:
            observed_flags = (_integer(row["lots_observed"]), _integer(row["amount_observed"]))
            quality = (
                ReportQuality.OBSERVED.value
                if any(flag == 1 for flag in observed_flags)
                else ReportQuality.DEGRADED.value
            )
            flows.append(
                StockFlowObservationDTO(
                    data_date=_iso_date(row["data_date"]),
                    branch_name=str(row["branch_name"] or "未提供分點"),
                    buy_shares=_integer(row["buy_shares"]),
                    sell_shares=_integer(row["sell_shares"]),
                    net_shares=_integer(row["net_shares"]),
                    buy_amount_thousand=_decimal(row["buy_amount_thousand"]),
                    sell_amount_thousand=_decimal(row["sell_amount_thousand"]),
                    net_amount_thousand=_decimal(row["net_amount_thousand"]),
                    trade_type=str(row["trade_type"] or ""),
                    source_id="sqlite.broker_flows",
                    quality=quality,
                )
            )
        source = self._source(
            "sqlite.broker_flows",
            "SQLite 分點買賣",
            row_count=len(flows),
            data_as_of=_latest_text(flow.data_date for flow in flows),
            quality=_worst_quality(flow.quality for flow in flows),
            cutoff=cutoff,
            limitations=("來源未提供 available_at；僅呈現有限筆數的近五日候選 row。",),
        )
        return tuple(flows), source

    def _read_market_ownership(
        self,
        code: str,
        cutoff: date,
        *,
        include_current: bool = False,
        observed_at: datetime | None = None,
        readback_clock: Callable[[], datetime] | None = None,
    ) -> tuple[
        tuple[StockMetricDTO, ...],
        tuple[StockMetricDTO, ...],
        tuple[StockMetricDTO, ...],
        tuple[StockReportSourceDTO, ...],
    ]:
        specifications = (
            (
                "institutional_flows",
                "SQLite 法人買賣超",
                (
                    ("foreign_investor_buy", "外資買進"),
                    ("foreign_investor_sell", "外資賣出"),
                    ("foreign_investor_net", "外資淨額"),
                    ("investment_trust_buy", "投信買進"),
                    ("investment_trust_sell", "投信賣出"),
                    ("investment_trust_net", "投信淨額"),
                    ("dealer_buy", "自營商買進"),
                    ("dealer_sell", "自營商賣出"),
                    ("dealer_net", "自營商淨額"),
                ),
                "institutional",
            ),
            (
                "credit_transactions",
                "SQLite 信用交易",
                (
                    ("margin_purchase", "融資買進"),
                    ("margin_balance", "融資餘額"),
                    ("short_sale", "融券賣出"),
                    ("short_balance", "融券餘額"),
                    ("financing", "借券融通"),
                    ("securities_lending", "借券"),
                ),
                "credit",
            ),
            (
                "tdcc_shareholding",
                "SQLite 集保股權分級",
                (
                    ("large_holder_ratio_bp", "大戶持股比例"),
                    ("retail_holder_ratio_bp", "散戶持股比例"),
                    ("dispersion_index_bp", "持股分散指標"),
                    ("shareholding_tiers", "持股級距"),
                ),
                "shareholding",
            ),
        )
        result: dict[str, tuple[StockMetricDTO, ...]] = {
            "institutional": (),
            "credit": (),
            "shareholding": (),
        }
        sources: list[StockReportSourceDTO] = []
        for table, label, fields, result_key in specifications:
            columns = self._columns(table)
            if not columns:
                continue
            code_col = _pick(columns, "stock_code", "證券代號")
            decision_col = _pick(columns, "decision_date", "日期")
            available_col = _pick(columns, "available_date", "available_at")
            if code_col is None or decision_col is None:
                raise ValueError(f"{table} 缺少股票代號／決策日欄位")
            filters = [
                f"{_quote(code_col)} = ?",
                f"{_non_empty_expr(decision_col)}",
                f"{_date_key_expr(decision_col)} <= ?",
            ]
            params_list: list[Any] = [code, _date_key(cutoff)]
            observed_col = _pick(columns, "observed_at")
            if include_current and observed_col:
                filters.append(f"julianday({_quote(observed_col)}) <= julianday(?)")
                params_list.append((observed_at or self.clock()).isoformat())
            elif available_col:
                filters.extend(
                    (
                        f"{_non_empty_expr(available_col)}",
                        f"{_date_key_expr(available_col)} <= ?",
                    )
                )
                params_list.append(_date_key(cutoff))
            select = [
                _select_column(columns, ("decision_date", "日期"), "data_as_of"),
                _select_column(columns, ("observed_at", "available_date", "available_at") if include_current else ("available_date", "available_at"), "available_at"),
                _select_column(columns, ("source_version",), "source_version"),
                _select_column(columns, ("quality",), "quality"),
            ]
            select.extend(_select_column(columns, (key,), key) for key, _label in fields)
            sql = f"""
                SELECT {", ".join(select)}
                FROM {self._table(table)}
                WHERE {" AND ".join(filters)}
                ORDER BY {_date_key_expr(decision_col)} DESC
                LIMIT 1
            """
            rows = self._query(sql, tuple(params_list))
            metrics: list[StockMetricDTO] = []
            if rows:
                row = rows[0]
                data_as_of = _iso_date(row["data_as_of"])
                available_at = str(row["available_at"] or "") if include_current and observed_col else _iso_date(row["available_at"])
                quality = _quality(row["quality"])
                for key, field_label in fields:
                    raw = row[key]
                    number = _decimal(raw)
                    text_value = "" if number is not None else str(raw or "")
                    if number is None and not text_value:
                        continue
                    metrics.append(
                        StockMetricDTO(
                            key=key,
                            label=field_label,
                            value=number,
                            value_text=text_value,
                            unit=("bp" if key.endswith("_bp") else "股" if result_key == "institutional" else "交易單位" if result_key == "credit" else ""),
                            data_as_of=data_as_of,
                            available_at=available_at,
                            source_id=f"sqlite.{table}",
                            quality=quality,
                        )
                    )
            result[result_key] = tuple(metrics)
            sources.append(
                self._source(
                    f"sqlite.{table}",
                    label,
                    row_count=len(metrics),
                    data_as_of=_iso_date(rows[0]["data_as_of"]) if rows else "",
                    available_at=(str(rows[0]["available_at"] or "") if include_current and observed_col else _iso_date(rows[0]["available_at"])) if rows else "",
                    version=str(rows[0]["source_version"] or "") if rows else "",
                    quality=_quality(rows[0]["quality"]) if rows else ReportQuality.MISSING.value,
                    cutoff=cutoff,
                    limitations=("沒有該股票 row 時維持缺資料，不補零。",),
                )
            )
        if include_current and self.candidate_db_file is not None and self.candidate_db_file.is_file():
            from data_module.institutional_revision_read_model import read_current_institutional, FIELDS
            with sqlite3.connect(self.candidate_db_file.resolve().as_uri() + '?mode=ro', uri=True) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA query_only=ON')
                conn.execute('BEGIN')
                row = read_current_institutional(
                    conn,
                    stock_code=code,
                    observed_at=observed_at or self.clock(),
                    decision_date=cutoff,
                )
            if row is not None:
                source_id = 'candidate.institutional.current_restated'
                labels = dict(specifications[0][2])
                result['institutional'] = tuple(StockMetricDTO(
                    key=field, label=labels[field], value=Decimal(row[field]), unit='股',
                    data_as_of=row['decision_date'], available_at=row['available_at'],
                    source_id=source_id, quality=ReportQuality.OBSERVED.value,
                ) for field in FIELDS)
                sources = [source for source in sources if source.source_id != 'sqlite.institutional_flows']
                sources.append(self._source(source_id, '法人現況研究（保留歷史版本）',
                    row_count=len(FIELDS), data_as_of=row['decision_date'], available_at=row['available_at'],
                    version=row.get('revision_observation_hash', row['source_version']),
                    quality=ReportQuality.OBSERVED.value, cutoff=cutoff,
                    limitations=('此為候選現況／修訂觀測，不授歷史PIT；原始列與失敗checkpoint保留。',)))
        if include_current:
            from data_module.current_observed_market_ownership_reader import (
                read_current_observed_market_ownership,
            )

            current_result = read_current_observed_market_ownership(
                stock_code=code,
                cutoff=cutoff,
                observed_at=observed_at or self.clock(),
                candidate_db_file=self.candidate_db_file,
                capture_root=self.current_ownership_capture_root,
                readback_clock=readback_clock or self.clock,
            )
            metric_labels = {
                "institutional": dict(specifications[0][2]),
                "credit": dict(specifications[1][2]),
                "tdcc": dict(specifications[2][2]),
            }
            source_ids = {
                "institutional": "candidate.phase3c.institutional_normalized",
                "credit": "candidate.phase3c.credit_normalized",
                "tdcc": "candidate.tdcc.raw_current_observed",
            }
            result_keys = {"institutional": "institutional", "credit": "credit", "tdcc": "shareholding"}
            source_labels = {
                "institutional": "目前觀測／非歷史 PIT：法人買賣超",
                "credit": "目前觀測／非歷史 PIT：信用交易",
                "tdcc": "目前觀測／非歷史 PIT：集保持股分布",
            }
            replaced_ids = {
                "institutional": {"sqlite.institutional_flows", "candidate.institutional.current_restated"},
                "credit": {"sqlite.credit_transactions"},
                "tdcc": {"sqlite.tdcc_shareholding"},
            }
            for kind, observation in current_result.observations.items():
                metric_rows: list[StockMetricDTO] = []
                for key, raw_value in observation.values.items():
                    unit = {
                        "shares": "股",
                        "lots": "張",
                        "trading_units": "交易單位",
                    }.get(observation.quantity_unit, observation.quantity_unit)
                    if kind == "tdcc":
                        unit = "基點" if key.endswith("_bp") else "層級"
                    number = Decimal(raw_value) if isinstance(raw_value, int) else None
                    metric_rows.append(StockMetricDTO(
                        key=key,
                        label=metric_labels[kind].get(key, key),
                        value=number,
                        value_text="" if number is not None else str(raw_value),
                        unit=unit,
                        data_as_of=observation.data_as_of,
                        available_at="",
                        source_id=source_ids[kind],
                        quality=ReportQuality.DEGRADED.value,
                    ))
                result[result_keys[kind]] = tuple(metric_rows)
                sources = [source for source in sources if source.source_id not in replaced_ids[kind]]
                custody_description = (
                    "Phase 3C 正規化觀測留存；原始 HTTP 回應位元組未留存"
                    if observation.custody_kind == "normalized_custody"
                    else "TDCC 官方原始回應及全量 aggregate 重播已驗證"
                )
                source_id = source_ids[kind]
                source_limits: tuple[str, ...] = (
                    "目前觀測候選資料；不得用於歷史 PIT 或正式資格",
                    "官方發布時間及可用時間未知；不將觀測時間當成發布時間",
                )
                if observation.custody_kind == "normalized_custody":
                    source_limits += ("原始 HTTP 回應未留存；只驗證正規化觀測 payload 與候選表",)
                else:
                    source_limits += ("TDCC 原始回應、層級及全量 aggregate 已按雜湊重驗",)
                sources.append(StockReportSourceDTO(
                    source_id=source_id,
                    source_label=source_labels[kind],
                    status=ReportSectionStatus.PARTIAL.value,
                    quality=ReportQuality.DEGRADED.value,
                    data_as_of=observation.data_as_of,
                    available_at="",
                    freshness=ReportFreshness.UNKNOWN.value,
                    version=f"{observation.source_version}:{observation.custody_sha256}",
                    row_count=observation.row_count,
                    limitations=source_limits,
                    freshness_reason=(
                        f"目前觀測時間 {observation.observed_at}；{custody_description}；"
                        "可用時間未知；非歷史 PIT"
                    ),
                    observed_at=observation.observed_at,
                    candidate_only=True,
                    current_observed_only=True,
                    historical_pit_eligible=False,
                ))
            for kind in ("institutional", "credit", "tdcc"):
                if kind in current_result.observations:
                    continue
                diagnostic = current_result.diagnostics.get(kind, "目前來源未提供可驗證觀測")
                source_id = source_ids[kind]
                sources.append(StockReportSourceDTO(
                    source_id=source_id,
                    source_label=source_labels[kind],
                    status=ReportSectionStatus.MISSING.value,
                    quality=ReportQuality.DEGRADED.value,
                    data_as_of="",
                    available_at="",
                    freshness=ReportFreshness.UNKNOWN.value,
                    row_count=0,
                    limitations=(f"目前觀測來源未載入：{diagnostic}", "發布／可用時間未知；非歷史 PIT"),
                    freshness_reason=f"目前觀測來源未載入或未通過驗證：{diagnostic}",
                    candidate_only=True,
                    current_observed_only=True,
                    historical_pit_eligible=False,
                ))
        return result["institutional"], result["credit"], result["shareholding"], tuple(sources)

    def _read_events(
        self,
        code: str,
        cutoff: date,
    ) -> tuple[tuple[StockEvidenceEventDTO, ...], StockReportSourceDTO | None]:
        table = "evidence_events"
        columns = self._columns(table)
        if not columns:
            return (), None
        symbol_col = _pick(columns, "symbol", "stock_code", "證券代號")
        available_col = _pick(columns, "available_date", "available_at")
        decision_col = _pick(columns, "decision_date", "日期")
        if symbol_col is None or decision_col is None:
            raise ValueError("evidence_events 缺少 symbol／decision_date 欄位")
        if available_col is None:
            raise ValueError("evidence_events 缺少 available_date，拒絕猜測 PIT 可用時間")
        fields = (
            "event_id", "event_date", "decision_date", "event_type", "event_family",
            "source_type", "source_id", "source_version", "data_quality", "as_of_date",
            "available_at", "reason_codes_json", "why_not_codes_json", "risk_codes_json",
            "warnings_json", "score_bp",
        )
        select = []
        for field_name in fields:
            source_names: tuple[str, ...] = (field_name,)
            if field_name == "data_quality":
                source_names = ("data_quality", "quality")
            elif field_name == "available_at":
                source_names = ("available_at", "available_date")
            select.append(_select_column(columns, source_names, field_name))
        sql = f"""
            SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(symbol_col)} = ?
              AND {_non_empty_expr(available_col)}
              AND {_date_key_expr(available_col)} <= ?
              AND {_non_empty_expr(decision_col)}
              AND {_date_key_expr(decision_col)} <= ?
            ORDER BY {_date_key_expr(decision_col)} DESC
            LIMIT ?
        """
        rows = self._query(sql, (code, _date_key(cutoff), _date_key(cutoff), _EVENT_LIMIT))
        event_ids = tuple(str(row["event_id"] or "") for row in rows if row["event_id"])
        outcomes = self._read_outcomes(event_ids, cutoff) if event_ids else {}
        events = tuple(
            StockEvidenceEventDTO(
                event_id=str(row["event_id"] or ""),
                event_date=_iso_date(row["event_date"]),
                decision_date=_iso_date(row["decision_date"]),
                event_type=str(row["event_type"] or ""),
                event_family=str(row["event_family"] or ""),
                source_type=str(row["source_type"] or ""),
                source_id=str(row["source_id"] or ""),
                source_version=str(row["source_version"] or ""),
                data_quality=str(row["data_quality"] or ""),
                as_of_date=_iso_date(row["as_of_date"]),
                available_at=_iso_date(row["available_at"]),
                reasons=_json_strings(row["reason_codes_json"]),
                why_not_reasons=_json_strings(row["why_not_codes_json"]),
                risk_reasons=_json_strings(row["risk_codes_json"]),
                warnings=_json_strings(row["warnings_json"]),
                score_bp=_integer(row["score_bp"]),
                outcomes=outcomes.get(str(row["event_id"] or ""), ()),
            )
            for row in rows
        )
        source = self._source(
            "sqlite.evidence_events",
            "SQLite 事件與 Evidence",
            row_count=len(events),
            data_as_of=_latest_text(event.decision_date for event in events),
            available_at=_latest_text(event.available_at for event in events),
            version=_latest_text(event.source_version for event in events),
            quality=_worst_quality(
                _quality(event.data_quality) for event in events
            ),
            cutoff=cutoff,
            limitations=("只讀取 available_date 不晚於查詢日的有限歷史 row；沒有 outcome 不補績效。",),
        )
        return events, source

    def _read_outcomes(
        self,
        event_ids: Sequence[str],
        cutoff: date,
    ) -> dict[str, tuple[StockOutcomeDTO, ...]]:
        table = "evidence_outcomes"
        columns = self._columns(table)
        if not columns or not event_ids:
            return {}
        event_col = _pick(columns, "event_id")
        if event_col is None:
            return {}
        calculated_col = _pick(columns, "calculated_at", "available_at")
        if calculated_col is None:
            return {}
        placeholders = ", ".join("?" for _ in event_ids)
        select = (
            _select_column(columns, ("event_id",), "event_id"),
            _select_column(columns, ("window_days",), "window_days"),
            _select_column(columns, ("outcome_status",), "outcome_status"),
            _select_column(columns, ("forward_return_bp",), "forward_return_bp"),
            _select_column(columns, ("benchmark_excess_bp",), "benchmark_excess_bp"),
            _select_column(columns, ("data_quality",), "data_quality"),
            _select_column(columns, ("calculated_at", "available_at"), "calculated_at"),
        )
        sql = f"""
            SELECT {", ".join(select)}
            FROM {self._table(table)}
            WHERE {_quote(event_col)} IN ({placeholders})
              AND {_non_empty_expr(calculated_col)}
              AND {_date_key_expr(calculated_col)} <= ?
            ORDER BY {_quote(event_col)}, {_select_raw(columns, ("window_days",))}
            LIMIT ?
        """
        rows = self._query(sql, (*event_ids, _date_key(cutoff), _EVENT_LIMIT * 3))
        grouped: dict[str, list[StockOutcomeDTO]] = {}
        for row in rows:
            event_id = str(row["event_id"] or "")
            grouped.setdefault(event_id, []).append(
                StockOutcomeDTO(
                    window_days=_integer(row["window_days"]) or 0,
                    outcome_status=str(row["outcome_status"] or ""),
                    forward_return_bp=_integer(row["forward_return_bp"]),
                    benchmark_excess_bp=_integer(row["benchmark_excess_bp"]),
                    data_quality=str(row["data_quality"] or ""),
                    calculated_at=str(row["calculated_at"] or ""),
                )
            )
        return {key: tuple(value) for key, value in grouped.items()}

    def _read_market_status(
        self,
        code: str,
        cutoff: date,
    ) -> tuple[StockMarketStatusSnapshotDTO, StockReportSourceDTO | None]:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        current_date = now.astimezone(_TAIPEI).date()
        if cutoff != current_date:
            limitation = "上市與交易狀態只代表當下觀測；歷史報告不會顯示目前狀態。"
            return (
                StockMarketStatusSnapshotDTO(status="unknown", limitations=(limitation,)),
                self._source(
                    "official.current_market_status", "Official current market status",
                    row_count=0, data_as_of="", available_at="",
                    quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                    limitations=(limitation,),
                ),
            )
        try:
            if self.market_status_provider is not None:
                raw = self.market_status_provider(code)
            elif self.market_status_pointer_path is not None:
                if not self.market_status_pointer_path.is_file():
                    raise FileNotFoundError("current market status pointer is missing")
                raw = CurrentMarketStatusReader.from_pointer(
                    self.market_status_pointer_path
                ).get(code)
            else:
                raise FileNotFoundError("current market status output root is not configured")
        except Exception as exc:
            reason = f"官方當下上市／交易狀態不可用：{type(exc).__name__}: {str(exc).splitlines()[0]}"
            dto = StockMarketStatusSnapshotDTO(
                status="unavailable",
                limitations=(reason, "沒有狀態證據不代表停牌或下市。"),
            )
            return dto, self._source(
                "official.current_market_status", "Official current market status",
                row_count=0, data_as_of="", available_at="",
                quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=dto.limitations,
            )

        if (
            _object_text(raw, "symbol") != code
            or _object_text(raw, "scope") != "current_only"
            or _object_value(raw, "pit_eligible") is not False
        ):
            limitation = "上市／交易狀態來源識別或 current-only 能力標記無效。"
            dto = StockMarketStatusSnapshotDTO(status="unavailable", limitations=(limitation,))
            return dto, self._source(
                "official.current_market_status", "Official current market status",
                row_count=0, data_as_of="", available_at="",
                quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=(limitation,),
            )

        observed_text = _object_text(raw, "observed_at")
        observed_clock = _aware_timestamp(observed_text)
        if observed_clock is None or observed_clock > now:
            limitation = "上市／交易狀態缺少有效時區擷取時間，或擷取時間晚於報告時間。"
            dto = StockMarketStatusSnapshotDTO(status="unavailable", limitations=(limitation,))
            return dto, self._source(
                "official.current_market_status", "Official current market status",
                row_count=0, data_as_of="", available_at="",
                quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=(limitation,),
            )
        observed_text = observed_clock.isoformat()
        listing_status = _object_text(raw, "listing_status")
        if listing_status not in {"listed", "delisted", "conflict", "unknown"}:
            listing_status = "unknown"
        raw_data_dates = _object_strings(raw, "source_data_dates")
        source_ids = _object_strings(raw, "source_ids")
        source_data_dates: list[str] = []
        limitations = [
            "上市／交易狀態只作當下註記，不改變排序、Advice、ML 特徵或歷史重播。",
        ]
        for raw_date in raw_data_dates:
            parsed = _coerce_date(raw_date)
            if parsed is None:
                limitations.append("一筆來源資料日格式無法解析，該日期未顯示。")
                continue
            source_data_dates.append(parsed.isoformat())
            if parsed > current_date:
                limitations.append("來源標示的上市／交易狀態資料日晚於目前報告日期。")
        restrictions: list[StockTradingRestrictionDTO] = []
        raw_restrictions = _object_value(raw, "trading_restrictions")
        if isinstance(raw_restrictions, Sequence) and not isinstance(raw_restrictions, (str, bytes)):
            for item in raw_restrictions[:100]:
                if not isinstance(item, Mapping):
                    limitations.append("一筆交易限制資料格式無效，未予顯示。")
                    continue
                if str(item.get("symbol", "") or "").strip() not in {"", code}:
                    limitations.append("一筆其他股票的交易限制資料已拒絕。")
                    continue
                restriction_source = str(item.get("source_id", "") or "").strip()
                restriction_hash = str(item.get("raw_sha256", "") or "").strip()
                restriction_observed = _aware_timestamp(item.get("observed_at"))
                if (
                    not restriction_source
                    or restriction_source not in source_ids
                    or not _is_sha256(restriction_hash)
                    or restriction_observed is None
                    or restriction_observed > now
                ):
                    limitations.append("一筆限制資料缺少可驗證的來源、雜湊或擷取時間，未予顯示。")
                    continue
                date_values: dict[str, str] = {}
                for name in ("effective_from", "effective_to", "resumed_on"):
                    parsed = _coerce_date(str(item.get(name, "") or ""))
                    date_values[name] = parsed.isoformat() if parsed else ""
                    if item.get(name) and parsed is None:
                        limitations.append(f"限制資料的 {name} 日期格式無效，保留未知。")
                restriction_source_dates = tuple(
                    parsed.isoformat()
                    for value in _object_strings(item, "source_data_dates")
                    if (parsed := _coerce_date(value)) is not None
                )
                published = _coerce_date(str(item.get("published_date", "") or ""))
                restrictions.append(StockTradingRestrictionDTO(
                    restriction_type=str(item.get("restriction_type", "") or "").strip(),
                    restriction_state=str(item.get("restriction_state", "") or "").strip(),
                    effective_from=date_values["effective_from"],
                    effective_to=date_values["effective_to"],
                    resumed_on=date_values["resumed_on"],
                    published_date=published.isoformat() if published else "",
                    notice_reference=str(item.get("notice_reference", "") or "").strip(),
                    source_id=restriction_source,
                    evidence_type=str(item.get("evidence_type", "") or "").strip(),
                    observed_at=restriction_observed.isoformat(),
                    source_data_dates=restriction_source_dates,
                    market=str(item.get("market", "") or "").strip(),
                    name=str(item.get("name", "") or "").strip(),
                    details=str(item.get("details", "") or "").strip(),
                    raw_sha256=restriction_hash.lower(),
                    source_url=str(item.get("source_url", "") or "").strip(),
                ))
        status_evidence: list[StockMarketStatusEvidenceDTO] = []
        raw_status_evidence = _object_value(raw, "status_evidence")
        if isinstance(raw_status_evidence, Sequence) and not isinstance(raw_status_evidence, (str, bytes)):
            for item in raw_status_evidence[:100]:
                if not isinstance(item, Mapping):
                    limitations.append("一筆上市／交易狀態證據格式無效，未予顯示。")
                    continue
                evidence_symbol = str(item.get("symbol", "") or "").strip()
                evidence_source = str(item.get("source_id", "") or "").strip()
                evidence_hash = str(item.get("raw_sha256", "") or "").strip()
                evidence_observed = _aware_timestamp(item.get("observed_at"))
                if (
                    evidence_symbol != code
                    or evidence_source not in source_ids
                    or not _is_sha256(evidence_hash)
                    or evidence_observed is None
                    or evidence_observed > now
                ):
                    limitations.append("一筆上市／交易狀態證據的股票、來源、雜湊或擷取時間不符，已拒絕。")
                    continue
                evidence_dates: dict[str, str] = {}
                for name in ("published_date", "effective_from", "effective_to", "resumed_on"):
                    parsed = _coerce_date(str(item.get(name, "") or ""))
                    evidence_dates[name] = parsed.isoformat() if parsed else ""
                    if item.get(name) and parsed is None:
                        limitations.append(f"狀態證據的 {name} 日期無法解析，保留未知。")
                evidence_source_dates = tuple(
                    parsed.isoformat()
                    for value in _object_strings(item, "source_data_dates")
                    if (parsed := _coerce_date(value)) is not None
                )
                status_evidence.append(StockMarketStatusEvidenceDTO(
                    evidence_type=str(item.get("evidence_type", "") or "").strip(),
                    source_id=evidence_source,
                    observed_at=evidence_observed.isoformat(),
                    published_date=evidence_dates["published_date"],
                    effective_from=evidence_dates["effective_from"],
                    effective_to=evidence_dates["effective_to"],
                    resumed_on=evidence_dates["resumed_on"],
                    notice_reference=str(item.get("notice_reference", "") or "").strip(),
                    source_data_dates=evidence_source_dates,
                    raw_sha256=evidence_hash.lower().removeprefix("sha256:"),
                    source_url=str(item.get("source_url", "") or "").strip(),
                    market=str(item.get("market", "") or "").strip(),
                    name=str(item.get("name", "") or "").strip(),
                    details=str(item.get("details", "") or "").strip(),
                    restriction_type=str(item.get("restriction_type", "") or "").strip(),
                    restriction_state=str(item.get("restriction_state", "") or "").strip(),
                ))
        partial_failure = _object_value(raw, "partial_failure") is True
        source_warnings = _object_strings(raw, "source_warnings")
        if partial_failure or source_warnings:
            limitations.extend(source_warnings)
        has_status_evidence = listing_status in {"listed", "delisted"} or bool(restrictions) or bool(status_evidence)
        status = (
            "partial" if partial_failure or source_warnings or listing_status == "conflict"
            else "available" if has_status_evidence
            else "unknown"
        )
        if not has_status_evidence:
            limitations.append("沒有觀測到此股票的上市或交易限制資料；狀態維持未知。")
        dto = StockMarketStatusSnapshotDTO(
            status=status,
            listing_status=listing_status,
            market=_object_text(raw, "market"),
            name=_object_text(raw, "name"),
            trading_restrictions=tuple(restrictions),
            status_evidence=tuple(status_evidence),
            source_ids=source_ids,
            source_data_dates=tuple(sorted(set(source_data_dates))),
            observed_at=observed_text,
            source_warnings=source_warnings,
            partial_failure=partial_failure,
            scope="current_only",
            pit_eligible=False,
            limitations=tuple(_dedupe(limitations)),
        )
        data_as_of = max(dto.source_data_dates) if dto.source_data_dates else ""
        source = self._source(
            "official.current_market_status", "Official current market status",
            row_count=1 if has_status_evidence else 0,
            data_as_of=data_as_of,
            available_at=observed_text,
            version=",".join(dto.source_ids),
            quality=(ReportQuality.OBSERVED.value if status == "available" else ReportQuality.DEGRADED.value),
            cutoff=cutoff,
            limitations=dto.limitations,
        )
        return dto, source

    def _future_cutoff_report(
        self,
        code: str,
        cutoff: date,
        context: object | None,
        generated_at: datetime,
    ) -> StockResearchReportDTO:
        """拒絕未來日期，避免把目前最新 row 標成尚未發生的日期。"""

        context_map = _context_map(context)
        context_code = context_map.get("stock_code", "")
        name = context_map.get("stock_name", "") if context_code in {"", code} else ""
        reason = f"查詢日期 {cutoff.isoformat()} 晚於目前台北日期；拒絕以目前資料填入未來日期。"
        labels = (
            ("price", "價格"),
            ("technical", "技術指標"),
            ("fundamental", "基本面／營收財報"),
            ("flows", "籌碼／分點"),
            ("ownership", "法人／信用／集保"),
            ("events", "產業／事件／歷史結果"),
            ("position", "持倉／Health／Exit"),
            ("advice", "既有建議與依據"),
            ("ml", "ML 研究結果"),
        )
        sections = tuple(
            StockReportSectionDTO(
                section_id=section_id,
                label=label,
                status=ReportSectionStatus.ERROR.value,
                summary=reason,
                limitations=(reason,),
            )
            for section_id, label in labels
        )
        return StockResearchReportDTO(
            stock_code=code,
            stock_name=name,
            as_of=cutoff.isoformat(),
            generated_at=generated_at.isoformat(),
            sections=sections,
            attention_reasons=(reason,),
            limitations=(reason,),
            research_context=context_map,
            read_only=True,
        )

    def _read_scenario_position(
        self, code: str, cutoff: date, context: object | None,
        context_map: Mapping[str, str], cancel_callback: Callable[[], bool] | None,
    ) -> PortfolioScenarioStockProjection:
        raw_ref = context.get("portfolio_scenario_ref") if isinstance(context, Mapping) else getattr(context, "portfolio_scenario_ref", None)
        ref = raw_ref if type(raw_ref) is PortfolioScenarioStockReference else PortfolioScenarioStockReference.from_mapping(raw_ref)
        if context_map.get("source_snapshot_id") != ref.artifact_id or self.portfolio_research_workspace is None:
            raise ValueError("原配置研究參照不符或workspace未配置，不讀其他帳本")
        self._check_cancel(cancel_callback)
        saved = self.portfolio_research_workspace.open_exact(
            ref.artifact_id, account_kind=ref.account_kind, portfolio_id=ref.portfolio_id,
            cancel_callback=cancel_callback,
        )
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        if saved.comparison.decision_at > now or saved.comparison.decision_at.astimezone(_TAIPEI).date() != cutoff:
            raise ValueError("原配置研究決策時鐘與本次個股範圍不符")
        projected = project_saved_scenario_stock(
            saved, reference=ref, stock_code=code,
            expected_account_source_hash=context_map.get("source_snapshot_hash", ""),
        )
        self._check_cancel(cancel_callback)
        return projected

    def _read_position(
        self,
        code: str,
        cutoff: date,
        context: Mapping[str, str],
        *,
        price_points: Sequence[StockPricePointDTO] = (),
        price_source: StockReportSourceDTO | None = None,
    ) -> tuple[StockPositionSnapshotDTO | None, StockReportSourceDTO | None]:
        if context.get("source_kind") == "portfolio_research_scenario":
            raise ValueError("配置封存禁止以目前同股持倉替代")
        if self.portfolio_service is None:
            return None, None
        getter = getattr(self.portfolio_service, "get_position_detail", None)
        if not callable(getter):
            return None, None
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        current_date = now.astimezone(_TAIPEI).date()
        if cutoff != current_date:
            reason = "\u6301\u5009\u4f86\u6e90\u53ea\u63d0\u4f9b\u7576\u4e0b\u72c0\u614b\uff1b\u6b77\u53f2\u6301\u5009\u8207 Exit \u4e0d\u986f\u793a\u3002"
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", available_at="", quality=ReportQuality.UNAVAILABLE.value,
                cutoff=cutoff, limitations=(reason,),
            )

        position = getter(code)
        if position is None:
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.MISSING.value, cutoff=cutoff,
                limitations=("\u6301\u5009\u4f86\u6e90\u6c92\u6709\u6b64\u80a1\u7684\u7cbe\u78ba\u6301\u5009\u5217\u3002",),
            )
        try:
            position_code = _normalize_stock_code(getattr(position, "stock_code", ""))
        except ValueError:
            position_code = ""
        if position_code != code:
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=("\u6301\u5009\u4f86\u6e90\u56de\u50b3\u4e0d\u540c\u80a1\u865f\uff0c\u5df2\u62d2\u7d55\u8a72\u5217\u3002",),
            )

        position_id = str(getattr(position, "position_id", "") or "").strip()
        portfolio_id = str(getattr(position, "portfolio_id", "") or "").strip()
        if context.get("position_id") and context["position_id"] != position_id:
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=("\u6301\u5009\u8b58\u5225\u8207\u76ee\u524d\u9078\u5b9a\u7684\u5167\u5bb9\u4e0d\u7b26\u3002",),
            )
        if context.get("portfolio_id") and context["portfolio_id"] != portfolio_id:
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=("\u6295\u8cc7\u7d44\u5408\u8b58\u5225\u8207\u76ee\u524d\u9078\u5b9a\u7684\u5167\u5bb9\u4e0d\u7b26\u3002",),
            )

        limitations: list[str] = ["\u6301\u5009\u5217\u50c5\u4ee3\u8868\u672c\u6b21\u7576\u4e0b\u8b80\u53d6\uff1b\u4f86\u6e90\u672a\u63d0\u4f9b\u7368\u7acb\u7684\u64f7\u53d6\u6642\u9593\u3002"]
        opened_at = str(getattr(position, "opened_at", "") or "").strip()
        opened_date = _coerce_date(opened_at)
        if opened_at and (opened_date is None or opened_date > cutoff):
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=("\u6301\u5009\u958b\u7acb\u65e5\u671f\u7121\u6548\u6216\u665a\u65bc\u5831\u544a\u65e5\uff0c\u5df2\u62d2\u7d55\u8a72\u5217\u3002",),
            )

        raw_last_trade_date = str(getattr(position, "last_trade_date", "") or "").strip()
        parsed_last_trade = _coerce_date(raw_last_trade_date)
        if raw_last_trade_date and parsed_last_trade is None:
            limitations.append("持倉的最後交易日格式有誤；此日期只代表交易事件，不作行情日期使用。")
        elif parsed_last_trade is not None and parsed_last_trade > cutoff:
            return None, self._source(
                "portfolio.position", "Portfolio position/health", row_count=0,
                data_as_of="", quality=ReportQuality.UNAVAILABLE.value, cutoff=cutoff,
                limitations=("持倉最後交易日晚於報告日期，已拒絕該持倉列。",),
            )

        dated_prices: list[tuple[date, StockPricePointDTO]] = []
        for candidate in price_points:
            price_date = _coerce_date(candidate.data_date)
            if (
                price_date is not None
                and price_date <= cutoff
                and price_date <= current_date
                and candidate.close_price is not None
                and candidate.close_price > 0
                and _is_sha256(candidate.source_snapshot_hash)
            ):
                dated_prices.append((price_date, candidate))
        quote_date, quote_point = max(dated_prices, key=lambda item: item[0]) if dated_prices else (None, None)
        quote_available_at = ""
        if quote_point is not None and quote_point.available_at:
            quote_clock = _aware_timestamp(quote_point.available_at)
            if quote_clock is None or quote_clock > now:
                quote_point = None
                quote_date = None
                limitations.append("行情來源可得時間無效或晚於報告時間，已拒絕該行情列。")
            else:
                quote_available_at = quote_clock.isoformat()
        quote_is_dated = quote_point is not None and quote_date is not None
        if not quote_is_dated:
            limitations.append("報告沒有同股、具日期且已指紋驗證的行情列；現價、損益、健康度與 Exit 暫不顯示。")
        elif not quote_available_at:
            limitations.append("行情列有交易所資料日與來源，但沒有可驗證的實際可得時間。")
        quote_freshness_verified = bool(
            quote_is_dated
            and price_source is not None
            and price_source.source_id == "sqlite.daily_prices"
            and price_source.freshness == ReportFreshness.FRESH.value
            and _coerce_date(price_source.data_as_of) == quote_date
            and quote_point is not None
            and quote_point.source_id == price_source.source_id
        )
        if quote_is_dated and not quote_freshness_verified:
            freshness_label = (
                price_source.freshness
                if price_source is not None
                else ReportFreshness.UNKNOWN.value
            )
            limitations.append(
                f"行情 freshness 為 {freshness_label}；仍保留標示資料日的價格與損益，"
                "但不作當下 Health 或 Exit 判定。"
            )

        quantity = _decimal(getattr(position, "quantity", None))
        average_cost = _decimal(getattr(position, "average_cost", None))
        invested = _decimal(getattr(position, "invested_amount", None))
        current_price = quote_point.close_price if quote_is_dated and quote_point is not None else None
        unrealized = None
        unrealized_pct = None
        if current_price is not None and quantity is not None and average_cost is not None:
            unrealized = ((current_price - average_cost) * quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
            pnl_basis = abs(average_cost * quantity)
            if pnl_basis > 0:
                unrealized_pct = unrealized / pnl_basis
        if invested is None and average_cost is not None and quantity is not None:
            invested = abs(average_cost * quantity)

        exposure_bp: int | None = None
        portfolio_getter = getattr(self.portfolio_service, "get_portfolio", None)
        if callable(portfolio_getter) and invested is not None:
            with suppress(Exception):
                portfolio = portfolio_getter()
                total = _decimal(getattr(portfolio, "total_invested_amount", None))
                if total is not None and total > 0:
                    exposure_bp = int(
                        (invested / total * Decimal("10000")).to_integral_value(
                            rounding=ROUND_HALF_EVEN
                        )
                    )

        source_summary = getattr(position, "source_summary", {})
        source_summary = source_summary if isinstance(source_summary, Mapping) else {}
        has_evaluable_price_thesis = any(
            _decimal(source_summary.get(field)) is not None
            for field in ("stop_loss_pct", "take_profit_pct")
        )
        condition: PortfolioConditionResult | None = None
        if (
            self.condition_monitor is not None
            and quote_freshness_verified
            and has_evaluable_price_thesis
            and current_price is not None
        ):
            condition = self.condition_monitor.evaluate(
                position,
                PortfolioCurrentSnapshot(
                    current_price=current_price,
                    quote_data_date=quote_date,
                    quote_source_id=(quote_point.source_id if quote_point is not None else ""),
                    quote_source_snapshot_hash=(
                        quote_point.source_snapshot_hash if quote_point is not None else ""
                    ),
                    quote_freshness_status="current",
                    quote_expected_date=quote_date,
                ),
            )
        trace = tuple(value for value in (
            str(getattr(position, "source_type", "") or ""),
            str(getattr(position, "source_id", "") or ""),
            quote_point.source_id if quote_point is not None else "",
            quote_date.isoformat() if quote_date is not None else "",
            quote_point.source_snapshot_hash if quote_point is not None else "",
            "PortfolioConditionMonitor" if condition is not None else "",
        ) if value)
        health = self.position_health_service.evaluate(
            stock_code=code,
            condition_result=condition,
            feedback_status=None,
            source_trace=trace,
        )
        if self.condition_monitor is None:
            limitations.append("持倉狀態監測器不可用；健康度僅顯示觀察狀態，未執行條件評估。")
        health_status = health.state.value
        health_label = health.state.value
        health_reasons = list(health.reasons)
        if not quote_freshness_verified:
            health_status = "UNKNOWN"
            freshness_label = (
                price_source.freshness
                if price_source is not None
                else ReportFreshness.UNKNOWN.value
            )
            health_label = (
                "未知（行情已過期）"
                if freshness_label == ReportFreshness.STALE.value
                else "未知（行情新鮮度未驗證）"
            )
            health_reasons.append(
                f"行情 freshness 為 {freshness_label}；僅保留價格／損益觀察，不評定持倉 Health。"
            )
        elif not has_evaluable_price_thesis:
            health_status = "UNKNOWN"
            health_label = "未知（僅價格／成本觀察）"
            health_reasons.append(
                "持倉沒有可與當下行情核對的結構化停損／停利假設；價格與損益不代表 thesis 健康。"
            )
            limitations.append(
                "持倉缺少可評估的結構化停損／停利假設；只顯示價格與損益，Health 保持未知。"
            )

        exit_status = "unavailable"
        exit_reasons: tuple[str, ...] = ()
        exit_source_id = ""
        exit_available_at = ""
        if quote_is_dated and not quote_freshness_verified:
            exit_reasons = ("行情 freshness 未通過；此 Exit 不可用。",)
        elif quote_is_dated and not has_evaluable_price_thesis:
            exit_reasons = ("持倉沒有可評估的結構化 thesis；未產生 Exit 判定。",)
        if quote_freshness_verified and has_evaluable_price_thesis and self.exit_provider is not None:
            raw_exit = _call_provider(
                self.exit_provider,
                code,
                cutoff,
                context=context,
                position=position,
                quote_snapshot=quote_point,
                condition_result=condition,
                health_result=health,
            )
            if raw_exit is not None:
                exit_date = _iso_date(_object_text(raw_exit, "data_as_of"))
                raw_exit_available = _object_text(raw_exit, "available_at")
                exit_available_clock = _aware_timestamp(raw_exit_available) if raw_exit_available else None
                exact_exit = (
                    _object_text(raw_exit, "stock_code") == code
                    and bool(position_id)
                    and _object_text(raw_exit, "position_id") == position_id
                    and bool(portfolio_id)
                    and _object_text(raw_exit, "portfolio_id") == portfolio_id
                    and quote_date is not None
                    and exit_date == quote_date.isoformat()
                    and (not raw_exit_available or (exit_available_clock is not None and exit_available_clock <= now))
                    and _object_value(raw_exit, "research_only") is True
                    and _object_value(raw_exit, "auto_action_allowed") is False
                )
                quote_hash = quote_point.source_snapshot_hash if quote_point is not None else ""
                exit_hash = _object_text(raw_exit, "source_snapshot_hash")
                if not _is_sha256(quote_hash) or exit_hash.lower() != quote_hash.lower():
                    exact_exit = False
                if exact_exit:
                    exit_status = _object_text(raw_exit, "status", "state") or "unavailable"
                    exit_reasons = _object_strings(raw_exit, "reasons", "limitations")
                    exit_source_id = _object_text(raw_exit, "source_id")
                    exit_available_at = raw_exit_available
                else:
                    limitations.append("Exit 讀取模型與本次持倉及報告行情來源不完全相符，已拒絕。")
            else:
                limitations.append("沒有與本次持倉及行情日期精確相符的當下 Exit 讀取模型。")
        elif self.exit_provider is None:
            limitations.append("尚未設定 Portfolio Exit 唯讀來源。")

        if not position_id or not portfolio_id:
            limitations.append("持倉識別資料不完整，Exit 不可用。")
        source_snapshot_hash = str(getattr(position, "source_snapshot_hash", "") or "").strip()
        if not source_snapshot_hash:
            limitations.append("持倉來源快照雜湊缺失，來源品質降級。")
        snapshot = StockPositionSnapshotDTO(
            is_holding=bool(getattr(position, "is_holding", True)),
            position_id=position_id,
            portfolio_id=portfolio_id,
            position_as_of=current_date.isoformat(),
            quote_data_date=quote_date.isoformat() if quote_is_dated and quote_date else "",
            quote_available_at=quote_available_at,
            quantity=quantity,
            average_cost=average_cost,
            invested_amount=invested,
            current_price=current_price,
            unrealized_pnl=unrealized,
            unrealized_pnl_pct=unrealized_pct,
            exposure_bp=exposure_bp,
            source_type=str(getattr(position, "source_type", "") or ""),
            source_id=str(getattr(position, "source_id", "") or ""),
            source_snapshot_hash=source_snapshot_hash,
            quote_source_snapshot_hash=(quote_point.source_snapshot_hash if quote_is_dated and quote_point else ""),
            opened_at=opened_at,
            last_trade_date=(parsed_last_trade.isoformat() if parsed_last_trade else raw_last_trade_date),
            health_status=health_status,
            health_label=health_label,
            health_reasons=tuple(_dedupe(health_reasons)),
            health_source_trace=tuple(health.source_trace),
            exit_status=exit_status,
            exit_reasons=exit_reasons,
            exit_source_id=exit_source_id,
            exit_available_at=exit_available_at,
            exit_research_only=True,
            exit_auto_action_allowed=False,
            limitations=tuple(_dedupe(limitations)),
        )
        source = self._source(
            "portfolio.position",
            "Portfolio position/health",
            row_count=1,
            data_as_of=current_date.isoformat(),
            available_at="",
            quality=(ReportQuality.OBSERVED.value
                     if quote_is_dated and position_id and portfolio_id and source_snapshot_hash and quote_available_at
                     else ReportQuality.DEGRADED.value),
            cutoff=cutoff,
            limitations=tuple(_dedupe((*limitations, "行情資料日另列於 quote_data_date；持倉日期不以行情日期代替。"))),
        )
        return snapshot, source

    def _read_advice(
        self,
        code: str,
        cutoff: date,
        context: Mapping[str, str],
    ) -> tuple[StockAdviceSnapshotDTO, StockReportSourceDTO | None]:
        if context.get("source_kind") == _DAILY_MARKET_RESEARCH_SOURCE_KIND:
            return (
                StockAdviceSnapshotDTO(
                    status=ReportQuality.UNAVAILABLE.value,
                    limitations=(
                        "每日市場研究快照只記錄既有條件觀察，不是已保存推薦或正式 Advice。",
                    ),
                ),
                None,
            )
        service = self.watchlist_analysis_service
        if service is None:
            return (
                StockAdviceSnapshotDTO(
                    limitations=("WatchlistAnalysisService 尚未提供保存結果讀取入口。",),
                ),
                None,
            )
        source_id = context.get("result_id") or context.get("source_id") or ""
        analysis = service.fetch(code, source_id, cutoff)
        if analysis.status != "saved":
            return (
                StockAdviceSnapshotDTO(
                    status=ReportQuality.UNAVAILABLE.value,
                    saved_analysis=analysis,
                    rule_reasons=(analysis.reasons,) if analysis.reasons else (),
                    limitations=(analysis.message or "沒有可用的已保存推薦結果。",),
                ),
                self._source(
                    f"recommendation.{analysis.result_id or source_id or 'latest'}",
                    "已保存推薦結果",
                    row_count=0,
                    data_as_of=analysis.data_date,
                    quality=ReportQuality.MISSING.value,
                    cutoff=cutoff,
                    limitations=(analysis.message or "沒有可用的已保存推薦結果。",),
                ),
            )
        raw_decision_date = str(analysis.decision_date or "").strip()
        decision_date = raw_decision_date or cutoff.isoformat()
        decision_date_value = _coerce_date(decision_date)
        raw_data_date = str(analysis.data_date or "").strip()
        data_date_value = _coerce_date(raw_data_date)
        data_date_problem = ""
        if raw_decision_date and (
            decision_date_value is None
            or decision_date_value.isoformat() != raw_decision_date
        ):
            data_date_problem = (
                f"保存來源決策／as-of 日期格式無效：{raw_decision_date!r}；拒絕合成 Advice。"
            )
        elif decision_date_value is not None and decision_date_value > cutoff:
            data_date_problem = (
                f"保存來源決策／as-of 日期 {decision_date_value.isoformat()} 晚於查詢截止日 "
                f"{cutoff.isoformat()}；拒絕合成 Advice。"
            )
        elif raw_data_date and (
            data_date_value is None or data_date_value.isoformat() != raw_data_date
        ):
            data_date_problem = (
                f"保存來源市場資料日格式無效：{raw_data_date!r}；拒絕合成 Advice。"
            )
        elif (
            data_date_value is not None
            and decision_date_value is not None
            and data_date_value > decision_date_value
        ):
            data_date_problem = (
                f"保存來源市場資料日 {data_date_value.isoformat()} 晚於來源決策／as-of 日期 "
                f"{decision_date_value.isoformat()}；拒絕合成 Advice。"
            )
        elif data_date_value is not None and data_date_value > cutoff:
            data_date_problem = (
                f"保存來源市場資料日 {data_date_value.isoformat()} 晚於查詢截止日 "
                f"{cutoff.isoformat()}；拒絕合成 Advice。"
            )
        if data_date_problem:
            return (
                StockAdviceSnapshotDTO(
                    status=ReportQuality.UNAVAILABLE.value,
                    saved_analysis=analysis,
                    rule_reasons=(analysis.reasons,) if analysis.reasons else (),
                    limitations=(data_date_problem,),
                ),
                self._source(
                    f"recommendation.{analysis.result_id or source_id or 'selected'}",
                    "Recommendation / Advice",
                    row_count=0,
                    data_as_of=raw_data_date,
                    quality=ReportQuality.UNAVAILABLE.value,
                    cutoff=cutoff,
                    limitations=(data_date_problem,),
                    status_override=ReportQuality.UNAVAILABLE.value,
                ),
            )
        result = service.load_result(analysis.result_id, as_of_date=cutoff)
        if result is None:
            return (
                StockAdviceSnapshotDTO(
                    status=ReportQuality.UNAVAILABLE.value,
                    saved_analysis=analysis,
                    limitations=("保存結果在查詢日邊界外，不能當成當下 Advice。",),
                ),
                None,
            )
        advice_limitations = [
            "Advice 沿用既有 AdviceComposer；本報告不重新計分、不自動下單。",
        ]
        if data_date_value is None:
            data_date = ""
            advice_limitations.append("推薦來源沒有可驗證的 data_date，故資料日保持未知。")
        else:
            data_date = data_date_value.isoformat()
        dashboard = AdviceComposer(AdvicePolicy()).compose(
            recommendations=result,
            portfolio_result=None,
            evidence_quality=ReportQuality.DEGRADED.value.upper(),
            decision_date=decision_date,
            # AdviceComposer 需要合法日期；缺少來源 data_date 時只以決策日
            # 完成既有唯讀投影，來源 DTO 仍保留空白，不把它宣稱為資料日。
            data_as_of_date=data_date or decision_date,
            mode=AdviceMode.GUIDED,
            evidence_warnings=("此 Advice 來自已保存研究快照，非即時重新評分。",),
        )
        recommendation = next(
            (row for row in dashboard.recommendations if row.stock_code == code),
            None,
        )
        if recommendation is None:
            return (
                StockAdviceSnapshotDTO(
                    status=ReportQuality.UNAVAILABLE.value,
                    saved_analysis=analysis,
                    limitations=("保存結果不包含此股票；未入選不等於看空。",),
                ),
                None,
            )
        recommendation = replace(recommendation, data_as_of_date=data_date)
        rule_reasons = _dedupe(
            (
                *recommendation.why_reasons,
                *recommendation.why_not_reasons,
                *recommendation.risk_reasons,
                analysis.reasons,
            )
        )
        source = self._source(
            f"recommendation.{analysis.result_id}",
            "已保存推薦／Advice 快照",
            row_count=1,
            data_as_of=data_date,
            available_at=analysis.analysis_date,
            version=analysis.profile_version,
            quality=ReportQuality.DEGRADED.value,
            cutoff=cutoff,
            limitations=(
                "保存結果只作研究參考，Advice policy 已將 evidence_quality 設為 DEGRADED。",
                *advice_limitations[1:],
            ),
        )
        return (
            StockAdviceSnapshotDTO(
                status=ReportQuality.DEGRADED.value,
                recommendation=recommendation,
                saved_analysis=analysis,
                rule_reasons=rule_reasons,
                agreement="not_comparable",
                limitations=tuple(advice_limitations),
            ),
            source,
        )

    def _read_ml(
        self,
        code: str,
        cutoff: date,
        context: Mapping[str, str],
    ) -> StockMLSnapshotDTO:
        if self.ml_provider is None:
            return StockMLSnapshotDTO(
                limitations=("沒有可用的目前研究模型登錄唯讀來源；ML 預測暫不可讀取。",),
            )
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("report clock must include a timezone")
        if cutoff != now.astimezone(_TAIPEI).date():
            return StockMLSnapshotDTO(
                limitations=("此研究模型只支援當下觀測；歷史日期不具使用資格。",),
            )

        context_map = dict(context)
        context_map["stock_code"] = code
        explicit_mode = context_map.get("ml_scope_mode", "")
        linked_saved_decision = bool(context_map.get("result_id")) or bool(
            context_map.get("source_snapshot_id") and context_map.get("source_snapshot_hash")
        )
        expected_mode = explicit_mode or (
            "selected_saved_decision" if linked_saved_decision else "current_stock_research"
        )
        if expected_mode not in {"current_stock_research", "selected_saved_decision"}:
            return StockMLSnapshotDTO(
                status=ReportQuality.UNAVAILABLE.value,
                scope_mode=expected_mode,
                limitations=(f"ML 範圍設定不受支援：{expected_mode}。",),
            )
        if expected_mode == "current_stock_research" and not context_map.get("current_event_date"):
            return StockMLSnapshotDTO(
                scope_mode=expected_mode,
                limitations=("目前 ML 需要報告內同股且有明確交易日的行情列。",),
            )
        expected_price_fingerprint = context_map.get("current_price_row_fingerprint_sha256", "")
        if expected_mode == "current_stock_research" and not _is_sha256(expected_price_fingerprint):
            return StockMLSnapshotDTO(
                scope_mode=expected_mode,
                limitations=("目前 ML 需要報告行情列的 OHLCV 指紋精確一致。",),
            )
        if expected_mode == "selected_saved_decision" and (
            not context_map.get("source_snapshot_hash")
            or not any(context_map.get(name) for name in ("result_id", "source_id", "source_snapshot_id"))
        ):
            return StockMLSnapshotDTO(
                scope_mode=expected_mode,
                limitations=("指定保存決策的 ML 必須提供確切的結果與來源快照識別。",),
            )

        result = _call_provider(self.ml_provider, code, cutoff, context=context_map)
        if result is None:
            reason = (
                "沒有與此股票及精確行情日期相符的當下 ML 執行紀錄。"
                if expected_mode == "current_stock_research"
                else "沒有與選定保存決策及來源識別精確相符的 ML 執行紀錄。"
            )
            return StockMLSnapshotDTO(scope_mode=expected_mode, limitations=(reason,))

        result_code = _object_text(result, "stock_code")
        run_id = _object_text(result, "run_id")
        source_id = _object_text(result, "source_id")
        model_manifest_sha = _object_text(result, "model_manifest_sha256")
        model_bundle_sha = _object_text(result, "model_bundle_sha256")
        dataset_version = _object_text(result, "dataset_version")
        model_version = _object_text(result, "model_version")
        event_date = _coerce_date(_object_text(result, "event_date"))
        inference_at = _aware_timestamp(_object_text(result, "inference_at"))
        generated_at = _aware_timestamp(_object_text(result, "available_at"))
        model_available_at = _aware_timestamp(_object_text(result, "model_available_at"))
        result_scope = _object_text(result, "scope_mode")
        result_context = _object_value(result, "context_identity")
        context_matches = isinstance(result_context, Mapping)
        if expected_mode == "selected_saved_decision":
            if isinstance(result_context, Mapping):
                context_matches = all(
                    str(result_context.get(key, "") or "").strip() == value
                    for key, value in context_map.items()
                    if key in {
                        "result_id", "source_id", "source_snapshot_id", "source_snapshot_hash",
                        "decision_date", "data_date", "profile_id", "profile_version",
                        "source_version", "source_kind", "source_workspace",
                        "mapping_source_id", "mapping_version", "mapping_observed_date",
                    }
                    and value
                )
            else:
                context_matches = False
        raw_prediction = _object_value(result, "predicted_benchmark_excess_return_bp")
        target_metric = _object_text(result, "target_metric")
        prediction_keys = _object_strings(result, "prediction_keys")
        predictions: dict[str, int] = {}
        if isinstance(raw_prediction, Mapping):
            for key, value in raw_prediction.items():
                if isinstance(value, bool) or not isinstance(value, int):
                    predictions = {}
                    break
                predictions[str(key)] = value
        symbols = _object_strings(result, "scope_symbols")
        source_snapshot_hash = _object_text(result, "source_snapshot_hash")
        expected_date = _coerce_date(context_map.get("current_event_date"))
        identity_ok = (
            result_code == code
            and expected_mode == result_scope
            and event_date is not None
            and event_date <= cutoff
            and code in symbols
            and 2 <= len(symbols) <= 16
            and _is_sha256(model_manifest_sha)
            and _is_sha256(model_bundle_sha)
            and _is_sha256(dataset_version)
            and _is_sha256(source_snapshot_hash)
            and target_metric == "benchmark_excess_after_standard_80bp_cost"
            and bool(prediction_keys)
            and set(predictions) == set(prediction_keys)
            and bool(run_id)
            and bool(source_id)
            and bool(model_version)
            and bool(predictions)
            and inference_at is not None
            and generated_at is not None
            and model_available_at is not None
            and context_matches
        )
        if expected_mode == "current_stock_research":
            identity_ok = identity_ok and (
                expected_date == event_date
                and _object_text(result, "current_price_row_fingerprint_sha256").lower()
                == expected_price_fingerprint.lower()
                and bool(_object_text(result, "cycle_id"))
            )
        else:
            selected_data_date = _coerce_date(context_map.get("data_date"))
            if selected_data_date is not None:
                identity_ok = identity_ok and selected_data_date == event_date
        if inference_at is not None and model_available_at is not None and generated_at is not None:
            identity_ok = identity_ok and (
                model_available_at <= inference_at <= now
                and inference_at <= generated_at <= now
                and inference_at.astimezone(_TAIPEI).date() <= cutoff
                and generated_at.astimezone(_TAIPEI).date() <= cutoff
            )
        identity_ok = identity_ok and (
            _object_value(result, "research_only") is True
            and _object_value(result, "historical_pit_eligible") is False
            and _object_value(result, "formal_qualified") is False
            and _object_value(result, "production_action_allowed") is False
        )
        if not identity_ok:
            return StockMLSnapshotDTO(
                scope_mode=expected_mode,
                status=ReportQuality.UNAVAILABLE.value,
                limitations=("ML 唯讀來源回傳了錯股、錯日期、雜湊未固定、過期或範圍不符的執行紀錄。",),
            )

        if event_date is None or inference_at is None or generated_at is None or model_available_at is None:
            return StockMLSnapshotDTO(
                scope_mode=expected_mode,
                status=ReportQuality.UNAVAILABLE.value,
                limitations=("ML 執行時間或行情日期缺失，已拒絕結果。",),
            )

        h5 = _object_value(result, "h5")
        if not isinstance(h5, Mapping):
            h5 = {}
        h5_status = str(h5.get("status", _object_text(result, "h5_status")) or "unknown")
        h5_horizon = _integer(h5.get("horizon", _object_value(result, "h5_horizon")))
        h5_end = _coerce_date(h5.get("horizon_end_date", _object_value(result, "h5_horizon_end_date")))
        limitations: list[str] = []
        if h5_status == "mature_gross_label":
            next_entry = _coerce_date(h5.get("next_entry_date"))
            gross_stock = h5.get("gross_stock_return_bp")
            gross_benchmark = h5.get("gross_benchmark_return_bp")
            target_excess = h5.get("benchmark_excess_after_standard_80bp_cost")
            after_lane = h5.get("after_lane_cost_stock_return_bp")
            valid_h5_ints = all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (gross_stock, gross_benchmark, target_excess)
            )
            valid_h5_math = (
                isinstance(gross_stock, int)
                and not isinstance(gross_stock, bool)
                and isinstance(gross_benchmark, int)
                and not isinstance(gross_benchmark, bool)
                and isinstance(target_excess, int)
                and not isinstance(target_excess, bool)
                and target_excess == gross_stock - gross_benchmark - 80
            )
            h5_clock = generated_at.astimezone(_TAIPEI).date() if generated_at is not None else None
            if (
                h5_horizon != 5
                or h5_end is None
                or next_entry is None
                or event_date is None
                or next_entry <= event_date
                or h5_end < next_entry
                or h5_end > cutoff
                or h5_clock is None
                or h5_end > h5_clock
                or not valid_h5_ints
                or not valid_h5_math
                or (after_lane is not None and (isinstance(after_lane, bool) or not isinstance(after_lane, int)))
            ):
                return StockMLSnapshotDTO(
                    scope_mode=expected_mode,
                    status=ReportQuality.UNAVAILABLE.value,
                    limitations=("成熟 H5 的日期、算術或整數結果欄位無效，已拒絕該結果。",),
                )
        elif h5_status not in {"not_mature", "not_mature_as_of_cutoff"}:
            h5_status = "unknown"
            h5 = {}
            limitations.append("H5 成熟狀態資料缺失或不受支援。")
        else:
            limitations.append("H5 標籤尚未成熟；不顯示報酬或成功結果。")
            if any(h5.get(name) is not None for name in (
                "gross_stock_return_bp", "gross_benchmark_return_bp",
                "benchmark_excess_after_standard_80bp_cost", "after_lane_cost_stock_return_bp",
                "next_entry_date", "horizon_end_date", "round_trip_cost", "price_inputs",
            )):
                return StockMLSnapshotDTO(
                    scope_mode=expected_mode,
                    status=ReportQuality.UNAVAILABLE.value,
                    limitations=("H5 尚未成熟，但 ML 來源已回傳結果欄位，已拒絕該資料。",),
                )

        def h5_int(key: str, fallback: str) -> int | None:
            value = h5.get(key, _object_value(result, fallback))
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                return None
            return value

        qualifications = _object_strings(result, "qualification")
        target_costs = _validated_target_costs(target_metric, {
            "total_round_trip_cost_bp": _object_value(result, "target_round_trip_cost_bp"),
            "buy_side_cost_bp": _object_value(result, "target_buy_side_cost_bp"),
            "sell_side_cost_bp": _object_value(result, "target_sell_side_cost_bp"),
        })
        explanations = _dedupe((
            "此為當下重述研究預測，不具歷史 PIT 資格，也未完成正式校準。",
            "輸出為此執行紀錄確切股票範圍內的基準超額報酬基點。",
            *qualifications,
        ))
        return StockMLSnapshotDTO(
            status=ReportQuality.DEGRADED.value,
            model_version=model_version,
            dataset_version=dataset_version,
            inference_at=inference_at.isoformat(),
            available_at=generated_at.isoformat(),
            model_available_at=model_available_at.isoformat(),
            research_or_formal="research_only",
            explanations=explanations,
            source_id=source_id,
            run_id=run_id,
            scope_mode=expected_mode,
            event_date=event_date.isoformat(),
            model_manifest_sha256=model_manifest_sha,
            model_bundle_sha256=model_bundle_sha,
            source_snapshot_hash=source_snapshot_hash,
            target_metric=target_metric,
            current_price_row_fingerprint_sha256=_object_text(
                result, "current_price_row_fingerprint_sha256"
            ),
            predicted_benchmark_excess_return_bp=predictions,
            target_round_trip_cost_bp=target_costs[0],
            target_buy_side_cost_bp=target_costs[1],
            target_sell_side_cost_bp=target_costs[2],
            h5_status=h5_status,
            h5_horizon=h5_horizon,
            h5_gross_stock_return_bp=h5_int("gross_stock_return_bp", "h5_gross_stock_return_bp"),
            h5_gross_benchmark_return_bp=h5_int("gross_benchmark_return_bp", "h5_gross_benchmark_return_bp"),
            h5_benchmark_excess_after_standard_80bp_cost=h5_int(
                "benchmark_excess_after_standard_80bp_cost",
                "h5_benchmark_excess_after_standard_80bp_cost",
            ),
            h5_after_lane_cost_stock_return_bp=h5_int(
                "after_lane_cost_stock_return_bp", "h5_after_lane_cost_stock_return_bp"
            ),
            h5_horizon_end_date=h5_end.isoformat() if h5_end else "",
            scope_symbols=symbols,
            research_only=True,
            historical_pit_eligible=False,
            formal_qualified=False,
            production_action_allowed=False,
            qualification=qualifications,
            limitations=tuple(limitations),
        )

    def _ml_source(self, ml: StockMLSnapshotDTO, cutoff: date) -> StockReportSourceDTO | None:
        if ml.status in {ReportQuality.UNAVAILABLE.value, ReportQuality.MISSING.value}:
            return None
        return self._source(
            ml.source_id or "ml.read_provider",
            "ML 唯讀研究結果",
            row_count=1,
            data_as_of=ml.event_date,
            available_at=ml.available_at,
            version=ml.model_manifest_sha256 or ml.model_version,
            quality=ml.status,
            cutoff=cutoff,
            limitations=ml.limitations,
        )

    def _source(
        self,
        source_id: str,
        label: str,
        *,
        row_count: int,
        data_as_of: str,
        period: str = "",
        available_at: str = "",
        version: str = "",
        quality: str = ReportQuality.OBSERVED.value,
        cutoff: date,
        limitations: Sequence[str] = (),
        coverage_status: str = "",
        status_override: str | None = None,
        preserve_source_quality: bool = False,
    ) -> StockReportSourceDTO:
        freshness_source_id = _FRESHNESS_SOURCE_ALIASES.get(source_id, source_id)
        freshness_evidence = self._freshness_statuses.get().get(freshness_source_id)
        freshness, freshness_validation = _freshness_from_evidence(
            data_as_of,
            cutoff,
            freshness_evidence,
            period=period,
        )
        normalized_quality = _quality(quality)
        evidence_status = str(
            freshness_evidence.get("freshness_status", "")
            if freshness_evidence is not None
            else ""
        ).strip().lower()
        source_limitations = list(limitations)
        if freshness_validation:
            source_limitations.append(f"Freshness probe：{freshness_validation}")
        freshness_reason = str(
            freshness_evidence.get("reason", "")
            if freshness_evidence is not None
            else ""
        ).strip()
        if freshness_evidence is not None and evidence_status in {
            "failed",
            "unknown",
            "not_applicable",
        }:
            # 有 row 但共同 probe 無法證明來源狀態時，顯示 partial／degraded，
            # 不能讓存在資料列看起來像已完成 freshness 驗證。
            if not preserve_source_quality and normalized_quality in {
                ReportQuality.OBSERVED.value,
                ReportQuality.ESTIMATED.value,
            }:
                normalized_quality = ReportQuality.DEGRADED.value
            if freshness_reason:
                source_limitations.append(f"Freshness probe：{freshness_reason}")
        elif freshness_evidence is not None and evidence_status in {
            "expected_wait",
            "stale",
            "partial",
        } and freshness_reason:
            source_limitations.append(f"Freshness probe：{freshness_reason}")
        if (
            row_count > 0
            and freshness == ReportFreshness.UNKNOWN.value
            and not preserve_source_quality
        ):
            if normalized_quality in {
                ReportQuality.OBSERVED.value,
                ReportQuality.ESTIMATED.value,
            }:
                normalized_quality = ReportQuality.DEGRADED.value
            source_limitations.append("來源沒有可驗證的 freshness cadence／期間，保留未知狀態。")
        resolved_available_at = available_at
        if not resolved_available_at and freshness_evidence is not None:
            candidate_available_at = str(
                freshness_evidence.get("available_at", "") or ""
            ).strip()
            candidate_date = _coerce_date(candidate_available_at)
            if candidate_date is not None and candidate_date <= cutoff:
                resolved_available_at = candidate_available_at
        status = status_override or (
            ReportSectionStatus.MISSING.value
            if row_count == 0
            else ReportSectionStatus.STALE.value
            if freshness == ReportFreshness.STALE.value
            else ReportSectionStatus.PARTIAL.value
            if evidence_status in {"failed", "unknown", "not_applicable"}
            or freshness == ReportFreshness.UNKNOWN.value
            else ReportSectionStatus.AVAILABLE.value
        )
        return StockReportSourceDTO(
            source_id=source_id,
            source_label=label,
            status=status,
            quality=normalized_quality,
            data_as_of=data_as_of,
            available_at=resolved_available_at,
            freshness=freshness,
            version=version,
            row_count=row_count,
            limitations=tuple(_dedupe(source_limitations)),
            frequency=(
                str(freshness_evidence.get("frequency", "") or "").strip()
                if freshness_evidence is not None
                else ""
            ),
            expected_period=(
                str(freshness_evidence.get("expected_period", "") or "").strip()
                if freshness_evidence is not None
                else ""
            ),
            freshness_reason=freshness_reason,
            coverage_status=coverage_status,
        )

    def _data_section(
        self,
        section_id: str,
        label: str,
        row_count: int,
        source: StockReportSourceDTO | Sequence[StockReportSourceDTO] | None,
        *,
        missing_reason: str,
    ) -> StockReportSectionDTO:
        sources = (
            (source,)
            if isinstance(source, StockReportSourceDTO)
            else tuple(source or ())
        )
        source_ids = tuple(item.source_id for item in sources)
        data_as_of = _latest_text(item.data_as_of for item in sources)
        available_at = _latest_text(item.available_at for item in sources)
        freshness = (
            ReportFreshness.STALE.value
            if any(item.freshness == ReportFreshness.STALE.value for item in sources)
            else ReportFreshness.FRESH.value
            if sources and any(item.freshness == ReportFreshness.FRESH.value for item in sources)
            else ReportFreshness.UNKNOWN.value
        )
        if row_count == 0:
            status = ReportSectionStatus.MISSING.value
            summary = missing_reason
            limitations: tuple[str, ...] = (missing_reason,)
        elif freshness == ReportFreshness.STALE.value:
            status = ReportSectionStatus.STALE.value
            summary = "來源依官方交易日／公告 cadence 判定為過期或範圍不足；詳見來源與限制。"
            limitations = _dedupe(tuple(item for source_item in sources for item in source_item.limitations))
        elif any(item.quality in {ReportQuality.DEGRADED.value, ReportQuality.ESTIMATED.value} for item in sources):
            status = ReportSectionStatus.PARTIAL.value
            summary = "有資料但品質或來源欄位不完整；詳見來源與限制。"
            limitations = _dedupe(tuple(item for source_item in sources for item in source_item.limitations))
        else:
            status = ReportSectionStatus.AVAILABLE.value
            summary = "已取得有限資料。"
            limitations = _dedupe(tuple(item for source_item in sources for item in source_item.limitations))
        return StockReportSectionDTO(
            section_id=section_id,
            label=label,
            status=status,
            summary=summary,
            data_as_of=data_as_of,
            available_at=available_at,
            freshness=freshness,
            source_ids=source_ids,
            limitations=limitations,
        )

    @staticmethod
    def _error_section(section_id: str, label: str, error: str) -> StockReportSectionDTO:
        return StockReportSectionDTO(
            section_id=section_id,
            label=label,
            status=ReportSectionStatus.ERROR.value,
            summary=error,
            limitations=(error,),
        )

    def _register_source(
        self,
        sources: list[StockReportSourceDTO],
        source: StockReportSourceDTO,
    ) -> None:
        if not any(item.source_id == source.source_id for item in sources):
            sources.append(source)

    def _load_freshness_statuses(
        self,
        cutoff: date,
        *,
        report_at: datetime,
    ) -> Mapping[str, Mapping[str, object]]:
        """載入單次報告使用的 freshness receipt。

        這裡只讀既有 probe 的明確檔案，不掃描 ``latest`` 檔案，也不從
        ``MAX(date)`` 猜測月／季資料是否已到期。receipt 的檢查時間若晚於
        報告時鐘，整份證據會被忽略，避免把未來狀態包進報告。current
        報告可在舊 receipt 的 daily row 仍對應到最新應發布官方 session
        時沿用；其他來源與歷史 cutoff 維持同日 receipt 規則。
        """

        path = self.freshness_status_path
        if path is None or not path.is_file():
            return {}
        try:
            with path.open("rb") as handle:
                raw = handle.read(_FRESHNESS_MAX_BYTES + 1)
        except OSError:
            return {}
        if len(raw) > _FRESHNESS_MAX_BYTES:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, Mapping):
            return {}
        checked_date = _freshness_checked_date(payload.get("checked_at"))
        if checked_date is None:
            return {}
        if not self._freshness_receipt_matches_config(payload):
            return {}
        if report_at.tzinfo is None or report_at.utcoffset() is None:
            return {}

        report_at_utc = report_at.astimezone(timezone.utc)
        is_current_report = report_at.astimezone(_TAIPEI).date() == cutoff
        receipt_checked_at = _freshness_checked_at(payload.get("checked_at"))
        carry_daily_session: date | None = None
        same_day_daily_session: date | None = None
        if is_current_report and (
            receipt_checked_at is None or receipt_checked_at > report_at_utc
        ):
            return {}
        if checked_date == cutoff:
            # Current report 不接受同日但晚於本次 report clock 的 receipt。
            # 歷史 cutoff 保留既有同日日期契約，避免把當下時鐘挪作歷史可得性。
            if (
                is_current_report
                and receipt_checked_at is not None
                and receipt_checked_at > report_at_utc
            ):
                return {}
        elif is_current_report and checked_date < cutoff:
            # 不用固定「前一日」或週末天數推 freshness。只有舊 receipt 的
            # daily actual/expected period 都等於本次 clock 下，既有官方日曆
            # 與專案 publication cutoff 證明的最新應發布 session，才可沿用。
            # 其他來源仍保持 unknown；來源時鐘缺失、未來或日曆 unresolved 皆 fail closed。
            if receipt_checked_at is None or receipt_checked_at > report_at_utc:
                return {}
            carry_daily_session, _calendar_reason = self._latest_completed_official_session(
                report_at
            )
            if carry_daily_session is None:
                return {}
        else:
            # 歷史 cutoff 不沿用其他日期的 freshness receipt。
            return {}

        if is_current_report and checked_date == cutoff:
            same_day_daily_session, _calendar_reason = (
                self._latest_completed_official_session(report_at)
            )

        items = payload.get("source_statuses")
        if not isinstance(items, list):
            return {}
        result: dict[str, Mapping[str, object]] = {}
        invalid_daily_clock_evidence: Mapping[str, object] | None = None
        for item in items:
            if not isinstance(item, Mapping):
                continue
            # probe 的 candidate_only 只描述候選 DB，不能替正式 SQLite
            # read model 證明 current／fresh；候選資料要經正式發布後才可
            # 進入本 service 的 source evidence。
            if item.get("candidate_only") is True:
                continue
            source_id = str(item.get("source_id", "") or "").strip()
            status = str(item.get("freshness_status", "") or "").strip().lower()
            if not source_id or status not in _FRESHNESS_STATUS_VALUES:
                continue
            if source_id == "sqlite.daily_prices" and is_current_report:
                source_available_at = item.get("available_at")
                has_source_clock = source_available_at is not None and not (
                    isinstance(source_available_at, str)
                    and not source_available_at.strip()
                )
                if has_source_clock:
                    source_checked_at = _freshness_checked_at(source_available_at)
                    if (
                        source_checked_at is None
                        or receipt_checked_at is None
                        or source_checked_at > receipt_checked_at
                        or source_checked_at > report_at_utc
                    ):
                        invalid_evidence = dict(item)
                        invalid_evidence["available_at"] = ""
                        if status in {"current", "expected_wait"}:
                            invalid_evidence["freshness_status"] = "unknown"
                            invalid_evidence["reason"] = (
                                "daily source available_at 時鐘無效或晚於 freshness receipt/report 時鐘"
                            )
                        invalid_daily_clock_evidence = invalid_evidence
                        continue
            if carry_daily_session is not None:
                if source_id != "sqlite.daily_prices" or status not in {
                    "current",
                    "expected_wait",
                }:
                    continue
                expected_period = _normalize_period(item.get("expected_period"))
                actual_period = _normalize_period(item.get("actual_period"))
                session_period = carry_daily_session.isoformat()
                if expected_period != session_period or actual_period != session_period:
                    continue
            elif (
                is_current_report
                and checked_date == cutoff
                and source_id == "sqlite.daily_prices"
                and status in {"current", "expected_wait"}
            ):
                if same_day_daily_session is None:
                    continue
                expected_period = _normalize_period(item.get("expected_period"))
                actual_period = _normalize_period(item.get("actual_period"))
                session_period = same_day_daily_session.isoformat()
                if expected_period != session_period or actual_period != session_period:
                    continue
            result[source_id] = item
        if invalid_daily_clock_evidence is not None:
            # 若同一 receipt 重複列出 daily source，只要一筆明示錯誤時鐘，
            # 就不讓另一筆狀態覆蓋它而把 current freshness 誤判為 fresh。
            result["sqlite.daily_prices"] = invalid_daily_clock_evidence
        return result

    def _freshness_receipt_matches_config(self, payload: Mapping[str, object]) -> bool:
        """確認 freshness receipt 與本次報告使用同一資料根與 SQLite。"""

        checks = payload.get("checks")
        checks_map = checks if isinstance(checks, Mapping) else {}
        receipt_db = payload.get("db_path") or checks_map.get("db_path")
        receipt_root = payload.get("data_root")
        configured_db = getattr(self.config, "db_file", None)
        if configured_db is None or not receipt_db or not receipt_root:
            return False
        configured_db_path = Path(str(configured_db)).expanduser().resolve(strict=False)
        configured_root = getattr(self.config, "data_root", None)
        if configured_root is None:
            # SimpleNamespace／輕量測試 config 沒有 data_root 時，SQLite
            # 的 parent/parent 是唯一可驗證的 fallback；正式 TWStockConfig
            # 一定會走明確 data_root。
            configured_root = configured_db_path.parent.parent
        configured_root_path = Path(str(configured_root)).expanduser().resolve(strict=False)
        try:
            receipt_db_path = Path(str(receipt_db)).expanduser().resolve(strict=False)
            receipt_root_path = Path(str(receipt_root)).expanduser().resolve(strict=False)
        except (OSError, ValueError, TypeError):
            return False
        return receipt_db_path == configured_db_path and receipt_root_path == configured_root_path

    def _columns(self, table: str) -> tuple[str, ...]:
        if table in self._column_cache:
            return self._column_cache[table]
        if self.db is None:
            return ()
        columns = tuple(self.db.get_table_columns(table))
        self._column_cache[table] = columns
        return columns

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[Any]:
        if self.db is None:
            return []
        with self.db.connect() as conn:
            return list(conn.execute(sql, params).fetchall())

    @staticmethod
    def _table(table: str) -> str:
        return _quote(table)

    @staticmethod
    def _check_cancel(cancel_callback: Callable[[], bool] | None) -> None:
        if cancel_callback is not None and cancel_callback():
            raise StockResearchReportCancelled("stock research report read cancelled")


def _normalize_stock_code(value: object) -> str:
    code = str(value or "").strip()
    if not code:
        raise ValueError("stock_code is required")
    return code


def _coerce_date(value: date | str | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    with suppress(ValueError):
        return date.fromisoformat(text[:10])
    return None


def _date_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def _iso_date(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    compact = text.replace("-", "").replace("/", "")
    if len(compact) >= 8 and compact[:8].isdigit():
        raw = compact[:8]
        with suppress(ValueError):
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    with suppress(ValueError):
        return date.fromisoformat(text[:10]).isoformat()
    return text


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _pick(columns: Sequence[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _select_raw(columns: Sequence[str], candidates: Sequence[str]) -> str:
    column = _pick(columns, *candidates)
    return _quote(column) if column else "0"


def _select_column(columns: Sequence[str], candidates: Sequence[str], alias: str) -> str:
    column = _pick(columns, *candidates)
    return f"{_quote(column)} AS {_quote(alias)}" if column else f"NULL AS {_quote(alias)}"


def _date_key_expr(column: str) -> str:
    return f"substr(replace(replace(CAST({_quote(column)} AS TEXT), '-', ''), '/', ''), 1, 8)"


def _non_empty_expr(column: str) -> str:
    return f"NULLIF(TRIM(CAST({_quote(column)} AS TEXT)), '') IS NOT NULL"


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _db_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes"}


def _price_row_fingerprint(
    *,
    code: str,
    data_date: str,
    open_price: Decimal | None,
    high_price: Decimal | None,
    low_price: Decimal | None,
    close_price: Decimal | None,
    volume: int | None,
    turnover: Decimal | None,
) -> str:
    try:
        return stock_price_row_fingerprint_sha256(
            stock_code=code,
            data_date=data_date,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
            turnover=turnover,
        )
    except ValueError:
        return ""


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _integer(value: object) -> int | None:
    decimal = _decimal(value)
    if decimal is None:
        return None
    with suppress(InvalidOperation, ValueError):
        return int(decimal.to_integral_value(rounding=ROUND_HALF_EVEN))
    return None


def _quality(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"observed", "ready", "pass", "passed"}:
        return ReportQuality.OBSERVED.value
    if text in {"estimated", "estimate"}:
        return ReportQuality.ESTIMATED.value
    if text in {"stale", "expired"}:
        return ReportQuality.STALE.value
    if text in {"missing", "unavailable", "blocked"}:
        return ReportQuality.MISSING.value
    if text in {"", "unknown"}:
        return ReportQuality.DEGRADED.value
    return ReportQuality.DEGRADED.value


def _freshness_checked_date(value: object) -> date | None:
    """將 freshness receipt 的檢查時間轉為台北日曆日。"""

    parsed: datetime | None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            with suppress(ValueError):
                return date.fromisoformat(text[:10])
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone(_TAIPEI).date()


def _freshness_checked_at(value: object) -> datetime | None:
    """解析可比較的 freshness receipt aware clock；不把日期字串當時鐘。"""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _freshness_from_evidence(
    data_as_of: str,
    cutoff: date,
    evidence: Mapping[str, object] | None,
    *,
    period: str = "",
) -> tuple[str, str]:
    """以 receipt cadence 與個股實際期間判斷 freshness。

    沒有與本次報告日期、資料根及 SQLite 綁定的 receipt 時，只有 PIT
    日期邊界可驗證，不能把資料日較早直接稱為 stale；週末／月季公告期
    可能合法落後，故保留 unknown。
    """

    if evidence is None:
        return (
            ReportFreshness.UNKNOWN.value,
            "缺少與本報告 cutoff、data root 及 SQLite 綁定的 freshness receipt。",
        )
    data_date = _coerce_date(data_as_of)
    if data_date is not None and data_date > cutoff:
        return ReportFreshness.UNKNOWN.value, "來源資料日晚於查詢日，拒絕 future freshness。"
    status = str(evidence.get("freshness_status", "") or "").strip().lower()
    if status in {"current", "expected_wait"}:
        expected_period = _normalize_period(evidence.get("expected_period"))
        actual_period = _normalize_period(evidence.get("actual_period"))
        observed_period = _normalize_period(period or data_as_of)
        if not expected_period:
            return ReportFreshness.UNKNOWN.value, "receipt 缺少 expected_period，不能驗證個股期間。"
        if actual_period and actual_period != expected_period:
            return (
                ReportFreshness.UNKNOWN.value,
                "receipt 的 actual_period 與 expected_period 不一致。",
            )
        if not observed_period:
            return ReportFreshness.UNKNOWN.value, "個股來源沒有可驗證的資料期間。"
        if observed_period != expected_period:
            return (
                ReportFreshness.STALE.value,
                f"個股資料期 {observed_period} 未達 receipt expected_period {expected_period}。",
            )
        return ReportFreshness.FRESH.value, "個股資料期與 receipt expected_period 相符。"
    if status in {"stale", "partial"}:
        return ReportFreshness.STALE.value, "receipt 已判定來源過期或覆蓋不完整。"
    return ReportFreshness.UNKNOWN.value, "receipt 狀態無法證明來源 freshness。"


def _normalize_period(value: object) -> str:
    """正規化 daily date／monthly period／quarter period，不混用 available_at。"""

    text = str(value or "").strip().replace("/", "-")
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        with suppress(ValueError):
            return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}").isoformat()
    if len(text) >= 10:
        parsed = _coerce_date(text)
        if parsed is not None:
            return parsed.isoformat()
    if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:].isdigit():
        return text
    compact_quarter = text.upper().replace(" ", "")
    if len(compact_quarter) == 6 and compact_quarter[4] == "Q" and compact_quarter[5] in "1234":
        return f"{compact_quarter[:4]}-{compact_quarter[4:]}"
    if len(compact_quarter) == 7 and compact_quarter[4] == "-" and compact_quarter[5] == "Q":
        return compact_quarter
    return text


def _resolve_freshness_status_path(
    config: object,
    explicit_path: Path | str | None,
) -> Path | None:
    """解析 freshness receipt 的單一受控路徑，不對 output 目錄做 glob。"""

    candidate: object = explicit_path
    if candidate is None:
        candidate = os.environ.get("DATA_FRESHNESS_STATUS_ARTIFACT")
    if candidate is None:
        candidate = getattr(config, "data_freshness_status_path", None)
    if candidate is None:
        output_root = getattr(config, "output_root", None)
        if output_root is None:
            return None
        candidate = Path(output_root) / "scheduled" / "data_freshness" / "latest_status.json"
    text = str(candidate).strip()
    return Path(text).expanduser().resolve() if text else None


def _latest_text(values: Sequence[str] | Any) -> str:
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    return max(cleaned) if cleaned else ""


def _worst_quality(values: Sequence[str] | Any) -> str:
    rank = {
        ReportQuality.OBSERVED.value: 0,
        ReportQuality.ESTIMATED.value: 1,
        ReportQuality.DEGRADED.value: 2,
        ReportQuality.STALE.value: 3,
        ReportQuality.MISSING.value: 4,
    }
    cleaned = [_quality(value) for value in values]
    return max(cleaned, key=lambda value: rank.get(value, 2)) if cleaned else ReportQuality.MISSING.value


def _json_strings(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return (str(value),)
    if isinstance(raw, (list, tuple)):
        return tuple(str(item) for item in raw if str(item).strip())
    return (str(raw),) if str(raw).strip() else ()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _context_map(context: object | None) -> dict[str, str]:
    if context is None:
        return {}
    fields = (
        "stock_code", "stock_name", "decision_date", "data_date", "result_id",
        "identity_status", "source_snapshot_id", "source_snapshot_hash",
        "profile_id", "profile_version", "source_id", "source_kind",
        "source_label", "source_workspace", "source_version",
        "mapping_source_id", "mapping_version", "mapping_observed_date",
        "ml_scope_mode", "position_id", "portfolio_id",
        "daily_snapshot_root", "daily_snapshot_cohort_id",
        "daily_snapshot_condition_keys", "daily_snapshot_combine_mode",
    )
    if isinstance(context, Mapping):
        return {
            field: str(context.get(field, "") or "").strip()
            for field in fields
            if str(context.get(field, "") or "").strip()
        }
    return {
        field: str(getattr(context, field, "") or "").strip()
        for field in fields
        if str(getattr(context, field, "") or "").strip()
    }


def _rank_context_from(context: object | None) -> ResearchRankContextDTO | None:
    """只接受 context 明確攜帶的已核驗排名脈絡。"""

    value = (
        context.get("rank_context")
        if isinstance(context, Mapping)
        else getattr(context, "rank_context", None)
    )
    if isinstance(value, ResearchRankContextDTO):
        return value
    if isinstance(value, Mapping):
        try:
            return ResearchRankContextDTO.from_mapping(value)
        except (TypeError, ValueError):
            return None
    return None


def _read_original_rank_report(
    rank_context: ResearchRankContextDTO | None,
    *,
    db_path: object | None,
    expected_stock_code: str,
    date_mismatch: bool,
    source_context_present: bool,
) -> StockOriginalRankingReportDTO:
    """從 pinned rank artifact 讀取原始 row；失敗時只回報未知。"""

    def context_value(name: str, default: Any = "") -> Any:
        return getattr(rank_context, name, default) if rank_context is not None else default

    mode_label = "Top" if context_value("direction") == "strong" else "Bottom"
    metadata = {
        "rank_kind": context_value("rank_kind", "original_stock_ranking"),
        "period": context_value("period", ""),
        "direction": context_value("direction", ""),
        "direction_label": mode_label,
        "decision_date": context_value("decision_date", ""),
        "comparison_window_dates": tuple(context_value("comparison_window_dates", ()) or ()),
        "comparison_window_rule": context_value("comparison_window_rule", ""),
        "volume_reference_point_count": context_value("volume_reference_point_count", 0),
        "declared_stock_codes": tuple(context_value("declared_stock_codes", ()) or ()),
        "eligible_stock_codes": tuple(context_value("eligible_stock_codes", ()) or ()),
        "missing_rank_stock_codes": tuple(context_value("missing_rank_stock_codes", ()) or ()),
        "research_universe_json": context_value("research_universe_json", ""),
        "research_universe_sha256": context_value("research_universe_sha256", ""),
        "method_name": context_value("method_name", ""),
        "method_version": context_value("method_version", ""),
        "method_contract_sha256": context_value("method_contract_sha256", ""),
        "engine_file_sha256": context_value("engine_file_sha256", ""),
        "engine_parameters_json": context_value("engine_parameters_json", ""),
        "engine_parameters_sha256": context_value("engine_parameters_sha256", ""),
        "source_schema_sha256": context_value("source_schema_sha256", ""),
        "selected_input_fingerprint_sha256": context_value(
            "selected_input_fingerprint_sha256", ""
        ),
        "ranking_root": context_value("ranking_root", ""),
        "snapshot_root": context_value("snapshot_root", ""),
        "rank_manifest_identity_sha256": context_value("rank_snapshot_id", ""),
        "rank_manifest_sha256": context_value("source_hash", ""),
        "parent_snapshot_identity_sha256": context_value("parent_snapshot_id", ""),
        "parent_snapshot_sha256": context_value("parent_snapshot_hash", ""),
        "parent_cohort_id": context_value("parent_cohort_id", ""),
        "filter_state": context_value("filter_state", "all"),
        "sort_key": context_value("sort_key", "rank"),
        "descending": context_value("descending", False),
    }
    reason = ""
    if not source_context_present or rank_context is None:
        reason = "排名來源脈絡缺漏或格式不支援。"
    elif date_mismatch:
        reason = "報告查詢日與排名決策日不一致；已拒絕跨日回填。"
    elif rank_context.selected_stock_code != expected_stock_code:
        reason = "排名來源股票與目前個股不一致。"
    elif not db_path or not str(db_path).strip():
        reason = "未配置可核驗原排名來源所需的資料庫路徑。"
    else:
        try:
            from app_module.original_stock_ranking import (
                read_original_stock_ranking_row_from_context,
            )

            row = read_original_stock_ranking_row_from_context(
                rank_context,
                db_path=Path(str(db_path)),
            )
            if not isinstance(row, Mapping):
                raise TypeError("pinned rank reader did not return a row mapping")
            row_code = str(row.get("stock_code") or "").strip()
            row_rank = row.get("rank")
            score_label = str(row.get("score_label") or "")
            comparison_date = str(row.get("comparison_date") or "").strip()
            latest_date = str(row.get("latest_date") or "").strip()
            if row_code != expected_stock_code:
                raise ValueError("pinned rank row stock mismatch")
            if type(row_rank) is not int or row_rank < 1:
                raise ValueError("pinned rank row rank is invalid")
            if not score_label:
                raise ValueError("pinned rank row has no publisher label")
            if not comparison_date or not latest_date:
                raise ValueError("pinned rank row is missing its actual comparison dates")
            expected_prefix = "Top " if rank_context.direction == "strong" else "Bottom "
            if not score_label.startswith(expected_prefix):
                raise ValueError("pinned rank row native label does not match direction")
            return StockOriginalRankingReportDTO(
                status="available",
                rank=row_rank,
                native_score_label=score_label,
                comparison_date=comparison_date,
                latest_date=latest_date,
                **metadata,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", "") or "").strip()
            message = str(exc).splitlines()[0].strip() or type(exc).__name__
            reason = f"{code}: {message}" if code else message
    return StockOriginalRankingReportDTO(
        status="unknown",
        reason=reason,
        **metadata,
    )


def _error_text(label: str, error: BaseException) -> str:
    message = str(error).splitlines()[0].strip() or type(error).__name__
    return f"{label}區塊讀取失敗：{message}"


def _call_provider(
    provider: Callable[..., object],
    code: str,
    cutoff: date,
    **extras: object,
) -> object | None:
    try:
        parameters = inspect.signature(provider).parameters
    except (TypeError, ValueError):
        return provider(code, cutoff)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    kwargs: dict[str, object] = {}
    if "stock_code" in parameters:
        kwargs["stock_code"] = code
    if "as_of_date" in parameters:
        kwargs["as_of_date"] = cutoff
    for name, value in extras.items():
        if accepts_kwargs or name in parameters:
            kwargs[name] = value
    if "stock_code" in parameters or "as_of_date" in parameters:
        return provider(**kwargs)
    return provider(code, cutoff, **kwargs)


def _object_text(value: object, *names: str) -> str:
    if isinstance(value, Mapping):
        for name in names:
            text = str(value.get(name, "") or "").strip()
            if text:
                return text
    for name in names:
        text = str(getattr(value, name, "") or "").strip()
        if text:
            return text
    return ""


def _object_value(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _aware_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _object_strings(value: object, *names: str) -> tuple[str, ...]:
    raw: object = ()
    if isinstance(value, Mapping):
        for name in names:
            if value.get(name) is not None:
                raw = value.get(name)
                break
    else:
        for name in names:
            candidate = getattr(value, name, None)
            if candidate is not None:
                raw = candidate
                break
    if isinstance(raw, str):
        return _dedupe(tuple(part.strip() for part in raw.replace("；", ";").split(";") if part.strip()))
    if isinstance(raw, (list, tuple, set)):
        return _dedupe(tuple(str(item) for item in raw))
    return ()


def _first_non_empty(*values: str) -> str:
    return next((value for value in values if value.strip()), "")


def _with_advice_agreement(
    advice: StockAdviceSnapshotDTO,
    rule_reasons: tuple[str, ...],
    ml_reasons: tuple[str, ...],
) -> StockAdviceSnapshotDTO:
    if not ml_reasons:
        return advice
    return StockAdviceSnapshotDTO(
        status=advice.status,
        recommendation=advice.recommendation,
        portfolio=advice.portfolio,
        saved_analysis=advice.saved_analysis,
        rule_reasons=rule_reasons,
        ml_reasons=ml_reasons,
        agreement="needs_review",
        limitations=advice.limitations,
    )


def _attention_reasons(
    prices: Sequence[StockPricePointDTO],
    fundamentals: Sequence[StockFundamentalObservationDTO],
    flows: Sequence[StockFlowObservationDTO],
    sections: Sequence[StockReportSectionDTO],
    advice: StockAdviceSnapshotDTO,
    position: StockPositionSnapshotDTO | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not prices:
        reasons.append("缺少最新可用價格")
    if prices and not prices[-1].close_price:
        reasons.append("最新價格 row 沒有收盤價")
    if not fundamentals:
        reasons.append("基本面資料不足")
    if not flows:
        reasons.append("籌碼／分點資料不足")
    if any(section.status in {ReportSectionStatus.STALE.value, ReportSectionStatus.ERROR.value} for section in sections):
        reasons.append("部分來源過期或讀取失敗")
    reasons.extend(advice.rule_reasons[:3])
    if position is not None:
        reasons.extend(position.health_reasons[:3])
    return _dedupe(reasons)


def _key_risks(
    advice: StockAdviceSnapshotDTO,
    events: Sequence[StockEvidenceEventDTO],
    position: StockPositionSnapshotDTO | None,
    limitations: Sequence[str],
    *,
    as_of_date: str = "",
) -> tuple[str, ...]:
    """Current risk projection; historical events and missingness stay separate."""
    saved_date = (
        advice.saved_analysis.decision_date if advice.saved_analysis
        else advice.recommendation.decision_date if advice.recommendation is not None
        else ""
    )
    risks = list(advice.recommendation.risk_reasons) if (
        advice.recommendation is not None
        and (not as_of_date or not saved_date or saved_date == as_of_date)
    ) else []
    if position is not None and position.is_holding:
        risks.extend(position.health_reasons)
        risks.extend(position.exit_reasons)
    # Events retain their original date/reasons in the history DTO, never current risk.
    return _dedupe(tuple(reason for reason in risks if not is_research_data_limitation(reason)))[:8]


def _technical_rule_observations(
    technical: StockTechnicalSnapshotDTO | None,
    shared_daily_features: Mapping[str, Any],
) -> tuple[str, ...]:
    """只解釋截止當下已讀到的指標，不產生分數、機率或交易適合度。"""
    values = (
        {metric.key: metric.value for metric in technical.indicators if metric.value is not None}
        if technical is not None
        else {}
    )
    facts: list[str] = []
    if technical is not None:
        facts.extend(
            f"技術觀察：{key}={values[key]}（資料日 {technical.data_date}；來源 {technical.source_id}）"
            for key in ("RSI", "MACD", "ADX")
            if key in values
        )
    raw_conditions = shared_daily_features.get("conditions", {})
    conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
    projection_error = str(shared_daily_features.get("projection_error", "") or "")
    for key, condition_name in (
        ("MA20", "close_above_ma20"),
        ("MA60", "close_above_ma60"),
    ):
        raw_condition = conditions.get(condition_name)
        condition = raw_condition if isinstance(raw_condition, Mapping) else {}
        state = str(condition.get("state", "unknown") or "unknown").lower()
        data_date = str(condition.get("data_date", "") or "")
        if state not in {"match", "no_match"}:
            reason = str(condition.get("reason", "") or "shared_daily_feature_condition_missing")
            detail = str(condition.get("detail", "") or projection_error)
            explanation = f"原因 {reason}"
            if detail:
                explanation += f"：{detail}"
            facts.append(
                f"技術觀察：收盤與 {key} 未能判定（資料日 {data_date or '未知'}；{explanation}）。"
            )
            continue

        relation = str(condition.get("relation", "unknown") or "unknown").lower()
        relation_label = {"above": "高於", "below": "低於", "equal": "等於"}.get(relation)
        close_value = condition.get("close_value")
        reference_value = condition.get("reference_value")
        if relation_label is None or close_value is None or reference_value is None:
            reason = str(condition.get("reason", "") or "shared_daily_feature_condition_incomplete")
            facts.append(
                f"技術觀察：收盤與 {key} 未能判定（資料日 {data_date or '未知'}；原因 {reason}）。"
            )
            continue
        facts.append(
            f"技術觀察：收盤 {close_value} {relation_label} {key} {reference_value}"
            f"（資料日 {data_date or '未知'}；只解釋行情，不是推薦或勝率）"
        )
    return tuple(facts)
