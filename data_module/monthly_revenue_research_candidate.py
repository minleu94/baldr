"""Capture bounded, research-only monthly revenue candidates from official APIs."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
from zoneinfo import ZoneInfo

from data_module.monthly_revenue_availability_history import (
    OFFICIAL_OPENAPI_URLS,
    build_historical_monthly_revenue_availability,
    parse_announcement_date,
    parse_revenue_period,
)


REPO_ROOT = Path(__file__).absolute().parents[1]
RESEARCH_OUTPUT_ROOT = REPO_ROOT / "output" / "fundamental_research_candidates"
REQUEST_TIMEOUT_SECONDS = 30
MAX_VENUE_ENTITY_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_ENTITY_BYTES = 16 * 1024 * 1024
MINIMUM_FREE_SPACE_RESERVE_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_CANDIDATE_CSV_BYTES = 16 * 1024 * 1024
MAX_CANDIDATE_METADATA_BYTES = 1024 * 1024
FAILED_BODY_PREFIX_BYTES = 64 * 1024
_SOURCE_IDS = {
    "twse": "twse-openapi-t187ap05_L",
    "tpex": "tpex-openapi-mopsfin_t187ap05_O",
}
_TAIPEI_TZ = ZoneInfo("Asia/Taipei")
_SNAPSHOT_FIELDS = (
    "market",
    "period",
    "stock_code",
    "company_name",
    "current_month_revenue",
    "previous_month_revenue",
    "previous_year_month_revenue",
    "mom_pct",
    "yoy_pct",
    "cumulative_revenue",
    "previous_year_cumulative_revenue",
    "cumulative_yoy_pct",
    "note",
    "fetched_at",
    "source",
    "source_version",
)
_RAW_TO_SNAPSHOT_FIELDS = {
    "company_name": "公司名稱",
    "current_month_revenue": "營業收入-當月營收",
    "previous_month_revenue": "營業收入-上月營收",
    "previous_year_month_revenue": "營業收入-去年當月營收",
    "mom_pct": "營業收入-上月比較增減(%)",
    "yoy_pct": "營業收入-去年同月增減(%)",
    "cumulative_revenue": "累計營業收入-當月累計營收",
    "previous_year_cumulative_revenue": "累計營業收入-去年累計營收",
    "cumulative_yoy_pct": "累計營業收入-前期比較增減(%)",
    "note": "備註",
}
_AMOUNT_FIELDS = (
    "營業收入-當月營收",
    "營業收入-上月營收",
    "營業收入-去年當月營收",
    "累計營業收入-當月累計營收",
    "累計營業收入-去年累計營收",
)
_PERCENT_FIELDS = (
    "營業收入-上月比較增減(%)",
    "營業收入-去年同月增減(%)",
    "累計營業收入-前期比較增減(%)",
)
_REQUIRED_SOURCE_FIELDS = (
    "資料年月",
    "公司代號",
    "公司名稱",
    *_AMOUNT_FIELDS,
    *_PERCENT_FIELDS,
    "出表日期",
    "備註",
)
_AVAILABILITY_FIELDS = (
    "stock_code",
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

_OpenUrl = Callable[..., Any]
_DiskUsage = Callable[[str | os.PathLike[str]], Any]


def capture_monthly_revenue_research_candidate() -> dict[str, Any]:
    """Capture one full-market TWSE+TPEx snapshot under the repository output root."""

    return _capture_monthly_revenue_research_candidate(
        candidate_parent=RESEARCH_OUTPUT_ROOT,
        opener=urlopen,
        disk_usage=shutil.disk_usage,
    )


def _capture_monthly_revenue_research_candidate(
    *,
    candidate_parent: Path,
    opener: _OpenUrl,
    disk_usage: _DiskUsage,
) -> dict[str, Any]:
    repo_root = _absolute_without_link_components(REPO_ROOT)
    parent = _absolute_without_link_components(candidate_parent)
    try:
        parent.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("research candidate output must remain inside the repository") from exc
    existing_probe = parent
    while not existing_probe.exists():
        if existing_probe.parent == existing_probe:
            raise ValueError("research candidate output has no existing filesystem ancestor")
        existing_probe = existing_probe.parent
    free_bytes = int(disk_usage(existing_probe).free)
    required_free_bytes = MAX_AGGREGATE_ENTITY_BYTES + MINIMUM_FREE_SPACE_RESERVE_BYTES
    if free_bytes < required_free_bytes:
        return {
            "status": "rejected",
            "reason": "research_candidate_free_space_below_reserve",
            "free_bytes": free_bytes,
            "required_free_bytes": required_free_bytes,
            "source_requests_made": 0,
            "writes_formal_data": False,
            "writes_formal_database": False,
            "formal_apply_authorized": False,
        }

    parent.mkdir(parents=True, exist_ok=True)
    _absolute_without_link_components(parent)
    started_at = datetime.now(timezone.utc)
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex}"
    run_root = parent / run_id
    run_root.mkdir(exist_ok=False)
    source_root = run_root / "source"
    source_root.mkdir(exist_ok=False)
    output_bytes_written = 0

    def write_candidate_file(path: Path, data: bytes) -> None:
        nonlocal output_bytes_written
        output_bytes_written += _write_create_only(
            path,
            data,
            allowed_root=run_root,
            disk_usage=disk_usage,
            max_file_bytes=_candidate_file_limit(path),
            reserve_bytes=MINIMUM_FREE_SPACE_RESERVE_BYTES,
            prior_output_bytes=output_bytes_written,
        )

    source_results: dict[str, dict[str, Any]] = {}
    source_rows: dict[str, list[dict[str, Any]]] = {}
    persisted_entity_bytes = 0
    consumed_entity_bytes = 0
    for venue in ("twse", "tpex"):
        request_url = OFFICIAL_OPENAPI_URLS[venue]
        entity_read_limit = min(
            MAX_VENUE_ENTITY_BYTES + 1,
            max(1, MAX_AGGREGATE_ENTITY_BYTES - consumed_entity_bytes + 1),
        )
        result, raw_rows, entity_bytes = _fetch_venue(
            venue=venue,
            request_url=request_url,
            opener=opener,
            entity_read_limit=entity_read_limit,
        )
        source_results[venue] = result
        consumed_entity_bytes += int(result.get("body_bytes_read") or 0)
        persisted_entity_bytes += len(entity_bytes or b"")
        if entity_bytes is not None:
            raw_name = f"{venue}.json" if result.get("body_capture_scope") == "full" else f"{venue}.failed-prefix.bin"
            relative_raw_path = f"source/{raw_name}"
            write_candidate_file(run_root / relative_raw_path, entity_bytes)
            result["saved_path"] = relative_raw_path
            result["saved_sha256"] = hashlib.sha256(entity_bytes).hexdigest()
        if raw_rows is not None:
            source_rows[venue] = raw_rows

    capture_status = "captured" if all(
        result.get("status") == "captured" for result in source_results.values()
    ) else "failed"
    period: str | None = None
    diagnostics: list[str] = []
    snapshot_rows: list[dict[str, str]] = []
    availability_rows: list[dict[str, str]] = []
    scope_manifest: dict[str, Any] | None = None
    candidate_manifest: dict[str, Any] | None = None
    capture_manifest: dict[str, Any] = {
        "schema_version": "monthly-revenue-openapi-capture.v1",
        "status": capture_status,
        "requested_period": None,
        "capture_scope": "daily_current_full_market_research_snapshot",
        "started_at_utc": started_at.isoformat(),
        "results": source_results,
    }

    if capture_status == "captured":
        try:
            snapshot_rows, period, numeric_qa = _build_snapshot_rows(
                source_rows=source_rows,
                source_results=source_results,
            )
            raw_periods = {
                (row["stock_code"], row["period"]) for row in snapshot_rows
            }
            latest_source_capture = max(
                datetime.fromisoformat(str(item["observed_at_utc"]).replace("Z", "+00:00"))
                for item in source_results.values()
            )
            latest_source_capture_utc = latest_source_capture.astimezone(timezone.utc)
            capture_date_taipei = latest_source_capture_utc.astimezone(_TAIPEI_TZ).date()
            date_only_available_date = capture_date_taipei + timedelta(days=1)
            for venue in ("twse", "tpex"):
                for raw_row in source_rows[venue]:
                    announced = parse_announcement_date(str(raw_row["出表日期"]).strip())
                    if announced > capture_date_taipei:
                        raise ValueError(
                            f"{venue} API row announcement date is after source capture: "
                            f"{raw_row.get('公司代號')}:{announced.isoformat()}"
                        )
            for venue in ("twse", "tpex"):
                for raw_row in source_rows[venue]:
                    raw_row["__availability_source"] = (
                        "twse.monthly_revenue_announcement"
                        if venue == "twse"
                        else "tpex.monthly_revenue_announcement"
                    )
                    raw_row["__source_version"] = source_results[venue]["source_version"]
            availability_result = build_historical_monthly_revenue_availability(
                official_rows_by_market=source_rows,
                raw_periods=raw_periods,
                start_period=period,
                end_period=period,
                markets=("twse", "tpex"),
                fetch_date=capture_date_taipei,
                snapshot_captured_at=latest_source_capture_utc.isoformat(),
            )
            if (
                availability_result.diagnostics
                or availability_result.duplicate_mapping_rows
                or availability_result.missing_availability_count
                or len(availability_result.rows) != len(snapshot_rows)
            ):
                diagnostics.extend(
                    str(item.message) for item in availability_result.diagnostics
                )
                diagnostics.append(
                    "availability coverage is incomplete or contains duplicate mappings"
                )
                raise ValueError("availability candidate did not cover every source key")
            availability_rows = [dict(row) for row in availability_result.rows]
            capture_manifest["requested_period"] = period
            capture_manifest["captured_at_utc"] = latest_source_capture_utc.isoformat()
            capture_manifest["source_row_count"] = len(snapshot_rows)
            capture_manifest["availability_row_count"] = len(availability_rows)
            capture_manifest["numeric_qa"] = numeric_qa
            capture_manifest["availability_policy"] = {
                "date_only_rule": "Taipei source capture date plus one calendar day",
                "source_observed_at_utc": latest_source_capture_utc.isoformat(),
                "source_capture_date_taipei": capture_date_taipei.isoformat(),
                "snapshot_capture_available_date": date_only_available_date.isoformat(),
                "not_formal_acceptance": True,
            }
            for venue in ("twse", "tpex"):
                source_results[venue]["source_version"] = (
                    f"{_SOURCE_IDS[venue]}-{_roc_period(period)}-sha256-"
                    f"{source_results[venue]['content_sha256']}"
                )
            for snapshot_row in snapshot_rows:
                venue = snapshot_row["market"]
                snapshot_row["fetched_at"] = str(
                    source_results[venue]["observed_at_utc"]
                )
                snapshot_row["source_version"] = str(
                    source_results[venue]["source_version"]
                )

            capture_manifest_bytes = _json_bytes(capture_manifest)
            write_candidate_file(source_root / "capture_run.json", capture_manifest_bytes)
            snapshot_bytes = _csv_bytes(snapshot_rows, _SNAPSHOT_FIELDS)
            availability_bytes = _csv_bytes(availability_rows, _AVAILABILITY_FIELDS)
            snapshot_file_name = f"twse_tpex_monthly_revenue_{period.replace('-', '')}_full.csv"
            availability_file_name = f"availability_capture_bound_{period.replace('-', '')}_full.csv"
            write_candidate_file(run_root / snapshot_file_name, snapshot_bytes)
            write_candidate_file(run_root / availability_file_name, availability_bytes)

            snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
            availability_sha256 = hashlib.sha256(availability_bytes).hexdigest()
            candidate_key_set = {
                f"{row['stock_code']}|{row['period']}" for row in snapshot_rows
            }
            scope_manifest = _build_scope_manifest(
                period=period,
                source_results=source_results,
                capture_manifest_bytes=capture_manifest_bytes,
                snapshot_file_name=snapshot_file_name,
                snapshot_sha256=snapshot_sha256,
                candidate_key_set=candidate_key_set,
                candidate_created_at_utc=datetime.now(timezone.utc),
            )
            scope_manifest_bytes = _json_bytes(scope_manifest)
            write_candidate_file(run_root / "full_source_scope_manifest.json", scope_manifest_bytes)

            readback = _verify_readback(
                run_root=run_root,
                snapshot_file_name=snapshot_file_name,
                availability_file_name=availability_file_name,
                snapshot_bytes=snapshot_bytes,
                availability_bytes=availability_bytes,
                capture_manifest_bytes=capture_manifest_bytes,
                scope_manifest_bytes=scope_manifest_bytes,
                source_results=source_results,
                expected_rows=len(snapshot_rows),
                expected_availability_rows=len(availability_rows),
            )
            candidate_manifest_payload = {
                "schema_version": "monthly-revenue-research-candidate.v1",
                "status": "research_only_candidate_created",
                "run_id": run_id,
                "candidate_period": period,
                "candidate_file": snapshot_file_name,
                "candidate_file_sha256": snapshot_sha256,
                "availability_file": availability_file_name,
                "availability_file_sha256": availability_sha256,
                "scope_manifest_file": "full_source_scope_manifest.json",
                "scope_manifest_sha256": hashlib.sha256(scope_manifest_bytes).hexdigest(),
                "source_row_count": len(snapshot_rows),
                "availability_row_count": len(availability_rows),
                "venue_row_counts": {
                    venue: len(source_rows[venue]) for venue in ("twse", "tpex")
                },
                "numeric_qa": numeric_qa,
                "units": {
                    "source_api_unit_explicit": False,
                    "formal_unit_contract_accepted": False,
                    "source_fields_preserved_without_conversion": True,
                },
                "owner_acceptance": False,
                "formal_apply_authorized": False,
                "historical_pit_credit": False,
                "candidate_completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "readback": readback,
                "writes_formal_data": False,
                "writes_formal_database": False,
                "auto_apply": False,
            }
            candidate_manifest_bytes = _json_bytes(candidate_manifest_payload)
            candidate_manifest_path = run_root / "candidate_manifest.json"
            write_candidate_file(candidate_manifest_path, candidate_manifest_bytes)
            if _read_bounded(candidate_manifest_path, MAX_AGGREGATE_ENTITY_BYTES) != candidate_manifest_bytes:
                raise ValueError("candidate manifest readback bytes differ")
            candidate_manifest = candidate_manifest_payload
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, InvalidOperation) as exc:
            diagnostics.append(f"{type(exc).__name__}: {exc}")
            capture_manifest["status"] = "captured" if capture_status == "captured" else "failed"
            if not (source_root / "capture_run.json").exists():
                write_candidate_file(source_root / "capture_run.json", _json_bytes(capture_manifest))

    if not (source_root / "capture_run.json").exists():
        write_candidate_file(source_root / "capture_run.json", _json_bytes(capture_manifest))

    status = (
        "captured"
        if candidate_manifest is not None
        else "rejected" if capture_status == "captured" else "failed"
    )
    status_payload = {
        "schema_version": "monthly-revenue-research-candidate-status.v1",
        "status": status,
        "run_id": run_id,
        "run_root": str(run_root),
        "candidate_period": period,
        "source_requests_made": len(source_results),
        "source_entity_bytes_saved": persisted_entity_bytes,
        "source_results": source_results,
        "diagnostics": diagnostics,
        "candidate_manifest_file": (
            "candidate_manifest.json" if candidate_manifest is not None else None
        ),
        "candidate_manifest_sha256": (
            hashlib.sha256(_json_bytes(candidate_manifest)).hexdigest()
            if candidate_manifest is not None
            else None
        ),
        "writes_formal_data": False,
        "writes_formal_database": False,
        "formal_apply_authorized": False,
    }
    write_candidate_file(run_root / "status.json", _json_bytes(status_payload))
    return status_payload


def _fetch_venue(
    *,
    venue: str,
    request_url: str,
    opener: _OpenUrl,
    entity_read_limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None, bytes | None]:
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "BaldrMonthlyRevenueResearchCandidate/1.0",
        },
        method="GET",
    )
    try:
        response = opener(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except HTTPError as exc:
        body, too_large, read_error = _read_limited_entity(
            exc,
            min(FAILED_BODY_PREFIX_BYTES + 1, entity_read_limit),
        )
        completion = datetime.now(timezone.utc)
        headers = _safe_response_headers(exc.headers)
        http_error_result = {
            "status": "failed",
            "requested_url": request_url,
            "final_url": exc.geturl(),
            "http_status": int(exc.code),
            "response_headers": headers,
            "observed_at_utc": completion.isoformat(),
            "body_capture_scope": (
                "prefix_65536_bytes"
                if too_large or len(body) > FAILED_BODY_PREFIX_BYTES
                else _body_scope(len(body), FAILED_BODY_PREFIX_BYTES, body)
            ),
            "body_bytes_read": len(body),
            "content_length_header": headers.get("content-length"),
            "error_type": "HTTPError",
            "error": f"official source returned HTTP {exc.code}",
            "read_error": read_error,
        }
        return http_error_result, None, body or None
    except Exception as exc:  # noqa: BLE001 - preserve bounded network failure detail
        completion = datetime.now(timezone.utc)
        return (
            {
                "status": "failed",
                "requested_url": request_url,
                "final_url": None,
                "http_status": None,
                "response_headers": {},
                "observed_at_utc": completion.isoformat(),
                "body_capture_scope": "no_response_body",
                "body_bytes_read": 0,
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
            },
            None,
            None,
        )

    with response:
        http_status = int(getattr(response, "status", 0) or 0)
        final_url = str(response.geturl())
        headers = _safe_response_headers(getattr(response, "headers", {}))
        body, too_large, read_error = _read_limited_entity(
            response,
            entity_read_limit,
        )
    completion = datetime.now(timezone.utc)
    if too_large or len(body) > MAX_VENUE_ENTITY_BYTES:
        prefix = body[:FAILED_BODY_PREFIX_BYTES]
        return (
            {
                "status": "failed",
                "requested_url": request_url,
                "final_url": final_url,
                "http_status": http_status,
                "response_headers": headers,
                "observed_at_utc": completion.isoformat(),
                "body_capture_scope": "prefix_65536_bytes",
                "body_bytes_read": len(body),
                "content_length_header": headers.get("content-length"),
                "entity_limit_bytes": MAX_VENUE_ENTITY_BYTES,
                "error_type": "EntityTooLarge",
                "error": "official source entity exceeded the per-venue byte limit",
                "read_error": read_error,
                "persisted_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
                "persisted_prefix_bytes": len(prefix),
            },
            None,
            prefix,
        )

    entity_hash = hashlib.sha256(body).hexdigest()
    result: dict[str, Any] = {
        "status": "failed",
        "requested_url": request_url,
        "final_url": final_url,
        "http_status": http_status,
        "response_headers": headers,
        "observed_at_utc": completion.isoformat(),
        "body_capture_scope": "full",
        "body_bytes_read": len(body),
        "content_bytes": len(body),
        "content_sha256": entity_hash,
        "content_encoding": headers.get("content-encoding", "identity"),
    }
    if read_error:
        prefix = body[:FAILED_BODY_PREFIX_BYTES]
        result.update(
            {
                "error_type": "ResponseReadError",
                "error": read_error,
                "body_capture_scope": "prefix_65536_bytes",
                "content_sha256": None,
                "content_bytes": None,
                "persisted_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
                "persisted_prefix_bytes": len(prefix),
            }
        )
        return result, None, prefix
    if http_status != 200 or final_url != request_url:
        result.update(
            {
                "error_type": "UnexpectedHttpResponse",
                "error": "official source did not return HTTP 200 at its pinned URL",
            }
        )
        return result, None, body
    try:
        decoded = _decode_entity(body, str(result["content_encoding"]))
        raw_rows = json.loads(decoded.decode("utf-8-sig"))
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError("official response JSON must be a non-empty row array")
        if any(not isinstance(row, Mapping) for row in raw_rows):
            raise ValueError("official response JSON rows must be objects")
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result.update(
            {
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "decoded_body_sha256": None,
            }
        )
        return result, None, body

    result.update(
        {
            "status": "captured",
            "json_row_count": len(raw_rows),
            "period_values_sample": sorted(
                {str(row.get("資料年月") or "").strip() for row in raw_rows}
            )[:10],
            "final_url": final_url,
        }
    )
    return result, [dict(row) for row in raw_rows], body


def _build_snapshot_rows(
    *,
    source_rows: Mapping[str, list[dict[str, Any]]],
    source_results: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    periods: set[str] = set()
    raw_rows_by_venue: dict[str, dict[str, dict[str, Any]]] = {}
    all_keys: set[tuple[str, str]] = set()
    numeric_qa: dict[str, Any] = {
        "amount_fields": {},
        "percentage_fields": {},
        "blank_percentage_cells": 0,
        "invalid_or_nonfinite_cells": 0,
        "source_unit_conversion": "none",
    }
    for field in _AMOUNT_FIELDS:
        numeric_qa["amount_fields"][field] = {"finite_decimal_count": 0}
    for field in _PERCENT_FIELDS:
        numeric_qa["percentage_fields"][field] = {
            "finite_decimal_count": 0,
            "blank_count": 0,
        }

    for venue in ("twse", "tpex"):
        venue_rows: dict[str, dict[str, Any]] = {}
        for raw_row_value in source_rows[venue]:
            raw_row = dict(raw_row_value)
            missing = [field for field in _REQUIRED_SOURCE_FIELDS if field not in raw_row]
            if missing:
                raise ValueError(f"{venue} API row misses required fields: {','.join(missing)}")
            if any(not isinstance(raw_row[field], str) for field in _REQUIRED_SOURCE_FIELDS):
                raise ValueError(f"{venue} API row contains non-text source fields")
            normalized = {field: raw_row[field].strip() for field in _REQUIRED_SOURCE_FIELDS}
            if not re.fullmatch(r"\d{5}", normalized["資料年月"]):
                raise ValueError(f"{venue} API row has an unsupported period shape")
            period = parse_revenue_period(normalized["資料年月"])
            periods.add(period)
            stock_code = normalized["公司代號"]
            if not re.fullmatch(r"\d{4,6}", stock_code):
                raise ValueError(f"{venue} API row has an invalid stock code")
            if not normalized["公司名稱"]:
                raise ValueError(f"{venue} API row has no company name")
            parse_announcement_date(normalized["出表日期"])
            if stock_code in venue_rows or (stock_code, period) in all_keys:
                raise ValueError(f"duplicate monthly revenue source key: {stock_code}|{period}")
            for field in _AMOUNT_FIELDS:
                _require_finite_decimal(normalized[field], venue, stock_code, field)
                numeric_qa["amount_fields"][field]["finite_decimal_count"] += 1
            for field in _PERCENT_FIELDS:
                value = normalized[field]
                if not value:
                    numeric_qa["percentage_fields"][field]["blank_count"] += 1
                    numeric_qa["blank_percentage_cells"] += 1
                    continue
                _require_finite_decimal(value, venue, stock_code, field)
                numeric_qa["percentage_fields"][field]["finite_decimal_count"] += 1
            venue_rows[stock_code] = raw_row
            all_keys.add((stock_code, period))
        if not venue_rows:
            raise ValueError(f"{venue} official API returned no validated source rows")
        raw_rows_by_venue[venue] = venue_rows

    if len(periods) != 1:
        raise ValueError("TWSE and TPEx source rows do not share exactly one period")
    period = next(iter(periods))
    snapshot: list[dict[str, str]] = []
    for venue in ("twse", "tpex"):
        result = source_results[venue]
        raw_hash = str(result["content_sha256"])
        source_version = (
            f"{_SOURCE_IDS[venue]}-{_roc_period(period)}-sha256-{raw_hash}"
        )
        result["source_version"] = source_version
        expected_period_count = sum(
            1
            for row in source_rows[venue]
            if parse_revenue_period(str(row["資料年月"]).strip()) == period
        )
        result["rows_for_period"] = expected_period_count
        result[f"rows_for_{period.replace('-', '_')}"] = expected_period_count
        for stock_code, raw_row in sorted(raw_rows_by_venue[venue].items()):
            normalized = {key: str(value).strip() for key, value in raw_row.items()}
            row = {
                "market": venue,
                "period": period,
                "stock_code": stock_code,
                "fetched_at": str(result["observed_at_utc"]),
                "source": (
                    "twse.open_api.monthly_revenue"
                    if venue == "twse"
                    else "tpex.open_api.monthly_revenue"
                ),
                "source_version": source_version,
            }
            row.update(
                {
                    target: normalized[source]
                    for target, source in _RAW_TO_SNAPSHOT_FIELDS.items()
                }
            )
            snapshot.append(row)
    return snapshot, period, numeric_qa


def _require_finite_decimal(value: str, venue: str, stock_code: str, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid Decimal source field: {venue}:{stock_code}:{field}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite Decimal source field: {venue}:{stock_code}:{field}")
    return result


def _build_scope_manifest(
    *,
    period: str,
    source_results: Mapping[str, Mapping[str, Any]],
    capture_manifest_bytes: bytes,
    snapshot_file_name: str,
    snapshot_sha256: str,
    candidate_key_set: set[str],
    candidate_created_at_utc: datetime,
) -> dict[str, Any]:
    venue_contracts: dict[str, dict[str, Any]] = {}
    for venue in ("twse", "tpex"):
        result = source_results[venue]
        venue_contracts[venue] = {
            "source": (
                "twse.open_api.monthly_revenue"
                if venue == "twse"
                else "tpex.open_api.monthly_revenue"
            ),
            "source_id": _SOURCE_IDS[venue],
            "raw_file": str(result["saved_path"]),
            "raw_sha256": str(result["content_sha256"]),
            "raw_bytes": int(result["content_bytes"]),
            "row_count": int(result["json_row_count"]),
            "captured_at_utc": str(result["observed_at_utc"]),
            "source_version": str(result["source_version"]),
        }
    snapshot_contract_available_at = datetime.now(timezone.utc)
    return {
        "schema_version": "monthly-revenue-full-official-research-scope.v1",
        "candidate_rows": len(candidate_key_set),
        "mapping_rows": len(candidate_key_set),
        "accepted_rows": len(candidate_key_set),
        "excluded_rows": 0,
        "excluded_keys": [],
        "candidate_file": snapshot_file_name,
        "candidate_file_sha256": snapshot_sha256,
        "accepted_file_sha256": snapshot_sha256,
        "candidate_key_sha256": _key_digest(candidate_key_set),
        "accepted_key_sha256": _key_digest(candidate_key_set),
        "excluded_key_sha256": _key_digest(set()),
        "source_scope": {
            "period": period,
            "twse_row_count": int(source_results["twse"]["json_row_count"]),
            "tpex_row_count": int(source_results["tpex"]["json_row_count"]),
        },
        "source_contract": {
            "schema_version": "monthly-revenue-source-contract.v1",
            "contract_id": "official_twse_tpex_openapi_monthly_revenue.v1",
            "composite_source": "twse_tpex.open_api.monthly_revenue_snapshot",
            "candidate_period": period,
            "candidate_available_at_utc": snapshot_contract_available_at.isoformat(),
            "capture_manifest_file": "source/capture_run.json",
            "capture_manifest_sha256": hashlib.sha256(capture_manifest_bytes).hexdigest(),
            "venues": venue_contracts,
        },
        "owner_acceptance": False,
        "formal_apply_authorized": False,
        "historical_pit_credit": False,
        "candidate_created_at_utc": candidate_created_at_utc.isoformat(),
    }


def _verify_readback(
    *,
    run_root: Path,
    snapshot_file_name: str,
    availability_file_name: str,
    snapshot_bytes: bytes,
    availability_bytes: bytes,
    capture_manifest_bytes: bytes,
    scope_manifest_bytes: bytes,
    source_results: Mapping[str, Mapping[str, Any]],
    expected_rows: int,
    expected_availability_rows: int,
) -> dict[str, Any]:
    readback_files: dict[str, Any] = {}
    for relative_path, expected_bytes in (
        (snapshot_file_name, snapshot_bytes),
        (availability_file_name, availability_bytes),
        ("source/capture_run.json", capture_manifest_bytes),
        ("full_source_scope_manifest.json", scope_manifest_bytes),
    ):
        actual = _read_bounded(run_root / relative_path, MAX_AGGREGATE_ENTITY_BYTES)
        if hashlib.sha256(actual).digest() != hashlib.sha256(expected_bytes).digest():
            raise ValueError(f"readback hash mismatch: {relative_path}")
        readback_files[relative_path] = {
            "bytes": len(actual),
            "sha256": hashlib.sha256(actual).hexdigest(),
        }
    for venue in ("twse", "tpex"):
        raw_path = run_root / str(source_results[venue]["saved_path"])
        raw_bytes = _read_bounded(raw_path, MAX_VENUE_ENTITY_BYTES)
        if hashlib.sha256(raw_bytes).hexdigest() != source_results[venue]["content_sha256"]:
            raise ValueError(f"source raw readback hash mismatch: {venue}")
        readback_files[str(source_results[venue]["saved_path"])] = {
            "bytes": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }
    snapshot_readback = _read_bounded(run_root / snapshot_file_name, MAX_AGGREGATE_ENTITY_BYTES)
    availability_readback = _read_bounded(run_root / availability_file_name, MAX_AGGREGATE_ENTITY_BYTES)
    snapshot_rows = list(csv.DictReader(io.StringIO(snapshot_readback.decode("utf-8-sig"))))
    availability_rows = list(
        csv.DictReader(io.StringIO(availability_readback.decode("utf-8-sig")))
    )
    if len(snapshot_rows) != expected_rows or len(availability_rows) != expected_availability_rows:
        raise ValueError("candidate CSV readback row count differs from in-memory result")
    if {f"{row['stock_code']}|{row['period']}" for row in snapshot_rows} != {
        f"{row['stock_code']}|{row['period']}" for row in availability_rows
    }:
        raise ValueError("candidate snapshot and availability readback keys differ")
    return {
        "status": "verified",
        "files": readback_files,
        "snapshot_rows": len(snapshot_rows),
        "availability_rows": len(availability_rows),
    }


def _read_limited_entity(
    response: Any,
    limit_bytes: int,
) -> tuple[bytes, bool, str | None]:
    chunks: list[bytes] = []
    remaining = max(0, limit_bytes)
    too_large = False
    read_error: str | None = None
    while remaining > 0:
        try:
            chunk = response.read(min(64 * 1024, remaining))
        except Exception as exc:  # noqa: BLE001 - retain bytes already received
            read_error = f"{type(exc).__name__}: {exc}"[:1000]
            break
        if not chunk:
            break
        chunks.append(bytes(chunk))
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) >= limit_bytes and limit_bytes > 0:
        too_large = True
    return body, too_large, read_error


def _decode_entity(raw: bytes, content_encoding: str) -> bytes:
    encoding = content_encoding.strip().lower() or "identity"
    if encoding not in {"identity", "none"}:
        raise ValueError(f"unsupported Content-Encoding: {encoding}")
    if len(raw) > MAX_VENUE_ENTITY_BYTES:
        raise ValueError("official JSON exceeded the per-venue byte limit")
    return raw


def _safe_response_headers(headers: Any) -> dict[str, str]:
    allowed = {
        "cache-control",
        "content-encoding",
        "content-length",
        "content-type",
        "date",
        "etag",
        "expires",
        "last-modified",
    }
    try:
        return {
            str(key).lower(): str(value)
            for key, value in headers.items()
            if str(key).lower() in allowed
        }
    except (AttributeError, TypeError):
        return {}


def _body_scope(length: int, limit: int, body: bytes) -> str:
    if not body:
        return "no_response_body"
    if length >= limit:
        return f"prefix_{limit}_bytes"
    return "full"


def _roc_period(period: str) -> str:
    year_text, month_text = period.split("-", maxsplit=1)
    return f"{int(year_text) - 1911:03d}{int(month_text):02d}"


def _key_digest(keys: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()


def _csv_bytes(rows: list[dict[str, str]], fieldnames: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _candidate_file_limit(path: Path) -> int:
    if path.name.endswith(".failed-prefix.bin"):
        return FAILED_BODY_PREFIX_BYTES
    if path.name in {"twse.json", "tpex.json"}:
        return MAX_VENUE_ENTITY_BYTES
    if path.name == "capture_run.json":
        return MAX_CANDIDATE_METADATA_BYTES
    if path.suffix.lower() == ".json":
        return MAX_CANDIDATE_METADATA_BYTES
    if path.suffix.lower() == ".csv":
        return MAX_CANDIDATE_CSV_BYTES
    return MAX_CANDIDATE_METADATA_BYTES


def _write_create_only(
    path: Path,
    data: bytes,
    *,
    allowed_root: Path,
    disk_usage: _DiskUsage,
    max_file_bytes: int,
    reserve_bytes: int,
    prior_output_bytes: int,
) -> int:
    root = _absolute_without_link_components(allowed_root)
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("research candidate output escaped its run root") from exc
    _absolute_without_link_components(target.parent)
    if not data or len(data) > max_file_bytes:
        raise ValueError(
            f"research candidate output exceeds its per-file limit: {target.name}"
        )
    if prior_output_bytes + len(data) > MAX_CANDIDATE_OUTPUT_BYTES:
        raise ValueError("research candidate output exceeds the total output limit")

    target.parent.mkdir(parents=True, exist_ok=True)
    target = _absolute_without_link_components(target)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("research candidate output escaped its run root") from exc
    _absolute_without_link_components(target.parent)
    free_bytes = int(disk_usage(target.parent).free)
    required_bytes = len(data) + reserve_bytes
    if free_bytes < required_bytes:
        raise OSError(
            "research candidate write would consume the minimum free-space reserve; "
            f"path={target.name}; free_bytes={free_bytes}; required_bytes={required_bytes}"
        )

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(os.fspath(target), flags, 0o600)
    try:
        with os.fdopen(file_descriptor, "wb", closefd=False) as handle:
            written = handle.write(data)
            if written != len(data):
                raise OSError("research candidate output write was incomplete")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(file_descriptor)
    return len(data)


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    file_stat = path.lstat()
    is_junction = getattr(path, "is_junction", None)
    if (
        path.is_symlink()
        or (callable(is_junction) and is_junction())
        or not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_nlink != 1
        or file_stat.st_size <= 0
        or file_stat.st_size > max_bytes
    ):
        raise ValueError(f"candidate readback file is not a bounded single-link file: {path}")
    with path.open("rb") as handle:
        before_stat = os.fstat(handle.fileno())
        data = handle.read(max_bytes + 1)
        after_stat = os.fstat(handle.fileno())
    after_path_stat = path.lstat()
    if (
        len(data) > max_bytes
        or len(data) != before_stat.st_size
        or _file_fingerprint(before_stat) != _file_fingerprint(after_stat)
        or _file_fingerprint(before_stat) != _file_fingerprint(after_path_stat)
    ):
        raise ValueError(f"candidate readback changed while it was read: {path}")
    return data


def _file_fingerprint(file_stat: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
        file_stat.st_nlink,
    )


def _absolute_without_link_components(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ValueError(f"research candidate path has a linked component: {current}")
    return absolute
