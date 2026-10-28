from dataclasses import replace
from datetime import date
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module import broker_flow_dashboard_query_service as broker_flow_service_module
from app_module.broker_flow_dashboard_dtos import (
    BrokerFlowDashboardQuery,
    BrokerFlowDashboardSnapshot,
)
from app_module.broker_flow_dashboard_query_service import (
    BrokerFlowDashboardQueryService,
)
from app_module.broker_flow_service import BrokerFlowService
from app_module.broker_flow_sqlite_read_repository import BrokerFlowReadSnapshot
from app_module.smart_money_semantic_service import (
    SQLiteSmartMoneyBatchSemanticAdapter,
    SmartMoneySemanticService,
)
from decision_module.flow_contracts import (
    BrokerFlowEvent,
    FlowSignalDTO,
    SmartMoneySummaryDTO,
    StockFlowAggregation,
)
from scripts.qa_broker_flow_dashboard_latency import (
    benchmark_operation,
    evaluate_latency_gate,
    inspect_broker_flow_sqlite,
    summarize_latency_samples,
)


@pytest.mark.parametrize(
    ("period", "expected_days"),
    (("day", 1), ("week", 5), ("month", 20)),
)
def test_dashboard_query_maps_period_to_broker_trading_days(period, expected_days):
    query = BrokerFlowDashboardQuery(
        period=period,
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )

    assert query.period_trading_days == expected_days


def test_dashboard_query_selects_recent_dates_at_or_before_explicit_as_of():
    query = BrokerFlowDashboardQuery(
        period="week",
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )
    available_dates = (
        date(2026, 6, 26),
        date(2026, 6, 27),
        date(2026, 6, 30),
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 6),
    )

    assert query.select_trading_dates(available_dates) == (
        date(2026, 6, 27),
        date(2026, 6, 30),
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    )


def test_dashboard_query_rejects_implicit_or_invalid_contract_values():
    with pytest.raises(ValueError, match="requested_as_of_date"):
        BrokerFlowDashboardQuery(
            period="week",
            scope="top_bottom",
            requested_as_of_date=None,
            limit_per_side=50,
        )
    with pytest.raises(ValueError, match="period"):
        BrokerFlowDashboardQuery(
            period="calendar_week",
            scope="top_bottom",
            requested_as_of_date=date(2026, 7, 5),
            limit_per_side=50,
        )
    with pytest.raises(ValueError, match="limit_per_side"):
        BrokerFlowDashboardQuery(
            period="week",
            scope="top_bottom",
            requested_as_of_date=date(2026, 7, 5),
            limit_per_side=0,
        )


def test_latency_summary_separates_cold_sample_and_warm_nearest_rank_p95():
    summary = summarize_latency_samples([900.0, 10.0, 20.0, 30.0, 40.0, 50.0])

    assert summary == {
        "sample_count": 6,
        "cold_ms": 900.0,
        "warm_sample_count": 5,
        "warm_p95_ms": 50.0,
        "warm_min_ms": 10.0,
        "warm_max_ms": 50.0,
    }


def test_acceptance_benchmark_keeps_warmup_and_twenty_raw_samples():
    calls = []

    result = benchmark_operation(
        "fixture",
        lambda: calls.append(len(calls)) or {"query_count": 2, "row_count": 7},
        runs=20,
    )

    assert len(calls) == 21
    assert len(result["raw_samples_ms"]) == 20
    assert result["warmup_ms"] >= 0
    assert result["last_result"] == {"query_count": 2, "row_count": 7}


def test_latency_gate_reports_failure_instead_of_masking_regression():
    result = evaluate_latency_gate(
        {"warm_p95_ms": 2000.0, "cold_ms": 4999.0},
        warm_limit_ms=2000.0,
        cold_limit_ms=5000.0,
    )

    assert result == {
        "status": "fail",
        "warm_limit_ms": 2000.0,
        "warm_p95_ms": 2000.0,
        "cold_limit_ms": 5000.0,
        "cold_ms": 4999.0,
    }


