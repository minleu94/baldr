from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from scripts import capture_current_official_valuation as valuation_cli
from scripts.scheduled.run_official_market_status_bundle import _valuation_capture_evidence
from data_module.current_official_valuation import (
    CAPTURE_RELATIVE_ROOT,
    CurrentOfficialValuationReadProvider,
    capture_current_official_valuation,
    parse_tpex_openapi_valuation_response,
    parse_tpex_valuation_response,
    parse_twse_valuation_response,
)


UTC = timezone.utc
CAPTURE_TIME = datetime(2026, 10, 4, 2, 0, tzinfo=UTC)
READ_TIME = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)


def _twse_body(date_text: str = "115/10/02", pe: str = "24.50") -> bytes:
    return json.dumps(
        [
            {
                "Date": date_text,
                "Code": "2330",
                "PEratio": pe,
                "DividendYield": "2.10",
                "PBratio": "6.25",
            }
        ],
        ensure_ascii=False,
    ).encode("utf-8")


def _tpex_body(date_text: str = "115/10/02") -> bytes:
    return f"""<!doctype html><html><body>
    <div>資料日期：{date_text}</div><div>全部產業</div>
    <table>
      <tr><th>股票代號</th><th>名稱</th><th>本益比</th><th>殖利率(%)</th><th>股價淨值比</th></tr>
      <tr><td>6488</td><td>環球晶</td><td>18.75</td><td>3.40</td><td>2.30</td></tr>
    </table></body></html>""".encode("utf-8")


def _tpex_openapi_body(date_text: str = "1151002") -> bytes:
    return json.dumps(
        [
            {
                "Date": date_text,
                "SecuritiesCompanyCode": "6488",
                "CompanyName": "test",
                "PriceEarningRatio": "57.77",
                "DividendPerShare": "7.70000000",
                "YieldRatio": "0.65",
                "PriceBookRatio": "5.88",
            }
        ],
        ensure_ascii=False,
    ).encode("utf-8")


class _Response:
    def __init__(self, content: bytes, url: str, status_code: int = 200) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json", "Set-Cookie": "private=value"}


class _Session:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _session(
    *,
    twse_date: str = "115/10/02",
    tpex_date: str = "115/10/02",
    twse_pe: str = "24.50",
    tpex_status: int = 200,
) -> _Session:
    tpex_url = "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php"
    return _Session(
        [
            _Response(_twse_body(twse_date, twse_pe), "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"),
            _Response(_tpex_body(tpex_date), tpex_url + "?" + urlencode({"l": "zh-tw", "o": "htm", "s": "0"}), status_code=tpex_status),
        ]
    )


def test_parsers_preserve_decimal_values_and_exchange_dates() -> None:
    twse = parse_twse_valuation_response(_twse_body())
    tpex = parse_tpex_valuation_response(_tpex_body())

    assert twse.source_date == date(2026, 10, 2)
    assert twse.rows[0].values["pe"] == Decimal("24.50")
    assert twse.rows[0].values["dividend_yield"] == Decimal("2.10")
    assert twse.rows[0].values["pb"] == Decimal("6.25")
    assert tpex.source_date == date(2026, 10, 2)
    assert tpex.rows[0].stock_code == "6488"
    assert tpex.rows[0].values["pb"] == Decimal("2.30")


def test_tpex_openapi_parser_uses_swagger_documented_fields() -> None:
    parsed = parse_tpex_openapi_valuation_response(_tpex_openapi_body())

    assert parsed.source_id == "tpex.openapi.tpex_mainboard_peratio_analysis"
    assert parsed.source_date == date(2026, 10, 2)
    assert parsed.rows[0].stock_code == "6488"
    assert parsed.rows[0].values == {
        "pe": Decimal("57.77"),
        "dividend_yield": Decimal("0.65"),
        "pb": Decimal("5.88"),
    }


