from __future__ import annotations

from datetime import date, datetime
import json

import pytest

from data_module import official_phase3c_fetcher as fetcher


class _JsonResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _CsvResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.encoding = "utf-8"


class _BytesResponse:
    def __init__(self, payload: bytes, *, headers=None, status_code: int = 200) -> None:
        self.content = payload
        self.headers = headers or {}
        self.status_code = status_code

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        yield self.content

    def close(self) -> None:
        pass


class _HttpFailureResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


_TDCC_OFFICIAL_00406A_LEVELS = (
    (1, 8024, 2441315, "0.04"),
    (2, 75477, 199320738, "4.01"),
    (3, 33226, 290682254, "5.85"),
    (4, 11526, 152382045, "3.06"),
    (5, 12939, 248750687, "5.00"),
    (6, 11565, 310385174, "6.24"),
    (7, 5882, 216226742, "4.35"),
    (8, 5955, 286520613, "5.76"),
    (9, 10352, 796737793, "16.03"),
    (10, 4865, 701323665, "14.11"),
    (11, 1983, 559642641, "11.26"),
    (12, 581, 288006145, "5.79"),
    (13, 205, 144272022, "2.90"),
    (14, 128, 118227036, "2.37"),
    (15, 207, 657983960, "13.24"),
    (16, 2, 4840830, "0.09"),
    (17, 182915, 4968062000, "100.00"),
)


def _tdcc_complete_csv(
    *,
    symbol: str,
    data_date: str,
    levels=_TDCC_OFFICIAL_00406A_LEVELS,
) -> str:
    lines = ["資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%"]
    lines.extend(
        f"{data_date},{symbol},{tier},{holders},{shares},{ratio}"
        for tier, holders, shares, ratio in levels
    )
    return "\n".join(lines) + "\n"


def _install_responses(monkeypatch, *payloads: dict[str, object]) -> None:
    responses = iter(_JsonResponse(payload) for payload in payloads)
    monkeypatch.setattr(fetcher, "safe_request", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)


def test_institutional_fetcher_supports_current_tpex_tables_shape(monkeypatch) -> None:
    twse_fields = [
        "證券代號",
        "證券名稱",
        "外陸資買進股數(不含外資自營商)",
        "外陸資賣出股數(不含外資自營商)",
        "外陸資買賣超股數(不含外資自營商)",
        "外資自營商買進股數",
        "外資自營商賣出股數",
        "外資自營商買賣超股數",
        "投信買進股數",
        "投信賣出股數",
        "投信買賣超股數",
        "自營商買進股數(自行買賣)",
        "自營商賣出股數(自行買賣)",
        "自營商買賣超股數(自行買賣)",
        "自營商買進股數(避險)",
        "自營商賣出股數(避險)",
        "自營商買賣超股數(避險)",
    ]
    twse_row = [
        "2330", "台積電", "100", "80", "20", "3", "2", "1",
        "10", "5", "5", "7", "4", "3", "2", "1", "1",
    ]
    tpex_row = [
        "6488", "環球晶",
        "90", "70", "20", "2", "1", "1", "92", "71", "21",
        "8", "3", "5", "6", "4", "2", "3", "1", "2",
        "9", "5", "4", "30",
    ]
    _install_responses(
        monkeypatch,
        {"stat": "OK", "date": "20260813", "fields": twse_fields, "data": [twse_row]},
        {
            "stat": "ok",
            "date": "20260813",
            "tables": [{"fields": ["代號"] + [f"欄{i}" for i in range(1, 24)], "data": [tpex_row]}],
        },
    )

    frame = fetcher.fetch_institutional_flows(date(2026, 8, 13))

    assert len(frame) == 2
    assert set(frame["source_version"]) == {
        "twse-official-T86",
        "tpex-official-3itrade",
    }
    twse = frame.loc[frame["stock_code"] == "2330"].iloc[0]
    assert int(twse["foreign_investor_buy"]) == 103
    assert int(twse["dealer_net"]) == 4
    tpex = frame.loc[frame["stock_code"] == "6488"].iloc[0]
    assert int(tpex["foreign_investor_net"]) == 21
    assert int(tpex["investment_trust_net"]) == 5
    assert int(tpex["dealer_net"]) == 4
    assert frame["available_date"].isna().all()


