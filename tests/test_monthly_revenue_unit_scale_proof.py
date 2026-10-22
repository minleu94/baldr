from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast

import pytest

import data_module.monthly_revenue_unit_scale_proof as proof_module
from data_module.monthly_revenue_unit_scale_proof import (
    MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA,
    MonthlyRevenueUnitScaleProofError,
    MopsMonthlyRevenueUnitScaleProof,
    _TableScope,
    _extract_table_scopes,
    _validate_table_scope_payload,
    build_mops_monthly_revenue_unit_scale_proof,
    read_mops_monthly_revenue_unit_scale_proof,
    write_mops_monthly_revenue_unit_scale_proof_create_only,
)
from data_module.mops_monthly_revenue_history import MopsMonthlyRevenueHistoricalCapture


_HEADERS = (
    "公司代號",
    "公司名稱",
    "當月營收",
    "上月營收",
    "去年當月營收",
    "上月比較增減(%)",
    "去年同月增減(%)",
    "當月累計營收",
    "去年累計營收",
    "前期比較增減(%)",
)


def _table(industry: str, stock_code: str, unit: str = "千元") -> str:
    headers = "".join(f"<th>{header}</th>" for header in _HEADERS)
    values = (
        stock_code,
        "測試公司",
        "100",
        "90",
        "80",
        "11.1",
        "25.0",
        "600",
        "500",
        "20.0",
    )
    cells = "".join(f"<td>{value}</td>" for value in (*values, ""))
    group_headers = (
        "<th colspan='2'>&nbsp;</th><th colspan='5'>營業收入</th>"
        "<th colspan='3'>累計營業收入</th><th rowspan='2'>備註</th>"
    )
    return (
        "<table><tr>"
        f"<th>產業別：{industry}</th><th>單位：{unit}</th>"
        "</tr><tr><td colspan='2'><table>"
        f"<tr>{group_headers}</tr><tr>{headers}</tr><tr>{cells}</tr>"
        "</table></td></tr></table>"
    )


def _empty_industry_table(
    industry: str = "存託憑證", *, aggregate_label: str = "合計", amount: str = "0"
) -> str:
    headers = "".join(f"<th>{header}</th>" for header in _HEADERS)
    aggregate_values = (
        amount, amount, amount, "&nbsp;", "&nbsp;", amount, amount, "&nbsp;", "&nbsp;"
    )
    aggregate = (
        f"<tr><th colspan='2'>{aggregate_label}</th>"
        + "".join(f"<td>{value}</td>" for value in aggregate_values)
        + "</tr>"
    )
    group_headers = (
        "<th colspan='2'>&nbsp;</th><th colspan='5'>營業收入</th>"
        "<th colspan='3'>累計營業收入</th><th rowspan='2'>備註</th>"
    )
    return (
        "<table><tr>"
        f"<th>產業別：{industry}</th><th>單位：千元</th>"
        "</tr><tr><td colspan='2'><table>"
        f"<tr>{group_headers}</tr><tr>{headers}</tr>{aggregate}"
        "</table></td></tr></table>"
    )


def test_extracts_scale_only_for_each_explicit_wrapper_table_pair():
    scopes = _extract_table_scopes(
        _table("電子工業", "2330") + _table("食品工業", "1201")
    )

    assert len(scopes) == 2
    assert [scope.table_index for scope in scopes] == [0, 1]
    assert [scope.industry_label for scope in scopes] == ["電子工業", "食品工業"]
    assert all(scope.unit_text == "千元" for scope in scopes)
    assert [scope.stock_codes for scope in scopes] == [("2330",), ("1201",)]
    assert "當月營收" in scopes[0].headers
    assert "當月累計營收" in scopes[0].headers
    assert "備註" not in scopes[0].headers
    assert len(scopes[0].source_rows[0][1]) == 10


def test_nested_outer_table_cell_is_not_treated_as_a_wrapper():
    html = (
        "<table><tr><td>封面文字<table>"
        "<tr><td>其他巢狀內容</td></tr></table></td></tr></table>"
        + _table("電子工業", "2330")
    )

    scopes = _extract_table_scopes(html)

    assert len(scopes) == 1
    assert scopes[0].industry_label == "電子工業"


def test_exact_depositary_receipts_zero_total_is_an_empty_scope():
    all_market_summary = (
        "<table><tr><th colspan='2'>全部國內上市公司合計</th>"
        "<td>5380508645</td></tr></table>"
    )
    scopes = _extract_table_scopes(_empty_industry_table() + all_market_summary)

    assert len(scopes) == 1
    assert scopes[0].industry_label == "存託憑證"
    assert scopes[0].headers == _HEADERS
    assert scopes[0].stock_codes == ()
    assert scopes[0].source_rows == ()


