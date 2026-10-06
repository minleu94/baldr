"""UX21 明示市場基準 adapter 的隔離資料庫與研究契約測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

import app_module.rule_research_benchmark_adapter as adapter_module
from app_module.rule_research_benchmark_adapter import (
    ExplicitBenchmarkRequest,
    load_explicit_market_benchmark,
)
from app_module.rule_research_forward_outcome import (
    Calendar,
    PricePoint,
    build_rule_research_forward_outcome,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    SAFETY_RESERVE_BYTES,
)
from tests import test_daily_market_snapshot_repository as snapshot_repository_tests
from tests import test_rule_research_sample_capture as sample_capture_tests


DECISION = "2025-01-02"
ENDPOINT = "2025-01-09"
AS_OF = "2025-01-10"
PRICE_BASIS = "unadjusted_close"
CORPORATE_ACTION_BASIS = "unadjusted"


def _seed_database(
    path: Path,
    rows: list[dict[str, object]],
    *,
    schema: str | None = None,
) -> Path:
    table_schema = schema or (
        'CREATE TABLE market_indices ('
        '"日期" TEXT NOT NULL, "指數名稱" TEXT NOT NULL, '
        '"收盤指數" REAL, "收盤價" REAL, "幣別" TEXT, "單位" TEXT, '
        '"價格基礎" TEXT, "公司行動基礎" TEXT, "可得日" TEXT)'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(table_schema)
        columns = tuple(rows[0]) if rows else ()
        if rows:
            quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f"INSERT INTO market_indices ({quoted}) VALUES ({placeholders})",
                [tuple(row.get(name) for name in columns) for row in rows],
            )
    return path


def _row(
    day: str,
    price: object = 10000,
    *,
    close_price: object | None = None,
    currency: str = "TWD",
    basis: str = PRICE_BASIS,
    corporate_action_basis: str = CORPORATE_ACTION_BASIS,
    available_date: str | None = None,
    name: str = "TAIEX",
) -> dict[str, object]:
    return {
        "日期": day,
        "指數名稱": name,
        "收盤指數": price,
        "收盤價": price if close_price is None else close_price,
        "幣別": currency,
        "單位": "index_points",
        "價格基礎": basis,
        "公司行動基礎": corporate_action_basis,
        "可得日": available_date or day.replace("/", "-")[:10],
    }


def _request(
    path: Path,
    *,
    endpoints: tuple[str, ...] = (DECISION, ENDPOINT),
    availability: dict[str, str | None] | None = None,
    **overrides: object,
) -> ExplicitBenchmarkRequest:
    values: dict[str, object] = {
        "database_path": path,
        "source_identity": "fixture.sqlite.market_indices.v1",
        "benchmark_name": "TAIEX",
        "decision_date": DECISION,
        "endpoint_dates": endpoints,
        "as_of_date": AS_OF,
        "currency": "TWD",
        "unit": "index_points",
        "price_basis": PRICE_BASIS,
        "corporate_action_basis": CORPORATE_ACTION_BASIS,
        "availability_by_date": availability or {day: day for day in endpoints},
        "target_currency": "TWD",
        "target_price_basis": PRICE_BASIS,
        "target_corporate_action_basis": CORPORATE_ACTION_BASIS,
    }
    values.update(overrides)
    return ExplicitBenchmarkRequest(**values)  # type: ignore[arg-type]


def _pin_then_load(request: ExplicitBenchmarkRequest):
    first = load_explicit_market_benchmark(request)
    if first.status != "unknown":
        return request, first
    assert first.benchmark is None and first.prices == ()
    assert first.observed_rowset_sha256
    assert first.observed_decision_row_sha256
    pinned = replace(
        request,
        expected_rowset_sha256=first.observed_rowset_sha256,
        expected_decision_row_sha256=first.observed_decision_row_sha256,
    )
    return pinned, load_explicit_market_benchmark(pinned)


def _assert_all_ineligible(result) -> None:
    assert result.historical_pit_eligible is False
    assert result.formal_eligible is False
    assert result.training_eligible is False
    assert result.trading_eligible is False
    assert result.execution_eligible is False
    assert result.natural_authority is False


def test_two_step_pins_yield_only_explicit_exact_market_points(tmp_path: Path) -> None:
    database = _seed_database(
        tmp_path / "market.db",
        [_row("2025/01/02", 10000), _row("20250109", 10500)],
    )
    request = _request(
        database,
        endpoints=("2025/01/02", "20250109"),
        availability={"20250109": "2025-01-09", "2025-01-02": "2025-01-02"},
    )

    pinned, result = _pin_then_load(request)

    assert result.status == "qualified_research"
    assert result.reason_codes == ()
    assert result.qualification_scope == "caller_declared_research_only"
    assert result.benchmark is not None
    assert result.benchmark.instrument_id == "market_indices.TAIEX"
    assert result.benchmark.source_identity.endswith(result.source_contract_sha256 or "")
    assert [point.trade_date for point in result.prices] == [DECISION, ENDPOINT]
    assert [point.price for point in result.prices] == [Decimal("10000.0"), Decimal("10500.0")]
    assert all(point.currency == "TWD" and point.price_basis == PRICE_BASIS for point in result.prices)
    assert all(point.corporate_action_basis == CORPORATE_ACTION_BASIS for point in result.prices)
    _assert_all_ineligible(result)

    contract = json.loads(result.source_contract_json or "{}")
    assert contract["availability_by_date"] == {DECISION: DECISION, ENDPOINT: ENDPOINT}
    assert contract["target_metadata"]["currency"] == "TWD"
    assert contract["source_metadata"]["price_basis"] == PRICE_BASIS
    assert contract["observed_rowset_sha256"] == result.observed_rowset_sha256
    assert contract["observed_decision_row_sha256"] == result.observed_decision_row_sha256
    assert pinned.expected_rowset_sha256 == result.observed_rowset_sha256


def test_adapter_points_feed_core_same_period_gross_excess(tmp_path: Path, monkeypatch) -> None:
    old_decision = date(2025, 1, 2)
    monkeypatch.setattr(snapshot_repository_tests, "DECISION_DATE", old_decision)
    monkeypatch.setattr(sample_capture_tests, "DECISION_DATE", old_decision)
    original_publish = sample_capture_tests._publish

    def publish_with_old_cutoff(*args, **kwargs):
        updates = dict(kwargs.get("manifest_updates") or {})
        updates["decision_cutoff"] = datetime.combine(
            old_decision, time(16), tzinfo=snapshot_repository_tests.TAIPEI
        ).isoformat()
        kwargs["manifest_updates"] = updates
        return original_publish(*args, **kwargs)

    monkeypatch.setattr(sample_capture_tests, "_publish", publish_with_old_cutoff)

    _, _, capture = sample_capture_tests._fixture(tmp_path)
    writer = BoundedRuleResearchCaptureWriter(tmp_path / "capture-receipts")
    monkeypatch.setattr(writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES + 1024**3)
    saved = writer.write(capture, revalidate=lambda: capture)
    package = writer.read(saved["receipt"]["capture_identity_sha256"])

    sessions = [old_decision]
    cursor = old_decision
    while len(sessions) <= 20:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            sessions.append(cursor)
    session_dates = tuple(item.isoformat() for item in sessions)
    endpoint = session_dates[5]
    today = datetime.now(timezone.utc).date().isoformat()
    database = _seed_database(
        tmp_path / "benchmark.db",
        [_row(session_dates[0], 10000), _row(endpoint, 10500)],
    )
    request = _request(
        database,
        endpoints=(session_dates[0], endpoint),
        availability={session_dates[0]: session_dates[0], endpoint: endpoint},
        as_of_date=today,
    )
    _, loaded = _pin_then_load(request)
    assert loaded.status == "qualified_research"
    assert loaded.benchmark is not None

    target_points = [
        PricePoint(
            instrument_id="2382",
            trade_date=day,
            state="available",
            price=Decimal(106 if index == 5 else 100 + index),
            source_identity="fixture.target.daily_prices",
            currency="TWD",
            unit="share",
            price_basis=PRICE_BASIS,
            corporate_action_basis=CORPORATE_ACTION_BASIS,
            available_date=day,
        )
        for index, day in enumerate(session_dates)
    ]
    calendar = Calendar(
        trading_dates=session_dates,
        known=True,
        complete=True,
        coverage_start=session_dates[0],
        coverage_end=session_dates[-1],
        source_identity="fixture.sessions.v1",
        available_date=session_dates[0],
    )
    projection = build_rule_research_forward_outcome(
        package,
        decision_date=session_dates[0],
        calendar=calendar,
        prices=[*target_points, *loaded.prices],
        benchmark=loaded.benchmark,
        cost_policy=None,
        as_of_date=today,
    ).to_dict()

    member = next(
        item for item in projection["members"]
        if item["stock_code"] == "2382" and item["method_id"] == "daily_market.close_above_ma20"
    )
    h5 = member["horizons"][0]
    assert h5["expected_end_date"] == endpoint
    assert h5["benchmark"]["end_price_date"] == endpoint
    assert h5["comparison"]["gross_excess_return"]["decimal"] == "0.01"
    assert h5["qualification"]["formal_eligible"] is False


@pytest.mark.parametrize(
    ("request_changes", "row_changes", "expected_status", "expected_code"),
    [
        ({"price_basis": "adjusted_close", "target_price_basis": "adjusted_close"}, {}, "rejected", "source_price_basis_mismatch"),
        ({"currency": "USD", "target_currency": "USD"}, {}, "rejected", "source_currency_mismatch"),
        ({"target_currency": "USD"}, {}, "rejected", "target_currency_mismatch"),
        ({}, {"公司行動基礎": "unknown"}, "unknown", "source_corporate_action_basis_unknown"),
    ],
)
def test_basis_currency_and_source_metadata_fail_closed(
    tmp_path: Path,
    request_changes: dict[str, Any],
    row_changes: dict[str, object],
    expected_status: str,
    expected_code: str,
) -> None:
    rows = [_row(DECISION, 10000), _row(ENDPOINT, 10500)]
    if row_changes:
        rows[0].update(row_changes)
    database = _seed_database(tmp_path / "market.db", rows)
    request = _request(database, **request_changes)

    pinned, result = _pin_then_load(request)

    assert result.status == expected_status
    assert expected_code in result.reason_codes
    assert result.benchmark is None and result.prices == ()
    if result.status == "unknown":
        assert pinned.expected_rowset_sha256
    _assert_all_ineligible(result)


@pytest.mark.parametrize(
    ("request_changes", "expected_code"),
    [
        ({"price_basis": None}, "price_basis_unknown"),
        ({"currency": "unknown"}, "currency_unknown"),
        ({"availability": {DECISION: DECISION}}, f"availability_{ENDPOINT}_unknown"),
        ({"availability": {DECISION: DECISION, ENDPOINT: None}}, f"availability_{ENDPOINT}_unknown"),
        ({"availability": {DECISION: DECISION, ENDPOINT: "2025-01-11"}}, f"availability_{ENDPOINT}_after_as_of"),
    ],
)
def test_unknown_basis_currency_or_availability_never_returns_prices(
    tmp_path: Path,
    request_changes: dict[str, Any],
    expected_code: str,
) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    changes = dict(request_changes)
    availability = changes.pop("availability", None)
    request = _request(database, availability=availability, **changes)

    first = load_explicit_market_benchmark(request)
    assert first.status == "unknown"
    assert expected_code in first.reason_codes
    assert first.benchmark is None and first.prices == ()
    _assert_all_ineligible(first)


def test_availability_before_trade_is_rejected(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    request = _request(
        database,
        availability={DECISION: "2025-01-01", ENDPOINT: ENDPOINT},
    )
    result = load_explicit_market_benchmark(request)
    assert result.status == "rejected"
    assert "available_before_trade_date" in result.reason_codes


@pytest.mark.parametrize(
    "rows",
    [
        [_row("2025-01-02", 10000), _row("20250102", 10000), _row(ENDPOINT, 10500)],
        [_row(DECISION, 10000, close_price=10001), _row(ENDPOINT, 10500)],
    ],
)
def test_duplicate_normalized_dates_or_conflicting_close_aliases_rejected(
    tmp_path: Path,
    rows: list[dict[str, object]],
) -> None:
    database = _seed_database(tmp_path / "market.db", rows)
    result = load_explicit_market_benchmark(_request(database))
    assert result.status == "rejected"
    assert result.benchmark is None and result.prices == ()
    assert any("duplicate" in code or "conflict" in code for code in result.reason_codes)


@pytest.mark.parametrize(
    "schema",
    [
        'CREATE TABLE market_indices ("日期" TEXT, "指數名稱" TEXT)',
        'CREATE TABLE market_indices ("日期" TEXT, "收盤指數" REAL)',
    ],
)
def test_missing_required_schema_is_unknown(tmp_path: Path, schema: str) -> None:
    database = _seed_database(tmp_path / "market.db", [], schema=schema)
    result = load_explicit_market_benchmark(_request(database))
    assert result.status == "unknown"
    assert "market_indices_required_schema_missing" in result.reason_codes


def test_missing_database_does_not_create_a_file_and_stock_price_is_never_fallback(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    result = load_explicit_market_benchmark(_request(missing))
    assert result.status == "unknown"
    assert not missing.exists()

    stock_db = tmp_path / "stock-only.db"
    with sqlite3.connect(stock_db) as connection:
        connection.execute('CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL)')
        connection.execute('INSERT INTO daily_prices VALUES (?, ?, ?)', (DECISION, "2382", 100))
    collision = load_explicit_market_benchmark(_request(stock_db, benchmark_name="2382"))
    assert collision.status == "rejected"
    assert "benchmark_name_stock_code_collision" in collision.reason_codes
    assert collision.benchmark is None and collision.prices == ()


def test_missing_name_never_defaults_to_taiex(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT)])
    result = load_explicit_market_benchmark(_request(database, benchmark_name=""))
    assert result.status == "rejected"
    assert "benchmark_name_required" in result.reason_codes
    assert result.benchmark is None


def test_revision_hash_and_decision_row_pin_reject_substitution(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    request = _request(database)
    pinned, qualified = _pin_then_load(request)
    assert qualified.status == "qualified_research"

    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE market_indices SET "收盤指數"=11000, "收盤價"=11000 WHERE "日期"=?', (ENDPOINT,))
    changed_endpoint = load_explicit_market_benchmark(pinned)
    assert changed_endpoint.status == "rejected"
    assert "rowset_revision_mismatch" in changed_endpoint.reason_codes

    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE market_indices SET "收盤指數"=10000, "收盤價"=10000 WHERE "日期"=?', (ENDPOINT,))
        connection.execute('UPDATE market_indices SET "收盤指數"=12000, "收盤價"=12000 WHERE "日期"=?', (DECISION,))
    decision_changed = load_explicit_market_benchmark(
        replace(pinned, expected_rowset_sha256=None)
    )
    assert decision_changed.status == "rejected"
    assert "decision_row_revision_mismatch" in decision_changed.reason_codes


def test_sqlite_storage_type_is_part_of_revision_identity(tmp_path: Path) -> None:
    schema = (
        'CREATE TABLE market_indices ('
        '"日期" TEXT, "指數名稱" TEXT, "收盤指數", "收盤價", "幣別" TEXT, '
        '"單位" TEXT, "價格基礎" TEXT, "公司行動基礎" TEXT, "可得日" TEXT)'
    )
    database = _seed_database(
        tmp_path / "market.db",
        [_row(DECISION, "100"), _row(ENDPOINT, "105")],
        schema=schema,
    )
    pinned, result = _pin_then_load(_request(database))
    assert result.status == "qualified_research"

    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE market_indices SET "收盤指數"=100, "收盤價"=100 WHERE "日期"=?', (DECISION,))
    revised = load_explicit_market_benchmark(pinned)
    assert revised.status == "rejected"
    assert "rowset_revision_mismatch" in revised.reason_codes


def test_sqlite_real_roundtrip_identity_detects_cast_text_collision(tmp_path: Path) -> None:
    schema = (
        'CREATE TABLE market_indices ('
        '"日期" TEXT, "指數名稱" TEXT, "收盤指數", "收盤價", "幣別" TEXT, '
        '"單位" TEXT, "價格基礎" TEXT, "公司行動基礎" TEXT, "可得日" TEXT)'
    )
    database = _seed_database(tmp_path / "market.db", [], schema=schema)
    with sqlite3.connect(database) as connection:
        connection.execute(
            'INSERT INTO market_indices VALUES (?, ?, 10000.0, 10000.0, ?, ?, ?, ?, ?)',
            (
                DECISION,
                "TAIEX",
                "TWD",
                "index_points",
                PRICE_BASIS,
                CORPORATE_ACTION_BASIS,
                DECISION,
            ),
        )
        connection.execute(
            'INSERT INTO market_indices VALUES (?, ?, 1.0000000000000002, '
            '1.0000000000000002, ?, ?, ?, ?, ?)',
            (
                ENDPOINT,
                "TAIEX",
                "TWD",
                "index_points",
                PRICE_BASIS,
                CORPORATE_ACTION_BASIS,
                ENDPOINT,
            ),
        )
    pinned, qualified = _pin_then_load(_request(database))
    assert qualified.status == "qualified_research"

    with sqlite3.connect(database) as connection:
        cast_before, real_before = connection.execute(
            'SELECT CAST("收盤指數" AS TEXT), printf(\'%!.26g\', "收盤指數") '
            'FROM market_indices WHERE "日期"=?',
            (ENDPOINT,),
        ).fetchone()
        connection.execute(
            'UPDATE market_indices SET "收盤指數"=1.0000000000000004, '
            '"收盤價"=1.0000000000000004 WHERE "日期"=?',
            (ENDPOINT,),
        )
        cast_after, real_after = connection.execute(
            'SELECT CAST("收盤指數" AS TEXT), printf(\'%!.26g\', "收盤指數") '
            'FROM market_indices WHERE "日期"=?',
            (ENDPOINT,),
        ).fetchone()

    assert cast_before == cast_after == "1.0"
    assert real_before != real_after
    revised = load_explicit_market_benchmark(pinned)
    assert revised.status == "rejected"
    assert "rowset_revision_mismatch" in revised.reason_codes


def test_decimal_text_and_precision_bounds_are_fail_closed(tmp_path: Path) -> None:
    schema = (
        'CREATE TABLE market_indices ('
        '"日期" TEXT, "指數名稱" TEXT, "收盤指數", "收盤價", "幣別" TEXT, '
        '"單位" TEXT, "價格基礎" TEXT, "公司行動基礎" TEXT, "可得日" TEXT)'
    )
    database = _seed_database(
        tmp_path / "market.db",
        [_row(DECISION, "1e999999999"), _row(ENDPOINT, "10000")],
        schema=schema,
    )
    result = load_explicit_market_benchmark(_request(database))
    assert result.status == "rejected"
    assert "benchmark_price_precision_bound" in result.reason_codes
    assert result.benchmark is None and result.prices == ()


def test_future_as_of_clock_and_endpoint_do_not_qualify(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    future_as_of = load_explicit_market_benchmark(_request(database, as_of_date=tomorrow))
    assert future_as_of.status == "rejected"
    assert "as_of_date_in_future" in future_as_of.reason_codes

    future_observed_at = load_explicit_market_benchmark(
        _request(database), observed_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert future_observed_at.status == "rejected"
    assert "observed_at_in_future" in future_observed_at.reason_codes

    before_as_of = load_explicit_market_benchmark(
        _request(database), observed_at=datetime(2025, 1, 9, tzinfo=timezone.utc)
    )
    assert before_as_of.status == "rejected"
    assert "as_of_date_in_future" in before_as_of.reason_codes

    late_endpoint = "2025-01-11"
    late_request = _request(
        database,
        endpoints=(DECISION, late_endpoint),
        availability={DECISION: DECISION, late_endpoint: late_endpoint},
    )
    _, late = _pin_then_load(late_request)
    assert late.status == "unknown"
    assert late.benchmark is None and late.prices == ()
    assert f"availability_{late_endpoint}_after_as_of" in late.reason_codes


def test_read_only_database_and_cancellation(tmp_path: Path) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    before = (hashlib.sha256(database.read_bytes()).hexdigest(), database.stat().st_mtime_ns)
    result = load_explicit_market_benchmark(_request(database), cancel_callback=lambda: False)
    after = (hashlib.sha256(database.read_bytes()).hexdigest(), database.stat().st_mtime_ns)
    assert before == after
    assert result.status == "unknown"

    cancelled = load_explicit_market_benchmark(_request(database), cancel_callback=lambda: True)
    assert cancelled.status == "unknown"
    assert "cancelled" in cancelled.reason_codes
    assert before == (hashlib.sha256(database.read_bytes()).hexdigest(), database.stat().st_mtime_ns)


def test_source_pin_detects_change_during_query(tmp_path: Path, monkeypatch) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    calls = 0

    def changing_pin(_path: Path):
        nonlocal calls
        calls += 1
        return (("first" if calls == 1 else "changed",),)

    monkeypatch.setattr(adapter_module, "_source_pin", changing_pin)
    result = load_explicit_market_benchmark(_request(database))
    assert result.status == "rejected"
    assert "source_changed_during_read" in result.reason_codes


def test_wal_commit_after_schema_snapshot_is_rejected(tmp_path: Path, monkeypatch) -> None:
    database = _seed_database(tmp_path / "market.db", [_row(DECISION), _row(ENDPOINT, 10500)])
    with sqlite3.connect(database) as setup:
        assert setup.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
    writer = sqlite3.connect(database, isolation_level=None)
    original_pin = adapter_module._source_pin
    calls = 0

    def commit_after_schema(path: Path):
        nonlocal calls
        calls += 1
        if calls == 3:
            writer.execute(
                'UPDATE market_indices SET "收盤指數"=10999, "收盤價"=10999 '
                'WHERE "日期"=?',
                (ENDPOINT,),
            )
        return original_pin(path)

    monkeypatch.setattr(adapter_module, "_source_pin", commit_after_schema)
    try:
        result = load_explicit_market_benchmark(_request(database))
    finally:
        writer.close()

    assert calls >= 3
    assert result.status == "rejected"
    assert "source_changed_during_read" in result.reason_codes
    assert result.benchmark is None and result.prices == ()


def test_invalid_database_path_is_a_rejected_input(tmp_path: Path) -> None:
    result = load_explicit_market_benchmark(_request(tmp_path / "market.db", database_path=None))
    assert result.status == "rejected"
    assert "database_path_invalid" in result.reason_codes