def test_latency_cli_emits_cjk_and_writes_output_under_cp1252_console(tmp_path):
    output_path = tmp_path / "latency.json"
    code = (
        "from pathlib import Path; "
        "from scripts.qa_broker_flow_dashboard_latency import _emit_report; "
        f"_emit_report('主力流向', Path({str(output_path)!r}))"
    )
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout.decode("utf-8").strip() == "主力流向"
    assert output_path.read_text(encoding="utf-8") == "主力流向\n"


def test_sqlite_shape_probe_is_read_only_and_missing_path_is_not_created(tmp_path):
    missing = tmp_path / "missing.db"

    result = inspect_broker_flow_sqlite(missing)

    assert result["quality"] == "missing"
    assert result["row_count"] == 0
    assert not missing.exists()


def _dashboard_event(code, net_qty, branch="branch_a"):
    return BrokerFlowEvent(
        date="2026-07-03",
        branch_system_key=branch,
        branch_display_name=branch,
        stock_code=code,
        stock_name=f"股票{code}",
        buy_qty=max(net_qty, 0),
        sell_qty=abs(min(net_qty, 0)),
        net_qty=net_qty,
        lots_quality="observed",
        lots_observed=True,
    )


class _DashboardRepository:
    def __init__(self, source):
        self.source = source
        self.calls = []

    def load_dashboard_source(self, query):
        self.calls.append(query)
        return self.source


class _BatchSemanticPort:
    def __init__(self):
        self.calls = []

    def build_batch_semantics(self, stock_codes, decision_date):
        self.calls.append((stock_codes, decision_date))
        return {}


def test_dashboard_service_scans_market_once_then_batches_only_selected_codes():
    events = tuple(
        [
            _dashboard_event(f"P{index:03d}", 10_000 - index, f"buy_{index % 3}")
            for index in range(60)
        ]
        + [
            _dashboard_event(f"N{index:03d}", -10_000 - index, f"sell_{index % 3}")
            for index in range(60)
        ]
    )
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=events,
        tracked_branches=(("branch_a", "branch_a"),),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=2,
        materialized_row_count=len(events),
    )
    repository = _DashboardRepository(source)
    semantic_port = _BatchSemanticPort()
    service = BrokerFlowDashboardQueryService(
        repository,
        semantic_port=semantic_port,
    )
    query = BrokerFlowDashboardQuery(
        period="week",
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )

    snapshot = service.load_dashboard_snapshot(query)

    assert repository.calls == [query]
    assert len(snapshot.top_signals) == 50
    assert len(snapshot.bottom_signals) == 50
    assert snapshot.summary.bullish_stock_count == 60
    assert snapshot.summary.bearish_stock_count == 60
    assert snapshot.as_of_date == date(2026, 7, 3)
    assert snapshot.source_fingerprint == "fixture-v1"
    assert snapshot.query_counts == {"repository": 2, "semantic_batch": 1}
    assert len(semantic_port.calls) == 1
    selected_codes, semantic_date = semantic_port.calls[0]
    assert len(selected_codes) == 100
    assert len(set(selected_codes)) == 100
    assert semantic_date == date(2026, 7, 3)


def _semantic_batch_event(
    day: str,
    code: str,
    name: str,
    net_qty: int | None,
    branch: str,
    *, lots_quality: str = "observed",
) -> BrokerFlowEvent:
    return BrokerFlowEvent(
        date=day,
        branch_system_key=branch,
        branch_display_name=branch,
        stock_code=code,
        stock_name=name,
        net_qty=net_qty,
        lots_available=lots_quality == "observed",
        lots_observed=lots_quality == "observed",
        lots_quality=lots_quality,
    )


class _SemanticBatchRepository:
    def __init__(self, source):
        self.source = source

    def load_stock_semantic_batch(self, stock_codes, decision_date, **kwargs):
        return self.source


class _SemanticBatchPrices:
    def load_recent_prices_batch(self, stock_codes, decision_date, limit):
        return {}


