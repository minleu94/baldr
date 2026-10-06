from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib

import pytest

from data_module.pit_inactive_security_termination_evidence import (
    InactiveTerminationEvidenceError,
    OfficialTerminationSourceSpec,
    parse_official_termination_notice,
    validate_official_termination_proof_readback,
)


CAPTURED_AT = datetime(2026, 9, 30, 23, 50, tzinfo=timezone.utc)
REAL_CUTOFF = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)
SOURCE_URL = "https://www.tpex.org.tw/storage/eb_data/11509/notice.html"


def _spec(
    *,
    symbol: str = "8183",
    issuer_name: str = "台灣精星科技股份有限公司",
    market_scope: str = "tpex_otc",
    published_on: date = date(2026, 9, 3),
    suspension_effective_on: date = date(2026, 9, 23),
    termination_effective_on: date = date(2026, 10, 1),
    source_url: str = SOURCE_URL,
) -> OfficialTerminationSourceSpec:
    return OfficialTerminationSourceSpec(
        source_url=source_url,
        symbol=symbol,
        issuer_name=issuer_name,
        market_scope=market_scope,
        published_on=published_on,
        suspension_effective_on=suspension_effective_on,
        termination_effective_on=termination_effective_on,
    )


def _body(
    *,
    symbol: str = "8183",
    issuer_name: str = "台灣精星科技股份有限公司",
    issuer_alias: str = "精星公司",
    published: str = "中華民國115年9月3日",
    suspended: str = "115年9月23日",
    terminated: str = "115年10月1日",
    conversion: str = "精星公司每1股普通股換發精成科公司普通股。",
) -> bytes:
    # 合成格式 fixture：只保留已 custody 官方 HTML 的日期標籤、主旨/代號、事件日期與普通股字樣；不是官方原文。
    return (
        "<!doctype html><html><head><meta http-equiv=\"Content-Type\" "
        "content=\"text/html; charset=utf-8\"><title>官方公告</title>"
        "<script>代號：9999</script></head><body>"
        f"<div>發文日期：{published}</div>"
        f"<p>公告{issuer_name}上櫃之有價證券（股票代號：{symbol}，"
        f"以下簡稱{issuer_alias}）"
        f"自{ suspended }起停止櫃檯買賣，並自{terminated}起終止櫃檯買賣。</p>"
        f"<p>{conversion}</p></body></html>"
    ).encode("utf-8")


def _metadata(
    body: bytes,
    *,
    status_code: int = 200,
    request_url: str = SOURCE_URL,
    final_url: str = SOURCE_URL,
    captured_at: datetime = CAPTURED_AT,
    raw_path: str = "attempt/raw/notice.html",
) -> dict[str, object]:
    return {
        "request_url": request_url,
        "final_url": final_url,
        "status_code": status_code,
        "content_type": "text/html; charset=utf-8",
        "charset": "utf-8",
        "captured_at": captured_at.isoformat(),
        "raw_sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        "raw_bytes": len(body),
        "raw_path": raw_path,
    }


def _parse(
    body: bytes | None = None,
    metadata: dict[str, object] | None = None,
    spec: OfficialTerminationSourceSpec | None = None,
    *,
    actual_capture_at: datetime = CAPTURED_AT,
    real_cutoff: datetime = REAL_CUTOFF,
):
    payload = body if body is not None else _body()
    response = metadata if metadata is not None else _metadata(payload)
    return parse_official_termination_notice(
        payload,
        response,
        spec if spec is not None else _spec(),
        actual_capture_at,
        real_cutoff,
    )


def test_notice_produces_separate_inactive_research_proof_without_active_identity() -> None:
    raw = _body()
    response = _metadata(raw)

    proof = _parse(raw, response)

    assert proof.symbol == "8183"
    assert proof.issuer_alias == "精星公司"
    assert proof.market_scope == "tpex_otc"
    assert proof.state == "proven_inactive_common_stock"
    assert proof.eligible is False
    assert proof.research_only is True
    assert proof.formal_credit is False
    assert proof.historical_pit is False
    assert proof.active_security_record is False
    assert proof.isin_code is None
    assert proof.cfi_code is None
    assert proof.source_raw_sha256 == response["raw_sha256"]
    assert proof.source_raw_path == response["raw_path"]
    assert proof.charset == "utf-8"
    assert proof.termination_effective_on == "2026-10-01"
    assert proof.evidence_facts["ordinary_stock_conversion_explicit"] is True
    assert proof.evidence_facts["issuer_common_stock_binding"] is True


def test_html_declared_charset_is_used_when_http_omits_it() -> None:
    raw = _body()
    response = _metadata(raw)
    response["content_type"] = "text/html"
    response["charset"] = None

    proof = _parse(raw, response)

    assert proof.charset == "utf-8"
    assert proof.charset_source == "html_meta"


def test_parser_is_bound_to_requested_symbol_not_a_hardcoded_symbol() -> None:
    spec = _spec(symbol="9999", issuer_name="測試公司股份有限公司")
    raw = _body(
        symbol="9999",
        issuer_name="測試公司股份有限公司",
        issuer_alias="測試公司",
        conversion="測試公司每1股普通股換發子公司普通股。",
    )

    proof = _parse(raw, _metadata(raw), spec)

    assert proof.symbol == "9999"


@pytest.mark.parametrize("status_code", [403, 404, 500])
def test_non_200_response_is_rejected(status_code: int) -> None:
    raw = _body()

    with pytest.raises(InactiveTerminationEvidenceError, match="not HTTP 200"):
        _parse(raw, _metadata(raw, status_code=status_code))


def test_request_or_redirected_final_url_must_match_exact_official_spec() -> None:
    raw = _body()
    response = _metadata(raw, final_url="https://example.invalid/notice.html")

    with pytest.raises(InactiveTerminationEvidenceError, match="exact source specification"):
        _parse(raw, response)


