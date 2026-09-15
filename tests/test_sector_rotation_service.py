from datetime import date, timedelta
from dataclasses import replace
import sqlite3

import pandas as pd

from app_module.decision_desk_dtos import DecisionDeskQuality
from app_module.industry_strength_service import (
    IndustryStrengthData,
    IndustryStrengthService,
    industry_level,
    is_usable_industry_index_name,
)
from app_module.sector_rotation_service import SectorRotationService, SQLiteIndustryIndexSectorRotationProvider


def _build_history_frame(
    sector_histories: dict[str, list[float]],
    target_date: date,
    date_fmt: str = "%Y-%m-%d",
) -> pd.DataFrame:
    rows = []
    first_date = target_date - timedelta(days=len(next(iter(sector_histories.values()))) - 1)
    for sector, history in sector_histories.items():
        for offset, close in enumerate(history):
            current = first_date + timedelta(days=offset)
            rows.append(
                {
                    "date": current.strftime(date_fmt),
                    "sector": sector,
                    "close": float(close),
                }
            )
    return pd.DataFrame(rows)


class FakeSectorProvider:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def fetch(self, as_of_date: date) -> pd.DataFrame:
        return self.frame.copy()


class BrokenSectorProvider:
    def fetch(self, as_of_date: date) -> pd.DataFrame:
        raise RuntimeError("sector data feed unavailable")


def test_sector_rotation_service_outputs_leading_trailing_and_stable_ranking():
    frame = _build_history_frame(
        {
            "semi": [80 + 2.5 * i for i in range(21)],
            "financial": [90 + i for i in range(21)],
            "electronics": [95 + 0.5 * i for i in range(21)],
        },
        date(2026, 6, 15),
    )
    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.leading_sector == "semi"
    assert snapshot.trailing_sector == "electronics"
    assert snapshot.rotation_intensity_bp is not None
    assert snapshot.rotation_intensity_bp > 2000
    assert snapshot.warnings == ()

    ranking = snapshot.meta["sector_ranking"]
    assert ranking[0]["sector"] == "semi"
    assert ranking[1]["sector"] == "financial"
    assert ranking[2]["sector"] == "electronics"
    assert isinstance(ranking[0]["relative_strength_bp"], int)
    assert isinstance(ranking[0]["change_5d_bp"], int)
    assert isinstance(ranking[0]["change_20d_bp"], int)


def test_sector_rotation_service_tie_breaker_is_deterministic_with_same_strength():
    frame = _build_history_frame(
        {"A": [100 + i for i in range(21)], "B": [100 + i for i in range(21)]},
        date(2026, 6, 15),
    )
    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    ranking = snapshot.meta["sector_ranking"]
    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert ranking[0]["sector"] == "A"
    assert ranking[1]["sector"] == "B"


def test_sector_rotation_service_supports_numeric_yyyymmdd_without_crash():
    base = date(2026, 6, 15)
    frame = _build_history_frame(
        {
            "A": [100 + i for i in range(21)],
            "B": [200 + i * 0.5 for i in range(21)],
        },
        base,
        date_fmt="%Y%m%d",
    ).copy()
    frame["date"] = frame["date"].astype(int)

    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(base)

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.leading_sector == "A"
    assert snapshot.trailing_sector == "B"
    assert snapshot.rotation_intensity_bp is not None
    assert snapshot.meta["sector_ranking"][0]["change_5d_bp"] is not None


def test_sector_rotation_service_supports_string_yyyymmdd_and_dash_dates():
    frame = _build_history_frame(
        {
            "A": [100 + i for i in range(21)],
            "B": [120 + i * 0.2 for i in range(21)],
        },
        date(2026, 6, 15),
    )
    frame.loc[0, "date"] = "20200101"
    frame.loc[1, "date"] = "2019-06-02"

    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality in {DecisionDeskQuality.OBSERVED, DecisionDeskQuality.DEGRADED}
    assert snapshot.leading_sector == "A"
    assert snapshot.as_of_date == date(2026, 6, 15)


