from __future__ import annotations

import csv
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

import data_module.ml_daily_price_source_quality as quality_module
import data_module.ml_pit_year_shard_exporter as pit_exporter_module
from data_module.ml_daily_price_source_quality import (
    DailyPriceSourceQualityError,
    assert_daily_price_source_quality,
    audit_daily_price_source,
    write_quarantine_report,
)
from data_module.ml_pit_year_shard_exporter import (
    PITYearShardBuildRequest,
    PITYearShardExporter,
)


_CSV_COLUMNS = (
    "證券代號",
    "證券名稱",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "成交股數",
)


def _build_database(
    path: Path,
    *,
    current_open: str,
    current_close: str,
    current_high: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("20260519", "3017", "奇鋐", "100", "105", "95", "100", 1000),
                (
                    "20260520",
                    "3017",
                    "奇鋐",
                    current_open,
                    current_open if current_high is None else current_high,
                    current_open,
                    current_close,
                    1000,
                ),
                ("20260521", "3017", "奇鋐", "120", "125", "115", "120", 1000),
            ),
        )


def _build_single_daily_price_database(
    path: Path,
    *,
    symbol: str = "0058",
    date_key: str = "20260520",
    name: str = "測試標的",
    open_value: object = None,
    high_value: object = None,
    low_value: object = None,
    close_value: object = None,
    volume: object = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                date_key,
                symbol,
                name,
                open_value,
                high_value,
                low_value,
                close_value,
                volume,
            ),
        )


def _write_csv(
    directory: Path,
    *,
    current_open: str,
    current_close: str,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "20260520.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        high = max(Decimal(current_open), Decimal(current_close))
        low = min(Decimal(current_open), Decimal(current_close))
        writer.writerow(
            {
                "證券代號": "3017",
                "證券名稱": "奇鋐",
                "開盤價": current_open,
                "最高價": format(high, "f"),
                "最低價": format(low, "f"),
                "收盤價": current_close,
                "成交股數": "1,000",
            }
        )
    return path


def _write_single_market_csv(
    directory: Path,
    *,
    symbol: str,
    current_open: str,
    current_high: str,
    current_low: str,
    current_close: str,
    volume: str = "1,000",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "20260520.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "證券代號": symbol,
                "證券名稱": symbol,
                "開盤價": current_open,
                "最高價": current_high,
                "最低價": current_low,
                "收盤價": current_close,
                "成交股數": volume,
            }
        )
    return path


def _write_raw_market_csv(
    directory: Path,
    *,
    symbol: str,
    date_key: str = "20260520",
    open_value: str,
    high_value: str,
    low_value: str,
    close_value: str,
    volume: str = "1,000",
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date_key}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "證券代號": symbol,
                "證券名稱": symbol,
                "開盤價": open_value,
                "最高價": high_value,
                "最低價": low_value,
                "收盤價": close_value,
                "成交股數": volume,
            }
        )
    return path


def test_source_mismatch_is_quarantined_without_source_write(tmp_path: Path) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="5", current_close="5")
    canonical = _write_csv(
        csv_root,
        current_open="95",
        current_close="96",
    )
    before = database.read_bytes()

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
    )

    assert report["status"] == "quarantine_required"
    assert report["candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["classification"] == (
        "sqlite_row_mismatch_against_canonical_daily_csv"
    )
    assert set(candidate["differing_fields"]) >= {"open", "close"}
    assert candidate["canonical_file"]["file_sha256"].startswith("sha256:")
    assert candidate["canonical_file"]["path"] == str(canonical.resolve())
    assert report["labels_mutated"] is False
    assert report["quality_timing"]["quality_mode"] == "retrospective_audit"
    assert report["quality_timing"]["uses_future_source_rows"] is True
    assert database.read_bytes() == before

    with pytest.raises(DailyPriceSourceQualityError):
        assert_daily_price_source_quality(
            sqlite_path=database,
            canonical_daily_price_dir=csv_root,
            start_date="2026-05-20",
            end_date="2026-05-20",
        )


def test_decimal_equivalent_price_formatting_is_not_a_mismatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(
        database,
        current_open="990.0",
        current_close="990.0",
        current_high="990.0",
    )
    _write_csv(csv_root, current_open="990.00", current_close="990.00")

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
    )

    assert report["status"] == "source_quality_pass"
    assert report["candidate_count"] == 0


