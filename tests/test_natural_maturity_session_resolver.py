from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
import json
import os
from pathlib import Path
import sqlite3

import pytest

from data_module.natural_maturity_session_resolver import (
    MAX_CACHE_CANDIDATES,
    NaturalMaturitySessionResolver,
    _hash_payload,
    verify_session_proof,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


CAPTURE = "2026-09-01"
# 16:00 Asia/Taipei on 9/9；9/10 row 即使存在也尚未進入可見 bounded source。
EVALUATION = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
SESSION_DATES = ("20260901", "20260902", "20260903", "20260904", "20260907", "20260908")


def _write_calendar(
    root: Path,
    *,
    captured_at: datetime,
    calendar_year: int = 2026,
    filename: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "中華民國開國紀念日",
                "Date": f"{calendar_year - 1911:03d}0101",
                "Weekday": "四",
                "Description": "依規定放假1日。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=calendar_year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
    )
    path = root / (
        filename
        or f"twse_holiday_schedule_{calendar_year}_test.json"
    )
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path


def _write_db(path: Path, dates: tuple[str, ...]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            'CREATE TABLE market_indices ("日期" TEXT, "指數名稱" TEXT, '
            '"收盤指數" TEXT, "收盤價" TEXT)'
        )
        for index, compact in enumerate(dates, start=1):
            connection.execute(
                'INSERT INTO market_indices ("日期", "指數名稱", "收盤指數", "收盤價") '
                "VALUES (?, ?, ?, ?)",
                (compact, "TAIEX", str(20_000 + index), str(20_000 + index)),
            )
    # fixture 可覆蓋正式 compact 與 resolver 支援的 ISO 日期形狀。
    assert all(len(value) in {8, 10} for value in dates)


def _resolver(tmp_path: Path, *, dates: tuple[str, ...]) -> NaturalMaturitySessionResolver:
    db_path = tmp_path / "twstock.db"
    _write_db(db_path, dates)
    calendar_path = _write_calendar(
        tmp_path / "calendar",
        captured_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    return NaturalMaturitySessionResolver(db_path, calendar_path.parent)


def _cross_year_resolver(
    tmp_path: Path,
    *,
    dates: tuple[str, ...],
) -> NaturalMaturitySessionResolver:
    db_path = tmp_path / "twstock.db"
    _write_db(db_path, dates)
    calendar_root = tmp_path / "calendar"
    captured_at = datetime(2026, 1, 19, tzinfo=timezone.utc)
    for year in (2025, 2026):
        _write_calendar(
            calendar_root,
            captured_at=captured_at,
            calendar_year=year,
        )
    return NaturalMaturitySessionResolver(db_path, calendar_root)


@pytest.mark.parametrize(
    "date_format",
    ("compact", "iso"),
)
def test_cross_year_bounded_query_excludes_prior_row_for_both_date_formats(
    tmp_path: Path,
    date_format: str,
) -> None:
    capture = date(2025, 12, 15)
    future_days = (
        date(2025, 12, 16),
        date(2025, 12, 17),
        date(2025, 12, 18),
        date(2025, 12, 19),
        date(2025, 12, 22),
        date(2025, 12, 23),
        date(2025, 12, 24),
        date(2025, 12, 25),
        date(2025, 12, 26),
        date(2025, 12, 29),
        date(2025, 12, 30),
        date(2025, 12, 31),
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
    )
    dates = (date(2025, 12, 1), capture, *future_days)
    values = tuple(
        day.strftime("%Y%m%d") if date_format == "compact" else day.isoformat()
        for day in dates
    )
    resolver = _cross_year_resolver(tmp_path, dates=values)

    result = resolver.resolve(
        capture.isoformat(),
        datetime(2026, 1, 20, 8, 0, tzinfo=timezone.utc),
        horizon_sessions=20,
    )

    assert result.status == "ready"
    assert result.endpoint_date == "2026-01-13"
    assert result.session_dates == tuple(day.isoformat() for day in future_days)
    assert result.proof is not None
    assert result.proof["market"]["baseline_observation"]["date"] == capture.isoformat()
    assert [
        item["date"] for item in result.proof["market"]["observations"]
    ] == list(result.session_dates)
    verified = verify_session_proof(
        result.proof,
        capture.isoformat(),
        result.endpoint_date,
        datetime(2026, 1, 20, 8, 0, tzinfo=timezone.utc),
        expected_db_path=tmp_path / "twstock.db",
    )
    assert verified["proof_hash"] == result.proof["proof_hash"]


def test_ready_resolution_has_exact_sessions_baseline_and_reverified_proof(
    tmp_path: Path,
) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)

    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)

    assert result.status == "ready"
    assert result.endpoint_date == "2026-09-08"
    assert result.session_dates == (
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",
        "2026-09-07",
        "2026-09-08",
    )
    assert result.proof is not None
    market = result.proof["market"]
    assert market["baseline_observation"]["date"] == CAPTURE
    assert market["query_range"]["start_date"] == CAPTURE
    assert market["query_range"]["end_date"] == "2026-09-09"

    verified = verify_session_proof(
        result.proof,
        CAPTURE,
        "2026-09-08",
        EVALUATION,
        expected_db_path=tmp_path / "twstock.db",
    )
    assert verified["proof_hash"] == result.proof["proof_hash"]