class _SemanticEvents:
    def __init__(self, events):
        self.events = list(events)

    def get_events(self, force_reload=False):
        return self.events


def _semantic_batch_events():
    return (
        _semantic_batch_event("2026-07-03", "2317", "鴻海", 12, "b1"),
        _semantic_batch_event("2026-07-03", "2330", "", 10, "b1"),
        _semantic_batch_event("2026-07-03", "2330", "當日第一個名稱", -3, "b2"),
        _semantic_batch_event("2026-07-03", "2330", "當日第二個名稱", 4, "b3"),
        _semantic_batch_event("2026-07-02", "2317", "鴻海", -5, "b1"),
        _semantic_batch_event(
            "2026-07-02", "2330", "較舊名稱", None, "b4",
            lots_quality="unavailable",
        ),
        _semantic_batch_event("2026-07-01", "2330", "台積電", 6, "b1"),
    )


def _semantic_source(events):
    return BrokerFlowReadSnapshot(
        selected_trading_dates=(
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ),
        events=tuple(events),
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="semantic-fixture-v1",
        query_count=2,
        materialized_row_count=len(events),
    )


def _legacy_semantic_batch(events, codes, decision_date):
    return {
        code: SmartMoneySemanticService(_SemanticEvents(events)).build_stock_semantics(
            code, decision_date
        )
        for code in codes
    }


def test_semantic_batch_reuses_verified_dates_and_preserves_same_day_name_order(
    monkeypatch,
):
    events = _semantic_batch_events()
    codes = ("2330", "2317")
    decision_date = date(2026, 7, 3)
    expected = _legacy_semantic_batch(events, codes, decision_date)
    adapter = SQLiteSmartMoneyBatchSemanticAdapter(
        _SemanticBatchRepository(_semantic_source(events)), _SemanticBatchPrices()
    )

    def unexpected_legacy_selection(*args, **kwargs):
        pytest.fail("verified repository snapshot should bypass per-stock re-selection")

    monkeypatch.setattr(
        SmartMoneySemanticService, "_events_for_stock", unexpected_legacy_selection
    )
    actual = adapter.build_batch_semantics(codes, decision_date)

    assert actual == expected
    assert actual["2330"].stock_name == "當日第一個名稱"


@pytest.mark.parametrize("mutation", ("out_of_order", "compact_dates"))
def test_semantic_batch_unverified_source_falls_back_to_legacy_selection(
    monkeypatch, mutation
):
    events = _semantic_batch_events()
    if mutation == "out_of_order":
        events = tuple(reversed(events))
    else:
        events = tuple(
            replace(event, date=event.date.replace("-", "")) for event in events
        )
    codes = ("2330", "2317")
    decision_date = date(2026, 7, 3)
    expected = _legacy_semantic_batch(events, codes, decision_date)
    adapter = SQLiteSmartMoneyBatchSemanticAdapter(
        _SemanticBatchRepository(_semantic_source(events)), _SemanticBatchPrices()
    )
    original = SmartMoneySemanticService._events_for_stock
    legacy_calls = []

    def tracked_legacy_selection(self, stock_code, *args, **kwargs):
        legacy_calls.append(stock_code)
        return original(self, stock_code, *args, **kwargs)

    monkeypatch.setattr(
        SmartMoneySemanticService, "_events_for_stock", tracked_legacy_selection
    )
    actual = adapter.build_batch_semantics(codes, decision_date)

    assert actual == expected
    assert legacy_calls == list(codes)


def _stock_detail_events():
    return (
        BrokerFlowEvent(
            date="2026-07-02",
            branch_system_key="branch_a",
            branch_display_name="Branch A",
            stock_code="2330",
            stock_name="股票2330",
            buy_qty=10,
            sell_qty=2,
            net_qty=8,
            lots_quality="observed",
        ),
        BrokerFlowEvent(
            date="2026-07-03",
            branch_system_key="branch_a",
            branch_display_name="Branch A",
            stock_code="2330",
            stock_name="股票2330",
            buy_qty=4,
            sell_qty=1,
            net_qty=3,
            lots_quality="observed",
        ),
        BrokerFlowEvent(
            date="2026-07-03",
            branch_system_key="branch_b",
            branch_display_name="Branch B",
            stock_code="2330",
            stock_name="股票2330",
            buy_qty=0,
            sell_qty=6,
            net_qty=-6,
            lots_quality="observed",
        ),
    )


