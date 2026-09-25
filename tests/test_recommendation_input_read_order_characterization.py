"""Pre-extraction candidate read order; isolated to PROFILE=test TEMP data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import date
from pathlib import Path
import re
import sqlite3
from threading import Barrier
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation_service import RecommendationService
from data_module.config import TWStockConfig
from recommendation_test_support import build_recommendation_test_preparer


def test_legacy_candidate_source_reads_are_lazy_and_keep_early_exit_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "profile-test-data",
        output_root=tmp_path / "profile-test-output",
        profile="test",
    )
    assert config.profile == "test"
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            "CREATE TABLE fundamental_valuation_metrics ("
            "stock_code TEXT, metric_name TEXT, value TEXT, as_of_date TEXT, "
            "available_date TEXT, source TEXT, source_version TEXT, quality TEXT)"
        )
        connection.executemany(
            "INSERT INTO fundamental_valuation_metrics VALUES (?, 'pe', ?, ?, ?, 'test', 'v1', 'observed')",
            [
                ("NO_SIGNAL", "1", "2026-05-19", "2026-05-19"),
                ("PE_HIGH", "20", "2026-05-19", "2026-05-19"),
                ("PASS_REVENUE", "5", "2026-05-19", "2026-05-19"),
            ],
        )

    codes = ("NO_SIGNAL", "PE_HIGH", "PASS_REVENUE")
    dates = pd.date_range("2026-05-01", periods=20, freq="D")
    frame = pd.DataFrame(
        [
            {
                "日期": current_date,
                "證券代號": code,
                "證券名稱": code,
                "收盤價": Decimal("100.00"),
                "成交股數": 1000,
            }
            for code in codes
            for current_date in dates
        ]
    )
    market_data_provider = lambda: frame.copy(deep=True)
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=market_data_provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config, market_data_provider=market_data_provider
        ),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""

    evaluator_calls: list[str] = []

    def evaluate(stock_frame: pd.DataFrame, _runtime_config: dict[str, object]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        evaluator_calls.append(code)
        if code == "NO_SIGNAL":
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "FinalScore": [Decimal("80.00")],
                "TotalScore": [Decimal("80.00")],
                "收盤價": [Decimal("100.00")],
            }
        )

    service.strategy_configurator.generate_recommendations = evaluate
    revenue_reads: list[str] = []

    def load_revenues(
        *,
        input_session: object,
        stock_code: str,
        decision_date: object,
    ) -> tuple[object, ...]:
        revenue_reads.append(stock_code)
        return ()

    service._load_governed_monthly_revenues = load_revenues

    original_connect = sqlite3.connect
    database_before = config.db_file.read_bytes()
    valuation_queries: list[str] = []

    def traced_connect(database: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original_connect(database, *args, **kwargs)
        connection.set_trace_callback(
            lambda statement: valuation_queries.append(statement)
            if "FROM fundamental_valuation_metrics" in statement
            else None
        )
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced_connect)

    result = service.run_recommendation(
        {"filters": {"pe_ratio_max": "10", "monthly_revenue_yoy_min": "0"}},
        as_of_date="2026-05-20",
        result_id="r018-read-order-characterization",
    )

    queried_codes = [
        re.search(r"WHERE stock_code = '([^']+)'", statement).group(1)
        for statement in valuation_queries
        if re.search(r"WHERE stock_code = '([^']+)'", statement)
    ]
    assert evaluator_calls == list(codes)
    assert queried_codes == ["PE_HIGH", "PASS_REVENUE"]
    assert revenue_reads == ["PASS_REVENUE"]
    assert result == []
    assert config.db_file.read_bytes() == database_before


def test_interleaved_monthly_reads_keep_invocation_session_cutoff_and_lineage() -> None:
    barrier = Barrier(2)
    observed: list[tuple[str, str, date]] = []

    class _Session:
        def __init__(self, lineage: str) -> None:
            self.lineage = lineage

        def load_monthly_revenues(
            self, *, stock_code: str, decision_date: date
        ) -> tuple[str, ...]:
            barrier.wait(timeout=5)
            observed.append((self.lineage, stock_code, decision_date))
            return (self.lineage,)

    service = object.__new__(RecommendationService)
    session_a = _Session("capture-A")
    session_b = _Session("capture-B")
    cutoff_a = date(2026, 5, 20)
    cutoff_b = date(2026, 5, 21)

    with ThreadPoolExecutor(max_workers=2) as pool:
        result_a = pool.submit(
            service._load_governed_monthly_revenues,
            input_session=session_a,
            stock_code="AAA",
            decision_date=cutoff_a,
        )
        result_b = pool.submit(
            service._load_governed_monthly_revenues,
            input_session=session_b,
            stock_code="BBB",
            decision_date=cutoff_b,
        )
        assert result_a.result(timeout=5) == ("capture-A",)
        assert result_b.result(timeout=5) == ("capture-B",)

    assert sorted(observed) == sorted(
        [
            ("capture-A", "AAA", cutoff_a),
            ("capture-B", "BBB", cutoff_b),
        ]
    )