def test_proof_reread_rejects_changed_bounded_market_row(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)
    assert result.proof is not None

    with sqlite3.connect(tmp_path / "twstock.db") as connection:
        connection.execute(
            'UPDATE market_indices SET "收盤指數" = ?, "收盤價" = ? '
            'WHERE "日期" = ? AND "指數名稱" = ?',
            ("99999", "99999", "20260904", "TAIEX"),
        )

    with pytest.raises(ValueError, match="bounded market hash|planned market rows"):
        verify_session_proof(
            result.proof,
            CAPTURE,
            "2026-09-08",
            EVALUATION,
            expected_db_path=tmp_path / "twstock.db",
        )


def test_rehashed_forged_market_proof_still_requires_source_rows(
    tmp_path: Path,
) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)
    assert result.proof is not None
    forged = copy.deepcopy(result.proof)
    forged_row = forged["market"]["observations"][0]
    forged_row["close"] = "99999"
    forged_row["close_index"] = "99999"
    forged_row["close_price"] = "99999"
    forged_row["row_hash"] = _hash_payload(
        {
            "source_table": "market_indices",
            "index_name": "TAIEX",
            "date": forged_row["date"],
            "close_index": forged_row["close_index"],
            "close_price": forged_row["close_price"],
            "close": forged_row["close"],
            "available_at": forged_row["available_at"],
        }
    )
    forged["market"]["observations_hash"] = _hash_payload(
        {"row_hashes": [
            item["row_hash"] for item in forged["market"]["observations"]
        ]}
    )
    forged["proof_hash"] = _hash_payload(
        {key: value for key, value in forged.items() if key != "proof_hash"}
    )

    with pytest.raises(ValueError, match="bounded market hash|planned market rows"):
        verify_session_proof(
            forged,
            CAPTURE,
            "2026-09-08",
            EVALUATION,
            expected_db_path=tmp_path / "twstock.db",
        )


def test_future_market_rows_are_outside_evaluation_bound(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    with sqlite3.connect(tmp_path / "twstock.db") as connection:
        connection.execute(
            'INSERT INTO market_indices ("日期", "指數名稱", "收盤指數", "收盤價") '
            "VALUES (?, ?, ?, ?)",
            ("20260910", "TAIEX", "-1", "-1"),
        )

    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)

    assert result.status == "ready"
    assert result.proof["market"]["query_range"]["end_date"] == "2026-09-09"


def test_before_close_same_day_row_is_not_visible_to_prior_endpoint(
    tmp_path: Path,
) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    with sqlite3.connect(tmp_path / "twstock.db") as connection:
        connection.execute(
            'INSERT INTO market_indices ("日期", "指數名稱", "收盤指數", "收盤價") '
            "VALUES (?, ?, ?, ?)",
            ("20260909", "TAIEX", "-1", "-1"),
        )

    early_evaluation = datetime(2026, 9, 9, 5, 0, tzinfo=timezone.utc)
    result = resolver.resolve(CAPTURE, early_evaluation, horizon_sessions=5)

    assert result.status == "ready"
    assert result.proof["market"]["query_range"]["end_date"] == "2026-09-08"