def test_candidate_sample_limit_bounds_evidence_without_losing_counts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="5", current_close="5")
    _write_csv(csv_root, current_open="95", current_close="96")

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
        candidate_sample_limit=0,
    )

    assert report["candidate_count"] == 1
    assert report["classification_counts"] == {
        "both_sources_one_sided_scale_discontinuity_requires_quarantine": 1
    }
    assert report["affected_date_counts"] == {"2026-05-20": 1}
    assert report["candidates"] == []
    assert report["candidate_sample_limit"] == 0
    assert report["candidate_samples_truncated"] is True


def test_full_candidate_sidecar_streams_rows_beyond_report_sample_limit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    rows = [
        ("20260520", f"{3000 + index:04d}", "測試標的", "5", "5", "5", "5", 1000)
        for index in range(70)
    ]
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    csv_root.mkdir(parents=True, exist_ok=True)
    csv_path = csv_root / "20260520.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for _date, symbol, name, *_rest in rows:
            writer.writerow(
                {
                    "證券代號": symbol,
                    "證券名稱": name,
                    "開盤價": "95",
                    "最高價": "96",
                    "最低價": "94",
                    "收盤價": "96",
                    "成交股數": "1,000",
                }
            )
    before = database.read_bytes()
    sidecar = tmp_path / "qa" / "source.candidates.jsonl"

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
        candidate_sample_limit=64,
        candidate_evidence_path=sidecar,
    )

    evidence = report["candidate_evidence"]
    assert report["candidate_count"] == 70
    assert report["candidate_sample_count"] == 64
    assert report["candidate_samples_truncated"] is True
    assert evidence["complete"] is True
    assert evidence["row_count"] == 70
    assert evidence["unique_key_count"] == 70
    assert evidence["candidate_digest"] == report["candidate_digest"]
    assert sidecar.is_file()
    assert database.read_bytes() == before


def test_ingest_guard_routes_each_symbol_to_its_declared_market_source(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("20260520", "2330", "台積電", "990.0", "995.0", "985.0", "992.0", 1000),
                ("20260520", "6488", "環球晶", "990.0", "995.0", "985.0", "992.0", 1000),
            ),
        )
    twse_file = _write_single_market_csv(
        twse,
        symbol="2330",
        current_open="990.00",
        current_high="995.00",
        current_low="985.00",
        current_close="992.00",
    )
    tpex_file = _write_single_market_csv(
        tpex,
        symbol="6488",
        current_open="990.00",
        current_high="995.00",
        current_low="985.00",
        current_close="992.00",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=twse,
        canonical_daily_price_dirs=(tpex,),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("2330", "6488"),
        quality_mode="ingest_guard",
    )

    assert report["status"] == "source_quality_pass"
    assert report["source"]["canonical_daily_price_dirs"] == [
        str(twse.resolve()),
        str(tpex.resolve()),
    ]
    assert report["source"]["canonical_source_markets"] == {
        str(twse.resolve()): "TWSE",
        str(tpex.resolve()): "TPEX",
    }
    assert report["source"]["route_status_counts"] == {
        "selected": 2,
        "missing": 0,
        "ambiguous": 0,
        "conflict": 0,
    }
    assert report["source"]["route_selected_by_source"] == {
        str(twse.resolve() / "20260520.csv"): 1,
        str(tpex.resolve() / "20260520.csv"): 1,
    }
    assert {
        (sample["symbol"], sample["market"])
        for sample in report["source"]["route_selected_samples"]
    } == {("2330", "TWSE"), ("6488", "TPEX")}
    assert twse_file.is_file()
    assert tpex_file.is_file()


