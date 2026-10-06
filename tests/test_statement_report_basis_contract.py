from __future__ import annotations

import pytest

from data_module.statement_report_basis_contract import (
    resolve_statement_report_basis,
)


def test_statement_basis_accepts_explicit_and_exact_legacy_mops_contract() -> None:
    assert resolve_statement_report_basis(
        explicit_value="individual",
        explicit_column_present=True,
        source="unknown.source",
        source_version="v1",
    ) == "individual"
    assert resolve_statement_report_basis(
        explicit_value=None,
        explicit_column_present=False,
        source="mops.financial_statement.raw",
        source_version="mops-t164-consolidated-v2",
    ) == "consolidated"


@pytest.mark.parametrize(
    ("source", "source_version"),
    (
        ("financial_data.income_statement_csv", "financial-data-statements-v1"),
        ("financial_data.balance_sheet_csv", "financial-data-statements-2026-06-17"),
        ("mops.financial_statement.raw", "mops-t164-individual-v1"),
    ),
)
def test_statement_basis_rejects_unproven_generic_financial_prefixes(
    source: str,
    source_version: str,
) -> None:
    with pytest.raises(ValueError, match="unproven"):
        resolve_statement_report_basis(
            explicit_value=None,
            explicit_column_present=False,
            source=source,
            source_version=source_version,
        )
