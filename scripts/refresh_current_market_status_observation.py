"""將官方市場狀態來源擷取到明確指定的 QA／輸出根目錄。

此命令不使用設定中的正式資料根目錄，必須明確指定 ``--output-dir``。每次
執行都建立唯一且不可變的目錄，所有觀測均標記為僅供現況使用且不具 PIT 資格。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data_module.current_market_status_observation import (
    CurrentMarketStatusError,
    MarketStatusEvidence,
    build_snapshot,
    decode_official_rows,
    explicit_payload_source_dates,
    explicit_source_dates,
    extract_name,
    extract_resume_date,
    extract_row_dates,
    extract_symbol,
    extract_termination_date,
    parse_official_market_notice,
    sha256_bytes,
    source_dates_for_aliases,
    validate_official_notice_url,
)


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    url: str
    evidence_type: str
    market: str | None = None
    description: str = ""
    source_date_aliases: tuple[str, ...] = ()
    method: str = "GET"
    request_params: tuple[tuple[str, str], ...] = ()
    source_page_url: str | None = None


_DEFAULT_NOTICE_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "data_module"
    / "official_market_status_notice_sources.json"
)
_NOTICE_MANIFEST_SCHEMA = "official-market-status-notice-sources.v1"


def official_notice_source_spec(url: str) -> SourceSpec:
    """為一份明確的 TPEx 官方公文建立唯一來源列。"""
    validate_official_notice_url(url)
    source_key = sha256_bytes(url.encode("utf-8")).removeprefix("sha256:")[:16]
    return SourceSpec(
        source_id=f"tpex.official_notice.{source_key}",
        url=url,
        evidence_type="official_notice",
        market="tpex",
        description="由正文解析的 TPEx 官方停交易／終止公文",
    )


def twse_official_notice_source_spec(page_url: str) -> SourceSpec:
    """由固定形式的 TWSE 公告頁連結導出官方 detail API GET。"""
    parsed = urlsplit(page_url)
    token_match = re.fullmatch(r"([A-F0-9]{32})=", parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.twse.com.tw"
        or parsed.path != "/zh/announcement/announcement/detail.html"
        or token_match is None
        or parsed.fragment
    ):
        raise CurrentMarketStatusError("twse_announcement_page_url_not_allowlisted")
    token = token_match.group(1)
    source_key = sha256_bytes(page_url.encode("utf-8")).removeprefix("sha256:")[:16]
    return SourceSpec(
        source_id=f"twse.official_notice.{source_key}",
        url="https://www.twse.com.tw/rwd/zh/announcement/announcement_detail",
        evidence_type="official_notice",
        market="twse",
        description="TWSE official current announcement detail",
        method="GET",
        request_params=(("id", token), ("response", "json")),
        source_page_url=page_url,
    )


def load_official_notice_source_specs(
    manifest_path: Path | None = None,
) -> tuple[SourceSpec, ...]:
    """Load persistent official notice URLs; the parser derives status from raw text."""
    path = Path(manifest_path or _DEFAULT_NOTICE_MANIFEST_PATH).expanduser()
    if path.is_symlink() or not path.is_file():
        raise CurrentMarketStatusError("official_notice_manifest_missing_or_symlink")
    raw = path.read_bytes()
    if len(raw) > 64 * 1024:
        raise CurrentMarketStatusError("official_notice_manifest_exceeds_size_limit")
    try:
        payload = json.loads(raw.decode("utf-8-sig", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentMarketStatusError("official_notice_manifest_invalid_json") from error
    if (
        not isinstance(payload, Mapping)
        or set(payload) != {"schema_version", "sources"}
        or payload.get("schema_version") != _NOTICE_MANIFEST_SCHEMA
        or not isinstance(payload.get("sources"), list)
        or len(payload["sources"]) > 100
    ):
        raise CurrentMarketStatusError("official_notice_manifest_schema_invalid")

    specs: list[SourceSpec] = []
    seen_urls: set[str] = set()
    for row in payload["sources"]:
        if not isinstance(row, Mapping) or set(row) != {"notice_url"}:
            raise CurrentMarketStatusError("official_notice_manifest_source_invalid")
        notice_url = row.get("notice_url")
        if not isinstance(notice_url, str) or notice_url in seen_urls:
            raise CurrentMarketStatusError("official_notice_manifest_url_missing_or_duplicate")
        parsed = urlsplit(notice_url)
        if parsed.hostname == "www.twse.com.tw":
            spec = twse_official_notice_source_spec(notice_url)
        else:
            spec = official_notice_source_spec(notice_url)
        seen_urls.add(notice_url)
        specs.append(spec)
    return tuple(specs)


def source_specs(
    *,
    observed_on: datetime | None = None,
    notice_manifest_path: Path | None = None,
) -> tuple[SourceSpec, ...]:
    """回傳官方現況來源設定，不內嵌任何特定股票代碼。"""
    now = observed_on or datetime.now(timezone.utc)
    taipei_today = now.astimezone(ZoneInfo("Asia/Taipei")).date()
    # TWSE 日期區間報表需涵蓋足夠期間，以納入較早開始且仍有效的停牌事件。
    # 查詢日期不會被記為來源資料日期，也不會使本次擷取取得 PIT 證據資格。
    start = (taipei_today - timedelta(days=180)).strftime("%Y%m%d")
    end = taipei_today.strftime("%Y%m%d")
    regular_sources = (
        SourceSpec("twse.current_roster", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "current_roster", "twse", "TWSE listed company roster"),
        SourceSpec("tpex.current_otc_roster", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "current_roster", "tpex", "TPEx OTC company roster", ("Date",)),
        SourceSpec("tpex.current_emerging_roster", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R", "current_roster", "emerging", "TPEx emerging company roster", ("Date",)),
        SourceSpec("twse.suspension_events", f"https://www.twse.com.tw/exchangeReport/TWTAWU?response=json&startDate={start}&endDate={end}", "trading_restriction", "twse", "TWSE suspension / resumption events"),
        SourceSpec("twse.trading_method_changes", "https://openapi.twse.com.tw/v1/exchangeReport/TWT85U", "trading_restriction", "twse", "TWSE trading method changes"),
        SourceSpec("twse.disposition_current", "https://openapi.twse.com.tw/v1/announcement/punish", "trading_restriction", "twse", "TWSE disposition list"),
        SourceSpec("twse.terminated_listing", "https://www.twse.com.tw/company/suspendListingCsvAndHtml?lang=en&selectYear=&type=html", "terminated", "twse", "TWSE terminated-listing table"),
        SourceSpec("tpex.cmode_current", "https://www.tpex.org.tw/openapi/v1/tpex_cmode", "trading_restriction", "tpex", "TPEx changed-trading, call auction, management and suspension list", ("Date",)),
        SourceSpec("tpex.suspension_events", "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history", "trading_restriction", "tpex", "TPEx suspension / resumption history"),
        SourceSpec("tpex.disposition_current", "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information", "trading_restriction", "tpex", "TPEx disposition list"),
        SourceSpec(
            "tpex.terminated_listing",
            "https://www.tpex.org.tw/www/zh-tw/company/deListed",
            "terminated",
            "tpex",
            "TPEx terminated-listing official JSON report endpoint",
            method="POST",
            request_params=(
                ("code", ""),
                ("date", ""),
                ("reason", "-1"),
                ("response", "json"),
                ("paging-offset", "0"),
                ("paging-size", "10"),
            ),
        ),
    )
    return regular_sources + load_official_notice_source_specs(notice_manifest_path)


def _fetch_bytes(
    url: str,
    *,
    timeout: float,
    method: str = "GET",
    params: dict[str, str] | None = None,
) -> tuple[bytes, int, str, str, datetime, dict[str, str]]:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504, 520),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    headers = {
        "User-Agent": "technical-analysis-current-status-observer/1.0",
        "Accept": "application/json,text/html,*/*",
        # TPEx 公司名錄回應本文較大，使用 identity 編碼以避免正式擷取曾見的
        # 壓縮回應截斷問題。
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    last_error: Exception | None = None
    try:
        for attempt in range(3):
            try:
                response = session.request(
                    method.upper(),
                    url,
                    headers=headers,
                    params=params if method.upper() == "GET" else None,
                    data=params if method.upper() == "POST" else None,
                    timeout=(min(timeout, 15), timeout),
                )
                body = response.content
                content_length = response.headers.get("Content-Length")
                content_encoding = str(response.headers.get("Content-Encoding", "identity")).lower()
                if (
                    content_length
                    and content_encoding in {"", "identity"}
                    and content_length.isdigit()
                    and len(body) != int(content_length)
                ):
                    raise requests.exceptions.ChunkedEncodingError(
                        f"incomplete response body: {len(body)} of {content_length} bytes"
                    )
                captured_at = datetime.now(timezone.utc)
                selected_headers = {
                    key.lower(): str(value)
                    for key, value in response.headers.items()
                    if key.lower() in {"content-length", "content-encoding", "transfer-encoding", "etag", "last-modified"}
                }
                return (
                    body,
                    int(response.status_code),
                    str(response.headers.get("Content-Type", "")),
                    str(response.url),
                    captured_at,
                    selected_headers,
                )
            except (requests.RequestException, OSError) as error:
                last_error = error
                if attempt == 2:
                    break
                time.sleep(0.35 * (attempt + 1))
        assert last_error is not None
        raise last_error
    finally:
        session.close()


def _details(row: dict[str, object]) -> str | None:
    excluded = {"代號", "公司名稱", "證券名稱", "股票名稱", "name", "symbol"}
    parts = [f"{key}={str(value).strip()}" for key, value in row.items() if str(key).strip() not in excluded and str(value or "").strip()]
    return "; ".join(parts)[:1200] or None


def _yes(value: object) -> bool:
    return str(value or "").strip().upper() in {"Y", "YES", "TRUE", "1", "是", "Ｙ"}


def _restriction_types(spec: SourceSpec, row: dict[str, object]) -> list[tuple[str, str]]:
    if spec.source_id == "tpex.cmode_current":
        fields = {
            "suspensionoftrading": "trading_suspension",
            "alteredtrading": "altered_trading_method",
            "periodictrading": "periodic_call_auction",
            "managedstock": "managed_stock",
        }
        found: list[tuple[str, str]] = []
        source_day = any(
            str(key).strip().lower() == "date" and str(value or "").strip()
            for key, value in row.items()
        )
        state = "reported_on_source_date" if source_day else "source_reported_state_date_unknown"
        for key, value in row.items():
            restriction_type = fields.get(str(key).strip().lower())
            if restriction_type and _yes(value):
                found.append((restriction_type, state))
        return found
    typed_by_source = {
        "twse.suspension_events": "trading_suspension_event",
        "twse.trading_method_changes": "trading_method_change",
        "twse.disposition_current": "disposition",
        "tpex.suspension_events": "trading_suspension_event",
        "tpex.disposition_current": "disposition",
    }
    restriction = typed_by_source.get(spec.source_id)
    if restriction == "trading_suspension_event":
        if extract_resume_date(row) is not None:
            return [(restriction, "resumed_on_source_date")]
        return [(restriction, "resumption_date_not_reported")]
    return [(restriction, "source_reported_current_or_recent_feed")] if restriction else []


def capture_sources(
    *,
    output_dir: Path,
    timeout: float = 30.0,
    specs: tuple[SourceSpec, ...] | None = None,
    fetcher: Any = _fetch_bytes,
) -> tuple[dict[str, object], Path]:
    """擷取來源、保存完整回應本文，並建立單一快照。"""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:10]
    # 深層 Windows 暫存根下也要能落盤；source_id 與 SHA 仍記錄於 snapshot/manifest。
    run_dir = output_dir / f"cms_{run_id}"
    run_dir.mkdir(exist_ok=False)
    raw_dir = run_dir / "raw"
    raw_dir.mkdir()

    observed_at = datetime.now(timezone.utc)
    captures: list[dict[str, object]] = []
    evidence: list[MarketStatusEvidence] = []
    any_failed = False
    for source_index, spec in enumerate(specs or source_specs(), start=1):
        record: dict[str, object] = {
            "source_id": spec.source_id,
            "description": spec.description,
            "requested_url": spec.url,
            "request_method": spec.method.upper(),
            "request_params": dict(spec.request_params),
            "market": spec.market,
            "scope": "current_observation",
            "pit_eligible": False,
        }
        if spec.source_page_url:
            record["source_page_url"] = spec.source_page_url
        try:
            body, status_code, content_type, final_url, captured_at, response_headers = fetcher(
                spec.url,
                timeout=timeout,
                method=spec.method,
                params=dict(spec.request_params),
            )
            digest = sha256_bytes(body)
            raw_path = raw_dir / f"s{source_index:04d}.bin"
            with raw_path.open("xb") as stream:
                stream.write(body)
            record.update(
                {
                    "status": "captured" if 200 <= status_code < 300 else "http_error",
                    "http_status": status_code,
                    "content_type": content_type,
                    "response_headers": response_headers,
                    "final_url": final_url,
                    "captured_at": captured_at.isoformat(),
                    "raw_path": str(raw_path),
                    "raw_sha256": digest,
                    "raw_bytes": len(body),
                }
            )
            if not 200 <= status_code < 300:
                record["parse_status"] = "not_attempted_http_error"
                any_failed = True
                captures.append(record)
                continue
            try:
                if spec.evidence_type == "official_notice":
                    statements = parse_official_market_notice(
                        body,
                        source_url=final_url,
                        observed_at=captured_at,
                    )
                    record["parse_status"] = "parsed"
                    record["row_count"] = len(statements)
                    record["source_data_dates"] = []
                    record["notice_publication_dates"] = sorted(
                        {statement.published_date.isoformat() for statement in statements}
                    )
                    record["notice_references"] = sorted(
                        {statement.notice_reference for statement in statements}
                    )
                    for statement in statements:
                        is_suspension = statement.statement_type == "trading_suspension"
                        evidence.append(
                            MarketStatusEvidence(
                                symbol=statement.symbol,
                                source_id=spec.source_id,
                                evidence_type=("trading_restriction" if is_suspension else "terminated"),
                                observed_at=captured_at.isoformat(),
                                raw_sha256=digest,
                                source_url=final_url,
                                published_date=statement.published_date.isoformat(),
                                notice_reference=statement.notice_reference,
                                effective_from=statement.effective_date.isoformat(),
                                effective_to=(
                                    statement.effective_to.isoformat()
                                    if statement.effective_to
                                    else None
                                ),
                                resumed_on=(
                                    statement.resumed_on.isoformat()
                                    if statement.resumed_on
                                    else None
                                ),
                                market=statement.market,
                                name=statement.name,
                                details=statement.details,
                                restriction_type="trading_suspension_notice" if is_suspension else None,
                                restriction_state="explicit_official_notice" if is_suspension else None,
                            )
                        )
                    captures.append(record)
                    continue
                rows = decode_official_rows(body, content_type)
                source_dates = sorted(set(
                    explicit_source_dates(rows)
                    + explicit_payload_source_dates(body)
                    + source_dates_for_aliases(rows, spec.source_date_aliases)
                ))
                record["parse_status"] = "parsed"
                record["row_count"] = len(rows)
                record["source_data_dates"] = source_dates
                record["query_scope"] = "official_current_or_recent_feed"
                for row in rows:
                    symbol = extract_symbol(row)
                    if symbol is None:
                        continue
                    start_date, end_date = extract_row_dates(row)
                    resumed_on = extract_resume_date(row)
                    if spec.evidence_type == "terminated":
                        effective_date = extract_termination_date(row)
                        # 保留官方明確標示的終止日期作為事件證據；讀取端不授予歷史 PIT。
                        effective_from = effective_date.isoformat() if effective_date else None
                    else:
                        effective_from = start_date.isoformat() if start_date else None
                    row_dates = sorted(set(
                        explicit_source_dates([row])
                        + explicit_payload_source_dates(body)
                        + source_dates_for_aliases([row], spec.source_date_aliases)
                    ))
                    if spec.source_id == "tpex.cmode_current" and row_dates:
                        # TPEx 每日狀態列可證明其 Date 所指日期的官方市場狀態，
                        # 但不回填可得時間，也不虛構生效區間。
                        evidence.append(
                            MarketStatusEvidence(
                                symbol=symbol,
                                source_id=spec.source_id,
                                evidence_type="current_market_status_report",
                                observed_at=captured_at.isoformat(),
                                raw_sha256=digest,
                                source_url=final_url,
                                source_data_dates=tuple(row_dates),
                                market=spec.market,
                                name=extract_name(row),
                                details=_details(row),
                            )
                        )
                    if spec.evidence_type == "trading_restriction":
                        typed_restrictions = _restriction_types(spec, row)
                        for restriction_type, restriction_state in typed_restrictions:
                            evidence.append(
                                MarketStatusEvidence(
                                    symbol=symbol,
                                    source_id=spec.source_id,
                                    evidence_type=spec.evidence_type,
                                    observed_at=captured_at.isoformat(),
                                    raw_sha256=digest,
                                    source_url=final_url,
                                    source_data_dates=tuple(row_dates),
                                    effective_from=effective_from,
                                    effective_to=end_date.isoformat() if end_date else None,
                                    resumed_on=resumed_on.isoformat() if resumed_on else None,
                                    market=spec.market,
                                    name=extract_name(row),
                                    details=_details(row),
                                    restriction_type=restriction_type,
                                    restriction_state=restriction_state,
                                )
                            )
                    else:
                        evidence.append(
                            MarketStatusEvidence(
                                symbol=symbol,
                                source_id=spec.source_id,
                                evidence_type=spec.evidence_type,
                                observed_at=captured_at.isoformat(),
                                raw_sha256=digest,
                                source_url=final_url,
                                source_data_dates=tuple(row_dates),
                                effective_from=effective_from,
                                effective_to=end_date.isoformat() if end_date else None,
                                resumed_on=resumed_on.isoformat() if resumed_on else None,
                                market=spec.market,
                                name=extract_name(row),
                                details=_details(row),
                            )
                        )
            except (CurrentMarketStatusError, UnicodeError, json.JSONDecodeError) as error:
                record["parse_status"] = "unrecognized_schema"
                record["parse_error"] = str(error)
                any_failed = True
        except Exception as error:  # keep independent sources available if one feed fails
            record["status"] = "capture_error"
            record["captured_at"] = datetime.now(timezone.utc).isoformat()
            record["error"] = f"{type(error).__name__}: {error}"
            any_failed = True
        captures.append(record)

    snapshot = build_snapshot(
        observed_at=max([observed_at] + [
            datetime.fromisoformat(str(item["captured_at"]))
            for item in captures if item.get("captured_at")
        ]),
        source_captures=captures,
        evidence=evidence,
    )
    snapshot["run_id"] = run_id
    snapshot["source_count"] = len(captures)
    snapshot["successful_source_count"] = sum(
        item.get("status") == "captured" and item.get("parse_status") == "parsed"
        for item in captures
    )
    snapshot["partial_failure"] = any_failed
    snapshot_path = run_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "current-market-status-capture-manifest.v1",
                "run_id": run_id,
                "snapshot_path": str(snapshot_path),
                "snapshot_sha256": sha256_bytes(snapshot_path.read_bytes()),
                "raw_sources": [
                    {key: capture.get(key) for key in ("source_id", "raw_path", "raw_sha256", "captured_at", "status", "parse_status")}
                    for capture in captures
                ],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    manifest_sha = sha256_bytes(manifest_path.read_bytes())
    pointer = {
        "schema_version": "current-market-status-pointer.v1",
        "scope": "current_only",
        "pit_eligible": False,
        "run_id": run_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": (Path(run_dir.name) / "snapshot.json").as_posix(),
        "snapshot_sha256": sha256_bytes(snapshot_path.read_bytes()),
        "manifest_path": (Path(run_dir.name) / "manifest.json").as_posix(),
        "manifest_sha256": manifest_sha,
        "source_count": snapshot["source_count"],
        "successful_source_count": snapshot["successful_source_count"],
        "partial_failure": snapshot["partial_failure"],
    }
    pointer_path = output_dir / "current_market_status_pointer.json"
    temporary_pointer = output_dir / f".p.{run_id}.tmp"
    with temporary_pointer.open("x", encoding="utf-8") as stream:
        json.dump(pointer, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # 指標是唯一可變更的發布物件；其所指向的 run 目錄不可覆寫，且雜湊會
    # 綁定同一 run 的快照與 manifest。
    os.replace(temporary_pointer, pointer_path)
    return snapshot, run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="Explicit output root; no formal data-root default")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--notice-manifest",
        type=Path,
        help="Persistent allowlisted official notice URL manifest; defaults to the repository source list.",
    )
    parser.add_argument(
        "--notice-url",
        action="append",
        default=[],
        help="額外擷取 TPEx 官方公文原件；可重複指定，聲明類型由公告正文辨識",
    )
    parser.add_argument(
        "--twse-notice-url",
        action="append",
        default=[],
        help="TWSE 公告詳情頁 URL；使用官方公告 API 讀取原文，限正式 TWSE detail URL。",
    )
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    try:
        notice_specs = tuple(official_notice_source_spec(url) for url in args.notice_url)
        notice_specs += tuple(
            twse_official_notice_source_spec(url) for url in args.twse_notice_url
        )
    except CurrentMarketStatusError as error:
        parser.error(str(error))
    configured_specs = source_specs(notice_manifest_path=args.notice_manifest)
    configured_source_ids = {spec.source_id for spec in configured_specs}
    supplemental_specs = tuple(
        spec for spec in notice_specs if spec.source_id not in configured_source_ids
    )
    snapshot, run_dir = capture_sources(
        output_dir=args.output_dir,
        timeout=args.timeout_seconds,
        specs=configured_specs + supplemental_specs,
    )
    securities = snapshot.get("securities")
    security_count = len(securities) if isinstance(securities, list) else 0
    print(json.dumps({
        "status": (
            "partial_failure" if snapshot["partial_failure"]
            else "current_market_status_captured"
        ),
        "run_id": snapshot["run_id"],
        "run_dir": str(run_dir),
        "snapshot_path": str(run_dir / "snapshot.json"),
        "pointer_path": str(Path(args.output_dir).resolve() / "current_market_status_pointer.json"),
        "source_count": snapshot["source_count"],
        "successful_source_count": snapshot["successful_source_count"],
        "security_count": security_count,
        "scope": snapshot["scope"],
        "pit_eligible": snapshot["pit_eligible"],
        "partial_failure": snapshot["partial_failure"],
    }, ensure_ascii=False))
    return 2 if snapshot["partial_failure"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