def test_duplicate_symbol_conflict_across_market_sources_is_quarantined(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _build_database(database, current_open="95.0", current_close="96.0")
    _write_single_market_csv(
        twse,
        symbol="3017",
        current_open="95.00",
        current_high="96.00",
        current_low="95.00",
        current_close="96.00",
    )
    _write_single_market_csv(
        tpex,
        symbol="3017",
        current_open="195.00",
        current_high="196.00",
        current_low="195.00",
        current_close="196.00",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dirs=(twse, tpex),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("3017",),
        quality_mode="ingest_guard",
    )

    assert report["classification_counts"] == {
        "canonical_daily_symbol_conflict_across_markets": 1
    }
    candidate = report["candidates"][0]
    assert candidate["canonical_row"] is None
    assert len(candidate["canonical_candidates"]) == 2
    assert {
        item["file"]["market"] for item in candidate["canonical_candidates"]
    } == {"TWSE", "TPEX"}
    assert candidate["differing_fields"] == []


def test_duplicate_symbol_equal_across_market_sources_is_ambiguous(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _build_database(database, current_open="95.0", current_close="96.0")
    for directory in (twse, tpex):
        _write_single_market_csv(
            directory,
            symbol="3017",
            current_open="95.00",
            current_high="96.00",
            current_low="95.00",
            current_close="96.00",
        )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dirs=(twse, tpex),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("3017",),
        quality_mode="ingest_guard",
    )

    assert report["classification_counts"] == {
        "canonical_daily_symbol_ambiguous_across_markets": 1
    }
    assert report["source"]["route_status_counts"] == {
        "selected": 0,
        "missing": 0,
        "ambiguous": 1,
        "conflict": 0,
    }
    candidate = report["candidates"][0]
    assert candidate["canonical_row"] is None
    assert {
        item["file"]["market"] for item in candidate["canonical_candidates"]
    } == {"TWSE", "TPEX"}


def test_route_map_is_reused_for_repeated_same_date_lookups(
    tmp_path: Path,
) -> None:
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _write_single_market_csv(
        twse,
        symbol="2330",
        current_open="990.00",
        current_high="995.00",
        current_low="985.00",
        current_close="992.00",
    )
    _write_single_market_csv(
        tpex,
        symbol="6488",
        current_open="990.00",
        current_high="995.00",
        current_low="985.00",
        current_close="992.00",
    )
    csv_cache: dict[object, object] = {}
    route_cache: dict[object, object] = {}

    first = quality_module._canonical_rows_for_date(
        "20260520",
        source_dirs=(twse.resolve(), tpex.resolve()),
        csv_cache=csv_cache,  # type: ignore[arg-type]
        route_cache=route_cache,  # type: ignore[arg-type]
    )
    second = quality_module._canonical_rows_for_date(
        "20260520",
        source_dirs=(twse.resolve(), tpex.resolve()),
        csv_cache=csv_cache,  # type: ignore[arg-type]
        route_cache=route_cache,  # type: ignore[arg-type]
    )

    assert first is second
    assert len(route_cache) == 1


def test_route_and_csv_caches_evict_old_dates_together(tmp_path: Path) -> None:
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    twse.mkdir()
    tpex.mkdir()
    csv_cache: dict[object, object] = {}
    route_cache: dict[object, object] = {}

    for day in range(1, 13):
        quality_module._canonical_rows_for_date(
            f"202601{day:02d}",
            source_dirs=(twse.resolve(), tpex.resolve()),
            csv_cache=csv_cache,  # type: ignore[arg-type]
            route_cache=route_cache,  # type: ignore[arg-type]
        )

    assert len(route_cache) == 8
    assert len(csv_cache) == 16
    assert {
        key[1] for key in csv_cache if isinstance(key, tuple)
    } == {f"202601{day:02d}" for day in range(5, 13)}


def test_canonical_raw_anomaly_is_quarantined_even_when_sqlite_matches(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="5", current_close="5")
    _write_csv(csv_root, current_open="5", current_close="5")

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
    )

    candidate = report["candidates"][0]
    assert candidate["classification"] == (
        "canonical_daily_row_has_scale_discontinuity"
    )
    assert candidate["differing_fields"] == []
    assert report["formal_training_allowed"] is False


def test_ingest_guard_never_reads_late_next_source_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="5", current_close="5")
    _write_csv(csv_root, current_open="95", current_close="96")
    original_reader = quality_module._canonical_csv_rows
    observed_paths: list[str] = []

    def recording_reader(path: Path):
        observed_paths.append(path.name)
        return original_reader(path)

    monkeypatch.setattr(quality_module, "_canonical_csv_rows", recording_reader)
    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
    )

    assert report["status"] == "quarantine_required"
    assert report["quality_timing"] == {
        "quality_mode": "ingest_guard",
        "uses_future_source_rows": False,
        "future_source_row_used": False,
        "quality_known_at": None,
        "quality_known_at_status": "source_receipt_time_not_supplied",
        "historical_retroactive_filtering_allowed": False,
    }
    assert "20260521.csv" not in observed_paths
    candidate = report["candidates"][0]
    assert candidate["detector"]["next_open"] is None
    assert candidate["detector"]["future_source_row_used"] is False
    assert candidate["canonical_context"]["next"] is None
    assert candidate["canonical_context"]["next_file"] is None


