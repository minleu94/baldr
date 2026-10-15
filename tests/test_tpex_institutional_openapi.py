from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.institutional_credit_flows_service import (
    EndpointSpec,
    FlowCaptureError,
    HttpResponse,
    capture_recent_flows,
    rebuild_flow_manifest_from_raw,
)
from data_module.tpex_institutional_openapi import (
    TPEX_OPENAPI_ENDPOINT,
    TPEX_OPENAPI_URL,
    TPEX_OPENAPI_VERSION,
    parse_tpex_institutional_openapi,
)


REQUESTED_DATE = "2026-09-08"
REQUESTED_ROC_DATE = "1150908"
COMPLETED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

EX_FOREIGN = (
    "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Buy",
    " Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Sell",
    "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference",
)
FOREIGN_DEALERS = (
    "Foreign Dealers-Total Buy",
    "Foreign Dealers-TotalSell",
    "ForeignDealers-Difference",
)
FOREIGN_TOTAL = (
    "ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy",
    "ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell",
    "ForeignInvestorsInclude MainlandAreaInvestors-Difference",
)
TRUST = (
    "SecuritiesInvestmentTrustCompanies-TotalBuy",
    "SecuritiesInvestmentTrustCompanies-TotalSell",
    "SecuritiesInvestmentTrustCompanies-Difference",
)
DEALER = ("Dealers-TotalBuy", "Dealers-TotalSell", "Dealers-Difference")
EXPECTED_KEYS = {
    "Date", "SecuritiesCompanyCode", "CompanyName", "Dealers -TotalSell", "TotalDifference",
    *EX_FOREIGN, *FOREIGN_DEALERS, *FOREIGN_TOTAL, *TRUST, *DEALER,
}


def _spec() -> EndpointSpec:
    return EndpointSpec(
        source_id="institutional_flows",
        market="TPEx",
        endpoint_id=TPEX_OPENAPI_ENDPOINT,
        source_version=TPEX_OPENAPI_VERSION,
        url=TPEX_OPENAPI_URL,
        params={},
        parser_kind="tpex_openapi_institutional",
        quantity_unit="shares",
    )


def _valid_row(*, code: str = "6547", report_day: str = REQUESTED_ROC_DATE) -> dict[str, Any]:
    row = {
        "Date": report_day,
        "SecuritiesCompanyCode": code,
        "CompanyName": "合成測試公司",
        "Dealers -TotalSell": "4",
        "TotalDifference": "73",
    }
    row.update(dict(zip(EX_FOREIGN, ("100", "50", "50"))))
    row.update(dict(zip(FOREIGN_DEALERS, ("10", "5", "5"))))
    row.update(dict(zip(FOREIGN_TOTAL, ("110", "55", "55"))))
    row.update(dict(zip(TRUST, ("30", "20", "10"))))
    row.update(dict(zip(DEALER, ("20", "12", "8"))))
    assert set(row) == EXPECTED_KEYS
    return row


