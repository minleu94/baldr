"""唯讀對照季報 CSV 與已封存的 MOPS 公告時間候選。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import stat
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


AUDIT_SCHEMA = "baldr.quarterly_announcement_crosswalk.v1"
MOPS_SCHEMA = "mops-ezsearch-statement-availability.v1"
MAX_CANDIDATE_ROOTS = 12
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CSV_BYTES = 16 * 1024 * 1024
MAX_QUERY_ROWS = 500
MAX_QUARTERLY_PROFILES = 200_000
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_REFERENCE_RE = re.compile(r"sha256:([0-9a-f]{64})\Z")
_TAIPEI = timezone(timedelta(hours=8))
_PERIOD_RE = re.compile(r"(?P<year>\d{3,4})-Q(?P<quarter>[1-4])\Z")
_STATEMENT_BY_ITEM = {
    "F26": "balance_sheet",
    "F27": "income_statement",
    "F28": "cash_flows_statement",
}
_MARKET_BY_MOPS = {"sii": "TWSE", "otc": "TPEx"}
_MOPS_CSV_FIELDS = (
    "stock_code",
    "statement_type",
    "period",
    "as_of_date",
    "announced_date",
    "available_date",
    "source",
    "source_version",
    "availability_contract_version",
    "evidence_class",
    "source_hash",
    "revision",
    "parent_revision",
)


class QuarterlyAnnouncementCrosswalkError(ValueError):
    """候選輸入不完整、身分不符或無法安全讀取。"""


def build_quarterly_announcement_crosswalk(
    *,
    quarterly_audit: Mapping[str, Any],
    announcement_candidate_roots: Sequence[Path],
) -> dict[str, Any]:
    """以市場、代碼、報表種類及季別對照公告候選，不判定數值版本或資格。"""

    _require_quarterly_boundary(quarterly_audit)
    roots = tuple(Path(root).expanduser().absolute() for root in announcement_candidate_roots)
    if not roots or len(roots) > MAX_CANDIDATE_ROOTS:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_root_count_invalid")

    bundles = tuple(_read_announcement_bundle(root) for root in roots)
    announcements: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    query_windows: dict[tuple[str, str], list[tuple[date, date]]] = defaultdict(list)
    query_errors: set[tuple[str, str]] = set()
    window_rows: list[dict[str, str]] = []
    for bundle in bundles:
        for query in bundle["query_manifest"]:
            market = _MARKET_BY_MOPS[query["market"]]
            statement = _STATEMENT_BY_ITEM[query["announcement_item"]]
            group = (market, statement)
            query_windows[group].append((query["start"], query["end"]))
            if query["source_status"] not in {"success", "fail"} or query["error_code"]:
                query_errors.add(group)
            window_rows.append(
                {
                    "market": market,
                    "statement_type": statement,
                    "start_date": query["start"].isoformat(),
                    "end_date": query["end"].isoformat(),
                    "source_status": query["source_status"],
                    "response_sha256": query["response_sha256"],
                }
            )
        for event in bundle["events"]:
            market = _MARKET_BY_MOPS[event["market"]]
            statement = _STATEMENT_BY_ITEM[event["announcement_item"]]
            key = (market, event["stock_code"], statement, event["period"])
            announcements[key].append(
                {
                    "announcement_at": event["announcement_at"],
                    "announced_date": event["announced_date"],
                    "available_date": event["available_date"],
                    "event_sha256": event["event_sha256"],
                    "source_sha256": event["source_sha256"],
                    "revision": event["revision"],
                }
            )

    complete_by_group = {
        group: _windows_are_contiguous(windows) and group not in query_errors
        for group, windows in query_windows.items()
    }
    all_window_dates = [value for windows in query_windows.values() for pair in windows for value in pair]
    window_start = min(all_window_dates).isoformat() if all_window_dates else None
    window_end = max(all_window_dates).isoformat() if all_window_dates else None

    resources = quarterly_audit.get("resources")
    if not isinstance(resources, list):
        raise QuarterlyAnnouncementCrosswalkError("quarterly_candidate_resources_invalid")
    crosswalk_resources: list[dict[str, Any]] = []
    totals: Counter[tuple[str, str, str]] = Counter()
    unique_timestamp_matches = 0
    ambiguous_version_matches = 0
    for resource in resources:
        if not isinstance(resource, Mapping):
            raise QuarterlyAnnouncementCrosswalkError("quarterly_candidate_resource_invalid")
        profiles = resource.get("row_profiles")
        state = resource.get("state")
        resource_market = resource.get("market")
        resource_statement = resource.get("statement")
        detail_rows: list[dict[str, Any]] = []
        counts: Counter[str] = Counter()
        profiles_complete = state == "available" and resource.get("row_profiles_complete") is True
        if not isinstance(profiles, list):
            profiles_complete = False
            profiles = []
        if sum(len(item["rows"]) for item in crosswalk_resources) + len(profiles) > MAX_QUARTERLY_PROFILES:
            raise QuarterlyAnnouncementCrosswalkError("quarterly_candidate_profile_limit_exceeded")
        for profile in profiles:
            if not isinstance(profile, Mapping):
                raise QuarterlyAnnouncementCrosswalkError("quarterly_candidate_profile_invalid")
            code = _normalized_code(profile.get("issuer_code"))
            period = _normalize_period(profile.get("fiscal_period"))
            if (
                code is None
                or period is None
                or resource_market not in {"TWSE", "TPEx"}
                or not isinstance(resource_statement, str)
            ):
                status = "identity_incomplete"
                matches: list[dict[str, str]] = []
            else:
                announcement_key = (
                    str(resource_market), code, resource_statement, period
                )
                matches = sorted(
                    announcements.get(announcement_key, []),
                    key=lambda item: (item["announced_date"], item["source_sha256"]),
                )
                if matches:
                    status = "one_announcement_candidate" if len(matches) == 1 else "multiple_announcement_candidates"
                    if len(matches) == 1:
                        unique_timestamp_matches += 1
                    else:
                        ambiguous_version_matches += 1
                elif complete_by_group.get(
                    (str(resource_market), resource_statement), False
                ):
                    status = "not_observed_in_selected_windows"
                else:
                    status = "query_window_incomplete"
            counts[status] += 1
            totals[(str(resource_market), str(resource_statement), status)] += 1
            detail_rows.append(
                {
                    "issuer_code": code,
                    "fiscal_period": period,
                    "status": status,
                    "announcement_timestamp_resolution": (
                        "unique_candidate_timestamp"
                        if status == "one_announcement_candidate"
                        else "ambiguous_candidate_versions"
                        if status == "multiple_announcement_candidates"
                        else "not_resolved"
                    ),
                    "announcement_count": len(matches),
                    "announcement_candidates": matches,
                }
            )
        crosswalk_resources.append(
            {
                "dataset_id": resource.get("dataset_id"),
                "market": resource_market,
                "statement": resource_statement,
                "industry": resource.get("industry"),
                "candidate_artifact_sha256": resource.get("sha256"),
                "row_profiles_complete": profiles_complete,
                "summary": dict(counts),
                "rows": detail_rows,
            }
        )

    summary_by_market_statement: dict[str, dict[str, Any]] = {}
    for (market, statement, status), count in sorted(totals.items()):
        summary_key = f"{market}|{statement}"
        item = summary_by_market_statement.setdefault(
            summary_key,
            {
                "market": market,
                "statement_type": statement,
                "one_announcement_candidate": 0,
                "multiple_announcement_candidates": 0,
                "not_observed_in_selected_windows": 0,
                "query_window_incomplete": 0,
                "identity_incomplete": 0,
                "profile_count": 0,
            },
        )
        item[status] = count
        item["profile_count"] += count

    required_groups = {
        (str(resource.get("market")), str(resource.get("statement")))
        for resource in resources
        if resource.get("market") in {"TWSE", "TPEx"}
        and resource.get("statement") in set(_STATEMENT_BY_ITEM.values())
    }
    windows_complete = bool(required_groups) and all(
        complete_by_group.get(group, False) for group in required_groups
    )
    is_complete = (
        bool(bundles)
        and windows_complete
        and all(item["row_profiles_complete"] for item in crosswalk_resources)
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "status": "available" if is_complete else "partial",
        "announcement_candidate_bundle_count": len(bundles),
        "announcement_candidate_bundles": [bundle["identity"] for bundle in bundles],
        "unique_announcement_timestamp_match_count": unique_timestamp_matches,
        "ambiguous_announcement_version_match_count": ambiguous_version_matches,
        "query_window_start": window_start,
        "query_window_end": window_end,
        "query_windows_complete_by_market_statement": {
            f"{market}|{statement}": complete
            for (market, statement), complete in sorted(complete_by_group.items())
        },
        "query_windows": sorted(
            window_rows,
            key=lambda item: (item["market"], item["statement_type"], item["start_date"]),
        ),
        "summary_by_market_statement": list(summary_by_market_statement.values()),
        "resources": crosswalk_resources,
        "limitations": [
            "對照只表示季報 CSV 與已選 MOPS 公告候選具有相同市場、公司代碼、報表種類及期別。",
            "公告候選不證明 CSV 數值版本、逐欄首次可得時間、修訂鏈、金額單位或報表基準。",
            "selected-window 未觀測不等於未申報；它只描述上列明選查詢窗口中的候選結果。",
            "MOPS EZSearch 的端點／用途授權仍須獨立核實；所有輸出維持 candidate-only，沒有 Gate credit。",
        ],
    }


def _read_announcement_bundle(root: Path) -> dict[str, Any]:
    try:
        root_stat = root.stat()
    except OSError as exc:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_root_unavailable") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_point(root):
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_root_not_directory")
    json_path = root / "mops-statement-availability.json"
    csv_path = root / "fundamental-statement-availability.csv"
    if _is_reparse_point(json_path) or _is_reparse_point(csv_path):
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_reparse_point")
    try:
        json_bytes = _read_bounded_file(json_path, MAX_JSON_BYTES)
        csv_bytes = _read_bounded_file(csv_path, MAX_CSV_BYTES)
        payload = json.loads(json_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, QuarterlyAnnouncementCrosswalkError) as exc:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_bundle_invalid") from exc
    _validate_mops_payload(payload)
    query_manifest = _validate_query_manifest(payload.get("query_manifest"))
    projections = _validate_projection(payload.get("availability_projection"), query_manifest)
    raw_events = _validate_raw_events(payload.get("rows"), query_manifest)
    _validate_raw_projection_links(raw_events, projections)
    try:
        payload_start = date.fromisoformat(str(payload.get("query_start_date")))
        payload_end = date.fromisoformat(str(payload.get("query_end_date")))
    except ValueError as exc:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_query_bounds_invalid") from exc
    if (
        not query_manifest
        or min(item["start"] for item in query_manifest) != payload_start
        or max(item["end"] for item in query_manifest) != payload_end
    ):
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_query_bounds_mismatch")
    csv_events = _parse_mops_csv(csv_bytes)
    if Counter(_projection_csv_tuple(item) for item in projections) != Counter(
        _event_tuple(item) for item in csv_events
    ):
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_csv_projection_mismatch")
    return {
        "query_manifest": query_manifest,
        "events": raw_events,
        "identity": {
            "candidate_name": root.name,
            "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
            "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "projection_row_count": len(projections),
            "raw_announcement_row_count": len(raw_events),
        },
    }


def _validate_mops_payload(payload: Any) -> None:
    expected = {
        "schema_version": MOPS_SCHEMA,
        "source_id": "mops.ezsearch.statement_publication",
        "source_version": "mops-ezsearch-statement-publication.v1",
        "research_only": True,
        "read_only_source": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "production_blend_alpha_bp": 0,
    }
    if not isinstance(payload, Mapping) or any(payload.get(key) != value for key, value in expected.items()):
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_boundary_invalid")


def _validate_query_manifest(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > MAX_QUERY_ROWS:
        raise QuarterlyAnnouncementCrosswalkError("announcement_query_manifest_invalid")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, date, date]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise QuarterlyAnnouncementCrosswalkError("announcement_query_row_invalid")
        market = item.get("market")
        announcement_item = item.get("announcement_item")
        status = item.get("source_status")
        row_count = item.get("row_count")
        error_code = item.get("error_code")
        sha = item.get("response_sha256")
        try:
            start = date.fromisoformat(str(item.get("query_start_date")))
            end = date.fromisoformat(str(item.get("query_end_date")))
        except ValueError as exc:
            raise QuarterlyAnnouncementCrosswalkError("announcement_query_date_invalid") from exc
        if (
            market not in _MARKET_BY_MOPS
            or announcement_item not in _STATEMENT_BY_ITEM
            or start > end
            or status not in {"success", "fail", "error"}
            or isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count < 0
            or (status == "fail" and row_count != 0)
            or not isinstance(error_code, str)
            or not isinstance(sha, str)
            or not _SHA256_RE.fullmatch(sha.lower())
        ):
            raise QuarterlyAnnouncementCrosswalkError("announcement_query_row_invalid")
        key = (str(market), str(announcement_item), start, end)
        if key in seen:
            raise QuarterlyAnnouncementCrosswalkError("announcement_query_window_duplicate")
        seen.add(key)
        result.append(
            {
                "market": market,
                "announcement_item": announcement_item,
                "start": start,
                "end": end,
                "source_status": status,
                "row_count": row_count,
                "error_code": error_code,
                "response_sha256": sha.lower(),
            }
        )
    return result


def _validate_projection(value: Any, queries: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise QuarterlyAnnouncementCrosswalkError("announcement_projection_invalid")
    query_by_sha: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for query in queries:
        query_by_sha[str(query["response_sha256"])].append(query)
    events: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise QuarterlyAnnouncementCrosswalkError("announcement_projection_row_invalid")
        source_hash = item.get("source_hash")
        if (
            not isinstance(source_hash, str)
            or not source_hash.startswith("sha256:")
            or not _SHA256_RE.fullmatch(source_hash[7:].lower())
        ):
            raise QuarterlyAnnouncementCrosswalkError("announcement_projection_hash_invalid")
        sha = source_hash[7:].lower()
        statement = item.get("statement_type")
        announced = _iso_date(item.get("announced_date"))
        matching_queries = [
            query
            for query in query_by_sha.get(sha, [])
            if statement == _STATEMENT_BY_ITEM[query["announcement_item"]]
            and announced is not None
            and query["start"] <= announced <= query["end"]
        ]
        if (
            len(matching_queries) != 1
            or item.get("source") != "mops.ezsearch.statement_publication"
            or item.get("source_version") != "mops-ezsearch-statement-publication.v1"
            or item.get("availability_contract_version") != "formal-availability.v2"
            or item.get("evidence_class") != "official_announcement"
        ):
            raise QuarterlyAnnouncementCrosswalkError("announcement_projection_provenance_invalid")
        query = matching_queries[0]
        code = _normalized_code(item.get("stock_code"))
        period = item.get("period")
        available = _iso_date(item.get("available_date"))
        revision = item.get("revision")
        if (
            code is None
            or not isinstance(period, str)
            or not re.fullmatch(r"\d{4}-Q[1-4]", period)
            or announced is None
            or available is None
            or available < announced
            or not isinstance(revision, str)
            or not revision.isdigit()
        ):
            raise QuarterlyAnnouncementCrosswalkError("announcement_projection_identity_invalid")
        as_of = _iso_date(item.get("as_of_date"))
        if as_of is None:
            raise QuarterlyAnnouncementCrosswalkError("announcement_projection_as_of_date_invalid")
        events.append(
            {
                "market": str(query["market"]),
                "announcement_item": str(query["announcement_item"]),
                "stock_code": code,
                "statement_type": str(statement),
                "period": period,
                "as_of_date": as_of.isoformat(),
                "announced_date": announced.isoformat(),
                "available_date": available.isoformat(),
                "source_sha256": sha,
                "revision": revision,
                "csv_source": "mops.ezsearch.statement_publication",
                "csv_source_version": "mops-ezsearch-statement-publication.v1",
                "availability_contract_version": "formal-availability.v2",
                "evidence_class": "official_announcement",
                "parent_revision": str(item.get("parent_revision") or ""),
            }
        )
    return events


def _validate_raw_events(
    value: Any,
    queries: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_QUERY_ROWS * 1000:
        raise QuarterlyAnnouncementCrosswalkError("announcement_raw_rows_invalid")
    query_by_sha: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for query in queries:
        query_by_sha[str(query["response_sha256"])].append(query)
    events: list[dict[str, str]] = []
    seen_event_hashes: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise QuarterlyAnnouncementCrosswalkError("announcement_raw_row_invalid")
        market = item.get("market")
        announcement_item = item.get("announcement_item")
        statement = item.get("statement_type")
        stock_code = _normalized_code(item.get("stock_code"))
        period = item.get("period")
        source_hash_match = _SHA256_REFERENCE_RE.fullmatch(
            str(item.get("source_hash") or "")
        )
        event_hash = item.get("event_hash")
        timestamp_text = item.get("announcement_at")
        if (
            market not in _MARKET_BY_MOPS
            or announcement_item not in _STATEMENT_BY_ITEM
            or statement != _STATEMENT_BY_ITEM[announcement_item]
            or stock_code is None
            or not isinstance(period, str)
            or _PERIOD_RE.fullmatch(period) is None
            or not isinstance(event_hash, str)
            or _SHA256_RE.fullmatch(event_hash.lower()) is None
            or event_hash.lower() in seen_event_hashes
            or source_hash_match is None
            or not isinstance(timestamp_text, str)
        ):
            raise QuarterlyAnnouncementCrosswalkError("announcement_raw_identity_invalid")
        try:
            timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QuarterlyAnnouncementCrosswalkError("announcement_raw_timestamp_invalid") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise QuarterlyAnnouncementCrosswalkError("announcement_raw_timestamp_timezone_missing")
        taipei_timestamp = timestamp.astimezone(_TAIPEI)
        response_sha = source_hash_match.group(1)
        matching_queries = [
            query
            for query in query_by_sha.get(response_sha, [])
            if query["market"] == market
            and query["announcement_item"] == announcement_item
            and query["start"] <= taipei_timestamp.date() <= query["end"]
        ]
        if len(matching_queries) != 1:
            raise QuarterlyAnnouncementCrosswalkError("announcement_raw_query_link_invalid")
        seen_event_hashes.add(event_hash.lower())
        events.append(
            {
                "market": str(market),
                "announcement_item": str(announcement_item),
                "stock_code": stock_code,
                "statement_type": str(statement),
                "period": period,
                "announced_date": taipei_timestamp.date().isoformat(),
                "announcement_at": taipei_timestamp.isoformat(),
                "event_sha256": event_hash.lower(),
                "source_sha256": response_sha,
                "revision": "1",
                "available_date": (taipei_timestamp.date() + timedelta(days=1)).isoformat(),
            }
        )
    return events


def _validate_raw_projection_links(
    raw_events: Sequence[Mapping[str, str]],
    projections: Sequence[Mapping[str, str]],
) -> None:
    raw_keys = {
        (
            item["market"],
            item["stock_code"],
            item["statement_type"],
            item["period"],
            item["announced_date"],
            item["source_sha256"],
        )
        for item in raw_events
    }
    if any(
        (
            item["market"],
            item["stock_code"],
            item["statement_type"],
            item["period"],
            item["announced_date"],
            item["source_sha256"],
        ) not in raw_keys
        for item in projections
    ):
        raise QuarterlyAnnouncementCrosswalkError("announcement_raw_projection_link_invalid")


def _parse_mops_csv(raw: bytes) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != _MOPS_CSV_FIELDS:
            raise QuarterlyAnnouncementCrosswalkError("announcement_csv_schema_invalid")
        rows: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise QuarterlyAnnouncementCrosswalkError("announcement_csv_row_invalid")
            rows.append({key: str(row[key]).strip() for key in _MOPS_CSV_FIELDS})
        return rows
    except (UnicodeDecodeError, csv.Error) as exc:
        raise QuarterlyAnnouncementCrosswalkError("announcement_csv_parse_invalid") from exc


def _event_tuple(item: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(item.get(key, "")).strip() for key in _MOPS_CSV_FIELDS)


def _projection_csv_tuple(item: Mapping[str, Any]) -> tuple[str, ...]:
    values = {
        "stock_code": item["stock_code"],
        "statement_type": item["statement_type"],
        "period": item["period"],
        "as_of_date": item["as_of_date"],
        "announced_date": item["announced_date"],
        "available_date": item["available_date"],
        "source": item["csv_source"],
        "source_version": item["csv_source_version"],
        "availability_contract_version": item["availability_contract_version"],
        "evidence_class": item["evidence_class"],
        "source_hash": f"sha256:{item['source_sha256']}",
        "revision": item["revision"],
        "parent_revision": item["parent_revision"],
    }
    return tuple(str(values[key]).strip() for key in _MOPS_CSV_FIELDS)


def _read_bounded_file(path: Path, maximum: int) -> bytes:
    if not path.is_file():
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_file_missing")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_file_size_invalid")
    raw = path.read_bytes()
    if len(raw) != size:
        raise QuarterlyAnnouncementCrosswalkError("announcement_candidate_file_readback_size_changed")
    return raw


def _windows_are_contiguous(windows: Sequence[tuple[date, date]]) -> bool:
    if not windows:
        return False
    ordered = sorted(windows)
    previous_end: date | None = None
    for start, end in ordered:
        if start > end or (previous_end is not None and start != date.fromordinal(previous_end.toordinal() + 1)):
            return False
        previous_end = end
    return True


def _require_quarterly_boundary(payload: Mapping[str, Any]) -> None:
    expected = {
        "schema_version": "baldr.open_data_quarterly_candidate_audit.v1",
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise QuarterlyAnnouncementCrosswalkError("quarterly_candidate_boundary_invalid")


def _normalize_period(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _PERIOD_RE.fullmatch(value.strip())
    if match is None:
        return None
    year = int(match.group("year"))
    if year < 1900:
        year += 1911
    if year < 1900 or year > 9999:
        return None
    return f"{year:04d}-Q{match.group('quarter')}"


def _normalized_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.isdigit() or not 4 <= len(text) <= 6:
        return None
    return text


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return path.is_symlink()
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