def test_proof_revalidates_annual_cache_bytes(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)
    assert result.proof is not None
    cache_path = Path(result.proof["calendar"]["annual_sources"][0]["evidence"]["path"])
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    cache_payload["raw_response_base64"] = "W10="
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="annual cache revalidation failed"):
        verify_session_proof(
            result.proof,
            CAPTURE,
            "2026-09-08",
            EVALUATION,
            expected_db_path=tmp_path / "twstock.db",
        )


def test_missing_middle_session_does_not_shift_endpoint(tmp_path: Path) -> None:
    resolver = _resolver(
        tmp_path,
        dates=("20260901", "20260902", "20260903", "20260907", "20260908"),
    )

    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)

    assert result.status == "pending"
    assert result.endpoint_date is None
    assert "2026-09-04" in result.missing_session_dates


def test_weekend_market_row_is_calendar_market_conflict(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES + ("20260906",))

    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)

    assert result.status == "pending"
    assert result.reason == "calendar_market_session_conflict:2026-09-06"


def test_same_resolver_does_not_reuse_expired_calendar(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, dates=SESSION_DATES)
    assert resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5).status == "ready"

    expired_evaluation = datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)
    result = resolver.resolve(CAPTURE, expired_evaluation, horizon_sessions=5)

    assert result.status == "waiting_for_calendar"
    assert "freshness window expired" in result.reason


def test_annual_candidate_bound_keeps_newest_valid_cache_after_old_files_accumulate(
    tmp_path: Path,
) -> None:
    """舊 immutable 批次超過 bounded 上限時仍能找到最新有效 cache。"""

    db_path = tmp_path / "twstock.db"
    _write_db(db_path, dates=SESSION_DATES)
    calendar_root = tmp_path / "calendar"
    expired_capture = datetime(2026, 7, 1, tzinfo=timezone.utc)
    old_paths: list[Path] = []
    for index in range(MAX_CACHE_CANDIDATES):
        old_paths.append(
            _write_calendar(
                calendar_root,
                captured_at=expired_capture + timedelta(minutes=index),
                filename=(
                    f"twse_holiday_schedule_2026_old_{index:03d}.json"
                ),
            )
        )
    newest_path = _write_calendar(
        calendar_root,
        captured_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        filename="twse_holiday_schedule_2026_z_new.json",
    )

    # 讓 bounded discovery 的排序證據 deterministic；authority 仍使用
    # cache 內經重驗的 captured_at，而不是檔案 mtime。
    base_mtime_ns = 1_700_000_000_000_000_000
    for index, path in enumerate(old_paths):
        os.utime(path, ns=(base_mtime_ns + index, base_mtime_ns + index))
    os.utime(
        newest_path,
        ns=(base_mtime_ns + MAX_CACHE_CANDIDATES + 1,
            base_mtime_ns + MAX_CACHE_CANDIDATES + 1),
    )

    resolver = NaturalMaturitySessionResolver(db_path, calendar_root)
    candidates = resolver._annual_candidates(2026)
    assert len(candidates) == MAX_CACHE_CANDIDATES
    assert newest_path.resolve() in candidates
    result = resolver.resolve(CAPTURE, EVALUATION, horizon_sessions=5)

    assert result.status == "ready"
    assert result.endpoint_date == "2026-09-08"
    assert result.proof is not None
    annual_sources = result.proof["calendar"]["annual_sources"]
    assert len(annual_sources) == 1
    assert Path(annual_sources[0]["evidence"]["path"]) == newest_path.resolve()
    verified = verify_session_proof(
        result.proof,
        CAPTURE,
        result.endpoint_date,
        EVALUATION,
        expected_db_path=db_path,
    )
    assert verified["proof_hash"] == result.proof["proof_hash"]
