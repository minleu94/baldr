"""Build a governed current-only quarterly statement snapshot candidate.

The TWSE/TPEx OpenAPI response is a batch snapshot.  It is useful for the
current reader, but it does not carry a row-level historical publication
receipt.  This command therefore writes the snapshot to the development
output tree and explicitly marks it as ineligible for the formal PIT table.
The MOPS EZSearch mapping is copied beside it as announcement/available-date
evidence; the numeric response is never promoted to a formal PIT value merely
because a matching announcement exists.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.current_fundamental_snapshots import COLUMNS


TARGET_STATEMENT_TYPES = frozenset({"income", "balance", "cashflow"})
STATEMENT_ITEM_PREFIX = {
    "income": "income_statement",
    "balance": "balance_sheet",
    "cashflow": "cash_flows_statement",
}
IDENTITY_FIELDS = frozenset(
    {
        "出表日期",
        "年度",
        "季別",
        "公司代號",
        "公司名稱",
        "Date",
        "Year",
        "Season",
        "SecuritiesCompanyCode",
        "CompanyName",
    }
)
MISSING_MARKERS = frozenset({"", "--", "—", "－", "N/A", "NA", "null", "None"})
NUMERIC_ITEM_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
FORMAL_PIT_INELIGIBILITY_REASON = (
    "OpenAPI numeric rows are a batch current snapshot without row-level "
    "historical publication/revision custody; MOPS announcement evidence is "
    "kept as a separate sidecar and cannot promote these values to formal PIT."
)
STATEMENT_NORMALIZATION_VERSION = "official-openapi-current-statement-normalizer.v2"


@dataclass
class BuildDiagnostics:
    malformed_endpoints: list[dict[str, str]] = field(default_factory=list)
    malformed_rows: list[dict[str, str]] = field(default_factory=list)
    invalid_values: list[dict[str, str]] = field(default_factory=list)
    duplicate_values: list[dict[str, str]] = field(default_factory=list)
    conflicting_values: list[dict[str, str]] = field(default_factory=list)
    missing_values: int = 0


@dataclass(frozen=True)
class EndpointContext:
    filename: str
    exchange: str
    statement_type: str
    url: str
    sha256: str
    status: str

    @property
    def source_version(self) -> str:
        return f"official-openapi-statement-endpoints.v1:sha256:{self.sha256}"


def build_candidate(
    *,
    openapi_root: Path,
    availability_roots: Sequence[Path],
    output_root: Path,
    period: str,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Read captured official responses and write a current-only candidate."""

    target_period, period_end = _normalise_target_period(period)
    openapi_root = Path(openapi_root).expanduser()
    availability_roots = tuple(Path(root).expanduser() for root in availability_roots)
    output_root = Path(output_root).expanduser()
    output_paths = _candidate_output_paths(output_root)
    source_roots = _candidate_source_roots(openapi_root, availability_roots)
    _validate_output_root_separation(output_root, source_roots)

    manifest_path = Path(openapi_root) / "endpoint_manifest.json"
    manifest = _read_json_object(manifest_path)
    source_capture_at = _parse_aware_datetime(
        str(manifest.get("captured_at", "")),
        field_name="captured_at",
    )
    capture_at = (
        source_capture_at
        if observed_at is None
        else _parse_aware_datetime(observed_at.isoformat(), field_name="observed_at")
    )
    if capture_at < source_capture_at:
        raise ValueError("observed_at 不得早於 endpoint manifest 的 captured_at")
    now = datetime.now(timezone.utc)
    if capture_at > now:
        raise ValueError("observed_at cannot be in the future")

    endpoints = manifest.get("endpoints")
    if not isinstance(endpoints, Mapping):
        raise ValueError("endpoint manifest has no endpoints mapping")

    diagnostics = BuildDiagnostics()
    logical_records: dict[tuple[str, str, str, str], dict[str, str]] = {}
    conflicted_keys: set[tuple[str, str, str, str]] = set()
    endpoint_summaries: list[dict[str, Any]] = []
    endpoint_source_paths: list[Path] = []

    for filename, raw_meta in sorted(endpoints.items()):
        endpoint_source_paths.append(Path(openapi_root) / str(filename))
        if not isinstance(raw_meta, Mapping):
            diagnostics.malformed_endpoints.append(
                {"file": str(filename), "reason": "manifest_entry_not_object"}
            )
            continue
        context = _endpoint_context(str(filename), raw_meta)
        if context.statement_type not in TARGET_STATEMENT_TYPES:
            continue
        endpoint_path = Path(openapi_root) / context.filename
        endpoint_summary: dict[str, Any] = {
            "file": context.filename,
            "exchange": context.exchange,
            "statement_type": context.statement_type,
            "url": context.url,
            "sha256": context.sha256,
            "status": context.status,
            "rows_seen": 0,
            "rows_selected": 0,
            "rows_malformed": 0,
            "fields_numeric": 0,
            "fields_missing": 0,
            "fields_invalid": 0,
        }
        if context.status != "ok":
            endpoint_summary["reason"] = "upstream_status_not_ok"
            diagnostics.malformed_endpoints.append(
                {"file": context.filename, "reason": "upstream_status_not_ok"}
            )
            endpoint_summaries.append(endpoint_summary)
            continue
        if not endpoint_path.exists():
            endpoint_summary["reason"] = "response_file_missing"
            diagnostics.malformed_endpoints.append(
                {"file": context.filename, "reason": "response_file_missing"}
            )
            endpoint_summaries.append(endpoint_summary)
            continue
        actual_sha256 = _sha256_file(endpoint_path).removeprefix("sha256:")
        if actual_sha256 != context.sha256:
            endpoint_summary["reason"] = "response_hash_mismatch"
            diagnostics.malformed_endpoints.append(
                {"file": context.filename, "reason": "response_hash_mismatch"}
            )
            endpoint_summaries.append(endpoint_summary)
            continue
        try:
            payload = json.loads(endpoint_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            endpoint_summary["reason"] = "response_not_json"
            diagnostics.malformed_endpoints.append(
                {"file": context.filename, "reason": f"response_not_json:{type(exc).__name__}"}
            )
            endpoint_summaries.append(endpoint_summary)
            continue
        if not isinstance(payload, list):
            endpoint_summary["reason"] = "response_not_row_array"
            diagnostics.malformed_endpoints.append(
                {"file": context.filename, "reason": "response_not_row_array"}
            )
            endpoint_summaries.append(endpoint_summary)
            continue

        for row_number, raw_row in enumerate(payload, start=1):
            endpoint_summary["rows_seen"] += 1
            if not isinstance(raw_row, Mapping):
                _record_malformed_row(
                    diagnostics,
                    endpoint_summary,
                    context,
                    row_number,
                    "row_not_object",
                )
                continue
            identity = _row_identity(raw_row, context.exchange, context.statement_type)
            if identity is None:
                _record_malformed_row(
                    diagnostics,
                    endpoint_summary,
                    context,
                    row_number,
                    "missing_stock_or_period",
                )
                continue
            stock_code, row_period = identity
            if row_period != target_period:
                _record_malformed_row(
                    diagnostics,
                    endpoint_summary,
                    context,
                    row_number,
                    f"period_mismatch:{row_period}",
                )
                continue
            endpoint_summary["rows_selected"] += 1
            logical_prefix = (stock_code, "statement_item", target_period, "")
            for item_name, raw_value in raw_row.items():
                if str(item_name) in IDENTITY_FIELDS:
                    continue
                text_value = "" if raw_value is None else str(raw_value).strip()
                if text_value in MISSING_MARKERS:
                    diagnostics.missing_values += 1
                    endpoint_summary["fields_missing"] += 1
                    continue
                parsed = _parse_decimal(text_value)
                if parsed is None:
                    diagnostics.invalid_values.append(
                        {
                            "file": context.filename,
                            "row": str(row_number),
                            "stock_code": stock_code,
                            "statement_type": context.statement_type,
                            "item_name": str(item_name),
                            "value": text_value,
                        }
                    )
                    endpoint_summary["fields_invalid"] += 1
                    continue
                endpoint_summary["fields_numeric"] += 1
                statement_prefix = STATEMENT_ITEM_PREFIX[context.statement_type]
                item_code = f"{statement_prefix}:{item_name}"
                key = (*logical_prefix[:3], item_code)
                record = _make_record(
                    stock_code=stock_code,
                    statement_type=context.statement_type,
                    period=target_period,
                    period_end=period_end,
                    item_code=item_code,
                    raw_item_name=str(item_name),
                    value=parsed,
                    observed_at=capture_at,
                    source=context.url,
                    source_version=context.source_version,
                    market=context.exchange,
                )
                previous = logical_records.get(key)
                if previous is None and key not in conflicted_keys:
                    logical_records[key] = record
                elif previous is not None and previous["value"] == record["value"]:
                    diagnostics.duplicate_values.append(
                        {
                            "stock_code": stock_code,
                            "statement_type": context.statement_type,
                            "item_code": item_code,
                            "file": context.filename,
                            "reason": "identical_value_duplicate",
                        }
                    )
                else:
                    logical_records.pop(key, None)
                    conflicted_keys.add(key)
                    diagnostics.conflicting_values.append(
                        {
                            "stock_code": stock_code,
                            "statement_type": context.statement_type,
                            "item_code": item_code,
                            "file": context.filename,
                            "reason": "conflicting_numeric_values",
                        }
                    )
        endpoint_summaries.append(endpoint_summary)

    if not logical_records:
        raise ValueError("no numeric statement observations survived validation")

    records = [logical_records[key] for key in sorted(logical_records)]
    availability_rows, availability_files = _read_availability_rows(
        availability_roots,
        target_period,
    )
    _validate_output_file_separation(
        output_paths.values(),
        (manifest_path, *endpoint_source_paths, *availability_files),
    )
    current_identity = {
        (row["stock_code"], _statement_type_from_item_code(row["item_code"]), row["period"])
        for row in records
    }
    availability_identity = {
        (row["stock_code"], row["statement_type"], row["period"])
        for row in availability_rows
    }
    missing_availability = sorted(current_identity - availability_identity)
    missing_numeric = sorted(availability_identity - current_identity)

    output_root.mkdir(parents=True, exist_ok=True)
    observations_path = output_paths["observations"]
    mapping_path = output_paths["availability_mapping"]
    manifest_output_path = output_paths["candidate_manifest"]
    pit_status_path = output_paths["pit_status"]
    preview_path = output_paths["preview"]
    command_path = output_paths["apply_command"]

    _write_records(observations_path, records)
    _write_mapping(mapping_path, availability_rows)
    manifest_output = {
        "schema_version": "current-fundamental-statement-candidate.v2",
        "kind": "statement_item",
        "period": target_period,
        "as_of_date": period_end.isoformat(),
        "observed_at": capture_at.isoformat(),
        "source_snapshot": {
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "manifest_captured_at": str(manifest.get("captured_at", "")),
            "endpoint_count": len(endpoint_summaries),
        },
        "source_policy": {
            "numeric_source": "official TWSE/TPEx OpenAPI",
            "numeric_unit_policy": (
                "The captured OpenAPI envelope does not prove row-level units; "
                "raw Decimal values are preserved and unit is unknown."
            ),
            "period_basis_policy": (
                "The captured OpenAPI envelope does not prove row-level period basis; "
                "period_basis is unknown and basis/aggregate eligibility are false."
            ),
            "announcement_sidecar": "MOPS EZSearch F26/F27/F28",
            "formal_pit_eligible": False,
            "formal_pit_ineligibility_reason": FORMAL_PIT_INELIGIBILITY_REASON,
            "research_only": True,
            "formal_credit_authorized": False,
        },
        "coverage": {
            "record_count": len(records),
            "current_identity_count": len(current_identity),
            "current_stock_count": len({row["stock_code"] for row in records}),
            "current_market_counts": _count_by(records, "market"),
            "current_statement_type_counts": _count_statement_types(records),
            "availability_row_count": len(availability_rows),
            "availability_identity_count": len(availability_identity),
            "availability_stock_count": len({row["stock_code"] for row in availability_rows}),
            "current_identity_missing_announcement_evidence_count": len(missing_availability),
            "current_identity_missing_announcement_evidence_sample": [
                {
                    "stock_code": stock,
                    "statement_type": statement_type,
                    "period": current_period,
                }
                for stock, statement_type, current_period in missing_availability[:50]
            ],
            "availability_identity_missing_numeric_snapshot_count": len(missing_numeric),
            "availability_identity_missing_numeric_snapshot_sample": [
                {
                    "stock_code": stock,
                    "statement_type": statement_type,
                    "period": current_period,
                }
                for stock, statement_type, current_period in missing_numeric[:50]
            ],
        },
        "diagnostics": {
            "malformed_endpoint_count": len(diagnostics.malformed_endpoints),
            "malformed_endpoints": diagnostics.malformed_endpoints,
            "malformed_row_count": len(diagnostics.malformed_rows),
            "malformed_row_sample": diagnostics.malformed_rows[:50],
            "invalid_numeric_value_count": len(diagnostics.invalid_values),
            "invalid_numeric_value_sample": diagnostics.invalid_values[:50],
            "missing_value_count": diagnostics.missing_values,
            "identical_duplicate_count": len(diagnostics.duplicate_values),
            "conflicting_value_count": len(diagnostics.conflicting_values),
            "conflicting_value_sample": diagnostics.conflicting_values[:50],
            "failed_endpoint_files": [
                summary["file"]
                for summary in endpoint_summaries
                if summary.get("status") != "ok"
            ],
        },
        "endpoint_summaries": endpoint_summaries,
        "availability_files": [str(path) for path in availability_files],
        "artifacts": {
            "observations_csv": observations_path.name,
            "observations_csv_sha256": _sha256_file(observations_path),
            "availability_mapping_csv": mapping_path.name,
            "availability_mapping_csv_sha256": _sha256_file(mapping_path),
            "formal_pit_status_json": pit_status_path.name,
            "preview_json": preview_path.name,
        },
    }
    _write_json(manifest_output_path, manifest_output)
    _write_json(
        pit_status_path,
        {
            "schema_version": "fundamental-statement-pit-status.v2",
            "period": target_period,
            "formal_pit_eligible": False,
            "numeric_source": "official TWSE/TPEx OpenAPI current snapshot",
            "numeric_unit_policy": (
                "The current OpenAPI capture does not prove row-level units; raw "
                "Decimal values are preserved with unit=unknown."
            ),
            "period_basis_policy": (
                "The current OpenAPI capture does not prove row-level period basis; "
                "period_basis=unknown and basis/aggregate eligibility=false."
            ),
            "announcement_source": "MOPS EZSearch F26/F27/F28",
            "reason": FORMAL_PIT_INELIGIBILITY_REASON,
            "cash_flow_numeric_snapshot_available": False,
            "cash_flow_availability_sidecar_available": any(
                row["statement_type"] == "cash_flows_statement" for row in availability_rows
            ),
            "preservation_rule": (
                "Do not apply this candidate to fundamental_statement_items; "
                "root may apply only to fundamental_current_observations."
            ),
        },
    )
    _write_json(
        preview_path,
        {
            "period": target_period,
            "observed_at": capture_at.isoformat(),
            "record_count": len(records),
            "rows": records[:25],
        },
    )
    command_path.write_text(
        "# Dry-run first; root owns backup/apply to the selected repository DB.\n"
        ".\\.venv\\Scripts\\python.exe scripts\\apply_current_statement_snapshot.py "
        f"--candidate {observations_path} --manifest {manifest_output_path}\n"
        "# Apply only after root backup/review:\n"
        ".\\.venv\\Scripts\\python.exe scripts\\apply_current_statement_snapshot.py "
        f"--candidate {observations_path} --manifest {manifest_output_path} "
        "--db-file <EXPLICIT_DB> --backup-dir <EXPLICIT_BACKUP_DIR> "
        "--apply --confirm apply-current-statement-snapshot\n",
        encoding="utf-8",
    )
    return manifest_output


def _endpoint_context(filename: str, metadata: Mapping[str, Any]) -> EndpointContext:
    exchange = str(metadata.get("exchange", "")).strip().lower()
    statement_type = str(metadata.get("statement_type", "")).strip().lower()
    sha256 = str(metadata.get("sha256", "")).strip().lower()
    if exchange not in {"twse", "tpex"}:
        raise ValueError(f"unsupported exchange in endpoint manifest: {exchange}")
    if statement_type not in TARGET_STATEMENT_TYPES:
        raise ValueError(f"unsupported statement type in endpoint manifest: {statement_type}")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError(f"invalid endpoint sha256: {filename}")
    return EndpointContext(
        filename=filename,
        exchange=exchange,
        statement_type=statement_type,
        url=str(metadata.get("url", "")).strip(),
        sha256=sha256,
        status=str(metadata.get("status", "")).strip().lower(),
    )


def _row_identity(
    row: Mapping[str, Any],
    exchange: str,
    statement_type: str,
) -> tuple[str, str] | None:
    if exchange == "twse":
        stock = _first_nonempty(row, "公司代號", "SecuritiesCompanyCode")
        year = _first_nonempty(row, "年度", "Year")
        season = _first_nonempty(row, "季別", "Season")
    else:
        # TPEx general endpoints use English identity labels, while several
        # sector endpoints use the TWSE Chinese aliases in the same payload.
        stock = _first_nonempty(row, "SecuritiesCompanyCode", "公司代號")
        year = _first_nonempty(row, "Year", "年度")
        season = _first_nonempty(row, "Season", "季別")
    if not re.fullmatch(r"\d{4,6}", stock):
        return None
    if not re.fullmatch(r"\d{1,4}", year) or season not in {"1", "2", "3", "4"}:
        return None
    normalized_year = int(year)
    if normalized_year < 1911:
        normalized_year += 1911
    return stock, f"{normalized_year:04d}-Q{season}"


def _first_nonempty(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(row.get(name, "")).strip()
        if value:
            return value
    return ""


def _make_record(
    *,
    stock_code: str,
    statement_type: str,
    period: str,
    period_end: date,
    item_code: str,
    raw_item_name: str,
    value: Decimal,
    observed_at: datetime,
    source: str,
    source_version: str,
    market: str,
) -> dict[str, str]:
    item_name = _display_item_name(statement_type, raw_item_name)
    unit = "unknown"
    source_version = _normalized_statement_source_version(
        source_version,
        stock_code=stock_code,
        market=market,
        statement_type=statement_type,
        period=period,
        item_code=item_code,
        item_name=item_name,
        value=format(value, "f"),
        unit=unit,
    )
    return {
        "stock_code": stock_code,
        "kind": "statement_item",
        "period": period,
        "as_of_date": period_end.isoformat(),
        "item_code": item_code,
        "item_name": item_name,
        "value": format(value, "f"),
        "unit": unit,
        "observed_at": observed_at.isoformat(),
        "source": source,
        "source_version": source_version,
        "market": market,
        "period_basis": "unknown",
        "basis_verified": "0",
        "aggregate_feature_eligible": "0",
    }


def _normalized_statement_source_version(
    raw_source_version: str,
    *,
    stock_code: str,
    market: str,
    statement_type: str,
    period: str,
    item_code: str,
    item_name: str,
    value: str,
    unit: str,
) -> str:
    """將正規化列綁定至原始擷取與目前正規化版本。"""
    if re.fullmatch(
        r"official-openapi-statement-endpoints\.v1:sha256:[0-9a-f]{64}",
        raw_source_version,
    ) is None:
        raise ValueError("statement source version must retain its raw endpoint SHA-256")
    payload = "\0".join(
        (
            STATEMENT_NORMALIZATION_VERSION,
            raw_source_version,
            stock_code,
            market,
            statement_type,
            period,
            item_code,
            item_name,
            value,
            unit,
            "period_basis=unknown",
            "basis_verified=0",
            "aggregate_feature_eligible=0",
        )
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return (
        f"{STATEMENT_NORMALIZATION_VERSION}:{market}:{statement_type}:{period}:"
        f"raw:{raw_source_version}:derived:sha256:{digest}"
    )


def _candidate_output_paths(output_root: Path) -> dict[str, Path]:
    """列出候選建置會寫入的所有固定輸出檔。"""
    return {
        "observations": output_root / "statement_current_observations.csv",
        "availability_mapping": output_root / "statement_availability_q2_mapping.csv",
        "candidate_manifest": output_root / "statement_current_candidate.json",
        "pit_status": output_root / "statement_formal_pit_status.json",
        "preview": output_root / "statement_current_preview.json",
        "apply_command": output_root / "apply_current_statement_snapshot_command.txt",
    }


def _candidate_source_roots(
    openapi_root: Path, availability_roots: Sequence[Path]
) -> tuple[Path, ...]:
    roots = [openapi_root]
    for raw_root in availability_roots:
        root = raw_root.expanduser()
        if root.is_file() or root.name.lower() == "mapping.csv":
            root = root.parent
        roots.append(root)
    return tuple(root.resolve(strict=False) for root in roots)


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(path).expanduser().resolve(strict=False))))