def test_capture_roundtrip_uses_immutable_hash_receipts_and_current_only_reader(tmp_path: Path) -> None:
    session = _session()
    times = iter([CAPTURE_TIME, CAPTURE_TIME, CAPTURE_TIME.replace(second=1), CAPTURE_TIME.replace(second=2)])
    captured = capture_current_official_valuation(
        tmp_path,
        session=session,
        clock=lambda: next(times),
    )

    assert captured.status == "captured"
    assert captured.wrapper_run_id == captured.run_id
    assert captured.receipt_path.is_file()
    assert captured.receipt_sha256 == __import__("hashlib").sha256(captured.receipt_path.read_bytes()).hexdigest()
    run_receipt = json.loads(captured.receipt_path.read_text(encoding="utf-8"))
    assert run_receipt["schema_version"] == "official-current-valuation-run.v1"
    assert run_receipt["status"] == "captured"
    assert len(run_receipt["markets"]) == 2
    assert [item.status for item in captured.markets] == ["captured", "captured"]
    assert len(session.calls) == 2
    capture_dirs = [path for market in ("twse", "tpex") for path in (tmp_path / CAPTURE_RELATIVE_ROOT / market).rglob("receipt.json")]
    assert len(capture_dirs) == 2
    for receipt_path in capture_dirs:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["formal_pit_eligible"] is False
        assert receipt["historical_pit_eligible"] is False
        assert "set-cookie" not in receipt["response"]["headers"]
        body = receipt_path.with_name("raw_response.bin").read_bytes()
        import hashlib

        assert "sha256:" + hashlib.sha256(body).hexdigest() == receipt["raw_response_sha256"]

    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)
    result = provider.read_current("2330", expected_market_date=date(2026, 10, 2))
    assert result.status == "ready"
    assert len(result.observations) == 3
    pe = next(item for item in result.observations if item.metric_name == "pe")
    assert pe.value == Decimal("24.50")
    assert pe.unit == "ratio"
    assert pe.as_of_date == date(2026, 10, 2)
    assert pe.available_at == CAPTURE_TIME
    assert pe.raw_response_sha256.startswith("sha256:")
    assert pe.formal_pit_eligible is False
    assert {item.market: item.status for item in result.market_coverage} == {
        "twse": "ready",
        "tpex": "ready",
    }

    historical = provider.read_current("2330", date(2026, 10, 3))
    assert historical.status == "blocked_historical_date"
    assert historical.observations == ()


def test_cli_stdout_is_verified_by_official_market_bundle_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    wrapper_run_id = "valuation-cli-contract-20261004"

    def capture_with_fixture(
        output_root: Path,
        *,
        wrapper_run_id: str | None = None,
        timeout_seconds: float = 20.0,
    ):
        return capture_current_official_valuation(
            output_root,
            wrapper_run_id=wrapper_run_id,
            timeout_seconds=timeout_seconds,
            session=_session(),
            clock=lambda: CAPTURE_TIME,
        )

    monkeypatch.setattr(valuation_cli, "capture_current_official_valuation", capture_with_fixture)

    exit_code = valuation_cli.main(
        [
            "--output-root",
            str(tmp_path),
            "--wrapper-run-id",
            wrapper_run_id,
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["schema_version"] == "official-current-valuation-run.v1"
    assert payload["formal_pit_eligible"] is False
    assert payload["historical_pit_eligible"] is False
    evidence = _valuation_capture_evidence(
        tmp_path,
        {"status_payload": payload},
        wrapper_run_id=wrapper_run_id,
    )
    assert evidence["validation"] == "verified", evidence
    assert evidence["terminal_run_id"] == wrapper_run_id
    assert evidence["historical_pit_eligible"] is False


def test_reader_rejects_tampered_raw_response(tmp_path: Path) -> None:
    captured = capture_current_official_valuation(
        tmp_path,
        session=_session(),
        clock=lambda: CAPTURE_TIME,
    )
    assert captured.status == "captured"
    raw_path = next((tmp_path / CAPTURE_RELATIVE_ROOT / "twse").rglob("raw_response.bin"))
    raw_path.write_bytes(raw_path.read_bytes() + b" ")

    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)
    result = provider.read_current("2330", expected_market_date=date(2026, 10, 2))
    assert result.status == "partial"
    assert result.observations == ()
    assert any("twse_capture_invalid" in diagnostic for diagnostic in result.diagnostics)


def test_reader_keeps_last_market_session_as_current_on_non_trading_day(tmp_path: Path) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(),
        clock=lambda: CAPTURE_TIME,
    )
    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)
    result = provider.read_current("2330", expected_market_date=date(2026, 10, 2))
    assert result.status == "ready"
    assert result.report_date == date(2026, 10, 4)
    assert {item.as_of_date for item in result.observations} == {date(2026, 10, 2)}


def test_reader_requires_exact_expected_market_date_for_freshness(tmp_path: Path) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(),
        clock=lambda: CAPTURE_TIME,
    )
    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)

    unverified = provider.read_current("2330")
    assert unverified.status == "freshness_unverified"
    assert len(unverified.observations) == 3
    assert {item.status for item in unverified.market_coverage} == {"freshness_unverified"}

    stale = provider.read_current("2330", expected_market_date=date(2026, 10, 3))
    assert stale.status == "unavailable"
    assert stale.observations == ()
    assert any("twse_capture_missing" in item for item in stale.diagnostics)
    assert next(item for item in stale.market_coverage if item.market == "twse").status == "missing"

    later_clock = datetime(2026, 10, 5, 2, tzinfo=UTC)
    next_session = CurrentOfficialValuationReadProvider(
        tmp_path, clock=lambda: later_clock
    ).read_current("2330", expected_market_date=date(2026, 10, 5))
    assert next_session.status == "unavailable"
    assert next_session.observations == ()