def test_source_spec_rejects_non_tpex_market_and_nonofficial_host() -> None:
    raw = _body()
    with pytest.raises(InactiveTerminationEvidenceError, match="market is not TPEx OTC"):
        _parse(raw, _metadata(raw), _spec(market_scope="twse_listed"))
    with pytest.raises(InactiveTerminationEvidenceError, match="outside the official TPEx"):
        _parse(raw, _metadata(raw), _spec(source_url="https://example.invalid/notice.html"))
    with pytest.raises(InactiveTerminationEvidenceError, match="outside the official TPEx"):
        _parse(
            raw,
            _metadata(raw),
            _spec(source_url="https://www.tpex.org.tw/storage/eb_data/11509/../11500054131.html"),
        )


def test_wrong_symbol_and_wrong_market_wording_are_rejected() -> None:
    raw = _body(symbol="9999")
    with pytest.raises(InactiveTerminationEvidenceError, match="symbol does not match"):
        _parse(raw, _metadata(raw))

    wrong_market = _body().replace("上櫃之有價證券".encode(), "上市之有價證券".encode())
    with pytest.raises(InactiveTerminationEvidenceError, match="market scope"):
        _parse(wrong_market, _metadata(wrong_market))


def test_wrong_notice_dates_are_rejected() -> None:
    raw = _body(terminated="115年10月2日")

    with pytest.raises(InactiveTerminationEvidenceError, match="termination date"):
        _parse(raw, _metadata(raw))


def test_missing_explicit_common_stock_conversion_is_rejected() -> None:
    raw = _body(conversion="股東依公告完成股份處理。")

    with pytest.raises(InactiveTerminationEvidenceError, match="does not prove ordinary"):
        _parse(raw, _metadata(raw))


def test_other_issuer_common_stock_conversion_does_not_prove_target_inactive_type() -> None:
    raw = _body(conversion="另一公司每1股普通股換發另一公司子公司普通股。")

    with pytest.raises(InactiveTerminationEvidenceError, match="does not prove ordinary"):
        _parse(raw, _metadata(raw))


def test_raw_hash_and_raw_byte_count_must_match_exact_body() -> None:
    original = _body()
    tampered = original + b" "
    with pytest.raises(InactiveTerminationEvidenceError, match="SHA-256"):
        _parse(tampered, _metadata(original))

    response = _metadata(original)
    response["raw_bytes"] = len(original) + 1
    with pytest.raises(InactiveTerminationEvidenceError, match="byte count"):
        _parse(original, response)


def test_capture_time_must_be_real_and_before_cutoff_not_backfilled() -> None:
    raw = _body()
    response = _metadata(raw)
    after_cutoff = datetime(2026, 10, 1, 0, 31, tzinfo=timezone.utc)
    response["captured_at"] = after_cutoff.isoformat()
    response["raw_path"] = "attempt/raw/late.html"

    with pytest.raises(InactiveTerminationEvidenceError, match="after the real cutoff"):
        _parse(raw, response, actual_capture_at=after_cutoff)


def test_publication_date_cannot_be_after_actual_taipei_capture_date() -> None:
    spec = _spec(
        published_on=date(2026, 10, 1),
        suspension_effective_on=date(2026, 10, 2),
        termination_effective_on=date(2026, 10, 3),
        source_url="https://www.tpex.org.tw/storage/eb_data/11510/11500054131.html",
    )
    capture_before_publication = datetime(2026, 9, 30, 15, 50, tzinfo=timezone.utc)
    real_cutoff_after_effective = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
    raw = _body(
        published="中華民國115年10月1日",
        suspended="115年10月2日",
        terminated="115年10月3日",
    )
    response = _metadata(raw, captured_at=capture_before_publication)
    response["request_url"] = spec.source_url
    response["final_url"] = spec.source_url

    with pytest.raises(InactiveTerminationEvidenceError, match="publication date is after"):
        _parse(
            raw,
            response,
            spec,
            actual_capture_at=capture_before_publication,
            real_cutoff=real_cutoff_after_effective,
        )


def test_termination_must_be_effective_at_cutoff() -> None:
    before_effective = datetime(2026, 9, 30, 15, 59, tzinfo=timezone.utc)
    captured_before_effective = datetime(2026, 9, 30, 15, 50, tzinfo=timezone.utc)
    raw = _body()
    response = _metadata(raw, captured_at=captured_before_effective)

    with pytest.raises(InactiveTerminationEvidenceError, match="not effective"):
        _parse(
            raw,
            response,
            actual_capture_at=captured_before_effective,
            real_cutoff=before_effective,
        )


def test_proof_readback_recomputes_bytes_and_rejects_mutation() -> None:
    raw = _body()
    response = _metadata(raw)
    proof = _parse(raw, response)

    reread = validate_official_termination_proof_readback(
        raw, response, _spec(), CAPTURED_AT, REAL_CUTOFF, proof.to_dict()
    )
    assert reread == proof

    tampered = proof.to_dict()
    tampered["eligible"] = True
    with pytest.raises(InactiveTerminationEvidenceError, match="differs from source-byte"):
        validate_official_termination_proof_readback(
            raw, response, _spec(), CAPTURED_AT, REAL_CUTOFF, tampered
        )


def test_readback_rejects_unrecognized_extra_proof_fields() -> None:
    raw = _body()
    response = _metadata(raw)
    proof = _parse(raw, response).to_dict()
    proof["isin_code"] = "FICTIONAL"

    with pytest.raises(InactiveTerminationEvidenceError, match="differs from source-byte"):
        validate_official_termination_proof_readback(
            raw, response, _spec(), CAPTURED_AT, REAL_CUTOFF, proof
        )
