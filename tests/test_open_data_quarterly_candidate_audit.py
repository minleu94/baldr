from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from data_module.open_data_quarterly_candidate_audit import (
    AUDIT_SCHEMA,
    GENERAL_MANIFEST_SCHEMA,
    MANIFEST_SCHEMA,
    QuarterlyCandidateAuditError,
    audit_quarterly_candidate_root,
)


def _manifest_source(
    *, dataset_id: str, artifact: str, body: bytes, industry: str = "general"
) -> dict[str, object]:
    digest = hashlib.sha256(body).hexdigest()
    return {
        "dataset_id": dataset_id,
        "market": "TWSE",
        "statement": "balance_sheet",
        "industry": industry,
        "catalog_url": f"https://data.gov.tw/dataset/{dataset_id}",
        "url": "https://example.invalid/resource.csv",
        "method": "GET",
        "redirects_followed": False,
        "max_body_bytes": 32 * 1024 * 1024,
        "status": 200,
        "body_bytes": len(body),
        "body_sha256": digest,
        "readback_bytes": len(body),
        "readback_sha256": digest,
        "readback_matches": True,
        "artifact": artifact,
        "csv_parse_status": "parsed",
        "error": None,
    }


def _write_manifest(
    root: Path,
    sources: list[dict[str, object]],
    *,
    schema: str = MANIFEST_SCHEMA,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": schema,
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "sources": sources,
    }
    (root / "capture_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_audit_profiles_each_resource_without_merging_or_exposing_values(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    root.mkdir(parents=True)
    active_body = (
        "\ufeff出表日期,年度,季別,公司代號,公司名稱,營收,EPS\n"
        "1151026,115,2,2330,台積電,0,N/A\n"
        "1151026,115,2,2330,台積電,,--\n"
        "1151026,115,2,2317,鴻海,null,SECRET_FINANCIAL_54821\n"
    ).encode("utf-8")
    empty_body = "出表日期,年度,季別,公司代號,公司名稱,營收\n".encode("utf-8")
    (root / "active.csv").write_bytes(active_body)
    (root / "empty.csv").write_bytes(empty_body)
    tampered_body = b"original body"
    (root / "tampered.csv").write_bytes(b"changed body")
    sources = [
        _manifest_source(dataset_id="1", artifact="active.csv", body=active_body),
        _manifest_source(dataset_id="2", artifact="empty.csv", body=empty_body),
        _manifest_source(dataset_id="3", artifact="missing.csv", body=b"missing"),
        _manifest_source(dataset_id="4", artifact="tampered.csv", body=tampered_body),
    ]
    _write_manifest(root, sources)

    result = audit_quarterly_candidate_root(root)
    payload = result.to_dict()
    assert payload["schema_version"] == AUDIT_SCHEMA
    assert payload["candidate_only"] is True
    assert payload["formal_db_write"] is False
    assert payload["source_acceptance"] is False
    assert payload["gate_credit"] is False
    assert payload["downstream_eligibility"] == "none"
    assert payload["overall_state"] == "invalid"
    assert payload["summary"] == {
        "resource_count": 4,
        "available_resource_count": 1,
        "empty_response_resource_count": 1,
        "missing_resource_count": 1,
        "invalid_resource_count": 1,
        "summary_complete": False,
        "row_count": 3,
        "unique_issuer_resource_count": 2,
        "duplicate_business_key_count": 1,
    }

    active, empty, missing, tampered = payload["resources"]
    assert active["state"] == "available"
    assert active["sha256"] == hashlib.sha256(active_body).hexdigest()
    assert active["manifest_sha256"] == active["sha256"]
    assert active["row_count"] == 3
    assert active["unique_issuer_count"] == 2
    assert active["periods"] == ["115-Q2"]
    assert active["output_dates"] == ["1151026"]
    assert active["duplicate_business_key_count"] == 1
    assert active["duplicate_business_key_row_count"] == 1
    assert active["schema_fingerprint"]
    assert active["headers"] == ["出表日期", "年度", "季別", "公司代號", "公司名稱", "營收", "EPS"]
    fields = {field["field_name"]: field for field in active["field_counts"]}
    assert set(fields) == {"營收", "EPS"}
    assert fields["營收"] == {
        "field_name": "營收",
        "blank_count": 1,
        "nonblank_count": 2,
        "known_placeholder_counts": {"null": 1},
    }
    assert fields["EPS"]["blank_count"] == 0
    assert fields["EPS"]["nonblank_count"] == 3
    assert fields["EPS"]["known_placeholder_counts"] == {"--": 1, "N/A": 1}
    assert active["row_profile_count"] == 2
    assert active["row_profiles_truncated"] is False
    assert active["row_profiles_complete"] is True
    assert active["row_profiles"] == [
        {
            "issuer_code": "2317",
            "issuer_name": "鴻海",
            "issuer_name_conflict": False,
            "fiscal_period": "115-Q2",
            "output_dates": ["1151026"],
            "source_row_count": 1,
            "blank_cell_count": 0,
            "nonblank_cell_count": 2,
            "blank_fields": [],
            "known_placeholder_counts": {"null": 1},
        },
        {
            "issuer_code": "2330",
            "issuer_name": "台積電",
            "issuer_name_conflict": False,
            "fiscal_period": "115-Q2",
            "output_dates": ["1151026"],
            "source_row_count": 2,
            "blank_cell_count": 1,
            "nonblank_cell_count": 3,
            "blank_fields": ["營收"],
            "known_placeholder_counts": {"--": 1, "N/A": 1},
        },
    ]
    profile_json = json.dumps(active["row_profiles"], ensure_ascii=False)
    assert "SECRET_FINANCIAL_54821" not in profile_json
    assert "original body" not in json.dumps(payload, ensure_ascii=False)
    assert (root / "active.csv").read_bytes() == active_body

    assert empty["state"] == "empty_response"
    assert empty["row_count"] == 0
    assert empty["unique_issuer_count"] == 0
    assert empty["field_counts"] == []
    assert empty["row_profiles"] == []
    assert empty["row_profile_count"] == 0
    assert empty["row_profile_scanned_key_count"] == 0
    assert empty["row_profiles_truncated"] is False
    assert empty["row_profiles_complete"] is True
    assert missing["state"] == "missing"
    assert missing["row_count"] is None
    assert tampered["state"] == "invalid"
    assert tampered["sha256"] == hashlib.sha256(b"changed body").hexdigest()
    assert tampered["manifest_sha256"] == hashlib.sha256(tampered_body).hexdigest()


def test_row_profiles_preserve_period_and_output_date_values_and_aggregate_duplicates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,營收,EPS\n"
        " 1151026 , 115 , 2 ,2330,台積電,,N/A\n"
        "1151027,115,2,2330,TSMC,100,NA\n"
    ).encode("utf-8")
    (root / "resource.csv").parent.mkdir(parents=True)
    (root / "resource.csv").write_bytes(body)
    _write_manifest(root, [_manifest_source(dataset_id="10", artifact="resource.csv", body=body)])

    resource = audit_quarterly_candidate_root(root).to_dict()["resources"][0]
    assert resource["duplicate_business_key_count"] == 1
    assert resource["duplicate_business_key_row_count"] == 1
    assert resource["row_profile_count"] == 1
    assert resource["row_profile_scanned_key_count"] == 1
    assert resource["row_profiles"] == [
        {
            "issuer_code": "2330",
            "issuer_name": None,
            "issuer_name_conflict": True,
            "fiscal_period": "115-Q2",
            "output_dates": [" 1151026 ", "1151027"],
            "source_row_count": 2,
            "blank_cell_count": 1,
            "nonblank_cell_count": 3,
            "blank_fields": ["營收"],
            "known_placeholder_counts": {"N/A": 1, "NA": 1},
        }
    ]


