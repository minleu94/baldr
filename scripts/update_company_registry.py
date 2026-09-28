from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests import RequestException

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_module.company_registry import (
    build_company_registry_source_contract,
    build_company_registry_rows,
    company_registry_source_contract_path,
    serialize_company_registry_csv,
    write_company_registry_csv,
    write_company_registry_source_contract,
)
from data_module.backup_retention import create_retained_backup
from data_module.config import TWStockConfig

TWSE_LISTED_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_OTC_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_EMERGING_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"
TWSE_LISTED_CSV_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv"
TPEX_OTC_CSV_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv"
TPEX_EMERGING_CSV_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_R.csv"

_SOURCE_CONFIG: dict[str, dict[str, str]] = {
    "twse_listed": {
        "market": "twse",
        "source_id": "official:twse:t187ap03_L",
        "json_url": TWSE_LISTED_URL,
        "csv_url": TWSE_LISTED_CSV_URL,
        "source_date_field": "出表日期",
    },
    "tpex_otc": {
        "market": "tpex",
        "source_id": "official:tpex:t187ap03_O",
        "json_url": TPEX_OTC_URL,
        "csv_url": TPEX_OTC_CSV_URL,
        "source_date_field": "Date",
    },
    "tpex_emerging": {
        "market": "emerging",
        "source_id": "official:tpex:t187ap03_R",
        "json_url": TPEX_EMERGING_URL,
        "csv_url": TPEX_EMERGING_CSV_URL,
        "source_date_field": "Date",
    },
}


@dataclass(frozen=True)
class _RegistrySourceCapture:
    rows: tuple[dict[str, Any], ...]
    market: str
    source_id: str
    endpoint: str | None
    requested_url: str | None
    response_format: str
    response_bytes: bytes
    available_at: datetime | None
    status: str
    source_date: str | None

    def to_contract_record(self) -> dict[str, object]:
        return {
            "market": self.market,
            "source_id": self.source_id,
            "endpoint": self.endpoint,
            "requested_url": self.requested_url,
            "format": self.response_format,
            "response_bytes": len(self.response_bytes),
            "response_sha256": f"sha256:{hashlib.sha256(self.response_bytes).hexdigest()}",
            "available_at": (
                self.available_at.astimezone(timezone.utc).isoformat()
                if self.available_at is not None
                else None
            ),
            "status": self.status,
            "source_date": self.source_date,
            "publication_date": None,
        }