def test_credit_fetcher_supports_current_repeated_field_tables_shape(monkeypatch) -> None:
    twse_row = [
        "2330", "台積電", "100", "40", "5", "900", "955", "2000",
        "20", "30", "2", "110", "118", "500", "10", "",
    ]
    tpex_row = [
        "6488", "環球晶", "500", "70", "20", "5", "545", "1000",
        "80", "10", "15", "3", "2", "1", "12", "0", "0", "0", "0", "",
    ]
    _install_responses(
        monkeypatch,
        {
            "stat": "OK",
            "date": "20260813",
            "tables": [
                {"fields": ["項目", "買進", "賣出", "現金償還", "前日餘額", "今日餘額"], "data": [["融資", "1", "1", "0", "1", "1"]]},
                {"fields": ["代號"] + [f"欄{i}" for i in range(1, 16)], "data": [twse_row]},
            ],
        },
        {
            "stat": "ok",
            "date": "20260813",
            "tables": [{"fields": ["代號"] + [f"欄{i}" for i in range(1, 20)], "data": [tpex_row]}],
        },
    )

    frame = fetcher.fetch_credit_transactions(date(2026, 8, 13))

    assert len(frame) == 2
    twse = frame.loc[frame["stock_code"] == "2330"].iloc[0]
    assert int(twse["margin_purchase"]) == 100
    assert int(twse["margin_balance"]) == 955
    assert int(twse["short_sale"]) == 30
    assert int(twse["short_balance"]) == 118
    tpex = frame.loc[frame["stock_code"] == "6488"].iloc[0]
    assert int(tpex["margin_purchase"]) == 70
    assert int(tpex["margin_balance"]) == 545
    assert int(tpex["short_sale"]) == 3
    assert int(tpex["short_balance"]) == 12


def test_credit_fetcher_retries_http_200_payload_until_daily_tables_are_ready(
    monkeypatch,
) -> None:
    twse_row = [
        "2330", "台積電", "100", "40", "5", "900", "955", "2000",
        "20", "30", "2", "110", "118", "500", "10", "",
    ]
    tpex_row = [
        "6488", "環球晶", "500", "70", "20", "5", "545", "1000",
        "80", "10", "15", "3", "2", "1", "12", "0", "0", "0", "0", "",
    ]
    responses = iter(
        _JsonResponse(payload)
        for payload in (
            {"stat": "查無資料", "date": "20260813", "tables": []},
            {
                "stat": "OK",
                "date": "20260813",
                "tables": [
                    {
                        "fields": ["代號"] + [f"欄{i}" for i in range(1, 16)],
                        "data": [twse_row],
                    }
                ],
            },
            {
                "stat": "ok",
                "date": "20260813",
                "tables": [
                    {
                        "fields": ["代號"] + [f"欄{i}" for i in range(1, 20)],
                        "data": [tpex_row],
                    }
                ],
            },
        )
    )
    sleeps: list[int] = []
    monkeypatch.setattr(fetcher, "safe_request", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(fetcher.time, "sleep", sleeps.append)

    frame = fetcher.fetch_credit_transactions(date(2026, 8, 13))

    assert len(frame) == 2
    assert sleeps == [fetcher.OFFICIAL_PAYLOAD_RETRY_SECONDS, 3]


def test_fetcher_fails_whole_date_when_official_response_date_drifts(monkeypatch) -> None:
    _install_responses(
        monkeypatch,
        {"stat": "OK", "date": "20260812", "fields": ["證券代號"], "data": [["2330"]]},
        {
            "stat": "ok",
            "date": "20260813",
            "tables": [{"fields": ["代號"] + [f"欄{i}" for i in range(1, 17)], "data": [["6488"] + ["0"] * 16]}],
        },
    )

    with pytest.raises(RuntimeError, match="官方回應日期不符"):
        fetcher.fetch_institutional_flows(date(2026, 8, 13))


def test_latest_tdcc_fetcher_uses_payload_week_date(monkeypatch) -> None:
    csv_text = _tdcc_complete_csv(symbol="2330", data_date="20260807")
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _CsvResponse(csv_text),
    )

    def fail_openapi(*_args, **_kwargs):
        raise RuntimeError("fallback disabled for this legacy fixture")

    monkeypatch.setattr(fetcher, "_safe_request_bounded_payload", fail_openapi)

    frame = fetcher.fetch_latest_tdcc_shareholding()

    assert len(frame) == 1
    assert frame.iloc[0]["decision_date"] == "2026-08-07"
    assert int(frame.iloc[0]["large_holder_ratio_bp"]) == 1324
    assert int(frame.iloc[0]["retail_holder_ratio_bp"]) == 1796
    assert int(frame.iloc[0]["dispersion_index_bp"]) == 472
    assert fetcher.fetch_tdcc_shareholding(date(2026, 8, 13)).empty


