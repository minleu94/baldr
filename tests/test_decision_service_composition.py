import runpy
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app_module.decision_service_composition import (
    build_decision_service_composition,
    build_industry_mapper,
)
from data_module.current_fundamental_snapshots import (
    ensure_current_observation_schema,
    insert_observations,
    monthly_snapshot_rows,
)
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortReader
from data_module.daily_source_snapshot import (
    DailySourceSnapshot,
    DailySourceSnapshotFileReader,
    DailySourceUseScope,
)


def _composition_dependencies() -> dict[str, MagicMock]:
    dependencies = {
        name: MagicMock(name=name)
        for name in (
            "IndustryMapper",
            "ScreeningService",
            "MarketRegimeDetector",
            "RegimeService",
            "RecommendationService",
            "StockScreener",
        )
    }
    dependencies["IndustryMapper"].return_value = object()
    dependencies["MarketRegimeDetector"].return_value = object()
    dependencies["StockScreener"].return_value = object()
    return dependencies


def _synthetic_dual_market_cohort(tmp_path: Path) -> DailyMonthlyRevenueCohortReader:
    """重用雙市場快照測試 fixture，避免另造 reader 或 acceptance。"""
    helpers = runpy.run_path(
        str(Path(__file__).with_name("test_daily_monthly_revenue_cohort.py"))
    )
    readers, _acceptances, batch_ids = helpers["_pair"](tmp_path)
    pin = helpers["_build_pair"](readers, batch_ids)
    return DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers=readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )


def _seed_monthly_rows_from_cohort(
    database: Path,
    cohort_reader: DailyMonthlyRevenueCohortReader,
    *,
    observed_at: datetime,
) -> None:
    rows: list[dict[str, str]] = []
    for snapshot in cohort_reader.verify_cohort():
        record = snapshot.records[0]
        csv_path = database.parent / f"{record.market}-monthly.csv"
        csv_path.write_text(
            "stock_code,period,fetched_at,current_month_revenue,"
            "previous_year_month_revenue,source_version,market,source\n"
            f"{record.stock_code},{record.period},"
            f"{observed_at.isoformat()},1234,900,"
            f"{record.source_version},{record.market},"
            "mops.monthly_revenue_static_snapshot\n",
            encoding="utf-8",
        )
        market_rows = monthly_snapshot_rows(
            csv_path,
            verified_source_versions=frozenset({record.source_version}),
        )
        for row in market_rows:
            row["observed_at"] = observed_at.isoformat()
        rows.extend(market_rows)
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        insert_observations(connection, rows)


def test_decision_service_composition_injects_shared_mapper_and_data_ports() -> None:
    dependencies = {
        name: MagicMock(name=name)
        for name in (
            "IndustryMapper",
            "ScreeningService",
            "MarketRegimeDetector",
            "RegimeService",
            "RecommendationService",
            "StockScreener",
        )
    }
    dependencies["IndustryMapper"].return_value = mapper = object()
    dependencies["MarketRegimeDetector"].return_value = regime_detector = object()
    dependencies["StockScreener"].return_value = stock_screener = object()
    industry_provider = lambda: None
    companies_provider = lambda: None
    market_provider = object()

    composition = build_decision_service_composition(
        config=SimpleNamespace(),
        dependencies=dependencies,
        companies_provider=companies_provider,
        industry_index_provider=industry_provider,
        market_index_provider=market_provider,
    )

    dependencies["IndustryMapper"].assert_called_once_with(
        composition.config,
        industry_index_provider=industry_provider,
        companies_provider=companies_provider,
    )
    dependencies["ScreeningService"].assert_called_once_with(
        composition.config, industry_mapper=mapper, stock_screener=stock_screener
    )
    stock_screener_kwargs = dependencies["StockScreener"].call_args.kwargs
    assert callable(stock_screener_kwargs["recent_stock_provider"])
    assert callable(stock_screener_kwargs["recent_industry_provider"])
    assert callable(stock_screener_kwargs["stock_fallback_provider"])
    assert callable(stock_screener_kwargs["industry_fallback_provider"])
    dependencies["MarketRegimeDetector"].assert_called_once_with()
    dependencies["RegimeService"].assert_called_once_with(
        composition.config,
        regime_detector=regime_detector,
        use_persistent_history=True,
        market_frame_provider=market_provider,
    )
    dependencies["RecommendationService"].assert_called_once()
    recommendation_args = dependencies["RecommendationService"].call_args
    assert recommendation_args.args == (composition.config,)
    assert recommendation_args.kwargs["industry_mapper"] is mapper
    assert recommendation_args.kwargs["regime_service"] is dependencies[
        "RegimeService"
    ].return_value
    assert recommendation_args.kwargs["input_preparer"] is not None


def test_normal_composition_injects_read_only_recommendation_calibration_consumer(monkeypatch) -> None:
    dependencies = {
        name: MagicMock(name=name)
        for name in (
            "IndustryMapper",
            "ScreeningService",
            "MarketRegimeDetector",
            "RegimeService",
            "RecommendationService",
            "StockScreener",
        )
    }
    dependencies["IndustryMapper"].return_value = object()
    dependencies["MarketRegimeDetector"].return_value = object()
    dependencies["StockScreener"].return_value = object()
    consumer = object()
    monkeypatch.setattr(
        "app_module.recommendation_calibration_consumer.build_default_recommendation_calibration_consumer",
        lambda config: consumer,
    )
    monkeypatch.setattr(
        "app_module.decision_service_composition._default_dependencies",
        lambda: dependencies,
    )

    config = SimpleNamespace()
    build_decision_service_composition(
        config=config,
        industry_index_provider=lambda: None,
        market_index_provider=object(),
    )

    kwargs = dependencies["RecommendationService"].call_args.kwargs
    assert kwargs["calibration_consumer"] is consumer