def _detail_snapshot(events, *, quality="observed", warnings=(), fingerprint="fixture-v1"):
    aggregation = StockFlowAggregation(
        stock_code="2330",
        stock_name="股票2330",
        total_buy_qty=14,
        total_sell_qty=9,
        total_net_qty=5,
        events=list(events),
    )
    signal = FlowSignalDTO(
        stock_code="2330",
        stock_name="股票2330",
        aggregation=aggregation,
    )
    return BrokerFlowDashboardSnapshot(
        as_of_date=date(2026, 7, 3),
        period="week",
        top_signals=(signal,),
        bottom_signals=(),
        summary=SmartMoneySummaryDTO(),
        semantics_by_code={},
        tracked_branches=(),
        quality=quality,
        warnings=warnings,
        source_fingerprint=fingerprint,
        selected_trading_dates=(date(2026, 7, 2), date(2026, 7, 3)),
    )


class _StockDetailRepository(_DashboardRepository):
    def load_stock_source(self, stock_code, query):
        self.calls.append((stock_code, query))
        return self.source


def test_stock_detail_reuses_clean_dashboard_events_with_exact_query_parity():
    events = _stock_detail_events()
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 2), date(2026, 7, 3)),
        events=events,
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=3,
        materialized_row_count=len(events),
    )
    repository = _StockDetailRepository(source)
    query_service = BrokerFlowDashboardQueryService(repository)
    query = BrokerFlowDashboardQuery(
        period="week",
        scope="all",
        requested_as_of_date=date(2026, 7, 3),
    )
    dashboard_snapshot = _detail_snapshot(events)

    queried = query_service.load_stock_branch_detail("2330", query)
    reads_after_query = len(repository.calls)
    reused = query_service.load_stock_branch_detail_from_dashboard_snapshot(
        "2330", query, dashboard_snapshot
    )

    assert reads_after_query == 1
    assert len(repository.calls) == reads_after_query
    assert reused is not None
    assert reused.rows == queried.rows
    assert reused.as_of_date == queried.as_of_date
    assert reused.period == queried.period
    assert reused.stock_code == queried.stock_code
    assert reused.quality == queried.quality
    assert reused.warnings == queried.warnings
    assert reused.source_fingerprint == queried.source_fingerprint
    assert reused.query_count == 0


@pytest.mark.parametrize(
    "snapshot_mutation",
    (
        "degraded",
        "warning",
        "period_mismatch",
        "date_mismatch",
        "missing_fingerprint",
        "unlisted_stock",
    ),
)
def test_stock_detail_snapshot_reuse_rejects_uncertain_or_unmatched_context(
    snapshot_mutation,
):
    events = _stock_detail_events()
    snapshot = _detail_snapshot(events)
    stock_code = "2330"
    query = BrokerFlowDashboardQuery(
        period="week",
        scope="all",
        requested_as_of_date=date(2026, 7, 3),
    )
    if snapshot_mutation == "degraded":
        snapshot = _detail_snapshot(events, quality="degraded")
    elif snapshot_mutation == "warning":
        snapshot = _detail_snapshot(events, warnings=("semantic_warning",))
    elif snapshot_mutation == "period_mismatch":
        snapshot = BrokerFlowDashboardSnapshot(
            **{**snapshot.__dict__, "period": "month"}
        )
    elif snapshot_mutation == "date_mismatch":
        query = BrokerFlowDashboardQuery(
            period="week",
            scope="all",
            requested_as_of_date=date(2026, 7, 4),
        )
    elif snapshot_mutation == "missing_fingerprint":
        snapshot = _detail_snapshot(events, fingerprint="")
    elif snapshot_mutation == "unlisted_stock":
        stock_code = "9999"

    service = BrokerFlowDashboardQueryService(_StockDetailRepository(None))

    assert (
        service.load_stock_branch_detail_from_dashboard_snapshot(
            stock_code, query, snapshot
        )
        is None
    )


