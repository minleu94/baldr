"""Governed company registry builder for companies.csv."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Iterable, Mapping, Sequence


COMPANY_REGISTRY_COLUMNS = (
    "industry_category",
    "stock_id",
    "stock_name",
    "type",
    "date",
    "download_time",
)
COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION = "company-registry-source-contract.v1"
COMPANY_REGISTRY_SOURCE_CONTRACT_ATTR = "company_registry_source_contract"
COMPANY_REGISTRY_SOURCE_MARKETS = ("twse", "tpex", "emerging")

INDUSTRY_CODE_TO_CATEGORY = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "20": "其他",
    "21": "化學生技醫療",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技",
    "34": "電子商務",
    "35": "綠能環保",
    "36": "數位雲端",
    "37": "運動休閒",
    "38": "居家生活",
    "80": "管理股票",
    "91": "存託憑證",
}


@dataclass(frozen=True)
class CompanyRegistryDiagnostic:
    code: str
    factor_name: str
    stock_code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "factor_name": self.factor_name,
            "stock_code": self.stock_code,
            "message": self.message,
        }


@dataclass(frozen=True)
class CompanyRegistryRow:
    industry_category: str
    stock_id: str
    stock_name: str
    type: str
    date: str
    download_time: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "industry_category": self.industry_category,
            "stock_id": self.stock_id,
            "stock_name": self.stock_name,
            "type": self.type,
            "date": self.date,
            "download_time": self.download_time,
        }


@dataclass(frozen=True)
class CompanyRegistryBuildResult:
    rows: tuple[CompanyRegistryRow, ...]
    diagnostics: tuple[CompanyRegistryDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def ready_for_apply(self) -> bool:
        return bool(self.rows) and not self.diagnostics

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Company Registry Build Result",
                "",
                f"- ready_for_apply: {str(self.ready_for_apply).lower()}",
                f"- row_count: {len(self.rows)}",
                f"- diagnostics: {len(self.diagnostics)}",
            ]
        )


def build_company_registry_rows(
    *,
    twse_rows: Iterable[Mapping[str, object]],
    tpex_rows: Iterable[Mapping[str, object]],
    emerging_rows: Iterable[Mapping[str, object]],
    download_time: str | None = None,
) -> CompanyRegistryBuildResult:
    download_time = download_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[CompanyRegistryRow] = []
    diagnostics: list[CompanyRegistryDiagnostic] = []

    for market, source_rows in (
        ("twse", twse_rows),
        ("tpex", tpex_rows),
        ("emerging", emerging_rows),
    ):
        for source_row in source_rows:
            record = _normalize_company_row(
                source_row,
                market=market,
                download_time=download_time,
            )
            if isinstance(record, CompanyRegistryDiagnostic):
                diagnostics.append(record)
            else:
                rows.append(record)

    unique_rows = _deduplicate_rows(rows)
    market_order = {"twse": 0, "tpex": 1, "emerging": 2}
    return CompanyRegistryBuildResult(
        rows=tuple(sorted(unique_rows, key=lambda row: (market_order[row.type], row.stock_id))),
        diagnostics=tuple(diagnostics),
    )


def write_company_registry_csv(
    output_file: Path,
    rows: Iterable[CompanyRegistryRow],
) -> None:
    output_file = Path(output_file)
    _atomic_replace_bytes(output_file, serialize_company_registry_csv(rows))


def serialize_company_registry_csv(rows: Iterable[CompanyRegistryRow]) -> bytes:
    """以舊六欄順序序列化 registry，不改既有 CSV wire。"""

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(COMPANY_REGISTRY_COLUMNS))
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_csv_row())
    return buffer.getvalue().encode("utf-8-sig")


def company_registry_source_contract_path(csv_path: Path) -> Path:
    """回傳與 companies CSV 配對的來源契約 sidecar 路徑。"""

    return Path(f"{Path(csv_path)}.source.json")


def build_company_registry_source_contract(
    *,
    csv_bytes: bytes,
    sources: Sequence[Mapping[str, object]],
    generated_at: datetime,
    artifact_name: str = "companies.csv",
) -> dict[str, object]:
    """綁定現況 companies CSV 與三個市場的原始來源讀取證據。

    此契約只說明目前分類快照及擷取來源，不代表歷史 PIT membership，
    也不把本機產生時間當成來源公告時間。
    """

    if not isinstance(csv_bytes, bytes):
        raise TypeError("csv_bytes 必須是 bytes")
    if not isinstance(artifact_name, str) or not artifact_name.strip():
        raise ValueError("artifact_name 不可為空")
    generated = _aware_utc_iso(generated_at, "generated_at")
    source_by_market: dict[str, dict[str, object]] = {}
    for source in sources:
        normalized = _normalize_company_source(source)
        market = str(normalized["market"])
        if market in source_by_market:
            raise ValueError(f"重複的 company registry market: {market}")
        source_by_market[market] = normalized
    if set(source_by_market) != set(COMPANY_REGISTRY_SOURCE_MARKETS):
        raise ValueError("sources 必須明確包含 twse、tpex、emerging 三個市場")

    ordered_sources = [
        source_by_market[market] for market in COMPANY_REGISTRY_SOURCE_MARKETS
    ]
    generated_time = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    for source in ordered_sources:
        available_at = source["available_at"]
        if available_at is not None and datetime.fromisoformat(
            str(available_at).replace("Z", "+00:00")
        ) > generated_time:
            raise ValueError("generated_at 不可早於來源 capture available_at")
    all_captured = all(source["status"] == "captured" for source in ordered_sources)
    warnings = [] if all_captured else ["company_registry_source_capture_unknown"]
    body: dict[str, object] = {
        "schema_version": COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
        "status": "captured" if all_captured else "unknown",
        "scope": "current_classification_only",
        "pit_eligible": False,
        "generated_at": generated,
        "artifact": {
            "name": artifact_name,
            "bytes": len(csv_bytes),
            "sha256": _sha256_prefixed(csv_bytes),
        },
        "sources": ordered_sources,
        "warnings": warnings,
    }
    body["source_contract_sha256"] = _sha256_prefixed(_canonical_json_bytes(body))
    return body


def serialize_company_registry_source_contract(
    contract: Mapping[str, object],
) -> bytes:
    """輸出穩定 UTF-8 JSON bytes，供 sidecar 原子替換。"""

    return (json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def write_company_registry_source_contract(
    csv_path: Path,
    contract: Mapping[str, object],
) -> Path:
    """以同目錄暫存檔替換 sidecar，避免留下半份 JSON。"""

    sidecar_path = company_registry_source_contract_path(csv_path)
    _atomic_replace_bytes(
        sidecar_path,
        serialize_company_registry_source_contract(contract),
    )
    return sidecar_path


def load_company_registry_source_contract(
    csv_path: Path,
    *,
    csv_bytes: bytes,
) -> dict[str, object]:
    """只在 sidecar 綁定本次同一份 CSV bytes 時回報 captured 狀態。

    舊 CSV、缺失 sidecar、格式錯誤或 bytes 不一致都保留 CSV reader 行為，
    但其來源身分退回 unknown/current-only。
    """

    csv_path = Path(csv_path)
    sidecar_path = company_registry_source_contract_path(csv_path)
    fallback = _unknown_company_registry_source_contract(
        csv_path=csv_path,
        csv_bytes=csv_bytes,
        warning="company_registry_source_manifest_missing",
    )
    try:
        parsed = json.loads(sidecar_path.read_bytes().decode("utf-8"))
    except FileNotFoundError:
        return fallback
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fallback["warnings"] = ["company_registry_source_manifest_invalid"]
        return fallback
    if not isinstance(parsed, dict) or not _valid_company_registry_source_contract(
        parsed,
        csv_path=csv_path,
        csv_bytes=csv_bytes,
    ):
        fallback["warnings"] = ["company_registry_source_manifest_mismatch"]
        return fallback
    return parsed


def _normalize_company_source(source: Mapping[str, object]) -> dict[str, object]:
    market = source.get("market")
    source_id = source.get("source_id")
    endpoint = source.get("endpoint")
    requested_url = source.get("requested_url")
    response_format = source.get("format")
    status = source.get("status")
    response_bytes = source.get("response_bytes")
    response_sha256 = source.get("response_sha256")
    available_at = source.get("available_at")
    source_date = source.get("source_date")
    if market not in COMPANY_REGISTRY_SOURCE_MARKETS:
        raise ValueError(f"不支援的 company registry market: {market!r}")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id 不可為空")
    if endpoint is not None and (not isinstance(endpoint, str) or not endpoint.strip()):
        raise ValueError("endpoint 必須是非空字串或 None")
    if requested_url is not None and (
        not isinstance(requested_url, str) or not requested_url.strip()
    ):
        raise ValueError("requested_url 必須是非空字串或 None")
    if response_format not in {"json", "csv", "local_json"}:
        raise ValueError("不支援的 company registry source format")
    if status not in {"captured", "unknown"}:
        raise ValueError("source status 必須是 captured 或 unknown")
    if isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < 0:
        raise ValueError("response_bytes 必須是非負整數")
    if not _is_sha256_prefixed(response_sha256):
        raise ValueError("response_sha256 格式無效")
    if available_at is not None and not isinstance(available_at, str):
        raise ValueError("available_at 必須是 ISO 時間或 None")
    if status == "captured":
        if (
            endpoint is None
            or requested_url is None
            or response_format not in {"json", "csv"}
        ):
            raise ValueError("captured source 必須有 endpoint 及實際 HTTP format")
        if not _validate_utc_iso(available_at, "available_at"):
            raise ValueError("captured source available_at 必須是 aware UTC")
    elif available_at is not None:
        raise ValueError("unknown source 不可宣稱 available_at")
    if source_date is not None and (
        not isinstance(source_date, str) or not source_date.strip()
    ):
        raise ValueError("source_date 必須是非空字串或 None")
    return {
        "market": market,
        "source_id": source_id,
        "endpoint": endpoint,
        "requested_url": requested_url,
        "format": response_format,
        "response_bytes": response_bytes,
        "response_sha256": response_sha256,
        "available_at": available_at,
        "status": status,
        "source_date": source_date,
        "publication_date": None,
    }


def _valid_company_registry_source_contract(
    contract: Mapping[str, object],
    *,
    csv_path: Path,
    csv_bytes: bytes,
) -> bool:
    if contract.get("schema_version") != COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION:
        return False
    if contract.get("scope") != "current_classification_only":
        return False
    if contract.get("pit_eligible") is not False:
        return False
    generated_at = contract.get("generated_at")
    if not _validate_utc_iso(generated_at, "generated_at"):
        return False
    artifact = contract.get("artifact")
    if not isinstance(artifact, dict):
        return False
    if artifact.get("name") != csv_path.name:
        return False
    artifact_bytes = artifact.get("bytes")
    if (
        isinstance(artifact_bytes, bool)
        or not isinstance(artifact_bytes, int)
        or artifact_bytes != len(csv_bytes)
    ):
        return False
    if artifact.get("sha256") != _sha256_prefixed(csv_bytes):
        return False
    sources = contract.get("sources")
    if not isinstance(sources, list) or len(sources) != len(COMPANY_REGISTRY_SOURCE_MARKETS):
        return False
    normalized: list[dict[str, object]] = []
    try:
        for source in sources:
            if not isinstance(source, dict):
                return False
            normalized.append(_normalize_company_source(source))
    except (TypeError, ValueError):
        return False
    if tuple(source["market"] for source in normalized) != COMPANY_REGISTRY_SOURCE_MARKETS:
        return False
    generated_time = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    if any(
        source["available_at"] is not None
        and datetime.fromisoformat(
            str(source["available_at"]).replace("Z", "+00:00")
        )
        > generated_time
        for source in normalized
    ):
        return False
    if any(source.get("publication_date") is not None for source in sources):
        return False
    all_captured = all(source["status"] == "captured" for source in normalized)
    expected_status = "captured" if all_captured else "unknown"
    if contract.get("status") != expected_status:
        return False
    warnings = contract.get("warnings")
    if not isinstance(warnings, list) or not all(
        isinstance(item, str) and item for item in warnings
    ):
        return False
    if (not all_captured) and "company_registry_source_capture_unknown" not in warnings:
        return False
    digest = contract.get("source_contract_sha256")
    if not _is_sha256_prefixed(digest):
        return False
    body = dict(contract)
    body.pop("source_contract_sha256", None)
    return digest == _sha256_prefixed(_canonical_json_bytes(body))


def _unknown_company_registry_source_contract(
    *,
    csv_path: Path,
    csv_bytes: bytes,
    warning: str,
) -> dict[str, object]:
    return {
        "schema_version": COMPANY_REGISTRY_SOURCE_CONTRACT_SCHEMA_VERSION,
        "status": "unknown",
        "scope": "current_classification_only",
        "pit_eligible": False,
        "generated_at": None,
        "artifact": {
            "name": csv_path.name,
            "bytes": len(csv_bytes),
            "sha256": _sha256_prefixed(csv_bytes),
        },
        "sources": [],
        "warnings": [warning],
        "source_contract_sha256": None,
    }


def _atomic_replace_bytes(output_file: Path, payload: bytes) -> None:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            dir=output_file.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_file)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _aware_utc_iso(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} 必須是帶時區的 datetime")
    return value.astimezone(timezone.utc).isoformat()


def _validate_utc_iso(value: object, field: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            return False
        _aware_utc_iso(parsed, field)
    except (TypeError, ValueError):
        return False
    return True


def _is_sha256_prefixed(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256_prefixed(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_company_row(
    source_row: Mapping[str, object],
    *,
    market: str,
    download_time: str,
) -> CompanyRegistryRow | CompanyRegistryDiagnostic:
    stock_code = _first(source_row, "公司代號", "SecuritiesCompanyCode")
    stock_name = _first(source_row, "公司簡稱", "CompanyAbbreviation", "公司名稱", "CompanyName")
    industry_code = _first(source_row, "產業別", "SecuritiesIndustryCode")
    source_date = _first(source_row, "出表日期", "Date")

    if not stock_code or not stock_name or not industry_code:
        return CompanyRegistryDiagnostic(
            code="company_registry.invalid_row",
            factor_name="company_registry",
            stock_code=stock_code,
            message="official company registry row is missing stock code, name, or industry code",
        )

    industry_category = INDUSTRY_CODE_TO_CATEGORY.get(industry_code)
    if industry_category is None:
        return CompanyRegistryDiagnostic(
            code="company_registry.unknown_industry_code",
            factor_name="company_registry",
            stock_code=stock_code,
            message=f"unknown official industry code: {industry_code}",
        )

    return CompanyRegistryRow(
        industry_category=industry_category,
        stock_id=stock_code,
        stock_name=stock_name,
        type=market,
        date=_normalize_source_date(source_date),
        download_time=download_time,
    )


def _deduplicate_rows(rows: Iterable[CompanyRegistryRow]) -> tuple[CompanyRegistryRow, ...]:
    selected: dict[tuple[str, str], CompanyRegistryRow] = {}
    for row in rows:
        key = (row.stock_id, row.type)
        if key not in selected or (row.date, row.download_time) > (
            selected[key].date,
            selected[key].download_time,
        ):
            selected[key] = row
    return tuple(selected.values())


def _first(source_row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = source_row.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _normalize_source_date(value: str) -> str:
    value = value.strip()
    if len(value) == 7 and value.isdigit():
        year = int(value[:3]) + 1911
        return f"{year:04d}-{value[3:5]}-{value[5:7]}"
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value
