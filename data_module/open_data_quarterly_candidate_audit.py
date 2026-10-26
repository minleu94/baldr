"""離線稽核 Open Data 季報候選 CSV；不下載、不寫入、不授予來源資格。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, TypedDict


MANIFEST_NAME = "capture_manifest.json"
INDUSTRY_MANIFEST_SCHEMA = "baldr.open_data_industry_quarterly_candidate.v1"
GENERAL_MANIFEST_SCHEMA = "baldr.open_data_csv_candidate.v1"
# 舊名稱保留為明確的產業 manifest 版本，方便呼叫端固定 schema。
MANIFEST_SCHEMA = INDUSTRY_MANIFEST_SCHEMA
SUPPORTED_MANIFEST_SCHEMAS = frozenset(
    {INDUSTRY_MANIFEST_SCHEMA, GENERAL_MANIFEST_SCHEMA}
)
AUDIT_SCHEMA = "baldr.open_data_quarterly_candidate_audit.v1"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RESOURCE_BYTES = 32 * 1024 * 1024
MAX_ROW_PROFILES_PER_RESOURCE = 5_000
KNOWN_PLACEHOLDERS = ("-", "--", "N/A", "NA", "null", "NULL")

_IDENTITY_AND_DATE_HEADERS = frozenset(
    {
        "出表日期",
        "年度",
        "季別",
        "公司代號",
        "公司名稱",
        "output_date",
        "report_date",
        "year",
        "fiscal_year",
        "quarter",
        "fiscal_quarter",
        "company_code",
        "issuer_code",
        "issuer_id",
        "stock_code",
        "security_code",
        "company_name",
    }
)
_ISSUER_HEADERS = (
    "公司代號",
    "證券代號",
    "stock_code",
    "issuer_code",
    "company_code",
    "issuer_id",
)
_YEAR_HEADERS = ("年度", "year", "fiscal_year")
_QUARTER_HEADERS = ("季別", "quarter", "fiscal_quarter")
_OUTPUT_DATE_HEADERS = ("出表日期", "output_date", "report_date")
_COMPANY_NAME_HEADERS = ("公司名稱", "company_name")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class QuarterlyCandidateAuditError(ValueError):
    """候選根目錄或 manifest 不足以建立可信的隔離稽核。"""


class QuarterlyResourceMetadata(TypedDict):
    dataset_id: str
    market: str
    statement: str
    industry: str


@dataclass(frozen=True)
class QuarterlyFieldCounts:
    field_name: str
    blank_count: int
    nonblank_count: int
    known_placeholder_counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "blank_count": self.blank_count,
            "nonblank_count": self.nonblank_count,
            "known_placeholder_counts": dict(self.known_placeholder_counts),
        }


@dataclass(frozen=True)
class QuarterlyCandidateResourceAudit:
    dataset_id: str
    market: str
    statement: str
    industry: str
    artifact: str | None
    sha256: str | None
    manifest_sha256: str | None
    state: str
    row_count: int | None
    unique_issuer_count: int | None
    periods: tuple[str, ...] = ()
    output_dates: tuple[str, ...] = ()
    duplicate_business_key_count: int | None = None
    duplicate_business_key_row_count: int | None = None
    schema_fingerprint: str | None = None
    headers: tuple[str, ...] = ()
    field_counts: tuple[QuarterlyFieldCounts, ...] = ()
    row_profiles: tuple[Mapping[str, Any], ...] = ()
    row_profile_count: int = 0
    row_profile_scanned_key_count: int = 0
    row_profiles_truncated: bool = False
    row_profiles_complete: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "market": self.market,
            "statement": self.statement,
            "industry": self.industry,
            "artifact": self.artifact,
            "sha256": self.sha256,
            "manifest_sha256": self.manifest_sha256,
            "state": self.state,
            "row_count": self.row_count,
            "unique_issuer_count": self.unique_issuer_count,
            "periods": list(self.periods),
            "output_dates": list(self.output_dates),
            "duplicate_business_key_count": self.duplicate_business_key_count,
            "duplicate_business_key_row_count": self.duplicate_business_key_row_count,
            "schema_fingerprint": self.schema_fingerprint,
            "headers": list(self.headers),
            "field_counts": [item.to_dict() for item in self.field_counts],
            "row_profiles": [dict(item) for item in self.row_profiles],
            "row_profile_count": self.row_profile_count,
            "row_profile_scanned_key_count": self.row_profile_scanned_key_count,
            "row_profiles_truncated": self.row_profiles_truncated,
            "row_profiles_complete": self.row_profiles_complete,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class QuarterlyCandidateAuditReport:
    overall_state: str
    summary: Mapping[str, Any]
    resources: tuple[QuarterlyCandidateResourceAudit, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AUDIT_SCHEMA,
            "candidate_only": True,
            "formal_db_write": False,
            "source_acceptance": False,
            "gate_credit": False,
            "downstream_eligibility": "none",
            "overall_state": self.overall_state,
            "summary": dict(self.summary),
            "resources": [item.to_dict() for item in self.resources],
            "limitations": [
                "本稽核只描述候選 CSV 的結構與儲存格；不判定空白代表缺漏或不適用。",
                "不推定金額單位、合併／個別基準、coverage、availability、PIT、license 或來源接受。",
                "現況快照與候選列不得因此進入正式資料庫、評分、回測或 ML。",
            ],
        }


def audit_quarterly_candidate_root(candidate_root: Path) -> QuarterlyCandidateAuditReport:
    """讀取呼叫者指定的候選根目錄並建立唯讀、candidate-only 資料品質摘要。"""
    try:
        # absolute() avoids Windows realpath permission failures on sandboxed
        # but readable temp/workspace directories. The selected root is an
        # explicit input; child artifacts are constrained below by basename.
        root = Path(candidate_root).expanduser().absolute()
        root.stat()
    except OSError as exc:
        raise QuarterlyCandidateAuditError("candidate_root_unavailable") from exc
    if not root.is_dir():
        raise QuarterlyCandidateAuditError("candidate_root_not_directory")
    manifest_path = _contained_path(root, MANIFEST_NAME)
    if not manifest_path.is_file() or _is_reparse_point(manifest_path):
        raise QuarterlyCandidateAuditError("candidate_manifest_missing")
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise QuarterlyCandidateAuditError("candidate_manifest_too_large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuarterlyCandidateAuditError(f"candidate_manifest_invalid:{exc}") from exc
    manifest_schema = _validate_manifest(manifest)
    sources = tuple(
        _normalize_manifest_source(source, manifest_schema)
        for source in manifest["sources"]
    )
    dataset_ids = [source.get("dataset_id") for source in sources]
    if (
        any(not isinstance(value, str) or not value.strip() for value in dataset_ids)
        or len(set(dataset_ids)) != len(dataset_ids)
    ):
        raise QuarterlyCandidateAuditError("candidate_manifest_duplicate_or_missing_dataset_id")

    resources = tuple(_audit_resource(root, source) for source in sources)
    counts = Counter(item.state for item in resources)
    summary = {
        "resource_count": len(resources),
        "available_resource_count": counts["available"],
        "empty_response_resource_count": counts["empty_response"],
        "missing_resource_count": counts["missing"],
        "invalid_resource_count": counts["invalid"],
        "summary_complete": counts["missing"] == 0 and counts["invalid"] == 0,
        "row_count": sum(item.row_count or 0 for item in resources),
        "unique_issuer_resource_count": sum(
            item.unique_issuer_count or 0 for item in resources
        ),
        "duplicate_business_key_count": sum(
            item.duplicate_business_key_count or 0 for item in resources
        ),
    }
    if counts["invalid"]:
        overall_state = "invalid"
    elif counts["missing"]:
        overall_state = "partial"
    elif counts["available"] == 0 and counts["empty_response"]:
        overall_state = "empty_response"
    else:
        overall_state = "available"
    return QuarterlyCandidateAuditReport(
        overall_state=overall_state,
        summary=summary,
        resources=resources,
    )


def _validate_manifest(manifest: Any) -> str:
    if not isinstance(manifest, Mapping):
        raise QuarterlyCandidateAuditError("candidate_manifest_not_object")
    schema = manifest.get("schema")
    if schema not in SUPPORTED_MANIFEST_SCHEMAS:
        raise QuarterlyCandidateAuditError("candidate_manifest_schema_unsupported")
    for key, expected in (
        ("candidate_only", True),
        ("formal_db_write", False),
        ("source_acceptance", False),
        ("gate_credit", False),
    ):
        if manifest.get(key) is not expected:
            raise QuarterlyCandidateAuditError(f"candidate_manifest_safety_flag:{key}")
    if not isinstance(manifest.get("sources"), list):
        raise QuarterlyCandidateAuditError("candidate_manifest_sources_not_array")
    if any(not isinstance(source, Mapping) for source in manifest["sources"]):
        raise QuarterlyCandidateAuditError("candidate_manifest_source_not_object")
    return str(schema)


def _normalize_manifest_source(
    source: Mapping[str, Any], manifest_schema: str
) -> Mapping[str, Any]:
    if manifest_schema == INDUSTRY_MANIFEST_SCHEMA:
        normalized = dict(source)
        normalized["capture_http_status"] = source.get("status")
        normalized["capture_status"] = "captured"
        normalized["capture_method"] = source.get("method")
        normalized["capture_truncated"] = False
        return normalized

    nested = source.get("source")
    if not isinstance(nested, Mapping):
        return {**source, "dataset_id": None}
    normalized = dict(source)
    normalized.update(
        {
            "dataset_id": nested.get("dataset_id"),
            "market": nested.get("market"),
            "statement": nested.get("statement"),
            "industry": nested.get("industry", "unknown"),
            "capture_http_status": source.get("http_status"),
            "capture_status": source.get("status"),
            "capture_method": source.get("request_method"),
            "capture_truncated": source.get("truncated_at_limit"),
        }
    )
    return normalized


def _audit_resource(
    root: Path, source: Mapping[str, Any]
) -> QuarterlyCandidateResourceAudit:
    metadata: QuarterlyResourceMetadata = {
        "dataset_id": _text_or_unknown(source.get("dataset_id")),
        "market": _text_or_unknown(source.get("market")),
        "statement": _text_or_unknown(source.get("statement")),
        "industry": _text_or_unknown(source.get("industry")),
    }
    artifact_value = source.get("artifact")
    artifact = artifact_value if isinstance(artifact_value, str) else None
    manifest_sha = source.get("body_sha256")
    manifest_sha256 = manifest_sha.lower() if isinstance(manifest_sha, str) else None
    if not _valid_resource_metadata(source) or not _valid_resource_receipt(source):
        return _resource_failure(
            metadata,
            artifact,
            manifest_sha256,
            "invalid",
            "manifest resource metadata, safety flags, or body/readback receipt is invalid",
        )
    if not isinstance(artifact, str):
        return _resource_failure(
            metadata, artifact, manifest_sha256, "invalid", "manifest artifact is missing"
        )
    try:
        path = _contained_path(root, artifact)
    except QuarterlyCandidateAuditError as exc:
        return _resource_failure(metadata, artifact, manifest_sha256, "invalid", str(exc))
    if not path.exists():
        return _resource_failure(
            metadata, artifact, manifest_sha256, "missing", "manifest-listed artifact is missing"
        )
    if not path.is_file():
        return _resource_failure(
            metadata, artifact, manifest_sha256, "invalid", "manifest artifact is not a file"
        )
    try:
        actual_bytes = path.stat().st_size
        if actual_bytes > int(source["max_body_bytes"]):
            return _resource_failure(
                metadata, artifact, manifest_sha256, "invalid", "artifact exceeds manifest size bound"
            )
        raw = path.read_bytes()
    except OSError as exc:
        return _resource_failure(metadata, artifact, manifest_sha256, "invalid", f"artifact read failed:{exc}")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    body_sha256 = source.get("body_sha256")
    readback_sha256 = source.get("readback_sha256")
    assert isinstance(body_sha256, str)
    assert isinstance(readback_sha256, str)
    if (
        actual_bytes != source["body_bytes"]
        or actual_bytes != source["readback_bytes"]
        or actual_sha256 != body_sha256.lower()
        or actual_sha256 != readback_sha256.lower()
    ):
        return _resource_failure(
            metadata,
            artifact,
            manifest_sha256,
            "invalid",
            "artifact byte count or SHA-256 differs from manifest body/readback receipt",
            actual_sha256=actual_sha256,
        )
    try:
        text = raw.decode("utf-8-sig")
        headers, rows = _parse_csv(text)
        return _profile_resource(
            metadata,
            artifact,
            actual_sha256,
            headers,
            rows,
        )
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        return _resource_failure(
            metadata,
            artifact,
            manifest_sha256,
            "invalid",
            f"CSV schema or parse error:{exc}",
            actual_sha256=actual_sha256,
        )


def _valid_resource_metadata(source: Mapping[str, Any]) -> bool:
    required = ("dataset_id", "market", "statement", "industry")
    if any(not isinstance(source.get(key), str) or not source[key].strip() for key in required):
        return False
    artifact = source.get("artifact")
    if not isinstance(artifact, str) or not artifact.strip():
        return False
    if source.get("csv_parse_status") != "parsed":
        return False
    if source.get("error") not in (None, ""):
        return False
    return True


def _valid_resource_receipt(source: Mapping[str, Any]) -> bool:
    if source.get("capture_method") != "GET" or source.get("redirects_followed") is not False:
        return False
    status = source.get("capture_http_status")
    if isinstance(status, bool) or not isinstance(status, int) or status != 200:
        return False
    if source.get("capture_status") != "captured":
        return False
    if source.get("capture_truncated") is not False:
        return False
    if source.get("readback_matches") is not True:
        return False
    body_sha256 = source.get("body_sha256")
    readback_sha256 = source.get("readback_sha256")
    if (
        not isinstance(body_sha256, str)
        or not _SHA256_RE.fullmatch(body_sha256)
        or not isinstance(readback_sha256, str)
        or not _SHA256_RE.fullmatch(readback_sha256)
    ):
        return False
    if body_sha256.lower() != readback_sha256.lower():
        return False
    for key in ("body_bytes", "readback_bytes", "max_body_bytes"):
        value = source.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
    if source["body_bytes"] != source["readback_bytes"]:
        return False
    if source["max_body_bytes"] <= 0 or source["max_body_bytes"] > MAX_RESOURCE_BYTES:
        return False
    return source["body_bytes"] <= source["max_body_bytes"]


def _contained_path(root: Path, artifact: str) -> Path:
    if (
        not artifact
        or artifact in {".", ".."}
        or "/" in artifact
        or "\\" in artifact
        or ":" in artifact
        or Path(artifact).name != artifact
    ):
        raise QuarterlyCandidateAuditError("artifact_must_be_basename")
    path = root / artifact
    if _is_reparse_point(path):
        raise QuarterlyCandidateAuditError("artifact_reparse_point_rejected")
    return path


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return path.is_symlink()
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_attribute)


def _parse_csv(text: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return (), ()
    headers = tuple(raw_headers)
    normalized = tuple(header.strip() for header in headers)
    if not headers or any(not name for name in normalized):
        raise ValueError("CSV header is empty or contains a blank column")
    if len(set(normalized)) != len(normalized):
        raise ValueError("CSV header contains duplicate column names")
    rows: list[tuple[str, ...]] = []
    for row in reader:
        if not row:
            continue
        if len(row) != len(headers):
            raise ValueError("CSV row width differs from header width")
        rows.append(tuple(row))
    return headers, tuple(rows)


def _profile_resource(
    metadata: QuarterlyResourceMetadata,
    artifact: str,
    actual_sha256: str,
    headers: tuple[str, ...],
    physical_rows: tuple[tuple[str, ...], ...],
) -> QuarterlyCandidateResourceAudit:
    if not headers:
        return QuarterlyCandidateResourceAudit(
            **metadata,
            artifact=artifact,
            sha256=actual_sha256,
            manifest_sha256=actual_sha256,
            state="empty_response",
            row_count=0,
            unique_issuer_count=0,
            duplicate_business_key_count=0,
            duplicate_business_key_row_count=0,
            row_profiles_complete=True,
            warnings=("resource body is empty and contains no schema header",),
        )
    normalized_headers = tuple(header.strip() for header in headers)
    positions = {name: index for index, name in enumerate(normalized_headers)}
    issuer_header = _first_header(positions, _ISSUER_HEADERS)
    year_header = _first_header(positions, _YEAR_HEADERS)
    quarter_header = _first_header(positions, _QUARTER_HEADERS)
    output_date_header = _first_header(positions, _OUTPUT_DATE_HEADERS)
    company_name_header = _first_header(positions, _COMPANY_NAME_HEADERS)
    if issuer_header is None or year_header is None or quarter_header is None:
        raise ValueError("CSV lacks issuer, fiscal year, or quarter identity column")

    valid_rows: list[tuple[str, ...]] = []
    output_dates: set[str] = set()
    all_identity_empty = True
    for row in physical_rows:
        normalized_values = tuple(value.strip() for value in row)
        if output_date_header is not None and normalized_values[positions[output_date_header]]:
            output_dates.add(normalized_values[positions[output_date_header]])
        identity_values = (
            normalized_values[positions[issuer_header]],
            normalized_values[positions[year_header]],
            normalized_values[positions[quarter_header]],
        )
        if any(identity_values):
            all_identity_empty = False
        if not any(identity_values):
            continue
        if not all(identity_values):
            raise ValueError("CSV data row has a partial issuer/year/quarter key")
        valid_rows.append(row)

    schema_fingerprint = hashlib.sha256(
        json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not valid_rows and physical_rows and all_identity_empty:
        return QuarterlyCandidateResourceAudit(
            **metadata,
            artifact=artifact,
            sha256=actual_sha256,
            manifest_sha256=actual_sha256,
            state="empty_response",
            row_count=0,
            unique_issuer_count=0,
            output_dates=tuple(sorted(output_dates)),
            duplicate_business_key_count=0,
            duplicate_business_key_row_count=0,
            schema_fingerprint=schema_fingerprint,
            headers=headers,
            row_profiles_complete=True,
            warnings=("CSV contains a header and no issuer-period data rows",),
        )
    if not valid_rows:
        return QuarterlyCandidateResourceAudit(
            **metadata,
            artifact=artifact,
            sha256=actual_sha256,
            manifest_sha256=actual_sha256,
            state="empty_response",
            row_count=0,
            unique_issuer_count=0,
            duplicate_business_key_count=0,
            duplicate_business_key_row_count=0,
            schema_fingerprint=schema_fingerprint,
            headers=headers,
            row_profiles_complete=True,
            warnings=("CSV contains a header and no data rows",),
        )

    issuer_position = positions[issuer_header]
    year_position = positions[year_header]
    quarter_position = positions[quarter_header]
    issuer_codes = {
        row[issuer_position].strip() for row in valid_rows if row[issuer_position].strip()
    }
    periods = {
        f"{row[year_position].strip()}-Q{row[quarter_position].strip()}"
        for row in valid_rows
    }
    keys = Counter(
        (
            row[issuer_position].strip(),
            row[year_position].strip(),
            row[quarter_position].strip(),
        )
        for row in valid_rows
    )
    financial_positions = tuple(
        index
        for index, header in enumerate(normalized_headers)
        if header not in _IDENTITY_AND_DATE_HEADERS
    )
    field_counts = tuple(
        _count_field(headers[index], (row[index] for row in valid_rows))
        for index in financial_positions
    )
    duplicate_key_count = sum(count > 1 for count in keys.values())
    duplicate_key_row_count = sum(count - 1 for count in keys.values() if count > 1)
    row_profiles = _build_row_profiles(
        valid_rows=valid_rows,
        issuer_position=issuer_position,
        year_position=year_position,
        quarter_position=quarter_position,
        output_date_position=(
            positions[output_date_header] if output_date_header is not None else None
        ),
        company_name_position=(
            positions[company_name_header] if company_name_header is not None else None
        ),
        financial_positions=financial_positions,
        headers=headers,
    )
    row_profiles_truncated = len(row_profiles) > MAX_ROW_PROFILES_PER_RESOURCE
    row_profiles = row_profiles[:MAX_ROW_PROFILES_PER_RESOURCE]
    warnings: tuple[str, ...] = (
        ("blank-cell meaning is unknown; blanks were not imputed",)
        if any(field.blank_count for field in field_counts)
        else ()
    )
    if row_profiles_truncated:
        warnings += (
            f"row profile output truncated at {MAX_ROW_PROFILES_PER_RESOURCE} keys; "
            f"{len(keys)} distinct keys were scanned",
        )
    return QuarterlyCandidateResourceAudit(
        **metadata,
        artifact=artifact,
        sha256=actual_sha256,
        manifest_sha256=actual_sha256,
        state="available",
        row_count=len(valid_rows),
        unique_issuer_count=len(issuer_codes),
        periods=tuple(sorted(periods)),
        output_dates=tuple(sorted(output_dates)),
        duplicate_business_key_count=duplicate_key_count,
        duplicate_business_key_row_count=duplicate_key_row_count,
        schema_fingerprint=schema_fingerprint,
        headers=headers,
        field_counts=field_counts,
        row_profiles=tuple(row_profiles),
        row_profile_count=len(row_profiles),
        row_profile_scanned_key_count=len(keys),
        row_profiles_truncated=row_profiles_truncated,
        row_profiles_complete=not row_profiles_truncated,
        warnings=warnings,
    )


def _build_row_profiles(
    *,
    valid_rows: list[tuple[str, ...]],
    issuer_position: int,
    year_position: int,
    quarter_position: int,
    output_date_position: int | None,
    company_name_position: int | None,
    financial_positions: tuple[int, ...],
    headers: tuple[str, ...],
) -> list[dict[str, Any]]:
    profiles: dict[tuple[str, str, str], dict[str, Any]] = {}
    known_placeholders = set(KNOWN_PLACEHOLDERS)
    for row in valid_rows:
        issuer = row[issuer_position].strip()
        year = row[year_position].strip()
        quarter = row[quarter_position].strip()
        key = (issuer, year, quarter)
        profile = profiles.get(key)
        if profile is None:
            profile = {
                "issuer_code": issuer,
                "issuer_names": set(),
                "fiscal_period": f"{year}-Q{quarter}",
                "output_dates": set(),
                "source_row_count": 0,
                "blank_cell_count": 0,
                "nonblank_cell_count": 0,
                "blank_fields": set(),
                "known_placeholder_counts": Counter(),
            }
            profiles[key] = profile
        profile["source_row_count"] += 1
        if company_name_position is not None:
            issuer_name = row[company_name_position].strip()
            if issuer_name:
                profile["issuer_names"].add(issuer_name)
        if output_date_position is not None:
            profile["output_dates"].add(row[output_date_position])
        for position in financial_positions:
            value = row[position].strip()
            if not value:
                profile["blank_cell_count"] += 1
                profile["blank_fields"].add(headers[position].strip())
            else:
                profile["nonblank_cell_count"] += 1
                if value in known_placeholders:
                    profile["known_placeholder_counts"][value] += 1

    result: list[dict[str, Any]] = []
    for key in sorted(profiles):
        profile = profiles[key]
        names = sorted(profile["issuer_names"])
        result.append(
            {
                "issuer_code": profile["issuer_code"],
                "issuer_name": names[0] if len(names) == 1 else None,
                "issuer_name_conflict": len(names) > 1,
                "fiscal_period": profile["fiscal_period"],
                "output_dates": sorted(profile["output_dates"]),
                "source_row_count": profile["source_row_count"],
                "blank_cell_count": profile["blank_cell_count"],
                "nonblank_cell_count": profile["nonblank_cell_count"],
                "blank_fields": sorted(profile["blank_fields"]),
                "known_placeholder_counts": {
                    token: profile["known_placeholder_counts"][token]
                    for token in KNOWN_PLACEHOLDERS
                    if profile["known_placeholder_counts"][token]
                },
            }
        )
    return result


def _count_field(field_name: str, values: Iterable[str]) -> QuarterlyFieldCounts:
    blank_count = 0
    nonblank_count = 0
    placeholders: Counter[str] = Counter()
    known = set(KNOWN_PLACEHOLDERS)
    for raw in values:
        value = raw.strip()
        if not value:
            blank_count += 1
        else:
            nonblank_count += 1
            if value in known:
                placeholders[value] += 1
    return QuarterlyFieldCounts(
        field_name=field_name,
        blank_count=blank_count,
        nonblank_count=nonblank_count,
        known_placeholder_counts={
            token: placeholders[token] for token in KNOWN_PLACEHOLDERS if placeholders[token]
        },
    )


def _resource_failure(
    metadata: QuarterlyResourceMetadata,
    artifact: str | None,
    manifest_sha256: str | None,
    state: str,
    warning: str,
    *,
    actual_sha256: str | None = None,
) -> QuarterlyCandidateResourceAudit:
    return QuarterlyCandidateResourceAudit(
        **metadata,
        artifact=artifact,
        sha256=actual_sha256,
        manifest_sha256=manifest_sha256,
        state=state,
        row_count=None,
        unique_issuer_count=None,
        duplicate_business_key_count=None,
        duplicate_business_key_row_count=None,
        warnings=(warning,),
    )


def _first_header(
    positions: Mapping[str, int], candidates: tuple[str, ...]
) -> str | None:
    return next((candidate for candidate in candidates if candidate in positions), None)


def _text_or_unknown(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else "unknown"
