"""離線稽核政府開放資料公司目錄候選；不下載、不寫入、不判定歷史母體。"""

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
from typing import Any, Mapping


MANIFEST_NAME = "capture_manifest.json"
MANIFEST_SCHEMA = "baldr.open_data_issuer_directory_candidate.v1"
AUDIT_SCHEMA = "baldr.open_data_issuer_directory_candidate_audit.v1"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RESOURCE_BYTES = 16 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
_EXPECTED_SOURCES = {"18419": "TWSE", "25036": "TPEx"}


class IssuerDirectoryCandidateAuditError(ValueError):
    """公司目錄候選根目錄或 manifest 不足以建立唯讀稽核。"""


@dataclass(frozen=True)
class IssuerDirectoryEntry:
    market: str
    code: str
    name: str | None
    industry_code: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "market": self.market,
            "code": self.code,
            "name": self.name,
            "industry_code": self.industry_code,
        }


@dataclass(frozen=True)
class IssuerDirectoryCandidateAudit:
    resources: tuple[Mapping[str, Any], ...]
    entries: tuple[IssuerDirectoryEntry, ...]
    directory_dates_by_market: Mapping[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AUDIT_SCHEMA,
            "candidate_only": True,
            "formal_db_write": False,
            "source_acceptance": False,
            "gate_credit": False,
            "downstream_eligibility": "none",
            "resources": [dict(item) for item in self.resources],
            "entries": [item.to_dict() for item in self.entries],
            "directory_dates_by_market": {
                market: list(dates)
                for market, dates in self.directory_dates_by_market.items()
            },
            "limitations": [
                "名錄只代表候選檔所標的當前觀測日，不是任一歷史財報期的 issuer 分母。",
                "名錄與季報候選的差異只描述本次選取檔案；不推定漏報、來源完整或 issuer 義務。",
                "此稽核不證明逐筆 available-at、PIT、授權、金額單位、報表基準或來源接受。",
            ],
        }


def audit_issuer_directory_candidate_root(
    candidate_root: Path,
) -> IssuerDirectoryCandidateAudit:
    """驗證呼叫者明選的 TWSE／TPEx 目錄候選 manifest、SHA 與 CSV。"""

    root = Path(candidate_root).expanduser().absolute()
    try:
        root_stat = root.stat()
    except OSError as exc:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_root_unavailable") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_point(root):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_root_not_directory")

    manifest_path = root / MANIFEST_NAME
    if _is_reparse_point(manifest_path):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_reparse_point")
    try:
        if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_missing_or_too_large")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_invalid") from exc

    _validate_manifest(manifest)
    resources: list[Mapping[str, Any]] = []
    entries: list[IssuerDirectoryEntry] = []
    dates: dict[str, set[str]] = {market: set() for market in _EXPECTED_SOURCES.values()}
    seen_markets: set[str] = set()
    for source in manifest["sources"]:
        normalized = _normalize_source(source)
        dataset_id = normalized["dataset_id"]
        market = _EXPECTED_SOURCES[dataset_id]
        if market in seen_markets:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_duplicate_market")
        seen_markets.add(market)
        resource_entries, output_dates, resource = _audit_resource(root, normalized)
        entries.extend(resource_entries)
        dates[market].update(output_dates)
        resources.append(resource)
    if seen_markets != set(_EXPECTED_SOURCES.values()):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_denominator_mismatch")
    return IssuerDirectoryCandidateAudit(
        resources=tuple(resources),
        entries=tuple(sorted(entries, key=lambda item: (item.market, item.code))),
        directory_dates_by_market={
            market: tuple(sorted(values)) for market, values in dates.items()
        },
    )