def test_broker_flow_service_falls_back_to_read_for_warning_snapshot():
    events = _stock_detail_events()
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 2), date(2026, 7, 3)),
        events=events,
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=3,
        materialized_row_count=len(events),
    )
    repository = _StockDetailRepository(source)
    query_service = BrokerFlowDashboardQueryService(repository)
    service = BrokerFlowService(None, dashboard_query_service=query_service)

    detail = service.load_stock_branch_detail(
        "2330",
        "week",
        date(2026, 7, 3),
        dashboard_snapshot=_detail_snapshot(events, warnings=("semantic_warning",)),
    )

    assert len(repository.calls) == 1
    assert detail.query_count == 3
    assert [row.branch_display_name for row in detail.rows] == ["Branch A", "Branch B"]


def test_market_aggregation_deduplicates_each_side_in_first_seen_order():
    events = (
        BrokerFlowEvent(
            date="2026-07-01",
            branch_system_key="branch-a",
            branch_display_name="分點甲",
            stock_code="2330",
            stock_name="台積電",
            net_qty=100,
        ),
        BrokerFlowEvent(
            date="2026-07-01",
            branch_system_key="branch-b",
            branch_display_name="分點乙",
            stock_code="2330",
            stock_name="台積電",
            net_qty=-100,
        ),
        BrokerFlowEvent(
            date="2026-07-02",
            branch_system_key="branch-a",
            branch_display_name="分點甲",
            stock_code="2330",
            stock_name="台積電",
            net_qty=200,
        ),
        BrokerFlowEvent(
            date="2026-07-02",
            branch_system_key="branch-a",
            branch_display_name="分點甲",
            stock_code="2330",
            stock_name="台積電",
            net_qty=-50,
        ),
        BrokerFlowEvent(
            date="2026-07-03",
            branch_system_key="branch-c",
            branch_display_name="分點丙",
            stock_code="2330",
            stock_name="台積電",
            net_qty=75,
        ),
        BrokerFlowEvent(
            date="2026-07-03",
            branch_system_key="branch-b",
            branch_display_name="分點乙",
            stock_code="2330",
            stock_name="台積電",
            net_qty=-25,
        ),
    )

    aggregation = BrokerFlowDashboardQueryService._aggregate_market(events)["2330"]

    assert aggregation.buying_branches == ["分點甲", "分點丙"]
    assert aggregation.selling_branches == ["分點乙", "分點甲"]
    assert aggregation.events == list(events)
    assert aggregation.total_net_qty == 200


def test_market_aggregation_constructs_only_one_result_per_stock(monkeypatch):
    constructed_stock_codes = []
    original_aggregation_type = StockFlowAggregation

    def count_construction(**kwargs):
        constructed_stock_codes.append(kwargs["stock_code"])
        return original_aggregation_type(**kwargs)

    monkeypatch.setattr(
        broker_flow_service_module,
        "StockFlowAggregation",
        count_construction,
    )
    events = (
        BrokerFlowEvent(
            date="2026-07-01",
            branch_system_key="branch-a",
            branch_display_name="Branch A",
            stock_code="2330",
            stock_name="Stock A",
            net_qty=100,
        ),
        BrokerFlowEvent(
            date="2026-07-01",
            branch_system_key="branch-b",
            branch_display_name="Branch B",
            stock_code="2317",
            stock_name="Stock B",
            net_qty=-50,
        ),
        BrokerFlowEvent(
            date="2026-07-02",
            branch_system_key="branch-c",
            branch_display_name="Branch C",
            stock_code="2330",
            stock_name="Stock A",
            net_qty=75,
        ),
    )

    aggregations = BrokerFlowDashboardQueryService._aggregate_market(events)

    assert constructed_stock_codes == ["2330", "2317"]
    assert aggregations["2330"].events == [events[0], events[2]]
    assert aggregations["2330"].total_net_qty == 175
    assert aggregations["2317"].events == [events[1]]


