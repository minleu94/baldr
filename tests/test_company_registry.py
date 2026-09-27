from __future__ import annotations

import csv

from data_module.company_registry import (
    CompanyRegistryDiagnostic,
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