@pytest.mark.parametrize(
    "html",
    (
        _empty_industry_table("其他產業"),
        _empty_industry_table(amount="1"),
        _empty_industry_table(aggregate_label="總計"),
    ),
)
def test_rejects_other_empty_scope_labels_or_nonzero_totals(html: str):
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="table_data_rows_missing"):
        _extract_table_scopes(html)


def test_scope_payload_allows_empty_codes_only_for_depositary_receipts():
    payload = [
        {
            "table_index": 0,
            "wrapper": {"industry_label": "存託憑證", "unit_text": "千元"},
            "inner_table_headers": list(_HEADERS),
            "stock_codes": [],
        }
    ]
    _validate_table_scope_payload(payload, expected_rows=0, expected_tables=1)
    bad_payload = [
        {
            "table_index": 0,
            "wrapper": {"industry_label": "其他產業", "unit_text": "千元"},
            "inner_table_headers": list(_HEADERS),
            "stock_codes": [],
        }
    ]
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="proof_empty_scope_industry_invalid"):
        _validate_table_scope_payload(bad_payload, expected_rows=0, expected_tables=1)


@pytest.mark.parametrize(
    "html",
    (
        _table("電子工業", "2330", unit="元"),
        _table("電子工業", "2330").replace("單位：千元", "", 1),
    ),
)
def test_rejects_missing_or_conflicting_table_unit(html: str):
    with pytest.raises(MonthlyRevenueUnitScaleProofError):
        _extract_table_scopes(html)


def test_rejects_company_code_duplicated_across_industry_tables():
    html = _table("電子工業", "2330") + _table("食品工業", "2330")

    with pytest.raises(
        MonthlyRevenueUnitScaleProofError,
        match="duplicate_stock_code_across_tables",
    ):
        _extract_table_scopes(html)


def test_rejects_incomplete_parser_field_mapping():
    html = _table("電子工業", "2330").replace("<th>當月營收</th>", "", 1)

    with pytest.raises(MonthlyRevenueUnitScaleProofError):
        _extract_table_scopes(html)


@pytest.mark.parametrize(
    "header",
    ("上月比較增減(%)", "前期比較增減(%)", "去年累計營收"),
)
def test_rejects_missing_percentage_or_revenue_field(header: str):
    html = _table("電子工業", "2330").replace(f"<th>{header}</th>", "", 1)

    with pytest.raises(MonthlyRevenueUnitScaleProofError):
        _extract_table_scopes(html)


def test_builder_requires_exact_validated_capture_type():
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="capture_type_invalid"):
        build_mops_monthly_revenue_unit_scale_proof(
            cast(MopsMonthlyRevenueHistoricalCapture, object())
        )


def _handmade_proof() -> MopsMonthlyRevenueUnitScaleProof:
    headers = tuple(_HEADERS)
    stock_codes = [f"{number:04d}" for number in range(1000, 1995)]
    scopes = tuple(
        _TableScope(
            table_index=index,
            industry_label=f"產業{index:02d}",
            unit_text="千元",
            headers=headers,
            stock_codes=tuple(stock_codes[index::33]),
            source_rows=(),
        )
        for index in range(33)
    )
    return MopsMonthlyRevenueUnitScaleProof(
        market="twse",
        source_id="mops.history.monthly_revenue.twse",
        period="2026-06",
        official_url="https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_6_0.html",
        raw_source_sha256="116fa1f6b8a78e8b145b39c1b5048618a92a6df4399698a0d5669ed5c58a5c52",
        raw_source_bytes=454774,
        parser_version="mops-monthly-revenue-history-capture-parser.v2",
        decoder_profile="mops-big5-cp950-strict.v1",
        effective_decoding_encoding="cp950",
        tables=scopes,
        row_count=995,
    )
def test_public_writer_rejects_handmade_proof_even_with_matching_sha(tmp_path):
    proof = _handmade_proof()
    artifact = tmp_path / "handmade-proof.json"
    artifact.write_bytes(proof.canonical_bytes())
    self_computed_sha = hashlib.sha256(proof.canonical_bytes()).hexdigest()
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="capture_type_invalid"):
        write_mops_monthly_revenue_unit_scale_proof_create_only(
            tmp_path / "twse-unit-scale-proof.json",
            cast(MopsMonthlyRevenueHistoricalCapture, proof),
        )
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="capture_type_invalid"):
        read_mops_monthly_revenue_unit_scale_proof(
            artifact,
            expected_sha256=self_computed_sha,
            capture=cast(MopsMonthlyRevenueHistoricalCapture, proof),
        )