def test_market_summary_without_directional_signals_remains_unknown():
    summary = BrokerFlowDashboardQueryService._build_market_summary([])

    assert summary.market_regime == "Unknown"
    assert summary.market_heat_score == 0.0
    assert summary.bullish_stock_count == 0
    assert summary.bearish_stock_count == 0


def test_market_summary_calls_balanced_observations_neutral():
    signals = [
        SimpleNamespace(
            aggregation=SimpleNamespace(total_net_qty=500),
            smart_money_score=20,
        ),
        SimpleNamespace(
            aggregation=SimpleNamespace(total_net_qty=-400),
            smart_money_score=20,
        ),
    ]

    summary = BrokerFlowDashboardQueryService._build_market_summary(signals)

    assert summary.market_regime == "Neutral"
    assert summary.market_heat_score == 50.0
    assert summary.bullish_stock_count == 1
    assert summary.bearish_stock_count == 1


@pytest.mark.parametrize(
    ("scope", "expected_top", "expected_bottom", "expected_net_qty_reads"),
    (
        (
            "top50",
            ("P2",),
            (),
            {"P1": 1, "P2": 1, "N1": 1, "N2": 1},
        ),
        (
            "bottom50",
            (),
            ("N2",),
            {"P1": 1, "P2": 1, "N1": 2, "N2": 2},
        ),
    ),
)
def test_single_side_scope_skips_sorting_the_discarded_side(
    scope,
    expected_top,
    expected_bottom,
    expected_net_qty_reads,
):
    class TrackingAggregation:
        def __init__(self, net_qty):
            self._net_qty = net_qty
            self.total_net_qty_reads = 0

        @property
        def total_net_qty(self):
            self.total_net_qty_reads += 1
            return self._net_qty

    class Signal:
        def __init__(self, stock_code, net_qty, smart_money_score):
            self.stock_code = stock_code
            self.aggregation = TrackingAggregation(net_qty)
            self.smart_money_score = smart_money_score

    signals = [
        Signal("P1", 500, 60),
        Signal("P2", 700, 90),
        Signal("N1", -300, 80),
        Signal("N2", -700, 90),
    ]
    query = BrokerFlowDashboardQuery(
        period="week",
        scope=scope,
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=1,
    )

    top, bottom = BrokerFlowDashboardQueryService._select_signals(signals, query)

    assert tuple(signal.stock_code for signal in top) == expected_top
    assert tuple(signal.stock_code for signal in bottom) == expected_bottom
    assert {
        signal.stock_code: signal.aggregation.total_net_qty_reads
        for signal in signals
    } == expected_net_qty_reads


def test_dashboard_service_returns_typed_missing_without_semantic_query():
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(),
        events=(),
        tracked_branches=(),
        quality="missing",
        warnings=("broker_flows_table_missing",),
        source_fingerprint="",
        query_count=1,
        materialized_row_count=0,
    )
    semantic_port = _BatchSemanticPort()
    query = BrokerFlowDashboardQuery(
        period="week",
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )

    snapshot = BrokerFlowDashboardQueryService(
        _DashboardRepository(source), semantic_port=semantic_port
    ).load_dashboard_snapshot(query)

    assert snapshot.quality == "missing"
    assert snapshot.top_signals == ()
    assert snapshot.bottom_signals == ()
    assert snapshot.warnings == ("broker_flows_table_missing",)
    assert semantic_port.calls == []