def test_reader_rejects_future_expected_market_date(tmp_path: Path) -> None:
    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)
    result = provider.read_current("2330", expected_market_date=date(2026, 10, 5))
    assert result.status == "blocked_future_expected_market_date"
    assert result.observations == ()


def test_failed_market_body_is_preserved_and_bound_to_wrapper_run(tmp_path: Path) -> None:
    session = _session()
    session.responses[1].status_code = 520
    session.responses.append(
        _Response(
            b"official api temporarily unavailable",
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
            status_code=520,
        )
    )
    wrapper_run_id = "daily-valuation-20261004-0450"
    captured = capture_current_official_valuation(
        tmp_path,
        wrapper_run_id=wrapper_run_id,
        session=session,
        clock=lambda: CAPTURE_TIME,
    )
    assert captured.status == "degraded"
    assert captured.wrapper_run_id == wrapper_run_id
    assert captured.run_id == wrapper_run_id
    payload = json.loads(captured.receipt_path.read_text(encoding="utf-8"))
    assert payload["wrapper_run_id"] == wrapper_run_id
    assert payload["run_id"] == wrapper_run_id
    twse, tpex = payload["markets"]
    assert twse["status"] == "captured"
    assert twse["raw_response_path"] and twse["raw_response_sha256"]
    assert tpex["status"] == "failed"
    assert tpex["failure_receipt_path"] and tpex["failure_receipt_sha256"]
    failed_receipt_path = Path(tpex["failure_receipt_path"])
    failure_receipt = json.loads(failed_receipt_path.read_text(encoding="utf-8"))
    raw_path = failed_receipt_path.with_name("raw_response.bin")
    import hashlib
    assert "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest() == failure_receipt["raw_response_sha256"]
    assert hashlib.sha256(failed_receipt_path.read_bytes()).hexdigest() == tpex["failure_receipt_sha256"]
    assert failure_receipt["response"]["http_status"] == 520
    assert tpex["prior_failure_attempts"][0]["source_id"] == "tpex.website.peratio_analysis"
    legacy_failure = tpex["prior_failure_attempts"][0]
    assert Path(legacy_failure["raw_response_path"]).is_file()
    assert hashlib.sha256(Path(legacy_failure["raw_response_path"]).read_bytes()).hexdigest() == legacy_failure[
        "raw_response_sha256"
    ].removeprefix("sha256:")


def test_tpex_openapi_fallback_captures_after_preserving_legacy_failure(tmp_path: Path) -> None:
    session = _session()
    session.responses[1].status_code = 520
    session.responses.append(
        _Response(
            _tpex_openapi_body(),
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
        )
    )
    captured = capture_current_official_valuation(
        tmp_path,
        wrapper_run_id="fallback-openapi-20261004",
        session=session,
        clock=lambda: CAPTURE_TIME,
    )

    assert captured.status == "captured"
    terminal = json.loads(captured.receipt_path.read_text(encoding="utf-8"))
    tpex = next(row for row in terminal["markets"] if row["market"] == "tpex")
    assert tpex["status"] == "captured"
    assert tpex["source_row_count"] == 1
    assert len(tpex["prior_failure_attempts"]) == 1
    failure = tpex["prior_failure_attempts"][0]
    assert failure["status"] == "failed"
    assert failure["captured_at"] == CAPTURE_TIME.isoformat()
    assert failure["raw_response_path"] and failure["raw_response_sha256"]
    assert failure["receipt_path"] and failure["receipt_sha256"]
    assert Path(failure["receipt_path"]).is_file()
    assert hashlib.sha256(Path(failure["receipt_path"]).read_bytes()).hexdigest() == failure[
        "receipt_sha256"
    ]
    capture_receipt = json.loads(Path(tpex["receipt_path"]).read_text(encoding="utf-8"))
    assert capture_receipt["source_id"] == "tpex.openapi.tpex_mainboard_peratio_analysis"
    assert capture_receipt["source_contract_reference"] == "https://www.tpex.org.tw/openapi/swagger.json"

    provider = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME)
    result = provider.read_current("6488", expected_market_date=date(2026, 10, 2), market="tpex")
    assert result.status == "ready"
    assert {row.metric_name: (row.value, row.unit) for row in result.observations} == {
        "pe": (Decimal("57.77"), "ratio"),
        "dividend_yield": (Decimal("0.65"), "percent"),
        "pb": (Decimal("5.88"), "ratio"),
    }