def _path_is_within(path: Path, parent: Path) -> bool:
    normalized_path = _normalized_path(path)
    normalized_parent = _normalized_path(parent)
    try:
        return os.path.commonpath((normalized_path, normalized_parent)) == normalized_parent
    except ValueError:
        return False


def _validate_output_root_separation(
    output_root: Path, source_roots: Sequence[Path]
) -> None:
    resolved_output_root = output_root.resolve(strict=False)
    for source_root in source_roots:
        if _path_is_within(resolved_output_root, source_root) or _path_is_within(
            source_root, resolved_output_root
        ):
            raise ValueError(
                "候選輸出根目錄與 OpenAPI 或 availability 來源根目錄重疊，拒絕寫入"
            )


def _validate_output_file_separation(
    output_paths: Iterable[Path], source_paths: Iterable[Path]
) -> None:
    for output_path in output_paths:
        resolved_output = output_path.expanduser().resolve(strict=False)
        normalized_output = os.path.normcase(os.path.normpath(str(resolved_output)))
        for source_path in source_paths:
            resolved_source = source_path.expanduser().resolve(strict=False)
            normalized_source = os.path.normcase(os.path.normpath(str(resolved_source)))
            if normalized_output == normalized_source:
                raise ValueError(
                    f"候選輸出檔與來源檔路徑相同，拒絕覆寫：{resolved_output}"
                )
            if resolved_output.exists() and resolved_source.exists():
                try:
                    same_file = os.path.samefile(resolved_output, resolved_source)
                except OSError as exc:
                    raise ValueError(
                        "無法確認候選輸出檔與來源檔是否為同一實體檔案"
                    ) from exc
                if same_file:
                    raise ValueError(
                        f"候選輸出檔與來源檔指向同一實體檔案，拒絕覆寫：{resolved_source}"
                    )