def test_ingest_guard_uses_actual_previous_observation_for_canonical_scale(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交股數 INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ("20260523", "3017", "奇鋐", "10", "10", "10", "10", 1000),
                ("20260525", "3017", "奇鋐", "5", "5", "5", "5", 1000),
            ),
        )
    _write_raw_market_csv(
        csv_root,
        symbol="3017",
        date_key="20260523",
        open_value="90",
        high_value="100",
        low_value="90",
        close_value="100",
    )
    _write_raw_market_csv(
        csv_root,
        symbol="3017",
        date_key="20260525",
        open_value="5",
        high_value="5",
        low_value="5",
        close_value="5",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-25",
        end_date="2026-05-25",
        quality_mode="ingest_guard",
    )

    assert report["candidate_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["classification"] == (
        "canonical_daily_row_has_one_sided_scale_discontinuity"
    )
    assert candidate["detector"]["previous_observation_date"] == "2026-05-23"
    assert candidate["canonical_context"]["previous_date"] == "2026-05-23"
    assert candidate["canonical_context"]["previous"]["close"] == "100"
    assert candidate["canonical_context"]["previous_file"]["path"].endswith(
        "20260523.csv"
    )


def test_ingest_guard_quarantines_null_sqlite_row_without_silent_drop(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="95", current_close="96")
    _write_csv(csv_root, current_open="95", current_close="96")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE daily_prices SET 開盤價 = NULL WHERE 日期 = ?",
            ("20260520",),
        )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
    )

    assert report["status"] == "quarantine_required"
    assert report["candidate_count"] == 1
    assert report["research_price_unavailable_count"] == 0
    assert report["research_price_invalid_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["classification"] == (
        "sqlite_row_missing_price_against_canonical_daily_csv"
    )
    assert candidate["sqlite_row"]["open"] is None
    assert candidate["canonical_row"]["open"] == "95"
    assert candidate["detector"]["future_source_row_used"] is False
    assert candidate["research_contract"]["status"] == "price_unavailable"
    assert candidate["research_contract"]["raw_row"] == candidate["sqlite_row"]
    assert candidate["research_contract"]["missing_mask"]["open"] is True
    assert candidate["research_contract"]["affected_window"][
        "surrounding_rows_may_not_be_bridged"
    ] is True
    assert candidate["research_contract"]["disposition"]["zero_fill"] is False
    assert candidate["research_contract"]["disposition"][
        "source_quality_research_eligible"
    ] is False


def test_ingest_guard_binds_unique_invalid_source_to_second_market_root(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _build_single_daily_price_database(database)
    _write_single_market_csv(
        twse,
        symbol="2330",
        current_open="990.00",
        current_high="995.00",
        current_low="985.00",
        current_close="992.00",
    )
    tpex_file = _write_raw_market_csv(
        tpex,
        symbol="0058",
        open_value="",
        high_value="",
        low_value="",
        close_value="",
        volume="0",
    )
    before = database.read_bytes()

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dirs=(twse, tpex),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("0058",),
        quality_mode="ingest_guard",
    )

    assert report["candidate_count"] == 1
    assert report["research_price_unavailable_count"] == 1
    assert report["research_price_invalid_count"] == 0
    assert report["source"]["route_status_counts"] == {
        "selected": 0,
        "missing": 1,
        "ambiguous": 0,
        "conflict": 0,
    }
    candidate = report["candidates"][0]
    assert candidate["classification"] == "sqlite_row_invalid_requires_quarantine"
    assert candidate["canonical_row"] is None
    assert candidate["canonical_file"]["path"] == str(tpex_file.resolve())
    assert candidate["canonical_file"]["file_sha256"] == quality_module._file_sha256(
        tpex_file
    )
    assert len(candidate["canonical_invalid_candidates"]) == 1
    assert candidate["canonical_invalid_candidates"][0]["file"]["path"] == str(
        tpex_file.resolve()
    )
    contract = candidate["research_contract"]
    assert contract["source_file"] == candidate["canonical_file"]
    assert contract["disposition"] == {
        "research_only": True,
        "include_price_feature_row": False,
        "include_price_label_row": False,
        "preserve_source_row": True,
        "zero_fill": False,
        "drop_source_row": False,
        "require_official_cause": False,
        "source_quality_research_eligible": True,
        "source_quality_disposition": "price_unavailable_missing_or_marker",
    }
    assert contract["missing_mask"] == {
        "open": True,
        "high": True,
        "low": True,
        "close": True,
    }
    assert contract["affected_window"] == {
        "feature_window_dates": ["2026-05-20"],
        "label_window_dates": [],
        "affected_dates": ["2026-05-20"],
        "window_scope": "anchor_only",
        "feature_window_complete": False,
        "label_window_complete": False,
        "horizon_expansion_required": True,
        "adjacency_break_at_anchor": True,
        "surrounding_rows_may_not_be_bridged": True,
    }
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    ("left", "right"),
    (
        (None, ""),
        ("-", "--"),
        ("N/A", "na"),
        ("None", "null"),
        ("—", "–"),
        ("―", "−"),
        ("－", "﹘"),
        ("﹣", None),
    ),
)
def test_raw_field_equal_equates_explicit_missing_marker_variants(
    left: object,
    right: object,
) -> None:
    assert quality_module._raw_field_equal("open", left, right) is True
    assert quality_module._raw_field_equal("open", left, "95") is False