def test_dashboard_cache_reuses_exact_query_and_invalidates_on_source_change():
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=(_dashboard_event("2330", 1000),),
        tracked_branches=(), quality="observed", warnings=(),
        source_fingerprint="fixture-v1", query_count=2, materialized_row_count=1,
    )

    class VersionedRepository(_DashboardRepository):
        version = "v1"

        def source_cache_key(self):
            return self.version

    repository = VersionedRepository(source)
    semantic_port = _BatchSemanticPort()
    service = BrokerFlowDashboardQueryService(repository, semantic_port=semantic_port)
    query = BrokerFlowDashboardQuery(
        period="week", scope="top_bottom_50",
        requested_as_of_date=date(2026, 7, 5), limit_per_side=50,
    )

    first = service.load_dashboard_snapshot(query)
    second = service.load_dashboard_snapshot(query)
    repository.version = "v2"
    third = service.load_dashboard_snapshot(query)

    assert first is second
    assert third is not second
    assert repository.calls == [query, query]
    assert len(semantic_port.calls) == 2


def test_dashboard_cache_discards_outputs_from_previous_source_versions():
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=(_dashboard_event("2330", 1000),),
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=2,
        materialized_row_count=1,
    )

    class VersionedRepository(_DashboardRepository):
        version = "v1"

        def source_cache_key(self):
            return self.version

        def dashboard_source_cache_key(self, query):
            return (self.version, query.requested_as_of_date, query.period)

    repository = VersionedRepository(source)
    service = BrokerFlowDashboardQueryService(repository)
    queries = [
        BrokerFlowDashboardQuery(
            period="week",
            scope=scope,
            requested_as_of_date=date(2026, 7, 5),
            limit_per_side=50,
        )
        for scope in ("top50", "bottom50", "all")
    ]

    for query in queries:
        service.load_dashboard_snapshot(query)

    assert len(service._dashboard_cache) == 3
    assert {key[0] for key in service._dashboard_cache} == {"v1"}
    assert repository.calls == [queries[0]]

    repository.version = "v2"
    service.load_dashboard_snapshot(queries[0])
    service.load_dashboard_snapshot(queries[1])

    assert len(service._dashboard_cache) == 2
    assert {key[0] for key in service._dashboard_cache} == {"v2"}
    assert repository.calls == [queries[0], queries[0]]


def test_dashboard_source_cache_reuses_scope_independent_source_and_isolates_events():
    events = (_dashboard_event("2330", 1000), _dashboard_event("2317", -400))
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=events,
        tracked_branches=(("branch_a", "branch_a"),),
        quality="degraded",
        warnings=("source_warning",),
        source_fingerprint="fixture-v1",
        query_count=2,
        materialized_row_count=len(events),
    )

    class ScopeCacheRepository(_DashboardRepository):
        version = "v1"

        def dashboard_source_cache_key(self, query):
            return (self.version, query.requested_as_of_date, query.period)

    repository = ScopeCacheRepository(source)
    service = BrokerFlowDashboardQueryService(repository)
    top_query = BrokerFlowDashboardQuery(
        period="week",
        scope="top50",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=1,
    )
    all_query = BrokerFlowDashboardQuery(
        period="week",
        scope="all",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )
    bottom_query = BrokerFlowDashboardQuery(
        period="week",
        scope="bottom50",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=1,
    )

    top_snapshot = service.load_dashboard_snapshot(top_query)
    top_snapshot.top_signals[0].aggregation.events[0].net_qty = -9999
    all_snapshot = service.load_dashboard_snapshot(all_query)
    bottom_snapshot = service.load_dashboard_snapshot(bottom_query)

    all_positive = next(
        signal for signal in all_snapshot.top_signals if signal.stock_code == "2330"
    )
    assert all_positive.aggregation.total_net_qty == 1000
    assert all_positive.aggregation.events[0].net_qty == 1000
    assert all_snapshot.summary.bullish_stock_count == 1
    assert all_snapshot.summary.bearish_stock_count == 1
    assert bottom_snapshot.bottom_signals[0].stock_code == "2317"
    assert all_snapshot.quality == "degraded"
    assert all_snapshot.warnings == ("source_warning",)
    assert all_snapshot.selected_trading_dates == (date(2026, 7, 3),)
    assert all_snapshot.source_fingerprint == "fixture-v1"
    assert repository.calls == [top_query]

    repository.version = "v2"
    repository.source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=(_dashboard_event("2330", 1600), _dashboard_event("2317", -900)),
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v2",
        query_count=2,
        materialized_row_count=2,
    )
    updated = service.load_dashboard_snapshot(bottom_query)

    assert updated.source_fingerprint == "fixture-v2"
    assert updated.bottom_signals[0].aggregation.total_net_qty == -900
    assert repository.calls == [top_query, bottom_query]


