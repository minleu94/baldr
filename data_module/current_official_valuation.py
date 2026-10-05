"""Current-only official valuation capture and read provider.

The collector stores exact TWSE/TPEx response bodies and append-only receipts
under the canonical output root. The reader selects the exact expected current
market-session date when supplied; it never writes or reads formal PIT tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


SCHEMA_VERSION = "official-current-valuation-capture.v1"
PARSER_VERSION = "official-current-valuation-parser.v1"
CAPTURE_RELATIVE_ROOT = Path("current_valuation")
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TPEX_URL = "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php"
TPEX_PARAMS = {"l": "zh-tw", "o": "htm", "s": "0"}
TPEX_OPENAPI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
TPEX_OPENAPI_SPEC_URL = "https://www.tpex.org.tw/openapi/swagger.json"
METRIC_FIELDS = {
    "pe": ("PEratio", "ratio"),
    "dividend_yield": ("DividendYield", "percent"),
    "pb": ("PBratio", "ratio"),
}
_STOCK_CODE = re.compile(r"\d{4,6}")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_MISSING = frozenset({"", "--", "—", "－", "N/A", "NA", "null", "None", "不適用"})
_TAIPEI = ZoneInfo("Asia/Taipei")
_SENSITIVE_HEADERS = frozenset({"set-cookie", "cookie", "authorization", "proxy-authorization"})


class CurrentOfficialValuationError(ValueError):
    """Official current valuation data is malformed or cannot be verified."""


@dataclass(frozen=True)
class ParsedValuationRow:
    stock_code: str
    values: Mapping[str, Decimal | None]


@dataclass(frozen=True)
class ParsedValuationSnapshot:
    market: str
    source_id: str
    parser_id: str
    source_date: date
    rows: tuple[ParsedValuationRow, ...]
    source_row_count: int
    duplicate_row_count: int
    numeric_counts: Mapping[str, int]
    missing_counts: Mapping[str, int]


@dataclass(frozen=True)
class OfficialValuationObservation:
    stock_code: str
    metric_name: str
    value: Decimal
    unit: str
    market: str
    as_of_date: date
    available_at: datetime
    source: str
    source_version: str
    receipt_path: Path
    raw_response_sha256: str
    formal_pit_eligible: bool = False


@dataclass(frozen=True)
class ValuationMarketCoverage:
    market: str
    status: str
    as_of_date: date | None
    available_at: datetime | None
    source: str | None
    source_version: str | None
    receipt_path: Path | None
    raw_response_sha256: str | None
    source_row_count: int
    unique_stock_count: int
    duplicate_row_count: int
    numeric_counts: Mapping[str, int]
    missing_counts: Mapping[str, int]
    diagnostic: str | None = None


@dataclass(frozen=True)
class CurrentOfficialValuationReadResult:
    status: str
    stock_code: str
    report_date: date
    observations: tuple[OfficialValuationObservation, ...]
    market_coverage: tuple[ValuationMarketCoverage, ...]
    diagnostics: tuple[str, ...]
    formal_pit_eligible: bool = False


@dataclass(frozen=True)
class MarketCaptureResult:
    market: str
    status: str
    source_date: date | None
    available_at: datetime | None
    source_row_count: int
    unique_stock_count: int
    numeric_counts: Mapping[str, int]
    missing_counts: Mapping[str, int]
    receipt_path: Path | None
    raw_response_sha256: str | None
    diagnostic: str | None = None
    receipt_sha256: str | None = None
    raw_response_path: Path | None = None
    raw_response_bytes: int | None = None
    failure_receipt_path: Path | None = None
    failure_receipt_sha256: str | None = None
    prior_failure_attempts: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ValuationCaptureRunResult:
    status: str
    completed_at: datetime
    markets: tuple[MarketCaptureResult, ...]
    wrapper_run_id: str
    run_id: str
    receipt_path: Path
    receipt_sha256: str
    formal_pit_eligible: bool = False


def parse_twse_valuation_response(raw: bytes) -> ParsedValuationSnapshot:
    """Parse TWSE BWIBBU_ALL JSON without guessing dates, units, or values."""
    document = _load_json(raw, "TWSE BWIBBU_ALL")
    if not isinstance(document, list) or not document:
        raise CurrentOfficialValuationError("TWSE valuation response must be a non-empty row array")
    rows: dict[str, ParsedValuationRow] = {}
    duplicate_count = 0
    dates: set[date] = set()
    numeric_counts = {metric: 0 for metric in METRIC_FIELDS}
    missing_counts = {metric: 0 for metric in METRIC_FIELDS}
    for row_number, raw_row in enumerate(document, start=1):
        if not isinstance(raw_row, Mapping):
            raise CurrentOfficialValuationError(f"TWSE valuation row {row_number} is not an object")
        required = {"Date", "Code", "PEratio", "DividendYield", "PBratio"}
        missing = required - set(raw_row)
        if missing:
            raise CurrentOfficialValuationError(
                f"TWSE valuation row {row_number} is missing fields: {sorted(missing)}"
            )
        code = str(raw_row.get("Code", "")).strip()
        if not _STOCK_CODE.fullmatch(code):
            raise CurrentOfficialValuationError(f"TWSE valuation row {row_number} has invalid Code")
        dates.add(_parse_roc_compact_date(raw_row["Date"]))
        values: dict[str, Decimal | None] = {}
        for metric, (field, _unit) in METRIC_FIELDS.items():
            value = _parse_decimal_or_missing(raw_row.get(field), field=f"TWSE {field} {code}")
            values[metric] = value
            if value is None:
                missing_counts[metric] += 1
            else:
                numeric_counts[metric] += 1
        parsed_row = ParsedValuationRow(code, values)
        if code in rows:
            if rows[code].values != parsed_row.values:
                raise CurrentOfficialValuationError(f"TWSE valuation has conflicting duplicate Code {code}")
            duplicate_count += 1
            continue
        rows[code] = parsed_row
    if len(dates) != 1:
        raise CurrentOfficialValuationError("TWSE valuation response contains mixed or missing source dates")
    return ParsedValuationSnapshot(
        market="twse",
        source_id="twse.openapi.bwibbu_all",
        parser_id=PARSER_VERSION,
        source_date=next(iter(dates)),
        rows=tuple(rows[code] for code in sorted(rows)),
        source_row_count=len(document),
        duplicate_row_count=duplicate_count,
        numeric_counts=numeric_counts,
        missing_counts=missing_counts,
    )


def parse_tpex_valuation_response(raw: bytes) -> ParsedValuationSnapshot:
    """Parse TPEx official daily P/E, yield, and P/B HTML table."""
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentOfficialValuationError("TPEx valuation response is empty or exceeds size limit")
    try:
        html = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise CurrentOfficialValuationError("TPEx valuation response is not UTF-8 HTML") from exc
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(
        r"資料日期\s*[:：]\s*(\d{2,3})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})",
        text,
    )
    if match is None:
        raise CurrentOfficialValuationError("TPEx official page does not expose a data date")
    source_date = _roc_date(match.group(1), match.group(2), match.group(3))
    if "全部產業" not in text:
        raise CurrentOfficialValuationError("TPEx response is not the unfiltered all-industry dataset")

    selected: tuple[list[str], list[Any]] | None = None
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for header_index, tr in enumerate(rows):
            headers = ["".join(cell.stripped_strings) for cell in tr.find_all(["th", "td"], recursive=False)]
            normalized = [_normalize_header(value) for value in headers]
            indexes = _tpex_header_indexes(normalized)
            if indexes is not None:
                selected = (normalized, rows[header_index + 1 :])
                break
        if selected is not None:
            break
    if selected is None:
        raise CurrentOfficialValuationError("TPEx official valuation table columns are missing")
    headers, body_rows = selected
    indexes = _tpex_header_indexes(headers)
    assert indexes is not None

    parsed_rows: dict[str, ParsedValuationRow] = {}
    source_row_count = 0
    duplicate_count = 0
    numeric_counts = {metric: 0 for metric in METRIC_FIELDS}
    missing_counts = {metric: 0 for metric in METRIC_FIELDS}
    for row_number, tr in enumerate(body_rows, start=1):
        cells = ["".join(cell.stripped_strings) for cell in tr.find_all(["td", "th"], recursive=False)]
        if not cells:
            continue
        if len(cells) != len(headers):
            # Footnotes and pagination rows may be shorter than the data table.
            if any(_STOCK_CODE.fullmatch(cell.strip()) for cell in cells):
                raise CurrentOfficialValuationError(f"TPEx valuation row {row_number} has an invalid shape")
            continue
        code = cells[indexes["code"]].strip()
        if not _STOCK_CODE.fullmatch(code):
            continue
        source_row_count += 1
        values: dict[str, Decimal | None] = {}
        for metric, column in (("pe", "pe"), ("dividend_yield", "yield"), ("pb", "pb")):
            value = _parse_decimal_or_missing(cells[indexes[column]], field=f"TPEx {column} {code}")
            values[metric] = value
            if value is None:
                missing_counts[metric] += 1
            else:
                numeric_counts[metric] += 1
        parsed_row = ParsedValuationRow(code, values)
        if code in parsed_rows:
            if parsed_rows[code].values != parsed_row.values:
                raise CurrentOfficialValuationError(f"TPEx valuation has conflicting duplicate Code {code}")
            duplicate_count += 1
            continue
        parsed_rows[code] = parsed_row
    if not parsed_rows:
        raise CurrentOfficialValuationError("TPEx official valuation table has no parseable stock rows")
    return ParsedValuationSnapshot(
        market="tpex",
        source_id="tpex.website.peratio_analysis",
        parser_id=PARSER_VERSION,
        source_date=source_date,
        rows=tuple(parsed_rows[code] for code in sorted(parsed_rows)),
        source_row_count=source_row_count,
        duplicate_row_count=duplicate_count,
        numeric_counts=numeric_counts,
        missing_counts=missing_counts,
    )


def parse_tpex_openapi_valuation_response(raw: bytes) -> ParsedValuationSnapshot:
    """解析 TPEx 官方 Swagger 所列每日估值 OpenAPI 回應。"""
    document = _load_json(raw, "TPEx tpex_mainboard_peratio_analysis")
    if not isinstance(document, list) or not document:
        raise CurrentOfficialValuationError("TPEx valuation OpenAPI must return a non-empty row array")
    rows: dict[str, ParsedValuationRow] = {}
    duplicate_count = 0
    dates: set[date] = set()
    numeric_counts = {metric: 0 for metric in METRIC_FIELDS}
    missing_counts = {metric: 0 for metric in METRIC_FIELDS}
    required = {
        "Date",
        "SecuritiesCompanyCode",
        "CompanyName",
        "PriceEarningRatio",
        "DividendPerShare",
        "YieldRatio",
        "PriceBookRatio",
    }
    fields = {
        "pe": "PriceEarningRatio",
        "dividend_yield": "YieldRatio",
        "pb": "PriceBookRatio",
    }
    for row_number, raw_row in enumerate(document, start=1):
        if not isinstance(raw_row, Mapping):
            raise CurrentOfficialValuationError(f"TPEx OpenAPI row {row_number} is not an object")
        missing = required - set(raw_row)
        if missing:
            raise CurrentOfficialValuationError(
                f"TPEx OpenAPI row {row_number} is missing fields: {sorted(missing)}"
            )
        code = str(raw_row.get("SecuritiesCompanyCode", "")).strip()
        if not _STOCK_CODE.fullmatch(code):
            raise CurrentOfficialValuationError(f"TPEx OpenAPI row {row_number} has invalid stock code")
        dates.add(_parse_roc_compact_date(raw_row["Date"]))
        values: dict[str, Decimal | None] = {}
        for metric, field in fields.items():
            value = _parse_decimal_or_missing(raw_row.get(field), field=f"TPEx {field} {code}")
            values[metric] = value
            if value is None:
                missing_counts[metric] += 1
            else:
                numeric_counts[metric] += 1
        parsed_row = ParsedValuationRow(code, values)
        if code in rows:
            if rows[code].values != parsed_row.values:
                raise CurrentOfficialValuationError(f"TPEx OpenAPI has conflicting duplicate stock code {code}")
            duplicate_count += 1
            continue
        rows[code] = parsed_row
    if len(dates) != 1:
        raise CurrentOfficialValuationError("TPEx OpenAPI response contains mixed or missing source dates")
    return ParsedValuationSnapshot(
        market="tpex",
        source_id="tpex.openapi.tpex_mainboard_peratio_analysis",
        parser_id=PARSER_VERSION,
        source_date=next(iter(dates)),
        rows=tuple(rows[code] for code in sorted(rows)),
        source_row_count=len(document),
        duplicate_row_count=duplicate_count,
        numeric_counts=numeric_counts,
        missing_counts=missing_counts,
    )


def capture_current_official_valuation(
    output_root: Path,
    *,
    wrapper_run_id: str | None = None,
    session: Any | None = None,
    timeout_seconds: float = 20.0,
    clock: Callable[[], datetime] | None = None,
) -> ValuationCaptureRunResult:
    """Fetch and custody-capture both official market snapshots.

    The function writes only create-only raw custody files under output_root.
    It never writes SQLite, formal valuation tables, or source financial data.
    """
    output_root = _safe_output_root(output_root)
    http = session or requests.Session()
    now = clock or (lambda: datetime.now(timezone.utc))
    run_started_at = _aware_utc(now(), "started_at")
    if wrapper_run_id is not None and not _RUN_ID.fullmatch(wrapper_run_id):
        raise ValueError("wrapper_run_id must be a bounded ASCII run identifier")
    run_id = wrapper_run_id or uuid4().hex
    run_root = _safe_output_root(output_root / CAPTURE_RELATIVE_ROOT / "runs" / run_id)
    run_root.mkdir(parents=True, exist_ok=False)
    routes: tuple[
        tuple[
            str,
            tuple[tuple[str, str, dict[str, str], Callable[[bytes], ParsedValuationSnapshot]], ...],
        ],
        ...,
    ] = (
        ("twse", (("twse.openapi.bwibbu_all", TWSE_URL, {}, parse_twse_valuation_response),)),
        (
            "tpex",
            (
                ("tpex.website.peratio_analysis", TPEX_URL, TPEX_PARAMS, parse_tpex_valuation_response),
                (
                    "tpex.openapi.tpex_mainboard_peratio_analysis",
                    TPEX_OPENAPI_URL,
                    {},
                    parse_tpex_openapi_valuation_response,
                ),
            ),
        ),
    )
    results: list[MarketCaptureResult] = []
    for market, attempts in routes:
        prior_failures: list[Mapping[str, Any]] = []
        market_result: MarketCaptureResult | None = None
        for attempt_index, (source_id, url, params, parser) in enumerate(attempts):
            raw: bytes | None = None
            response: Any | None = None
            body_completed_at: datetime | None = None
            parsed: ParsedValuationSnapshot | None = None
            failure_receipt_path: Path | None = None
            failure_receipt_sha256: str | None = None
            try:
                response = http.get(
                    url,
                    params=params or None,
                    headers={
                        "User-Agent": "technical-analysis-current-valuation/1.0",
                        "Accept": "text/html" if source_id == "tpex.website.peratio_analysis" else "application/json",
                        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
                    },
                    timeout=timeout_seconds,
                )
                raw = bytes(response.content)
                body_completed_at = _aware_utc(now(), "body_completed_at")
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise CurrentOfficialValuationError("official response exceeds size limit")
                if int(response.status_code) != 200:
                    raise CurrentOfficialValuationError(f"official response HTTP {response.status_code}")
                final_url = str(getattr(response, "url", "") or url)
                parsed = parser(raw)
                if parsed.source_id != source_id:
                    raise CurrentOfficialValuationError("parser source identity differs from configured route")
                _validate_source_url(
                    market,
                    final_url,
                    require_parameters=source_id == "tpex.website.peratio_analysis",
                    source_id=source_id,
                )
                receipt_path, raw_digest = _persist_capture(
                    output_root=output_root,
                    parsed=parsed,
                    raw_response=raw,
                    requested_url=url,
                    final_url=final_url,
                    request_parameters=params,
                    response_headers=getattr(response, "headers", {}),
                    http_status=int(response.status_code),
                    captured_at=body_completed_at,
                    run_id=run_id,
                    wrapper_run_id=run_id,
                )
                receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                market_result = MarketCaptureResult(
                    market=market,
                    status="captured",
                    source_date=parsed.source_date,
                    available_at=body_completed_at,
                    source_row_count=parsed.source_row_count,
                    unique_stock_count=len(parsed.rows),
                    numeric_counts=dict(parsed.numeric_counts),
                    missing_counts=dict(parsed.missing_counts),
                    receipt_path=receipt_path,
                    raw_response_sha256=raw_digest,
                    receipt_sha256=receipt_sha256,
                    raw_response_path=receipt_path.parent / "raw_response.bin",
                    raw_response_bytes=len(raw),
                    diagnostic=(
                        f"captured_after_{len(prior_failures)}_source_failure(s)" if prior_failures else None
                    ),
                    prior_failure_attempts=tuple(prior_failures),
                )
                break
            except Exception as exc:
                diagnostic = f"{type(exc).__name__}:{exc}"
                if raw is not None and len(raw) <= MAX_RESPONSE_BYTES:
                    attempt_id = (
                        f"{attempt_index + 1:02d}-{source_id.rsplit('.', 1)[-1]}"
                        if attempt_index < len(attempts) - 1
                        else None
                    )
                    failure_receipt_path, failure_receipt_sha256 = _persist_failed_capture(
                        run_root=run_root,
                        market=market,
                        source_id=source_id,
                        attempt_id=attempt_id,
                        requested_url=url,
                        request_parameters=params,
                        response=response,
                        raw_response=raw,
                        body_completed_at=body_completed_at,
                        source_date=parsed.source_date if parsed is not None else None,
                        diagnostic=diagnostic,
                    )
                failure_evidence: dict[str, Any] = {
                    "source_id": source_id,
                    "requested_url": url,
                    "final_url": str(getattr(response, "url", "") or url),
                    "status": "failed",
                    "raw_response_path": (
                        str((failure_receipt_path.parent / "raw_response.bin").resolve())
                        if failure_receipt_path is not None
                        else None
                    ),
                    "raw_response_sha256": _sha256(raw) if raw is not None else None,
                    "raw_response_bytes": len(raw) if raw is not None else None,
                    "receipt_path": str(failure_receipt_path.resolve()) if failure_receipt_path else None,
                    "receipt_sha256": failure_receipt_sha256,
                    "diagnostic": diagnostic,
                    "captured_at": body_completed_at.isoformat() if body_completed_at else None,
                }
                if attempt_index < len(attempts) - 1:
                    prior_failures.append(failure_evidence)
                    continue
                market_result = MarketCaptureResult(
                    market=market,
                    status="failed",
                    source_date=parsed.source_date if parsed is not None else None,
                    available_at=body_completed_at,
                    source_row_count=0,
                    unique_stock_count=0,
                    numeric_counts={},
                    missing_counts={},
                    receipt_path=None,
                    raw_response_sha256=_sha256(raw) if raw is not None else None,
                    diagnostic=diagnostic,
                    raw_response_path=(
                        failure_receipt_path.parent / "raw_response.bin"
                        if failure_receipt_path is not None
                        else None
                    ),
                    raw_response_bytes=len(raw) if raw is not None else None,
                    failure_receipt_path=failure_receipt_path,
                    failure_receipt_sha256=failure_receipt_sha256,
                    prior_failure_attempts=tuple(prior_failures),
                )
        if market_result is None:
            raise CurrentOfficialValuationError(f"{market} route attempts produced no terminal result")
        results.append(market_result)
    status = "captured" if all(result.status == "captured" for result in results) else "degraded"
    completed_at = _aware_utc(now(), "completed_at")
    run_receipt_path = run_root / "receipt.json"
    run_receipt = _build_run_receipt(
        status=status,
        run_id=run_id,
        wrapper_run_id=run_id,
        started_at=run_started_at,
        completed_at=completed_at,
        markets=results,
    )
    run_receipt_bytes = (_canonical_json(run_receipt) + "\n").encode("utf-8")
    _write_create_only(run_receipt_path, run_receipt_bytes)
    receipt_sha256 = hashlib.sha256(run_receipt_path.read_bytes()).hexdigest()
    return ValuationCaptureRunResult(
        status=status,
        completed_at=completed_at,
        markets=tuple(results),
        wrapper_run_id=run_id,
        run_id=run_id,
        receipt_path=run_receipt_path,
        receipt_sha256=receipt_sha256,
    )


class CurrentOfficialValuationReadProvider:
    """Read hash-verified, current-only market valuation observations."""

    def __init__(
        self,
        output_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.output_root = _safe_output_root(output_root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def read_current(
        self,
        stock_code: str,
        as_of_date: date | str | None = None,
        *,
        market: str | None = None,
        expected_market_date: date | str | None = None,
    ) -> CurrentOfficialValuationReadResult:
        now = _aware_utc(self._clock(), "clock")
        report_date = now.astimezone(_TAIPEI).date()
        requested_date = report_date if as_of_date is None else _parse_report_date(as_of_date)
        expected_date = (
            None
            if expected_market_date is None
            else _parse_report_date(expected_market_date)
        )
        normalized_code = str(stock_code).strip()
        if requested_date != report_date:
            return CurrentOfficialValuationReadResult(
                status="blocked_historical_date",
                stock_code=normalized_code,
                report_date=requested_date,
                observations=(),
                market_coverage=(),
                diagnostics=("current valuation snapshots are unavailable for historical report dates",),
            )
        if expected_date is not None and expected_date > report_date:
            return CurrentOfficialValuationReadResult(
                status="blocked_future_expected_market_date",
                stock_code=normalized_code,
                report_date=report_date,
                observations=(),
                market_coverage=(),
                diagnostics=("expected_market_date cannot be later than the current Taipei report date",),
            )
        if not _STOCK_CODE.fullmatch(normalized_code):
            return CurrentOfficialValuationReadResult(
                status="blocked_invalid_stock_code",
                stock_code=normalized_code,
                report_date=report_date,
                observations=(),
                market_coverage=(),
                diagnostics=("stock_code must contain 4 to 6 digits",),
            )
        if market is not None and market not in {"twse", "tpex"}:
            return CurrentOfficialValuationReadResult(
                status="blocked_invalid_market",
                stock_code=normalized_code,
                report_date=report_date,
                observations=(),
                market_coverage=(),
                diagnostics=("market must be twse or tpex",),
            )

        snapshots: dict[str, tuple[ParsedValuationSnapshot, datetime, str, Path, str]] = {}
        coverage: list[ValuationMarketCoverage] = []
        diagnostics: list[str] = []
        for venue in ("twse", "tpex"):
            try:
                loaded = _load_latest_market_capture(
                    self.output_root,
                    market=venue,
                    now=now,
                    expected_source_date=expected_date,
                )
            except (OSError, UnicodeError, json.JSONDecodeError, CurrentOfficialValuationError) as exc:
                diagnostic = f"{venue}_capture_invalid:{type(exc).__name__}:{exc}"
                diagnostics.append(diagnostic)
                coverage.append(_empty_coverage(venue, "invalid", diagnostic))
                continue
            if loaded is None:
                diagnostics.append(f"{venue}_capture_missing")
                coverage.append(_empty_coverage(venue, "missing", f"no official current capture for {venue}"))
                continue
            parsed, available_at, source_version, receipt_path, raw_digest = loaded
            snapshots[venue] = (parsed, available_at, source_version, receipt_path, raw_digest)
            coverage_status = "freshness_unverified"
            coverage_diagnostic: str | None = "expected_market_date_missing"
            if expected_date is not None:
                if parsed.source_date < expected_date:
                    coverage_status = "stale"
                    coverage_diagnostic = "official valuation source date precedes expected market date"
                elif parsed.source_date > expected_date:
                    coverage_status = "out_of_sync"
                    coverage_diagnostic = "official valuation source date follows expected market date"
                else:
                    coverage_status = "ready"
                    coverage_diagnostic = None
            coverage.append(
                ValuationMarketCoverage(
                    market=venue,
                    status=coverage_status,
                    as_of_date=parsed.source_date,
                    available_at=available_at,
                    source=parsed.source_id,
                    source_version=source_version,
                    receipt_path=receipt_path,
                    raw_response_sha256=raw_digest,
                    source_row_count=parsed.source_row_count,
                    unique_stock_count=len(parsed.rows),
                    duplicate_row_count=parsed.duplicate_row_count,
                    numeric_counts=dict(parsed.numeric_counts),
                    missing_counts=dict(parsed.missing_counts),
                    diagnostic=coverage_diagnostic,
                )
            )

        matches: list[tuple[str, ParsedValuationSnapshot, datetime, str, Path]] = []
        for venue, (parsed, available_at, source_version, receipt_path, _raw_digest) in snapshots.items():
            if market is not None and venue != market:
                continue
            if any(row.stock_code == normalized_code for row in parsed.rows):
                matches.append((venue, parsed, available_at, source_version, receipt_path))
        if len(matches) > 1:
            return CurrentOfficialValuationReadResult(
                status="blocked_ambiguous_market",
                stock_code=normalized_code,
                report_date=report_date,
                observations=(),
                market_coverage=tuple(coverage),
                diagnostics=tuple(diagnostics + ["stock code is present in both market sources"]),
            )
        if not matches:
            status = "partial" if snapshots else "unavailable"
            return CurrentOfficialValuationReadResult(
                status=status,
                stock_code=normalized_code,
                report_date=report_date,
                observations=(),
                market_coverage=tuple(coverage),
                diagnostics=tuple(diagnostics + ["stock code has no official current valuation row"]),
            )

        venue, parsed, available_at, source_version, receipt_path = matches[0]
        row = next(record for record in parsed.rows if record.stock_code == normalized_code)
        source_version_hash = source_version
        raw_hash = next(
            item.raw_response_sha256
            for item in coverage
            if item.market == venue
        )
        if raw_hash is None:
            raise CurrentOfficialValuationError("matched market is missing its raw-response hash")
        observations = tuple(
            OfficialValuationObservation(
                stock_code=normalized_code,
                metric_name=metric,
                value=value,
                unit=METRIC_FIELDS[metric][1],
                market=venue,
                as_of_date=parsed.source_date,
                available_at=available_at,
                source=parsed.source_id,
                source_version=source_version_hash,
                receipt_path=receipt_path,
                raw_response_sha256=raw_hash,
            )
            for metric, value in row.values.items()
            if value is not None
        )
        matched_coverage = next(item for item in coverage if item.market == venue)
        if matched_coverage.status != "ready":
            result_status = matched_coverage.status
        else:
            result_status = "ready" if observations else "partial"
        if expected_date is None:
            diagnostics.append("expected_market_date_missing:freshness_not_verified")
        return CurrentOfficialValuationReadResult(
            status=result_status,
            stock_code=normalized_code,
            report_date=report_date,
            observations=observations,
            market_coverage=tuple(coverage),
            diagnostics=tuple(diagnostics),
        )


def _persist_capture(
    *,
    output_root: Path,
    parsed: ParsedValuationSnapshot,
    raw_response: bytes,
    requested_url: str,
    final_url: str,
    request_parameters: Mapping[str, str],
    response_headers: Mapping[str, Any],
    http_status: int,
    captured_at: datetime,
    run_id: str,
    wrapper_run_id: str,
) -> tuple[Path, str]:
    digest = _sha256(raw_response)
    date_key = parsed.source_date.strftime("%Y%m%d")
    capture_key = f"{digest[7:19]}-{captured_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    capture_dir = _safe_output_root(
        output_root / CAPTURE_RELATIVE_ROOT / parsed.market / date_key / capture_key
    )
    capture_dir.mkdir(parents=True, exist_ok=True)
    safe_headers = {
        str(key).lower(): str(value)
        for key, value in dict(response_headers).items()
        if str(key).lower() not in _SENSITIVE_HEADERS
    }
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_authority": parsed.market,
        "source_id": parsed.source_id,
        "parser_id": parsed.parser_id,
        "source_date": parsed.source_date.isoformat(),
        "run_id": run_id,
        "wrapper_run_id": wrapper_run_id,
        "requested_url": requested_url,
        "final_url": final_url,
        "request_parameters": dict(request_parameters),
        "response": {"http_status": http_status, "headers": safe_headers},
        "captured_at": captured_at.isoformat(),
        "available_at": captured_at.isoformat(),
        "availability_basis": "response_body_read_completed_at",
        "raw_response_path": "raw_response.bin",
        "raw_response_sha256": digest,
        "raw_response_bytes": len(raw_response),
        "source_row_count": parsed.source_row_count,
        "unique_stock_count": len(parsed.rows),
        "duplicate_row_count": parsed.duplicate_row_count,
        "numeric_counts": dict(parsed.numeric_counts),
        "missing_counts": dict(parsed.missing_counts),
        "metric_units": {metric: metadata[1] for metric, metadata in METRIC_FIELDS.items()},
        "source_contract_reference": (
            TPEX_OPENAPI_SPEC_URL
            if parsed.source_id == "tpex.openapi.tpex_mainboard_peratio_analysis"
            else None
        ),
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
    }
    receipt = {**body, "content_sha256": _sha256(_canonical_json(body).encode("utf-8"))}
    receipt_bytes = (_canonical_json(receipt) + "\n").encode("utf-8")
    raw_path = capture_dir / "raw_response.bin"
    receipt_path = capture_dir / "receipt.json"
    _write_create_only(raw_path, raw_response)
    _write_create_only(receipt_path, receipt_bytes)
    observation_id = hashlib.sha256(receipt_bytes).hexdigest()[:16]
    _write_create_only(capture_dir / "observations" / f"{observation_id}.json", receipt_bytes)
    if _sha256(raw_path.read_bytes()) != digest:
        raise CurrentOfficialValuationError("raw response readback hash mismatch")
    return receipt_path, digest


def _persist_failed_capture(
    *,
    run_root: Path,
    market: str,
    source_id: str,
    attempt_id: str | None,
    requested_url: str,
    request_parameters: Mapping[str, str],
    response: Any | None,
    raw_response: bytes,
    body_completed_at: datetime | None,
    source_date: date | None,
    diagnostic: str,
) -> tuple[Path, str]:
    """Keep bounded failed official response bodies with their failure receipt."""
    market_root = run_root / "markets" / market
    if attempt_id is not None:
        market_root = market_root / "attempts" / attempt_id
    raw_path = market_root / "raw_response.bin"
    receipt_path = market_root / "receipt.json"
    digest = _sha256(raw_response)
    status_code = getattr(response, "status_code", None)
    final_url = str(getattr(response, "url", "") or requested_url)
    headers = {
        str(key).lower(): str(value)
        for key, value in dict(getattr(response, "headers", {}) or {}).items()
        if str(key).lower() not in _SENSITIVE_HEADERS
    }
    body: dict[str, Any] = {
        "schema_version": "official-current-valuation-market-failure.v1",
        "market": market,
        "source_id": source_id,
        "attempt_id": attempt_id,
        "requested_url": requested_url,
        "final_url": final_url,
        "request_parameters": dict(request_parameters),
        "response": {"http_status": status_code, "headers": headers},
        "source_date": source_date.isoformat() if source_date is not None else None,
        "body_completed_at": body_completed_at.isoformat() if body_completed_at else None,
        "raw_response_path": "raw_response.bin",
        "raw_response_sha256": digest,
        "raw_response_bytes": len(raw_response),
        "status": "failed",
        "diagnostic": diagnostic,
        "formal_pit_eligible": False,
        "historical_pit_eligible": False,
    }
    payload = {**body, "content_sha256": _sha256(_canonical_json(body).encode("utf-8"))}
    _write_create_only(raw_path, raw_response)
    receipt_bytes = (_canonical_json(payload) + "\n").encode("utf-8")
    _write_create_only(receipt_path, receipt_bytes)
    return receipt_path, hashlib.sha256(receipt_bytes).hexdigest()


def _build_run_receipt(
    *,
    status: str,
    run_id: str,
    wrapper_run_id: str,
    started_at: datetime,
    completed_at: datetime,
    markets: Sequence[MarketCaptureResult],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "official-current-valuation-run.v1",
        "status": status,
        "run_id": run_id,
        "wrapper_run_id": wrapper_run_id,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "formal_pit_eligible": False,
        "historical_pit_eligible": False,
        "markets": [
            {
                "market": item.market,
                "status": item.status,
                "source_date": item.source_date.isoformat() if item.source_date else None,
                "available_at": item.available_at.isoformat() if item.available_at else None,
                "source_row_count": item.source_row_count,
                "unique_stock_count": item.unique_stock_count,
                "raw_response_path": str(item.raw_response_path.resolve())
                if item.raw_response_path
                else None,
                "raw_response_sha256": item.raw_response_sha256,
                "raw_response_bytes": item.raw_response_bytes,
                "receipt_path": str(item.receipt_path.resolve())
                if item.receipt_path
                else None,
                "receipt_sha256": item.receipt_sha256,
                "failure_receipt_path": str(item.failure_receipt_path.resolve())
                if item.failure_receipt_path
                else None,
                "failure_receipt_sha256": item.failure_receipt_sha256,
                "prior_failure_attempts": [dict(attempt) for attempt in item.prior_failure_attempts],
                "diagnostic": item.diagnostic,
            }
            for item in markets
        ],
    }
    return {**body, "content_sha256": _sha256(_canonical_json(body).encode("utf-8"))}


def _load_latest_market_capture(
    output_root: Path,
    *,
    market: str,
    now: datetime,
    expected_source_date: date | None = None,
) -> tuple[ParsedValuationSnapshot, datetime, str, Path, str] | None:
    root = output_root / CAPTURE_RELATIVE_ROOT / market
    if not root.is_dir():
        return None
    date_dirs: list[tuple[date, Path]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        if re.match(r"^\d{8}", path.name) and not re.fullmatch(
            r"\d{8}", path.name
        ):
            raise CurrentOfficialValuationError(
                "source-date directory name is malformed"
            )
        try:
            parsed_date = datetime.strptime(path.name, "%Y%m%d").date()
        except ValueError:
            if re.fullmatch(r"\d{8}", path.name):
                raise CurrentOfficialValuationError(
                    "source-date directory name is not a valid date"
                )
            continue
        date_dirs.append((parsed_date, path))
    date_dirs.sort(key=lambda item: item[0], reverse=True)
    if not date_dirs:
        return None
    report_date = now.astimezone(_TAIPEI).date()
    if any(source_date > report_date for source_date, _path in date_dirs):
        raise CurrentOfficialValuationError("future source-date directory exists")
    if expected_source_date is not None:
        if expected_source_date > report_date:
            raise CurrentOfficialValuationError(
                "expected source date is later than the current Taipei report date"
            )
        selected_dir = next(
            (
                path
                for source_date, path in date_dirs
                if source_date == expected_source_date
            ),
            None,
        )
        if selected_dir is None:
            return None
        latest_dir = selected_dir
    else:
        latest_dir = date_dirs[0][1]
    capture_dirs = [path for path in latest_dir.iterdir() if path.is_dir()]
    if not capture_dirs:
        raise CurrentOfficialValuationError("latest source-date directory has no captures")
    loaded: list[tuple[ParsedValuationSnapshot, datetime, str, Path, str]] = []
    failures: list[str] = []
    for capture_dir in sorted(capture_dirs):
        receipt_path = capture_dir / "receipt.json"
        try:
            loaded.append(_load_capture(receipt_path, capture_dir, market, latest_dir.name, now))
        except (OSError, UnicodeError, json.JSONDecodeError, CurrentOfficialValuationError) as exc:
            failures.append(f"{capture_dir.name}:{type(exc).__name__}:{exc}")
    if failures:
        raise CurrentOfficialValuationError(
            "latest source date contains invalid or future capture(s): " + "; ".join(failures[:5])
        )
    if not loaded:
        raise CurrentOfficialValuationError("latest source date has no readable capture receipt")
    return max(loaded, key=lambda item: item[1])


def _load_capture(
    receipt_path: Path,
    capture_dir: Path,
    market: str,
    date_dir_name: str,
    now: datetime,
) -> tuple[ParsedValuationSnapshot, datetime, str, Path, str]:
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise CurrentOfficialValuationError("receipt root is not an object")
    _validate_receipt(payload, capture_dir, market, date_dir_name)
    raw_path = capture_dir / "raw_response.bin"
    raw = raw_path.read_bytes()
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentOfficialValuationError("raw response is empty or too large")
    digest = _sha256(raw)
    if digest != payload.get("raw_response_sha256"):
        raise CurrentOfficialValuationError("raw response hash does not match receipt")
    if len(raw) != payload.get("raw_response_bytes"):
        raise CurrentOfficialValuationError("raw response byte count does not match receipt")
    source_id = str(payload.get("source_id", ""))
    if market == "twse":
        parsed = parse_twse_valuation_response(raw)
    elif source_id == "tpex.openapi.tpex_mainboard_peratio_analysis":
        parsed = parse_tpex_openapi_valuation_response(raw)
    else:
        parsed = parse_tpex_valuation_response(raw)
    _validate_parsed_matches_receipt(parsed, payload)
    available_at = _parse_aware(payload.get("available_at"), "available_at")
    if available_at > now:
        raise CurrentOfficialValuationError("available_at is in the future")
    source_version = f"{parsed.source_id}:{parsed.source_date.isoformat()}:{digest}"
    return parsed, available_at, source_version, receipt_path, digest


def _validate_receipt(
    payload: Mapping[str, Any],
    capture_dir: Path,
    market: str,
    date_dir_name: str,
) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CurrentOfficialValuationError("unsupported receipt schema")
    if payload.get("source_authority") != market:
        raise CurrentOfficialValuationError("receipt market identity mismatch")
    source_id = str(payload.get("source_id", ""))
    allowed_sources = {
        "twse": {"twse.openapi.bwibbu_all"},
        "tpex": {
            "tpex.website.peratio_analysis",
            "tpex.openapi.tpex_mainboard_peratio_analysis",
        },
    }[market]
    if source_id not in allowed_sources or payload.get("parser_id") != PARSER_VERSION:
        raise CurrentOfficialValuationError("receipt source/parser identity mismatch")
    expected_contract_reference = (
        TPEX_OPENAPI_SPEC_URL
        if source_id == "tpex.openapi.tpex_mainboard_peratio_analysis"
        else None
    )
    if payload.get("source_contract_reference") != expected_contract_reference:
        raise CurrentOfficialValuationError("receipt source contract reference does not match its source")
    if payload.get("formal_pit_eligible") is not False or payload.get("historical_pit_eligible") is not False:
        raise CurrentOfficialValuationError("current valuation receipt must remain outside formal PIT")
    if payload.get("availability_basis") != "response_body_read_completed_at":
        raise CurrentOfficialValuationError("receipt does not prove body-read completion time")
    if payload.get("raw_response_path") != "raw_response.bin":
        raise CurrentOfficialValuationError("receipt raw path is not canonical")
    if date.fromisoformat(str(payload.get("source_date", ""))).strftime("%Y%m%d") != date_dir_name:
        raise CurrentOfficialValuationError("receipt source date does not match directory")
    raw_digest = str(payload.get("raw_response_sha256", ""))
    has_legacy_capture_key = capture_dir.name.startswith(raw_digest[7:23] + "-")
    has_compact_capture_key = capture_dir.name.startswith(raw_digest[7:19] + "-")
    if not _SHA256.fullmatch(raw_digest) or not (has_legacy_capture_key or has_compact_capture_key):
        raise CurrentOfficialValuationError("capture directory does not match raw-response hash")
    response = payload.get("response")
    if not isinstance(response, Mapping) or response.get("http_status") != 200:
        raise CurrentOfficialValuationError("receipt does not record HTTP 200")
    _validate_source_url(market, str(payload.get("requested_url", "")), source_id=source_id)
    _validate_source_url(
        market,
        str(payload.get("final_url", "")),
        require_parameters=source_id == "tpex.website.peratio_analysis",
        source_id=source_id,
    )
    request = payload.get("request_parameters")
    expected_params = TPEX_PARAMS if source_id == "tpex.website.peratio_analysis" else {}
    if not isinstance(request, Mapping) or dict(request) != expected_params:
        raise CurrentOfficialValuationError("receipt request parameters do not match official route")
    if payload.get("metric_units") != {metric: metadata[1] for metric, metadata in METRIC_FIELDS.items()}:
        raise CurrentOfficialValuationError("receipt metric units do not match the pinned parser contract")
    content_hash = payload.get("content_sha256")
    if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
        raise CurrentOfficialValuationError("receipt content hash is malformed")
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if _sha256(_canonical_json(body).encode("utf-8")) != content_hash:
        raise CurrentOfficialValuationError("receipt content hash mismatch")


def _validate_parsed_matches_receipt(parsed: ParsedValuationSnapshot, payload: Mapping[str, Any]) -> None:
    expected_counts = {
        "source_row_count": parsed.source_row_count,
        "unique_stock_count": len(parsed.rows),
        "duplicate_row_count": parsed.duplicate_row_count,
        "numeric_counts": dict(parsed.numeric_counts),
        "missing_counts": dict(parsed.missing_counts),
    }
    if date.fromisoformat(str(payload.get("source_date", ""))) != parsed.source_date:
        raise CurrentOfficialValuationError("raw response data date differs from receipt")
    for key, expected in expected_counts.items():
        if payload.get(key) != expected:
            raise CurrentOfficialValuationError(f"receipt {key} differs from parsed raw response")


def _tpex_header_indexes(headers: Sequence[str]) -> dict[str, int] | None:
    code_candidates = {"股票代號", "股票代碼", "證券代號", "代號"}
    code_index = next((i for i, value in enumerate(headers) if value in code_candidates), None)
    pe_index = next((i for i, value in enumerate(headers) if value == "本益比"), None)
    yield_index = next((i for i, value in enumerate(headers) if value.startswith("殖利率")), None)
    pb_index = next((i for i, value in enumerate(headers) if value == "股價淨值比"), None)
    if (
        code_index is None
        or pe_index is None
        or yield_index is None
        or pb_index is None
    ):
        return None
    return {"code": code_index, "pe": pe_index, "yield": yield_index, "pb": pb_index}


def _parse_decimal_or_missing(value: object, *, field: str) -> Decimal | None:
    raw = str(value or "").strip().replace(",", "")
    if raw in _MISSING:
        return None
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise CurrentOfficialValuationError(f"{field} is not Decimal text") from exc
    if not parsed.is_finite():
        raise CurrentOfficialValuationError(f"{field} is non-finite")
    return parsed


def _parse_roc_compact_date(value: object) -> date:
    raw = re.sub(r"\D", "", str(value or ""))
    if len(raw) not in {6, 7}:
        raise CurrentOfficialValuationError("TWSE Date must be ROC YYYYMMDD")
    year_text, month_text, day_text = raw[:-4], raw[-4:-2], raw[-2:]
    return _roc_date(year_text, month_text, day_text)


def _roc_date(year: object, month: object, day: object) -> date:
    try:
        return date(int(str(year)) + 1911, int(str(month)), int(str(day)))
    except ValueError as exc:
        raise CurrentOfficialValuationError("official source date is invalid") from exc


def _parse_report_date(value: date | str) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(_TAIPEI).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("as_of_date must be an ISO date") from exc


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s\u3000\xa0]", "", value).replace("％", "%")


def _load_json(raw: bytes, label: str) -> Any:
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CurrentOfficialValuationError(f"{label} response is empty or too large")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentOfficialValuationError(f"{label} response is not valid JSON") from exc


def _validate_source_url(
    market: str,
    value: str,
    *,
    require_parameters: bool = False,
    source_id: str | None = None,
) -> None:
    parsed = urlparse(value)
    if market == "twse":
        expected_host, expected_path = "openapi.twse.com.tw", "/v1/exchangeReport/BWIBBU_ALL"
    elif source_id == "tpex.openapi.tpex_mainboard_peratio_analysis":
        expected_host, expected_path = "www.tpex.org.tw", "/openapi/v1/tpex_mainboard_peratio_analysis"
    else:
        expected_host, expected_path = (
            "www.tpex.org.tw",
            "/web/stock/aftertrading/peratio_analysis/pera_result.php",
        )
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(query_pairs)
    allowed_queries = ({}, TPEX_PARAMS) if source_id == "tpex.website.peratio_analysis" else ({},)
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.netloc != expected_host
        or parsed.path != expected_path
        or parsed.fragment
        or len(query_pairs) != len(query)
        or query not in allowed_queries
        or (require_parameters and query != TPEX_PARAMS)
    ):
        raise CurrentOfficialValuationError(f"{market} URL is not the pinned official valuation endpoint")


def _write_create_only(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise CurrentOfficialValuationError(f"immutable valuation custody conflict: {path}")
        return
    temporary = path.with_name(f".{uuid4().hex[:12]}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # NTFS rename 具原子性且目的檔已存在時會失敗；部分受管工作區無法建立硬連結。
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != value:
                raise CurrentOfficialValuationError(f"immutable valuation custody race conflict: {path}")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _empty_coverage(market: str, status: str, diagnostic: str) -> ValuationMarketCoverage:
    return ValuationMarketCoverage(
        market=market,
        status=status,
        as_of_date=None,
        available_at=None,
        source=None,
        source_version=None,
        receipt_path=None,
        raw_response_sha256=None,
        source_row_count=0,
        unique_stock_count=0,
        duplicate_row_count=0,
        numeric_counts={},
        missing_counts={},
        diagnostic=diagnostic,
    )


def _safe_output_root(value: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError("output_root must resolve to an absolute path")
    for component in (candidate, *candidate.parents):
        if component.exists() and component.is_symlink():
            raise ValueError("output_root path cannot contain a symlink")
    return candidate.resolve()


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_aware(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CurrentOfficialValuationError(f"{field_name} is not ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentOfficialValuationError(f"{field_name} has no timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


__all__ = [
    "CurrentOfficialValuationError",
    "CurrentOfficialValuationReadProvider",
    "CurrentOfficialValuationReadResult",
    "MarketCaptureResult",
    "OfficialValuationObservation",
    "ValuationCaptureRunResult",
    "capture_current_official_valuation",
    "parse_tpex_valuation_response",
    "parse_twse_valuation_response",
]