def test_sector_rotation_service_degrades_when_sector_data_insufficient():
    frame = pd.concat(
        [
            _build_history_frame(
                {"good_sector": [100 + i for i in range(21)]},
                date(2026, 6, 15),
            ),
            _build_history_frame(
                {"weak_sector": [100 + i for i in range(5)]},
                date(2026, 6, 15),
            ),
        ],
        ignore_index=True,
    ).rename(columns={"sector": "產業別", "close": "收盤指數"})

    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.leading_sector == "good_sector"
    assert snapshot.trailing_sector is None
    assert snapshot.rotation_intensity_bp is None
    assert any("sector_rotation_data_insufficient:weak_sector" in w for w in snapshot.warnings)


def test_sector_rotation_service_returns_missing_when_no_match_date():
    frame = pd.DataFrame(
        {
            "date": ["2026-06-10", "2026-06-11"],
            "sector": ["半導體", "金融保險"],
            "close": [100.0, 120.0],
        }
    )
    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.MISSING
    assert snapshot.warnings == ("sector_rotation_missing",)
    assert snapshot.leading_sector is None


def test_sector_rotation_service_degraded_on_provider_failure():
    service = SectorRotationService(BrokenSectorProvider())
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.leading_sector is None
    assert any("sector_rotation_provider_error" in w for w in snapshot.warnings)


def test_sector_rotation_service_handles_non_contiguous_index_and_observes_ranking():
    frame = _build_history_frame(
        {
            "A": [100 + i for i in range(21)],
            "B": [200 + i * 0.5 for i in range(21)],
        },
        date(2026, 6, 15),
    )
    frame.index = [i * 2 for i in range(len(frame))]

    service = SectorRotationService(FakeSectorProvider(frame))
    snapshot = service.build_snapshot(date(2026, 6, 15))

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.leading_sector == "A"
    assert snapshot.trailing_sector == "B"
    assert snapshot.rotation_intensity_bp is not None
    ranking = snapshot.meta["sector_ranking"]
    assert ranking[0]["sector"] == "A"
    assert ranking[1]["sector"] == "B"


def test_sqlite_industry_index_provider_builds_sector_rotation_from_sqlite(tmp_path):
    target_date = date(2026, 6, 15)
    db_path = tmp_path / "twstock.db"
    rows = []
    first_date = target_date - timedelta(days=20)
    for offset in range(21):
        current = first_date + timedelta(days=offset)
        date_key = current.strftime("%Y%m%d")
        rows.extend(
            [
                (date_key, "半導體", 100 + offset * 2.5),
                (date_key, "金融保險", 100 + offset * 1.0),
                (date_key, "水泥", 100 + offset * 0.2),
            ]
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            )
            """
        )
        conn.executemany(
            "INSERT INTO industry_indices (日期, 指數名稱, 收盤指數) VALUES (?, ?, ?)",
            rows,
        )

    service = SectorRotationService(SQLiteIndustryIndexSectorRotationProvider(db_path))
    snapshot = service.build_snapshot(target_date)

    assert snapshot.quality == DecisionDeskQuality.OBSERVED
    assert snapshot.as_of_date == target_date
    assert snapshot.leading_sector == "半導體"
    assert snapshot.trailing_sector == "水泥"
    assert snapshot.rotation_intensity_bp is not None
    assert snapshot.meta["source"] == "sqlite_industry_indices"


def test_sqlite_industry_index_provider_uses_latest_available_date_with_warning(tmp_path):
    latest_date = date(2026, 6, 12)
    requested_date = date(2026, 6, 15)
    db_path = tmp_path / "twstock.db"
    rows = []
    first_date = latest_date - timedelta(days=20)
    for offset in range(21):
        current = first_date + timedelta(days=offset)
        date_key = current.strftime("%Y%m%d")
        rows.extend(
            [
                (date_key, "半導體", 100 + offset * 2.0),
                (date_key, "金融保險", 100 + offset * 1.0),
            ]
        )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                PRIMARY KEY (指數名稱, 日期)
            )
            """
        )
        conn.executemany(
            "INSERT INTO industry_indices (日期, 指數名稱, 收盤指數) VALUES (?, ?, ?)",
            rows,
        )

    service = SectorRotationService(SQLiteIndustryIndexSectorRotationProvider(db_path))
    snapshot = service.build_snapshot(requested_date)

    assert snapshot.quality == DecisionDeskQuality.DEGRADED
    assert snapshot.as_of_date == latest_date
    assert snapshot.leading_sector == "半導體"
    assert "sector_rotation_as_of_fallback:2026-06-12" in snapshot.warnings