def test_latest_tdcc_fetcher_rejects_ambiguous_payload_dates(monkeypatch) -> None:
    csv_text = "\n".join(
        [
            _tdcc_complete_csv(symbol="2330", data_date="20260807").rstrip(),
            *[
                line
                for line in _tdcc_complete_csv(
                    symbol="2317", data_date="20260808"
                ).splitlines()[1:]
            ],
        ]
    ) + "\n"
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _CsvResponse(csv_text),
    )

    def fail_openapi(*_args, **_kwargs):
        raise RuntimeError("fallback disabled for ambiguous fixture")

    monkeypatch.setattr(fetcher, "_safe_request_bounded_payload", fail_openapi)

    assert fetcher.fetch_latest_tdcc_shareholding().empty


def test_tdcc_legacy_csv_keeps_leading_zero_and_strict_observed_time(monkeypatch) -> None:
    csv_text = _tdcc_complete_csv(symbol="000218", data_date="20260924")
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _CsvResponse(csv_text),
    )

    frame = fetcher.fetch_latest_tdcc_shareholding()

    assert len(frame) == 1
    assert frame.iloc[0]["stock_code"] == "000218"
    assert frame.iloc[0]["source_version"] == "tdcc-official-od-1-5"
    assert int(frame.iloc[0]["large_holder_ratio_bp"]) == 1324
    assert int(frame.iloc[0]["retail_holder_ratio_bp"]) == 1796
    assert frame.iloc[0]["publication_at"] is None
    assert frame.iloc[0]["available_date"] is None
    assert frame.iloc[0]["first_observed_at"] == frame.iloc[0]["available_at"]
    assert datetime.fromisoformat(str(frame.iloc[0]["first_observed_at"])).utcoffset() is not None


@pytest.mark.parametrize(
    "shape_error",
    ["missing_tier", "duplicate_tier", "total_shares", "total_holders"],
)
def test_tdcc_legacy_csv_rejects_incomplete_duplicate_or_nonconserving_17_tiers(
    monkeypatch,
    shape_error: str,
) -> None:
    levels = list(_TDCC_OFFICIAL_00406A_LEVELS)
    if shape_error == "missing_tier":
        levels.pop(15)
    elif shape_error == "duplicate_tier":
        levels.append(levels[15])
    elif shape_error == "total_shares":
        tier, holders, shares, ratio = levels[16]
        levels[16] = (tier, holders, shares + 1, ratio)
    elif shape_error == "total_holders":
        tier, holders, shares, ratio = levels[16]
        levels[16] = (tier, holders + 1, shares, ratio)
    csv_text = _tdcc_complete_csv(
        symbol="00406A",
        data_date="20260924",
        levels=tuple(levels),
    )
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _CsvResponse(csv_text),
    )

    def fail_openapi(*_args, **_kwargs):
        raise RuntimeError("registered fallback unavailable in strictness test")

    monkeypatch.setattr(fetcher, "_safe_request_bounded_payload", fail_openapi)

    assert fetcher.fetch_latest_tdcc_shareholding().empty


