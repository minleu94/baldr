from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.build_mops_quarterly_event_numeric_bridge import build_bridge


SOURCES = (
    ("F26", "balance_sheet", "mops.t164sb03.consolidated_balance_sheet", "ajax_t164sb03"),
    ("F27", "income_statement", "mops.t164sb04.consolidated_income_statement", "ajax_t164sb04"),
    ("F28", "cash_flows_statement", "mops.t164sb05.consolidated_cash_flows_statement", "ajax_t164sb05"),
)
LISTING_ROW_HASH = "a" * 64


def _write_json(path: Path, payload: object) -> str:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _run_dir(root: Path) -> tuple[Path, Path]:
    run_dir = root / "quarterly-run"
    run_dir.mkdir()
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()
    announcement_path = root / "announcements.json"
    file_hashes: dict[str, str] = {}
    raw_hashes: dict[str, str] = {}
    source_records = []
    candidate_rows = []
    for event_code, statement_type, source_id, endpoint in SOURCES:
        raw_name = f"{endpoint}_2330_115Q2.html"
        raw_path = raw_dir / raw_name
        raw_hash = sha256((endpoint + "-response").encode()).hexdigest()
        raw_path.write_text(endpoint + "-response", encoding="utf-8")
        raw_hashes[raw_name] = f"sha256:{raw_hash}"
        source_records.append({
            "source_id": source_id,
            "source_version": "mops-endpoint-candidate.v2",
            "statement_type": statement_type,
            "source_url": f"https://mopsov.twse.com.tw/mops/web/{endpoint}",
            "request": {"TYPEK": "sii", "co_id": "2330", "year": "115", "season": "2"},
            "period": "2026-Q2",
            "accepted_numeric_row_count": 2,
            "raw_response": {"basename": raw_name, "sha256": f"sha256:{raw_hash}"},
        })
        for index in range(2):
            row_hash = sha256(f"{statement_type}-{index}".encode()).hexdigest()
            candidate_rows.append({
                "stock_code": "2330",
                "market": "sii",
                "period": "2026-Q2",
                "statement_type": statement_type,
                "announcement_date": "2026-08-14T13:59:44+08:00",
                "publication_timestamp": "2026-08-14T13:59:44+08:00",
                "announcement_event_date": "2026-08-14T13:59:44+08:00",
                "announcement_event_timestamp": "2026-08-14T13:59:44+08:00",
                "numeric_available_at": "2026-09-07T08:00:00+08:00",
                "numeric_available_date": "2026-09-08",
                "available_date": "2026-09-08",
                "content_hash": row_hash,
                "numeric_source_row_sha256": f"sha256:{row_hash}",
                "availability_event_sha256": f"sha256:{LISTING_ROW_HASH}",
                "statement_items": {f"item-{index}": 100 + index},
            })
    file_hashes["statement-sources.json"] = _write_json(run_dir / "statement-sources.json", {"sources": source_records})
    candidate = {
        "schema_version": "mops-statement-pit-candidate.v2",
        "source_id": "mops.statement.publication",
        "source_version": "mops-t164-consolidated-statements.v2",
        "captured_at": "2026-09-07T08:00:00+08:00",
        "research_only": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
        "rows": candidate_rows,
        "lineage": {
            "numeric_statement_source": {"source_id": "mops.financial_statement.raw"},
            "availability_artifact_sha256": "sha256:" + "b" * 64,
            "canonical_dataset_lineage": {"manifest_sha256": "sha256:" + "c" * 64, "dataset_sha256": "sha256:" + "d" * 64},
        },
    }
    file_hashes["statement-pit-candidate.json"] = _write_json(run_dir / "statement-pit-candidate.json", candidate)
    availability = {
        "schema_version": "mops-document-listing-availability.v1",
        "source_id": "mops.document_listing.statement_publication",
        "source_version": "mops-t57sb01.v1",
        "captured_at": "2026-09-07T08:00:00+08:00",
        "research_only": True,
        "formal_oos_allowed": False,
        "raw_response": {"basename": "mops_t57sb01_2330_115.html", "sha256": "sha256:" + "e" * 64},
        "rows": [{
            "stock_code": "2330", "period": "2026-Q2", "period_end": "2026-06-30",
            "publication_timestamp": "2026-08-14T13:59:44+08:00", "document_filename": "202602_2330_AI1.pdf",
            "document_size_bytes": "9323383", "correction_status": "none", "listing_row_sha256": LISTING_ROW_HASH,
        }],
    }
    file_hashes["availability-source.json"] = _write_json(run_dir / "availability-source.json", availability)
    t57_raw = raw_dir / "mops_t57sb01_2330_115.html"
    t57_raw.write_bytes(b"t57 source response")
    raw_hashes[t57_raw.name] = f"sha256:{sha256(t57_raw.read_bytes()).hexdigest()}"

    events = []
    for index, (event_code, statement_type, _source_id, endpoint) in enumerate(SOURCES, start=1):
        event = {
            "stock_code": "2330", "market": "sii", "period": "2026-Q2",
            "period_end": "2026-06-30",
            "statement_type": statement_type, "announcement_item": event_code,
            "announcement_name": event_code, "announcement_at": "2026-08-14T13:46:30+08:00",
            "detail_url": f"https://mopsov.twse.com.tw/mops/web/{endpoint}?TYPEK=all&co_id=2330&year=115&season=2",
        }
        material = {key: event[key] for key in ("announcement_at", "announcement_item", "detail_url", "period", "stock_code")}
        event["event_hash"] = sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        events.append(event)
    _write_json(announcement_path, {
        "schema_version": "mops-ezsearch-statement-availability.v1",
        "source_id": "mops.ezsearch.statement_publication",
        "source_version": "mops-ezsearch-statement-publication.v1",
        "research_only": True,
        "formal_credit_authorized": False,
        "rows": events,
    })
    _write_json(run_dir / "run-manifest.json", {
        "schema_version": "mops-statement-pit-run-manifest.v2",
        "run_id": "quarterly-test-r8",
        "captured_at": "2026-09-07T08:00:00+08:00",
        "research_only": True,
        "formal_oos_allowed": False,
        "files": file_hashes,
        "raw_files": raw_hashes,
    })
    return run_dir, announcement_path


