from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib

import pytest

from data_module.company_registry import (
    CompanyRegistryDiagnostic,
    build_company_registry_source_contract,
    build_company_registry_rows,
    write_company_registry_csv,
)


def test_build_company_registry_rows_normalizes_twse_and_tpex_sources() -> None:
    result = build_company_registry_rows(
        twse_rows=[
            {
                "出表日期": "1150615",
                "公司代號": "9935",
                "公司簡稱": "慶豐富",
                "產業別": "38",
            }
        ],
        tpex_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "3207",
                "CompanyAbbreviation": "耀勝",
                "SecuritiesIndustryCode": "28",
            }
        ],
        emerging_rows=[
            {
                "Date": "1150616",
                "SecuritiesCompanyCode": "6871",
                "CompanyAbbreviation": "新創",
                "SecuritiesIndustryCode": "36",
            }
        ],
        download_time="2026-06-16 12:00:00",
    )

    assert result.diagnostics == ()
    assert [row.to_csv_row() for row in result.rows] == [
        {
            "industry_category": "居家生活",
            "stock_id": "9935",
            "stock_name": "慶豐富",
            "type": "twse",
            "date": "2026-06-15",
            "download_time": "2026-06-16 12:00:00",
        },
        {
            "industry_category": "電子零組件業",
            "stock_id": "3207",
            "stock_name": "耀勝",
            "type": "tpex",
            "date": "2026-06-16",
            "download_time": "2026-06-16 12:00:00",
        },
        {
            "industry_category": "數位雲端",
            "stock_id": "6871",
            "stock_name": "新創",
            "type": "emerging",
            "date": "2026-06-16",
            "download_time": "2026-06-16 12:00:00",
        },
    ]


def test_build_company_registry_rows_reports_unknown_industry_code() -> None:
    result = build_company_registry_rows(
        twse_rows=[
            {
                "出表日期": "1150615",
                "公司代號": "9999",
                "公司簡稱": "未知",
                "產業別": "ZZ",
            }
        ],
        tpex_rows=[],
        emerging_rows=[],
        download_time="2026-06-16 12:00:00",
    )

    assert result.rows == ()
    diagnostic = result.diagnostics[0]
    assert isinstance(diagnostic, CompanyRegistryDiagnostic)
    payload = diagnostic.to_dict()
    assert tuple(payload) == ("code", "factor_name", "stock_code", "message")
    assert payload == {
        "code": "company_registry.unknown_industry_code",
        "factor_name": "company_registry",
        "stock_code": "9999",
        "message": "unknown official industry code: ZZ",
    }


def test_build_company_registry_rows_preserves_diagnostic_order() -> None:
    result = build_company_registry_rows(
        twse_rows=[
            {"公司簡稱": "不完整", "產業別": "01"},
            {"公司代號": "9999", "公司簡稱": "未知", "產業別": "ZZ"},
        ],
        tpex_rows=[],
        emerging_rows=[],
        download_time="2026-06-16 12:00:00",
    )

    assert result.rows == ()
    assert all(isinstance(item, CompanyRegistryDiagnostic) for item in result.diagnostics)
    assert [item.code for item in result.diagnostics] == [
        "company_registry.invalid_row",
        "company_registry.unknown_industry_code",
    ]
    payloads = [item.to_dict() for item in result.diagnostics]
    assert all(
        tuple(payload) == ("code", "factor_name", "stock_code", "message")
        for payload in payloads
    )
    assert payloads == [
        {
            "code": "company_registry.invalid_row",
            "factor_name": "company_registry",
            "stock_code": "",
            "message": "official company registry row is missing stock code, name, or industry code",
        },
        {
            "code": "company_registry.unknown_industry_code",
            "factor_name": "company_registry",
            "stock_code": "9999",
            "message": "unknown official industry code: ZZ",
        },
    ]


def test_write_company_registry_csv_preserves_expected_schema(tmp_path) -> None:
    result = build_company_registry_rows(
        twse_rows=[
            {
                "出表日期": "1150615",
                "公司代號": "9935",
                "公司簡稱": "慶豐富",
                "產業別": "38",
            }
        ],
        tpex_rows=[],
        emerging_rows=[],
        download_time="2026-06-16 12:00:00",
    )
    output = tmp_path / "companies.csv"

    write_company_registry_csv(output, result.rows)

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "industry_category": "居家生活",
            "stock_id": "9935",
            "stock_name": "慶豐富",
            "type": "twse",
            "date": "2026-06-15",
            "download_time": "2026-06-16 12:00:00",
        }
    ]
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert output.read_bytes().splitlines()[0] == (
        b"\xef\xbb\xbfindustry_category,stock_id,stock_name,type,date,download_time"
    )


def test_company_registry_source_contract_binds_current_csv_without_pit_credit() -> None:
    csv_bytes = b"\xef\xbb\xbfindustry_category,stock_id\r\n\xe5\x8d\x8a\xe5\xb0\x8e\xe9\xab\x94\xe6\xa5\xad,2330\r\n"
    captured_at = "2026-09-27T18:00:00+00:00"
    sources = [
        {
            "market": market,
            "source_id": f"official:{market}:company-registry",
            "endpoint": f"https://example.invalid/{market}.json",
            "requested_url": f"https://example.invalid/{market}.json",
            "format": "json",
            "response_bytes": 3,
            "response_sha256": f"sha256:{hashlib.sha256(market.encode()).hexdigest()}",
            "available_at": captured_at,
            "status": "captured",
            "source_date": "1150919",
            "publication_date": None,
        }
        for market in ("twse", "tpex", "emerging")
    ]

    contract = build_company_registry_source_contract(
        csv_bytes=csv_bytes,
        sources=sources,
        generated_at=datetime(2026, 9, 27, 18, 1, tzinfo=timezone.utc),
    )

    assert contract["status"] == "captured"
    assert contract["scope"] == "current_classification_only"
    assert contract["pit_eligible"] is False
    assert contract["artifact"] == {
        "name": "companies.csv",
        "bytes": len(csv_bytes),
        "sha256": f"sha256:{hashlib.sha256(csv_bytes).hexdigest()}",
    }
    assert all(item["publication_date"] is None for item in contract["sources"])
    assert all(item["source_date"] == "1150919" for item in contract["sources"])
    assert contract["source_contract_sha256"].startswith("sha256:")


@pytest.mark.parametrize("available_at", ["not-a-time", "2026-09-27T18:00:00"])
def test_company_registry_rejects_invalid_or_naive_capture_time(available_at: str) -> None:
    sources = [
        {
            "market": market,
            "source_id": f"official:{market}:company-registry",
            "endpoint": f"https://example.invalid/{market}.json",
            "requested_url": f"https://example.invalid/{market}.json",
            "format": "json",
            "response_bytes": 3,
            "response_sha256": f"sha256:{hashlib.sha256(market.encode()).hexdigest()}",
            "available_at": available_at if market == "twse" else "2026-09-27T18:00:00+00:00",
            "status": "captured",
            "source_date": None,
            "publication_date": None,
        }
        for market in ("twse", "tpex", "emerging")
    ]

    with pytest.raises(ValueError, match="available_at 必須是 aware UTC"):
        build_company_registry_source_contract(
            csv_bytes=b"companies",
            sources=sources,
            generated_at=datetime(2026, 9, 27, 19, 0, tzinfo=timezone.utc),
        )
