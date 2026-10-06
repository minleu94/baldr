"""有限額保存 TWSE/TPEx 季報 OpenAPI 原始快照，只供研究檢視。

模組保存每次實際觀測的 HTTP entity，並輸出 Decimal 預覽；不推定歷史可得日、
不向官方分母驗證發行人、不寫資料庫，也不授予 PIT／Formal／訓練資格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
from typing import Any, BinaryIO, Callable, Mapping, Protocol, Sequence
import uuid
import zlib
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "mops_quarterly_openapi_research"
TAIPEI = ZoneInfo("Asia/Taipei")

MAX_ENTITY_BYTES = 8 * 1024 * 1024
MAX_DECODED_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_RAW_BYTES = 256 * 1024 * 1024
MAX_PREVIEW_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024 * 1024
MIN_FREE_SPACE_BYTES = 16 * 1024 * 1024
MAX_READ_CHUNK_BYTES = 64 * 1024
MAX_PREVIEW_RECORD_BYTES = 1024 * 1024
MAX_DIAGNOSTIC_SAMPLES = 100
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_PACING_SECONDS = 2
MAX_REQUEST_ELAPSED_SECONDS = 60.0
MAX_RUN_ELAPSED_SECONDS = 900.0

TWSE_CATALOG_URL = "https://openapi.twse.com.tw/v1/swagger.json"
TPEX_CATALOG_URL = "https://www.tpex.org.tw/openapi/swagger.json"
CATEGORY_CODES = ("basi", "bd", "ci", "fh", "ins", "mim")
CATEGORY_LABELS = {
    "basi": "金融業",
    "bd": "證券期貨業",
    "ci": "一般業",
    "fh": "金控業",
    "ins": "保險業",
    "mim": "異業",
}
STATEMENT_NUMBERS = {"income": "06", "balance": "07"}
IDENTITY_FIELDS = frozenset(
    {
        "Date",
        "Year",
        "Season",
        "SecuritiesCompanyCode",
        "CompanyName",
        "出表日期",
        "年度",
        "季別",
        "公司代號",
        "公司名稱",
    }
)
EPS_FIELD_NAMES = frozenset({"基本每股盈餘（元）", "基本每股盈餘(元)"})
SHARE_FIELD_SUFFIXES = ("（單位：股）", "(單位：股)")
MISSING_MARKERS = frozenset({"", "--", "—", "－", "N/A", "NA", "null", "None"})
DECIMAL_TEXT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
STOCK_CODE_RE = re.compile(r"^\d{4,6}$")

TWSE_TARGET_HOST = "openapi.twse.com.tw"
TPEX_TARGET_SERVER = "https://www.tpex.org.tw/openapi/v1"
CATALOG_BASELINE_PROVENANCE = {
    "twse": {
        "url": TWSE_CATALOG_URL,
        "repository_reference_path": "output/qa/twse_openapi_catalog_metadata_20261001_run02/response_body.raw",
        "bytes": 309960,
        "sha256": "06e1cea82448361e733a0ad1ae16e52f5d5d6b71905acd078472f852c32c0eb0",
        "captured_at_utc": "2026-09-30T22:42:35.027180Z/2026-09-30T22:42:36.494611Z",
        "reference_only_not_runtime_input": True,
    },
    "tpex": {
        "url": TPEX_CATALOG_URL,
        "repository_reference_path": "output/qa/tpex_openapi_catalog_metadata_20261001_run02/response_body.raw",
        "bytes": 476923,
        "sha256": "05af7755d0d528626c104f7a8ccd7b00c6a0cf228d30bcb4669020e514eb0c7e",
        "captured_at_utc": "2026-09-30T22:38:51.226937Z/2026-09-30T22:38:52.420371Z",
        "reference_only_not_runtime_input": True,
    },
}


@dataclass(frozen=True)
class Endpoint:
    market: str
    statement_type: str
    category: str
    route: str
    url: str

    @property
    def endpoint_id(self) -> str:
        return f"{self.market}_{self.statement_type}_{self.category}"


def _endpoint_table() -> tuple[Endpoint, ...]:
    endpoints: list[Endpoint] = []
    for market in ("twse", "tpex"):
        for statement_type, number in STATEMENT_NUMBERS.items():
            for category in CATEGORY_CODES:
                if market == "twse":
                    route = f"/opendata/t187ap{number}_L_{category}"
                    url = f"https://{TWSE_TARGET_HOST}/v1{route}"
                else:
                    route = f"/mopsfin_t187ap{number}_O_{category}"
                    url = f"{TPEX_TARGET_SERVER}{route}"
                endpoints.append(
                    Endpoint(
                        market=market,
                        statement_type=statement_type,
                        category=category,
                        route=route,
                        url=url,
                    )
                )
    return tuple(endpoints)


TARGET_ENDPOINTS = _endpoint_table()
ENDPOINT_BY_ID = {endpoint.endpoint_id: endpoint for endpoint in TARGET_ENDPOINTS}

# 指紋取自 2026-10-01 獨立保存的 TWSE/TPEx 官方 catalog，只鎖定這 24 個回應契約；
# 每次執行另保存完整 catalog 雜湊，不凍結整份 catalog。
EXPECTED_ROUTE_FINGERPRINTS: Mapping[tuple[str, str, str], str] = {
    ("twse", "income", "basi"): "e089a2c9a553e0b5ab13caf3efd5a24e6f5e907110d14522780e3f45df22275e",
    ("twse", "balance", "basi"): "6474ed44861cc17dd879ed645bec03a4285588a4bc9ba80401497430c7f78145",
    ("twse", "income", "bd"): "f2a53c2162287afcf62434292b7a50ddc98b7be4ac27c4599fc55eadaedfd3c9",
    ("twse", "balance", "bd"): "1e04528dd15d7825e5a88b606470074fd65cd594f6dc285e796832ef6d2f7245",
    ("twse", "income", "ci"): "e73d9998d7f7e8347e47a28dbb2ac1210e56e920ff2c2860715bb3379f2b267e",
    ("twse", "balance", "ci"): "8cb7908b5ba2e6593061e6437e67de5ee6fe5a79a636659df6703dd439b23028",
    ("twse", "income", "fh"): "a84474eab86c350cec45a94b47d79458e9061f3ea8eea132e0a331640fb7de8b",
    ("twse", "balance", "fh"): "3373abf527d935d3993244b8abb06bec5f7ca5f6113c83f0d16025fc02457f1e",
    ("twse", "income", "ins"): "8cc70af1b0bda9f394a35665fa918deebfa03445b35d655a2800fe0e3c17977e",
    ("twse", "balance", "ins"): "dd2be801c31d69c236ab7e3fb2632f09903be2d48911aad7e4a9f6ce1a8729d3",
    ("twse", "income", "mim"): "96ed89ae9e30e8963871ae7b82f78639ef75e0ff5d1939371dd762fc00979428",
    ("twse", "balance", "mim"): "6e3a591d840cc917196ffbcbb3cc13f87e0e02cc1d9cd383dd5d277028e44da4",
    ("tpex", "income", "basi"): "29c31d0848bdf12ac79b9cb16b73f2974fe887e6921b8f66a8031a617b009adb",
    ("tpex", "balance", "basi"): "926bf489ad2cdddd68fce0abf9af21f2b80b6e1dcaf3609e7e0f2c5d7340cf76",
    ("tpex", "income", "bd"): "7e91b2429dc19c1ba21c2e54bca74eb75fc12de62bb7e0514cb789a50e8fd170",
    ("tpex", "balance", "bd"): "b63958b0723a14f3aacf93937014d0500cb85154d1146e11cf01b799bfa8e852",
    ("tpex", "income", "ci"): "fa2015afa4e6e8f42ddd81a9831e98bab96064cacb3952f1de60eed5efb4472f",
    ("tpex", "balance", "ci"): "56946920814eacdbd4aedd246a5476084e889a390ff7468065aa4d8ebe86b58a",
    ("tpex", "income", "fh"): "53e6d16ee3e4fb4f21c357d883e56b5b144e7a62c4202fb592387182b1ad110f",
    ("tpex", "balance", "fh"): "7cd56e60c683b419e9366b6038fda52bb157795de940aa56970366f39a1798d8",
    ("tpex", "income", "ins"): "a9c4470ac360b53a66172c0481b95ab67a6f6b04ffd886bac952fa36328d4fa6",
    ("tpex", "balance", "ins"): "cee0f1f137cbca9af6b301d74841cd179ed334a9960a22a64d6ed916fa338dc0",
    ("tpex", "income", "mim"): "175ee5dc4cf3fb96fee68aea687bf02d729b678734c0c335d3d7d7918a7aaacb",
    ("tpex", "balance", "mim"): "dde4e0d1b62b1d2c2906a134d390e340dd53f6034c1eed7e3afe24f47ea808bf",
}

CATALOG_EXPECTATIONS = {
    "twse": {
        "url": TWSE_CATALOG_URL,
        "swagger": "2.0",
        "host": TWSE_TARGET_HOST,
        "base_path": "/v1",
        "server": "https://openapi.twse.com.tw/v1",
    },
    "tpex": {
        "url": TPEX_CATALOG_URL,
        "openapi_prefix": "3.0.",
        "server": TPEX_TARGET_SERVER,
    },
}


class RawResponse(Protocol):
    def read(self, amount: int, *, decode_content: bool = False) -> bytes: ...


class HttpResponse(Protocol):
    status_code: int
    reason: str
    headers: Mapping[str, Any]
    url: str
    raw: RawResponse

    def close(self) -> None: ...


class HttpSession(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: int,
        stream: bool,
        allow_redirects: bool,
    ) -> HttpResponse: ...


class PreviewSink(Protocol):
    truncated: bool

    def write_record(self, record: Mapping[str, Any]) -> bool: ...


@dataclass(frozen=True)
class BodyRead:
    raw_entity: bytes
    complete: bool
    read_error: str
    limit_reached: bool
    declared_length: int | None


@dataclass(frozen=True)
class HttpCapture:
    requested_url: str
    request_started_at_utc: str
    request_completed_at_utc: str
    http_status: int | None
    http_reason: str
    response_url: str
    content_type: str
    content_encoding: str
    content_length_header: str
    body: BodyRead
    transport_status: str
    error_code: str
    error_reason: str
    decoded_body: bytes | None
    decode_error: str
    decoded_limit_exceeded: bool
    response_json: Any
    request_elapsed_seconds: float
    run_elapsed_seconds: float


class CaptureError(RuntimeError):
    """封閉失敗流程，並保留已寫入的收據。"""


class CaptureWriter:
    def __init__(
        self,
        run_root: Path,
        *,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    ) -> None:
        self.run_root = run_root
        self.disk_usage = disk_usage
        self.aggregate_raw_bytes = 0
        self.metadata_bytes = 0
        self.preview_bytes = 0
        self.files: list[dict[str, Any]] = []

    def write_raw(self, relative_path: str, payload: bytes) -> dict[str, Any]:
        if len(payload) > MAX_ENTITY_BYTES:
            raise CaptureError("raw_entity_exceeds_per_entity_cap")
        if self.aggregate_raw_bytes + len(payload) > MAX_AGGREGATE_RAW_BYTES:
            raise CaptureError("aggregate_raw_cap_exceeded")
        self._check_space(len(payload))
        item = self._write(relative_path, payload, kind="raw_entity", max_bytes=MAX_ENTITY_BYTES)
        self.aggregate_raw_bytes += len(payload)
        return item

    def write_metadata(self, relative_path: str, payload: bytes) -> dict[str, Any]:
        if self.metadata_bytes + len(payload) > MAX_METADATA_BYTES:
            raise CaptureError("metadata_cap_exceeded")
        self._check_space(len(payload))
        item = self._write(relative_path, payload, kind="metadata", max_bytes=MAX_METADATA_BYTES)
        self.metadata_bytes += len(payload)
        return item

    def write_preview_line(self, stream: BinaryIO, payload: bytes) -> bool:
        if len(payload) > MAX_PREVIEW_RECORD_BYTES:
            return False
        if self.preview_bytes + len(payload) > MAX_PREVIEW_BYTES:
            return False
        self._check_space(len(payload))
        stream.write(payload)
        self.preview_bytes += len(payload)
        return True

    def register_preview(self, relative_path: str) -> dict[str, Any]:
        path = self._resolve_existing_path(relative_path)
        info = path.stat()
        if info.st_size > MAX_PREVIEW_BYTES or info.st_size != self.preview_bytes:
            raise CaptureError("preview_readback_size_mismatch")
        body = _bounded_read_file(path, MAX_PREVIEW_BYTES)
        item = {
            "path": relative_path,
            "kind": "numeric_preview_ndjson",
            "bytes": len(body),
            "sha256": _sha256(body),
        }
        self.files.append(item)
        return item

    def _write(self, relative_path: str, payload: bytes, *, kind: str, max_bytes: int) -> dict[str, Any]:
        if len(payload) > max_bytes:
            raise CaptureError(f"{kind}_cap_exceeded")
        path = self._resolve_new_path(relative_path)
        _mkdir_no_links(path.parent)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                view = memoryview(payload)
                written = 0
                while written < len(view):
                    written += stream.write(view[written : written + MAX_READ_CHUNK_BYTES])
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        readback = _bounded_read_file(path, max_bytes)
        if readback != payload:
            raise CaptureError(f"{kind}_readback_mismatch")
        item = {
            "path": relative_path,
            "kind": kind,
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
        self.files.append(item)
        return item

    def _resolve_new_path(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
            raise CaptureError("unsafe_relative_output_path")
        path = self.run_root.joinpath(*pure.parts)
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise CaptureError("output_path_escaped_run_root") from exc
        _assert_no_link_ancestors(path.parent)
        if path.exists() or path.is_symlink():
            raise CaptureError("create_only_output_already_exists")
        return path

    def _resolve_existing_path(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
            raise CaptureError("unsafe_relative_output_path")
        path = self.run_root.joinpath(*pure.parts)
        try:
            path.relative_to(self.run_root)
        except ValueError as exc:
            raise CaptureError("output_path_escaped_run_root") from exc
        _assert_no_link_ancestors(path)
        if not path.is_file():
            raise CaptureError("existing_output_not_regular_file")
        return path

    def _check_space(self, incoming_bytes: int) -> None:
        usage = self.disk_usage(self.run_root)
        if usage.free - incoming_bytes < MIN_FREE_SPACE_BYTES:
            raise CaptureError("minimum_free_space_reserve_would_be_violated")


class PreviewStream:
    def __init__(self, writer: CaptureWriter) -> None:
        self.writer = writer
        self.relative_path = "numeric_preview.ndjson"
        self.writer._check_space(0)
        self.path = writer._resolve_new_path(self.relative_path)
        _mkdir_no_links(self.path.parent)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        self._descriptor = os.open(self.path, flags, 0o600)
        self._stream = os.fdopen(self._descriptor, "wb", closefd=False)
        self.truncated = False
        self.records_written = 0
        self.closed = False

    def write_record(self, record: Mapping[str, Any]) -> bool:
        if self.truncated:
            return False
        payload = _canonical_json(record) + b"\n"
        if not self.writer.write_preview_line(self._stream, payload):
            self.truncated = True
            return False
        self.records_written += 1
        return True

    def close_and_readback(self) -> dict[str, Any]:
        if not self.closed:
            try:
                self._stream.flush()
                os.fsync(self._stream.fileno())
            finally:
                self._stream.close()
                os.close(self._descriptor)
                self.closed = True
        return self.writer.register_preview(self.relative_path)

    def close_preserving_partial(self) -> dict[str, Any] | None:
        if self.closed:
            return next(
                (item for item in self.writer.files if item.get("path") == self.relative_path),
                None,
            )
        try:
            self._stream.flush()
            os.fsync(self._stream.fileno())
        finally:
            self._stream.close()
            os.close(self._descriptor)
            self.closed = True
        try:
            return self.writer.register_preview(self.relative_path)
        except (OSError, ValueError, CaptureError):
            return None


def run_quarterly_openapi_research_capture(
    session: HttpSession,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] | None = None,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    expected_route_fingerprints: Mapping[tuple[str, str, str], str] | None = None,
) -> dict[str, Any]:
    """先保存並驗證兩份 catalog，再各呼叫固定 24 個數值端點一次。

    輸出路徑、時鐘、節流、elapsed 時鐘、磁碟量測及指紋只供隔離測試注入；
    正式 CLI 不提供這些覆寫，固定使用 repo 輸出根與系統實際時鐘。
    """

    now = clock or (lambda: datetime.now(timezone.utc))
    elapsed_clock = monotonic or time.monotonic
    expected = expected_route_fingerprints or EXPECTED_ROUTE_FINGERPRINTS
    if len(TARGET_ENDPOINTS) != 24 or len(expected) != 24:
        raise CaptureError("fixed_route_allowlist_invariant_failed")
    run_start = _aware_utc_text(now())
    run_started_monotonic = elapsed_clock()
    run_id = f"quarterly-openapi-{datetime.fromisoformat(run_start.replace('Z', '+00:00')).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex}"
    output_root = Path(output_root)
    _mkdir_no_links(output_root)
    run_root = output_root / run_id
    run_root.mkdir(mode=0o700, exist_ok=False)
    writer = CaptureWriter(run_root, disk_usage=disk_usage)
    request_counter = 0
    catalog_results: dict[str, HttpCapture] = {}
    catalog_descriptors: dict[str, dict[str, Any]] = {}
    endpoint_summaries: list[dict[str, Any]] = []
    catalog_failures: list[dict[str, str]] = []
    terminal_status = "blocked_catalog_contract_or_transport"
    preview: PreviewStream | None = None
    preview_summary: dict[str, Any] | None = None
    try:
        writer._check_space(0)
        started = {
        "schema_version": "mops-quarterly-openapi-research-run-start.v1",
        "run_id": run_id,
        "started_at_utc": run_start,
        "fixed_request_plan": {
            "catalog_requests": 2,
            "numeric_requests_after_catalog_pass": 24,
            "total_max_requests": 26,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "max_request_elapsed_seconds": MAX_REQUEST_ELAPSED_SECONDS,
            "max_run_elapsed_seconds": MAX_RUN_ELAPSED_SECONDS,
            "retry_count": 0,
            "pacing_seconds_between_requests": REQUEST_PACING_SECONDS,
            "redirects_followed": False,
        },
        "eligibility": _ineligibility_flags(),
        }
        writer.write_metadata("run_started.json", _canonical_json(started))
        catalog_raw_custody_failed = False
        run_budget_exhausted = False
        elapsed_budget_status = ""
        for market in ("twse", "tpex"):
            if catalog_raw_custody_failed:
                break
            if not _ready_for_next_request(
                requests_made=request_counter,
                run_started_monotonic=run_started_monotonic,
                monotonic=elapsed_clock,
                sleep=sleep,
            ):
                run_budget_exhausted = True
                elapsed_budget_status = "run_elapsed_budget_exceeded"
                break
            request_counter += 1
            request_started_monotonic = elapsed_clock()
            expectation = CATALOG_EXPECTATIONS[market]
            result, receipt = _capture_one_request(
                session,
                url=str(expectation["url"]),
                request_id=f"catalog_{market}",
                request_index=request_counter,
                run_id=run_id,
                clock=now,
                writer=writer,
                monotonic=elapsed_clock,
                request_started_monotonic=request_started_monotonic,
                run_started_monotonic=run_started_monotonic,
            )
            catalog_results[market] = result
            _persist_request(writer, request_id=f"catalog_{market}", body=result.body, receipt=receipt)
            raw_receipt = receipt.get("raw_body", {})
            if (
                isinstance(raw_receipt, Mapping)
                and int(raw_receipt.get("bytes", 0) or 0) > 0
                and raw_receipt.get("saved") is not True
            ):
                catalog_raw_custody_failed = True
            if result.error_code in {"request_elapsed_budget_exceeded", "run_elapsed_budget_exceeded"}:
                elapsed_budget_status = result.error_code
                break

        for market in ("twse", "tpex"):
            if market not in catalog_results:
                reason = (
                    elapsed_budget_status or "run_elapsed_budget_exceeded"
                    if run_budget_exhausted or elapsed_budget_status
                    else "not_requested_after_custody_failure"
                )
                catalog_failures.append({"market": market, "reason": reason})
                continue
            capture = catalog_results[market]
            if capture.transport_status != "http_json_ok" or capture.response_json is None:
                catalog_failures.append(
                    {"market": market, "reason": capture.error_code or capture.transport_status}
                )
                continue
            try:
                descriptor = validate_catalog_document(
                    market,
                    capture.response_json,
                    expected_route_fingerprints=expected,
                )
            except (TypeError, ValueError, KeyError, RecursionError) as exc:
                catalog_failures.append(
                    {"market": market, "reason": _bounded_text(f"{type(exc).__name__}:{exc}", 512)}
                )
            else:
                catalog_descriptors[market] = descriptor
        validation_record = {
            "schema_version": "mops-quarterly-openapi-catalog-validation.v1",
            "run_id": run_id,
            "catalogs_validated": sorted(catalog_descriptors),
            "target_contract_count": sum(
                len(item.get("targets", [])) for item in catalog_descriptors.values()
            ),
            "catalog_hashes": {
                market: _sha256(catalog_results[market].body.raw_entity)
                for market in ("twse", "tpex")
                if market in catalog_results and catalog_results[market].body.raw_entity
            },
            "failures": catalog_failures,
        }
        writer.write_metadata("catalog_validation.json", _canonical_json(validation_record))
        if elapsed_budget_status:
            terminal_status = elapsed_budget_status
        elif run_budget_exhausted or _run_elapsed_exceeded(run_started_monotonic, elapsed_clock):
            run_budget_exhausted = True
            elapsed_budget_status = "run_elapsed_budget_exceeded"
            terminal_status = elapsed_budget_status
        elif catalog_failures or set(catalog_descriptors) != {"twse", "tpex"}:
            terminal_status = "blocked_catalog_contract_or_transport"
        else:
            preview = PreviewStream(writer)
            seen_identities: dict[tuple[str, str, str, str], set[str]] = {}
            seen_row_counts: dict[tuple[str, str, str, str], int] = {}
            any_numeric_review = False
            for endpoint in TARGET_ENDPOINTS:
                if not _ready_for_next_request(
                    requests_made=request_counter,
                    run_started_monotonic=run_started_monotonic,
                    monotonic=elapsed_clock,
                    sleep=sleep,
                ):
                    run_budget_exhausted = True
                    elapsed_budget_status = "run_elapsed_budget_exceeded"
                    break
                request_counter += 1
                request_started_monotonic = elapsed_clock()
                capture, receipt = _capture_one_request(
                    session,
                    url=endpoint.url,
                    request_id=endpoint.endpoint_id,
                    request_index=request_counter,
                    run_id=run_id,
                    clock=now,
                    writer=writer,
                    monotonic=elapsed_clock,
                    request_started_monotonic=request_started_monotonic,
                    run_started_monotonic=run_started_monotonic,
                )
                _persist_request(
                    writer,
                    request_id=endpoint.endpoint_id,
                    body=capture.body,
                    receipt=receipt,
                )
                target_schema = _target_schema(catalog_descriptors[endpoint.market], endpoint)
                endpoint_summary = _inspect_numeric_response(
                    endpoint,
                    capture,
                    run_id,
                    target_schema,
                    preview,
                    seen_identities,
                    seen_row_counts,
                )
                endpoint_summary["request_index"] = request_counter
                endpoint_summary["response_raw_sha256"] = (
                    _sha256(capture.body.raw_entity) if capture.body.raw_entity else None
                )
                endpoint_summary["observed_at_utc"] = capture.request_completed_at_utc
                endpoint_summary["request_elapsed_seconds"] = capture.request_elapsed_seconds
                endpoint_summary["run_elapsed_seconds"] = capture.run_elapsed_seconds
                endpoint_summaries.append(endpoint_summary)
                if endpoint_summary["status"] in {
                    "transport_failure",
                    "entity_or_decode_limit",
                    "json_parse_failure",
                    "schema_review_required",
                    "identity_review_required",
                    "key_review_required",
                }:
                    any_numeric_review = True
                raw_receipt = receipt.get("raw_body", {})
                if (
                    isinstance(raw_receipt, Mapping)
                    and int(raw_receipt.get("bytes", 0) or 0) > 0
                    and raw_receipt.get("saved") is not True
                ):
                    any_numeric_review = True
                    endpoint_summary["status"] = "transport_failure"
                    endpoint_summary["error_code"] = "raw_entity_custody_failed"
                    break
                if capture.error_code in {"request_elapsed_budget_exceeded", "run_elapsed_budget_exceeded"}:
                    elapsed_budget_status = capture.error_code
                    run_budget_exhausted = capture.error_code == "run_elapsed_budget_exceeded"
                    break
            preview_item = preview.close_and_readback()
            preview_summary = {
                **preview_item,
                "records_written": preview.records_written,
                "truncated": preview.truncated,
                "preview_is_complete_dataset": False,
            }
            if elapsed_budget_status:
                terminal_status = elapsed_budget_status
            elif run_budget_exhausted or _run_elapsed_exceeded(run_started_monotonic, elapsed_clock):
                elapsed_budget_status = "run_elapsed_budget_exceeded"
                terminal_status = elapsed_budget_status
            else:
                terminal_status = (
                    "completed_with_review_items"
                    if any_numeric_review
                    else "completed_observation_only"
                )

        result_summary = {
            "schema_version": "mops-quarterly-openapi-research-run.v1",
            "run_id": run_id,
            "run_root": str(run_root),
            "started_at_utc": run_start,
            "capture_phase_completed_at_utc": _aware_utc_text(now()),
            "capture_phase_elapsed_seconds": max(0.0, elapsed_clock() - run_started_monotonic),
            "status": "pending_final_readback",
            "capture_outcome": terminal_status,
            "requests_made": request_counter,
            "catalog_request_count": len(catalog_results),
            "numeric_request_count": len(endpoint_summaries),
            "catalog_validation": validation_record,
            "catalog_baseline_provenance": CATALOG_BASELINE_PROVENANCE,
            "catalogs": {
                market: _catalog_run_summary(catalog_results[market], catalog_descriptors.get(market))
                if market in catalog_results
                else {
                    "requested_url": CATALOG_EXPECTATIONS[market]["url"],
                    "transport_status": "not_requested_after_custody_failure",
                    "error_code": "not_requested_after_custody_failure",
                }
                for market in ("twse", "tpex")
            },
            "endpoint_summaries": endpoint_summaries,
            "preview": preview_summary,
            "artifact_files": list(writer.files),
            "budgets": {
                "raw_entity_bytes_total": writer.aggregate_raw_bytes,
                "raw_entity_cap_bytes_total": MAX_AGGREGATE_RAW_BYTES,
                "preview_bytes": writer.preview_bytes,
                "preview_cap_bytes": MAX_PREVIEW_BYTES,
                "metadata_bytes_before_summary": writer.metadata_bytes,
                "metadata_cap_bytes": MAX_METADATA_BYTES,
                "per_entity_raw_cap_bytes": MAX_ENTITY_BYTES,
                "per_entity_decoded_cap_bytes": MAX_DECODED_BYTES,
                "free_space_reserve_bytes": MIN_FREE_SPACE_BYTES,
                "request_elapsed_budget_seconds": MAX_REQUEST_ELAPSED_SECONDS,
                "run_elapsed_budget_seconds": MAX_RUN_ELAPSED_SECONDS,
                "budget_stops_subsequent_requests": True,
                "single_blocking_read_may_overrun_budget": True,
            },
            "coverage": {
                "catalog_contract_passed": set(catalog_descriptors) == {"twse", "tpex"}
                and not catalog_failures,
                "numeric_endpoints_attempted": len(endpoint_summaries),
                "numeric_route_attempts_complete": len(endpoint_summaries) == 24,
                "issuer_identity_verified": False,
                "official_denominator_bound": False,
                "issuer_coverage_complete": False,
                "full_market_coverage_verified": False,
                "income_statement_scope": True,
                "balance_sheet_scope": True,
                "cash_flow_statement_scope": False,
                "equity_change_statement_scope": False,
                "cross_route_records_deduplicated": False,
            },
            "time_policy": {
                "observed_at": "actual per-response HTTP completion time in UTC",
                "available_at": None,
                "available_at_reason": "numeric OpenAPI rows do not establish row-level availability time",
                "source_reported_date_is_available_at": False,
                "future_reported_period_values_in_preview": "withheld",
                "historical_pit_eligible": False,
            },
            "eligibility": _ineligibility_flags(),
        }
        writer.write_metadata("run_summary.json", _canonical_json(result_summary))
        readback = verify_capture_run(run_root, expected_route_fingerprints=expected)
        verified_at = _aware_utc_text(now())
        final_status = _terminal_status_after_capture(
            terminal_status,
            readback=readback,
            requests_made=request_counter,
            numeric_count=len(endpoint_summaries),
        )
        materialized_at = _aware_utc_text(now())
        terminal: dict[str, Any] = {
            "schema_version": "mops-quarterly-openapi-research-terminal.v1",
            "run_id": run_id,
            "run_root": str(run_root),
            "status": final_status,
            "captured_at_utc": _aware_utc_text(now()),
            "verification_completed_at_utc": verified_at,
            "research_artifact_materialized_at_utc": materialized_at,
            "research_artifact_readback_verified_at_utc": verified_at,
            "candidate_available_at": None,
            "candidate_available_at_reason": "source disclosure availability is unknown; artifact custody time is recorded separately",
            "readback": readback,
            "formal_pit_eligible": False,
            "issuer_coverage_complete": False,
        }
        writer.write_metadata("collector_terminal.json", _canonical_json(terminal))
        return {**result_summary, "status": final_status, "terminal": terminal}
    except Exception as exc:
        if preview is not None:
            preview.close_preserving_partial()
        terminal = {
            "schema_version": "mops-quarterly-openapi-research-terminal.v1",
            "run_id": run_id,
            "failed_at_utc": _aware_utc_text(now()),
            "research_artifact_materialized_at_utc": None,
            "research_artifact_readback_verified_at_utc": None,
            "candidate_available_at": None,
            "status": "collector_internal_error",
            "error_type": type(exc).__name__,
            "error_reason": _bounded_text(str(exc), 512),
            "requests_made": request_counter,
            "artifact_files": list(writer.files),
            "eligibility": _ineligibility_flags(),
        }
        terminal_path = run_root / "collector_terminal.json"
        if not terminal_path.exists() and not terminal_path.is_symlink():
            writer.write_metadata("collector_terminal.json", _canonical_json(terminal))
        raise


def validate_catalog_document(
    market: str,
    payload: Any,
    *,
    expected_route_fingerprints: Mapping[tuple[str, str, str], str] | None = None,
) -> dict[str, Any]:
    """驗證固定路由、主機或伺服器、response ref 與欄位結構。"""

    expected = expected_route_fingerprints or EXPECTED_ROUTE_FINGERPRINTS
    if market not in {"twse", "tpex"}:
        raise ValueError("unsupported_catalog_market")
    if not isinstance(payload, Mapping):
        raise ValueError("catalog_root_not_object")
    paths = payload.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("catalog_paths_missing")

    components: Mapping[str, Any] = {}
    if market == "twse":
        if payload.get("swagger") != "2.0":
            raise ValueError("twse_swagger_version_drift")
        if payload.get("host") != TWSE_TARGET_HOST or payload.get("basePath") != "/v1":
            raise ValueError("twse_catalog_host_or_basepath_drift")
        if "https" not in payload.get("schemes", ["https"]):
            raise ValueError("twse_catalog_https_scheme_missing")
    else:
        version = str(payload.get("openapi", ""))
        if not version.startswith("3.0."):
            raise ValueError("tpex_openapi_version_drift")
        servers = payload.get("servers")
        if not isinstance(servers, list) or not any(
            isinstance(server, Mapping) and server.get("url") == TPEX_TARGET_SERVER
            for server in servers
        ):
            raise ValueError("tpex_catalog_server_drift")
        raw_components = payload.get("components")
        if not isinstance(raw_components, Mapping) or not isinstance(
            raw_components.get("schemas"), Mapping
        ):
            raise ValueError("tpex_catalog_schemas_missing")
        components = raw_components["schemas"]  # type: ignore[assignment]

    targets: list[dict[str, Any]] = []
    market_endpoints = [item for item in TARGET_ENDPOINTS if item.market == market]
    for endpoint in market_endpoints:
        operation_raw = paths.get(endpoint.route)
        if not isinstance(operation_raw, Mapping):
            raise ValueError(f"catalog_target_route_missing:{endpoint.route}")
        operation = operation_raw.get("get")
        if not isinstance(operation, Mapping):
            raise ValueError(f"catalog_target_get_missing:{endpoint.route}")
        parameters = operation.get("parameters", [])
        if parameters not in (None, []):
            raise ValueError(f"catalog_target_parameters_drift:{endpoint.route}")
        responses = operation.get("responses")
        if not isinstance(responses, Mapping) or not isinstance(responses.get("200"), Mapping):
            raise ValueError(f"catalog_target_200_missing:{endpoint.route}")
        response_200 = responses["200"]
        schema_ref = ""
        if market == "twse":
            schema = response_200.get("schema")
            if not isinstance(schema, Mapping):
                raise ValueError(f"catalog_target_schema_missing:{endpoint.route}")
        else:
            content = response_200.get("content")
            if not isinstance(content, Mapping) or not isinstance(content.get("application/json"), Mapping):
                raise ValueError(f"catalog_target_json_content_missing:{endpoint.route}")
            raw_schema = content["application/json"].get("schema")
            if not isinstance(raw_schema, Mapping):
                raise ValueError(f"catalog_target_schema_missing:{endpoint.route}")
            schema_ref = str(raw_schema.get("$ref", ""))
            expected_ref = _expected_tpex_schema_ref(endpoint)
            if schema_ref != expected_ref:
                raise ValueError(f"catalog_target_schema_ref_drift:{endpoint.route}")
            ref_name = schema_ref.rsplit("/", 1)[-1]
            schema_value = components.get(ref_name)
            if not isinstance(schema_value, Mapping):
                raise ValueError(f"catalog_target_schema_ref_unresolved:{endpoint.route}")
            schema = schema_value
        properties = schema.get("properties")
        if schema.get("type") != "object" or not isinstance(properties, Mapping):
            raise ValueError(f"catalog_target_object_schema_drift:{endpoint.route}")
        if any(
            not isinstance(name, str)
            or not isinstance(prop, Mapping)
            or prop.get("type") != "string"
            for name, prop in properties.items()
        ):
            raise ValueError(f"catalog_target_property_type_drift:{endpoint.route}")
        descriptor = {
            "market": endpoint.market,
            "route": endpoint.route,
            "method": "get",
            "parameters": list(parameters or []),
            "schema_ref": schema_ref,
            "schema": schema,
        }
        fingerprint = _sha256(_canonical_json(descriptor))
        pin = expected.get((endpoint.market, endpoint.statement_type, endpoint.category))
        if pin is None or fingerprint != pin:
            raise ValueError(f"catalog_target_schema_fingerprint_drift:{endpoint.route}")
        targets.append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "route": endpoint.route,
                "schema_ref": schema_ref or None,
                "schema_sha256": fingerprint,
                "property_names": list(properties.keys()),
                "property_count": len(properties),
                "required_properties": list(schema.get("required", []))
                if isinstance(schema.get("required", []), list)
                else [],
            }
        )
    return {
        "market": market,
        "catalog_contract_version": "2026-10-01-target-route-schema-v1",
        "targets": targets,
        "target_route_count": len(targets),
    }


def verify_capture_run(
    run_root: Path,
    *,
    expected_route_fingerprints: Mapping[tuple[str, str, str], str] | None = None,
) -> dict[str, Any]:
    """以 bounded read 重驗收據、原始回應、catalog 契約與預覽列。"""

    root = Path(run_root)
    _assert_no_link_ancestors(root)
    if _is_link_or_junction(root) or not root.is_dir():
        raise ValueError("run_root_must_be_regular_directory")
    summary_path = root / "run_summary.json"
    summary_raw = _bounded_read_file(summary_path, MAX_METADATA_BYTES)
    summary = _strict_json_loads(summary_raw.decode("utf-8"))
    if not isinstance(summary, Mapping) or summary.get("schema_version") != "mops-quarterly-openapi-research-run.v1":
        raise ValueError("run_summary_invalid")
    if summary.get("status") != "pending_final_readback":
        raise ValueError("run_summary_not_awaiting_readback")
    files = summary.get("artifact_files")
    if not isinstance(files, list):
        raise ValueError("run_summary_artifact_files_missing")
    verified: list[str] = []
    raw_total = 0
    metadata_total = len(summary_raw)
    preview_total = 0
    file_by_path: dict[str, tuple[dict[str, Any], Path]] = {}
    receipts: dict[str, dict[str, Any]] = {}
    catalog_descriptors: dict[str, dict[str, Any]] = {}
    raw_endpoint_summaries = summary.get("endpoint_summaries")
    if not isinstance(raw_endpoint_summaries, list):
        raise ValueError("endpoint_summary_list_missing")
    endpoint_summary_by_id = {
        str(item.get("endpoint_id")): item
        for item in raw_endpoint_summaries
        if isinstance(item, Mapping) and item.get("endpoint_id") is not None
    }
    for item in files:
        if not isinstance(item, Mapping):
            raise ValueError("artifact_entry_not_object")
        relative = item.get("path")
        kind = item.get("kind")
        if not isinstance(relative, str) or not isinstance(kind, str):
            raise ValueError("artifact_entry_missing_identity")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("artifact_relative_path_invalid")
        path = root.joinpath(*pure.parts)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("artifact_path_escaped_run_root") from exc
        _assert_no_link_ancestors(path)
        data = _bounded_read_file(path, _limit_for_kind(kind))
        if len(data) != item.get("bytes") or _sha256(data) != item.get("sha256"):
            raise ValueError(f"artifact_hash_or_size_mismatch:{relative}")
        if kind == "raw_entity":
            raw_total += len(data)
            if raw_total > MAX_AGGREGATE_RAW_BYTES:
                raise ValueError("run_raw_aggregate_cap_exceeded")
        elif kind == "metadata":
            metadata_total += len(data)
            if metadata_total > MAX_METADATA_BYTES:
                raise ValueError("run_metadata_cap_exceeded")
        elif kind == "numeric_preview_ndjson":
            preview_total += len(data)
            if preview_total > MAX_PREVIEW_BYTES:
                raise ValueError("run_preview_cap_exceeded")
        file_by_path[relative] = (dict(item), path)
        if kind == "metadata" and relative.endswith("/receipt.json"):
            receipt = _strict_json_loads(data.decode("utf-8"))
            if not isinstance(receipt, Mapping):
                raise ValueError(f"request_receipt_not_object:{relative}")
            request_id = receipt.get("request_id")
            if not isinstance(request_id, str) or relative != f"{request_id}/receipt.json":
                raise ValueError(f"request_receipt_path_binding_mismatch:{relative}")
            if request_id in receipts:
                raise ValueError(f"duplicate_request_receipt:{request_id}")
            if receipt.get("run_id") != summary.get("run_id"):
                raise ValueError(f"request_receipt_run_binding_mismatch:{request_id}")
            receipts[request_id] = dict(receipt)
        verified.append(relative)

    numeric_count = summary.get("numeric_request_count")
    if not isinstance(numeric_count, int) or numeric_count < 0 or numeric_count > len(TARGET_ENDPOINTS):
        raise ValueError("numeric_request_count_invalid")
    if summary.get("requests_made") != len(receipts):
        raise ValueError("request_count_receipt_count_mismatch")
    request_indexes: set[int] = set()
    for request_id, receipt in receipts.items():
        if request_id in {"catalog_twse", "catalog_tpex"}:
            expected_url = CATALOG_EXPECTATIONS[request_id.removeprefix("catalog_")]["url"]
        elif request_id in ENDPOINT_BY_ID:
            expected_url = ENDPOINT_BY_ID[request_id].url
        else:
            expected_url = None
        if expected_url is None or receipt.get("requested_url") != expected_url:
            raise ValueError(f"request_url_not_allowlisted:{request_id}")
        if receipt.get("attempt_number") != 1 or receipt.get("retry_count") != 0:
            raise ValueError(f"request_retry_contract_drift:{request_id}")
        request_elapsed = receipt.get("request_elapsed_seconds")
        run_elapsed = receipt.get("run_elapsed_seconds")
        request_elapsed_value = _nonnegative_seconds(request_elapsed)
        run_elapsed_value = _nonnegative_seconds(run_elapsed)
        if (
            not _is_nonnegative_seconds(request_elapsed)
            or not _is_nonnegative_seconds(run_elapsed)
            or run_elapsed_value < request_elapsed_value
        ):
            raise ValueError(f"request_elapsed_receipt_invalid:{request_id}")
        if receipt.get("error_code") == "request_elapsed_budget_exceeded" and request_elapsed_value < MAX_REQUEST_ELAPSED_SECONDS:
            raise ValueError(f"request_elapsed_budget_receipt_mismatch:{request_id}")
        if receipt.get("error_code") == "run_elapsed_budget_exceeded" and run_elapsed_value < MAX_RUN_ELAPSED_SECONDS:
            raise ValueError(f"run_elapsed_budget_receipt_mismatch:{request_id}")
        index = receipt.get("request_index")
        if not isinstance(index, int) or index in request_indexes:
            raise ValueError(f"request_index_invalid:{request_id}")
        request_indexes.add(index)
        raw_meta = receipt.get("raw_body")
        if not isinstance(raw_meta, Mapping):
            raise ValueError(f"raw_body_receipt_missing:{request_id}")
        if raw_meta.get("saved") is True:
            raw_relative = raw_meta.get("path")
            if not isinstance(raw_relative, str) or raw_relative != f"{request_id}/response_body.raw":
                raise ValueError(f"raw_body_path_binding_mismatch:{request_id}")
            file_record = file_by_path.get(raw_relative)
            if file_record is None or file_record[0].get("kind") != "raw_entity":
                raise ValueError(f"raw_body_artifact_not_manifested:{request_id}")
            raw_body = _bounded_read_file(file_record[1], MAX_ENTITY_BYTES)
            if (
                raw_meta.get("sha256") != _sha256(raw_body)
                or receipt.get("raw_body_sha256") != _sha256(raw_body)
                or receipt.get("raw_body_bytes") != len(raw_body)
            ):
                raise ValueError(f"raw_body_receipt_hash_mismatch:{request_id}")
            if receipt.get("raw_body_complete") is True:
                decoded: bytes | None = None
                expected_decoded_hash = receipt.get("decoded_body_sha256")
                if expected_decoded_hash is not None:
                    decoded, decode_error, limit_exceeded = _decode_entity(
                        raw_body,
                        content_encoding=str(receipt.get("content_encoding", "")),
                    )
                    if decode_error or limit_exceeded or decoded is None:
                        raise ValueError(f"raw_body_decode_readback_failed:{request_id}")
                    if expected_decoded_hash != _sha256(decoded):
                        raise ValueError(f"decoded_body_hash_mismatch:{request_id}")
                elif receipt.get("json_parse_status") != "not_parsed":
                    raise ValueError(f"decoded_body_hash_missing:{request_id}")
                if receipt.get("transport_status") == "http_json_ok":
                    if expected_decoded_hash is None or receipt.get("json_parse_status") != "parsed":
                        raise ValueError(f"successful_http_json_missing_decode_receipt:{request_id}")
                    if decoded is None:
                        raise ValueError(f"successful_http_json_body_missing:{request_id}")
                    parsed = _strict_json_loads(decoded.decode("utf-8-sig", errors="strict"))
                    if request_id.startswith("catalog_"):
                        market = request_id.removeprefix("catalog_")
                        try:
                            descriptor = validate_catalog_document(
                                market,
                                parsed,
                                expected_route_fingerprints=expected_route_fingerprints,
                            )
                        except (TypeError, ValueError, KeyError):
                            validation = summary.get("catalog_validation", {})
                            validated = validation.get("catalogs_validated", []) if isinstance(validation, Mapping) else []
                            if market in validated:
                                raise ValueError(f"catalog_contract_readback_mismatch:{market}")
                        else:
                            catalog_descriptors[market] = descriptor
                    elif not isinstance(parsed, list):
                        endpoint_summary = endpoint_summary_by_id.get(request_id, {})
                        if not isinstance(endpoint_summary, Mapping) or endpoint_summary.get("status") != "schema_review_required":
                            raise ValueError(f"numeric_response_root_not_row_array:{request_id}")
                    else:
                        numeric_summary = endpoint_summary_by_id.get(request_id)
                        if isinstance(numeric_summary, Mapping) and numeric_summary.get("row_count") != len(parsed):
                            raise ValueError(f"numeric_response_row_count_mismatch:{request_id}")
        elif int(raw_meta.get("bytes", 0) or 0) > 0:
            if receipt.get("error_code") != "raw_entity_custody_failed":
                raise ValueError(f"captured_raw_entity_not_saved:{request_id}")

    if request_indexes != set(range(1, len(receipts) + 1)):
        raise ValueError("request_indexes_not_contiguous")
    ordered_request_ids = [
        request_id
        for request_id, _ in sorted(
            receipts.items(), key=lambda item: int(item[1]["request_index"])
        )
    ]
    catalog_prefix = ["catalog_twse", "catalog_tpex"][: min(2, len(ordered_request_ids))]
    numeric_receipt_count = max(0, len(ordered_request_ids) - 2)
    if numeric_receipt_count != numeric_count:
        raise ValueError("numeric_request_count_receipt_mismatch")
    expected_order = catalog_prefix + [
        endpoint.endpoint_id for endpoint in TARGET_ENDPOINTS[:numeric_receipt_count]
    ]
    if ordered_request_ids != expected_order:
        raise ValueError("request_receipts_not_fixed_plan_prefix")
    if numeric_receipt_count and len(catalog_prefix) != 2:
        raise ValueError("numeric_request_before_both_catalogs")
    if summary.get("catalog_request_count") != sum(
        1 for request_id in receipts if request_id in {"catalog_twse", "catalog_tpex"}
    ):
        raise ValueError("catalog_request_count_receipt_mismatch")
    capture_outcome = summary.get("capture_outcome")
    if capture_outcome in {
        "completed_observation_only",
        "completed_with_review_items",
        "completed_with_endpoint_failures",
        "run_elapsed_budget_exceeded",
        "request_elapsed_budget_exceeded",
    }:
        if capture_outcome == "completed_observation_only" and len(receipts) != 26:
            raise ValueError("successful_observation_did_not_attempt_all_routes")
        if capture_outcome == "completed_observation_only" and any(
            receipt.get("transport_status") != "http_json_ok" for receipt in receipts.values()
        ):
            raise ValueError("successful_observation_contains_transport_failure")
    elif int(summary.get("numeric_request_count", 0) or 0) != 0:
        raise ValueError("catalog_blocked_but_numeric_request_was_made")

    endpoint_summaries = raw_endpoint_summaries
    if not isinstance(endpoint_summaries, list) or len(endpoint_summaries) != int(numeric_count or 0):
        raise ValueError("endpoint_summary_count_mismatch")
    for item in endpoint_summaries:
        if not isinstance(item, Mapping):
            raise ValueError("endpoint_summary_not_object")
        endpoint_id = item.get("endpoint_id")
        if endpoint_id not in receipts or endpoint_id not in ENDPOINT_BY_ID:
            raise ValueError("endpoint_summary_receipt_binding_mismatch")
        receipt = receipts[str(endpoint_id)]
        if item.get("url") != receipt.get("requested_url"):
            raise ValueError("endpoint_summary_url_binding_mismatch")
        if item.get("response_raw_sha256") != receipt.get("raw_body_sha256"):
            raise ValueError("endpoint_summary_raw_hash_binding_mismatch")
        if item.get("observed_at_utc") != receipt.get("request_completed_at_utc"):
            raise ValueError("endpoint_observed_clock_binding_mismatch")
        if item.get("request_elapsed_seconds") != receipt.get("request_elapsed_seconds"):
            raise ValueError("endpoint_request_elapsed_binding_mismatch")
        if item.get("run_elapsed_seconds") != receipt.get("run_elapsed_seconds"):
            raise ValueError("endpoint_run_elapsed_binding_mismatch")
        if item.get("available_at") is not None or item.get("formal_pit_eligible") is not False:
            raise ValueError("endpoint_preview_eligibility_drift")

    _verify_numeric_summaries_against_sources(
        root,
        endpoint_summaries,
        receipts,
        catalog_descriptors,
        run_id=str(summary.get("run_id", "")),
    )

    preview_meta = summary.get("preview")
    if preview_meta is not None:
        if not isinstance(preview_meta, Mapping):
            raise ValueError("preview_summary_invalid")
        preview_path = preview_meta.get("path")
        preview_entry = file_by_path.get(str(preview_path))
        if preview_entry is None or preview_entry[0].get("kind") != "numeric_preview_ndjson":
            raise ValueError("preview_file_missing_from_manifest")
        preview_count, preview_count_by_endpoint = _verify_preview_ndjson(
            preview_entry[1],
            run_root=root,
            run_id=str(summary.get("run_id", "")),
            receipts=receipts,
            catalog_descriptors=catalog_descriptors,
        )
        if preview_count != preview_meta.get("records_written"):
            raise ValueError("preview_record_count_mismatch")
        if any(
            item.get("preview_rows_written") != preview_count_by_endpoint.get(str(item.get("endpoint_id", "")), 0)
            for item in endpoint_summaries
        ):
            raise ValueError("preview_endpoint_count_mismatch")
    elif numeric_count:
        raise ValueError("numeric_capture_preview_missing")

    return {
        "run_id": summary.get("run_id"),
        "artifact_count": len(verified),
        "verified_paths": verified,
        "raw_entity_bytes": raw_total,
        "metadata_bytes_including_summary": metadata_total,
        "preview_bytes": preview_total,
        "issuer_coverage_complete": False,
        "formal_pit_eligible": False,
        "request_receipts_verified": len(receipts),
        "catalog_contracts_revalidated": len([item for item in receipts if item.startswith("catalog_")]),
        "numeric_rows_rechecked": sum(int(item.get("row_count", 0) or 0) for item in endpoint_summaries),
        "preview_rows_rechecked": int((preview_meta or {}).get("records_written", 0))
        if isinstance(preview_meta, Mapping)
        else 0,
    }


def _terminal_status_after_capture(
    capture_outcome: str,
    *,
    readback: Mapping[str, Any],
    requests_made: int,
    numeric_count: int,
) -> str:
    if readback.get("formal_pit_eligible") is not False or readback.get("issuer_coverage_complete") is not False:
        raise CaptureError("readback_eligibility_contract_drift")
    if capture_outcome == "blocked_catalog_contract_or_transport":
        if numeric_count != 0:
            raise CaptureError("catalog_block_did_not_stop_numeric_requests")
        return capture_outcome
    if capture_outcome == "run_elapsed_budget_exceeded":
        return capture_outcome
    if capture_outcome == "request_elapsed_budget_exceeded":
        return capture_outcome
    if capture_outcome == "completed_observation_only" and requests_made == 26 and numeric_count == 24:
        return "completed_observation_only"
    if capture_outcome == "completed_with_review_items" and requests_made == 26 and numeric_count == 24:
        return "completed_with_review_items"
    if numeric_count > 0:
        return "completed_with_endpoint_failures"
    return "blocked_incomplete_request_set"


def _run_elapsed_exceeded(
    run_started_monotonic: float,
    monotonic: Callable[[], float],
) -> bool:
    return max(0.0, monotonic() - run_started_monotonic) >= MAX_RUN_ELAPSED_SECONDS


def _ready_for_next_request(
    *,
    requests_made: int,
    run_started_monotonic: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    if _run_elapsed_exceeded(run_started_monotonic, monotonic):
        return False
    if requests_made:
        sleep(REQUEST_PACING_SECONDS)
        if _run_elapsed_exceeded(run_started_monotonic, monotonic):
            return False
    return True


def _elapsed_budget_error(
    *,
    request_started_monotonic: float,
    run_started_monotonic: float,
    monotonic: Callable[[], float],
) -> str:
    current = monotonic()
    if max(0.0, current - run_started_monotonic) >= MAX_RUN_ELAPSED_SECONDS:
        return "run_elapsed_budget_exceeded"
    if max(0.0, current - request_started_monotonic) >= MAX_REQUEST_ELAPSED_SECONDS:
        return "request_elapsed_budget_exceeded"
    return ""


def _verify_preview_ndjson(
    path: Path,
    *,
    run_root: Path,
    run_id: str,
    receipts: Mapping[str, Mapping[str, Any]],
    catalog_descriptors: Mapping[str, Mapping[str, Any]],
) -> tuple[int, dict[str, int]]:
    _assert_no_link_ancestors(path)
    before = path.lstat()
    if (
        _is_link_or_junction(path)
        or not stat.S_ISREG(before.st_mode)
        or before.st_size > MAX_PREVIEW_BYTES
        or before.st_nlink != 1
    ):
        raise ValueError("preview_path_not_bounded_regular_file")
    records_seen = 0
    by_endpoint: dict[str, int] = {}
    bytes_seen = 0
    order = {endpoint.endpoint_id: index for index, endpoint in enumerate(TARGET_ENDPOINTS)}
    active_endpoint = ""
    active_payload: list[Any] = []
    previous_endpoint_order = -1
    last_row_by_endpoint: dict[str, int] = {}
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened_before = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(opened_before):
            raise ValueError("preview_changed_before_readback")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            line_number = 0
            while True:
                line = stream.readline(MAX_PREVIEW_RECORD_BYTES + 1)
                if not line:
                    break
                line_number += 1
                if len(line) > MAX_PREVIEW_RECORD_BYTES:
                    raise ValueError("preview_line_or_file_cap_exceeded")
                bytes_seen += len(line)
                if bytes_seen > MAX_PREVIEW_BYTES:
                    raise ValueError("preview_line_or_file_cap_exceeded")
                if not line.strip():
                    continue
                record = _strict_json_loads(line.decode("utf-8"))
                if not isinstance(record, Mapping):
                    raise ValueError(f"preview_record_not_object:{line_number}")
                endpoint_id = str(record.get("endpoint_id", ""))
                receipt = receipts.get(endpoint_id)
                endpoint = ENDPOINT_BY_ID.get(endpoint_id)
                if receipt is None or endpoint is None or record.get("run_id") != run_id:
                    raise ValueError(f"preview_run_or_endpoint_binding_mismatch:{line_number}")
                current_order = order[endpoint_id]
                if current_order < previous_endpoint_order:
                    raise ValueError("preview_endpoint_order_regressed")
                if endpoint_id != active_endpoint:
                    active_endpoint = endpoint_id
                    previous_endpoint_order = current_order
                    active_payload = _load_numeric_payload_for_readback(run_root, receipt)
                expected = _expected_preview_from_source(
                    endpoint,
                    receipt,
                    record,
                    active_payload,
                    catalog_descriptors,
                )
                if not expected:
                    raise ValueError(f"preview_row_does_not_match_source:{line_number}")
                row_number = record.get("row_number")
                previous_row = last_row_by_endpoint.get(endpoint_id, 0)
                if not isinstance(row_number, int) or row_number <= previous_row:
                    raise ValueError(f"preview_row_number_invalid_or_duplicated:{line_number}")
                last_row_by_endpoint[endpoint_id] = row_number
                by_endpoint[endpoint_id] = by_endpoint.get(endpoint_id, 0) + 1
                records_seen += 1
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if (
        _file_identity(before) != _file_identity(opened_after)
        or _file_identity(before) != _file_identity(after)
        or after.st_nlink != 1
        or _is_link_or_junction(path)
    ):
        raise ValueError("preview_changed_during_readback")
    return records_seen, by_endpoint


def _verify_numeric_summaries_against_sources(
    run_root: Path,
    endpoint_summaries: Sequence[Mapping[str, Any]],
    receipts: Mapping[str, Mapping[str, Any]],
    catalog_descriptors: Mapping[str, Mapping[str, Any]],
    *,
    run_id: str,
) -> None:
    seen_identities: dict[tuple[str, str, str, str], set[str]] = {}
    seen_row_counts: dict[tuple[str, str, str, str], int] = {}
    raw_readback_total = 0
    expected_fields = (
        "status",
        "row_count",
        "reported_period_counts",
        "missing_or_invalid_key_rows",
        "identity_alias_conflict_rows",
        "schema_drift_rows",
        "invalid_decimal_field_count",
        "missing_value_field_count",
        "cross_category_same_market_period_identity_rows",
        "repeated_reported_identity_rows_preserved",
        "future_period_rows_with_values_withheld",
        "official_no_data",
        "full_market_complete",
        "diagnostic_samples",
    )

    class _DiscardPreview:
        truncated = False

        def write_record(self, record: Mapping[str, Any]) -> bool:
            del record
            return True

    for endpoint, summary in zip(TARGET_ENDPOINTS, endpoint_summaries, strict=False):
        receipt = receipts.get(endpoint.endpoint_id)
        if receipt is None:
            raise ValueError(f"numeric_summary_receipt_missing:{endpoint.endpoint_id}")
        raw_meta = receipt.get("raw_body")
        raw_body = b""
        if isinstance(raw_meta, Mapping) and raw_meta.get("saved") is True:
            raw_body = _read_raw_body_for_readback(run_root, receipt)
            raw_readback_total += len(raw_body)
            if raw_readback_total > MAX_AGGREGATE_RAW_BYTES:
                raise ValueError("numeric_readback_aggregate_cap_exceeded")
        decoded: bytes | None = None
        response_json: Any = None
        if receipt.get("transport_status") == "http_json_ok":
            decoded, decode_error, decode_overflow = _decode_entity(
                raw_body,
                content_encoding=str(receipt.get("content_encoding", "")),
            )
            if decoded is None or decode_error or decode_overflow:
                raise ValueError(f"numeric_readback_decode_failed:{endpoint.endpoint_id}")
            try:
                response_json = _strict_json_loads(decoded.decode("utf-8-sig", errors="strict"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ValueError(f"numeric_readback_json_failed:{endpoint.endpoint_id}") from exc
        capture = HttpCapture(
            requested_url=str(receipt.get("requested_url", "")),
            request_started_at_utc=str(receipt.get("request_started_at_utc", "")),
            request_completed_at_utc=str(receipt.get("request_completed_at_utc", "")),
            http_status=_safe_status(receipt.get("http_status")),
            http_reason=str(receipt.get("http_reason", "")),
            response_url=str(receipt.get("response_url") or ""),
            content_type=str(receipt.get("content_type", "")),
            content_encoding=str(receipt.get("content_encoding", "")),
            content_length_header=str(receipt.get("content_length_header", "")),
            body=BodyRead(
                raw_entity=raw_body,
                complete=bool(receipt.get("raw_body_complete")),
                read_error=str(receipt.get("raw_body_read_error") or ""),
                limit_reached=bool(receipt.get("raw_body_limit_reached")),
                declared_length=_safe_status(receipt.get("declared_content_length")),
            ),
            transport_status=str(receipt.get("transport_status", "http_or_body_failure")),
            error_code=str(receipt.get("error_code") or ""),
            error_reason=str(receipt.get("error_reason") or ""),
            decoded_body=decoded,
            decode_error="",
            decoded_limit_exceeded=False,
            response_json=response_json,
            request_elapsed_seconds=_nonnegative_seconds(receipt.get("request_elapsed_seconds")),
            run_elapsed_seconds=_nonnegative_seconds(receipt.get("run_elapsed_seconds")),
        )
        schema = _target_schema(catalog_descriptors[endpoint.market], endpoint)
        derived = _inspect_numeric_response(
            endpoint,
            capture,
            run_id,
            schema,
            _DiscardPreview(),
            seen_identities,
            seen_row_counts,
        )
        for key in expected_fields:
            if summary.get(key) != derived.get(key):
                raise ValueError(f"numeric_summary_source_mismatch:{endpoint.endpoint_id}:{key}")


def _load_numeric_payload_for_readback(
    run_root: Path,
    receipt: Mapping[str, Any],
) -> list[Any]:
    raw_body = _read_raw_body_for_readback(run_root, receipt)
    decoded, decode_error, decoded_limit = _decode_entity(
        raw_body,
        content_encoding=str(receipt.get("content_encoding", "")),
    )
    if decoded is None or decode_error or decoded_limit:
        raise ValueError("preview_source_raw_decode_failed")
    payload = _strict_json_loads(decoded.decode("utf-8-sig", errors="strict"))
    if not isinstance(payload, list):
        raise ValueError("preview_source_payload_not_array")
    return payload


def _read_raw_body_for_readback(run_root: Path, receipt: Mapping[str, Any]) -> bytes:
    raw_meta = receipt.get("raw_body")
    if not isinstance(raw_meta, Mapping) or raw_meta.get("saved") is not True:
        raise ValueError("readback_source_raw_not_saved")
    relative = raw_meta.get("path")
    if not isinstance(relative, str):
        raise ValueError("preview_source_raw_path_missing")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("preview_source_raw_path_invalid")
    path = run_root.joinpath(*pure.parts)
    _assert_no_link_ancestors(path)
    raw_body = _bounded_read_file(path, MAX_ENTITY_BYTES)
    if _sha256(raw_body) != raw_meta.get("sha256"):
        raise ValueError("readback_source_raw_hash_mismatch")
    return raw_body


def _expected_preview_from_source(
    endpoint: Endpoint,
    receipt: Mapping[str, Any],
    record: Mapping[str, Any],
    payload: list[Any],
    catalog_descriptors: Mapping[str, Mapping[str, Any]],
) -> bool:
    row_number = record.get("row_number")
    if not isinstance(row_number, int) or row_number <= 0 or row_number > len(payload):
        return False
    raw_row = payload[row_number - 1]
    if not isinstance(raw_row, Mapping) or any(not isinstance(key, str) for key in raw_row):
        return False
    schema_descriptor = catalog_descriptors.get(endpoint.market)
    if schema_descriptor is None:
        return False
    schema = _target_schema(schema_descriptor, endpoint)
    row = dict(raw_row)
    if (
        not set(row).issubset(schema["property_names"])
        or any(not isinstance(value, str) for value in row.values())
        or any(name not in row for name in schema["required_properties"])
    ):
        return False
    stock_code, stock_conflict = _single_alias(row, "SecuritiesCompanyCode", "公司代號")
    year_text, year_conflict = _single_alias(row, "Year", "年度")
    season_text, season_conflict = _single_alias(row, "Season", "季別")
    company_name, company_conflict = _single_alias(row, "CompanyName", "公司名稱")
    source_date, source_date_conflict = _single_alias(row, "Date", "出表日期")
    period = _reported_period(year_text, season_text)
    if (
        stock_conflict
        or year_conflict
        or season_conflict
        or company_conflict
        or source_date_conflict
        or not STOCK_CODE_RE.fullmatch(stock_code)
        or period is None
    ):
        return False
    observed_at = str(receipt.get("request_completed_at_utc", ""))
    observed_date = _parse_aware_utc(observed_at).astimezone(TAIPEI).date()
    future = _quarter_end(period) > observed_date
    expected_fields, _, _ = _numeric_fields_for_row(row)
    if future:
        expected_fields = []
    checks = {
        "endpoint_id": endpoint.endpoint_id,
        "market": endpoint.market,
        "category_code": endpoint.category,
        "category_label": CATEGORY_LABELS[endpoint.category],
        "statement_type": endpoint.statement_type,
        "stock_code": stock_code,
        "company_name": company_name or None,
        "reported_period": period,
        "source_reported_date": source_date or None,
        "period_end_after_observation": future,
        "observed_at_utc": observed_at,
        "available_at": None,
        "issuer_identity_verified": False,
        "numeric_fields": expected_fields,
        "historical_pit_eligible": False,
        "formal_pit_eligible": False,
        "formal_credit": False,
        "training_eligible": False,
    }
    return all(record.get(key) == value for key, value in checks.items())


def _target_schema(catalog_descriptor: Mapping[str, Any], endpoint: Endpoint) -> dict[str, Any]:
    targets = catalog_descriptor.get("targets")
    if not isinstance(targets, list):
        raise CaptureError("validated_catalog_targets_missing")
    for target in targets:
        if isinstance(target, Mapping) and target.get("endpoint_id") == endpoint.endpoint_id:
            names = target.get("property_names")
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                break
            return {
                "property_names": frozenset(names),
                "required_properties": frozenset(
                    item for item in target.get("required_properties", []) if isinstance(item, str)
                ),
                "schema_sha256": str(target.get("schema_sha256", "")),
            }
    raise CaptureError(f"validated_catalog_target_unavailable:{endpoint.endpoint_id}")


def _inspect_numeric_response(
    endpoint: Endpoint,
    capture: HttpCapture,
    run_id: str,
    schema: Mapping[str, Any],
    preview: PreviewSink,
    seen_identities: dict[tuple[str, str, str, str], set[str]],
    seen_row_counts: dict[tuple[str, str, str, str], int],
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "endpoint_id": endpoint.endpoint_id,
        "url": endpoint.url,
        "market": endpoint.market,
        "statement_type": endpoint.statement_type,
        "category_code": endpoint.category,
        "category_label": CATEGORY_LABELS[endpoint.category],
        "catalog_schema_sha256": schema.get("schema_sha256"),
        "row_count": 0,
        "preview_rows_written": 0,
        "reported_period_counts": {},
        "missing_or_invalid_key_rows": 0,
        "schema_drift_rows": 0,
        "invalid_decimal_field_count": 0,
        "missing_value_field_count": 0,
        "source_row_date_fields_are_availability": False,
        "available_at": None,
        "available_at_reason": "not_disclosed_by_numeric_endpoint",
        "issuer_identity_verified": False,
        "formal_pit_eligible": False,
        "status": "transport_failure",
    }
    if capture.transport_status != "http_json_ok":
        base["error_code"] = capture.error_code or capture.transport_status
        base["error_reason"] = capture.error_reason
        return base
    payload = capture.response_json
    if not isinstance(payload, list):
        base["status"] = "schema_review_required"
        base["error_code"] = "top_level_payload_not_array"
        base["top_level_type"] = type(payload).__name__
        return base
    if not payload:
        base["status"] = "observed_empty_list"
        base["observation_label"] = "empty_response"
        base["official_no_data"] = False
        base["full_market_complete"] = False
        return base

    required = schema.get("required_properties", frozenset())
    allowed = schema.get("property_names", frozenset())
    current_taipei_date = _parse_aware_utc(capture.request_completed_at_utc).astimezone(TAIPEI).date()
    periods: dict[str, int] = {}
    malformed_keys = 0
    identity_alias_conflicts = 0
    repeated_identity_rows = 0
    row_schema_drift = 0
    invalid_decimal_fields = 0
    missing_fields = 0
    preview_written = 0
    preview_withheld_future = 0
    preview_capped = False
    identity_collision_rows = 0
    diagnostic_samples: list[dict[str, Any]] = []
    any_row_schema_drift = False

    for row_number, raw_row in enumerate(payload, start=1):
        if not isinstance(raw_row, Mapping) or any(not isinstance(key, str) for key in raw_row):
            row_schema_drift += 1
            any_row_schema_drift = True
            _append_sample(diagnostic_samples, {"row": row_number, "reason": "row_not_string_key_object"})
            continue
        row = dict(raw_row)
        unexpected = sorted(set(row) - allowed)
        invalid_property_values = [key for key, value in row.items() if not isinstance(value, str)]
        if unexpected or invalid_property_values:
            row_schema_drift += 1
            any_row_schema_drift = True
            _append_sample(
                diagnostic_samples,
                {
                    "row": row_number,
                    "reason": "row_schema_drift",
                    "unexpected_keys": unexpected[:20],
                    "non_string_values": invalid_property_values[:20],
                },
            )
            continue
        if any(name not in row for name in required):
            row_schema_drift += 1
            any_row_schema_drift = True
            _append_sample(diagnostic_samples, {"row": row_number, "reason": "catalog_required_property_missing"})
            continue
        stock_code, stock_conflict = _single_alias(row, "SecuritiesCompanyCode", "公司代號")
        year_text, year_conflict = _single_alias(row, "Year", "年度")
        season_text, season_conflict = _single_alias(row, "Season", "季別")
        company_name, company_conflict = _single_alias(row, "CompanyName", "公司名稱")
        source_reported_date, source_date_conflict = _single_alias(row, "Date", "出表日期")
        period = _reported_period(year_text, season_text)
        if stock_conflict or year_conflict or season_conflict or company_conflict or source_date_conflict:
            malformed_keys += 1
            identity_alias_conflicts += 1
            _append_sample(diagnostic_samples, {"row": row_number, "reason": "identity_alias_conflict_pending"})
            continue
        if not STOCK_CODE_RE.fullmatch(stock_code) or period is None:
            malformed_keys += 1
            _append_sample(
                diagnostic_samples,
                {"row": row_number, "reason": "reported_key_or_period_pending", "stock_code": stock_code[:16]},
            )
            continue
        periods[period] = periods.get(period, 0) + 1
        identity_key = (endpoint.market, endpoint.statement_type, stock_code, period)
        previous_endpoints = seen_identities.setdefault(identity_key, set())
        if previous_endpoints and endpoint.endpoint_id not in previous_endpoints:
            identity_collision_rows += 1
        previous_endpoints.add(endpoint.endpoint_id)
        if seen_row_counts.get(identity_key, 0) > 0:
            repeated_identity_rows += 1
        seen_row_counts[identity_key] = seen_row_counts.get(identity_key, 0) + 1
        future_period = _quarter_end(period) > current_taipei_date
        numeric_fields, invalid_in_row, missing_in_row = _numeric_fields_for_row(row)
        invalid_decimal_fields += invalid_in_row
        missing_fields += missing_in_row
        if future_period:
            preview_withheld_future += 1
            numeric_fields = []
        preview_record = {
            "run_id": run_id,
            "endpoint_id": endpoint.endpoint_id,
            "market": endpoint.market,
            "category_code": endpoint.category,
            "category_label": CATEGORY_LABELS[endpoint.category],
            "statement_type": endpoint.statement_type,
            "row_number": row_number,
            "stock_code": stock_code,
            "company_name": company_name or None,
            "reported_period": period,
            "source_reported_date": source_reported_date or None,
            "period_end_after_observation": future_period,
            "observed_at_utc": capture.request_completed_at_utc,
            "available_at": None,
            "available_at_reason": "not_disclosed_by_numeric_endpoint",
            "issuer_identity_verified": False,
            "numeric_fields": numeric_fields,
            "historical_pit_eligible": False,
            "formal_pit_eligible": False,
            "formal_credit": False,
            "training_eligible": False,
        }
        if preview.write_record(preview_record):
            preview_written += 1
        else:
            preview_capped = preview.truncated

    base.update(
        {
            "row_count": len(payload),
            "preview_rows_written": preview_written,
            "reported_period_counts": periods,
            "missing_or_invalid_key_rows": malformed_keys,
            "identity_alias_conflict_rows": identity_alias_conflicts,
            "schema_drift_rows": row_schema_drift,
            "invalid_decimal_field_count": invalid_decimal_fields,
            "missing_value_field_count": missing_fields,
            "cross_category_same_market_period_identity_rows": identity_collision_rows,
            "repeated_reported_identity_rows_preserved": repeated_identity_rows,
            "future_period_rows_with_values_withheld": preview_withheld_future,
            "preview_capped": preview_capped,
            "diagnostic_samples": diagnostic_samples,
            "records_deduplicated": False,
        }
    )
    if any_row_schema_drift:
        base["status"] = "schema_review_required"
    elif identity_alias_conflicts:
        base["status"] = "identity_review_required"
    elif malformed_keys:
        base["status"] = "key_review_required"
    else:
        base["status"] = "observed_row_array"
    base["official_no_data"] = False
    base["full_market_complete"] = False
    return base


def _capture_one_request(
    session: HttpSession,
    *,
    url: str,
    request_id: str,
    request_index: int,
    run_id: str,
    clock: Callable[[], datetime],
    writer: CaptureWriter,
    monotonic: Callable[[], float] = time.monotonic,
    request_started_monotonic: float | None = None,
    run_started_monotonic: float | None = None,
) -> tuple[HttpCapture, dict[str, Any]]:
    started_at = _aware_utc_text(clock())
    request_started_elapsed = (
        monotonic() if request_started_monotonic is None else request_started_monotonic
    )
    run_started_elapsed = (
        request_started_elapsed if run_started_monotonic is None else run_started_monotonic
    )
    response: HttpResponse | None = None
    body: BodyRead | None = None
    raw_record: dict[str, Any] | None = None
    raw_save_error = ""
    http_status: int | None = None
    http_reason = ""
    response_url = ""
    content_type = ""
    content_encoding = ""
    content_length_header = ""
    json_parse_status = "not_parsed"
    try:
        response = session.get(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, identity",
                "User-Agent": "technical-analysis-quarterly-research-readonly/1.0",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=False,
        )
        http_status = _safe_status(response.status_code)
        http_reason = _bounded_text(getattr(response, "reason", ""), 160)
        response_url = _bounded_text(getattr(response, "url", ""), 512)
        content_type = _bounded_text(_header(response.headers, "Content-Type"), 160)
        content_encoding = _bounded_text(_header(response.headers, "Content-Encoding"), 80).lower()
        content_length_header = _bounded_text(_header(response.headers, "Content-Length"), 32)
        body = _read_bounded_entity(
            response.raw,
            content_length_header,
            monotonic=monotonic,
            request_started_monotonic=request_started_elapsed,
            run_started_monotonic=run_started_elapsed,
        )
        if body.raw_entity:
            attempted_path = f"{request_id}/response_body.raw"
            try:
                raw_record = writer.write_raw(attempted_path, body.raw_entity)
            except (CaptureError, OSError, ValueError) as exc:
                raw_save_error = _bounded_text(f"{type(exc).__name__}:{exc}", 512)
        completed_at = _aware_utc_text(clock())
        error_code = ""
        error_reason = ""
        elapsed_error = _elapsed_budget_error(
            request_started_monotonic=request_started_elapsed,
            run_started_monotonic=run_started_elapsed,
            monotonic=monotonic,
        )
        if raw_save_error:
            error_code = "raw_entity_custody_failed"
            error_reason = raw_save_error
        elif body.read_error in {"request_elapsed_budget_exceeded", "run_elapsed_budget_exceeded"}:
            error_code = body.read_error
            error_reason = body.read_error
        elif elapsed_error:
            error_code = elapsed_error
            error_reason = elapsed_error
        elif response_url != url:
            error_code = "response_url_mismatch"
            error_reason = "response URL differs from fixed requested URL"
        elif body.read_error:
            error_code = "response_read_error"
            error_reason = body.read_error
        elif body.limit_reached or not body.complete:
            error_code = "raw_entity_limit_or_incomplete"
            error_reason = "response entity incomplete within fixed byte cap"
        elif http_status != 200:
            error_code = "http_status_not_200"
            error_reason = f"HTTP status {http_status} {http_reason}".strip()
        elif not _is_json_content_type(content_type):
            error_code = "content_type_not_json"
            error_reason = "HTTP 200 response content-type is not JSON"
        decoded: bytes | None = None
        decode_error = ""
        decoded_limit = False
        response_json: Any = None
        if (
            not error_code
            and not raw_save_error
            and body.complete
            and not body.read_error
            and not body.limit_reached
        ):
            decoded, decode_error, decoded_limit = _decode_entity(
                body.raw_entity,
                content_encoding=content_encoding,
            )
            if decoded_limit:
                error_code = "decoded_entity_limit"
                error_reason = "decoded JSON entity exceeded fixed cap"
            elif decode_error:
                error_code = "content_encoding_invalid"
                error_reason = decode_error
            elif http_status == 200 and _is_json_content_type(content_type) and decoded is not None:
                try:
                    response_json = _strict_json_loads(decoded.decode("utf-8-sig", errors="strict"))
                    json_parse_status = "parsed"
                except (UnicodeError, ValueError, RecursionError) as exc:
                    error_code = "invalid_json"
                    error_reason = _bounded_text(f"{type(exc).__name__}:{exc}", 512)
        elapsed_now = monotonic()
        request_elapsed_seconds = max(0.0, elapsed_now - request_started_elapsed)
        run_elapsed_seconds = max(0.0, elapsed_now - run_started_elapsed)
        if not error_code:
            if run_elapsed_seconds >= MAX_RUN_ELAPSED_SECONDS:
                error_code = "run_elapsed_budget_exceeded"
                error_reason = error_code
            elif request_elapsed_seconds >= MAX_REQUEST_ELAPSED_SECONDS:
                error_code = "request_elapsed_budget_exceeded"
                error_reason = error_code
        transport_status = "http_or_body_failure" if error_code else "http_json_ok"
        capture = HttpCapture(
            requested_url=url,
            request_started_at_utc=started_at,
            request_completed_at_utc=completed_at,
            http_status=http_status,
            http_reason=http_reason,
            response_url=response_url,
            content_type=content_type,
            content_encoding=content_encoding,
            content_length_header=content_length_header,
            body=body,
            transport_status=transport_status,
            error_code=error_code,
            error_reason=error_reason,
            decoded_body=decoded,
            decode_error=decode_error,
            decoded_limit_exceeded=decoded_limit,
            response_json=response_json,
            request_elapsed_seconds=request_elapsed_seconds,
            run_elapsed_seconds=run_elapsed_seconds,
        )
        receipt = _request_receipt(run_id, request_id, request_index, capture)
        if body.raw_entity and raw_save_error:
            receipt["raw_body"] = {
                "path": None,
                "attempted_path": f"{request_id}/response_body.raw",
                "sha256": _sha256(body.raw_entity),
                "bytes": len(body.raw_entity),
                "saved": False,
                "save_error": raw_save_error,
                "hash_scope": "bounded_entity_bytes_read_not_saved",
            }
        elif body.raw_entity and raw_record is not None:
            receipt["raw_body"] = {
                **raw_record,
                "saved": True,
                "hash_scope": "full_entity" if body.complete else "bounded_prefix",
            }
        else:
            receipt["raw_body"] = {
                "path": None,
                "sha256": None,
                "bytes": 0,
                "saved": False,
                "hash_scope": "unavailable",
            }
        receipt["decoded_body_sha256"] = _sha256(decoded) if decoded is not None else None
        receipt["decoded_body_bytes"] = len(decoded) if decoded is not None else None
        receipt["json_parse_status"] = json_parse_status
        receipt["transport_status"] = capture.transport_status
        receipt["error_code"] = capture.error_code or None
        receipt["error_reason"] = capture.error_reason or None
        return capture, receipt
    except Exception as exc:
        if body is None:
            body = BodyRead(b"", False, "", False, None)
        if body.raw_entity and raw_record is None and not raw_save_error:
            try:
                raw_record = writer.write_raw(f"{request_id}/response_body.raw", body.raw_entity)
            except (CaptureError, OSError, ValueError) as custody_exc:
                raw_save_error = _bounded_text(f"{type(custody_exc).__name__}:{custody_exc}", 512)
        completed_at = _aware_utc_text(clock())
        capture = HttpCapture(
            requested_url=url,
            request_started_at_utc=started_at,
            request_completed_at_utc=completed_at,
            http_status=http_status,
            http_reason=http_reason,
            response_url=response_url,
            content_type=content_type,
            content_encoding=content_encoding,
            content_length_header=content_length_header,
            body=body,
            transport_status="http_or_body_failure",
            error_code=(
                "raw_entity_custody_failed"
                if raw_save_error
                else _elapsed_budget_error(
                    request_started_monotonic=request_started_elapsed,
                    run_started_monotonic=run_started_elapsed,
                    monotonic=monotonic,
                )
                or "request_exception"
            ),
            error_reason=raw_save_error or _bounded_text(f"{type(exc).__name__}:{exc}", 512),
            decoded_body=None,
            decode_error="",
            decoded_limit_exceeded=False,
            response_json=None,
            request_elapsed_seconds=max(0.0, monotonic() - request_started_elapsed),
            run_elapsed_seconds=max(0.0, monotonic() - run_started_elapsed),
        )
        receipt = _request_receipt(run_id, request_id, request_index, capture)
        if raw_record is not None:
            receipt["raw_body"] = {
                **raw_record,
                "saved": True,
                "hash_scope": "full_entity" if body.complete else "bounded_prefix",
            }
        elif body.raw_entity:
            receipt["raw_body"] = {
                "path": None,
                "attempted_path": f"{request_id}/response_body.raw",
                "sha256": _sha256(body.raw_entity),
                "bytes": len(body.raw_entity),
                "saved": False,
                "save_error": raw_save_error or "request_failed_after_entity_read",
                "hash_scope": "bounded_entity_bytes_read_not_saved",
            }
        else:
            receipt["raw_body"] = {
                "path": None,
                "sha256": None,
                "bytes": 0,
                "saved": False,
                "hash_scope": "unavailable",
            }
        receipt.update(
            {
                "decoded_body_sha256": _sha256(capture.decoded_body) if capture.decoded_body is not None else None,
                "decoded_body_bytes": len(capture.decoded_body) if capture.decoded_body is not None else None,
                "json_parse_status": json_parse_status,
                "transport_status": capture.transport_status,
                "error_code": capture.error_code,
                "error_reason": capture.error_reason,
            }
        )
        return capture, receipt
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def _read_bounded_entity(
    raw: RawResponse,
    content_length_header: str,
    *,
    monotonic: Callable[[], float] | None = None,
    request_started_monotonic: float | None = None,
    run_started_monotonic: float | None = None,
) -> BodyRead:
    declared = _parse_content_length(content_length_header)
    retained = bytearray()
    read_error = ""
    complete = False
    limit_reached = False
    elapsed_clock = monotonic or time.monotonic
    request_started = elapsed_clock() if request_started_monotonic is None else request_started_monotonic
    run_started = request_started if run_started_monotonic is None else run_started_monotonic
    while len(retained) < MAX_ENTITY_BYTES:
        read_error = _elapsed_budget_error(
            request_started_monotonic=request_started,
            run_started_monotonic=run_started,
            monotonic=elapsed_clock,
        )
        if read_error:
            break
        amount = min(MAX_READ_CHUNK_BYTES, MAX_ENTITY_BYTES - len(retained))
        try:
            chunk = raw.read(amount, decode_content=False)
        except Exception as exc:
            read_error = _elapsed_budget_error(
                request_started_monotonic=request_started,
                run_started_monotonic=run_started,
                monotonic=elapsed_clock,
            ) or _bounded_text(f"{type(exc).__name__}:{exc}", 512)
            break
        read_error = _elapsed_budget_error(
            request_started_monotonic=request_started,
            run_started_monotonic=run_started,
            monotonic=elapsed_clock,
        )
        if read_error:
            if isinstance(chunk, bytes) and chunk:
                retained.extend(chunk[:amount])
            break
        if not chunk:
            complete = True
            if declared is not None and declared != len(retained):
                read_error = "content_length_mismatch"
            break
        if not isinstance(chunk, bytes):
            read_error = "response stream returned non-bytes data"
            break
        retained.extend(chunk)
    if len(retained) == MAX_ENTITY_BYTES and not read_error:
        read_error = _elapsed_budget_error(
            request_started_monotonic=request_started,
            run_started_monotonic=run_started,
            monotonic=elapsed_clock,
        )
        if read_error:
            return BodyRead(bytes(retained), False, read_error, False, declared)
        try:
            trailing_byte = raw.read(1, decode_content=False)
        except Exception as exc:
            read_error = _elapsed_budget_error(
                request_started_monotonic=request_started,
                run_started_monotonic=run_started,
                monotonic=elapsed_clock,
            ) or _bounded_text(f"{type(exc).__name__}:{exc}", 512)
            complete = False
        else:
            read_error = _elapsed_budget_error(
                request_started_monotonic=request_started,
                run_started_monotonic=run_started,
                monotonic=elapsed_clock,
            )
            if read_error:
                complete = False
            elif not isinstance(trailing_byte, bytes):
                read_error = "response stream returned non-bytes data during cap probe"
                complete = False
            elif trailing_byte:
                limit_reached = True
                complete = False
            elif declared is not None and declared != MAX_ENTITY_BYTES:
                read_error = "content_length_mismatch"
                complete = True
            else:
                complete = True
        if not complete and not read_error:
            limit_reached = True
    return BodyRead(bytes(retained), complete, read_error, limit_reached, declared)


def _decode_entity(raw: bytes, *, content_encoding: str) -> tuple[bytes | None, str, bool]:
    encoding = content_encoding.strip().lower()
    if encoding in {"", "identity"}:
        if len(raw) > MAX_DECODED_BYTES:
            return None, "", True
        return raw, "", False
    if "," in encoding:
        return None, "unsupported multiple content encodings", False
    if encoding == "gzip":
        try:
            decoded = bytearray()
            with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
                while True:
                    remaining = MAX_DECODED_BYTES - len(decoded)
                    chunk = stream.read(min(MAX_READ_CHUNK_BYTES, remaining + 1))
                    if not chunk:
                        return bytes(decoded), "", False
                    decoded.extend(chunk)
                    if len(decoded) > MAX_DECODED_BYTES:
                        return None, "", True
        except (OSError, EOFError, zlib.error) as exc:
            return None, f"invalid gzip entity:{type(exc).__name__}", False
    if encoding == "deflate":
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                return _bounded_inflate(raw, wbits), "", False
            except _DecodedLimit:
                return None, "", True
            except zlib.error:
                continue
        return None, "invalid deflate entity", False
    return None, f"unsupported content-encoding:{encoding[:64]}", False


class _DecodedLimit(Exception):
    pass


def _bounded_inflate(raw: bytes, wbits: int) -> bytes:
    decoder = zlib.decompressobj(wbits=wbits)
    output = bytearray()
    for offset in range(0, len(raw), MAX_READ_CHUNK_BYTES):
        pending = raw[offset : offset + MAX_READ_CHUNK_BYTES]
        while pending:
            remaining = MAX_DECODED_BYTES - len(output)
            chunk = decoder.decompress(pending, remaining + 1)
            output.extend(chunk)
            if len(output) > MAX_DECODED_BYTES:
                raise _DecodedLimit
            pending = decoder.unconsumed_tail
    remaining = MAX_DECODED_BYTES - len(output)
    output.extend(decoder.flush(remaining + 1))
    if len(output) > MAX_DECODED_BYTES:
        raise _DecodedLimit
    if not decoder.eof:
        raise zlib.error("incomplete compressed stream")
    return bytes(output)


def _persist_request(
    writer: CaptureWriter,
    *,
    request_id: str,
    body: BodyRead,
    receipt: Mapping[str, Any],
) -> None:
    del body
    writer.write_metadata(f"{request_id}/receipt.json", _canonical_json(receipt))


def _request_receipt(
    run_id: str,
    request_id: str,
    request_index: int,
    capture: HttpCapture,
) -> dict[str, Any]:
    return {
        "schema_version": "mops-quarterly-openapi-http-receipt.v1",
        "run_id": run_id,
        "request_id": request_id,
        "request_index": request_index,
        "attempt_number": 1,
        "retry_count": 0,
        "requested_url": capture.requested_url,
        "request_started_at_utc": capture.request_started_at_utc,
        "request_completed_at_utc": capture.request_completed_at_utc,
        "request_elapsed_seconds": capture.request_elapsed_seconds,
        "run_elapsed_seconds": capture.run_elapsed_seconds,
        "http_status": capture.http_status,
        "http_reason": capture.http_reason,
        "response_url": capture.response_url or None,
        "content_type": capture.content_type,
        "content_encoding": capture.content_encoding,
        "content_length_header": capture.content_length_header,
        "raw_body_bytes": len(capture.body.raw_entity),
        "raw_body_sha256": _sha256(capture.body.raw_entity) if capture.body.raw_entity else None,
        "raw_body_complete": capture.body.complete,
        "raw_body_limit_reached": capture.body.limit_reached,
        "raw_body_read_error": capture.body.read_error or None,
        "raw_body_hash_scope": "full_entity" if capture.body.complete else "bounded_prefix",
        "declared_content_length": capture.body.declared_length,
    }


def _inspect_catalog_body(content_type: str, response_json: Any) -> str:
    if not _is_json_content_type(content_type) or response_json is None:
        return "catalog_body_not_json"
    return "http_json_ok"


def _catalog_run_summary(capture: HttpCapture, descriptor: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "requested_url": capture.requested_url,
        "http_status": capture.http_status,
        "request_started_at_utc": capture.request_started_at_utc,
        "request_completed_at_utc": capture.request_completed_at_utc,
        "request_elapsed_seconds": capture.request_elapsed_seconds,
        "run_elapsed_seconds": capture.run_elapsed_seconds,
        "response_body_sha256": _sha256(capture.body.raw_entity) if capture.body.raw_entity else None,
        "response_body_bytes": len(capture.body.raw_entity),
        "transport_status": capture.transport_status,
        "error_code": capture.error_code or None,
        "catalog_contract": dict(descriptor) if descriptor is not None else None,
    }


def _expected_tpex_schema_ref(endpoint: Endpoint) -> str:
    name = f"mopsfin_t187ap{STATEMENT_NUMBERS[endpoint.statement_type]}_O_{endpoint.category}"
    if endpoint.statement_type == "balance" and endpoint.category in {"ins", "mim"}:
        name += "A"
    return f"#/components/schemas/{name}"


def _field_unit(name: str) -> str:
    if name in EPS_FIELD_NAMES:
        return "元/股"
    if name.endswith(SHARE_FIELD_SUFFIXES):
        return "股"
    return "unit_unknown"


def _reported_period(year_text: str, season_text: str) -> str | None:
    year_text = year_text.strip()
    season_text = season_text.strip()
    if not re.fullmatch(r"\d{3,4}", year_text) or not re.fullmatch(r"[1-4]", season_text):
        return None
    year = int(year_text)
    if len(year_text) == 3:
        year += 1911
    if year < 1912 or year > 9999:
        return None
    return f"{year:04d}-Q{season_text}"


def _quarter_end(period: str) -> date:
    match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if match is None:
        raise ValueError("invalid_reported_period")
    year, quarter = int(match.group(1)), int(match.group(2))
    month = quarter * 3
    if month == 12:
        return date(year, 12, 31)
    first_day_after = date(year, month + 1, 1)
    return date.fromordinal(first_day_after.toordinal() - 1)


def _decimal_value(raw_value: str) -> Decimal | None:
    value = raw_value.strip()
    if not DECIMAL_TEXT_RE.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _numeric_fields_for_row(row: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    numeric_fields: list[dict[str, Any]] = []
    invalid_count = 0
    missing_count = 0
    for item_name, raw_value in row.items():
        if item_name in IDENTITY_FIELDS:
            continue
        if not isinstance(raw_value, str):
            invalid_count += 1
            continue
        if not raw_value or raw_value.strip() in MISSING_MARKERS:
            missing_count += 1
            continue
        if len(item_name.encode("utf-8")) > 512 or len(raw_value) > 256:
            invalid_count += 1
            continue
        parsed = _decimal_value(raw_value)
        if parsed is None:
            invalid_count += 1
            continue
        unit = _field_unit(item_name)
        numeric_fields.append(
            {
                "item_name": item_name,
                "raw_value": raw_value,
                "decimal_value": str(parsed),
                "unit": unit,
                "unit_basis": "explicit_eps_field_label"
                if unit == "元/股"
                else "explicit_share_field_label"
                if unit == "股"
                else "unknown_from_catalog",
            }
        )
    return numeric_fields, invalid_count, missing_count


def _first_nonempty(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _single_alias(row: Mapping[str, Any], *keys: str) -> tuple[str, bool]:
    values = {
        value.strip()
        for key in keys
        if isinstance((value := row.get(key)), str) and value.strip()
    }
    if len(values) > 1:
        return "", True
    return (next(iter(values)) if values else ""), False


def _append_sample(samples: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if len(samples) < MAX_DIAGNOSTIC_SAMPLES:
        samples.append(value)


def _ineligibility_flags() -> dict[str, bool]:
    return {
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_oos_eligible": False,
        "formal_credit": False,
        "training_eligible": False,
        "database_write_performed": False,
        "issuer_identity_verified": False,
        "full_market_coverage_verified": False,
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strict_json_loads(value: str) -> Any:
    """拒絕重複物件鍵與非有限常數，並以 Decimal 保留 JSON 小數文字精度。"""

    return json.loads(
        value,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_nonfinite_json_number,
        parse_float=Decimal,
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_object_key")
        result[key] = value
    return result


def _reject_nonfinite_json_number(value: str) -> None:
    raise ValueError(f"nonfinite_json_constant_rejected:{value}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bounded_text(value: object, limit: int) -> str:
    return " ".join(str(value).split())[:limit]


def _aware_utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock_must_return_timezone_aware_datetime")
    normalized = value.astimezone(timezone.utc)
    if normalized > datetime.now(timezone.utc) + timezone.utc.utcoffset(normalized):
        raise ValueError("clock_value_cannot_be_future")
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_aware_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp_must_be_aware")
    return parsed.astimezone(timezone.utc)


def _is_json_content_type(value: str) -> bool:
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _header(headers: Mapping[str, Any], name: str) -> str:
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value)
    return ""


def _parse_content_length(value: str) -> int | None:
    if not re.fullmatch(r"\d{1,16}", value.strip()):
        return None
    return int(value)


def _safe_status(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nonnegative_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return 0.0
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) and result >= 0 else 0.0


def _is_nonnegative_seconds(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    if isinstance(value, Decimal):
        return value.is_finite() and value >= 0
    return math.isfinite(value) and value >= 0


def _bounded_read_file(path: Path, max_bytes: int) -> bytes:
    _assert_no_link_ancestors(path)
    if _is_link_or_junction(path) or not path.is_file():
        raise ValueError(f"artifact_must_be_regular_file:{path.name}")
    before = path.lstat()
    if before.st_nlink != 1:
        raise ValueError(f"artifact_link_count_invalid:{path.name}")
    if before.st_size > max_bytes:
        raise ValueError(f"artifact_exceeds_read_cap:{path.name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode) or _file_identity(before) != _file_identity(opened_before):
            raise ValueError(f"artifact_changed_before_open:{path.name}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(MAX_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    if (
        len(payload) > max_bytes
        or len(payload) != before.st_size
        or _file_identity(before) != _file_identity(opened_after)
        or _file_identity(before) != _file_identity(after)
    ):
        raise ValueError(f"artifact_changed_during_bounded_read:{path.name}")
    return payload


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except (AttributeError, OSError):
        attributes = 0
    if attributes & 0x400:
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _mkdir_no_links(path: Path) -> None:
    path = Path(path)
    missing: list[Path] = []
    current = path
    while not current.exists():
        if _is_link_or_junction(current):
            raise ValueError(f"output_directory_link_rejected:{current}")
        missing.append(current)
        if current.parent == current:
            raise ValueError("output_directory_root_unavailable")
        current = current.parent
    _assert_no_link_ancestors(current)
    if _is_link_or_junction(current) or not current.is_dir():
        raise ValueError(f"output_directory_not_regular:{current}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=False)
    _assert_no_link_ancestors(path)
    if not path.is_dir():
        raise ValueError(f"output_directory_not_regular:{path}")


def _assert_no_link_ancestors(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    for ancestor in (absolute, *absolute.parents):
        if ancestor.exists() or ancestor.is_symlink():
            if _is_link_or_junction(ancestor):
                raise ValueError(f"path_link_or_reparse_point_rejected:{ancestor.name}")


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
        int(info.st_nlink),
    )


def _limit_for_kind(kind: str) -> int:
    if kind == "raw_entity":
        return MAX_ENTITY_BYTES
    if kind == "metadata":
        return MAX_METADATA_BYTES
    if kind == "numeric_preview_ndjson":
        return MAX_PREVIEW_BYTES
    raise ValueError(f"unknown_artifact_kind:{kind}")