def test_ingest_guard_rejects_mixed_valid_and_invalid_duplicate_symbol(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _build_single_daily_price_database(database)
    _write_single_market_csv(
        twse,
        symbol="0058",
        current_open="95.00",
        current_high="96.00",
        current_low="94.00",
        current_close="95.50",
    )
    tpex_file = _write_raw_market_csv(
        tpex,
        symbol="0058",
        open_value="",
        high_value="",
        low_value="",
        close_value="",
        volume="0",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dirs=(twse, tpex),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("0058",),
        quality_mode="ingest_guard",
    )

    assert report["research_price_unavailable_count"] == 0
    assert report["research_price_invalid_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["canonical_file"]["path"] == str((twse / "20260520.csv").resolve())
    assert candidate["canonical_row"]["symbol"] == "0058"
    assert candidate["canonical_invalid_candidates"][0]["file"]["path"] == str(
        tpex_file.resolve()
    )
    assert candidate["research_contract"]["source_file"]["path"] == str(
        (twse / "20260520.csv").resolve()
    )
    assert candidate["research_contract"]["disposition"][
        "source_quality_research_eligible"
    ] is False
    assert candidate["research_contract"]["disposition"][
        "source_quality_disposition"
    ] == "canonical_price_evidence_not_identically_unavailable"


def test_ingest_guard_rejects_two_invalid_duplicate_symbols_without_guessing_file(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    twse = tmp_path / "daily_price"
    tpex = tmp_path / "daily_price_tpex"
    _build_single_daily_price_database(database)
    twse_file = _write_raw_market_csv(
        twse,
        symbol="0058",
        open_value="",
        high_value="",
        low_value="",
        close_value="",
        volume="0",
    )
    tpex_file = _write_raw_market_csv(
        tpex,
        symbol="0058",
        open_value="",
        high_value="",
        low_value="",
        close_value="",
        volume="0",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dirs=(twse, tpex),
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("0058",),
        quality_mode="ingest_guard",
    )

    assert report["research_price_unavailable_count"] == 0
    assert report["research_price_invalid_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["canonical_file"] is None
    assert candidate["canonical_raw_row"] is None
    assert {
        item["file"]["path"]
        for item in candidate["canonical_invalid_candidates"]
    } == {str(twse_file.resolve()), str(tpex_file.resolve())}
    assert candidate["research_contract"]["source_file"] is None
    assert candidate["research_contract"]["disposition"][
        "source_quality_research_eligible"
    ] is False


@pytest.mark.parametrize(
    ("case_name", "canonical_open", "canonical_high", "canonical_low", "canonical_close", "canonical_volume"),
    (
        ("canonical_nonnumeric", "not-a-number", "", "", "", "0"),
        ("volume_mismatch", "", "", "", "", "964"),
    ),
)
def test_ingest_guard_rejects_non_equivalent_canonical_missing_cases(
    tmp_path: Path,
    case_name: str,
    canonical_open: str,
    canonical_high: str,
    canonical_low: str,
    canonical_close: str,
    canonical_volume: str,
) -> None:
    database = tmp_path / "sqlite" / f"{case_name}.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_single_daily_price_database(database)
    _write_raw_market_csv(
        csv_root,
        symbol="0058",
        open_value=canonical_open,
        high_value=canonical_high,
        low_value=canonical_low,
        close_value=canonical_close,
        volume=canonical_volume,
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("0058",),
        quality_mode="ingest_guard",
    )

    assert report["status"] == "quarantine_required"
    assert report["research_price_unavailable_count"] == 0
    assert report["research_price_invalid_count"] == 1
    candidate = report["candidates"][0]
    assert candidate["classification"] == (
        "sqlite_row_missing_price_against_canonical_daily_csv"
    )
    assert candidate["research_contract"]["disposition"][
        "source_quality_research_eligible"
    ] is False
    assert candidate["research_contract"]["disposition"]["zero_fill"] is False


@pytest.mark.parametrize(
    ("open_value", "expected_classification"),
    (
        ("-95", "sqlite_row_mismatch_against_canonical_daily_csv"),
        ("not-a-number", "sqlite_row_missing_price_against_canonical_daily_csv"),
    ),
)
def test_ingest_guard_rejects_negative_or_nonnumeric_sqlite_price(
    tmp_path: Path,
    open_value: str,
    expected_classification: str,
) -> None:
    database = tmp_path / "sqlite" / f"sqlite_{open_value.replace('-', 'negative_')}.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_single_daily_price_database(
        database,
        open_value=open_value,
        high_value="96",
        low_value="94",
        close_value="95",
        volume=0,
    )
    _write_single_market_csv(
        csv_root,
        symbol="0058",
        current_open="95",
        current_high="96",
        current_low="94",
        current_close="95",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        symbols=("0058",),
        quality_mode="ingest_guard",
    )

    assert report["status"] == "quarantine_required"
    assert report["candidate_count"] == 1
    assert report["formal_training_allowed"] is False
    candidate = report["candidates"][0]
    assert candidate["classification"] == expected_classification
    assert candidate.get("research_contract") is None or candidate[
        "research_contract"
    ]["disposition"]["source_quality_research_eligible"] is False


def test_partial_canonical_price_row_cannot_use_missing_only_exception(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="95", current_close="96")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE daily_prices SET 最高價 = NULL WHERE 日期 = ?",
            ("20260520",),
        )
    _write_raw_market_csv(
        csv_root,
        symbol="3017",
        open_value="195",
        high_value="--",
        low_value="95",
        close_value="96",
    )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
        candidate_sample_limit=0,
    )

    assert report["candidate_count"] == 1
    assert report["research_price_unavailable_count"] == 0
    assert report["research_price_invalid_count"] == 1
    assert report["classification_counts"] == {
        "sqlite_row_missing_price_against_canonical_daily_csv": 1
    }
    assert report["candidates"] == []
    assert not pit_exporter_module._source_quality_is_price_unavailable_only(
        report
    )


def test_quality_known_at_requires_aware_receipt_time(tmp_path: Path) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(
        database,
        current_open="95",
        current_close="96",
        current_high="96",
    )
    _write_csv(csv_root, current_open="95", current_close="96")

    with pytest.raises(ValueError, match="timezone-aware"):
        audit_daily_price_source(
            sqlite_path=database,
            canonical_daily_price_dir=csv_root,
            start_date="2026-05-20",
            end_date="2026-05-20",
            quality_mode="ingest_guard",
            quality_known_at="2026-05-20T08:30:00",
        )

    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
        quality_mode="ingest_guard",
        quality_known_at="2026-05-20T08:30:00+08:00",
    )
    assert report["quality_timing"]["quality_known_at"] == (
        "2026-05-20T08:30:00+08:00"
    )