def test_dashboard_source_cache_requires_stable_source_key_across_read():
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=(_dashboard_event("2330", 1000),),
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=2,
        materialized_row_count=1,
    )

    class ChangingRepository(_DashboardRepository):
        version = "v1"

        def load_dashboard_source(self, query):
            source_snapshot = super().load_dashboard_source(query)
            self.version = "v2"
            return source_snapshot

        def dashboard_source_cache_key(self, query):
            return (self.version, query.requested_as_of_date, query.period)

    repository = ChangingRepository(source)
    service = BrokerFlowDashboardQueryService(repository)
    first_query = BrokerFlowDashboardQuery(
        period="week",
        scope="top50",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )
    second_query = BrokerFlowDashboardQuery(
        period="week",
        scope="bottom50",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )
    third_query = BrokerFlowDashboardQuery(
        period="week",
        scope="all",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )

    service.load_dashboard_snapshot(first_query)
    service.load_dashboard_snapshot(second_query)
    service.load_dashboard_snapshot(third_query)

    assert repository.calls == [first_query, second_query]


def test_dashboard_semantic_reuse_builder_requires_stable_cached_source():
    source = BrokerFlowReadSnapshot(
        selected_trading_dates=(date(2026, 7, 3),),
        events=(_dashboard_event("2330", 1000), _dashboard_event("2317", -400)),
        tracked_branches=(),
        quality="observed",
        warnings=(),
        source_fingerprint="fixture-v1",
        query_count=2,
        materialized_row_count=2,
    )

    class VersionedRepository(_DashboardRepository):
        version = "v1"

        def source_cache_key(self):
            return self.version

        def dashboard_source_cache_key(self, query):
            return (self.version, query.requested_as_of_date, query.period)

    class DashboardAwareSemanticPort(_BatchSemanticPort):
        def __init__(self):
            super().__init__()
            self.dashboard_calls = []

        def build_batch_semantics_from_dashboard(
            self,
            stock_codes,
            decision_date,
            *,
            dashboard_source,
            expected_source_version,
        ):
            self.dashboard_calls.append(
                (stock_codes, decision_date, dashboard_source, expected_source_version)
            )
            return {}

    query = BrokerFlowDashboardQuery(
        period="week",
        scope="top_bottom",
        requested_as_of_date=date(2026, 7, 5),
        limit_per_side=50,
    )

    stable_repository = VersionedRepository(source)
    stable_port = DashboardAwareSemanticPort()
    stable_service = BrokerFlowDashboardQueryService(
        stable_repository, semantic_port=stable_port
    )
    stable_service.load_dashboard_snapshot(query)

    assert stable_repository.calls == [query]
    assert len(stable_port.dashboard_calls) == 1
    stable_codes, stable_date, stable_source, stable_version = stable_port.dashboard_calls[0]
    assert set(stable_codes) == {"2330", "2317"}
    assert stable_date == date(2026, 7, 3)
    assert stable_source is source
    assert stable_version == "v1"
    assert stable_port.calls == []

    class ChangingRepository(VersionedRepository):
        def load_dashboard_source(self, query):
            loaded = super().load_dashboard_source(query)
            self.version = "v2"
            return loaded

    changing_repository = ChangingRepository(source)
    changing_port = DashboardAwareSemanticPort()
    changing_service = BrokerFlowDashboardQueryService(
        changing_repository, semantic_port=changing_port
    )
    changing_service.load_dashboard_snapshot(query)

    assert changing_repository.calls == [query]
    assert changing_port.dashboard_calls == []
    assert len(changing_port.calls) == 1