@pytest.mark.parametrize(
    ("tier", "ratio"),
    [("99", "50.00"), ("15", "not-a-number")],
)
def test_tdcc_legacy_csv_rejects_invalid_tier_or_numeric_instead_of_zero(
    monkeypatch, tier: str, ratio: str
) -> None:
    levels = list(_TDCC_OFFICIAL_00406A_LEVELS)
    _tier, holders, shares, _ratio = levels[14]
    levels[14] = (
        int(tier),
        holders,
        shares,
        ratio,
    )
    csv_text = _tdcc_complete_csv(
        symbol="000218",
        data_date="20260924",
        levels=tuple(levels),
    )
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _CsvResponse(csv_text),
    )

    def fail_openapi(*_args, **_kwargs):
        raise RuntimeError("registered fallback unavailable in strictness test")

    monkeypatch.setattr(fetcher, "_safe_request_bounded_payload", fail_openapi)

    assert fetcher.fetch_latest_tdcc_shareholding().empty


def _tdcc_openapi_payload() -> bytes:
    rows = [
        {
            "證券代號": "000218",
            "占集保庫存數比例%": ratio,
            "人數": str(holders),
            "\ufeff資料日期": "20260924",
            "股數": str(shares),
            "持股分級": str(tier),
        }
        for tier, holders, shares, ratio in _TDCC_OFFICIAL_00406A_LEVELS
    ]
    return json.dumps(
        rows,
        ensure_ascii=False,
    ).encode("utf-8")


def test_tdcc_registered_openapi_fallback_uses_canonical_parser_and_real_date(
    monkeypatch,
) -> None:
    def fail_legacy(*_args, **_kwargs):
        raise RuntimeError("legacy route unavailable")

    observed = {}
    monkeypatch.setattr(fetcher, "safe_request", fail_legacy)

    def openapi(url, *, max_response_bytes, **_kwargs):
        observed["url"] = url
        observed["cap"] = max_response_bytes
        return (
            _tdcc_openapi_payload(),
            {"Content-Length": str(len(_tdcc_openapi_payload()))},
            200,
        )

    monkeypatch.setattr(fetcher, "_safe_request_bounded_payload", openapi)

    frame = fetcher.fetch_latest_tdcc_shareholding()

    assert observed["url"] == fetcher.TDCC_OPENAPI_URL
    assert observed["cap"] == 16 * 1024 * 1024
    assert len(frame) == 1
    assert frame.iloc[0]["stock_code"] == "000218"
    assert frame.iloc[0]["decision_date"] == "2026-09-24"
    assert frame.iloc[0]["source_version"] == "tdcc-openapi-1-5.v1"
    assert int(frame.iloc[0]["large_holder_ratio_bp"]) == 1324
    assert int(frame.iloc[0]["retail_holder_ratio_bp"]) == 1796
    assert frame.iloc[0]["first_observed_at"] == frame.iloc[0]["available_at"]
    assert frame.iloc[0]["quality"] == "degraded"


def test_tdcc_registered_openapi_fallback_never_substitutes_another_date(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("legacy unavailable")),
    )
    monkeypatch.setattr(
        fetcher,
        "_safe_request_bounded_payload",
        lambda *_args, **_kwargs: (
            _tdcc_openapi_payload(),
            {"Content-Length": str(len(_tdcc_openapi_payload()))},
            200,
        ),
    )

    assert fetcher.fetch_tdcc_shareholding(date(2026, 9, 25)).empty


