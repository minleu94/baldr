from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from ml_module.recommendation_calibration_evidence import (
    verify_natural_maturity_session_proof,
)
from data_module.recommendation_natural_maturity_proof import (
    verify_natural_maturity_session_proof as verify_data_session_proof,
)
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
)


CAPTURE_DATE = "2026-01-02"
EVALUATION_AT = datetime(2026, 2, 2, 8, 0, tzinfo=timezone.utc)
ENDPOINT_DATE = "2026-01-30"


def _write_calendar(root: Path, year: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "國曆新年休市",
                "Date": f"{year - 1911:03d}0101",
                "Weekday": "四" if year == 2026 else "三",
                "Description": "測試用官方年度休市紀錄。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    captured_at = datetime(2026, 1, 25, 8, 0, tzinfo=timezone.utc)
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": f'"session-{year}"'},
        max_age=timedelta(days=31),
    )
    write_twse_calendar_cache(
        root / f"twse_holiday_schedule_{year}_test.json",
        cache,
        allowed_root=root,
    )


def _write_market_database(path: Path, *, include_endpoint_stock: bool) -> None:
    session_dates = (
        "20260105", "20260106", "20260107", "20260108", "20260109",
        "20260112", "20260113", "20260114", "20260115", "20260116",
        "20260119", "20260120", "20260121", "20260122", "20260123",
        "20260126", "20260127", "20260128", "20260129", "20260130",
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                成交股數 INTEGER,
                成交金額 INTEGER,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                RSI TEXT,
                MACD TEXT,
                ADX TEXT
            );
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT,
                收盤指數 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE industry_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT,
                收盤指數 TEXT
            );
            """
        )
        market_dates = ("20260102", *session_dates)
        for index, day in enumerate(market_dates, start=1):
            close = str(20_000 + index)
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?, ?)",
                (day, "TAIEX", close, close),
            )
        stock_rows = [("20260102", "2330", "100"),]
        if include_endpoint_stock:
            # 中間日期故意沒有個股列，endpoint 仍只按官方 session 精確取值。
            stock_rows.append((ENDPOINT_DATE.replace("-", ""), "2330", "120"))
        for day, symbol, close in stock_rows:
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (day, symbol, 100_000, 10_000_000, close, close, close, close),
            )


def _service_fixture(tmp_path: Path, *, include_endpoint_stock: bool) -> tuple[
    RecommendationNaturalOutcomeService,
    dict[str, object],
    NaturalMaturitySessionResolver,
]:
    database = tmp_path / "twstock.db"
    _write_market_database(database, include_endpoint_stock=include_endpoint_stock)
    calendar_root = tmp_path / "calendar"
    _write_calendar(calendar_root, 2025)
    _write_calendar(calendar_root, 2026)
    resolver = NaturalMaturitySessionResolver(database, calendar_root)
    scenario = build_legacy_cost_scenario(50)
    payload: dict[str, object] = {
        "capture_as_of_date": CAPTURE_DATE,
        "fixed_round_trip_cost_bp": 50,
        "rows": [{"row_id": "row-2330", "symbol": "2330"}],
        **scenario.metadata(),
    }
    service = RecommendationNaturalOutcomeService(
        MLHistoricalSnapshotProvider(database),
        session_resolver=resolver,
        evaluation_at=EVALUATION_AT,
    )
    return service, payload, resolver


def test_natural_outcome_uses_exact_twenty_official_sessions_and_verified_market(
    tmp_path: Path,
) -> None:
    service, payload, resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=True,
    )

    resolution = resolver.resolve(CAPTURE_DATE, EVALUATION_AT, horizon_sessions=20)
    assert resolution.status == "ready"
    assert resolution.endpoint_date == ENDPOINT_DATE
    assert resolution.proof is not None
    source_files = [tmp_path / "twstock.db", *(tmp_path / "calendar").glob("*.json")]
    source_bytes = {path: path.read_bytes() for path in source_files}
    verified = verify_natural_maturity_session_proof(
        resolution.proof,
        capture_date=CAPTURE_DATE,
        label_end_date=ENDPOINT_DATE,
        evaluation_at=EVALUATION_AT,
        expected_db_path=tmp_path / "twstock.db",
    )
    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date(),
        max_rows=10,
    )

    assert pending == 0
    assert diagnostics == ("liquidity_cost_missing:2330:2026-01-02",)
    assert len(outcomes) == 1
    assert outcomes[0].label_end_date == ENDPOINT_DATE
    assert outcomes[0].session_proof == verified
    assert verify_data_session_proof(
        resolution.proof,
        capture_date=CAPTURE_DATE,
        label_end_date=ENDPOINT_DATE,
        evaluation_at=EVALUATION_AT,
        expected_db_path=tmp_path / "twstock.db",
    ) == verified
    assert {path: path.read_bytes() for path in source_files} == source_bytes


def test_natural_outcome_keeps_missing_endpoint_stock_pending(
    tmp_path: Path,
) -> None:
    service, payload, _resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=False,
    )

    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date(),
        max_rows=10,
    )

    assert outcomes == []
    assert pending == 1
    assert diagnostics == (
        f"natural_maturity_endpoint_stock_close_invalid:2330:{ENDPOINT_DATE}",
    )


def test_natural_outcome_clock_mismatch_stays_pending(
    tmp_path: Path,
) -> None:
    service, payload, _resolver = _service_fixture(
        tmp_path,
        include_endpoint_stock=True,
    )

    outcomes, pending, diagnostics = service._outcomes_for_capture(
        payload,
        evaluation_day=EVALUATION_AT.astimezone(timezone(timedelta(hours=8))).date()
        + timedelta(days=1),
        max_rows=10,
    )

    assert outcomes == []
    assert pending == 1
    assert diagnostics == ("natural_maturity_evaluation_clock_mismatch",)


@pytest.mark.parametrize("case", [
    "horizon", "unknown", "hash", "capture", "endpoint", "clock",
    "cutoff", "wrong_db", "missing_sessions", "wrong_index", "missing_calendar",
    "changed_calendar", "changed_market",
])
def test_data_session_adapter_preserves_legacy_rejections(
    tmp_path: Path, case: str,
) -> None:
    from data_module.natural_maturity_session_resolver import _hash_payload

    _service, _payload, resolver = _service_fixture(tmp_path, include_endpoint_stock=True)
    resolution = resolver.resolve(CAPTURE_DATE, EVALUATION_AT, horizon_sessions=20)
    assert resolution.proof is not None
    proof = json.loads(json.dumps(resolution.proof))
    evaluation = EVALUATION_AT
    database = tmp_path / "twstock.db"
    if case == "horizon":
        proof["horizon_sessions"] = 19
    elif case == "unknown":
        proof["status"] = "waiting_for_calendar"
    elif case == "capture":
        proof["capture_date"] = "2026-01-01"
    elif case == "endpoint":
        proof["endpoint_date"] = "2026-01-29"
    elif case == "clock":
        proof["evaluation_at"] = (evaluation + timedelta(seconds=1)).isoformat()
    elif case == "cutoff":
        evaluation = datetime(2026, 1, 30, 6, 29, tzinfo=timezone.utc)
        proof["evaluation_at"] = evaluation.isoformat()
    elif case == "wrong_db":
        database = tmp_path / "other.db"
    elif case == "missing_sessions":
        proof["missing_session_dates"] = ["2026-01-20"]
    elif case == "wrong_index":
        proof["market"]["index_name"] = "unknown"
    elif case == "missing_calendar":
        proof["calendar"]["calendar_cache_path"] = str(tmp_path / "absent-calendar")
    elif case == "changed_calendar":
        cache = Path(proof["calendar"]["annual_sources"][0]["evidence"]["path"])
        cache_payload = json.loads(cache.read_bytes())
        cache_payload["raw_response_base64"] = "e30="
        cache.write_text(json.dumps(cache_payload), encoding="utf-8")
    elif case == "changed_market":
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE market_indices SET 收盤指數='1', 收盤價='1'")
    proof["proof_hash"] = _hash_payload({
        key: value for key, value in proof.items() if key != "proof_hash"
    })
    if case == "hash":
        proof["proof_hash"] = "sha256:" + "0" * 64
    errors = []
    for verify in (verify_natural_maturity_session_proof, verify_data_session_proof):
        with pytest.raises(ValueError) as caught:
            verify(
                proof,
                capture_date=CAPTURE_DATE,
                label_end_date=ENDPOINT_DATE,
                evaluation_at=evaluation,
                expected_db_path=database,
            )
        errors.append((type(caught.value), str(caught.value)))
    assert errors[0] == errors[1]
    if case == "cutoff":
        assert errors[0][1] == "session proof endpoint is after evaluation cutoff"


def test_missing_calendar_cannot_produce_natural_maturity_proof(tmp_path: Path) -> None:
    database = tmp_path / "twstock.db"
    _write_market_database(database, include_endpoint_stock=True)
    resolver = NaturalMaturitySessionResolver(database, tmp_path / "absent-calendar")
    resolution = resolver.resolve(CAPTURE_DATE, EVALUATION_AT, horizon_sessions=20)
    assert resolution.status == "waiting_for_calendar"
    assert resolution.proof is None


def test_data_session_adapter_preserves_signature_and_missing_resolver_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import inspect

    assert inspect.signature(verify_data_session_proof) == inspect.signature(
        verify_natural_maturity_session_proof
    )
    original_import = builtins.__import__

    def reject_resolver(name, *args, **kwargs):
        if name == "data_module.natural_maturity_session_resolver":
            raise ImportError("fixture resolver unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_resolver)
    for verify in (verify_natural_maturity_session_proof, verify_data_session_proof):
        with pytest.raises(ValueError, match="^natural maturity session resolver is unavailable$") as caught:
            verify(
                {"horizon_sessions": 20},
                capture_date=CAPTURE_DATE,
                label_end_date=ENDPOINT_DATE,
                evaluation_at=EVALUATION_AT,
                expected_db_path="missing.db",
            )
        assert type(caught.value.__cause__) is ImportError
        assert str(caught.value.__cause__) == "fixture resolver unavailable"