def _payload(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _parse(payload: bytes, *, requested_date: str = REQUESTED_DATE,
           spec: EndpointSpec | None = None, payload_sha256: str | None = None):
    return parse_tpex_institutional_openapi(
        payload,
        requested_date=requested_date,
        completed_at=COMPLETED_AT,
        spec=spec or _spec(),
        payload_sha256=payload_sha256 or hashlib.sha256(payload).hexdigest(),
    )


def test_openapi_parser_pins_exact_endpoint_and_preserves_large_integer_aggregates():
    assert TPEX_OPENAPI_URL == "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
    assert TPEX_OPENAPI_VERSION == "tpex-openapi-3insti-daily.v1"
    assert TPEX_OPENAPI_ENDPOINT == "tpex:openapi:3insti_daily_trading"
    assert len(EXPECTED_KEYS) == 20

    row = _valid_row()
    row.update(dict(zip(EX_FOREIGN, ("9007199254741000", "9007199254740993", "7"))))
    row.update(dict(zip(FOREIGN_DEALERS, ("13", "5", "8"))))
    row.update(dict(zip(FOREIGN_TOTAL, ("9007199254741013", "9007199254740998", "15"))))
    row.update(dict(zip(TRUST, ("100", "40", "60"))))
    row.update(dict(zip(DEALER, ("80", "20", "60"))))
    row["Dealers -TotalSell"] = "10"
    row["TotalDifference"] = "135"
    payload = _payload([row])

    parsed = _parse(payload)

    assert parsed.observation_date == REQUESTED_DATE
    assert parsed.publication_at is None
    assert parsed.availability_evidence == "first_observed_only"
    assert parsed.quantity_unit == "shares"
    assert parsed.quarantine == ()
    assert len(parsed.rows) == 1
    result = parsed.rows[0]
    assert result["stock_code"] == "6547"
    assert result["observed_at"] == COMPLETED_AT.isoformat()
    assert result["foreign_investor_buy"] == 9007199254741013
    assert result["foreign_investor_sell"] == 9007199254740998
    assert result["foreign_investor_net"] == 15
    assert result["investment_trust_net"] == 60
    assert result["dealer_net"] == 60
    assert result["source_version"] == TPEX_OPENAPI_VERSION
    assert result["provenance"]["quantity_unit"] == "shares"


@pytest.mark.parametrize("field, value, error", [
    ("Date", "1150907", "report date mismatch"),
    ("Date", "115/09/08", "report date mismatch"),
    ("CompanyName", 17, "numeric"),
    ("SecuritiesCompanyCode", None, "field schema/type mismatch"),
    ("Dealers -TotalSell", True, "field schema/type mismatch"),
    ("TotalDifference", 1.5, "numeric"),
])
def test_parser_rejects_wrong_date_and_non_string_or_json_numeric_values(field, value, error):
    row = _valid_row()
    row[field] = value
    payload = _payload([row])

    with pytest.raises(FlowCaptureError, match=error):
        _parse(payload)


def test_parser_rejects_json_number_tokens_before_coercion():
    row = _valid_row()
    row["Dealers -TotalSell"] = 4
    payload = _payload([row])

    with pytest.raises(FlowCaptureError, match="numeric"):
        _parse(payload)

    nonfinite = _payload([_valid_row()]).replace(
        b'"Dealers -TotalSell":"4"', b'"Dealers -TotalSell":NaN'
    )
    with pytest.raises(FlowCaptureError, match="numeric"):
        _parse(nonfinite)


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_parser_requires_exact_twenty_field_schema(mutation):
    row = _valid_row()
    if mutation == "missing":
        row.pop("CompanyName")
    else:
        row["unrecognized"] = "value"
    with pytest.raises(FlowCaptureError, match="field schema"):
        _parse(_payload([row]))


def test_parser_rejects_duplicate_json_key_and_duplicate_security_code():
    body = _payload([_valid_row()])
    duplicate_key = body[:-2] + b',"Date":"1150908"}]'
    with pytest.raises(FlowCaptureError, match="duplicate field"):
        _parse(duplicate_key)

    with pytest.raises(FlowCaptureError, match="duplicate/invalid security"):
        _parse(_payload([_valid_row(), _valid_row()]))


@pytest.mark.parametrize("group", [EX_FOREIGN, FOREIGN_DEALERS, FOREIGN_TOTAL, TRUST, DEALER])
def test_each_declared_group_buy_sell_net_must_conserve(group):
    row = _valid_row()
    row[group[2]] = str(int(row[group[2]]) + 1)
    with pytest.raises(FlowCaptureError, match="conservation mismatch"):
        _parse(_payload([row]))


def test_parser_rejects_foreign_subtotal_total_and_dealer_hedge_contradictions():
    subtotal = _valid_row()
    subtotal[FOREIGN_TOTAL[0]] = str(int(subtotal[FOREIGN_TOTAL[0]]) + 1)
    subtotal[FOREIGN_TOTAL[1]] = str(int(subtotal[FOREIGN_TOTAL[1]]) + 1)
    with pytest.raises(FlowCaptureError, match="foreign subtotal"):
        _parse(_payload([subtotal]))

    total = _valid_row()
    total["TotalDifference"] = "74"
    with pytest.raises(FlowCaptureError, match="declared total"):
        _parse(_payload([total]))

    hedge = _valid_row()
    hedge["Dealers -TotalSell"] = "13"
    with pytest.raises(FlowCaptureError, match="hedge sell"):
        _parse(_payload([hedge]))


def test_parser_preserves_signed_net_while_buy_and_sell_remain_counts():
    row = _valid_row()
    row.update(dict(zip(TRUST, ("10", "30", "-20"))))
    row["TotalDifference"] = "43"

    parsed = _parse(_payload([row]))

    assert parsed.rows[0]["investment_trust_buy"] == 10
    assert parsed.rows[0]["investment_trust_sell"] == 30
    assert parsed.rows[0]["investment_trust_net"] == -20


def test_one_invalid_row_rejects_the_whole_daily_payload_without_partial_acceptance():
    valid = _valid_row(code="6547")
    invalid = _valid_row(code="6488")
    invalid["TotalDifference"] = "74"

    with pytest.raises(FlowCaptureError, match="declared total"):
        _parse(_payload([valid, invalid]))


@pytest.mark.parametrize("changed_spec", [
    replace(_spec(), quantity_unit="lots"),
    replace(_spec(), source_version="tpex-3insti-web.v1"),
    replace(_spec(), endpoint_id="tpex:3itrade"),
    replace(_spec(), params={"d": "115/09/08"}),
])
def test_parser_rejects_unpinned_endpoint_identity_and_units(changed_spec):
    with pytest.raises(FlowCaptureError, match="endpoint/version/unit mismatch"):
        _parse(_payload([_valid_row()]), spec=changed_spec)


def test_parser_rejects_bad_raw_hash():
    payload = _payload([_valid_row()])
    with pytest.raises(FlowCaptureError, match="raw hash mismatch"):
        _parse(payload, payload_sha256="0" * 64)


def _fake_tpex_transport(payload: bytes, calls: list[tuple[str, dict[str, str], int]]):
    def transport(url: str, params, timeout_seconds: int) -> HttpResponse:
        calls.append((url, dict(params), timeout_seconds))
        if url != TPEX_OPENAPI_URL or dict(params) != {}:
            raise AssertionError(f"new TPEx scope used an unexpected request: {url} {params!r}")
        return HttpResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            payload=payload,
            url=url,
            attempts=1,
        )

    return transport