def test_row_profile_cap_reports_scanned_count_and_truncation(tmp_path: Path) -> None:
    from data_module.open_data_quarterly_candidate_audit import (
        MAX_ROW_PROFILES_PER_RESOURCE,
    )

    root = tmp_path / "candidate"
    rows = [
        f"1151026,115,2,{index:05d},Issuer {index},,N/A"
        for index in range(MAX_ROW_PROFILES_PER_RESOURCE + 1)
    ]
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,營收,EPS\n"
        + "\n".join(rows)
        + "\n"
    ).encode("utf-8")
    (root / "resource.csv").parent.mkdir(parents=True)
    (root / "resource.csv").write_bytes(body)
    _write_manifest(root, [_manifest_source(dataset_id="11", artifact="resource.csv", body=body)])

    resource = audit_quarterly_candidate_root(root).to_dict()["resources"][0]
    assert resource["row_profile_count"] == MAX_ROW_PROFILES_PER_RESOURCE
    assert resource["row_profile_scanned_key_count"] == MAX_ROW_PROFILES_PER_RESOURCE + 1
    assert resource["row_profiles_truncated"] is True
    assert resource["row_profiles_complete"] is False
    assert resource["row_profiles"][0]["issuer_code"] == "00000"
    assert resource["row_profiles"][-1]["issuer_code"] == "04999"
    assert any(
        "5000 keys" in warning and "5001 distinct keys were scanned"
        for warning in resource["warnings"]
    )