def _display_item_name(statement_type: str, field_name: str) -> str:
    """Keep the report type visible without guessing the source basis."""
    if statement_type == "income":
        prefix, basis = "損益表", "期間基礎未驗證"
    elif statement_type == "cashflow":
        prefix, basis = "現金流量表", "期間基礎未明示"
    else:
        prefix, basis = "資產負債表", "期間基礎未驗證"
    return f"{prefix}:{basis}:{field_name}"


def _parse_decimal(value: str) -> Decimal | None:
    normalized = value.replace(",", "").strip()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = "-" + normalized[1:-1].strip()
    if not NUMERIC_ITEM_RE.fullmatch(normalized):
        return None
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _normalise_target_period(period: str) -> tuple[str, date]:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", period.strip())
    if match is None:
        raise ValueError("period must be YYYY-Q1..Q4")
    year, quarter = int(match.group(1)), int(match.group(2))
    month = quarter * 3
    if month == 12:
        period_end = date(year, 12, 31)
    else:
        period_end = date(year, month + 1, 1).replace(day=1)
        period_end = date.fromordinal(period_end.toordinal() - 1)
    return f"{year:04d}-Q{quarter}", period_end


def _parse_aware_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone")
    return parsed.astimezone(timezone.utc)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_availability_rows(
    roots: Sequence[Path], period: str,
) -> tuple[list[dict[str, str]], tuple[Path, ...]]:
    rows: list[dict[str, str]] = []
    paths: list[Path] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for root in roots:
        root = Path(root)
        if root.name.lower() == "mapping.csv":
            candidates = [root]
        elif root.is_dir():
            candidates = sorted({root / "mapping.csv", *root.glob("*/mapping.csv")})
        else:
            candidates = []
        for path in candidates:
            if not path.exists():
                continue
            paths.append(path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                for raw in csv.DictReader(stream):
                    row = {str(key): str(value or "") for key, value in raw.items()}
                    if row.get("period", "").strip() != period:
                        continue
                    fingerprint = tuple(sorted(row.items()))
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    rows.append(row)
    return rows, tuple(paths)


def _write_records(path: Path, records: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)


def _write_mapping(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    fieldnames = (
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
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _record_malformed_row(
    diagnostics: BuildDiagnostics,
    summary: dict[str, Any],
    context: EndpointContext,
    row_number: int,
    reason: str,
) -> None:
    summary["rows_malformed"] += 1
    diagnostics.malformed_rows.append(
        {
            "file": context.filename,
            "row": str(row_number),
            "reason": reason,
        }
    )


def _statement_type_from_item_code(item_code: str) -> str:
    return item_code.split(":", 1)[0]


def _count_by(records: Iterable[Mapping[str, str]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record[field_name]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_statement_types(records: Iterable[Mapping[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        statement_type = _statement_type_from_item_code(record["item_code"])
        counts[statement_type] = counts.get(statement_type, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openapi-root", type=Path, required=True)
    parser.add_argument("--availability-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--observed-at", type=str)
    args = parser.parse_args(argv)
    observed_at = (
        None
        if args.observed_at is None
        else _parse_aware_datetime(args.observed_at, field_name="observed_at")
    )
    manifest = build_candidate(
        openapi_root=args.openapi_root,
        availability_roots=args.availability_root,
        output_root=args.output_root,
        period=args.period,
        observed_at=observed_at,
    )
    print(
        json.dumps(
            {
                "status": "candidate_ready",
                "output_root": str(args.output_root),
                "period": manifest["period"],
                "observed_at": manifest["observed_at"],
                "record_count": manifest["coverage"]["record_count"],
                "current_stock_count": manifest["coverage"]["current_stock_count"],
                "formal_pit_eligible": manifest["source_policy"]["formal_pit_eligible"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
