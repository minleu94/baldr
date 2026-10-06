from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import requests
from urllib3.exceptions import MaxRetryError
from urllib3.response import HTTPResponse

import scripts.refresh_current_market_status_observation as refresh_script
from data_module.current_market_status_observation import (
    CurrentMarketStatusError,
    CurrentMarketStatusReader,
    MarketStatusEvidence,
    build_snapshot,
    decode_official_rows,
    explicit_payload_source_dates,
    extract_resume_date,
    extract_symbol,
    extract_row_dates,
    extract_termination_date,
    parse_official_market_notice,
    sha256_bytes,
)
from scripts.refresh_current_market_status_observation import (
    SourceSpec,
    capture_sources,
    load_official_notice_source_specs,
    official_notice_source_spec,
    source_specs,
    twse_official_notice_source_spec,
    _fetch_bytes,
)


def _install_scripted_http_session(
    monkeypatch: pytest.MonkeyPatch,
    response_for_attempt: Any,
) -> dict[str, Any]:
    counters: dict[str, Any] = {"attempts": 0, "sessions": 0, "retry_policies": []}

    class _Response:
        def __init__(self, status_code: int, body: bytes, url: str) -> None:
            self.status_code = status_code
            self.content = body
            self.headers = {
                "Content-Length": str(len(body)),
                "Content-Type": "application/json",
                "Content-Encoding": "identity",
            }
            self.url = url

    class _Session:
        def mount(self, prefix: str, adapter: Any) -> None:
            assert prefix == "https://"
            self.retry = adapter.max_retries
            counters["retry_policies"].append(self.retry)

        def request(self, method: str, url: str, **kwargs: Any) -> _Response:
            retry = self.retry
            for _ in range(16):
                status_code, body = response_for_attempt(counters["attempts"])
                counters["attempts"] += 1
                if retry.is_retry(method.upper(), status_code, has_retry_after=False):
                    try:
                        retry = retry.increment(
                            method=method.upper(),
                            url=url,
                            response=HTTPResponse(status=status_code, headers={}),
                        )
                    except MaxRetryError as error:
                        raise requests.exceptions.RetryError(error) from error
                    continue
                return _Response(status_code, body, url)
            raise AssertionError("simulated HTTP retry loop was not bounded")

        def close(self) -> None:
            return None

    def session_factory() -> _Session:
        counters["sessions"] += 1
        return _Session()

    monkeypatch.setattr(refresh_script.requests, "Session", session_factory)
    return counters


def _evidence(
    symbol: str,
    evidence_type: str,
    *,
    effective_from: str | None = None,
    market: str | None = "twse",
) -> MarketStatusEvidence:
    raw = b'{"fixture":true}'
    return MarketStatusEvidence(
        symbol=symbol,
        source_id=f"official.{evidence_type}",
        evidence_type=evidence_type,
        observed_at="2026-10-04T10:00:00+00:00",
        raw_sha256=sha256_bytes(raw),
        source_url="https://official.example.test/feed",
        effective_from=effective_from,
        market=market,
        name=f"Name {symbol}",
    )


def test_current_status_reader_keeps_unknown_separate_from_listing_and_quote_absence() -> None:
    snapshot = build_snapshot(
        observed_at=datetime(2026, 10, 4, 10, tzinfo=timezone.utc),
        source_captures=[],
        evidence=[
            _evidence("2323", "current_roster"),
            _evidence("2323", "trading_restriction"),
            _evidence("2867", "terminated", effective_from="2026-09-01"),
            _evidence("8183", "terminated", effective_from="2026-10-05"),
        ],
    )
    reader = CurrentMarketStatusReader(snapshot)

    assert reader.get("2323").listing_status == "listed"
    assert len(reader.get("2323").trading_restrictions) == 1
    assert reader.get("2867").listing_status == "delisted"
    assert reader.get("8183").listing_status == "unknown"
    missing = reader.get("5301")
    assert missing.listing_status == "unknown"
    assert missing.status_reason == "not_observed_in_captured_sources"
    assert missing.pit_eligible is False


def test_capture_uses_compact_paths_under_deep_windows_output_root(tmp_path: Path) -> None:
    root_text = str(tmp_path)
    extra_length = max(1, 175 - len(root_text) - 1)
    output_root = tmp_path / ("d" * extra_length)
    spec = SourceSpec(
        "tpex.official_notice.0123456789abcdef",
        "https://www.tpex.org.tw/openapi/v1/fixture",
        "listing_status",
        "tpex",
        "fixture",
    )
    body = b'{"data":[]}'

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        return body, 200, "application/json", url, datetime(2026, 10, 4, tzinfo=timezone.utc), {}

    snapshot, run_dir = capture_sources(output_dir=output_root, specs=(spec,), fetcher=fetcher)
    raw_path = Path(snapshot["source_captures"][0]["raw_path"])

    assert run_dir.name.startswith("cms_")
    assert raw_path.name == "s0001.bin"
    assert len(str(raw_path)) < 260
    expected_sha256 = snapshot["source_captures"][0]["raw_sha256"].removeprefix("sha256:")
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == expected_sha256