def test_clean_source_passes_and_quarantine_output_is_atomic(tmp_path: Path) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(
        database,
        current_open="95",
        current_close="96",
        current_high="96",
    )
    _write_csv(csv_root, current_open="95", current_close="96")

    report = assert_daily_price_source_quality(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
    )
    assert report["status"] == "source_quality_pass"
    output = tmp_path / "qa" / "source_quality.json"
    written = write_quarantine_report(
        output,
        report,
        source_roots=(database.parent, csv_root),
    )
    assert written == output.resolve()
    assert output.is_file()
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert write_quarantine_report(
        output,
        report,
        source_roots=(database.parent, csv_root),
    ) == output.resolve()


def test_candidate_evidence_jsonl_is_atomic_and_non_overwriting(
    tmp_path: Path,
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())
    writer.write(
        {
            "date": "2026-05-20",
            "symbol": "3017",
            "classification": "test",
        }
    )
    manifest = writer.finalize()
    before = output.read_bytes()

    with pytest.raises(FileExistsError):
        quality_module._CandidateEvidenceWriter(output, source_roots=())

    assert output.read_bytes() == before
    assert manifest["complete"] is True
    assert manifest["row_count"] == 1
    assert manifest["unique_key_count"] == 1
    assert manifest["file_sha256"].startswith("sha256:")