def test_proof_artifact_is_create_only_and_readback_is_bound_to_capture(tmp_path, monkeypatch):
    proof = _handmade_proof()
    capture = cast(MopsMonthlyRevenueHistoricalCapture, object())
    monkeypatch.setattr(
        proof_module,
        "build_mops_monthly_revenue_unit_scale_proof",
        lambda supplied: proof if supplied is capture else pytest.fail("capture drift"),
    )
    artifact = tmp_path / "twse-unit-scale-proof.json"
    write_mops_monthly_revenue_unit_scale_proof_create_only(artifact, capture)
    raw = artifact.read_bytes()
    reopened = read_mops_monthly_revenue_unit_scale_proof(
        artifact,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        capture=capture,
    )

    assert reopened["schema_version"] == MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA
    assert reopened["raw_source_sha256"] == proof.raw_source_sha256
    assert reopened["unit_text"] == "千元"
    assert reopened["scale_to_base_unit"] == 1000
    assert reopened["currency"] == "unknown"
    assert reopened["historical_pit_eligible"] is False
    assert reopened["financial_qualification_created"] is False
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="create_only_conflict"):
        write_mops_monthly_revenue_unit_scale_proof_create_only(artifact, capture)


def test_reader_rejects_scale_flag_tampering_even_with_recomputed_sha(tmp_path, monkeypatch):
    proof = _handmade_proof()
    capture = cast(MopsMonthlyRevenueHistoricalCapture, object())
    monkeypatch.setattr(
        proof_module,
        "build_mops_monthly_revenue_unit_scale_proof",
        lambda supplied: proof if supplied is capture else pytest.fail("capture drift"),
    )
    artifact = tmp_path / "proof.json"
    payload = proof.to_dict()
    payload["source_to_parser_field_mapping"][5]["unit_scale_applies"] = True
    artifact.write_bytes(proof_module._canonical_json_bytes(payload))
    tampered_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="proof_sha256_not_bound_to_capture"):
        read_mops_monthly_revenue_unit_scale_proof(
            artifact, expected_sha256=tampered_sha, capture=capture
        )


@pytest.mark.parametrize(
    "overrides,reason",
    (
        ({"requested_url": "https://example.invalid/report.html"}, "capture_identity_or_raw_sha_mismatch"),
        ({"decoder_profile": "wrong-decoder"}, "capture_identity_or_raw_sha_mismatch"),
    ),
)
def test_builder_rejects_source_or_decoder_drift(overrides, reason):
    capture = object.__new__(MopsMonthlyRevenueHistoricalCapture)
    values = {
        "market": "twse",
        "period": "2026-06",
        "requested_url": "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_6_0.html",
        "response_url": "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_6_0.html",
        "transport_mode": "redirect_chain_v1",
        "decoder_profile": "mops-big5-cp950-strict.v1",
        "effective_decoding_encoding": "cp950",
    }
    values.update(overrides)
    for key, value in values.items():
        object.__setattr__(capture, key, value)
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match=reason):
        build_mops_monthly_revenue_unit_scale_proof(capture)


def test_reader_detects_file_replacement_during_bounded_read(tmp_path, monkeypatch):
    proof = _handmade_proof()
    capture = cast(MopsMonthlyRevenueHistoricalCapture, object())
    monkeypatch.setattr(
        proof_module,
        "build_mops_monthly_revenue_unit_scale_proof",
        lambda supplied: proof if supplied is capture else pytest.fail("capture drift"),
    )
    artifact = tmp_path / "proof.json"
    artifact.write_bytes(proof.canonical_bytes())
    original_reader = proof_module._read_bounded_regular_file_no_follow

    def replace_then_read(path, *, maximum_bytes):
        replacement = Path(path).with_suffix(".replacement")
        replacement.write_bytes(proof.canonical_bytes() + b" ")
        os.replace(replacement, path)
        return original_reader(path, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(proof_module, "_read_bounded_regular_file_no_follow", replace_then_read)
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="proof_file_or_parent_changed_during_read"):
        read_mops_monthly_revenue_unit_scale_proof(
            artifact,
            expected_sha256=hashlib.sha256(proof.canonical_bytes()).hexdigest(),
            capture=capture,
        )


def test_parent_chain_rejects_symlink_or_reparse_directory(tmp_path):
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink creation is unavailable")
    with pytest.raises(MonthlyRevenueUnitScaleProofError, match="proof_path_invalid|proof_parent_not_plain_directory"):
        proof_module._resolve_proof_target(alias / "proof.json")