def test_header_only_response_with_output_date_is_empty_not_coverage(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,營業收入\n"
        '"1151026","","","","",""\n'
    ).encode("utf-8")
    (root / "one.csv").parent.mkdir(parents=True)
    (root / "one.csv").write_bytes(body)
    _write_manifest(root, [_manifest_source(dataset_id="9", artifact="one.csv", body=body)])

    report = audit_quarterly_candidate_root(root).to_dict()
    resource = report["resources"][0]
    assert resource["state"] == "empty_response"
    assert resource["row_count"] == 0
    assert resource["output_dates"] == ["1151026"]
    assert report["summary"]["unique_issuer_resource_count"] == 0


def test_nested_general_industry_manifest_schema_is_supported(tmp_path: Path) -> None:
    root = tmp_path / "general-candidate"
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,資產總計\n"
        "1151026,115,2,2330,台積電,100\n"
    ).encode("utf-8")
    (root / "general.csv").parent.mkdir(parents=True)
    (root / "general.csv").write_bytes(body)
    flat = _manifest_source(dataset_id="94831", artifact="general.csv", body=body)
    nested = {
        "dataset_id": flat.pop("dataset_id"),
        "market": flat.pop("market"),
        "statement": flat.pop("statement"),
        "catalog_url": "https://data.gov.tw/dataset/94831",
        "url": "https://example.invalid/resource.csv",
    }
    flat["source"] = nested
    flat["request_method"] = flat.pop("method")
    flat["http_status"] = flat.pop("status")
    flat["status"] = "captured"
    flat["truncated_at_limit"] = False
    _write_manifest(root, [flat], schema=GENERAL_MANIFEST_SCHEMA)

    result = audit_quarterly_candidate_root(root).to_dict()
    resource = result["resources"][0]
    assert resource["dataset_id"] == "94831"
    assert resource["market"] == "TWSE"
    assert resource["statement"] == "balance_sheet"
    assert resource["industry"] == "unknown"
    assert resource["state"] == "available"
    assert resource["row_count"] == 1


def test_manifest_safety_flags_and_artifact_root_containment_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    body = b"out-of-root"
    outside = tmp_path / "outside.csv"
    outside.write_bytes(body)
    source = _manifest_source(dataset_id="1", artifact="outside.csv", body=body)
    source["artifact"] = "../outside.csv"
    _write_manifest(root, [source])

    resource = audit_quarterly_candidate_root(root).to_dict()["resources"][0]
    assert resource["state"] == "invalid"
    assert "artifact_must_be_basename" in resource["warnings"][0]

    manifest_path = root / "capture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["formal_db_write"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(QuarterlyCandidateAuditError, match="safety_flag:formal_db_write"):
        audit_quarterly_candidate_root(root)


def test_invalid_csv_row_width_and_unsupported_manifest_schema_are_diagnostic(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    body = (
        "出表日期,年度,季別,公司代號,公司名稱,營收\n"
        "1151026,115,2,2330,台積電\n"
    ).encode("utf-8")
    (root / "bad.csv").parent.mkdir(parents=True)
    (root / "bad.csv").write_bytes(body)
    _write_manifest(root, [_manifest_source(dataset_id="2", artifact="bad.csv", body=body)])
    result = audit_quarterly_candidate_root(root).to_dict()
    assert result["resources"][0]["state"] == "invalid"
    assert "row width differs" in result["resources"][0]["warnings"][0]

    manifest_path = root / "capture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "unknown.v9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(QuarterlyCandidateAuditError, match="schema_unsupported"):
        audit_quarterly_candidate_root(root)


def test_manifest_body_readback_mismatch_is_invalid_without_reading_resource(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    body = b"header-only placeholder"
    (root / "resource.csv").parent.mkdir(parents=True)
    (root / "resource.csv").write_bytes(body)
    source = _manifest_source(dataset_id="5", artifact="resource.csv", body=body)
    source["readback_sha256"] = "0" * 64
    _write_manifest(root, [source])

    resource = audit_quarterly_candidate_root(root).to_dict()["resources"][0]
    assert resource["state"] == "invalid"
    assert resource["sha256"] is None
    assert "receipt is invalid" in resource["warnings"][0]