def test_builds_timestamp_corrected_candidate_with_three_exact_event_links(tmp_path: Path) -> None:
    run_dir, announcements = _run_dir(tmp_path)
    bridge, candidate = build_bridge(quarterly_run_dir=run_dir, announcement_artifact=announcements)

    assert bridge["bridge_status"] == "candidate_lineage_verified"
    assert bridge["identity"] == {
        "stock_code": "2330", "period": "2026-Q2", "period_end": "2026-06-30", "statement_scope": "consolidated"
    }
    assert bridge["numeric_row_count"] == 6
    assert [item["announcement_item"] for item in bridge["statement_bridges"]] == ["F26", "F27", "F28"]
    assert all(item["numeric_source_row_count"] == 2 for item in bridge["statement_bridges"])
    assert all(item["query_scope_match"].startswith("issuer-period-endpoint-match") for item in bridge["statement_bridges"])
    assert candidate["rows"][0]["announcement_event_timestamp"] == "2026-08-14T13:46:30+08:00"
    assert candidate["rows"][0]["available_date"] == "2026-08-15"
    assert candidate["rows"][0]["availability_date_basis"] == "mops_announcement_next_taipei_calendar_date"
    assert candidate["rows"][0]["numeric_available_at"] == "2026-09-07T08:00:00+08:00"
    assert candidate["rows"][0]["numeric_available_date"] == "2026-09-08"
    assert candidate["rows"][0]["announcement_event_evidence"]["event_hash"].startswith("sha256:")
    assert candidate["publication_event_bridge"]["pdf_bytes_verification"] == "unverified"
    assert candidate["formal_credit_authorized"] is False
    assert candidate["downstream_eligibility"] == "none"
    canonical_bridge = json.dumps(bridge, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert candidate["publication_event_bridge"]["artifact_sha256"] == f"sha256:{sha256(canonical_bridge).hexdigest()}"


def test_rejects_tampered_raw_t164_bytes(tmp_path: Path) -> None:
    run_dir, announcements = _run_dir(tmp_path)
    (run_dir / "raw" / "ajax_t164sb03_2330_115Q2.html").write_text("changed bytes", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_bridge(quarterly_run_dir=run_dir, announcement_artifact=announcements)


def test_rejects_wrong_period_announcement_even_when_company_matches(tmp_path: Path) -> None:
    run_dir, announcements = _run_dir(tmp_path)
    payload = json.loads(announcements.read_text(encoding="utf-8"))
    payload["rows"][0]["period"] = "2026-Q1"
    _write_json(announcements, payload)
    with pytest.raises(ValueError, match="same-company, same-period F26"):
        build_bridge(quarterly_run_dir=run_dir, announcement_artifact=announcements)
