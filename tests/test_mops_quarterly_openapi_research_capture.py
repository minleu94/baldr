"""季報 OpenAPI 隔離研究收集器的本機 mock 測試。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, cast

import pytest

from data_module import mops_quarterly_openapi_research_capture as capture_module
from scripts import capture_mops_quarterly_openapi_research as capture_cli


_PROPERTIES = {
    "Date": {"type": "string"},
    "Year": {"type": "string"},
    "Season": {"type": "string"},
    "SecuritiesCompanyCode": {"type": "string"},
    "CompanyName": {"type": "string"},
    "年度": {"type": "string"},
    "季別": {"type": "string"},
    "公司代號": {"type": "string"},
    "公司名稱": {"type": "string"},
    "出表日期": {"type": "string"},
    "基本每股盈餘（元）": {"type": "string"},
    "營業收入（單位：千元）": {"type": "string"},
    "流通在外股數（單位：股）": {"type": "string"},
}


def _catalog_fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[tuple[str, str, str], str]]:
    """建立不含真實公司資料的合成 catalog route fixture。"""

    twse_paths: dict[str, Any] = {}
    tpex_paths: dict[str, Any] = {}
    tpex_schemas: dict[str, Any] = {}
    fingerprints: dict[tuple[str, str, str], str] = {}
    for endpoint in capture_module.TARGET_ENDPOINTS:
        schema = {"type": "object", "properties": dict(_PROPERTIES)}
        if endpoint.market == "twse":
            operation = {
                "parameters": [],
                "responses": {"200": {"schema": schema}},
            }
            twse_paths[endpoint.route] = {"get": operation}
            schema_ref = ""
        else:
            ref = capture_module._expected_tpex_schema_ref(endpoint)
            schema_name = ref.rsplit("/", 1)[-1]
            tpex_schemas[schema_name] = schema
            operation = {
                "parameters": [],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": ref}}
                        }
                    }
                },
            }
            tpex_paths[endpoint.route] = {"get": operation}
            schema_ref = ref
        descriptor = {
            "market": endpoint.market,
            "route": endpoint.route,
            "method": "get",
            "parameters": [],
            "schema_ref": schema_ref,
            "schema": schema,
        }
        fingerprints[(endpoint.market, endpoint.statement_type, endpoint.category)] = hashlib.sha256(
            capture_module._canonical_json(descriptor)
        ).hexdigest()
    twse = {
        "swagger": "2.0",
        "host": capture_module.TWSE_TARGET_HOST,
        "basePath": "/v1",
        "schemes": ["https"],
        "paths": twse_paths,
    }
    tpex = {
        "openapi": "3.0.1",
        "servers": [{"url": capture_module.TPEX_TARGET_SERVER}],
        "paths": tpex_paths,
        "components": {"schemas": tpex_schemas},
    }
    return twse, tpex, fingerprints


class _BodyReader:
    def __init__(self, body: bytes, *, after_read: Callable[[], None] | None = None) -> None:
        self.body = body
        self.offset = 0
        self.after_read = after_read

    def read(self, amount: int, *, decode_content: bool = False) -> bytes:
        assert decode_content is False
        chunk = self.body[self.offset : self.offset + amount]
        self.offset += len(chunk)
        if self.after_read is not None:
            self.after_read()
        return chunk


class _Response:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        after_read: Callable[[], None] | None = None,
        response_url: str | None = None,
    ) -> None:
        self.status_code = status
        self.reason = "OK" if status == 200 else "Bad Request"
        self.headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        self.url = response_url or url
        self.raw = _BodyReader(body, after_read=after_read)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(
        self,
        *,
        twse: Mapping[str, Any],
        tpex: Mapping[str, Any],
        numeric_overrides: Mapping[str, Any] | None = None,
        after_get: Callable[[], None] | None = None,
        after_read: Callable[[], None] | None = None,
        status_overrides: Mapping[str, int] | None = None,
        response_url_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self.catalogs = {"twse": dict(twse), "tpex": dict(tpex)}
        self.numeric_overrides = dict(numeric_overrides or {})
        self.calls: list[dict[str, Any]] = []
        self.responses: list[_Response] = []
        self.pacing: list[float] = []
        self.after_get = after_get
        self.after_read = after_read
        self.status_overrides = dict(status_overrides or {})
        self.response_url_overrides = dict(response_url_overrides or {})

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: int,
        stream: bool,
        allow_redirects: bool,
    ) -> _Response:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "timeout": timeout,
                "stream": stream,
                "allow_redirects": allow_redirects,
            }
        )
        assert timeout == capture_module.REQUEST_TIMEOUT_SECONDS
        assert stream is True
        assert allow_redirects is False
        if url == capture_module.TWSE_CATALOG_URL:
            body = capture_module._canonical_json(self.catalogs["twse"])
        elif url == capture_module.TPEX_CATALOG_URL:
            body = capture_module._canonical_json(self.catalogs["tpex"])
        else:
            override = self.numeric_overrides.get(url, [])
            body = capture_module._canonical_json(override)
        response = _Response(
            url,
            body,
            status=self.status_overrides.get(url, 200),
            after_read=self.after_read,
            response_url=self.response_url_overrides.get(url),
        )
        self.responses.append(response)
        if self.after_get is not None:
            self.after_get()
        return response


class _SingleResponseSession:
    def __init__(self, url: str, body: bytes) -> None:
        self.response = _Response(url, body)

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: int,
        stream: bool,
        allow_redirects: bool,
    ) -> _Response:
        assert url == self.response.url
        assert timeout == 30 and stream and allow_redirects is False
        assert headers["Accept"] == "application/json"
        return self.response


def _valid_row() -> dict[str, str]:
    return {
        "Date": "115/08/15",
        "Year": "115",
        "Season": "2",
        "SecuritiesCompanyCode": "2330",
        "CompanyName": "合成測試公司",
        "基本每股盈餘（元）": "1.2500",
        "營業收入（單位：千元）": "1000000",
        "流通在外股數（單位：股）": "1000",
    }


def _run(
    tmp_path: Path,
    *,
    row_overrides: Mapping[str, Any] | None = None,
    twse_mutator: Any = None,
    disk_usage: Any = None,
    monotonic: Callable[[], float] | None = None,
    after_get: Callable[[], None] | None = None,
    after_read: Callable[[], None] | None = None,
    sleep_override: Callable[[float], None] | None = None,
    status_overrides: Mapping[str, int] | None = None,
    response_url_overrides: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], _Session, dict[tuple[str, str, str], str]]:
    twse, tpex, fingerprints = _catalog_fixtures()
    if twse_mutator is not None:
        twse_mutator(twse)
    row = _valid_row()
    if row_overrides:
        row.update(row_overrides)
    numeric = {capture_module.TARGET_ENDPOINTS[0].url: [row]}
    session = _Session(
        twse=twse,
        tpex=tpex,
        numeric_overrides=numeric,
        after_get=after_get,
        after_read=after_read,
        status_overrides=status_overrides,
        response_url_overrides=response_url_overrides,
    )
    kwargs: dict[str, Any] = {
        "output_root": tmp_path / "candidates",
        "clock": lambda: datetime.now(timezone.utc),
        "sleep": sleep_override or session.pacing.append,
        "expected_route_fingerprints": fingerprints,
    }
    if monotonic is not None:
        kwargs["monotonic"] = monotonic
    if disk_usage is not None:
        kwargs["disk_usage"] = disk_usage
    result = capture_module.run_quarterly_openapi_research_capture(
        cast(capture_module.HttpSession, session), **kwargs
    )
    return result, session, fingerprints


def test_allowlist_is_exactly_24_fixed_targets_with_64_character_fingerprints() -> None:
    assert len(capture_module.TARGET_ENDPOINTS) == 24
    assert len(capture_module.EXPECTED_ROUTE_FINGERPRINTS) == 24
    assert all(len(value) == 64 for value in capture_module.EXPECTED_ROUTE_FINGERPRINTS.values())
    assert all(endpoint.url.startswith("https://") for endpoint in capture_module.TARGET_ENDPOINTS)


def test_complete_mock_capture_revalidates_nonempty_decimal_preview(tmp_path: Path) -> None:
    result, session, fingerprints = _run(tmp_path)

    assert result["status"] == "completed_observation_only"
    assert result["requests_made"] == 26
    assert result["numeric_request_count"] == 24
    assert len(session.calls) == 26
    assert session.pacing == [capture_module.REQUEST_PACING_SECONDS] * 25
    assert all(response.closed for response in session.responses)
    assert {call["url"] for call in session.calls} == {
        capture_module.TWSE_CATALOG_URL,
        capture_module.TPEX_CATALOG_URL,
        *(endpoint.url for endpoint in capture_module.TARGET_ENDPOINTS),
    }
    assert all(call["timeout"] == 30 and call["allow_redirects"] is False for call in session.calls)

    run_root = Path(result["run_root"])
    readback = capture_module.verify_capture_run(
        run_root,
        expected_route_fingerprints=fingerprints,
    )
    assert readback["request_receipts_verified"] == 26
    assert readback["numeric_rows_rechecked"] == 1
    assert readback["preview_rows_rechecked"] == 1
    assert readback["issuer_coverage_complete"] is False
    assert readback["formal_pit_eligible"] is False
    assert result["terminal"]["research_artifact_materialized_at_utc"]
    assert result["terminal"]["research_artifact_readback_verified_at_utc"] == result["terminal"]["verification_completed_at_utc"]
    assert result["terminal"]["candidate_available_at"] is None

    preview_path = run_root / "numeric_preview.ndjson"
    preview = json.loads(preview_path.read_text(encoding="utf-8").splitlines()[0])
    fields = {field["item_name"]: field for field in preview["numeric_fields"]}
    assert preview["run_id"] == result["run_id"]
    assert preview["available_at"] is None
    assert preview["issuer_identity_verified"] is False
    assert fields["營業收入（單位：千元）"]["raw_value"] == "1000000"
    assert fields["營業收入（單位：千元）"]["unit"] == "unit_unknown"
    assert fields["營業收入（單位：千元）"]["unit_basis"] == "unknown_from_catalog"
    assert fields["基本每股盈餘（元）"]["unit"] == "元/股"
    assert fields["基本每股盈餘（元）"]["unit_basis"] == "explicit_eps_field_label"
    assert fields["流通在外股數（單位：股）"]["unit"] == "股"
    assert fields["流通在外股數（單位：股）"]["unit_basis"] == "explicit_share_field_label"
    assert all(result["eligibility"][flag] is False for flag in result["eligibility"] if flag != "research_only")


def test_empty_lists_are_saved_as_observations_not_official_no_data(tmp_path: Path) -> None:
    twse, tpex, fingerprints = _catalog_fixtures()
    session = _Session(twse=twse, tpex=tpex)
    result = capture_module.run_quarterly_openapi_research_capture(
        cast(capture_module.HttpSession, session),
        output_root=tmp_path / "candidates",
        clock=lambda: datetime.now(timezone.utc),
        sleep=lambda _seconds: None,
        expected_route_fingerprints=fingerprints,
    )
    summary = result["endpoint_summaries"][0]
    assert result["status"] == "completed_observation_only"
    assert summary["status"] == "observed_empty_list"
    assert summary["observation_label"] == "empty_response"
    assert summary["official_no_data"] is False
    assert summary["full_market_complete"] is False
    assert summary["row_count"] == 0


def test_catalog_contract_drift_blocks_all_numeric_requests(tmp_path: Path) -> None:
    result, session, _ = _run(
        tmp_path,
        twse_mutator=lambda catalog: catalog["paths"].pop(capture_module.TARGET_ENDPOINTS[0].route),
    )
    assert result["status"] == "blocked_catalog_contract_or_transport"
    assert result["numeric_request_count"] == 0
    assert len(session.calls) == 2
    assert result["terminal"]["readback"]["request_receipts_verified"] == 2


@pytest.mark.parametrize(
    ("overrides", "expected_status", "expected_conflicts"),
    [
        ({"Year": None}, "schema_review_required", 0),
        ({"營業收入（單位：千元）": 100}, "schema_review_required", 0),
        ({"Year": "115", "年度": "114"}, "identity_review_required", 1),
    ],
)
def test_untrusted_row_values_are_pending_and_not_previewed(
    tmp_path: Path,
    overrides: Mapping[str, Any],
    expected_status: str,
    expected_conflicts: int,
) -> None:
    result, _session, fingerprints = _run(tmp_path, row_overrides=overrides)
    endpoint = result["endpoint_summaries"][0]
    assert result["status"] == "completed_with_review_items"
    assert endpoint["status"] == expected_status
    assert endpoint["identity_alias_conflict_rows"] == expected_conflicts
    assert endpoint["preview_rows_written"] == 0
    assert Path(result["run_root"], "numeric_preview.ndjson").read_bytes() == b""
    readback = capture_module.verify_capture_run(
        Path(result["run_root"]),
        expected_route_fingerprints=fingerprints,
    )
    assert readback["preview_rows_rechecked"] == 0


def test_future_period_values_are_withheld_from_preview(tmp_path: Path) -> None:
    result, _session, fingerprints = _run(
        tmp_path,
        row_overrides={"Year": "116", "Season": "4", "年度": "116"},
    )
    endpoint = result["endpoint_summaries"][0]
    assert endpoint["future_period_rows_with_values_withheld"] == 1
    assert endpoint["preview_rows_written"] == 1
    record = json.loads(Path(result["run_root"], "numeric_preview.ndjson").read_text(encoding="utf-8"))
    assert record["period_end_after_observation"] is True
    assert record["numeric_fields"] == []
    capture_module.verify_capture_run(
        Path(result["run_root"]),
        expected_route_fingerprints=fingerprints,
    )


def test_first_catalog_raw_custody_failure_is_receipted_and_stops_numeric_calls(tmp_path: Path) -> None:
    calls = 0

    def disk_usage(_path: Path) -> Any:
        nonlocal calls
        calls += 1
        free = (
            capture_module.MIN_FREE_SPACE_BYTES
            if calls == 3
            else capture_module.MIN_FREE_SPACE_BYTES + 32 * 1024 * 1024
        )
        return SimpleNamespace(total=free, used=0, free=free)

    result, session, fingerprints = _run(tmp_path, disk_usage=disk_usage)
    assert result["status"] == "blocked_catalog_contract_or_transport"
    assert len(session.calls) == 1
    receipt_path = Path(result["run_root"], "catalog_twse", "receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["error_code"] == "raw_entity_custody_failed"
    assert receipt["raw_body"]["saved"] is False
    assert receipt["raw_body"]["attempted_path"] == "catalog_twse/response_body.raw"
    assert result["terminal"]["readback"]["request_receipts_verified"] == 1
    capture_module.verify_capture_run(
        Path(result["run_root"]),
        expected_route_fingerprints=fingerprints,
    )


def test_numeric_raw_custody_failure_marks_endpoint_and_stops_following_routes(tmp_path: Path) -> None:
    calls = 0

    def disk_usage(_path: Path) -> Any:
        nonlocal calls
        calls += 1
        free = (
            capture_module.MIN_FREE_SPACE_BYTES
            if calls == 9
            else capture_module.MIN_FREE_SPACE_BYTES + 32 * 1024 * 1024
        )
        return SimpleNamespace(total=free, used=0, free=free)

    result, session, fingerprints = _run(tmp_path, disk_usage=disk_usage)
    assert result["status"] == "completed_with_endpoint_failures"
    assert len(session.calls) == 3
    assert result["numeric_request_count"] == 1
    endpoint = result["endpoint_summaries"][0]
    assert endpoint["status"] == "transport_failure"
    assert endpoint["error_code"] == "raw_entity_custody_failed"
    receipt = json.loads(
        Path(result["run_root"], endpoint["endpoint_id"], "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["raw_body"]["saved"] is False
    assert receipt["transport_status"] == "http_or_body_failure"
    assert result["terminal"]["readback"]["request_receipts_verified"] == 3
    capture_module.verify_capture_run(
        Path(result["run_root"]),
        expected_route_fingerprints=fingerprints,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"{not-json",
        b"[" * 4000 + b"0" + b"]" * 4000,
        b'{"identity":"first","identity":"overwritten"}',
        b'{"amount":NaN}',
    ],
    ids=["invalid-json", "deep-json-recursion", "duplicate-key", "nonfinite-constant"],
)
def test_json_parse_failure_keeps_http_body_and_hash_custody(tmp_path: Path, body: bytes) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    writer = capture_module.CaptureWriter(run_root)
    url = capture_module.TWSE_CATALOG_URL
    captured, receipt = capture_module._capture_one_request(
        cast(capture_module.HttpSession, _SingleResponseSession(url, body)),
        url=url,
        request_id="catalog_twse",
        request_index=1,
        run_id="synthetic-json-failure",
        clock=lambda: datetime.now(timezone.utc),
        writer=writer,
    )

    assert captured.http_status == 200
    assert captured.transport_status == "http_or_body_failure"
    assert captured.error_code == "invalid_json"
    assert receipt["raw_body"]["saved"] is True
    assert receipt["raw_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert (run_root / "catalog_twse" / "response_body.raw").read_bytes() == body
    assert captured.response_json is None


def test_raw_readback_failure_never_reports_json_source_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    writer = capture_module.CaptureWriter(run_root)

    def failed_readback(_path: Path, _limit: int) -> bytes:
        raise ValueError("mock_readback_failure")

    monkeypatch.setattr(capture_module, "_bounded_read_file", failed_readback)
    url = capture_module.TWSE_CATALOG_URL
    body = b"{}"
    captured, receipt = capture_module._capture_one_request(
        cast(capture_module.HttpSession, _SingleResponseSession(url, body)),
        url=url,
        request_id="catalog_twse",
        request_index=1,
        run_id="synthetic-readback-failure",
        clock=lambda: datetime.now(timezone.utc),
        writer=writer,
    )

    assert captured.http_status == 200
    assert captured.transport_status == "http_or_body_failure"
    assert captured.error_code == "raw_entity_custody_failed"
    assert receipt["raw_body"]["saved"] is False
    assert receipt["raw_body"]["attempted_path"] == "catalog_twse/response_body.raw"
    assert receipt["transport_status"] == "http_or_body_failure"
    assert not writer.files


def test_metadata_write_obeys_free_space_reserve(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    writer = capture_module.CaptureWriter(
        root,
        disk_usage=lambda _path: SimpleNamespace(
            total=100,
            used=0,
            free=capture_module.MIN_FREE_SPACE_BYTES,
        ),
    )
    with pytest.raises(capture_module.CaptureError, match="minimum_free_space_reserve"):
        writer.write_metadata("receipt.json", b"{}")
    assert not (root / "receipt.json").exists()


def test_preview_register_reads_existing_create_only_file(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    writer = capture_module.CaptureWriter(root)
    preview = capture_module.PreviewStream(writer)
    assert preview.write_record({"run_id": "synthetic", "row_number": 1})
    receipt = preview.close_and_readback()
    assert receipt["path"] == "numeric_preview.ndjson"
    assert receipt["bytes"] > 0


def test_bounded_reader_rejects_oversized_file_before_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "oversized.raw"
    with path.open("wb") as stream:
        stream.truncate(capture_module.MAX_ENTITY_BYTES + 1)

    def unexpected_open(*_args: Any, **_kwargs: Any) -> int:
        raise AssertionError("超限檔案必須在 open/read 前拒收")

    monkeypatch.setattr(capture_module.os, "open", unexpected_open)
    with pytest.raises(ValueError, match="artifact_exceeds_read_cap"):
        capture_module._bounded_read_file(path, capture_module.MAX_ENTITY_BYTES)


def test_bounded_reader_rejects_hard_linked_artifact(tmp_path: Path) -> None:
    path = tmp_path / "body.raw"
    alias = tmp_path / "alias.raw"
    path.write_bytes(b"[]")
    os.link(path, alias)
    with pytest.raises(ValueError, match="artifact_link_count_invalid"):
        capture_module._bounded_read_file(path, 8)


def test_json_fraction_is_preserved_as_decimal_without_float_conversion() -> None:
    parsed = capture_module._strict_json_loads('{"amount": 12345678901234567890.125}')
    assert parsed["amount"] == Decimal("12345678901234567890.125")
    assert isinstance(parsed["amount"], Decimal)


def test_entity_cap_probe_requires_eof_and_detects_lying_content_length() -> None:
    cap = capture_module.MAX_ENTITY_BYTES
    exact = capture_module._read_bounded_entity(_BodyReader(b"x" * cap), str(cap))
    assert len(exact.raw_entity) == cap
    assert exact.complete is True
    assert exact.limit_reached is False
    assert exact.read_error == ""

    overlong = capture_module._read_bounded_entity(_BodyReader(b"x" * (cap + 1)), str(cap))
    assert len(overlong.raw_entity) == cap
    assert overlong.complete is False
    assert overlong.limit_reached is True

    short_declared = capture_module._read_bounded_entity(_BodyReader(b"x" * (cap - 1)), str(cap))
    assert short_declared.complete is True
    assert short_declared.read_error == "content_length_mismatch"


def test_request_elapsed_budget_keeps_prefix_and_stops_later_routes(tmp_path: Path) -> None:
    elapsed = [0.0]
    result, session, fingerprints = _run(
        tmp_path,
        monotonic=lambda: elapsed[0],
        after_read=lambda: elapsed.__setitem__(0, elapsed[0] + capture_module.MAX_REQUEST_ELAPSED_SECONDS + 1),
    )

    assert result["status"] == "request_elapsed_budget_exceeded"
    assert result["capture_outcome"] == "request_elapsed_budget_exceeded"
    assert result["requests_made"] == 1
    assert [call["url"] for call in session.calls] == [capture_module.TWSE_CATALOG_URL]
    run_root = Path(result["run_root"])
    receipt = json.loads((run_root / "catalog_twse" / "receipt.json").read_text(encoding="utf-8"))
    raw = receipt["raw_body"]
    assert raw["saved"] is True
    assert raw["bytes"] > 0
    assert receipt["raw_body_complete"] is False
    assert receipt["error_code"] == "request_elapsed_budget_exceeded"
    assert receipt["request_elapsed_seconds"] >= capture_module.MAX_REQUEST_ELAPSED_SECONDS
    readback = capture_module.verify_capture_run(run_root, expected_route_fingerprints=fingerprints)
    assert readback["request_receipts_verified"] == 1


def test_completed_body_crossing_request_budget_after_parse_revalidates_saved_decode(
    tmp_path: Path,
) -> None:
    ticks = [0.0]

    def monotonic() -> float:
        ticks[0] += 10.0
        return ticks[0]

    result, session, fingerprints = _run(tmp_path, monotonic=monotonic)

    assert result["status"] == "request_elapsed_budget_exceeded"
    assert len(session.calls) == 1
    run_root = Path(result["run_root"])
    receipt = json.loads((run_root / "catalog_twse" / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["raw_body_complete"] is True
    assert receipt["decoded_body_sha256"] is not None
    assert receipt["json_parse_status"] == "parsed"
    assert receipt["transport_status"] == "http_or_body_failure"
    assert receipt["error_code"] == "request_elapsed_budget_exceeded"
    assert capture_module.verify_capture_run(
        run_root, expected_route_fingerprints=fingerprints
    )["request_receipts_verified"] == 1


@pytest.mark.parametrize(
    ("status_overrides", "response_url_overrides", "expected_error"),
    [
        ({capture_module.TWSE_CATALOG_URL: 404}, {}, "http_status_not_200"),
        ({}, {capture_module.TWSE_CATALOG_URL: "https://elsewhere.invalid/body"}, "response_url_mismatch"),
    ],
    ids=["http-404", "response-url-mismatch"],
)
def test_complete_raw_http_failures_remain_readback_verifiable(
    tmp_path: Path,
    status_overrides: Mapping[str, int],
    response_url_overrides: Mapping[str, str],
    expected_error: str,
) -> None:
    result, session, fingerprints = _run(
        tmp_path,
        status_overrides=status_overrides,
        response_url_overrides=response_url_overrides,
    )

    assert result["status"] == "blocked_catalog_contract_or_transport"
    assert len(session.calls) == 2
    run_root = Path(result["run_root"])
    receipt = json.loads((run_root / "catalog_twse" / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["http_status"] == status_overrides.get(capture_module.TWSE_CATALOG_URL, 200)
    assert receipt["raw_body"]["saved"] is True
    assert receipt["raw_body_complete"] is True
    assert receipt["decoded_body_sha256"] is None
    assert receipt["json_parse_status"] == "not_parsed"
    assert receipt["error_code"] == expected_error
    assert capture_module.verify_capture_run(
        run_root, expected_route_fingerprints=fingerprints
    )["request_receipts_verified"] == 2


def test_run_elapsed_budget_stops_after_overrun_response_and_preserves_receipt(tmp_path: Path) -> None:
    elapsed = [0.0]
    body_reads = [0]

    def after_read() -> None:
        body_reads[0] += 1
        if body_reads[0] == 31:
            elapsed[0] += 80.0

    result, session, fingerprints = _run(
        tmp_path,
        monotonic=lambda: elapsed[0],
        after_get=lambda: elapsed.__setitem__(0, elapsed[0] + 50.0),
        after_read=after_read,
        sleep_override=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
    )

    assert result["status"] == "run_elapsed_budget_exceeded"
    assert result["capture_outcome"] == "run_elapsed_budget_exceeded"
    assert result["requests_made"] == 16
    assert result["numeric_request_count"] == 14
    assert len(session.calls) == 16
    assert session.calls[-1]["url"] == capture_module.TARGET_ENDPOINTS[13].url
    assert session.responses[-1].closed is True
    assert result["endpoint_summaries"][-1]["status"] == "transport_failure"
    run_root = Path(result["run_root"])
    receipt = json.loads(
        (run_root / capture_module.TARGET_ENDPOINTS[13].endpoint_id / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["raw_body"]["saved"] is True
    assert receipt["error_code"] == "run_elapsed_budget_exceeded"
    assert receipt["run_elapsed_seconds"] >= capture_module.MAX_RUN_ELAPSED_SECONDS
    readback = capture_module.verify_capture_run(run_root, expected_route_fingerprints=fingerprints)
    assert readback["request_receipts_verified"] == 16


def test_run_budget_checked_after_pacing_before_next_request(tmp_path: Path) -> None:
    elapsed = [0.0]
    pace_calls: list[float] = []

    def sleeper(seconds: float) -> None:
        pace_calls.append(seconds)
        elapsed[0] += capture_module.MAX_RUN_ELAPSED_SECONDS / 2

    result, session, fingerprints = _run(
        tmp_path,
        monotonic=lambda: elapsed[0],
        sleep_override=sleeper,
    )

    assert result["status"] == "run_elapsed_budget_exceeded"
    assert result["requests_made"] == 2
    assert len(session.calls) == 2
    assert [call["url"] for call in session.calls] == [
        capture_module.TWSE_CATALOG_URL,
        capture_module.TPEX_CATALOG_URL,
    ]
    assert pace_calls == [capture_module.REQUEST_PACING_SECONDS] * 2
    readback = capture_module.verify_capture_run(
        Path(result["run_root"]), expected_route_fingerprints=fingerprints
    )
    assert readback["request_receipts_verified"] == 2


def test_cli_rejects_scope_overrides_before_session_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_session() -> Any:
        raise AssertionError("參數拒絕前不得建立 HTTP session")

    monkeypatch.setattr(capture_cli.requests, "Session", forbidden_session)
    with pytest.raises(SystemExit):
        capture_cli.main(["--url", "https://example.invalid/"])
    with pytest.raises(SystemExit):
        capture_cli.main(["--preview", "--capture"])


def test_cli_defaults_to_no_network_no_write_preview(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_session() -> Any:
        raise AssertionError("預覽不得建立 HTTP session")

    def forbidden_capture(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("預覽不得呼叫 capture")

    monkeypatch.setattr(capture_cli.requests, "Session", forbidden_session)
    monkeypatch.setattr(capture_cli, "run_quarterly_openapi_research_capture", forbidden_capture)
    root_existed_before = capture_cli.DEFAULT_OUTPUT_ROOT.exists()
    assert capture_cli.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "preview"
    assert result["network_requests"] == 0
    assert result["files_written"] is False
    assert result["fixed_request_plan"]["maximum_requests"] == 26
    assert result["fixed_request_plan"]["max_request_elapsed_seconds"] == 60
    assert result["fixed_request_plan"]["max_run_elapsed_seconds"] == 900
    assert result["fixed_request_plan"]["single_blocking_read_may_overrun_budget"] is True
    assert len(result["fixed_request_plan"]["numeric_endpoints"]) == 24
    assert capture_cli.DEFAULT_OUTPUT_ROOT.exists() is root_existed_before


def test_cli_capture_json_is_safe_for_cp1252_console(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_bytes = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(stream_bytes, encoding="cp1252")

    class _ContextSession:
        def __enter__(self) -> _ContextSession:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    monkeypatch.setattr(capture_cli.requests, "Session", _ContextSession)
    monkeypatch.setattr(
        capture_cli,
        "run_quarterly_openapi_research_capture",
        lambda _session: {"status": "completed_with_review_items", "company_name": "合成測試公司"},
    )
    monkeypatch.setattr(capture_cli.sys, "stdout", cp1252_stdout)

    assert capture_cli.main(["--capture"]) == 0
    cp1252_stdout.flush()
    rendered = stream_bytes.getvalue().decode("cp1252")
    parsed = json.loads(rendered)
    assert parsed["company_name"] == "合成測試公司"