def test_bounded_tdcc_request_rejects_content_length_over_source_cap(monkeypatch) -> None:
    response = _BytesResponse(
        b"{}",
        headers={"Content-Length": str(fetcher.TDCC_OPENAPI_MAX_BYTES + 1)},
    )
    monkeypatch.setattr(fetcher.requests, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(fetcher._PayloadSizeLimitExceeded, match="Content-Length"):
        fetcher._safe_request_bounded_payload(
            fetcher.TDCC_OPENAPI_URL,
            max_response_bytes=fetcher.TDCC_OPENAPI_MAX_BYTES,
            max_attempts=1,
        )


def test_safe_request_preserves_last_http_status_after_bounded_retries(monkeypatch) -> None:
    responses = [_HttpFailureResponse(520) for _ in range(3)]
    requests_seen = []

    def failed_get(*_args, **_kwargs):
        requests_seen.append(True)
        return responses[len(requests_seen) - 1]

    monkeypatch.setattr(fetcher.requests, "get", failed_get)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="last HTTP status=520"):
        fetcher.safe_request(
            fetcher.TPEX_CREDIT_OPENAPI_URL,
            max_attempts=3,
        )

    assert len(requests_seen) == 3
    assert all(response.closed for response in responses)


@pytest.mark.parametrize("legacy_row_shape", ["short", "invalid_quantity"])
def test_tpex_credit_openapi_fallback_recovers_incomplete_legacy_rows(
    monkeypatch,
    legacy_row_shape: str,
) -> None:
    twse_row = [
        "2330", "台積電", "100", "40", "5", "900", "955", "2000",
        "20", "30", "2", "110", "118", "500", "10", "",
    ]
    twse_payload = {
        "stat": "OK",
        "date": "20260813",
        "tables": [
            {
                "fields": ["項目", "買進", "賣出", "現金償還", "前日餘額", "今日餘額"],
                "data": [["融資", "1", "1", "0", "1", "1"]],
            },
            {"fields": ["代號"] + [f"欄{i}" for i in range(1, 16)], "data": [twse_row]},
        ],
    }
    tpex_payload = [
        {
            "SecuritiesCompanyCode": "6488",
            "Date": "1150813",
            "MarginPurchase": "70",
            "MarginPurchaseBalance": "545",
            "ShortSale": "3",
            "ShortSaleBalance": "12",
        }
    ]
    legacy_row = (
        ["6488", "環球晶"]
        if legacy_row_shape == "short"
        else [
            "6488", "環球晶", "500", "bad-quantity", "20", "5", "545", "1000",
            "80", "10", "15", "3", "2", "1", "12", "0", "0", "0", "0", "",
        ]
    )
    legacy_payload = {
        "stat": "ok",
        "date": "20260813",
        "tables": [
            {
                "fields": ["代號"] + [f"欄{i}" for i in range(1, 20)],
                "data": [legacy_row],
            }
        ],
    }
    requests_seen: list[str] = []

    def route_request(url, *_args, **_kwargs):
        requests_seen.append(url)
        if url.endswith("MI_MARGN"):
            return _JsonResponse(twse_payload)
        if "margin_bal_result.php" in url:
            return _JsonResponse(legacy_payload)
        if url == fetcher.TPEX_CREDIT_OPENAPI_URL:
            return _BytesResponse(json.dumps(tpex_payload).encode("utf-8"))
        raise AssertionError(f"unexpected official route: {url}")

    monkeypatch.setattr(fetcher, "safe_request", route_request)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)

    frame = fetcher.fetch_credit_transactions(date(2026, 8, 13))

    assert len(frame) == 2
    tpex = frame.loc[frame["stock_code"] == "6488"].iloc[0]
    assert tpex["source_version"] == "tpex-mainboard-margin-openapi.v1"
    assert tpex["decision_date"] == "2026-08-13"
    assert int(tpex["margin_balance"]) == 545
    assert int(tpex["short_balance"]) == 12
    assert tpex["first_observed_at"] == tpex["available_at"]
    assert fetcher.TPEX_CREDIT_OPENAPI_URL in requests_seen
    assert len([url for url in requests_seen if "margin_bal_result.php" in url]) >= 1


