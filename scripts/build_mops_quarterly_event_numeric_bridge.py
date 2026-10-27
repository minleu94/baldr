"""Build a research-only bridge from MOPS quarterly announcement events to saved T164 rows."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


SCHEMA_VERSION = "mops-quarterly-event-numeric-bridge.v1"
STATEMENT_EVENTS = {
    "F26": ("balance_sheet", "mops.t164sb03.consolidated_balance_sheet", "ajax_t164sb03"),
    "F27": ("income_statement", "mops.t164sb04.consolidated_income_statement", "ajax_t164sb04"),
    "F28": ("cash_flows_statement", "mops.t164sb05.consolidated_cash_flows_statement", "ajax_t164sb05"),
}
SHA256_REFERENCE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TAIPEI_TIMEZONE = timezone(timedelta(hours=8))


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _reference(value: object, field: str) -> str:
    if not isinstance(value, str) or not SHA256_REFERENCE.fullmatch(value):
        raise ValueError(f"{field} must be a sha256 reference")
    return value


def _verified_member(directory: Path, name: str, expected_hash: object, *, field: str) -> Path:
    if Path(name).name != name:
        raise ValueError(f"{field} must be a run-directory basename")
    path = directory / name
    expected = _reference(expected_hash, field)
    if not path.is_file() or f"sha256:{_sha256(path)}" != expected:
        raise ValueError(f"{field} hash mismatch or file missing")
    return path


def build_bridge(*, quarterly_run_dir: Path, announcement_artifact: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify saved candidate lineage, then derive an event-timestamp candidate copy.

    The source run, its source artifacts, and formal data are never modified.
    """
    run_dir = quarterly_run_dir.resolve()
    manifest_path = run_dir / "run-manifest.json"
    manifest = _json(manifest_path)
    if manifest.get("schema_version") != "mops-statement-pit-run-manifest.v2":
        raise ValueError("unsupported quarterly run manifest")
    if manifest.get("research_only") is not True or manifest.get("formal_oos_allowed") is not False:
        raise ValueError("quarterly run manifest must retain research-only boundary")
    file_manifest = manifest.get("files")
    raw_manifest = manifest.get("raw_files")
    if not isinstance(file_manifest, dict) or not isinstance(raw_manifest, dict):
        raise ValueError("run manifest is missing artifact or raw-file hashes")

    required_files = ("statement-pit-candidate.json", "statement-sources.json", "availability-source.json")
    file_paths = {
        name: _verified_member(run_dir, name, file_manifest.get(name), field=f"files.{name}")
        for name in required_files
    }
    raw_dir = run_dir / "raw"
    if not raw_dir.is_dir():
        raise ValueError("quarterly run raw directory is missing")
    raw_paths = {
        name: _verified_member(raw_dir, name, expected, field=f"raw_files.{name}")
        for name, expected in raw_manifest.items()
    }
    candidate = _json(file_paths["statement-pit-candidate.json"])
    sources = _json(file_paths["statement-sources.json"])
    availability = _json(file_paths["availability-source.json"])
    announcements = _json(announcement_artifact)

    if candidate.get("source_id") != "mops.statement.publication" or candidate.get("research_only") is not True:
        raise ValueError("numeric candidate is not the expected research-only MOPS source")
    if candidate.get("formal_oos_allowed") is not False or candidate.get("formal_credit_authorized") is not False:
        raise ValueError("numeric candidate safety boundary is not fail-closed")
    if sources.get("sources") is None or not isinstance(sources["sources"], list):
        raise ValueError("statement-sources artifact is missing source records")
    if announcements.get("source_id") != "mops.ezsearch.statement_publication":
        raise ValueError("announcement artifact is not MOPS EZSearch publication evidence")
    if announcements.get("research_only") is not True or announcements.get("formal_credit_authorized") is not False:
        raise ValueError("announcement artifact safety boundary is not fail-closed")

    candidate_rows = candidate.get("rows")
    announcement_rows = announcements.get("rows")
    if not isinstance(candidate_rows, list) or not isinstance(announcement_rows, list):
        raise ValueError("candidate or announcement artifact is missing rows")
    availability_rows = availability.get("rows")
    if not isinstance(availability_rows, list):
        raise ValueError("availability source artifact is missing rows")
    stock_periods = {
        (str(row.get("stock_code", "")), str(row.get("period", "")))
        for row in candidate_rows
        if isinstance(row, dict)
    }
    if len(stock_periods) != 1:
        raise ValueError("numeric candidate must contain one company-period slice")
    stock_code, period = next(iter(stock_periods))
    matched_availability = [
        row for row in availability_rows
        if isinstance(row, dict) and str(row.get("stock_code")) == stock_code and row.get("period") == period
    ]
    if len(matched_availability) != 1:
        raise ValueError("expected one same-company, same-period T57 availability row")
    availability_row = matched_availability[0]
    listing_row_hash = availability_row.get("listing_row_sha256")
    if not isinstance(listing_row_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", listing_row_hash):
        raise ValueError("T57 availability row hash is invalid")
    listing_event_reference = f"sha256:{listing_row_hash}"
    if any(row.get("availability_event_sha256") != listing_event_reference for row in candidate_rows if isinstance(row, dict)):
        raise ValueError("numeric rows do not all reference the matched T57 availability row")

    source_by_type: dict[str, dict[str, Any]] = {}
    for source in sources["sources"]:
        if isinstance(source, dict) and source.get("statement_type") in {value[0] for value in STATEMENT_EVENTS.values()}:
            statement_type = str(source["statement_type"])
            if statement_type in source_by_type:
                raise ValueError(f"duplicate numeric source for {statement_type}")
            source_by_type[statement_type] = source

    event_hash_source = _sha256(announcement_artifact)
    statement_bridges: list[dict[str, Any]] = []
    corrected_candidate = deepcopy(candidate)
    corrected_rows = corrected_candidate["rows"]
    corrected_row_hashes = [
        row.get("numeric_source_row_sha256")
        for row in corrected_rows
        if isinstance(row, dict)
    ]
    if len(corrected_row_hashes) != len(set(corrected_row_hashes)):
        raise ValueError("numeric_source_row_sha256 values must be unique")
    corrected_rows_by_hash = {
        row.get("numeric_source_row_sha256"): row
        for row in corrected_rows
        if isinstance(row, dict)
    }
    for event_code, (statement_type, source_id, endpoint) in STATEMENT_EVENTS.items():
        numeric_source = source_by_type.get(statement_type)
        if numeric_source is None:
            raise ValueError(f"numeric source missing for {statement_type}")
        source_ref = numeric_source.get("raw_response")
        request = numeric_source.get("request")
        if not isinstance(source_ref, dict) or not isinstance(request, dict):
            raise ValueError(f"numeric source lineage missing for {statement_type}")
        if numeric_source.get("source_id") != source_id or numeric_source.get("period") != period:
            raise ValueError(f"numeric source identity mismatch for {statement_type}")
        if str(request.get("co_id")) != stock_code or request.get("TYPEK") != "sii":
            raise ValueError(f"numeric source request scope mismatch for {statement_type}")
        raw_name = str(source_ref.get("basename", ""))
        raw_path = _verified_member(raw_dir, raw_name, source_ref.get("sha256"), field=f"T164 raw {statement_type}")
        if raw_name not in raw_manifest or f"sha256:{_sha256(raw_path)}" != raw_manifest[raw_name]:
            raise ValueError(f"run manifest does not bind T164 raw {statement_type}")

        matched_events = [
            row for row in announcement_rows
            if isinstance(row, dict)
            and str(row.get("stock_code", "")).zfill(4) == stock_code
            and row.get("period") == period
            and row.get("announcement_item") == event_code
            and row.get("statement_type") == statement_type
        ]
        if len(matched_events) != 1:
            raise ValueError(f"expected exactly one same-company, same-period {event_code} event")
        event = matched_events[0]
        if event.get("market") != "sii" or event.get("period_end") != availability_row.get("period_end"):
            raise ValueError(f"{event_code} market or period-end does not match the T57 issuer-period")
        event_hash = event.get("event_hash")
        if not isinstance(event_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", event_hash):
            raise ValueError(f"{event_code} event hash is invalid")
        event_material = {
            key: str(event[key])
            for key in ("announcement_at", "announcement_item", "detail_url", "period", "stock_code")
        }
        expected_event_hash = sha256(
            json.dumps(event_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if event_hash != expected_event_hash:
            raise ValueError(f"{event_code} event hash does not verify its announcement identity")
        detail_url = event.get("detail_url")
        if not isinstance(detail_url, str):
            raise ValueError(f"{event_code} event detail URL is missing")
        parsed_event_url = urlsplit(detail_url)
        event_query = parse_qs(parsed_event_url.query)
        if not parsed_event_url.path.endswith(endpoint) or event_query.get("co_id") != [stock_code]:
            raise ValueError(f"{event_code} detail endpoint or issuer does not match T164 source")
        if event_query.get("TYPEK") != ["all"]:
            raise ValueError(f"{event_code} MOPS event query scope is unexpected")
        announcement_at = event.get("announcement_at")
        if not isinstance(announcement_at, str) or re.fullmatch(r"\d{4}-\d\d-\d\dT[^\s]+(?:Z|[+-]\d\d:\d\d)", announcement_at) is None:
            raise ValueError(f"{event_code} announcement timestamp must include an ISO timezone")
        try:
            parsed_announcement_at = datetime.fromisoformat(announcement_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{event_code} announcement timestamp is invalid") from exc
        if parsed_announcement_at.tzinfo is None:
            raise ValueError(f"{event_code} announcement timestamp must include an ISO timezone")
        announced_local_date = parsed_announcement_at.astimezone(_TAIPEI_TIMEZONE).date()
        event_available_date = announced_local_date + timedelta(days=1)
        source_rows = [row for row in candidate_rows if isinstance(row, dict) and row.get("statement_type") == statement_type]
        if len(source_rows) != int(numeric_source.get("accepted_numeric_row_count", -1)) or not source_rows:
            raise ValueError(f"numeric row count mismatch for {statement_type}")
        source_version = candidate.get("source_version")
        if not isinstance(source_version, str) or (
            any(row.get("source_version") not in {None, source_version} for row in source_rows)
        ):
            raise ValueError(f"numeric source version mismatch for {statement_type}")
        row_refs = []
        for row in source_rows:
            row_sha = _reference(row.get("numeric_source_row_sha256"), "numeric_source_row_sha256")
            content_hash = row.get("content_hash")
            if not isinstance(content_hash, str) or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
                raise ValueError("numeric row content_hash is invalid")
            row_refs.append({"numeric_source_row_sha256": row_sha, "content_hash": content_hash})
            corrected_row = corrected_rows_by_hash.get(row_sha)
            if not isinstance(corrected_row, dict):
                raise ValueError("numeric row is missing from derived candidate copy")
            corrected_row["announcement_date"] = announcement_at
            corrected_row["publication_timestamp"] = announcement_at
            corrected_row["announcement_event_date"] = announcement_at
            corrected_row["announcement_event_timestamp"] = announcement_at
            corrected_row["available_date"] = event_available_date.isoformat()
            corrected_row["availability_date_basis"] = "mops_announcement_next_taipei_calendar_date"
            corrected_row["announcement_event_evidence"] = {
                "source_id": announcements["source_id"],
                "source_version": announcements.get("source_version"),
                "source_artifact_sha256": f"sha256:{event_hash_source}",
                "event_hash": f"sha256:{event_hash}",
                "announcement_item": event_code,
            }
        statement_bridges.append({
            "announcement_item": event_code,
            "announcement_name": event.get("announcement_name"),
            "statement_type": statement_type,
            "announcement_at": announcement_at,
            "announcement_event_hash": f"sha256:{event_hash}",
            "detail_url": detail_url,
            "numeric_source_id": source_id,
            "numeric_source_version": source_version,
            "numeric_endpoint_source_version": numeric_source.get("source_version"),
            "numeric_source_artifact_sha256": file_manifest["statement-pit-candidate.json"],
            "numeric_statement_source_sha256": file_manifest["statement-sources.json"],
            "numeric_raw_response": {"basename": raw_name, "sha256": raw_manifest[raw_name]},
            "numeric_source_row_count": len(row_refs),
            "numeric_rows": row_refs,
            "t57_listing_row_sha256": listing_event_reference,
            "query_scope_match": "issuer-period-endpoint-match; MOPS TYPEK=all vs T164 TYPEK=sii; TWSE market scope corroborated by issuer event and T57 listing",
        })

    numeric_versions = {candidate.get("source_version")}
    if not isinstance(candidate.get("source_version"), str) or not candidate.get("source_version"):
        raise ValueError("numeric source version is missing from candidate")
    bridge: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_id": "mops.quarterly_event_numeric_bridge",
        "source_version": "mops-quarterly-event-numeric-bridge.v1",
        "captured_at": manifest.get("captured_at"),
        "research_only": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
        "bridge_status": "candidate_lineage_verified",
        "identity": {"stock_code": stock_code, "period": period, "period_end": availability_row.get("period_end"), "statement_scope": "consolidated"},
        "run_id": manifest.get("run_id"),
        "run_manifest_sha256": f"sha256:{_sha256(manifest_path)}",
        "announcement_artifact_sha256": f"sha256:{event_hash_source}",
        "t57_availability_artifact_sha256": file_manifest["availability-source.json"],
        "t57_listing_row_sha256": listing_event_reference,
        "t57_document": {
            "filename": availability_row.get("document_filename"),
            "size_bytes": int(str(availability_row.get("document_size_bytes", "0"))),
            "upload_at": availability_row.get("publication_timestamp"),
            "correction_status": availability_row.get("correction_status"),
            "pdf_bytes_verification": "unverified",
        },
        "numeric_candidate_sha256": file_manifest["statement-pit-candidate.json"],
        "numeric_source_version": candidate.get("source_version"),
        "numeric_row_count": len(candidate_rows),
        "numeric_source_versions_in_this_candidate": sorted(str(item) for item in numeric_versions),
        "statement_bridges": statement_bridges,
        "limitations": [
            "This bridge links saved candidate metadata and hashes; it does not authenticate the local PDF bytes.",
            "The numeric capture timestamp/date remain unchanged as first-observed lineage; date-only availability is the next Taipei calendar date after the MOPS announcement.",
            "This does not prove the PDF and T164 numeric payload are the same report version.",
            "This unique version applies only to the saved r8 candidate; it does not resolve the three current formal-observation version groups.",
            "No formal database rows, source acceptance, Gate credit, or ML eligibility are granted.",
        ],
    }
    bridge_hash = sha256(json.dumps(bridge, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    corrected_candidate["lineage"]["publication_event_bridge"] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_sha256": f"sha256:{bridge_hash}",
        "event_count": len(statement_bridges),
    }
    corrected_candidate["lineage"]["availability_artifact_sha256"] = f"sha256:{_sha256(file_paths['availability-source.json'])}"
    corrected_candidate["publication_event_bridge"] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_sha256": f"sha256:{bridge_hash}",
        "status": "candidate_only",
        "formal_oos_allowed": False,
        "pdf_bytes_verification": "unverified",
    }
    return bridge, corrected_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarterly-run-dir", type=Path, required=True)
    parser.add_argument("--announcement-artifact", type=Path, required=True)
    parser.add_argument("--output-bridge", type=Path, required=True)
    parser.add_argument("--output-candidate", type=Path, required=True)
    args = parser.parse_args(argv)
    bridge, candidate = build_bridge(
        quarterly_run_dir=args.quarterly_run_dir,
        announcement_artifact=args.announcement_artifact,
    )
    for path, payload in ((args.output_bridge, bridge), (args.output_candidate, candidate)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