def build_quarterly_candidate_directory_comparison(
    *, quarterly_audit: Mapping[str, Any], directory_audit: Mapping[str, Any]
) -> dict[str, Any]:
    """比較目前選取的季報候選與目錄候選，不把差異命名為漏報。"""

    _require_candidate_boundary(quarterly_audit, "quarterly candidate")
    _require_candidate_boundary(directory_audit, "issuer directory candidate")
    if quarterly_audit.get("schema_version") != "baldr.open_data_quarterly_candidate_audit.v1":
        raise IssuerDirectoryCandidateAuditError("quarterly_candidate_schema_unsupported")
    if directory_audit.get("schema_version") != AUDIT_SCHEMA:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_schema_unsupported")
    resources = quarterly_audit.get("resources")
    directory_entries = directory_audit.get("entries")
    directory_dates = directory_audit.get("directory_dates_by_market")
    if not isinstance(resources, list) or not isinstance(directory_entries, list) or not isinstance(directory_dates, Mapping):
        raise IssuerDirectoryCandidateAuditError("candidate_comparison_payload_invalid")

    quarterly_codes: dict[str, set[str]] = {market: set() for market in _EXPECTED_SOURCES.values()}
    periods: dict[str, set[str]] = {market: set() for market in _EXPECTED_SOURCES.values()}
    output_dates: dict[str, set[str]] = {market: set() for market in _EXPECTED_SOURCES.values()}
    all_profiles_complete = True
    for resource in resources:
        if not isinstance(resource, Mapping):
            raise IssuerDirectoryCandidateAuditError("quarterly_candidate_resource_invalid")
        market = resource.get("market")
        if market not in quarterly_codes:
            continue
        if resource.get("state") != "available":
            all_profiles_complete = False
            continue
        if resource.get("row_profiles_complete") is not True:
            all_profiles_complete = False
            continue
        profiles = resource.get("row_profiles")
        if not isinstance(profiles, list):
            all_profiles_complete = False
            continue
        for profile in profiles:
            if not isinstance(profile, Mapping):
                raise IssuerDirectoryCandidateAuditError("quarterly_candidate_profile_invalid")
            code = _normalized_code(profile.get("issuer_code"))
            if code is None:
                raise IssuerDirectoryCandidateAuditError("quarterly_candidate_code_missing")
            quarterly_codes[market].add(code)
            period = profile.get("fiscal_period")
            if isinstance(period, str) and period.strip():
                periods[market].add(period.strip())
            profile_dates = profile.get("output_dates")
            if isinstance(profile_dates, list):
                output_dates[market].update(
                    item.strip() for item in profile_dates if isinstance(item, str) and item.strip()
                )

    directory_by_market: dict[str, dict[str, Mapping[str, Any]]] = {
        market: {} for market in _EXPECTED_SOURCES.values()
    }
    for entry in directory_entries:
        if not isinstance(entry, Mapping):
            raise IssuerDirectoryCandidateAuditError("directory_candidate_entry_invalid")
        market = entry.get("market")
        code = _normalized_code(entry.get("code"))
        if market not in directory_by_market or code is None:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_entry_invalid")
        if code in directory_by_market[market]:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_duplicate_code")
        directory_by_market[market][code] = entry

    rows: list[dict[str, Any]] = []
    for market in _EXPECTED_SOURCES.values():
        roster = directory_by_market[market]
        candidate = quarterly_codes[market]
        for code in sorted(set(roster) | candidate):
            directory_entry = roster.get(code)
            in_candidate = code in candidate
            rows.append(
                {
                    "market": market,
                    "code": code,
                    "name": directory_entry.get("name") if directory_entry else None,
                    "industry_code": directory_entry.get("industry_code") if directory_entry else None,
                    "directory_observed": directory_entry is not None,
                    "quarterly_candidate_observed": in_candidate,
                    "comparison_state": (
                        "in_both"
                        if directory_entry is not None and in_candidate
                        else "directory_only_in_current_comparison"
                        if directory_entry is not None
                        else "quarterly_candidate_without_directory_match"
                    ),
                }
            )

    return {
        "schema_version": "baldr.quarterly_candidate_directory_comparison.v1",
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "comparison_scope": "currently_selected_quarterly_candidate_root_only",
        "complete": all_profiles_complete,
        "directory_dates_by_market": {
            market: list(directory_dates.get(market, ())) for market in _EXPECTED_SOURCES.values()
        },
        "quarterly_periods_by_market": {
            market: sorted(values) for market, values in periods.items()
        },
        "quarterly_output_dates_by_market": {
            market: sorted(values) for market, values in output_dates.items()
        },
        "summary_by_market": {
            market: {
                "directory_issuer_count": len(directory_by_market[market]),
                "quarterly_candidate_issuer_count": len(quarterly_codes[market]),
                "in_both_count": len(set(directory_by_market[market]) & quarterly_codes[market]),
                "directory_only_in_current_comparison_count": len(
                    set(directory_by_market[market]) - quarterly_codes[market]
                ),
                "quarterly_candidate_without_directory_match_count": len(
                    quarterly_codes[market] - set(directory_by_market[market])
                ),
            }
            for market in _EXPECTED_SOURCES.values()
        },
        "rows": rows,
        "limitations": [
            "名錄與季報候選的出表日期可能不同；這是近時點檔案對照，不是同日歷史母體。",
            "季報只比較目前選取的候選目錄；未選取的其他候選資源不納入。",
            "目錄有但目前候選未見，不代表未申報、漏抓或應申報；可能有期別、產業、身分或時點原因。",
            "本對照不推定 coverage、available-at、PIT、授權、來源接受、Gate credit 或 ML 資格。",
        ],
    }