def main(argv: list[str] | None = None, *, now_utc: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply official TWSE/TPEX companies.csv registry update."
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--source-json-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", choices=["apply-company-registry"], default=None)
    args = parser.parse_args(argv)

    config = TWStockConfig()
    output = args.output or (config.meta_data_dir / "companies.csv")
    backup_dir = args.backup_dir or config.backup_dir
    if now_utc is not None and (
        now_utc.tzinfo is None or now_utc.utcoffset() is None
    ):
        raise ValueError("now_utc 必須是帶時區的 datetime")
    try:
        captures = _load_source_captures(args.source_json_dir)
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "official_company_registry_source_unavailable",
                    "error": str(exc),
                    "output": str(output),
                    "writes_allowed": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1

    # 生成時間與 download_time 必須晚於最後一筆來源回應完成擷取。
    generated_at = now_utc if now_utc is not None else _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("now_utc 必須是帶時區的 datetime")
    generated_at = generated_at.astimezone(timezone.utc)
    if any(
        capture.available_at is not None and capture.available_at > generated_at
        for capture in captures.values()
    ):
        raise ValueError("now_utc 不可早於來源 capture available_at")
    download_time = generated_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    sources = {key: capture.rows for key, capture in captures.items()}
    result = build_company_registry_rows(
        twse_rows=sources["twse_listed"],
        tpex_rows=sources["tpex_otc"],
        emerging_rows=sources["tpex_emerging"],
        download_time=download_time,
    )

    if args.apply:
        if args.confirm != "apply-company-registry":
            print("Applying company registry requires --confirm apply-company-registry")
            return 2
        if not result.ready_for_apply:
            print(result.to_markdown())
            for diagnostic in result.diagnostics:
                print(f"- {diagnostic.code}: {diagnostic.stock_code} {diagnostic.message}".rstrip())
            return 1
        backup_file = _backup_existing(output, backup_dir)
        source_path = company_registry_source_contract_path(output)
        source_backup_file = _backup_existing(
            source_path,
            backup_dir,
            label="company_registry_source",
        )
        intended_csv_bytes = serialize_company_registry_csv(result.rows)
        write_company_registry_csv(output, result.rows)
        try:
            published_csv_bytes = output.read_bytes()
        except OSError as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "company_registry_csv_readback_failed",
                        "error": str(exc),
                        "output": str(output),
                        "source_manifest_path": str(source_path),
                        "csv_artifact_written": True,
                        "source_manifest_written": False,
                        "backup_file": str(backup_file) if backup_file else None,
                        "source_backup_file": (
                            str(source_backup_file) if source_backup_file else None
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        if published_csv_bytes != intended_csv_bytes:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "company_registry_csv_changed_before_readback",
                        "output": str(output),
                        "source_manifest_path": str(source_path),
                        "expected_csv_sha256": hashlib.sha256(intended_csv_bytes).hexdigest(),
                        "readback_csv_sha256": hashlib.sha256(published_csv_bytes).hexdigest(),
                        "csv_artifact_written": True,
                        "source_manifest_written": False,
                        "backup_file": str(backup_file) if backup_file else None,
                        "source_backup_file": (
                            str(source_backup_file) if source_backup_file else None
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        source_contract = build_company_registry_source_contract(
            csv_bytes=intended_csv_bytes,
            sources=[capture.to_contract_record() for capture in captures.values()],
            generated_at=generated_at,
            artifact_name=output.name,
        )
        try:
            sidecar_path = write_company_registry_source_contract(
                output,
                source_contract,
            )
        except OSError as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "company_registry_source_manifest_publication_failed",
                        "error": str(exc),
                        "output": str(output),
                        "source_manifest_path": str(source_path),
                        "source_manifest_readback": "unknown_until_matching_sidecar_is_written",
                        "csv_artifact_written": True,
                        "source_manifest_written": False,
                        "backup_file": str(backup_file) if backup_file else None,
                        "source_backup_file": (
                            str(source_backup_file) if source_backup_file else None
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        print(result.to_markdown())
        print("- applied: true")
        print(f"- output: {output}")
        print(f"- backup_file: {backup_file or 'none'}")
        print(f"- source_manifest: {sidecar_path}")
        print(f"- source_manifest_status: {source_contract['status']}")
        print(f"- source_contract_sha256: {source_contract['source_contract_sha256']}")
        return 0

    print(result.to_markdown())
    print(f"- output: {output}")
    for diagnostic in result.diagnostics:
        print(f"- {diagnostic.code}: {diagnostic.stock_code} {diagnostic.message}".rstrip())
    return 0 if result.ready_for_apply else 1


def _load_sources(source_json_dir: Path | None) -> dict[str, list[dict[str, Any]]]:
    if source_json_dir is not None:
        source_json_dir = Path(source_json_dir)
        return {
            "twse_listed": _load_json_file(source_json_dir / "twse_listed.json"),
            "tpex_otc": _load_json_file(source_json_dir / "tpex_otc.json"),
            "tpex_emerging": _load_json_file(source_json_dir / "tpex_emerging.json"),
        }
    return {
        "twse_listed": _fetch_official_registry(
            TWSE_LISTED_URL,
            TWSE_LISTED_CSV_URL,
        ),
        "tpex_otc": _fetch_official_registry(
            TPEX_OTC_URL,
            TPEX_OTC_CSV_URL,
        ),
        "tpex_emerging": _fetch_official_registry(
            TPEX_EMERGING_URL,
            TPEX_EMERGING_CSV_URL,
        ),
    }


def _fetch_official_registry(json_url: str, csv_url: str) -> list[dict[str, Any]]:
    try:
        return _fetch_json(json_url)
    except RuntimeError as json_error:
        try:
            return _fetch_csv(csv_url)
        except RuntimeError as csv_error:
            raise RuntimeError(
                "official registry source unavailable: "
                f"json={json_url}: {json_error}; "
                f"csv={csv_url}: {csv_error}"
            ) from csv_error


def _fetch_json(url: str) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"official registry response is not a list: {url}")
            return data
        except (RequestException, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch official registry after retries: {url}: {last_error}")


def _fetch_csv(url: str) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/csv,application/octet-stream",
                },
                timeout=60,
            )
            response.raise_for_status()
            text = response.content.decode("utf-8-sig")
            rows = [
                dict(row)
                for row in csv.DictReader(io.StringIO(text))
                if any(str(value or "").strip() for value in row.values())
            ]
            if not rows:
                raise ValueError("official registry CSV contains no rows")
            return rows
        except (RequestException, UnicodeDecodeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(
        f"failed to fetch official registry CSV after retries: {url}: {last_error}"
    )


def _load_source_captures(
    source_json_dir: Path | None,
) -> dict[str, _RegistrySourceCapture]:
    if source_json_dir is not None:
        source_json_dir = Path(source_json_dir)
        captures: dict[str, _RegistrySourceCapture] = {}
        for key, source in _SOURCE_CONFIG.items():
            path = source_json_dir / f"{key}.json"
            raw_bytes = path.read_bytes()
            rows = _decode_json_rows(raw_bytes, str(path))
            captures[key] = _RegistrySourceCapture(
                rows=tuple(rows),
                market=source["market"],
                source_id=source["source_id"],
                endpoint=None,
                requested_url=None,
                response_format="local_json",
                response_bytes=raw_bytes,
                available_at=None,
                status="unknown",
                source_date=_source_date(rows, source["source_date_field"]),
            )
        return captures

    captures = {}
    for key, source in _SOURCE_CONFIG.items():
        captures[key] = _fetch_official_registry_capture(
            key=key,
            json_url=source["json_url"],
            csv_url=source["csv_url"],
            market=source["market"],
            source_id=source["source_id"],
            source_date_field=source["source_date_field"],
        )
    return captures


def _fetch_official_registry_capture(
    *,
    key: str,
    json_url: str,
    csv_url: str,
    market: str,
    source_id: str,
    source_date_field: str,
) -> _RegistrySourceCapture:
    try:
        return _fetch_json_capture(
            url=json_url,
            market=market,
            source_id=source_id,
            source_date_field=source_date_field,
        )
    except RuntimeError as json_error:
        try:
            return _fetch_csv_capture(
                url=csv_url,
                market=market,
                source_id=source_id,
                source_date_field=source_date_field,
            )
        except RuntimeError as csv_error:
            raise RuntimeError(
                f"official registry source unavailable for {key}: "
                f"json={json_url}: {json_error}; csv={csv_url}: {csv_error}"
            ) from csv_error


def _fetch_json_capture(
    *,
    url: str,
    market: str,
    source_id: str,
    source_date_field: str,
) -> _RegistrySourceCapture:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=60,
            )
            response.raise_for_status()
            raw_bytes = response.content
            available_at = _utc_now()
            data = response.json()
            if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
                raise ValueError(f"official registry response is not a list of objects: {url}")
            rows = [dict(row) for row in data]
            return _RegistrySourceCapture(
                rows=tuple(rows),
                market=market,
                source_id=source_id,
                endpoint=_response_endpoint(response),
                requested_url=url,
                response_format="json",
                response_bytes=raw_bytes,
                available_at=available_at,
                status="captured",
                source_date=_source_date(rows, source_date_field),
            )
        except (RequestException, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch official registry JSON after retries: {url}: {last_error}")


def _fetch_csv_capture(
    *,
    url: str,
    market: str,
    source_id: str,
    source_date_field: str,
) -> _RegistrySourceCapture:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/csv,application/octet-stream",
                },
                timeout=60,
            )
            response.raise_for_status()
            raw_bytes = response.content
            available_at = _utc_now()
            text = raw_bytes.decode("utf-8-sig")
            rows = [
                dict(row)
                for row in csv.DictReader(io.StringIO(text))
                if any(str(value or "").strip() for value in row.values())
            ]
            if not rows:
                raise ValueError("official registry CSV contains no rows")
            return _RegistrySourceCapture(
                rows=tuple(rows),
                market=market,
                source_id=source_id,
                endpoint=_response_endpoint(response),
                requested_url=url,
                response_format="csv",
                response_bytes=raw_bytes,
                available_at=available_at,
                status="captured",
                source_date=_source_date(rows, source_date_field),
            )
        except (RequestException, UnicodeDecodeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch official registry CSV after retries: {url}: {last_error}")


def _response_endpoint(response: object) -> str:
    response_url = getattr(response, "url", None)
    if not isinstance(response_url, str) or not response_url.strip():
        raise ValueError("HTTP response 缺少有效的最終 response.url")
    return response_url


def _decode_json_rows(raw_bytes: bytes, source_path: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"source JSON is invalid: {source_path}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError(f"source JSON is not a list of objects: {source_path}")
    return [dict(row) for row in data]


def _source_date(rows: list[dict[str, Any]], field: str) -> str | None:
    values = {
        str(row[field]).strip()
        for row in rows
        if row.get(field) is not None and str(row[field]).strip()
    }
    return next(iter(values)) if len(values) == 1 else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"source json is not a list: {path}")
    return data


def _backup_existing(
    output: Path,
    backup_dir: Path,
    *,
    label: str = "company_registry",
) -> Path | None:
    output = Path(output)
    if not output.exists():
        return None
    return create_retained_backup(output, Path(backup_dir), label=label)


if __name__ == "__main__":
    raise SystemExit(main())
