"""Synthetic R018 source/preparation characterization; no formal data access."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation.input_preparation import (
    RecommendationInputPreparer,
    load_recommendation_market_frame,
    prepare_recommendation_market,
    resolve_recommendation_cutoff,
)
from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from app_module.recommendation_service import RecommendationService
from data_module.config import TWStockConfig
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from data_module.recommendation_input_providers import (
    HistoricalRecommendationMarketFrameProvider,
    PITRecommendationMembershipProvider,
    RecommendationFundamentalInputProvider,
)
from recommendation_test_support import build_recommendation_test_preparer


def _test_config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(
        data_root=tmp_path / "profile-test-data",
        output_root=tmp_path / "profile-test-output",
        profile="test",
    )
    assert config.profile == "test"
    return config


def test_recommendation_service_requires_explicit_input_preparer() -> None:
    with pytest.raises(ValueError, match="必須由 application composition 注入 input_preparer"):
        RecommendationService(
            SimpleNamespace(db_file="unused.db", use_sqlite=False),
            industry_mapper=MagicMock(),
        )


class _FrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = 0

    def __call__(self) -> pd.DataFrame:
        self.calls += 1
        return self.frame.copy(deep=True)


def test_cutoff_resolution_preserves_explicit_historical_and_natural_identity() -> None:
    config = {"as_of_date": None}
    explicit = resolve_recommendation_cutoff(
        config=config,
        as_of_date="2026/05/20",
        historical_research=False,
        select_latest_available_cutoff=False,
    )
    assert (
        explicit.cutoff,
        explicit.temporal_mode,
        explicit.cutoff_selection,
        explicit.cutoff_policy,
    ) == (
        "2026-05-20",
        "explicit_cutoff_not_natural",
        "caller_requested_cutoff",
        "caller_explicit_cutoff_not_natural",
    )

    historical = resolve_recommendation_cutoff(
        config=config,
        as_of_date=date(2026, 5, 20),
        historical_research=True,
        select_latest_available_cutoff=False,
    )
    assert (
        historical.cutoff,
        historical.temporal_mode,
        historical.cutoff_selection,
        historical.cutoff_policy,
    ) == (
        "2026-05-20",
        "historical_research_not_as_if_available",
        "explicit_historical_cutoff",
        "explicit_historical_research",
    )

    latest = resolve_recommendation_cutoff(
        config=config,
        as_of_date=None,
        historical_research=False,
        select_latest_available_cutoff=True,
    )
    assert (
        latest.cutoff,
        latest.temporal_mode,
        latest.cutoff_selection,
        latest.cutoff_policy,
    ) == (
        None,
        "natural_producer_clock",
        "producer_selected_latest_available_cutoff",
        "source_latest_available_exact",
    )


@pytest.mark.parametrize(
    ("config", "as_of_date", "historical", "latest"),
    [
        ({"as_of_date": "2026-05-20"}, None, False, True),
        ({"as_of_date": None}, None, True, False),
        ({"as_of_date": None}, None, True, True),
    ],
)
def test_cutoff_resolution_rejects_ambiguous_requests(
    config: dict[str, object],
    as_of_date: str | None,
    historical: bool,
    latest: bool,
) -> None:
    with pytest.raises(ValueError):
        resolve_recommendation_cutoff(
            config=config,
            as_of_date=as_of_date,
            historical_research=historical,
            select_latest_available_cutoff=latest,
        )


def test_prepared_market_matches_legacy_decision_frame_and_fingerprint(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    source = pd.DataFrame(
        [
            {"日期": "2026-05-19", "證券代號": "2330", "證券名稱": "TSMC", "available_date": "2026-05-19", "收盤價": "10"},
            {"日期": "2026-05-20", "證券代號": "2330", "證券名稱": "old", "available_date": "2026-05-20", "收盤價": "20"},
            {"日期": "2026-05-20", "證券代號": "2330", "證券名稱": "revised", "available_date": "2026-05-21", "收盤價": "21"},
            {"日期": "2026-05-20", "證券代號": "2317", "證券名稱": "HON", "available_date": "2026-05-20", "收盤價": "30"},
            {"日期": "2026-05-21", "證券代號": "2317", "證券名稱": "future", "available_date": "2026-05-21", "收盤價": "40"},
        ]
    )
    provider = _FrameProvider(source)
    service_config = SimpleNamespace(db_file=config.db_file, use_sqlite=False)
    service = RecommendationService(
        service_config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            service_config, market_data_provider=provider
        ),
    )
    legacy, legacy_stock_column, legacy_cutoff = service._decision_frame(
        source.copy(deep=True), "2026-05-20"
    )
    legacy = legacy[legacy[legacy_stock_column].isin({"2330"})].copy()
    canonical = legacy.sort_values(
        [legacy_stock_column, "日期"], kind="stable"
    )
    legacy_payload = (
        canonical.reindex(sorted(canonical.columns), axis=1)
        .astype(str)
        .to_dict("records")
    )
    legacy_fingerprint = sha256(
        __import__("json").dumps(
            legacy_payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()

    prepared = prepare_recommendation_market(
        source_frame=source.copy(deep=True),
        cutoff="2026-05-20",
        market_data_provider=provider,
        universe=("2330",),
    )
    pd.testing.assert_frame_equal(prepared.frame, legacy)
    assert prepared.stock_column == legacy_stock_column
    assert prepared.decision_cutoff == legacy_cutoff == "2026-05-20"
    assert prepared.source_id == "_FrameProvider"
    assert prepared.market_data_fingerprint == legacy_fingerprint
    assert prepared.data_date == "2026-05-20"


def test_empty_market_preparation_preserves_cutoff_and_source_identity() -> None:
    provider = _FrameProvider(pd.DataFrame(columns=["日期", "證券代號", "證券名稱"]))
    prepared = prepare_recommendation_market(
        source_frame=provider(),
        cutoff="2026-05-20",
        market_data_provider=provider,
    )
    assert prepared.decision_cutoff == "2026-05-20"
    assert prepared.source_id == "_FrameProvider"
    assert prepared.data_date == ""
    assert prepared.frame.empty


def test_empty_market_without_date_column_keeps_legacy_early_return() -> None:
    source = pd.DataFrame(columns=["證券代號"])
    provider = _FrameProvider(source)

    prepared = prepare_recommendation_market(
        source_frame=source,
        cutoff="2026-05-20",
        market_data_provider=provider,
    )

    assert list(prepared.frame.columns) == ["證券代號", "證券名稱"]
    assert prepared.stock_column == "證券代號"
    assert prepared.decision_cutoff == "2026-05-20"
    assert prepared.source_id == "_FrameProvider"
    assert prepared.market_data_fingerprint == sha256(b"[]").hexdigest()
    assert prepared.data_date == ""


def test_market_source_dispatch_keeps_explicit_historical_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    frame = pd.DataFrame({"日期": ["2026-05-20"], "證券代號": ["2330"]})

    class _Historical:
        def __call__(self, cutoff: str | None) -> pd.DataFrame:
            calls.append(f"historical:{cutoff}")
            return frame

    config = SimpleNamespace(use_sqlite=False)
    market_provider = DefaultRecommendationMarketDataProvider(config)
    monkeypatch.setattr(
        DefaultRecommendationMarketDataProvider,
        "__call__",
        lambda _self: calls.append("current") or frame,
    )
    loaded = load_recommendation_market_frame(
        config=config,
        market_data_provider=market_provider,
        historical_market_provider=_Historical(),  # type: ignore[arg-type]
        cutoff="2026-05-20",
    )

    assert calls == ["historical:2026-05-20"]
    assert loaded.equals(frame)


def test_invocation_session_is_lazy_and_keeps_candidate_reads_explicit(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    trace: list[object] = []
    frame = pd.DataFrame(
        {"日期": ["2026-05-20"], "證券代號": ["2330"], "收盤價": ["10"]}
    )

    class _Market:
        def __call__(self) -> pd.DataFrame:
            trace.append("market")
            return frame.copy(deep=True)

    class _Historical:
        def __call__(self, cutoff: str | None) -> pd.DataFrame:
            trace.append(("historical", cutoff))
            return frame.copy(deep=True)

    class _PIT:
        def read(self, cutoff: str, values: object) -> str:
            trace.append(("pit", cutoff, values))
            return "pit-result"

    class _Fundamental:
        def load_pe(self, *, stock_code: str, decision_date: str) -> None:
            trace.append(("pe", stock_code, decision_date))
            return None

        def load_monthly_revenues(
            self, *, stock_code: str, decision_date: date
        ) -> tuple[object, ...]:
            trace.append(("revenue", stock_code, decision_date))
            return ()

    preparer = RecommendationInputPreparer(
        market_data_provider=_Market(),  # type: ignore[arg-type]
        historical_market_provider=_Historical(),  # type: ignore[arg-type]
        pit_membership_provider=_PIT(),  # type: ignore[arg-type]
        fundamental_input_provider=_Fundamental(),  # type: ignore[arg-type]
    )
    session = preparer.begin(config)
    assert trace == []

    resolution = session.resolve_cutoff(
        runtime_config={"as_of_date": None},
        as_of_date="2026-05-20",
        historical_research=False,
        select_latest_available_cutoff=False,
    )
    market = session.prepare_market(cutoff=resolution.cutoff)
    assert market.decision_cutoff == "2026-05-20"
    assert trace == ["market"]

    assert session.read_pit_membership("2026-05-20", {"pit_market_scope": "twse"}) == "pit-result"  # type: ignore[comparison-overlap]
    assert session.load_pe(stock_code="2330", decision_date="2026-05-20") is None
    assert session.load_monthly_revenues(
        stock_code="2330", decision_date=date(2026, 5, 20)
    ) == ()
    assert trace == [
        "market",
        ("pit", "2026-05-20", {"pit_market_scope": "twse"}),
        ("pe", "2330", "2026-05-20"),
        ("revenue", "2330", date(2026, 5, 20)),
    ]


def test_historical_sqlite_market_read_is_readonly_and_missing_db_is_not_created(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    config.use_sqlite = True
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" TEXT)'
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("20260519", "2330", "100"),
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("20260520", "2330", "101"),
        )
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("20260521", "2330", "102"),
        )
    before = sha256(config.db_file.read_bytes()).hexdigest()

    frame = HistoricalRecommendationMarketFrameProvider(config)("2026-05-20")

    assert frame["日期"].tolist() == ["20260519", "20260520"]
    assert sha256(config.db_file.read_bytes()).hexdigest() == before

    missing = _test_config(tmp_path / "missing")
    missing.use_sqlite = True
    missing_path = Path(missing.db_file)
    assert not missing_path.exists()
    with pytest.raises(sqlite3.OperationalError):
        HistoricalRecommendationMarketFrameProvider(missing)("2026-05-20")
    assert not missing_path.exists()


def test_historical_csv_source_priority_is_all_stocks_then_primary(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    config.use_sqlite = False
    config.all_stocks_data_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"日期": "2026-05-20", "證券代號": "2330", "證券名稱": "backup"}]
    ).to_csv(config.all_stocks_data_file, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [{"日期": "2026-05-20", "證券代號": "2317", "證券名稱": "primary"}]
    ).to_csv(config.stock_data_file, index=False, encoding="utf-8-sig")

    frame = HistoricalRecommendationMarketFrameProvider(config)("2026-05-20")

    assert frame["證券代號"].tolist() == ["2330"]


def test_fundamental_pe_reader_is_pit_bounded_and_does_not_create_missing_db(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            "CREATE TABLE fundamental_valuation_metrics ("
            "stock_code TEXT, metric_name TEXT, value TEXT, as_of_date TEXT, "
            "available_date TEXT, source TEXT, source_version TEXT, quality TEXT)"
        )
        connection.executemany(
            "INSERT INTO fundamental_valuation_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2330", "pe", "12.5", "2026-05-10", "2026-05-11", "s", "1", "observed"),
                ("2330", "pe", "99", "2026-05-19", "2026-05-21", "s", "2", "observed"),
                ("2330", "pe", "77", "2026-05-21", "2026-05-19", "s", "3", "observed"),
            ],
        )
    before = sha256(config.db_file.read_bytes()).hexdigest()

    provider = RecommendationFundamentalInputProvider(config.db_file)
    observation = provider.load_pe(
        stock_code="2330", decision_date="2026-05-20"
    )

    assert observation is not None
    assert observation.as_context() == {
        "value": "12.5",
        "as_of_date": "2026-05-10",
        "available_date": "2026-05-11",
        "source": "s",
        "source_version": "1",
        "quality": "observed",
    }
    assert sha256(config.db_file.read_bytes()).hexdigest() == before

    missing = _test_config(tmp_path / "missing-pe")
    missing_db = Path(missing.db_file)
    with pytest.raises(sqlite3.OperationalError):
        RecommendationFundamentalInputProvider(missing_db).load_pe(
            stock_code="2330", decision_date="2026-05-20"
        )
    assert not missing_db.exists()


def test_monthly_revenue_reader_is_lazy_and_requires_existing_database(
    tmp_path: Path,
) -> None:
    config = _test_config(tmp_path)
    calls: list[tuple[str, date]] = []
    factory_calls: list[str] = []

    class _MonthlyProvider:
        def load_monthly_revenues(
            self, *, stock_code: str, decision_date: date
        ) -> tuple[object, ...]:
            calls.append((stock_code, decision_date))
            return ()

    missing_db = Path(config.db_file)
    cached_calls: list[tuple[str, date]] = []

    class _CachedMonthlyProvider:
        def load_monthly_revenues(
            self, *, stock_code: str, decision_date: date
        ) -> tuple[object, ...]:
            cached_calls.append((stock_code, decision_date))
            return ()

    # Explicit provider is equivalent to the legacy service's already-warmed
    # cache, so it remains callable even if the source file is later absent.
    cached = RecommendationFundamentalInputProvider(
        missing_db,
        monthly_revenue_provider=_CachedMonthlyProvider(),  # type: ignore[arg-type]
    )
    assert cached.load_monthly_revenues(
        stock_code="CACHE", decision_date=date(2026, 5, 20)
    ) == ()
    assert cached_calls == [("CACHE", date(2026, 5, 20))]
    assert not missing_db.exists()

    def missing_factory() -> FundamentalSQLiteProvider | None:
        factory_calls.append("missing-db")
        return _MonthlyProvider()  # type: ignore[return-value]

    missing = RecommendationFundamentalInputProvider(
        missing_db, monthly_revenue_provider_factory=missing_factory
    )
    assert missing.load_monthly_revenues(
        stock_code="2330", decision_date=date(2026, 5, 20)
    ) == ()
    assert calls == []
    assert factory_calls == []
    assert not missing_db.exists()

    missing_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(missing_db):
        pass
    # 舊 service 對同一 instance 的初次 missing DB 會 cache no-provider，
    # 後續即使 DB 出現也不重試。
    assert missing.load_monthly_revenues(
        stock_code="2330", decision_date=date(2026, 5, 20)
    ) == ()
    assert calls == []
    assert factory_calls == []

    def active_factory() -> FundamentalSQLiteProvider | None:
        factory_calls.append("active-db")
        return _MonthlyProvider()  # type: ignore[return-value]

    active = RecommendationFundamentalInputProvider(
        missing_db, monthly_revenue_provider_factory=active_factory
    )
    assert active.load_monthly_revenues(
        stock_code="2330", decision_date=date(2026, 5, 20)
    ) == ()
    assert calls == [("2330", date(2026, 5, 20))]
    assert factory_calls == ["active-db"]


def test_pit_membership_provider_preserves_request_and_fails_closed() -> None:
    class _Reader:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail
            self.calls: list[dict[str, object]] = []

        @staticmethod
        def default_decision_at(value: date) -> str:
            return f"{value.isoformat()}T08:00:00+08:00"

        def read(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            if self.fail:
                raise OSError("synthetic PIT source unavailable")
            return "synthetic-result"

    reader = _Reader()
    provider = PITRecommendationMembershipProvider(
        reader, configured_market_scope="twse_listed"  # type: ignore[arg-type]
    )
    result = provider.read(
        "2026-05-20",
        {"pit_decision_at": "2026-05-20T10:00:00+08:00"},
    )
    assert result == "synthetic-result"
    assert reader.calls == [
        {
            "as_of_date": date(2026, 5, 20),
            "decision_at": "2026-05-20T10:00:00+08:00",
            "market_scope": "twse_listed",
        }
    ]

    failing_reader = _Reader(fail=True)
    failing_provider = PITRecommendationMembershipProvider(
        failing_reader, configured_market_scope="twse_listed"  # type: ignore[arg-type]
    )
    failed = failing_provider.read("2026-05-20", {})
    assert failed is not None
    assert failed.status == "unavailable"
    assert failed.quality == "missing"
    assert failed.rows == ()
    assert failed.warnings == ("pit_membership_reader_error:OSError",)