def _capture(output_root: Path, payload: bytes, calls: list[tuple[str, dict[str, str], int]]):
    return capture_recent_flows(
        output_root=output_root,
        as_of_date=date(2026, 9, 8),
        sessions=1,
        max_lookback_days=1,
        max_attempts=1,
        transport=_fake_tpex_transport(payload, calls),
        rate_limit_seconds=0,
        capture_scope="tpex_openapi_institutional",
    )


def test_named_scope_uses_one_exact_tpex_openapi_request_and_preserves_raw(tmp_path: Path):
    payload = _payload([_valid_row()])
    calls: list[tuple[str, dict[str, str], int]] = []
    readback = _capture(tmp_path / "flows", payload, calls)

    assert calls == [(TPEX_OPENAPI_URL, {}, 30)]
    manifest_path = Path(readback["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scope = manifest["capture_scope"]
    assert scope["name"] == "tpex_openapi_institutional"
    assert scope["markets"] == ["TPEx"]
    assert scope["source_ids"] == ["institutional_flows"]
    assert scope["endpoint_ids"] == [TPEX_OPENAPI_ENDPOINT]
    assert {"twse:T86", "tpex:3itrade", "twse:MI_MARGN", "tpex:margin_bal"}.issubset(
        set(scope["excluded_endpoint_ids"])
    )
    assert manifest["discovered_sessions"] == [REQUESTED_DATE]
    assert manifest["totals"] == {"institutional_flows": 1}
    assert manifest["candidate_only"] is True
    assert manifest["formal_apply_allowed"] is False
    assert len(manifest["sources"]) == 1
    source = manifest["sources"][0]
    # 原manifest按source/date分組；端點、版本與單位在該raw的metadata。
    grouped_raw = source["raw_artifacts"][0]
    source_metadata = json.loads((manifest_path.parent / grouped_raw["metadata_path"]).read_text(encoding="utf-8"))
    assert source_metadata["endpoint_id"] == TPEX_OPENAPI_ENDPOINT
    assert source_metadata["source_version"] == TPEX_OPENAPI_VERSION
    assert source_metadata["quantity_unit"] == "shares"
    raw = source["raw_artifacts"][0]
    raw_path = manifest_path.parent / raw["path"]
    assert raw_path.read_bytes() == payload
    assert raw["sha256"] == hashlib.sha256(payload).hexdigest()
    metadata = json.loads((manifest_path.parent / raw["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["url"] == TPEX_OPENAPI_URL
    assert metadata["request_parameters"] == {}
    assert metadata["requested_date"] == REQUESTED_DATE
    assert metadata["source_version"] == TPEX_OPENAPI_VERSION
    candidate = json.loads((manifest_path.parent / source["candidate_rows_path"]).read_text(encoding="utf-8"))
    assert candidate[0]["values"]["dealer_net"] == 8


@pytest.mark.parametrize("overrides", [
    {"sessions": 2, "max_lookback_days": 2},
    {"max_lookback_days": 2},
    {"max_attempts": 2},
    {"sessions": True},
    {"max_lookback_days": True},
    {"max_attempts": True},
    {"sessions": 1.0},
    {"max_lookback_days": 1.0},
    {"max_attempts": 1.0},
])
def test_non_single_or_non_exact_parameters_reject_before_transport_or_output(tmp_path: Path, overrides):
    output_root = tmp_path / "must-not-exist"
    calls: list[tuple[str, dict[str, str], int]] = []
    arguments = {
        "output_root": output_root,
        "as_of_date": date(2026, 9, 8),
        "sessions": 1,
        "max_lookback_days": 1,
        "max_attempts": 1,
        "transport": _fake_tpex_transport(_payload([_valid_row()]), calls),
        "rate_limit_seconds": 0,
        "capture_scope": "tpex_openapi_institutional",
    }
    arguments.update(overrides)

    with pytest.raises(ValueError):
        capture_recent_flows(**arguments)
    assert calls == []
    assert not output_root.exists()


def test_report_date_mismatch_is_preserved_as_raw_failure_without_fallback(tmp_path: Path):
    payload = _payload([_valid_row(report_day="1150907")])
    calls: list[tuple[str, dict[str, str], int]] = []

    with pytest.raises(FlowCaptureError, match="report date mismatch"):
        _capture(tmp_path / "flows", payload, calls)

    assert calls == [(TPEX_OPENAPI_URL, {}, 30)]
    run_dirs = list((tmp_path / "flows" / "runs").iterdir())
    assert len(run_dirs) == 1
    raw_files = list((run_dirs[0] / "raw").rglob("*"))
    assert any(path.is_file() and path.read_bytes() == payload for path in raw_files)
    candidate_dir = run_dirs[0] / "candidate"
    if candidate_dir.exists():
        assert not list(candidate_dir.rglob("*.json"))


def test_rebuild_replays_exact_scope_without_network_or_raw_mutation(tmp_path: Path):
    payload = _payload([_valid_row()])
    calls: list[tuple[str, dict[str, str], int]] = []
    readback = _capture(tmp_path / "flows", payload, calls)
    manifest_path = Path(readback["manifest_path"])
    run_dir = manifest_path.parent
    original_manifest = manifest_path.read_bytes()
    original_raw = {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "raw").rglob("*")
        if path.is_file()
    }

    replay = rebuild_flow_manifest_from_raw(run_dir)

    assert replay["capture_replayed_without_network"] is True
    assert manifest_path.read_bytes() == original_manifest
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "raw").rglob("*")
        if path.is_file()
    } == original_raw
    replay_manifest = json.loads(Path(replay["manifest_path"]).read_text(encoding="utf-8"))
    assert replay_manifest["capture_scope"] == json.loads(original_manifest)["capture_scope"]
    assert replay_manifest["totals"] == {"institutional_flows": 1}
    assert calls == [(TPEX_OPENAPI_URL, {}, 30)]


@pytest.mark.parametrize("date_args", [[], ["--as-of-date", ""]])
def test_cli_requires_explicit_tpex_report_date_before_capture(monkeypatch, date_args):
    from scripts import complete_institutional_credit_flows as cli

    def forbidden(**kwargs):
        raise AssertionError("未明選報告日不得進capture或取今日")

    monkeypatch.setattr(cli, "capture_recent_flows", forbidden)
    monkeypatch.setattr(cli, "_today_taipei", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main(["capture", "--capture-scope", "tpex_openapi_institutional",
                  "--sessions", "1", "--max-lookback-days", "1", "--max-attempts", "1", *date_args])
    assert error.value.code == 2


@pytest.mark.parametrize("scope", ["legacy_all", "twse_institutional", "tpex_openapi_institutional"])
def test_cli_preserves_other_scope_dates_and_explicit_tpex_date(monkeypatch, scope):
    from scripts import complete_institutional_credit_flows as cli

    calls = []
    today = date(2026, 10, 16)
    monkeypatch.setattr(cli, "_today_taipei", lambda: today)

    def capture(**kwargs):
        calls.append(kwargs)
        return {"candidate_only": True}

    monkeypatch.setattr(cli, "capture_recent_flows", capture)
    arguments = ["capture", "--capture-scope", scope]
    if scope == "tpex_openapi_institutional":
        arguments += ["--as-of-date", "2026-10-15", "--sessions", "1",
                      "--max-lookback-days", "1", "--max-attempts", "1"]
    assert cli.main(arguments) == 0
    assert len(calls) == 1
    assert calls[0]["capture_scope"] == scope
    assert calls[0]["as_of_date"] == (date(2026, 10, 15) if scope == "tpex_openapi_institutional" else today)
    if scope == "tpex_openapi_institutional":
        assert (calls[0]["sessions"], calls[0]["max_lookback_days"], calls[0]["max_attempts"]) == (1, 1, 1)
