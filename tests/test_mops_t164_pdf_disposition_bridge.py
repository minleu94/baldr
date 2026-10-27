import hashlib
import json

import pytest

from data_module.mops_t164_pdf_disposition_bridge import (
    validate_mops_t164_pdf_disposition_bundle,
)
from scripts.validate_mops_t164_pdf_disposition import main as validate_cli


_PDF_BYTES = b"official issuer PDF fixture"
_PDF_SHA = hashlib.sha256(_PDF_BYTES).hexdigest()
_TRUNCATED_PDF_SHA = _PDF_SHA[:20] + _PDF_SHA[21:]
_SOURCE_VERSION = "mops-t164-consolidated-statements-with-t57sb01-xbrl-row-codes.v2"


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _candidate_row(index, statement_type, code):
    period_start = {
        "balance_sheet": None,
        "income_statement": "2026-04-01",
        "cash_flows_statement": "2026-01-01",
    }[statement_type]
    return {
        "stock_code": "2330",
        "market": "sii",
        "period": "2026-Q2",
        "statement_scope": "consolidated",
        "statement_type": statement_type,
        "item_code": code,
        "item_code_source": "mops.t164sb01.xbrl.row_code",
        "item_name": f"item-{code}",
        "source_version": _SOURCE_VERSION,
        "period_start": period_start,
        "period_end": "2026-06-30",
        "item_indent": 1,
        "official_indent_depth": 1,
        "numeric_source_row_sha256": "sha256:" + f"{index + 1:064x}",
        "official_item_name": f"item-{code}",
        "period_basis": {
            "balance_sheet": "period_end_snapshot",
            "income_statement": "quarter_single",
            "cash_flows_statement": "year_to_date",
        }[statement_type],
        "value": index + 1,
        "raw_value": str(index + 1),
        "value_unit": "TWD",
        "value_scale": 1000,
        "announcement_event_timestamp": "2026-08-14T13:46:30+08:00",
        "numeric_available_at": "2026-08-14T13:46:30+08:00",
        "numeric_available_date": "2026-08-15",
        "available_date": "2026-08-15",
        "content_hash": f"{index + 1:064x}",
        "availability_event_sha256": "sha256:" + "c" * 64,
        "item_code_lineage_sha256": "sha256:" + "d" * 64,
    }


def _bundle(tmp_path):
    official_pdf_path = tmp_path / "issuer-report.pdf"
    official_pdf_path.write_bytes(_PDF_BYTES)
    rows = []
    codes = {}
    for statement_type, count, prefix in (
        ("balance_sheet", 57, "B"),
        ("income_statement", 37, "I"),
        ("cash_flows_statement", 78, "C"),
    ):
        codes[statement_type] = [f"{prefix}{index:03d}" for index in range(count)]
        rows.extend(
            _candidate_row(len(rows), statement_type, code)
            for code in codes[statement_type]
        )
    candidate_path = _write_json(
        tmp_path / "candidate.json",
        {
            "schema_version": "mops-statement-pit-candidate.v2",
            "source_id": "mops.statement.publication",
            "source_version": _SOURCE_VERSION,
            "research_only": True,
            "formal_oos_allowed": False,
            "formal_credit_authorized": False,
            "rows": rows,
        },
    )
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

    def bridge(filename, bridge_rows, hash_field="candidate_artifact_sha256"):
        return _write_json(
            tmp_path / filename,
            {
                "company": "2330",
                "period": "2026-Q2",
                hash_field: candidate_sha,
                "candidate_source_version": _SOURCE_VERSION,
                "official_pdf_sha256": _PDF_SHA,
                "formal_db_write": False,
                "gate_credit": False,
                "pit_credit": False,
                "ml_credit": False,
                "numeric_values_emitted": False,
                "rows": bridge_rows,
            },
        )

    bs_codes = codes["balance_sheet"]
    bs_pdf_rows = [
        {"item_code": code, "pdf_mapping": mapping}
        for code, mapping in zip(
            bs_codes[:44],
            [
                *(["direct_pdf_code_label_value_match"] * 38),
                *(["pdf_1920_plus_1990_aggregate"] * 3),
                "candidate_zero_pdf_dash",
                "no_standalone_pdf_page4_row",
                "no_standalone_pdf_page4_row",
            ],
        )
    ]
    bs_pdf_path = bridge(
        "bs-pdf.json", bs_pdf_rows, "candidate_projection_sha256"
    )
    bs_open_rows = []
    for index, code in enumerate(bs_codes[44:], start=44):
        candidate_row = rows[index]
        bs_open_rows.append(
            {
                "item_code": code,
                "numeric_source_row_sha256": candidate_row["numeric_source_row_sha256"],
                "official_item_name": candidate_row["official_item_name"],
                "period_basis": candidate_row["period_basis"],
                "unit": candidate_row["value_unit"],
                "scale": candidate_row["value_scale"],
                "period": "2026-Q2",
                "pdf_comparison": "pdf_code_alias" if index == 44 else "pdf_same_code",
            }
        )
    bs_open_path = bridge("bs-open.json", bs_open_rows, "candidate_sha256")

    income_comparisons = [
        *(["exact_visual_match"] * 33),
        "label_and_value_match_code_differs",
        "candidate_value_reconciles_to_pdf_components",
        "candidate_zero_rendered_as_dash",
        "no_independent_pdf_line",
    ]
    income_path = bridge(
        "income.json",
        [
            {"item_code": code, "comparison": comparison}
            for code, comparison in zip(codes["income_statement"], income_comparisons)
        ],
    )
    cash_statuses = [
        *(["direct_label_value_match"] * 64),
        "candidate_aggregates_multiple_pdf_lines",
        "candidate_zero_pdf_dash",
        "candidate_zero_pdf_dash",
        *(["no_standalone_pdf_row_subtotal"] * 7),
        "unresolved_mapping",
        "unresolved_mapping",
        "unresolved_mapping",
        "unresolved_gross_net_presentation_semantics",
    ]
    cash_path = bridge(
        "cash.json",
        [
            {"item_code": code, "comparison": comparison}
            for code, comparison in zip(codes["cash_flows_statement"], cash_statuses)
        ],
    )

    summary_counts = {
        "balance_sheet": {
            "direct": 50, "code_alias": 1, "aggregates": 3,
            "zero_vs_dash": 1, "no_independent_pdf_row": 2, "unresolved": 0,
        },
        "income_statement": {
            "direct": 33, "code_alias": 1, "aggregates": 1,
            "zero_vs_dash": 1, "no_independent_pdf_row": 1, "unresolved": 0,
        },
        "cash_flows_statement": {
            "direct": 64, "code_alias": 0, "aggregates": 1,
            "zero_vs_dash": 2, "no_independent_pdf_row": 7, "unresolved": 4,
        },
    }
    summary_path = _write_json(
        tmp_path / "summary.json",
        {
            "schema_version": "baldr.q2.t164_v2.full_pdf_content_bridge_summary.v1",
            "company": "2330",
            "period": "2026-Q2",
            "candidate_projection_sha256": candidate_sha,
            "official_pdf_sha256": _PDF_SHA,
            "candidate_rows_classified": 172,
            "statements": [
                {"statement": statement, "rows": sum(statuses.values()), **statuses}
                for statement, statuses in summary_counts.items()
            ],
            "total_statuses": {
                "direct": 147,
                "code_alias": 2,
                "aggregates": 5,
                "zero_vs_dash": 4,
                "no_independent_pdf_row": 10,
                "unresolved": 4,
            },
            "unresolved_codes": codes["cash_flows_statement"][-4:],
            "formal_db_write": False,
            "gate_credit": False,
            "pit_credit": False,
            "ml_credit": False,
        },
    )
    return {
        "candidate_path": candidate_path,
        "official_pdf_path": official_pdf_path,
        "summary_path": summary_path,
        "balance_sheet_pdf_bridge_path": bs_pdf_path,
        "balance_sheet_open_data_bridge_path": bs_open_path,
        "income_statement_bridge_path": income_path,
        "cash_flow_bridge_path": cash_path,
    }