class _IndustryStrengthProvider:
    def __init__(self, data: IndustryStrengthData, latest: date):
        self.data = data
        self.latest = latest

    def latest_available_date(self) -> date:
        return self.latest

    def fetch(self, as_of_date: date, *, session_limit: int = 25) -> IndustryStrengthData:
        return self.data


def _industry_strength_data(*, omit_first_index_date: bool = False, benchmark_name: str = "TAIEX"):
    target = date(2026, 6, 21)
    dates = [date(2026, 6, 1) + timedelta(days=index) for index in range(21)]
    index_rows = []
    market_rows = []
    price_rows = []
    for index, current in enumerate(dates):
        if not (omit_first_index_date and index == 0):
            index_rows.extend(
                [
                    {"日期": current.strftime("%Y%m%d"), "指數名稱": "半導體類指數", "收盤指數": str(100 + index * 2)},
                    {"日期": current.strftime("%Y%m%d"), "指數名稱": "水泥類指數", "收盤指數": str(100 + index)},
                    {"日期": current.strftime("%Y%m%d"), "指數名稱": "電子類兩倍槓桿指數", "收盤指數": str(100 + index * 4)},
                ]
            )
        market_rows.append(
            {"日期": current.strftime("%Y%m%d"), "指數名稱": benchmark_name, "收盤指數": str(100 + index)}
        )
        price_rows.extend(
            [
                {"日期": current.strftime("%Y%m%d"), "證券代號": "2330", "證券名稱": "台積電", "收盤價": str(100 + index * 3)},
                {"日期": current.strftime("%Y%m%d"), "證券代號": "2317", "證券名稱": "鴻海", "收盤價": str(100 + index * 2)},
                {"日期": current.strftime("%Y%m%d"), "證券代號": "1101", "證券名稱": "台泥", "收盤價": str(100 + index)},
            ]
        )
    companies = pd.DataFrame(
        [
            {"industry_category": "半導體業", "stock_id": "2330", "stock_name": "台積電", "type": "twse", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "半導體業", "stock_id": "2330", "stock_name": "台積電", "type": "twse", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "半導體業", "stock_id": "2317", "stock_name": "鴻海", "type": "tpex", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "水泥工業", "stock_id": "1101", "stock_name": "台泥", "type": "twse", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "存託憑證", "stock_id": "9900", "stock_name": "存託憑證", "type": "tpex", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "半導體業", "stock_id": "9999", "stock_name": "歧義股", "type": "twse", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
            {"industry_category": "金融保險", "stock_id": "9999", "stock_name": "歧義股", "type": "twse", "date": "2026-06-01", "download_time": "2026-06-01 08:00:00"},
        ]
    )
    return target, IndustryStrengthData(
        industry_indices=pd.DataFrame(index_rows),
        market_indices=pd.DataFrame(market_rows),
        daily_prices=pd.DataFrame(price_rows),
        companies=companies,
        mapping_observed_date=date(2026, 6, 1),
        mapping_available_at="2026-06-01T08:00:00+08:00",
    )


def test_industry_strength_excludes_proxy_indexes_and_keeps_parent_levels_explicit():
    assert is_usable_industry_index_name("半導體類指數") is True
    assert is_usable_industry_index_name("電子類兩倍槓桿指數") is False
    assert is_usable_industry_index_name("金融類日報酬反向一倍指數") is False
    assert is_usable_industry_index_name("半導體類報酬指數") is False
    assert industry_level("電子工業類指數") == "aggregate"
    assert industry_level("電子零組件類指數") == "leaf"


def test_industry_strength_uses_market_sessions_without_stretching_missing_index_endpoint():
    target, data = _industry_strength_data(omit_first_index_date=True)
    service = IndustryStrengthService(
        provider=_IndustryStrengthProvider(data, target)
    )

    summary = service.build_industry_strength(target)
    semiconductor = next(row for row in summary.rows if row.industry_name == "半導體業")

    assert summary.as_of_date == target
    assert semiconductor.return_5d_bp is not None
    assert semiconductor.return_20d_bp is None
    assert semiconductor.rank_20d is None
    assert "industry_index_insufficient_window:20d" in semiconductor.warnings


def test_industry_strength_aligns_coverage_to_twse_and_reports_mapping_gaps():
    target, data = _industry_strength_data()
    service = IndustryStrengthService(
        provider=_IndustryStrengthProvider(data, target)
    )

    summary = service.build_industry_strength(target)
    semiconductor = next(row for row in summary.rows if row.industry_name == "半導體業")

    assert semiconductor.market_scope == "twse"
    assert semiconductor.constituent_count == 1
    assert semiconductor.eligible_stock_count_20d == 1
    assert semiconductor.coverage_20d_bp == 10000
    assert [item.stock_code for item in semiconductor.representative_stocks] == ["2330"]
    assert "2317" not in [item.stock_code for item in semiconductor.representative_stocks]
    assert "存託憑證" in summary.unmapped_industry_categories
    assert "2330" in summary.duplicate_membership_codes
    assert "9999" in summary.ambiguous_membership_codes
    assert "industry_mapping_market_scope_exclusions:1" in summary.warnings
    assert summary.coverage["mapping_unambiguous_mapped_code_count"] == 2


def test_industry_strength_requires_taiex_and_does_not_fabricate_relative_rankings():
    target, data = _industry_strength_data(benchmark_name="OTHER_INDEX")
    service = IndustryStrengthService(
        provider=_IndustryStrengthProvider(data, target)
    )

    summary = service.build_industry_strength(target)
    result = service.build_screening_result(
        direction="strong", period="week", top_n=10, decision_date=target
    )

    assert summary.as_of_date is None
    assert summary.rows == ()
    assert any(item.startswith("benchmark_name_missing:TAIEX") for item in summary.warnings)
    assert result.rows == ()
    assert "industry_strength_no_rankable_industries" in result.warnings


def test_industry_strength_ignores_future_observations_and_unknown_mapping_is_not_historical():
    target, data = _industry_strength_data()
    future = target + timedelta(days=1)
    data = replace(
        data,
        market_indices=pd.concat(
            [
                data.market_indices,
                pd.DataFrame([{"日期": future.strftime("%Y%m%d"), "指數名稱": "TAIEX", "收盤指數": "999"}]),
            ],
            ignore_index=True,
        ),
        industry_indices=pd.concat(
            [
                data.industry_indices,
                pd.DataFrame([{"日期": future.strftime("%Y%m%d"), "指數名稱": "半導體類指數", "收盤指數": "999"}]),
            ],
            ignore_index=True,
        ),
    )
    service = IndustryStrengthService(
        provider=_IndustryStrengthProvider(data, target + timedelta(days=1))
    )

    summary = service.build_industry_strength(target)

    assert summary.as_of_date == target
    assert all(row.index_close != "999" for row in summary.rows)

    data = replace(data, mapping_available_at=None)
    historical_service = IndustryStrengthService(
        provider=_IndustryStrengthProvider(data, target + timedelta(days=1))
    )
    historical = historical_service.build_industry_strength(target - timedelta(days=1))
    assert historical.rows == ()
    assert "industry_mapping_not_available_at_as_of" in historical.warnings