def _validate_manifest(payload: Any) -> None:
    if not isinstance(payload, Mapping) or payload.get("schema") != MANIFEST_SCHEMA:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_schema_unsupported")
    expected = {
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_boundary_mismatch")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != len(_EXPECTED_SOURCES):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_source_count_invalid")
    ids: list[str] = []
    for source in sources:
        if not isinstance(source, Mapping) or not isinstance(source.get("source"), Mapping):
            raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_source_invalid")
        metadata = source["source"]
        dataset_id = metadata.get("dataset_id")
        if not isinstance(dataset_id, str) or dataset_id not in _EXPECTED_SOURCES:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_unknown_dataset")
        if metadata.get("market") != _EXPECTED_SOURCES[dataset_id]:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_market_mismatch")
        ids.append(dataset_id)
    if set(ids) != set(_EXPECTED_SOURCES) or len(set(ids)) != len(ids):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_denominator_mismatch")


def _normalize_source(source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = source.get("source")
    if not isinstance(metadata, Mapping):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_manifest_source_invalid")
    dataset_id = metadata.get("dataset_id")
    assert isinstance(dataset_id, str)
    market = metadata.get("market")
    artifact = source.get("artifact")
    expected_values = {
        "method": "GET",
        "redirects_followed": False,
        "http_status": 200,
        "truncated": False,
        "status": "captured",
        "readback_matches": True,
    }
    if market != _EXPECTED_SOURCES[dataset_id] or not isinstance(artifact, str) or not artifact:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_metadata_invalid")
    for key, expected in expected_values.items():
        if source.get(key) != expected:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_source_receipt_invalid")
    for key in ("body_sha256", "readback_sha256"):
        digest = source.get(key)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise IssuerDirectoryCandidateAuditError("directory_candidate_source_hash_invalid")
    if source["body_sha256"].lower() != source["readback_sha256"].lower():
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_hash_mismatch")
    for key in ("body_bytes", "max_body_bytes"):
        value = source.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_source_size_invalid")
    readback_bytes = source.get("readback_bytes", source["body_bytes"])
    if (
        isinstance(readback_bytes, bool)
        or not isinstance(readback_bytes, int)
        or readback_bytes < 0
    ):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_size_invalid")
    if source["max_body_bytes"] <= 0 or source["max_body_bytes"] > MAX_RESOURCE_BYTES:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_size_invalid")
    if source["body_bytes"] != readback_bytes:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_size_invalid")
    if source["body_bytes"] > source["max_body_bytes"]:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_source_size_invalid")
    csv_profile = source.get("csv_profile")
    if not isinstance(csv_profile, Mapping):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_profile_missing")
    if (csv_profile.get("code_column"), csv_profile.get("industry_column")) != ("公司代號", "產業別"):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_profile_invalid")
    for key in ("row_count", "unique_codes"):
        value = csv_profile.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_profile_invalid")
    date_distribution = csv_profile.get("output_date_distribution")
    if not isinstance(date_distribution, Mapping) or any(
        not isinstance(key, str)
        or isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for key, value in date_distribution.items()
    ):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_profile_invalid")
    return {
        "dataset_id": dataset_id,
        "market": market,
        "artifact": artifact,
        "body_bytes": source["body_bytes"],
        "readback_bytes": readback_bytes,
        "max_body_bytes": source["max_body_bytes"],
        "body_sha256": source["body_sha256"].lower(),
        "readback_sha256": source["readback_sha256"].lower(),
        "expected_row_count": csv_profile.get("row_count"),
        "expected_unique_codes": csv_profile.get("unique_codes"),
        "output_dates": csv_profile.get("output_date_distribution"),
    }


def _audit_resource(
    root: Path, source: Mapping[str, Any]
) -> tuple[list[IssuerDirectoryEntry], set[str], dict[str, Any]]:
    artifact = source["artifact"]
    if Path(artifact).name != artifact or artifact in {".", ".."}:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_path_invalid")
    path = root / artifact
    if _is_reparse_point(path):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_reparse_point")
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_missing") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_not_file")
    if file_stat.st_size > source["max_body_bytes"] or file_stat.st_size > MAX_RESOURCE_BYTES:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_too_large")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if (
        len(raw) != source["body_bytes"]
        or len(raw) != source["readback_bytes"]
        or digest != source["body_sha256"]
        or digest != source["readback_sha256"]
    ):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_artifact_hash_mismatch")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        headers = reader.fieldnames or []
        if not {"公司代號", "公司名稱", "產業別", "出表日期"}.issubset(headers):
            raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_schema_invalid")
        entries: list[IssuerDirectoryEntry] = []
        codes: set[str] = set()
        dates: set[str] = set()
        date_counts: Counter[str] = Counter()
        for row in reader:
            code = _normalized_code(row.get("公司代號"))
            date = (row.get("出表日期") or "").strip()
            if code is None or not date:
                raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_row_invalid")
            if code in codes:
                raise IssuerDirectoryCandidateAuditError("directory_candidate_duplicate_code")
            codes.add(code)
            dates.add(date)
            date_counts[date] += 1
            entries.append(
                IssuerDirectoryEntry(
                    market=source["market"],
                    code=code,
                    name=_optional_text(row.get("公司名稱")),
                    industry_code=_optional_text(row.get("產業別")),
                )
            )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_parse_failed") from exc
    if len(entries) != source["expected_row_count"] or len(codes) != source["expected_unique_codes"]:
        raise IssuerDirectoryCandidateAuditError("directory_candidate_csv_count_mismatch")
    expected_dates = source["output_dates"]
    if not isinstance(expected_dates, Mapping) or dict(date_counts) != dict(expected_dates):
        raise IssuerDirectoryCandidateAuditError("directory_candidate_output_date_mismatch")
    return entries, dates, {
        "dataset_id": source["dataset_id"],
        "market": source["market"],
        "artifact": artifact,
        "row_count": len(entries),
        "unique_code_count": len(codes),
        "output_dates": sorted(dates),
        "sha256": digest,
        "state": "verified_candidate",
    }


def _require_candidate_boundary(payload: Mapping[str, Any], label: str) -> None:
    expected = {
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
    }
    if not isinstance(payload, Mapping):
        raise IssuerDirectoryCandidateAuditError(f"{label} payload invalid")
    for key, value in expected.items():
        if payload.get(key) != value:
            raise IssuerDirectoryCandidateAuditError(f"{label} boundary mismatch")


def _normalized_code(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if text else None


def _optional_text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return path.is_symlink()
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_attribute)
