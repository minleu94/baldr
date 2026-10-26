from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.open_data_issuer_directory_candidate_audit import (
    IssuerDirectoryCandidateAuditError,
    audit_issuer_directory_candidate_root,
    build_quarterly_candidate_directory_comparison,
)


def _write_directory_candidate(root: Path) -> None:
    sources: list[dict[str, Any]] = []
    payloads = {
        "18419": ("TWSE", "18419_twse_company_directory.csv", [("1151025", "1101", "台泥", "01"), ("1151025", "1589", "永冠-KY", "91")]),
        "25036": ("TPEx", "25036_tpex_company_directory.csv", [("1151025", "6488", "環球晶", "22")]),
    }
    for dataset_id, (market, filename, rows) in payloads.items():
        path = root / filename
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("出表日期", "公司代號", "公司名稱", "產業別"))
            writer.writerows(rows)
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        sources.append(
            {
                "source": {"dataset_id": dataset_id, "market": market},
                "method": "GET",
                "redirects_followed": False,
                "http_status": 200,
                "truncated": False,
                "status": "captured",
                "readback_matches": True,
                "artifact": filename,
                "body_bytes": len(body),
                "readback_bytes": len(body),
                "max_body_bytes": 1024 * 1024,
                "body_sha256": digest,
                "readback_sha256": digest,
                "csv_profile": {
                    "code_column": "公司代號",
                    "industry_column": "產業別",
                    "row_count": len(rows),
                    "unique_codes": len(rows),
                    "output_date_distribution": {"1151025": len(rows)},
                },
            }
        )
    (root / "capture_manifest.json").write_text(
        json.dumps(
            {
                "schema": "baldr.open_data_issuer_directory_candidate.v1",
                "candidate_only": True,
                "formal_db_write": False,
                "source_acceptance": False,
                "gate_credit": False,
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )


def _quarterly_audit() -> dict[str, Any]:
    return {
        "schema_version": "baldr.open_data_quarterly_candidate_audit.v1",
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "resources": [
            {
                "market": "TWSE",
                "state": "available",
                "row_profiles_complete": True,
                "row_profiles": [
                    {"issuer_code": "1101", "fiscal_period": "115-Q2", "output_dates": ["1151026"]},
                    {"issuer_code": "2357", "fiscal_period": "115-Q2", "output_dates": ["1151026"]},
                ],
            }
        ],
    }


def test_directory_manifest_and_csv_are_verified_read_only_candidates(tmp_path: Path) -> None:
    _write_directory_candidate(tmp_path)

    report = audit_issuer_directory_candidate_root(tmp_path).to_dict()

    assert report["schema_version"] == "baldr.open_data_issuer_directory_candidate_audit.v1"
    assert report["candidate_only"] is True
    assert report["formal_db_write"] is False
    assert report["source_acceptance"] is False
    assert report["gate_credit"] is False
    assert report["downstream_eligibility"] == "none"
    assert report["directory_dates_by_market"] == {"TWSE": ["1151025"], "TPEx": ["1151025"]}
    assert [row["code"] for row in report["entries"]] == ["6488", "1101", "1589"]


def test_directory_candidate_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    _write_directory_candidate(tmp_path)
    csv_path = tmp_path / "18419_twse_company_directory.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b" ")

    with pytest.raises(IssuerDirectoryCandidateAuditError, match="hash_mismatch"):
        audit_issuer_directory_candidate_root(tmp_path)


def test_directory_manifest_cannot_grant_source_or_gate_eligibility(tmp_path: Path) -> None:
    _write_directory_candidate(tmp_path)
    manifest_path = tmp_path / "capture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_acceptance"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IssuerDirectoryCandidateAuditError, match="boundary"):
        audit_issuer_directory_candidate_root(tmp_path)


def test_comparison_labels_file_discrepancies_without_calling_them_missing_reports(
    tmp_path: Path,
) -> None:
    _write_directory_candidate(tmp_path)
    directory = audit_issuer_directory_candidate_root(tmp_path).to_dict()

    comparison = build_quarterly_candidate_directory_comparison(
        quarterly_audit=_quarterly_audit(), directory_audit=directory
    )

    assert comparison["candidate_only"] is True
    assert comparison["gate_credit"] is False
    assert comparison["downstream_eligibility"] == "none"
    twse = comparison["summary_by_market"]["TWSE"]
    assert twse == {
        "directory_issuer_count": 2,
        "quarterly_candidate_issuer_count": 2,
        "in_both_count": 1,
        "directory_only_in_current_comparison_count": 1,
        "quarterly_candidate_without_directory_match_count": 1,
    }
    states = {(row["market"], row["code"]): row["comparison_state"] for row in comparison["rows"]}
    assert states[("TWSE", "1589")] == "directory_only_in_current_comparison"
    assert states[("TWSE", "2357")] == "quarterly_candidate_without_directory_match"
    assert any("不代表未申報" in item for item in comparison["limitations"])