def test_twse_credit_malformed_rows_block_even_when_tpex_legacy_succeeds(monkeypatch) -> None:
    twse_payload = {
        "stat": "OK",
        "date": "20260813",
        "tables": [
            {
                "fields": ["代號"] + [f"欄{i}" for i in range(1, 16)],
                "data": [["2330", "short-row"]],
            }
        ],
    }
    tpex_row = [
        "6488", "環球晶", "500", "70", "20", "5", "545", "1000",
        "80", "10", "15", "3", "2", "1", "12", "0", "0", "0", "0", "",
    ]
    tpex_payload = {
        "stat": "ok",
        "date": "20260813",
        "tables": [{"fields": ["代號"] + [f"欄{i}" for i in range(1, 20)], "data": [tpex_row]}],
    }

    def route_request(url, *_args, **_kwargs):
        if url.endswith("MI_MARGN"):
            return _JsonResponse(twse_payload)
        if "margin_bal_result.php" in url:
            return _JsonResponse(tpex_payload)
        raise AssertionError(f"unexpected official route: {url}")

    monkeypatch.setattr(fetcher, "safe_request", route_request)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="TWSE MI_MARGN"):
        fetcher.fetch_credit_transactions(date(2026, 8, 13))


def test_tpex_credit_openapi_rejects_latest_payload_from_another_date(monkeypatch) -> None:
    payload = [
        {
            "SecuritiesCompanyCode": "6488",
            "Date": "1150812",
            "MarginPurchase": "70",
            "MarginPurchaseBalance": "545",
            "ShortSale": "3",
            "ShortSaleBalance": "12",
        }
    ]
    monkeypatch.setattr(
        fetcher,
        "safe_request",
        lambda *_args, **_kwargs: _BytesResponse(json.dumps(payload).encode("utf-8")),
    )

    with pytest.raises(ValueError, match="observation date mismatch"):
        fetcher._fetch_tpex_credit_openapi(date(2026, 8, 13))


def test_tpex_credit_openapi_http_520_remains_retryable_external_failure(
    monkeypatch,
) -> None:
    twse_row = [
        "2330", "台積電", "100", "40", "5", "900", "955", "2000",
        "20", "30", "2", "110", "118", "500", "10", "",
    ]
    twse_payload = {
        "stat": "OK",
        "date": "20260813",
        "tables": [
            {
                "fields": ["項目", "買進", "賣出", "現金償還", "前日餘額", "今日餘額"],
                "data": [["融資", "1", "1", "0", "1", "1"]],
            },
            {"fields": ["代號"] + [f"欄{i}" for i in range(1, 16)], "data": [twse_row]},
        ],
    }

    def route_request(url, *_args, **_kwargs):
        if url.endswith("MI_MARGN"):
            return _JsonResponse(twse_payload)
        if "margin_bal_result.php" in url:
            return _JsonResponse(
                {
                    "stat": "ok",
                    "date": "20260813",
                    "tables": [
                        {
                            "fields": ["代號"] + [f"欄{i}" for i in range(1, 20)],
                            "data": [["6488", "short-row"]],
                        }
                    ],
                }
            )
        if url == fetcher.TPEX_CREDIT_OPENAPI_URL:
            raise RuntimeError("registered TPEx OpenAPI HTTP 520")
        raise AssertionError(f"unexpected official route: {url}")

    monkeypatch.setattr(fetcher, "safe_request", route_request)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="registered TPEx OpenAPI HTTP 520"):
        fetcher.fetch_credit_transactions(date(2026, 8, 13))