def test_legacy_mapper_composition_injects_explicit_company_and_index_providers() -> None:
    constructor = MagicMock(return_value="mapper")
    config = SimpleNamespace()
    company_frame_provider = lambda: None
    index_frame_provider = lambda: None

    result = build_industry_mapper(
        config,
        constructor=constructor,
        companies_provider=company_frame_provider,
        industry_index_provider=index_frame_provider,
    )

    assert result == "mapper"
    constructor.assert_called_once_with(
        config,
        industry_index_provider=index_frame_provider,
        companies_provider=company_frame_provider,
    )


def test_composition_binds_one_verified_dual_market_reader_to_current_input_port(
    tmp_path: Path,
) -> None:
    cohort_reader = _synthetic_dual_market_cohort(tmp_path)
    frozen_at = datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc)
    database = tmp_path / "current-fundamentals.sqlite"
    _seed_monthly_rows_from_cohort(
        database,
        cohort_reader,
        observed_at=datetime(2026, 10, 2, 4, 30, tzinfo=timezone.utc),
    )
    config = SimpleNamespace(db_file=database, output_root=tmp_path / "recommendation")
    dependencies = _composition_dependencies()

    build_decision_service_composition(
        config=config,
        dependencies=dependencies,
        companies_provider=lambda: None,
        industry_index_provider=lambda: None,
        market_index_provider=object(),
        daily_monthly_cohort_reader=cohort_reader,
    )

    preparer = dependencies["RecommendationService"].call_args.kwargs[
        "input_preparer"
    ]
    assert preparer.daily_monthly_cohort_reader is cohort_reader
    assert (
        preparer.current_fundamental_provider.daily_source_snapshot_reader
        is cohort_reader
    )
    # The composition-owned preparer and its live current provider share the
    # same pinned reader; the calls below exercise both stock-to-market routes.
    preparer.market_session_cadence_factory = lambda *_args, **_kwargs: None
    session = preparer.begin(config, invocation_frozen_at=frozen_at)
    resolution = session.resolve_cutoff(
        runtime_config={},
        as_of_date=None,
        historical_research=False,
        select_latest_available_cutoff=False,
    )
    assert resolution.cutoff is None

    results = {
        stock_code: session.load_current_monthly_revenues(
            stock_code=stock_code,
            cutoff_at=frozen_at,
        )
        for stock_code in ("2330", "6488")
    }
    assert {stock_code: result.status for stock_code, result in results.items()} == {
        "2330": "ready",
        "6488": "ready",
    }
    assert all(result.latest_period == "2026-04" for result in results.values())
    context = session.daily_monthly_cohort_source_context()
    assert context["cohort_sha256"] == cohort_reader.pin.cohort_sha256
    assert context["pin"] == cohort_reader.pin.to_dict()
    assert context["read_outcome_by_stock"] == {
        "2330": "ready",
        "6488": "ready",
    }
    assert context["source_scope"] == "current_observed_only"
    assert context["historical_pit_eligible"] is False
    assert context["formal_pit_eligible"] is False


def test_invalid_cohort_reader_type_fails_before_dependency_resolution(monkeypatch) -> None:
    resolve_dependencies = MagicMock(side_effect=AssertionError("too late"))
    monkeypatch.setattr(
        "app_module.decision_service_composition._default_dependencies",
        resolve_dependencies,
    )

    with pytest.raises(TypeError, match="daily_monthly_cohort_reader_type_invalid"):
        build_decision_service_composition(
            config=SimpleNamespace(),
            daily_monthly_cohort_reader=object(),  # type: ignore[arg-type]
        )

    resolve_dependencies.assert_not_called()


def test_broken_second_market_fails_before_any_service_construction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cohort_reader = _synthetic_dual_market_cohort(tmp_path)
    dependencies = _composition_dependencies()
    original_read_snapshot = DailySourceSnapshotFileReader.read_snapshot
    attempted_markets: list[str] = []

    def fail_tpex_read(
        reader: DailySourceSnapshotFileReader,
        batch_id: str,
        *,
        expected_scope: DailySourceUseScope,
    ) -> DailySourceSnapshot:
        market = expected_scope.market
        attempted_markets.append(str(market))
        if market == "tpex":
            raise OSError("synthetic_tpex_batch_unavailable")
        return original_read_snapshot(
            reader,
            batch_id,
            expected_scope=expected_scope,
        )

    monkeypatch.setattr(DailySourceSnapshotFileReader, "read_snapshot", fail_tpex_read)
    with pytest.raises(OSError, match="synthetic_tpex_batch_unavailable"):
        build_decision_service_composition(
            config=SimpleNamespace(),
            dependencies=dependencies,
            companies_provider=lambda: None,
            industry_index_provider=lambda: None,
            market_index_provider=object(),
            daily_monthly_cohort_reader=cohort_reader,
        )

    assert attempted_markets == ["twse", "tpex"]
    for constructor in dependencies.values():
        constructor.assert_not_called()