def test_bundle_validates_complete_row_accounting_and_fail_closed_status(tmp_path):
    report = validate_mops_t164_pdf_disposition_bundle(**_bundle(tmp_path))

    assert report["candidate_row_count"] == 172
    assert report["classified_row_count"] == 172
    assert report["total_status_counts"]["unresolved"] == 4
    assert report["row_accounting_verified"] is True
    assert report["pdf_content_reopened"] is False
    assert report["gate_credit"] is False
    assert report["ml_credit"] is False


def test_bundle_rejects_missing_candidate_disposition(tmp_path):
    bundle = _bundle(tmp_path)
    bridge_path = bundle["cash_flow_bridge_path"]
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["rows"].pop()
    _write_json(bridge_path, payload)

    with pytest.raises(ValueError, match="row count mismatch|does not account"):
        validate_mops_t164_pdf_disposition_bundle(**bundle)


def test_bundle_rejects_pdf_hash_drift(tmp_path):
    bundle = _bundle(tmp_path)
    bridge_path = bundle["income_statement_bridge_path"]
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    payload["official_pdf_sha256"] = "b" * 64
    _write_json(bridge_path, payload)

    with pytest.raises(ValueError, match="PDF bridge reference does not match"):
        validate_mops_t164_pdf_disposition_bundle(**bundle)


def test_bundle_records_single_character_pdf_reference_omission(tmp_path):
    bundle = _bundle(tmp_path)
    for key in (
        "summary_path",
        "balance_sheet_pdf_bridge_path",
        "income_statement_bridge_path",
        "cash_flow_bridge_path",
    ):
        path = bundle[key]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["official_pdf_sha256"] = _TRUNCATED_PDF_SHA
        _write_json(path, payload)

    report = validate_mops_t164_pdf_disposition_bundle(**bundle)

    assert report["pdf_reference_status"]["summary"] == "single_character_omission"
    assert report["pdf_reference_status"]["balance_sheet_open_data"] == "exact"
    assert report["pdf_reference_corrections"]["cash_flows_statement"]["verified_pdf_bytes_sha256"] == _PDF_SHA


def test_cli_refuses_to_overwrite_candidate_input(tmp_path, capsys):
    bundle = _bundle(tmp_path)
    original_candidate = bundle["candidate_path"].read_bytes()
    arguments = [
        "--candidate", str(bundle["candidate_path"]),
        "--official-pdf", str(bundle["official_pdf_path"]),
        "--summary", str(bundle["summary_path"]),
        "--balance-sheet-pdf-bridge", str(bundle["balance_sheet_pdf_bridge_path"]),
        "--balance-sheet-open-data-bridge", str(bundle["balance_sheet_open_data_bridge_path"]),
        "--income-statement-bridge", str(bundle["income_statement_bridge_path"]),
        "--cash-flow-bridge", str(bundle["cash_flow_bridge_path"]),
        "--output", str(bundle["candidate_path"]),
    ]

    assert validate_cli(arguments) == 2
    assert bundle["candidate_path"].read_bytes() == original_candidate
    assert "must not overlap" in capsys.readouterr().out

\n