def test_twse_fields_data_shape_and_source_date_are_decoded_without_using_event_dates() -> None:
    raw = json.dumps(
        {
            "stat": "OK",
            "date": "20261002",
            "fields": ["證券代號", "暫停交易起日", "恢復交易日"],
            "data": [["2323", "2026/10/01", "2026/10/08"]],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    rows = decode_official_rows(raw, "application/json")

    assert extract_symbol(rows[0]) == "2323"
    assert explicit_payload_source_dates(raw) == ["2026-10-02"]
    assert extract_symbol({"Date": "1151002"}) is None


def test_resume_date_is_not_mistaken_for_last_suspended_date() -> None:
    row = {"暫停交易起日": "115/09/23", "恢復交易日": "115/10/05"}
    assert extract_row_dates(row) == (
        datetime(2026, 9, 23).date(),
        None,
    )
    assert extract_resume_date(row) == datetime(2026, 10, 5).date()


def test_twse_twawu_official_row_preserves_suspension_and_resume_dates(
    tmp_path: Path,
) -> None:
    # 此列照錄自 TWSE TWTAWU captured raw：
    # raw/s0004.bin，SHA-256 4b11854bfbd8785aaed1a97e795a82cf0236bc2f37f98803fb185de4ffba317d。
    # 官方欄位名與值保持原樣，避免只用泛化別名遮住 schema 漏接。
    raw = json.dumps(
        {
            "stat": "OK",
            "fields": [
                "編號",
                "證券代號",
                "證券名稱",
                "暫停交易日期",
                "暫停交易時間",
                "恢復交易日期",
                "恢復交易時間",
            ],
            "data": [[1, "030089", "貿聯統一56購04", "115/06/10", "8:00", "115/06/11", "8:00"]],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    spec = SourceSpec(
        "twse.suspension_events",
        "https://www.twse.com.tw/exchangeReport/TWTAWU?response=json&startDate=20260407&endDate=20261004",
        "trading_restriction",
        "twse",
        "TWSE TWTAWU fixture copied from captured official row",
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        return raw, 200, "application/json;charset=UTF-8", url, datetime(
            2026, 10, 4, tzinfo=timezone.utc
        ), {}

    snapshot, run_dir = capture_sources(
        output_dir=tmp_path / "twse-twawu-date-fixture",
        specs=(spec,),
        fetcher=fetcher,
    )
    reader = CurrentMarketStatusReader.from_path(run_dir / "snapshot.json")
    restriction = reader.get("030089").trading_restrictions[0]

    assert snapshot["partial_failure"] is False
    assert restriction["effective_from"] == "2026-06-10"
    assert restriction["effective_to"] is None
    assert restriction["resumed_on"] == "2026-06-11"


def test_tpex_suspension_history_keeps_resume_date_distinct_from_halt_end(
    tmp_path: Path,
) -> None:
    raw = json.dumps(
        [
            {
                "Date": "115",
                "SecuritiesCompanyCode": "1234",
                "CompanyName": "fixture",
                "DateOfSuspendedTrading": "1150923",
                "DateOfResumedTrading": "1151005",
            }
        ],
        ensure_ascii=False,
    ).encode("utf-8")
    spec = SourceSpec(
        "tpex.suspension_events",
        "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history",
        "trading_restriction",
        "tpex",
        "fixture",
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        return raw, 200, "application/json", url, datetime(2026, 10, 4, tzinfo=timezone.utc), {}

    snapshot, _ = capture_sources(
        output_dir=tmp_path / "suspension-fixture",
        specs=(spec,),
        fetcher=fetcher,
    )

    restriction = CurrentMarketStatusReader(snapshot).get("1234").trading_restrictions[0]
    assert restriction["effective_from"] == "2026-09-23"
    assert restriction["effective_to"] is None
    assert restriction["resumed_on"] == "2026-10-05"
    assert restriction["restriction_state"] == "resumed_on_source_date"


def test_official_termination_html_table_is_parsed() -> None:
    # 保留自 2026-10-04 TWSE 官方終止上市表格的實際雙層表頭與欄位形狀。
    html = """<!doctype html><html><table class="grid links"><thead>
    <tr><th colspan='3'><div>終止上市公司</div></th></tr>
    <tr><th>終止上市日期</th><th>公司名稱</th><th>上市編號</th></tr></thead><tbody>
    <tr align="center"><td>115年09月01日</td><td>三商壽</td><td>2867</td></tr>
    </tbody></table></html>"""
    rows = decode_official_rows(html.encode("utf-8"), "text/html")
    assert extract_symbol(rows[0]) == "2867"
    assert extract_termination_date(rows[0]) == datetime(2026, 9, 1).date()


def _captured_tpex_terminated_listing_raw() -> bytes:
    # Exact 1,332-byte body from the 2026-10-04 official capture
    # (SHA-256 86b5cf847348056b6220d293b6a569e897939b57b6c3fc9ea5b5d1b6293036a2).
    return base64.b64decode(
        "eyJ0YWJsZXMiOlt7ImZpZWxkcyI6WyLogqHnpajku6PomZ8iLCLlhazlj7jlkI3nqLEiLCLntYLmraLkuIrmq4Pm"
        "l6XmnJ8iLCLntYLmraLkuIrmq4Pljp/lm6AiLCLlhazlj7jos4fmlpnntrLlnYAiXSwiZGF0YSI6W1siODE4MyIs"
        "IuWPsOeBo+eyvuaYn+enkeaKgOiCoeS7veaciemZkOWFrOWPuCIsIjExNS0xMC0wMSIsIuacrOS4reW/g+itieWI"
        "uOWVhueHn+alreiZleaJgOiyt+izo+acieWDueitieWIuOalreWLmeimj+WJh+esrDEy5qKd5LmLMuOAgeesrDEy"
        "5qKd5LmLMTDlj4rnrKwxNeaineS5izE4IiwiaHR0cHM6Ly9tb3BzLnR3c2UuY29tLnR3L21vcHMvIy93ZWIvdDA1"
        "c3QwMyJdLFsiNTM3MSIsIuS4reW8t+WFiembu+iCoeS7veaciemZkOWFrOWPuCIsIjExNS0wOS0wMyIsIuS+neac"
        "rOS4reW/g+itieWIuOWVhueHn+alreiZleaJgOiyt+izo+acieWDueitieWIuOalreWLmeimj+WJh+esrDE15qKd"
        "5LmLMTLjgIExNOOAgTE15Y+KMTbopo/lrpoiLCJodHRwczovL21vcHMudHdzZS5jb20udHcvbW9wcy8jL3dlYi90"
        "MDVzdDAzIl0sWyI0MTMwIiwi5YGl5Lqe55Sf54mp56eR5oqA6IKh5Lu95pyJ6ZmQ5YWs5Y+4IiwiMTE1LTA3LTI4"
        "Iiwi5pys5Lit5b+D6K2J5Yi45ZWG54ef5qWt6JmV5omA6LK36LOj5pyJ5YO56K2J5Yi45qWt5YuZ6KaP5YmH56ys"
        "MTXmop3kuYsxMiIsImh0dHBzOi8vbW9wcy50d3NlLmNvbS50dy9tb3BzLyMvd2ViL3QwNXN0MDMiXSxbIjUyMzYi"
        "LCLlh4zpmb3libXmlrDnp5HmioDogqHku73mnInpmZDlhazlj7giLCIxMTUtMDctMTYiLCLmnKzkuK3lv4PorYnl"
        "iLjllYbnh5/mpa3omZXmiYDosrfos6PmnInlg7norYnliLjmpa3li5nopo/liYfnrKwxMuaineS5izLnrKwx6aCF"
        "56ysMeasviIsImh0dHBzOi8vbW9wcy50d3NlLmNvbS50dy9tb3BzLyMvd2ViL3QwNXN0MDMiXSxbIjM0MjYiLCLl"
        "j7DoiIjpm7vlrZDkvIHmpa3ogqHku73mnInpmZDlhazlj7giLCIxMTUtMDYtMDgiLCLmnKzkuK3lv4PorYnliLjl"
        "lYbnh5/mpa3omZXmiYDosrfos6PmnInlg7norYnliLjmpa3li5nopo/liYfnrKwxNeaineS5izE4IiwiaHR0cHM6"
        "Ly9tb3BzLnR3c2UuY29tLnR3L21vcHMvIy93ZWIvdDA1c3QwMyJdLFsiNDk4NyIsIuenkeiqoOiCoeS7veaciemZ"
        "kOWFrOWPuCIsIjExNS0wNS0yOSIsIuacrOS4reW/g+itieWIuOWVhueHn+alreiZleaJgOiyt+izo+acieWDueit"
        "ieWIuOalreWLmeimj+WJh+esrDE15qKd5LmLMTgiLCJodHRwczovL21vcHMudHdzZS5jb20udHcvbW9wcy8jL3dl"
        "Yi90MDVzdDAzIl1dLCJ0b3RhbENvdW50Ijo2LCJ0aXRsZSI6IiIsIm5vdGVzIjpbXX1dLCJkYXRlIjoiMjAyNiIs"
        "InN0YXQiOiJvayJ9"
    )


def test_tpex_terminated_listing_official_tables_capture_is_typed_and_current_only(
    tmp_path: Path,
) -> None:
    raw = _captured_tpex_terminated_listing_raw()
    assert hashlib.sha256(raw).hexdigest() == (
        "86b5cf847348056b6220d293b6a569e897939b57b6c3fc9ea5b5d1b6293036a2"
    )
    observed_at = datetime(2026, 10, 4, 12, 1, 40, tzinfo=timezone.utc)
    spec = next(
        item for item in source_specs(observed_on=observed_at)
        if item.source_id == "tpex.terminated_listing"
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        assert url == "https://www.tpex.org.tw/www/zh-tw/company/deListed"
        assert method == "POST"
        assert dict(params or {})["response"] == "json"
        return raw, 200, "application/json;charset=UTF-8", url, observed_at, {}

    snapshot, run_dir = capture_sources(
        output_dir=tmp_path / "tpex-terminated-listing",
        specs=(spec,),
        fetcher=fetcher,
    )
    capture = snapshot["source_captures"][0]
    reader = CurrentMarketStatusReader.from_path(run_dir / "snapshot.json")
    observation = reader.get("5371")
    termination = observation.status_evidence[0]

    assert snapshot["scope"] == "current_only"
    assert snapshot["pit_eligible"] is False
    assert snapshot["partial_failure"] is False
    assert capture["parse_status"] == "parsed"
    assert capture["row_count"] == 6
    assert capture["raw_sha256"] == (
        "sha256:86b5cf847348056b6220d293b6a569e897939b57b6c3fc9ea5b5d1b6293036a2"
    )
    assert observation.listing_status == "delisted"
    assert observation.name == "中強光電股份有限公司"
    assert termination["effective_from"] == "2026-09-03"
    assert termination["market"] == "tpex"
    assert termination["raw_sha256"] == capture["raw_sha256"]


def test_tpex_terminated_listing_tables_reject_empty_bad_date_missing_field_and_short_row() -> None:
    raw = _captured_tpex_terminated_listing_raw()
    baseline = json.loads(raw.decode("utf-8"))
    cases: list[dict[str, object]] = []

    empty = json.loads(json.dumps(baseline))
    empty["tables"][0]["data"] = []
    empty["tables"][0]["totalCount"] = 0
    cases.append(empty)

    invalid_date = json.loads(json.dumps(baseline))
    target = next(row for row in invalid_date["tables"][0]["data"] if row[0] == "5371")
    target[2] = "115-13-40"
    cases.append(invalid_date)

    missing_field = json.loads(json.dumps(baseline))
    missing_field["tables"][0]["fields"].pop(2)
    for row in missing_field["tables"][0]["data"]:
        row.pop(2)
    cases.append(missing_field)

    short_row = json.loads(json.dumps(baseline))
    short_row["tables"][0]["data"][0].pop()
    cases.append(short_row)

    truncated = json.loads(json.dumps(baseline))
    truncated["tables"][0]["totalCount"] = len(truncated["tables"][0]["data"]) + 1
    cases.append(truncated)

    for payload in cases:
        with pytest.raises(CurrentMarketStatusError):
            decode_official_rows(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json;charset=UTF-8",
            )


def test_tpex_cmode_date_and_named_suspension_are_typed(tmp_path: Path) -> None:
    raw = json.dumps(
        [
            {
                "Date": "1151002",
                "SecuritiesCompanyCode": "3085",
                "CompanyName": "新零售",
                "AlteredTrading": "",
                "PeriodicTrading": "",
                "ManagedStock": "",
                "MatchingFrequency": "",
                "SuspensionOfTrading": "Ｙ",
                " FinancialAnnouncements": "Ｙ",
            }
        ],
        ensure_ascii=False,
    ).encode("utf-8")
    spec = SourceSpec(
        "tpex.cmode_current",
        "https://www.tpex.org.tw/openapi/v1/tpex_cmode",
        "trading_restriction",
        "tpex",
        "fixture",
        ("Date",),
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        return raw, 200, "application/json", url, datetime(2026, 10, 4, 0, tzinfo=timezone.utc), {"content-length": str(len(raw))}

    snapshot, _ = capture_sources(output_dir=tmp_path / "status-fixture", specs=(spec,), fetcher=fetcher)
    observation = CurrentMarketStatusReader(snapshot).get("3085")
    assert observation.listing_status == "listed"
    assert observation.source_data_dates == ("2026-10-02",)
    restriction = observation.trading_restrictions[0]
    assert restriction["restriction_type"] == "trading_suspension"
    assert restriction["restriction_state"] == "reported_on_source_date"
    assert restriction["effective_from"] is None


def test_twse_suspension_query_never_requests_future_market_dates() -> None:
    specs = source_specs(observed_on=datetime(2026, 10, 4, 0, tzinfo=timezone.utc))
    twse = next(item for item in specs if item.source_id == "twse.suspension_events")
    assert "endDate=20261004" in twse.url
    assert "endDate=202611" not in twse.url


def test_fetch_bytes_retries_tpex_520_then_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(refresh_script.time, "sleep", lambda _: None)
    outcomes = [(520, b"transient gateway error"), (200, b'{"data":[]}')]
    counters = _install_scripted_http_session(
        monkeypatch,
        lambda index: outcomes[min(index, len(outcomes) - 1)],
    )

    body, status, content_type, final_url, _, headers = _fetch_bytes(
        "https://official.example.test/status",
        timeout=1.0,
    )

    assert (body, status, content_type, final_url) == (
        b'{"data":[]}',
        200,
        "application/json",
        "https://official.example.test/status",
    )
    assert headers["content-length"] == str(len(body))
    assert counters["attempts"] == 2
    assert counters["sessions"] == 1
    retry = counters["retry_policies"][0]
    assert retry.total == retry.connect == retry.read == retry.status == 3
    assert retry.backoff_factor == 0.4
    assert retry.respect_retry_after_header is True
    assert retry.allowed_methods == frozenset({"GET"})
    assert retry.status_forcelist == (429, 500, 502, 503, 504, 520)


def test_fetch_bytes_http_520_exhaustion_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(refresh_script.time, "sleep", lambda _: None)
    counters = _install_scripted_http_session(
        monkeypatch,
        lambda _: (520, b"transient gateway error"),
    )

    with pytest.raises(requests.exceptions.RetryError):
        _fetch_bytes("https://official.example.test/status", timeout=1.0)

    # Three existing outer attempts, each with the initial request plus three
    # urllib3 retries. No new retry loop or attempt receipt is introduced.
    assert counters["attempts"] == 12
    assert counters["sessions"] == 1


def test_fetch_bytes_http_400_remains_non_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(refresh_script.time, "sleep", lambda _: None)
    counters = _install_scripted_http_session(
        monkeypatch,
        lambda _: (400, b"bad request"),
    )

    body, status, *_ = _fetch_bytes(
        "https://official.example.test/status",
        timeout=1.0,
    )

    assert status == 400
    assert body == b"bad request"
    assert counters["attempts"] == 1
    assert counters["sessions"] == 1


def test_reader_rejects_pit_eligible_snapshot() -> None:
    with pytest.raises(CurrentMarketStatusError, match="scope_invariant"):
        CurrentMarketStatusReader(
            {
                "schema_version": "current-market-status-observation.v1",
                "scope": "current_only",
                "pit_eligible": True,
                "observed_at": "2026-10-04T00:00:00+00:00",
                "securities": [],
            }
        )


def test_refresh_command_capture_uses_explicit_output_and_preserves_raw_hash(tmp_path: Path) -> None:
    body = json.dumps([{"證券代號": "1234", "公司名稱": "Example"}], ensure_ascii=False).encode("utf-8")
    spec = SourceSpec(
        "fixture.roster", "https://official.example.test/roster", "current_roster", "twse"
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        assert url == spec.url
        assert timeout == 4.0
        assert method == "GET"
        return body, 200, "application/json", url, datetime(2026, 10, 4, 10, tzinfo=timezone.utc), {"content-length": str(len(body))}

    snapshot, run_dir = capture_sources(
        output_dir=tmp_path / "qa-only",
        timeout=4.0,
        specs=(spec,),
        fetcher=fetcher,
    )

    assert snapshot["scope"] == "current_only"
    assert snapshot["pit_eligible"] is False
    raw_path = Path(snapshot["source_captures"][0]["raw_path"])
    assert raw_path.is_relative_to(run_dir)
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == snapshot["source_captures"][0]["raw_sha256"].removeprefix("sha256:")
    assert CurrentMarketStatusReader.from_path(run_dir / "snapshot.json").get("1234").listing_status == "listed"
    assert CurrentMarketStatusReader.from_pointer(tmp_path / "qa-only" / "current_market_status_pointer.json").get("1234").listing_status == "listed"

    raw_path.write_bytes(b"tampered")
    with pytest.raises(CurrentMarketStatusError, match="raw_hash_mismatch"):
        CurrentMarketStatusReader.from_path(run_dir / "snapshot.json")


def _tpex_notice_html(subject: str, body: str) -> bytes:
    return f"""<!doctype html><html><body>
    <div>財團法人中華民國證券櫃檯買賣中心</div><div>公告</div>
    <div>發文日期：中華民國115年9月3日</div>
    <div>發文字號：證櫃監字第11500054131號</div>
    <div>主旨：{subject}</div><div>依據：官方規則</div><div>公告事項：{body}</div>
    </body></html>""".encode("utf-8")


def test_official_notice_parser_only_emits_explicit_body_statements() -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=timezone.utc)
    source_url = "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html"
    suspension_only = _tpex_notice_html(
        "公告甲公司股票（證券代號：5371）自115年8月24日起停止櫃檯買賣。",
        "申請書中股份轉換日期115年9月3日。",
    )
    statements = parse_official_market_notice(
        suspension_only, source_url=source_url, observed_at=observed_at
    )
    assert [(item.statement_type, item.effective_date.isoformat()) for item in statements] == [
        ("trading_suspension", "2026-08-24")
    ]
    assert statements[0].published_date.isoformat() == "2026-09-03"
    assert statements[0].notice_reference == "證櫃監字第11500054131號"

    explicit_both = _tpex_notice_html(
        "公告乙公司股份有限公司股票（股票代號：8183）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。",
        "本中心受理該公司115年8月17日終止上櫃申請書。",
    )
    statements = parse_official_market_notice(
        explicit_both, source_url=source_url, observed_at=observed_at
    )
    assert {(item.statement_type, item.effective_date.isoformat()) for item in statements} == {
        ("trading_suspension", "2026-09-23"),
        ("listing_termination", "2026-10-01"),
    }
    assert {item.name for item in statements} == {"乙公司股份有限公司"}


def test_official_notice_rejects_untrusted_url_ambiguous_symbol_and_future_publication() -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=timezone.utc)
    body = _tpex_notice_html(
        "公告甲公司股票（證券代號：5371）自115年8月24日起停止櫃檯買賣。", ""
    )
    with pytest.raises(CurrentMarketStatusError, match="url_not_allowlisted"):
        parse_official_market_notice(
            body,
            source_url="https://example.test/storage/eb_data/11509/11500054131.html",
            observed_at=observed_at,
        )
    ambiguous = body.replace(
        "證券代號：5371".encode("utf-8"),
        "證券代號：5371）／（證券代號：8183".encode("utf-8"),
    )
    with pytest.raises(CurrentMarketStatusError, match="symbol_ambiguous"):
        parse_official_market_notice(
            ambiguous,
            source_url="https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html",
            observed_at=observed_at,
        )
    future = body.replace("115年9月3日".encode("utf-8"), "115年10月5日".encode("utf-8"))
    with pytest.raises(CurrentMarketStatusError, match="publication_after_capture"):
        parse_official_market_notice(
            future,
            source_url="https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html",
            observed_at=observed_at,
        )


def test_official_notice_capture_keeps_publication_effective_and_raw_lineage(tmp_path: Path) -> None:
    source_url = "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html"
    body = _tpex_notice_html(
        "公告乙公司股票（股票代號：8183）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。",
        "",
    )
    spec = official_notice_source_spec(source_url)

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        return body, 200, "text/html; charset=utf-8", url, datetime(2026, 10, 4, tzinfo=timezone.utc), {"content-length": str(len(body))}

    snapshot, run_dir = capture_sources(
        output_dir=tmp_path / "notice-capture",
        specs=(spec,),
        fetcher=fetcher,
    )
    observation = CurrentMarketStatusReader.from_path(run_dir / "snapshot.json").get("8183")
    assert snapshot["scope"] == "current_only"
    assert snapshot["pit_eligible"] is False
    assert observation.listing_status == "delisted"
    assert len(observation.status_evidence) == 2
    termination = next(item for item in observation.status_evidence if item["evidence_type"] == "terminated")
    assert termination["published_date"] == "2026-09-03"
    assert termination["effective_from"] == "2026-10-01"
    assert termination["notice_reference"] == "證櫃監字第11500054131號"
    assert termination["raw_sha256"] == snapshot["source_captures"][0]["raw_sha256"]
    restriction = observation.trading_restrictions[0]
    assert restriction["published_date"] == "2026-09-03"
    assert restriction["effective_from"] == "2026-09-23"


def _twse_notice_api_payload(
    *,
    symbol: str,
    company: str,
    publication_date: str,
    reference: str,
    halt_start: str,
    halt_end: str,
    new_share_start: str,
) -> bytes:
    payload = {
        "stat": "ok",
        "fields": ["發文機關", "發文日期", "發文字號", "主旨", "依據", "公告事項"],
        "data": [[
            "臺灣證券交易所股份有限公司 公告",
            publication_date,
            reference,
            f"{company}股份有限公司（公司代號：{symbol}）減資換發股票停止舊股票上市買賣及新股票開始上市買賣日期。",
            "依公司公告申報書。",
            "四、舊股票停止在市場買賣日期："
            f"自{halt_start}起至{halt_end}止。\n"
            f"六、新股票上市開始買賣暨舊股票終止上市日期：{new_share_start}。",
        ]],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize(
    (
        "symbol",
        "company",
        "publication_date",
        "reference",
        "halt_start",
        "halt_end",
        "new_share_start",
        "expected_start",
        "expected_end",
        "expected_resume",
    ),
    [
        (
            "2323", "中環", "中華民國115年09月10日", "臺證上一字第1150018271號",
            "115年10月01日", "115年10月08日", "115年10月12日",
            "2026-10-01", "2026-10-08", "2026-10-12",
        ),
        (
            "2601", "益航", "中華民國115年09月09日", "臺證上一字第1150018275號",
            "115年09月23日", "115年10月03日", "115年10月05日",
            "2026-09-23", "2026-10-03", "2026-10-05",
        ),
    ],
)
def test_twse_announcement_api_notice_keeps_effective_interval_and_resume_distinct(
    symbol: str,
    company: str,
    publication_date: str,
    reference: str,
    halt_start: str,
    halt_end: str,
    new_share_start: str,
    expected_start: str,
    expected_end: str,
    expected_resume: str,
) -> None:
    source_url = (
        "https://www.twse.com.tw/rwd/zh/announcement/announcement_detail"
        "?id=DAEFD7C7ACC511F19A80005056BE3760&response=json"
    )
    raw = _twse_notice_api_payload(
        symbol=symbol,
        company=company,
        publication_date=publication_date,
        reference=reference,
        halt_start=halt_start,
        halt_end=halt_end,
        new_share_start=new_share_start,
    )

    statements = parse_official_market_notice(
        raw,
        source_url=source_url,
        observed_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
    )

    assert len(statements) == 1
    statement = statements[0]
    assert statement.symbol == symbol
    assert statement.statement_type == "trading_suspension"
    assert statement.published_date.isoformat() == (
        "2026-09-10" if symbol == "2323" else "2026-09-09"
    )
    assert statement.notice_reference == reference
    assert statement.effective_date.isoformat() == expected_start
    assert statement.effective_to.isoformat() == expected_end
    assert statement.resumed_on.isoformat() == expected_resume
    # Same-symbol share exchange is not a delisting statement for the company.
    assert all(item.statement_type != "listing_termination" for item in statements)


def test_twse_announcement_source_spec_uses_fixed_official_api_and_reader_keeps_evidence(
    tmp_path: Path,
) -> None:
    page_url = (
        "https://www.twse.com.tw/zh/announcement/announcement/detail.html"
        "?DAEFD7C7ACC511F19A80005056BE3760="
    )
    spec = twse_official_notice_source_spec(page_url)
    assert spec.url == "https://www.twse.com.tw/rwd/zh/announcement/announcement_detail"
    assert dict(spec.request_params) == {
        "id": "DAEFD7C7ACC511F19A80005056BE3760",
        "response": "json",
    }
    assert spec.source_page_url == page_url
    body = _twse_notice_api_payload(
        symbol="2323",
        company="中環",
        publication_date="中華民國115年09月10日",
        reference="臺證上一字第1150018271號",
        halt_start="115年10月01日",
        halt_end="115年10月08日",
        new_share_start="115年10月12日",
    )

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        assert url == spec.url
        assert method == "GET"
        assert params == dict(spec.request_params)
        return (
            body,
            200,
            "application/json;charset=UTF-8",
            f"{url}?id={params['id']}&response=json",
            datetime(2026, 10, 4, 1, tzinfo=timezone.utc),
            {"content-length": str(len(body))},
        )

    snapshot, run_dir = capture_sources(
        output_dir=tmp_path / "twse-notice-current",
        specs=(spec,),
        fetcher=fetcher,
    )
    reader = CurrentMarketStatusReader.from_path(run_dir / "snapshot.json")
    observation = reader.get("2323")
    restriction = observation.trading_restrictions[0]
    assert observation.scope == "current_only"
    assert observation.pit_eligible is False
    assert observation.listing_status == "unknown"
    assert restriction["effective_from"] == "2026-10-01"
    assert restriction["effective_to"] == "2026-10-08"
    assert restriction["resumed_on"] == "2026-10-12"
    assert restriction["published_date"] == "2026-09-10"
    assert restriction["notice_reference"] == "臺證上一字第1150018271號"
    assert restriction["raw_sha256"] == snapshot["source_captures"][0]["raw_sha256"]
    assert Path(snapshot["source_captures"][0]["raw_path"]).is_file()


def test_twse_announcement_api_rejects_duplicate_or_unbound_query_parameters() -> None:
    observed_at = datetime(2026, 10, 4, tzinfo=timezone.utc)
    raw = _twse_notice_api_payload(
        symbol="2323",
        company="中環",
        publication_date="中華民國115年09月10日",
        reference="臺證上一字第1150018271號",
        halt_start="115年10月01日",
        halt_end="115年10月08日",
        new_share_start="115年10月12日",
    )
    for source_url in (
        "https://www.twse.com.tw/rwd/zh/announcement/announcement_detail"
        "?id=DAEFD7C7ACC511F19A80005056BE3760&id=DAEFD7C7ACC511F19A80005056BE3760&response=json",
        "https://www.twse.com.tw/rwd/zh/announcement/announcement_detail"
        "?id=DAEFD7C7ACC511F19A80005056BE3760&response=json&extra=1",
    ):
        with pytest.raises(CurrentMarketStatusError, match="url_not_allowlisted"):
            parse_official_market_notice(raw, source_url=source_url, observed_at=observed_at)


def test_repository_notice_manifest_is_loaded_for_each_natural_source_registry_call() -> None:
    configured = load_official_notice_source_specs()
    assert len(configured) == 4
    sources = source_specs(observed_on=datetime(2026, 10, 4, tzinfo=timezone.utc))
    notice_specs = [spec for spec in sources if spec.evidence_type == "official_notice"]
    assert {spec.source_id for spec in notice_specs} == {spec.source_id for spec in configured}
    assert {spec.source_page_url for spec in notice_specs if spec.source_page_url} == {
        "https://www.twse.com.tw/zh/announcement/announcement/detail.html?DAEFD7C7ACC511F19A80005056BE3760=",
        "https://www.twse.com.tw/zh/announcement/announcement/detail.html?2BFE5104AC3311F19A80005056BE3760=",
    }
    assert {spec.url for spec in notice_specs if spec.market == "tpex"} == {
        "https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html",
        "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html",
    }


@pytest.mark.parametrize(
    "manifest",
    [
        {
            "schema_version": "official-market-status-notice-sources.v1",
            "sources": [
                {"notice_url": "https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html"},
                {"notice_url": "https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html"},
            ],
        },
        {
            "schema_version": "official-market-status-notice-sources.v1",
            "sources": [{"notice_url": "https://example.test/storage/eb_data/11508/11500050581.html"}],
        },
        {
            "schema_version": "unsupported",
            "sources": [],
        },
    ],
)
def test_official_notice_manifest_rejects_duplicate_untrusted_or_invalid_sources(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    path = tmp_path / "notice-sources.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CurrentMarketStatusError):
        load_official_notice_source_specs(path)


def test_natural_capture_reads_notice_manifest_and_retains_evidence_next_refresh(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 10, 4, 1, tzinfo=timezone.utc)
    notice_by_url = {
        "https://www.tpex.org.tw/storage/eb_data/11508/11500050581.html": _tpex_notice_html(
            "中強光電股份有限公司（股票代號：5371）自115年8月24日起停止櫃檯買賣。",
            "",
        ),
        "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html": _tpex_notice_html(
            "台灣精星科技股份有限公司（股票代號：8183）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。",
            "",
        ),
    }
    twse_bodies = {
        "DAEFD7C7ACC511F19A80005056BE3760": _twse_notice_api_payload(
            symbol="2323",
            company="中環",
            publication_date="中華民國115年09月10日",
            reference="臺證上一字第1150018271號",
            halt_start="115年10月01日",
            halt_end="115年10月08日",
            new_share_start="115年10月12日",
        ),
        "2BFE5104AC3311F19A80005056BE3760": _twse_notice_api_payload(
            symbol="2601",
            company="益航",
            publication_date="中華民國115年09月09日",
            reference="臺證上一字第1150018275號",
            halt_start="115年09月23日",
            halt_end="115年10月03日",
            new_share_start="115年10月05日",
        ),
    }

    def fetcher(url: str, *, timeout: float, method: str = "GET", params=None):
        request_params = dict(params or {})
        if url == "https://www.twse.com.tw/rwd/zh/announcement/announcement_detail":
            body = twse_bodies[request_params["id"]]
            final_url = f"{url}?{urlencode(request_params)}"
            content_type = "application/json"
        else:
            body = notice_by_url.get(url, b"[]")
            final_url = url
            content_type = "text/html" if url in notice_by_url else "application/json"
        return (
            body,
            200,
            content_type,
            final_url,
            observed_at,
            {"content-length": str(len(body))},
        )

    first_snapshot, _ = capture_sources(
        output_dir=tmp_path / "natural-current-status",
        specs=source_specs(observed_on=observed_at),
        fetcher=fetcher,
    )
    second_snapshot, second_run_dir = capture_sources(
        output_dir=tmp_path / "natural-current-status",
        specs=source_specs(observed_on=observed_at),
        fetcher=fetcher,
    )
    reader = CurrentMarketStatusReader.from_path(second_run_dir / "snapshot.json")

    assert first_snapshot["partial_failure"] is False
    assert second_snapshot["partial_failure"] is False
    assert reader.get("2323").trading_restrictions[0]["effective_to"] == "2026-10-08"
    assert reader.get("2601").trading_restrictions[0]["resumed_on"] == "2026-10-05"
    assert reader.get("5371").listing_status == "unknown"
    assert reader.get("5371").trading_restrictions[0]["effective_from"] == "2026-08-24"
    assert reader.get("8183").listing_status == "delisted"
    assert reader.get("8183").status_evidence[0]["raw_sha256"].startswith("sha256:")