def test_candidate_evidence_writer_abort_leaves_no_partial_artifact(
    tmp_path: Path,
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())
    writer.write(
        {
            "date": "2026-05-20",
            "symbol": "3017",
            "classification": "test",
        }
    )
    writer.abort()

    assert not output.exists()
    assert not list(output.parent.glob(".*.tmp"))


def test_candidate_evidence_writer_flush_failure_closes_and_cleans_temp(
    tmp_path: Path,
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())
    inner_stream = writer._stream

    class _FlushFailingStream:
        def __init__(self, wrapped: object) -> None:
            self.wrapped = wrapped

        @property
        def closed(self) -> bool:
            return bool(getattr(self.wrapped, "closed"))

        def flush(self) -> None:
            raise OSError("injected_flush_failure")

        def close(self) -> None:
            self.wrapped.close()

    writer._stream = _FlushFailingStream(inner_stream)  # type: ignore[assignment]

    with pytest.raises(OSError, match="injected_flush_failure"):
        writer.finalize()

    assert not output.exists()
    assert inner_stream.closed
    assert not list(output.parent.glob(".*.tmp"))


def test_candidate_evidence_writer_fsync_failure_closes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())

    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("injected_fsync_failure")

    monkeypatch.setattr(quality_module.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected_fsync_failure"):
        writer.finalize()

    assert not output.exists()
    assert writer._stream.closed
    assert not list(output.parent.glob(".*.tmp"))


def test_candidate_evidence_writer_link_failure_closes_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected_link_failure")

    monkeypatch.setattr(quality_module.os, "link", fail_link)
    with pytest.raises(OSError, match="injected_link_failure"):
        writer.finalize()

    assert not output.exists()
    assert writer._stream.closed
    assert not list(output.parent.glob(".*.tmp"))


def test_candidate_evidence_writer_race_collision_preserves_existing_bytes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "qa" / "candidates.jsonl"
    writer = quality_module._CandidateEvidenceWriter(output, source_roots=())
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = b"existing-retry-artifact\n"
    output.write_bytes(existing)

    with pytest.raises(FileExistsError):
        writer.finalize()

    assert output.read_bytes() == existing
    assert writer._stream.closed
    assert not list(output.parent.glob(".*.tmp"))


def test_quarantine_report_cannot_overwrite_source_root(tmp_path: Path) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="95", current_close="96")
    _write_csv(csv_root, current_open="95", current_close="96")
    report = audit_daily_price_source(
        sqlite_path=database,
        canonical_daily_price_dir=csv_root,
        start_date="2026-05-20",
        end_date="2026-05-20",
    )

    with pytest.raises(ValueError, match="outside source roots"):
        write_quarantine_report(
            csv_root / "forbidden.json",
            report,
            source_roots=(database.parent, csv_root),
        )


@pytest.mark.usefixtures("synthetic_ml_capacity")
def test_pit_builder_runs_source_guard_before_creating_publication(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sqlite" / "source.sqlite"
    csv_root = tmp_path / "daily_price"
    _build_database(database, current_open="5", current_close="5")
    _write_csv(csv_root, current_open="95", current_close="96")
    output = tmp_path / "publication"

    with pytest.raises(DailyPriceSourceQualityError, match="quarantine required"):
        PITYearShardExporter().build(
            PITYearShardBuildRequest(
                database_path=database,
                output_root=output,
                decision_at="2026-05-21T08:30:00+08:00",
                history_start_date="2026-05-20",
                symbols=("3017",),
                years=(2026,),
                daily_price_source_dir=csv_root,
                source_quality_report_path=tmp_path / "qa" / "source.json",
            )
        )
    assert not output.exists()
    report_path = tmp_path / "qa" / "source.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["quality_timing"]["quality_mode"] == "ingest_guard"
    assert report["quality_timing"]["uses_future_source_rows"] is False