def test_wrapper_run_id_is_validated_before_capturing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="wrapper_run_id"):
        capture_current_official_valuation(
            tmp_path,
            wrapper_run_id="../escape",
            session=_session(),
            clock=lambda: CAPTURE_TIME,
        )


def test_reader_rejects_future_capture_clock_even_with_valid_receipt(tmp_path: Path) -> None:
    future_clock = datetime(2026, 10, 6, 2, tzinfo=UTC)
    captured = capture_current_official_valuation(
        tmp_path,
        session=_session(),
        clock=lambda: future_clock,
    )
    assert captured.status == "captured"
    result = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME).read_current(
        "2330", expected_market_date=date(2026, 10, 2)
    )
    assert result.observations == ()
    assert any("available_at is in the future" in item for item in result.diagnostics)
    assert {item.status for item in result.market_coverage} == {"invalid"}


def test_latest_invalid_capture_is_not_bypassed_by_older_valid_date(tmp_path: Path) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(twse_date="115/10/01", tpex_date="115/10/01"),
        clock=lambda: CAPTURE_TIME,
    )
    capture_current_official_valuation(
        tmp_path,
        session=_session(twse_date="115/10/02", tpex_date="115/10/02"),
        clock=lambda: CAPTURE_TIME.replace(second=1),
    )
    latest_raw = next((tmp_path / CAPTURE_RELATIVE_ROOT / "twse" / "20261002").rglob("raw_response.bin"))
    latest_raw.write_bytes(latest_raw.read_bytes() + b" ")

    result = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME).read_current(
        "2330", expected_market_date=date(2026, 10, 2)
    )
    assert result.observations == ()
    assert next(item for item in result.market_coverage if item.market == "twse").status == "invalid"
    assert any("twse_capture_invalid" in diagnostic for diagnostic in result.diagnostics)


def test_expected_session_selects_exact_older_source_date_when_newer_date_exists(
    tmp_path: Path,
) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(
            twse_date="115/10/01",
            tpex_date="115/10/01",
            twse_pe="11.11",
        ),
        clock=lambda: CAPTURE_TIME,
    )
    capture_current_official_valuation(
        tmp_path,
        session=_session(
            twse_date="115/10/02",
            tpex_date="115/10/02",
            twse_pe="22.22",
        ),
        clock=lambda: CAPTURE_TIME.replace(second=1),
    )

    result = CurrentOfficialValuationReadProvider(
        tmp_path, clock=lambda: READ_TIME
    ).read_current("2330", expected_market_date=date(2026, 10, 1))

    assert result.status == "ready"
    pe = next(item for item in result.observations if item.metric_name == "pe")
    assert pe.as_of_date == date(2026, 10, 1)
    assert pe.value == Decimal("11.11")


def test_expected_session_does_not_fall_back_when_exact_date_is_missing(
    tmp_path: Path,
) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(twse_date="115/10/02", tpex_date="115/10/02"),
        clock=lambda: CAPTURE_TIME,
    )

    result = CurrentOfficialValuationReadProvider(
        tmp_path, clock=lambda: READ_TIME
    ).read_current("2330", expected_market_date=date(2026, 10, 1))

    assert result.observations == ()
    assert result.status == "unavailable"
    assert any("twse_capture_missing" in item for item in result.diagnostics)


def test_unexpected_future_source_date_directory_is_not_ignored(
    tmp_path: Path,
) -> None:
    future_directory = tmp_path / CAPTURE_RELATIVE_ROOT / "twse" / "20261005"
    future_directory.mkdir(parents=True)

    result = CurrentOfficialValuationReadProvider(
        tmp_path, clock=lambda: READ_TIME
    ).read_current("2330", expected_market_date=date(2026, 10, 2))

    assert result.observations == ()
    assert any("future source-date directory exists" in item for item in result.diagnostics)


def test_partial_market_does_not_fall_back_to_an_older_tpex_date(tmp_path: Path) -> None:
    capture_current_official_valuation(
        tmp_path,
        session=_session(twse_date="115/10/02", tpex_date="115/10/01"),
        clock=lambda: CAPTURE_TIME,
    )
    result = CurrentOfficialValuationReadProvider(tmp_path, clock=lambda: READ_TIME).read_current(
        "6488", expected_market_date=date(2026, 10, 2)
    )
    assert result.status == "partial"
    assert result.observations == ()
    assert next(item for item in result.market_coverage if item.market == "twse").status == "ready"
    assert next(item for item in result.market_coverage if item.market == "tpex").status == "missing"
