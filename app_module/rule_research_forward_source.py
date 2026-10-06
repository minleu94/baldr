"""UX21：current-observed SQLite／年度計畫日曆唯讀 adapter，沒有 PIT 資格。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from app_module.daily_market_feature_snapshot import _feature_fingerprint
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource, _source_pin
from app_module.rule_research_forward_outcome import Calendar, CostPolicy, PricePoint, build_parent_rule_research_forward_outcome
from app_module.rule_research_observation_acceptance import _parent
from app_module.rule_research_parent_capture import BoundedRuleResearchParentWriter, _snapshot_repository
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, _digest, _json, _require
from data_module.official_trading_calendar_cache import load_verified_twse_calendar_cache
from app_module.rule_research_benchmark_adapter import load_explicit_market_benchmark
from app_module.rule_research_benchmark_settings import benchmark_request as make_benchmark_request, result_payload, read_benchmark_settings

ADAPTER_VERSION = "rule-research-current-observed-forward.v1"
BENCHMARK_ADAPTER_VERSION = "rule-research-current-observed-forward.v2"


def build_current_observed_forward(parent_receipt: str | Path, source_db: str | Path,
        calendar_cache: str | Path, *, as_of_date: str, cost_policy: CostPolicy | None = None,
        benchmark_settings: dict[str, Any] | None = None,
        cancel_callback: Callable[[], bool] | None = None) -> dict[str, Any]:
    """只讀指定來源；年度計畫 session 僅供研究，臨時休市與 available-at 保留未知。"""
    cancel = cancel_callback or (lambda: False)
    def check() -> None:
        _require(not cancel(), "forward_cancelled")
    check()
    if benchmark_settings is not None:
        benchmark_settings = read_benchmark_settings(benchmark_settings)
    now = datetime.now(timezone.utc)
    as_of = date.fromisoformat(as_of_date)
    _require(as_of.isoformat() == as_of_date and as_of <= now.date(), "forward_as_of_invalid")
    parent, ready, parent_pin = _parent(parent_receipt)
    decision = date.fromisoformat(ready["decision_date"])
    path = Path(calendar_cache).absolute()
    _require(path.is_file(), "forward_calendar_exact_file_required")
    verified = load_verified_twse_calendar_cache(path, calendar_year=decision.year, observed_at=now)
    # loader 已核對完整 normalized_days 與 raw capture；complete 是年度計畫範圍完整，非實際交易 custody。
    year_start, year_end = date(decision.year, 1, 1), date(decision.year, 12, 31)
    from datetime import timedelta
    days = tuple((year_start + timedelta(days=i)).isoformat()
        for i in range((year_end-year_start).days+1)
        if (year_start + timedelta(days=i)).weekday() < 5
        and verified.schedule.get(year_start + timedelta(days=i), True))
    # validated_at 是每次讀取 clock，非 immutable source revision；保存 envelope 另有 observed_at。
    calendar_evidence = {k: v for k, v in verified.evidence.items() if k != "validated_at"}
    calendar_identity = _digest(_json(calendar_evidence).encode("utf-8"))
    calendar = Calendar(days, True, True, year_start.isoformat(), year_end.isoformat(),
                        "twse-annual-plan:" + calendar_identity, None)
    after = [d for d in days if d > decision.isoformat()]
    endpoints = sorted({decision.isoformat(), *(after[h-1] for h in (5, 10, 20) if len(after) >= h)})
    snapshots: dict[str, dict[str, Any]] = {}
    children = []
    writer = BoundedRuleResearchCaptureWriter(Path(parent["capture_root"]) / "samples" / parent["plan_sha256"])
    for batch in parent["batches"]:
        check()
        if batch["status"] == "captured":
            children.append(writer.read(batch["capture_identity_sha256"]))
            saved = _snapshot_repository(Path(parent["snapshot_root"]), parent, batch).load_manifest(
                batch["manifest_sha256"], batch["cohort_id"], decision)
            snapshots.update(saved.stock_snapshots)
    points: list[PricePoint] = []
    issues: list[dict[str, str]] = []
    row_pins: list[dict[str, Any]] = []
    source_path = Path(source_db).absolute()
    with SQLiteDailyMarketSnapshotSource(source_path, as_of, cancel_callback=cancel) as source:
        pin = _source_pin(source.db_path)
        target_pin = _digest(_json({"database": str(source.db_path.resolve()),
            "schema_identity": source.schema_identity, "database_revision_pin": pin}).encode("utf-8"))
        benchmark_result = None
        target_basis_status = "unknown"
        request = None
        if benchmark_settings is not None:
            request, target_basis_status = make_benchmark_request(benchmark_settings,
                decision_date=decision.isoformat(), endpoint_dates=endpoints,
                as_of_date=as_of_date, target_source_pin=target_pin)
            benchmark_result = load_explicit_market_benchmark(request, cancel_callback=cancel, observed_at=now)
            check()
        for code in parent["universe"]["value"]["included_stock_codes"]:
            check()
            rows, _, scope, _ = source.load(code)
            by_date: dict[str, list[Any]] = {}
            for observed_row in rows:
                day = str(observed_row.data_date).replace("/", "-")
                by_date.setdefault(day, []).append(observed_row)
            close = snapshots.get(code, {}).get("features", {}).get("close", {})
            for day in endpoints:
                if day > as_of_date:
                    continue
                found = by_date.get(day, [])
                row = found[0] if len(found) == 1 else None
                price = row.close_price if row is not None else None
                reason = "exact_endpoint_missing" if not found else "duplicate_endpoint" if len(found) > 1 else ""
                if price is not None and (not price.is_finite() or price <= 0):
                    price, reason = None, "invalid_endpoint_price"
                if row is not None and day == decision.isoformat():
                    fingerprint = _feature_fingerprint("close", row.source_id, day,
                        row.source_snapshot_hash, row, price)
                    if close.get("state") != "observed" or close.get("data_date") != day or close.get("source_fingerprint_sha256") != fingerprint:
                        price, reason = None, "original_decision_price_revision_or_missing"
                if reason:
                    issues.append({"stock_code": code, "trade_date": day, "reason": reason})
                row_pins.append({"stock_code": code, "trade_date": day,
                    "source_row_sha256": row.source_snapshot_hash if row is not None else None,
                    "original_decision_feature_sha256": close.get("source_fingerprint_sha256") if day == decision.isoformat() else None})
                points.append(PricePoint(code, day, "available" if price is not None else "missing",
                    price, scope + ":daily_prices", "TWD", "share", "unadjusted_close", "unknown", None))
        source.validate_source_stable()
        if benchmark_result is not None and benchmark_result.status == "qualified_research":
            _require(request is not None and target_basis_status == "caller_declared_research_only",
                     "forward_benchmark_target_basis_unverified")
            assert request is not None and request.target_corporate_action_basis is not None
            points = [replace(point, corporate_action_basis=request.target_corporate_action_basis)
                      for point in points]  # 只用明示、source-pin綁定的研究宣告，不授自然權威。
            points.extend(benchmark_result.prices)
        projection = build_parent_rule_research_forward_outcome(
            BoundedRuleResearchParentWriter(Path(parent_receipt).absolute().parent.parent).read(parent_pin["parent_identity_sha256"]),
            children, decision_date=decision.isoformat(), as_of_date=as_of_date,
            calendar=calendar, prices=points,
            benchmark=None if benchmark_result is None else benchmark_result.benchmark,
            cost_policy=cost_policy).to_dict()
        source_contract = {"adapter_version": ADAPTER_VERSION, "database": str(source.db_path),
            "schema_identity_sha256": source.schema_identity, "database_revision_pin": pin,
            "calendar_cache": str(path.resolve()), "calendar_evidence": calendar_evidence,
            "calendar_scope": "planned_annual_closures_only", "temporary_closure_status": "unknown",
            "price_scope": "exact_endpoints_within_last_120_observed_rows",
            "price_basis": "unadjusted_close", "corporate_action_basis": "unknown",
            "source_availability": "unknown", "source_mode": "current_observed",
            "benchmark_status": "unconfigured_unknown", "row_pins": row_pins, "issues": issues}
        if benchmark_settings is not None:
            _require(benchmark_result is not None, "forward_benchmark_result_missing")
            assert benchmark_result is not None
            source_contract.update(adapter_version=BENCHMARK_ADAPTER_VERSION,
                benchmark_request=benchmark_settings, benchmark_result=result_payload(benchmark_result),
                benchmark_status=benchmark_result.status, benchmark_endpoint_dates=endpoints,
                target_source_pin_sha256=target_pin, target_basis_status=target_basis_status)
            # 再讀同請求，拒絕benchmark在target讀取期間修訂；不自動接受觀測pin。
            _require(request is not None and result_payload(load_explicit_market_benchmark(
                request, cancel_callback=cancel, observed_at=now)) == source_contract["benchmark_result"],
                "forward_benchmark_changed_during_read")
        source.validate_source_stable()
    check()
    _require(_parent(parent_receipt)[2] == parent_pin, "forward_parent_changed")
    # 官方 cache loader 再讀原檔，禁止過程中替換成不同版本。
    _require(dict(load_verified_twse_calendar_cache(path, calendar_year=decision.year,
        observed_at=now).evidence) == dict(verified.evidence), "forward_calendar_changed")
    return {"projection": projection, "parent_pin": parent_pin, "source_contract": source_contract}
