"""MOPS 月營收歷史報告的有界擷取與原件驗證。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPResponse
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Sequence
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from bs4 import BeautifulSoup

from data_module.daily_source_snapshot import (
    DailySourceSnapshotError,
    DailySourceTransportCapture,
    _content_type_charset_text,
    _datetime_text as _daily_datetime_text,
    _html_meta_charset_text,
    _transport_capture_from_dict,
)
from data_module.monthly_revenue_availability_history import (
    MOPS_REDIRECT_API_URL,
    MOPS_STATIC_MARKET_PATH,
    MOPS_STATIC_TYPEK,
    _extract_mops_static_path,
    _validate_mops_static_report,
    parse_announcement_date,
    parse_mops_monthly_revenue_html,
)
from data_module.monthly_revenue_snapshot_harvester import (
    _cell_text,
    _clean_text,
    _has_required_headers,
    _normalize_header,
    parse_mops_monthly_revenue_snapshot_html,
)

if TYPE_CHECKING:
    from data_module.monthly_revenue_revision_archive import MonthlyRevenueRawBatchEvidenceV1


MopsHistoryMarket = Literal["twse", "tpex"]
MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS: dict[MopsHistoryMarket, str] = {
    "twse": "mops.history.monthly_revenue.twse",
    "tpex": "mops.history.monthly_revenue.tpex",
}
MOPS_MONTHLY_REVENUE_HISTORY_DATASET_ID = "mops.official.monthly_revenue_history"
MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION = (
    "mops-monthly-revenue-history-capture-parser.v1"
)
MOPS_MONTHLY_REVENUE_HISTORY_ROW_PARSER = (
    "monthly_revenue_snapshot_harvester.parse_mops_monthly_revenue_snapshot_html"
)
MOPS_MONTHLY_REVENUE_HISTORY_SCHEMA_VERSION = (
    "mops-monthly-revenue-history-capture.v1"
)
MOPS_MONTHLY_REVENUE_HISTORY_REDIRECT_SCHEMA_VERSION = (
    "mops-monthly-revenue-history-capture.v3"
)
MOPS_HTTP_ENTITY_BODY_SEMANTICS = "http_entity_body_after_transfer_decoding"
MOPS_MONTHLY_REVENUE_HISTORY_TRANSPORT_MODES = (
    "direct_static_v1",
    "redirect_chain_v1",
)
MOPS_MONTHLY_REVENUE_HISTORY_LICENSE_STATUS = (
    "not_established_by_current_opendata_dataset_license"
)
MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES = 8 * 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES = 8 * 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_JSON_BYTES = 12 * 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_ARTIFACT_BYTES = 24 * 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_CHUNK_RECEIPT_BYTES = 48 * 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_ARTIFACT_BYTES = 1024 * 1024
MAX_MOPS_MONTHLY_REVENUE_HISTORY_PERIODS_PER_MARKET = 2
MAX_MOPS_MONTHLY_REVENUE_HISTORY_CAPTURES = 4
MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLANNED_PERIODS = 240
MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS = 8.0
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_PERIOD_RE = re.compile(r"\A(\d{4})-(0[1-9]|1[0-2])\Z")
_UNIT_RE = re.compile(
    r"(?:金額)?單位\s*[:：]\s*(?:新臺幣|新台幣)?\s*(仟元|千元|元)"
)


class MopsMonthlyRevenueHistoryError(ValueError):
    """MOPS 歷史報告擷取或原件驗證失敗。"""

    def __init__(self, message: str, *, transport_hops: tuple["MopsMonthlyRevenueTransportHop", ...] = ()) -> None:
        super().__init__(message)
        self.transport_hops = transport_hops


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueTransportHop:
    """逐跳保存受限HTTP事實；raw_response_bytes是Transfer-Encoding解碼後的entity body。"""

    method: str
    request_url: str
    request_headers: tuple[tuple[str, str], ...]
    request_body: bytes
    request_started_at: datetime
    response_url: str
    response_status: int
    response_headers: tuple[tuple[str, str], ...]
    raw_response_bytes: bytes
    observed_bytes_sha256: str
    response_body_completed_at: datetime
    body_observation_ended_at: datetime
    eof_observed: bool
    body_truncated: bool

    def __post_init__(self) -> None:
        if self.method not in {"GET", "POST"}:
            raise MopsMonthlyRevenueHistoryError("transport_hop_method_invalid")
        _require_text(self.request_url, "hop_request_url")
        _require_text(self.response_url, "hop_response_url")
        for name in ("request_started_at", "response_body_completed_at", "body_observation_ended_at"):
            _require_aware(getattr(self, name), name)
        if type(self.request_body) is not bytes or type(self.raw_response_bytes) is not bytes:
            raise MopsMonthlyRevenueHistoryError("transport_hop_body_type_invalid")
        if type(self.request_headers) is not tuple or type(self.response_headers) is not tuple:
            raise MopsMonthlyRevenueHistoryError("transport_hop_headers_collection_invalid")
        if type(self.response_status) is not int or not 100 <= self.response_status <= 599:
            raise MopsMonthlyRevenueHistoryError("transport_hop_status_invalid")
        if type(self.eof_observed) is not bool or type(self.body_truncated) is not bool:
            raise MopsMonthlyRevenueHistoryError("transport_hop_completion_flags_invalid")
        if self.eof_observed == self.body_truncated:
            raise MopsMonthlyRevenueHistoryError("transport_hop_completion_flags_conflict")
        if self.response_body_completed_at < self.request_started_at or self.body_observation_ended_at < self.response_body_completed_at:
            raise MopsMonthlyRevenueHistoryError("transport_hop_clock_order_invalid")
        if hashlib.sha256(self.raw_response_bytes).hexdigest() != self.observed_bytes_sha256:
            raise MopsMonthlyRevenueHistoryError("transport_hop_raw_sha256_mismatch")
        if len(self.raw_response_bytes) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES:
            raise MopsMonthlyRevenueHistoryError("transport_hop_body_exceeds_limit")
        if tuple(sorted(self.request_headers)) != self.request_headers or tuple(sorted(self.response_headers)) != self.response_headers:
            raise MopsMonthlyRevenueHistoryError("transport_hop_headers_not_canonical")
        if any(type(k) is not str or type(v) is not str for k, v in (*self.request_headers, *self.response_headers)):
            raise MopsMonthlyRevenueHistoryError("transport_hop_headers_invalid")
        if any(
            not key.isascii() or key != key.lower() or "\r" in value or "\n" in value or len(value) > 8192
            for key, value in (*self.request_headers, *self.response_headers)
        ):
            raise MopsMonthlyRevenueHistoryError("transport_hop_header_value_invalid")
        if any(k not in {"accept", "content-type", "origin", "referer", "user-agent"} for k, _ in self.request_headers):
            raise MopsMonthlyRevenueHistoryError("transport_hop_request_header_not_allowlisted")
        if any(k not in {"content-type", "content-encoding", "content-length", "date", "location", "transfer-encoding"} for k, _ in self.response_headers):
            raise MopsMonthlyRevenueHistoryError("transport_hop_response_header_not_allowlisted")
        if len({key for key, _ in self.request_headers}) != len(self.request_headers) or len({key for key, _ in self.response_headers}) != len(self.response_headers):
            raise MopsMonthlyRevenueHistoryError("transport_hop_duplicate_header")

    @property
    def request_body_sha256(self) -> str:
        return hashlib.sha256(self.request_body).hexdigest()

    @property
    def raw_response_sha256(self) -> str | None:
        """只有觀測到EOF時才回報完整HTTP entity body SHA。"""
        return self.observed_bytes_sha256 if self.eof_observed else None

    @property
    def complete_raw_sha256(self) -> str:
        if not self.eof_observed or self.body_truncated:
            raise MopsMonthlyRevenueHistoryError("完整response_sha需要EOF證據")
        return self.observed_bytes_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "request_url": self.request_url,
            "request_headers": [list(item) for item in self.request_headers],
            "request_body_base64": base64.b64encode(self.request_body).decode("ascii"),
            "request_body_sha256": self.request_body_sha256,
            "request_started_at": _datetime_text(self.request_started_at),
            "response_url": self.response_url,
            "response_status": self.response_status,
            "response_headers": [list(item) for item in self.response_headers],
            "response_body_semantics": MOPS_HTTP_ENTITY_BODY_SEMANTICS,
            "raw_response_bytes_base64": base64.b64encode(self.raw_response_bytes).decode("ascii"),
            "raw_response_sha256": self.raw_response_sha256,
            "observed_prefix_sha256": self.observed_bytes_sha256,
            "response_body_completed_at": _datetime_text(self.response_body_completed_at),
            "body_observation_ended_at": _datetime_text(self.body_observation_ended_at),
            "eof_observed": self.eof_observed,
            "body_truncated": self.body_truncated,
        }


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueHistoryFailureReceipt:
    """失敗仍保留各跳原始回應前綴與SHA，供明確challenge／截斷診斷。"""

    market: MopsHistoryMarket
    period: str
    transport_mode: str
    reason_code: str
    transport_hops: tuple[MopsMonthlyRevenueTransportHop, ...]

    def __post_init__(self) -> None:
        if self.market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS:
            raise MopsMonthlyRevenueHistoryError("failure_receipt_market_invalid")
        _validate_period(self.period)
        _validate_transport_mode(self.transport_mode)
        _require_text(self.reason_code, "failure_receipt_reason_code")
        if type(self.transport_hops) is not tuple:
            raise MopsMonthlyRevenueHistoryError("failure_receipt_hops_invalid")
        if _hop_bytes(self.transport_hops) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES:
            raise MopsMonthlyRevenueHistoryError("failure_receipt_bytes_exceed_limit")

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "period": self.period,
            "transport_mode": self.transport_mode,
            "reason_code": self.reason_code,
            "transport_hops": [hop.to_dict() for hop in self.transport_hops],
        }


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueHistoricalCapture:
    """單一市場、單一資料年月的 MOPS HTML 原件與實際 transport。"""

    market: MopsHistoryMarket
    period: str
    requested_url: str
    response_url: str
    request_started_at: datetime
    transport_capture: DailySourceTransportCapture
    transport_mode: str = "direct_static_v1"
    transport_hops: tuple[MopsMonthlyRevenueTransportHop, ...] = ()

    def __post_init__(self) -> None:
        if self.market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS:
            raise MopsMonthlyRevenueHistoryError("market_unsupported")
        if not _PERIOD_RE.fullmatch(self.period):
            raise MopsMonthlyRevenueHistoryError("period_invalid")
        _require_aware(self.request_started_at, "request_started_at")
        if type(self.transport_capture) is not DailySourceTransportCapture:
            raise MopsMonthlyRevenueHistoryError("transport_capture_type_invalid")
        if self.transport_mode not in MOPS_MONTHLY_REVENUE_HISTORY_TRANSPORT_MODES:
            raise MopsMonthlyRevenueHistoryError("transport_mode_invalid")
        expected_url = _official_history_url(self.market, self.period)
        if self.requested_url != expected_url or self.response_url != expected_url:
            raise MopsMonthlyRevenueHistoryError("endpoint_identity_mismatch")
        if self.transport_capture.official_source_url != expected_url:
            raise MopsMonthlyRevenueHistoryError("transport_source_url_mismatch")
        if self.transport_capture.response_url not in {None, expected_url}:
            raise MopsMonthlyRevenueHistoryError("transport_response_url_mismatch")
        if self.transport_capture.response_status != 200:
            raise MopsMonthlyRevenueHistoryError("http_status_not_200")
        if self.transport_capture.body_completed_at < self.request_started_at:
            raise MopsMonthlyRevenueHistoryError("body_completion_precedes_request")
        if self.transport_mode == "direct_static_v1":
            if self.transport_hops:
                raise MopsMonthlyRevenueHistoryError("direct_mode_cannot_have_transport_hops")
        else:
            _validate_redirect_chain(
                market=self.market,
                period=self.period,
                requested_url=self.requested_url,
                response_url=self.response_url,
                request_started_at=self.request_started_at,
                final_capture=self.transport_capture,
                hops=self.transport_hops,
            )
        if len(self.raw_response_bytes) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES:
            raise MopsMonthlyRevenueHistoryError("body_exceeds_limit")
        try:
            html = self.transport_capture.decoded_html
        except (DailySourceSnapshotError, LookupError, UnicodeError) as exc:
            raise MopsMonthlyRevenueHistoryError("html_strict_decode_failed") from exc
        static_path = urlsplit(expected_url).path
        try:
            _validate_mops_static_report(
                html, market=self.market, period=self.period, static_path=static_path
            )
            rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
                html,
                market=self.market,
                period=self.period,
                fetched_at=_datetime_text(self.transport_capture.body_completed_at),
                source_version=self.source_version,
            )
            date_rows, _ = parse_mops_monthly_revenue_html(
                html, market=self.market, period=self.period
            )
        except (TypeError, ValueError) as exc:
            raise MopsMonthlyRevenueHistoryError("official_report_validation_failed") from exc
        if diagnostics or not rows:
            raise MopsMonthlyRevenueHistoryError("historical_snapshot_parser_rejected_report")
        if date_rows and len(date_rows) != len(rows):
            raise MopsMonthlyRevenueHistoryError("availability_parser_rows_disagree")
        if len({row["stock_code"] for row in rows}) != len(rows):
            raise MopsMonthlyRevenueHistoryError("parser_duplicate_stock_code")

    @property
    def source_id(self) -> str:
        return MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS[self.market]

    @property
    def dataset_id(self) -> str:
        return MOPS_MONTHLY_REVENUE_HISTORY_DATASET_ID

    @property
    def raw_response_bytes(self) -> bytes:
        return self.transport_capture.raw_response_bytes

    @property
    def raw_response_sha256(self) -> str:
        return self.transport_capture.transport_sha256

    @property
    def revision_id(self) -> str:
        return f"sha256:{self.raw_response_sha256}"

    @property
    def source_version(self) -> str:
        completed = _datetime_text(self.transport_capture.body_completed_at)
        if self.transport_mode == "redirect_chain_v1":
            chain_sha = hashlib.sha256(_canonical_json_bytes(
                [hop.to_dict() for hop in self.transport_hops]
            )).hexdigest()
            return (
                f"{self.source_id}.redirect-chain.v1:{self.period}:captured_at:{completed}"
                f":chain-sha256:{chain_sha}:sha256:{self.raw_response_sha256}"
            )
        return (
            f"{self.source_id}.v1:{self.period}:captured_at:{completed}"
            f":sha256:{self.raw_response_sha256}"
        )

    @property
    def rows(self) -> tuple[dict[str, str], ...]:
        html = self.transport_capture.decoded_html
        rows, diagnostics = parse_mops_monthly_revenue_snapshot_html(
            html,
            market=self.market,
            period=self.period,
            fetched_at=_datetime_text(self.transport_capture.body_completed_at),
            source_version=self.source_version,
        )
        if diagnostics or not rows:
            raise MopsMonthlyRevenueHistoryError("historical_snapshot_parser_rejected_report")
        return tuple(dict(row) for row in rows)

    @property
    def printed_report_date(self) -> str | None:
        rows, diagnostics = parse_mops_monthly_revenue_html(
            self.transport_capture.decoded_html,
            market=self.market,
            period=self.period,
        )
        if diagnostics or not rows:
            return None
        raw_date = rows[0].get("出表日期", "")
        try:
            return parse_announcement_date(raw_date).isoformat()
        except ValueError:
            return None

    @property
    def observed_unit_annotations(self) -> tuple[str, ...]:
        """只回報此歷史原件內明確出現的單位文字，不推及 OpenData API。"""
        text = self.transport_capture.decoded_html
        return tuple(sorted(set(_UNIT_RE.findall(text))))

    @property
    def raw_source_values_by_stock_code(self) -> dict[str, dict[str, str]]:
        """依既有欄名整理器抽取原始欄位文字，不清理數值或推單位。"""
        records: dict[str, dict[str, str]] = {}
        soup = BeautifulSoup(self.transport_capture.decoded_html, "html.parser")
        for table in soup.find_all("table"):
            header: list[str] | None = None
            for tr in table.find_all("tr"):
                cells = [_cell_text(cell) for cell in tr.find_all(["th", "td"])]
                if not cells:
                    continue
                normalized = [_normalize_header(cell) for cell in cells]
                if "公司代號" in normalized:
                    header = normalized if _has_required_headers(normalized) else None
                    continue
                if header is None:
                    continue
                mapped = dict(zip(header, cells, strict=False))
                stock_code = _clean_text(mapped.get("公司代號", ""))
                if not re.fullmatch(r"\d{4,6}", stock_code) or stock_code in records:
                    continue
                records[stock_code] = dict(mapped)
        if set(records) != {row["stock_code"] for row in self.rows}:
            raise MopsMonthlyRevenueHistoryError("raw_source_rows_disagree_with_reused_parser")
        return records

    @property
    def availability_at(self) -> None:
        """原件擷取時間不是歷史發布時間；目前不提供可用時間。"""
        return None

    @property
    def availability_basis(self) -> str:
        return "retrospective_capture_only"

    @property
    def historical_pit_eligible(self) -> bool:
        return False

    @property
    def license_status(self) -> str:
        return MOPS_MONTHLY_REVENUE_HISTORY_LICENSE_STATUS

    def _transport_capture_dict(self) -> dict[str, object]:
        payload = dict(self.transport_capture.to_dict())
        payload.update(
            {
                "response_url": self.transport_capture.response_url,
                "content_encoding_original_text": (
                    self.transport_capture.content_encoding_original_text
                ),
                "eof_observed": self.transport_capture.eof_observed,
                "body_observation_ended_at": _daily_datetime_text(
                    self.transport_capture.body_observation_ended_at
                    or self.transport_capture.body_completed_at
                ),
            }
        )
        return payload

    @property
    def transport_chain_json(self) -> str:
        return _canonical_json_bytes([hop.to_dict() for hop in self.transport_hops]).decode("utf-8")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": (
                MOPS_MONTHLY_REVENUE_HISTORY_REDIRECT_SCHEMA_VERSION
                if self.transport_mode == "redirect_chain_v1"
                else MOPS_MONTHLY_REVENUE_HISTORY_SCHEMA_VERSION
            ),
            "dataset_id": self.dataset_id,
            "market": self.market,
            "period": self.period,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "revision_id": self.revision_id,
            "parent_revision_id": None,
            "requested_url": self.requested_url,
            "response_url": self.response_url,
            "request_started_at": _datetime_text(self.request_started_at),
            "body_completed_at": _datetime_text(self.transport_capture.body_completed_at),
            "body_observation_ended_at": _datetime_text(
                self.transport_capture.body_observation_ended_at
                or self.transport_capture.body_completed_at
            ),
            "raw_response_sha256": self.raw_response_sha256,
            "raw_response_bytes": len(self.raw_response_bytes),
            "transport_capture": self._transport_capture_dict(),
            "parser_version": MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION,
            "reused_row_parser": MOPS_MONTHLY_REVENUE_HISTORY_ROW_PARSER,
            "printed_report_date": self.printed_report_date,
            "observed_unit_annotations": list(self.observed_unit_annotations),
            "source_unit": "unknown",
            "normalized_currency_unit": None,
            "availability_at": None,
            "availability_basis": self.availability_basis,
            "historical_pit_eligible": False,
            "license_status": self.license_status,
            "rows": list(self.rows),
            "raw_source_values_by_stock_code": self.raw_source_values_by_stock_code,
        }
        if self.transport_mode == "redirect_chain_v1":
            payload["transport_mode"] = self.transport_mode
            payload["transport_hops"] = [hop.to_dict() for hop in self.transport_hops]
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())

    def to_monthly_revenue_raw_batch_evidence(
        self,
    ) -> "MonthlyRevenueRawBatchEvidenceV1":
        """轉成封存 DTO；擷取時鐘只代表原件完成觀測後的時間。"""
        from data_module.monthly_revenue_revision_archive import (
            MonthlyRevenueRawBatchEvidenceV1,
            MonthlyRevenueRawRowV1,
        )

        completed_at = self.transport_capture.body_completed_at
        parsed_rows = parse_mops_monthly_revenue_history_capture(self)
        source_values_by_stock_code = self.raw_source_values_by_stock_code
        annotations = self.observed_unit_annotations
        observed_unit_text = annotations[0] if len(annotations) == 1 else None
        rows = tuple(
            MonthlyRevenueRawRowV1.build(
                stock_code=row["stock_code"],
                period=self.period,
                source_values=source_values_by_stock_code[row["stock_code"]],
                source_unit_text=observed_unit_text,
                unit_status="unknown",
                unit_proof_sha256=None,
            )
            for row in parsed_rows
        )
        transport_dict = self._transport_capture_dict()
        transport_dict.pop("raw_response_bytes_base64", None)
        transport_provenance_items: list[tuple[str, str | int | bool | None]] = [
            ("request_started_at", _datetime_text(self.request_started_at)),
            ("requested_url", self.requested_url),
            ("response_url", self.response_url),
            ("observed_printed_report_date", self.printed_report_date),
            ("transport_capture_json", _canonical_json_bytes(transport_dict).decode("utf-8")),
        ]
        if self.transport_mode == "redirect_chain_v1":
            transport_provenance_items.extend((
                ("transport_mode", self.transport_mode),
                ("transport_chain_json", self.transport_chain_json),
            ))
        transport_provenance = tuple(transport_provenance_items)
        return MonthlyRevenueRawBatchEvidenceV1(
            market=self.market,
            source_id=self.source_id,
            source_version=self.source_version,
            period=self.period,
            parser_version=MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION,
            raw_source_bytes=self.raw_response_bytes,
            raw_source_sha256=self.raw_response_sha256,
            captured_at=completed_at,
            available_at=completed_at,
            availability_basis="retrospective_capture_observation",
            rows=tuple(sorted(rows, key=lambda row: row.stock_code)),
            transport_provenance=tuple(sorted(transport_provenance)),
            official_announcement_at=None,
            official_revision_id=None,
        )


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueHistoryBatch:
    """符合小批次上限的歷史報告擷取結果；各期失敗不丟棄已完成原件。"""

    requested_pairs: tuple[tuple[MopsHistoryMarket, str], ...]
    captures: tuple[MopsMonthlyRevenueHistoricalCapture, ...]
    failures: tuple[tuple[MopsHistoryMarket, str, str], ...]
    failure_receipts: tuple[MopsMonthlyRevenueHistoryFailureReceipt, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.requested_pairs) is not tuple
            or not self.requested_pairs
            or len(self.requested_pairs) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CAPTURES
        ):
            raise MopsMonthlyRevenueHistoryError("batch_capture_count_out_of_bounds")
        if type(self.captures) is not tuple or type(self.failures) is not tuple:
            raise MopsMonthlyRevenueHistoryError("batch_result_collections_invalid")
        if type(self.failure_receipts) is not tuple:
            raise MopsMonthlyRevenueHistoryError("batch_failure_receipts_invalid")
        for market, period in self.requested_pairs:
            if market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS:
                raise MopsMonthlyRevenueHistoryError("batch_requested_market_invalid")
            _validate_period(period)
        if len(set(self.requested_pairs)) != len(self.requested_pairs):
            raise MopsMonthlyRevenueHistoryError("batch_requested_pair_duplicate")
        capture_pairs = tuple((item.market, item.period) for item in self.captures)
        if any(type(item) is not MopsMonthlyRevenueHistoricalCapture for item in self.captures):
            raise MopsMonthlyRevenueHistoryError("batch_capture_type_invalid")
        if len(set(capture_pairs)) != len(capture_pairs) or any(
            pair not in self.requested_pairs for pair in capture_pairs
        ):
            raise MopsMonthlyRevenueHistoryError("batch_capture_not_requested")
        failure_pairs: list[tuple[MopsHistoryMarket, str]] = []
        for failure in self.failures:
            if type(failure) is not tuple or len(failure) != 3:
                raise MopsMonthlyRevenueHistoryError("batch_failure_invalid")
            market, period, error = failure
            if market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS:
                raise MopsMonthlyRevenueHistoryError("batch_failure_market_invalid")
            _validate_period(period)
            if type(error) is not str or not error:
                raise MopsMonthlyRevenueHistoryError("batch_failure_error_invalid")
            failure_pairs.append((market, period))
        if len(set(failure_pairs)) != len(failure_pairs) or any(
            pair not in self.requested_pairs or pair in capture_pairs
            for pair in failure_pairs
        ):
            raise MopsMonthlyRevenueHistoryError("batch_failure_pair_invalid")
        if set(capture_pairs).union(failure_pairs) != set(self.requested_pairs):
            raise MopsMonthlyRevenueHistoryError("batch_result_count_mismatch")
        receipt_pairs: list[tuple[str, str]] = []
        for receipt in self.failure_receipts:
            if type(receipt) is not MopsMonthlyRevenueHistoryFailureReceipt:
                raise MopsMonthlyRevenueHistoryError("batch_failure_receipt_type_invalid")
            receipt_pairs.append((receipt.market, receipt.period))
        if len(set(receipt_pairs)) != len(receipt_pairs) or any(
            pair not in failure_pairs for pair in receipt_pairs
        ):
            raise MopsMonthlyRevenueHistoryError("batch_failure_receipt_pair_invalid")


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueHistoryCapturePlan:
    """長期年月範圍的純規劃；每個chunk最多四組市場與年月。"""

    start_period: str
    end_period: str
    markets: tuple[MopsHistoryMarket, ...]
    chunks: tuple[tuple[tuple[MopsHistoryMarket, str], ...], ...]
    plan_sha256: str

    @property
    def requested_pairs(self) -> tuple[tuple[MopsHistoryMarket, str], ...]:
        return tuple(pair for chunk in self.chunks for pair in chunk)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mops-monthly-revenue-history-plan.v1",
            "start_period": self.start_period,
            "end_period": self.end_period,
            "markets": list(self.markets),
            "requested_period_count": len(_all_bounded_periods(self.start_period, self.end_period)),
            "requested_pairs": [list(pair) for pair in self.requested_pairs],
            "chunks": [[list(pair) for pair in chunk] for chunk in self.chunks],
            "plan_sha256": self.plan_sha256,
            "network_enabled": False,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueHistoryPlanChunkResult:
    """一批實際嘗試、失敗理由與未處理項目及下一個可續接游標。"""

    plan_sha256: str
    cursor: str
    next_cursor: str | None
    batch: MopsMonthlyRevenueHistoryBatch
    unattempted_pairs: tuple[tuple[MopsHistoryMarket, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mops-monthly-revenue-history-plan-chunk.v1",
            "plan_sha256": self.plan_sha256,
            "cursor": self.cursor,
            "next_cursor": self.next_cursor,
            "attempted_pairs": [list(pair) for pair in self.batch.requested_pairs],
            "captured": [
                {
                    "market": capture.market,
                    "period": capture.period,
                    "source_id": capture.source_id,
                    "source_version": capture.source_version,
                    "revision_id": capture.revision_id,
                    "raw_response_sha256": capture.raw_response_sha256,
                }
                for capture in self.batch.captures
            ],
            "failures": [list(item) for item in self.batch.failures],
            "failure_transport_receipts": [
                item.to_dict() for item in self.batch.failure_receipts
            ],
            "unattempted_pairs": [list(pair) for pair in self.unattempted_pairs],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())


def plan_mops_monthly_revenue_history_capture(
    *,
    start_period: str,
    end_period: str,
    markets: Sequence[MopsHistoryMarket],
) -> MopsMonthlyRevenueHistoryCapturePlan:
    """規劃最多240個月份；不連線，並拆成明確可續接的小批次。"""
    periods = _all_bounded_periods(start_period, end_period)
    if type(markets) not in (tuple, list) or not markets or len(markets) > 2:
        raise MopsMonthlyRevenueHistoryError("markets_count_invalid")
    if len(set(markets)) != len(markets) or any(
        market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS for market in markets
    ):
        raise MopsMonthlyRevenueHistoryError("markets_invalid_or_duplicate")
    market_tuple = tuple(markets)
    chunks: list[tuple[tuple[MopsHistoryMarket, str], ...]] = []
    for offset in range(0, len(periods), MAX_MOPS_MONTHLY_REVENUE_HISTORY_PERIODS_PER_MARKET):
        selected_periods = periods[offset:offset + MAX_MOPS_MONTHLY_REVENUE_HISTORY_PERIODS_PER_MARKET]
        chunks.append(
            tuple((market, period) for market in market_tuple for period in selected_periods)
        )
    identity = {
        "schema_version": "mops-monthly-revenue-history-plan.v1",
        "start_period": start_period,
        "end_period": end_period,
        "markets": list(market_tuple),
        "chunks": [[list(pair) for pair in chunk] for chunk in chunks],
    }
    return MopsMonthlyRevenueHistoryCapturePlan(
        start_period=start_period,
        end_period=end_period,
        markets=market_tuple,
        chunks=tuple(chunks),
        plan_sha256=hashlib.sha256(_canonical_json_bytes(identity)).hexdigest(),
    )


def capture_mops_monthly_revenue_history_plan_chunk(
    plan: MopsMonthlyRevenueHistoryCapturePlan,
    *,
    cursor: str | None = None,
    timeout_seconds: float = MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
    transport_mode: str = "direct_static_v1",
) -> MopsMonthlyRevenueHistoryPlanChunkResult:
    """只執行游標指定的有界年月；transport模式必須由呼叫端明選。"""
    if type(plan) is not MopsMonthlyRevenueHistoryCapturePlan:
        raise MopsMonthlyRevenueHistoryError("plan_type_invalid")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int))
            or not 0 < float(timeout_seconds) <= MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS):
        raise MopsMonthlyRevenueHistoryError("timeout_out_of_bounds")
    _validate_transport_mode(transport_mode)
    index = _plan_cursor_index(plan, cursor)
    selected = plan.chunks[index]
    captures: list[MopsMonthlyRevenueHistoricalCapture] = []
    failures: list[tuple[MopsHistoryMarket, str, str]] = []
    failure_receipts: list[MopsMonthlyRevenueHistoryFailureReceipt] = []
    for market, period in selected:
        try:
            captures.append(
                capture_mops_monthly_revenue_history_period(
                    market=market,
                    period=period,
                    timeout_seconds=float(timeout_seconds),
                    transport_mode=transport_mode,
                )
            )
        except Exception as exc:
            failures.append((market, period, _safe_error(exc)))
            hops = getattr(exc, "transport_hops", ())
            if hops:
                failure_receipts.append(MopsMonthlyRevenueHistoryFailureReceipt(
                    market=market,
                    period=period,
                    transport_mode=transport_mode,
                    reason_code=_safe_error(exc),
                    transport_hops=tuple(hops),
                ))
    batch = MopsMonthlyRevenueHistoryBatch(
        requested_pairs=selected,
        captures=tuple(captures),
        failures=tuple(failures),
        failure_receipts=tuple(failure_receipts),
    )
    next_index = index + 1
    next_cursor = _plan_cursor(plan, next_index) if next_index < len(plan.chunks) else None
    remaining = tuple(
        pair for chunk in plan.chunks[next_index:] for pair in chunk
    )
    return MopsMonthlyRevenueHistoryPlanChunkResult(
        plan_sha256=plan.plan_sha256,
        cursor=_plan_cursor(plan, index),
        next_cursor=next_cursor,
        batch=batch,
        unattempted_pairs=remaining,
    )


def write_mops_monthly_revenue_history_plan_create_only(
    path: Path | str, plan: MopsMonthlyRevenueHistoryCapturePlan
) -> tuple[Path, str]:
    if type(plan) is not MopsMonthlyRevenueHistoryCapturePlan:
        raise MopsMonthlyRevenueHistoryError("plan_type_invalid")
    _plan_cursor_index(plan, None)
    return _write_small_json_create_only(path, plan.canonical_bytes(), "plan")


def write_mops_monthly_revenue_history_plan_chunk_receipt_create_only(
    path: Path | str, result: MopsMonthlyRevenueHistoryPlanChunkResult
) -> tuple[Path, str]:
    if type(result) is not MopsMonthlyRevenueHistoryPlanChunkResult:
        raise MopsMonthlyRevenueHistoryError("plan_chunk_result_type_invalid")
    payload = result.canonical_bytes()
    if len(payload) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_CHUNK_RECEIPT_BYTES:
        raise MopsMonthlyRevenueHistoryError("plan_chunk_receipt_artifact_size_exceeds_limit")
    return _write_small_json_create_only(
        path, payload, "plan_chunk_receipt", max_bytes=MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_CHUNK_RECEIPT_BYTES
    )


def _write_small_json_create_only(
    path: Path | str, payload: bytes, label: str, *, max_bytes: int = MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_ARTIFACT_BYTES
) -> tuple[Path, str]:
    target = Path(path).expanduser()
    if not target.is_absolute() or target.parent.resolve(strict=True) != target.parent:
        raise MopsMonthlyRevenueHistoryError(f"{label}_artifact_path_invalid")
    if len(payload) > max_bytes:
        raise MopsMonthlyRevenueHistoryError(f"{label}_artifact_size_exceeds_limit")
    try:
        descriptor = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            if stream.write(payload) != len(payload):
                raise MopsMonthlyRevenueHistoryError(f"{label}_artifact_short_write")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise MopsMonthlyRevenueHistoryError(f"{label}_artifact_create_only_conflict") from exc
    except OSError as exc:
        raise MopsMonthlyRevenueHistoryError(f"{label}_artifact_write_failed") from exc
    return target, hashlib.sha256(payload).hexdigest()


def capture_mops_monthly_revenue_history_batch(
    *,
    start_period: str,
    end_period: str,
    markets: Sequence[MopsHistoryMarket],
    timeout_seconds: float = MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
    transport_mode: str = "direct_static_v1",
) -> MopsMonthlyRevenueHistoryBatch:
    """逐市場／月份擷取MOPS歷史報告；模式明選且失敗不自動重試。"""
    periods = _bounded_periods(start_period, end_period)
    if type(markets) not in (tuple, list) or not markets:
        raise MopsMonthlyRevenueHistoryError("markets_must_be_nonempty_tuple_or_list")
    if len(markets) > 2 or len(set(markets)) != len(markets):
        raise MopsMonthlyRevenueHistoryError("markets_count_or_duplicate_invalid")
    if any(market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS for market in markets):
        raise MopsMonthlyRevenueHistoryError("market_unsupported")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int))
            or not 0 < float(timeout_seconds) <= MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS):
        raise MopsMonthlyRevenueHistoryError("timeout_out_of_bounds")
    _validate_transport_mode(transport_mode)
    requested_pairs = tuple((market, period) for market in markets for period in periods)
    if len(requested_pairs) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CAPTURES:
        raise MopsMonthlyRevenueHistoryError("batch_capture_count_out_of_bounds")
    captures: list[MopsMonthlyRevenueHistoricalCapture] = []
    failures: list[tuple[MopsHistoryMarket, str, str]] = []
    failure_receipts: list[MopsMonthlyRevenueHistoryFailureReceipt] = []
    for market, period in requested_pairs:
        try:
            captures.append(
                capture_mops_monthly_revenue_history_period(
                    market=market, period=period, timeout_seconds=float(timeout_seconds),
                    transport_mode=transport_mode,
                )
            )
        except Exception as exc:
            failures.append((market, period, _safe_error(exc)))
            hops = getattr(exc, "transport_hops", ())
            if hops:
                failure_receipts.append(MopsMonthlyRevenueHistoryFailureReceipt(
                    market=market, period=period, transport_mode=transport_mode,
                    reason_code=_safe_error(exc), transport_hops=tuple(hops),
                ))
    return MopsMonthlyRevenueHistoryBatch(
        requested_pairs=requested_pairs,
        captures=tuple(captures),
        failures=tuple(failures),
        failure_receipts=tuple(failure_receipts),
    )


def capture_mops_monthly_revenue_history_period(
    *,
    market: MopsHistoryMarket,
    period: str,
    timeout_seconds: float = MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS,
    transport_mode: str = "direct_static_v1",
) -> MopsMonthlyRevenueHistoricalCapture:
    """單次明確模式擷取一個精確市場／月份，不會在direct/redirect間fallback。"""
    if market not in MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS:
        raise MopsMonthlyRevenueHistoryError("market_unsupported")
    _validate_period(period)
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int))
            or not 0 < float(timeout_seconds) <= MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS):
        raise MopsMonthlyRevenueHistoryError("timeout_out_of_bounds")
    _validate_transport_mode(transport_mode)
    if transport_mode == "redirect_chain_v1":
        return _capture_mops_monthly_revenue_history_redirect_chain(
            market=market, period=period, timeout_seconds=float(timeout_seconds)
        )
    url = _official_history_url(market, period)
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://mops.twse.com.tw/mops/#/web/t21sc04_ifrs",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=float(timeout_seconds)) as response:
            response_url = response.geturl()
            status = int(response.status)
            headers = response.headers
            content_type = headers.get("Content-Type", "")
            content_encoding = headers.get("Content-Encoding")
            transfer_encoding = headers.get("Transfer-Encoding")
            content_length = headers.get("Content-Length")
            _validate_transfer_encoding(transfer_encoding)
            body = _read_bounded_eof(
                response,
                started_monotonic=started_monotonic,
                timeout_seconds=float(timeout_seconds),
            )
            ended = datetime.now(timezone.utc)
    except MopsMonthlyRevenueHistoryError:
        raise
    except Exception as exc:
        raise MopsMonthlyRevenueHistoryError("official_http_get_failed") from exc
    if status != 200:
        raise MopsMonthlyRevenueHistoryError("http_status_not_200")
    if response_url != url:
        raise MopsMonthlyRevenueHistoryError("response_url_redirected_or_changed")
    if not content_type or content_type.split(";", 1)[0].strip().lower() not in {
        "text/html", "application/xhtml+xml"
    }:
        raise MopsMonthlyRevenueHistoryError("content_type_not_html")
    if content_encoding not in {None, "", "identity"}:
        raise MopsMonthlyRevenueHistoryError("content_encoding_not_identity")
    header_charset = _content_type_charset_text(content_type)
    meta_charset = _html_meta_charset_text(body)
    if header_charset is not None:
        encoding = header_charset
        basis = "http_content_type_charset"
    elif meta_charset is not None:
        encoding = meta_charset
        basis = "html_meta_charset"
    else:
        raise MopsMonthlyRevenueHistoryError("html_charset_evidence_missing")
    raw_sha = hashlib.sha256(body).hexdigest()
    try:
        transport = DailySourceTransportCapture(
            raw_response_bytes=body,
            official_source_url=url,
            response_status=status,
            content_type=content_type,
            declared_decoding_encoding=encoding,
            decoding_basis=basis,
            body_completed_at=ended,
            transport_sha256=raw_sha,
            response_body_complete=True,
            received_body_bytes=len(body),
            content_length_original_text=content_length,
            body_completion_evidence_ref="eof:mops-bounded-history-read-until-empty",
            html_meta_charset_original_text=meta_charset,
            response_url=response_url,
            content_encoding_original_text=content_encoding,
            eof_observed=True,
            body_observation_ended_at=ended,
        )
        return MopsMonthlyRevenueHistoricalCapture(
            market=market,
            period=period,
            requested_url=url,
            response_url=response_url,
            request_started_at=started,
            transport_capture=transport,
        )
    except (DailySourceSnapshotError, TypeError, ValueError) as exc:
        if isinstance(exc, MopsMonthlyRevenueHistoryError):
            raise
        raise MopsMonthlyRevenueHistoryError("transport_or_report_validation_failed") from exc


def _capture_mops_monthly_revenue_history_redirect_chain(
    *, market: MopsHistoryMarket, period: str, timeout_seconds: float
) -> MopsMonthlyRevenueHistoricalCapture:
    """依MOPS既有POST→popup→static鏈擷取，三跳各自受絕對期限與總bytes限制。"""
    hops: list[MopsMonthlyRevenueTransportHop] = []
    first_started: datetime | None = None
    redirect_body = json.dumps(
        {
            "apiName": "ajax_t21sc04_ifrs",
            "parameters": {
                "TYPEK": MOPS_STATIC_TYPEK[market],
                "year": str(int(period[:4]) - 1911),
                "month": period[5:7],
                "encodeURIComponent": 1,
                "firstin": 1,
                "step": 1,
                "off": 1,
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    redirect_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://mops.twse.com.tw",
        "Referer": "https://mops.twse.com.tw/mops/#/web/t21sc04_ifrs",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        first = _perform_redirect_hop(
            method="POST", url=MOPS_REDIRECT_API_URL, headers=redirect_headers,
            body=redirect_body, timeout_seconds=timeout_seconds,
            remaining_chain_bytes=MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES,
        )
        hops.append(first)
        first_started = first.request_started_at
        _reject_known_challenge(first)
        _require_hop_success(first, expected_url=MOPS_REDIRECT_API_URL, expected_status=200)
        if (_header_value(first.response_headers, "content-type") or "").split(";", 1)[0].strip().lower() != "application/json":
            raise MopsMonthlyRevenueHistoryError("redirect_response_content_type_not_json")
        redirect_payload = json.loads(first.raw_response_bytes.decode("utf-8", errors="strict"))
        if not isinstance(redirect_payload, dict):
            raise MopsMonthlyRevenueHistoryError("redirect_response_json_invalid")
        report_url = redirect_payload.get("result", {}).get("url") if isinstance(redirect_payload.get("result"), dict) else None
        if not isinstance(report_url, str) or not _is_official_popup_url(report_url):
            raise MopsMonthlyRevenueHistoryError("redirect_popup_url_invalid")

        second = _perform_redirect_hop(
            method="GET", url=report_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://mops.twse.com.tw/mops/#/web/t21sc04_ifrs",
                "User-Agent": "Mozilla/5.0",
            },
            body=b"", timeout_seconds=timeout_seconds,
            remaining_chain_bytes=MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES - _hop_bytes(hops),
        )
        hops.append(second)
        _reject_known_challenge(second)
        _require_hop_success(second, expected_url=report_url, expected_status=200)
        popup_html = _decode_hop_html(second)
        static_path = _extract_mops_static_path(popup_html)
        if static_path is None or not _valid_static_path_for_period(static_path, market, period):
            raise MopsMonthlyRevenueHistoryError("popup_static_path_market_period_mismatch")
        static_url = f"https://mopsov.twse.com.tw{static_path}"

        third = _perform_redirect_hop(
            method="GET", url=static_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": report_url,
                "User-Agent": "Mozilla/5.0",
            },
            body=b"", timeout_seconds=timeout_seconds,
            remaining_chain_bytes=MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES - _hop_bytes(hops),
        )
        hops.append(third)
        _reject_known_challenge(third)
        _require_hop_success(third, expected_url=static_url, expected_status=200)
        if not third.eof_observed:
            raise MopsMonthlyRevenueHistoryError("static_response_truncated")
        if _hop_bytes(hops) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES:
            raise MopsMonthlyRevenueHistoryError("transport_chain_body_exceeds_limit")
        chain_json = _canonical_json_bytes([hop.to_dict() for hop in hops])
        if len(chain_json) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_JSON_BYTES:
            raise MopsMonthlyRevenueHistoryError("transport_chain_metadata_exceeds_limit")

        content_type = _header_value(third.response_headers, "content-type")
        content_encoding = _header_value(third.response_headers, "content-encoding")
        content_length = _header_value(third.response_headers, "content-length")
        if not content_type or content_type.split(";", 1)[0].strip().lower() not in {
            "text/html", "application/xhtml+xml"
        }:
            raise MopsMonthlyRevenueHistoryError("content_type_not_html")
        if content_encoding not in {None, "", "identity"}:
            raise MopsMonthlyRevenueHistoryError("content_encoding_not_identity")
        meta_charset = _html_meta_charset_text(third.raw_response_bytes)
        header_charset = _content_type_charset_text(content_type)
        if header_charset is not None:
            encoding, basis = header_charset, "http_content_type_charset"
        elif meta_charset is not None:
            encoding, basis = meta_charset, "html_meta_charset"
        else:
            raise MopsMonthlyRevenueHistoryError("html_charset_evidence_missing")
        final_capture = DailySourceTransportCapture(
            raw_response_bytes=third.raw_response_bytes,
            official_source_url=static_url,
            response_status=third.response_status,
            content_type=content_type,
            declared_decoding_encoding=encoding,
            decoding_basis=basis,
            body_completed_at=third.response_body_completed_at,
            transport_sha256=third.complete_raw_sha256,
            response_body_complete=third.eof_observed,
            received_body_bytes=len(third.raw_response_bytes),
            content_length_original_text=content_length,
            body_completion_evidence_ref="eof:mops-redirect-chain-bounded-read1",
            html_meta_charset_original_text=meta_charset,
            response_url=third.response_url,
            content_encoding_original_text=content_encoding,
            eof_observed=third.eof_observed,
            body_observation_ended_at=third.body_observation_ended_at,
        )
        return MopsMonthlyRevenueHistoricalCapture(
            market=market,
            period=period,
            requested_url=static_url,
            response_url=third.response_url,
            request_started_at=first_started or third.request_started_at,
            transport_capture=final_capture,
            transport_mode="redirect_chain_v1",
            transport_hops=tuple(hops),
        )
    except Exception as exc:
        if isinstance(exc, MopsMonthlyRevenueHistoryError):
            error = exc
        else:
            error = MopsMonthlyRevenueHistoryError(
                f"redirect_chain_failed:{type(exc).__name__}:{str(exc)[:180]}"
            )
        captured_hops = tuple(getattr(error, "transport_hops", ()))
        error.transport_hops = tuple(hops) + tuple(
            hop for hop in captured_hops if hop not in hops
        )
        raise error from (exc if error is not exc else None)


def _perform_redirect_hop(
    *, method: str, url: str, headers: dict[str, str], body: bytes,
    timeout_seconds: float, remaining_chain_bytes: int,
) -> MopsMonthlyRevenueTransportHop:
    if remaining_chain_bytes <= 0:
        raise MopsMonthlyRevenueHistoryError("transport_chain_body_budget_exhausted")
    _validate_hop_request_url(method, url)
    safe_request_headers = tuple(sorted(
        (key.lower(), value) for key, value in headers.items()
        if key.lower() in {"accept", "content-type", "origin", "referer", "user-agent"}
    ))
    request = Request(url, data=body if method == "POST" else None, headers=headers, method=method)
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    response = None
    try:
        opener = build_opener(_NoRedirectHandler())
        try:
            response = opener.open(request, timeout=timeout_seconds)
        except HTTPError as http_error:
            response = http_error
        response_url = response.geturl()
        status = _require_response_status(response)
        safe_response_headers = _safe_response_headers(response.headers)
        raw, eof, truncated, ended = _read_transport_prefix(
            response,
            started_monotonic=started_monotonic,
            timeout_seconds=timeout_seconds,
            max_bytes=min(MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES, remaining_chain_bytes),
        )
        hop = MopsMonthlyRevenueTransportHop(
            method=method, request_url=url, request_headers=safe_request_headers,
            request_body=body, request_started_at=started, response_url=response_url,
            response_status=status, response_headers=safe_response_headers,
            raw_response_bytes=raw, observed_bytes_sha256=hashlib.sha256(raw).hexdigest(),
            response_body_completed_at=ended, body_observation_ended_at=ended,
            eof_observed=eof, body_truncated=truncated,
        )
        if not eof:
            raise MopsMonthlyRevenueHistoryError("response_body_truncated", transport_hops=(hop,))
        return hop
    except MopsMonthlyRevenueHistoryError:
        raise
    except Exception as exc:
        if response is not None:
            raw = b""
            ended = datetime.now(timezone.utc)
            try:
                raw, _, _, ended = _read_transport_prefix(
                    response,
                    started_monotonic=started_monotonic,
                    timeout_seconds=timeout_seconds,
                    max_bytes=min(MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES, remaining_chain_bytes),
                )
            except Exception:
                pass
            status = _require_response_status(response)
            response_url = response.geturl()
            hop = MopsMonthlyRevenueTransportHop(
                method=method, request_url=url, request_headers=safe_request_headers,
                request_body=body, request_started_at=started, response_url=response_url,
                response_status=status, response_headers=_safe_response_headers(response.headers),
                raw_response_bytes=raw, observed_bytes_sha256=hashlib.sha256(raw).hexdigest(),
                response_body_completed_at=ended, body_observation_ended_at=ended,
                eof_observed=False, body_truncated=True,
            )
            raise MopsMonthlyRevenueHistoryError(
                f"transport_hop_failed:{type(exc).__name__}:{str(exc)[:180]}",
                transport_hops=(hop,),
            ) from exc
        raise MopsMonthlyRevenueHistoryError(
            f"transport_hop_failed:{type(exc).__name__}:{str(exc)[:180]}"
        ) from exc
    finally:
        if response is not None:
            response.close()


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_transport_prefix(response, *, started_monotonic: float, timeout_seconds: float, max_bytes: int) -> tuple[bytes, bool, bool, datetime]:
    chunks: list[bytes] = []
    total = 0
    deadline = started_monotonic + timeout_seconds
    # HTTPResponse.read1 會處理 Transfer-Encoding；直接讀 response.fp 會拿到chunk framing。
    read_once = getattr(response, "read1", None)
    if not callable(read_once):
        raise MopsMonthlyRevenueHistoryError("bounded_single_read_unavailable")
    while total <= max_bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return b"".join(chunks), False, True, datetime.now(timezone.utc)
        try:
            _set_response_socket_deadline(response, remaining)
        except Exception:
            if _http_response_framing_complete(response) is True:
                # 固定長度/分塊 framing 已完整耗盡；高層reader此時只會回傳空值。
                pass
            else:
                return b"".join(chunks), False, True, datetime.now(timezone.utc)
        try:
            piece = read_once(min(64 * 1024, max_bytes + 1 - total))
        except Exception:
            return b"".join(chunks), False, True, datetime.now(timezone.utc)
        if not piece:
            if time.monotonic() >= deadline:
                return b"".join(chunks), False, True, datetime.now(timezone.utc)
            framing_complete = _http_response_framing_complete(response)
            if framing_complete is False:
                return b"".join(chunks), False, True, datetime.now(timezone.utc)
            return b"".join(chunks), True, False, datetime.now(timezone.utc)
        accepted = piece[: max(0, max_bytes - total)]
        if accepted:
            chunks.append(accepted)
            total += len(accepted)
        if len(piece) > len(accepted):
            return b"".join(chunks), False, True, datetime.now(timezone.utc)
        if time.monotonic() >= deadline:
            return b"".join(chunks), False, True, datetime.now(timezone.utc)
    return b"".join(chunks), False, True, datetime.now(timezone.utc)


def _safe_response_headers(headers: object) -> tuple[tuple[str, str], ...]:
    allowed = {"content-type", "content-encoding", "content-length", "date", "location", "transfer-encoding"}
    pairs: list[tuple[str, str]] = []
    if hasattr(headers, "items"):
        for key, value in headers.items():
            name = str(key).lower()
            if name in allowed:
                pairs.append((name, str(value)))
    return tuple(sorted(pairs))


def _require_response_status(response: object) -> int:
    """取得實際HTTP狀態；缺值或非有效狀態時拒絕合成 transport receipt。"""
    status = getattr(response, "status", None)
    if status is None:
        status = getattr(response, "code", None)
    if type(status) is not int or not 100 <= status <= 599:
        raise MopsMonthlyRevenueHistoryError("transport_http_status_missing_or_invalid")
    return status


def _header_value(headers: tuple[tuple[str, str], ...], name: str) -> str | None:
    return next((value for key, value in headers if key == name), None)


def _hop_bytes(hops: Sequence[MopsMonthlyRevenueTransportHop]) -> int:
    return sum(len(hop.raw_response_bytes) for hop in hops)


def _require_hop_success(hop: MopsMonthlyRevenueTransportHop, *, expected_url: str, expected_status: int) -> None:
    if hop.request_url != expected_url or hop.response_url != expected_url:
        raise MopsMonthlyRevenueHistoryError("transport_hop_url_redirect_or_mismatch")
    if hop.response_status != expected_status:
        raise MopsMonthlyRevenueHistoryError(f"transport_hop_http_status_{hop.response_status}")
    if not hop.eof_observed or hop.body_truncated:
        raise MopsMonthlyRevenueHistoryError("transport_hop_incomplete_body")
    if _header_value(hop.response_headers, "content-encoding") not in {None, "", "identity"}:
        raise MopsMonthlyRevenueHistoryError("transport_hop_content_encoding_not_identity")
    _validate_transfer_encoding(_header_value(hop.response_headers, "transfer-encoding"))
    content_length = _header_value(hop.response_headers, "content-length")
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdigit() or int(content_length) != len(hop.raw_response_bytes):
            raise MopsMonthlyRevenueHistoryError("transport_hop_content_length_mismatch")


def _validate_transfer_encoding(value: str | None) -> None:
    if value is not None and value.strip().casefold() != "chunked":
        raise MopsMonthlyRevenueHistoryError("transport_transfer_encoding_unsupported")


def _reject_known_challenge(hop: MopsMonthlyRevenueTransportHop) -> None:
    text = "\n".join((
        hop.raw_response_bytes.decode("utf-8", errors="ignore"),
        hop.raw_response_bytes.decode("big5", errors="ignore"),
    )).casefold()
    markers = ("captcha", "驗證碼", "機器人", "robot check", "access denied", "challenge")
    if any(marker.casefold() in text for marker in markers):
        raise MopsMonthlyRevenueHistoryError("official_challenge_response")


def _decode_hop_html(hop: MopsMonthlyRevenueTransportHop) -> str:
    content_type = _header_value(hop.response_headers, "content-type") or ""
    encoding = _content_type_charset_text(content_type) or _html_meta_charset_text(hop.raw_response_bytes)
    if encoding is None:
        raise MopsMonthlyRevenueHistoryError("popup_html_charset_evidence_missing")
    return hop.raw_response_bytes.decode(encoding, errors="strict")


def _is_official_popup_url(value: str) -> bool:
    if type(value) is not str or len(value) > 8192:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if not (
        parsed.scheme == "https"
        and parsed.hostname == "mopsov.twse.com.tw"
        and parsed.username is None and parsed.password is None and port in (None, 443)
        and not parsed.fragment
    ):
        return False
    if parsed.path == "/mops/web/t21sc04_ifrs":
        return not parsed.query
    if parsed.path != "/mops/web/ajax_t21sc04_ifrs":
        return False
    return re.fullmatch(r"parameters=[0-9A-Fa-f]{2,4096}", parsed.query) is not None


def _valid_static_path_for_period(path: str, market: MopsHistoryMarket, period: str) -> bool:
    folder = MOPS_STATIC_MARKET_PATH.get(market)
    roc_year = int(period[:4]) - 1911
    month = int(period[5:7])
    expected = f"/nas/t21/{folder}/t21sc03_{roc_year}_{month}_0.html"
    return path == expected


def _validate_hop_request_url(method: str, url: str) -> None:
    parsed = urlsplit(url)
    if method == "POST":
        valid = url == MOPS_REDIRECT_API_URL
    else:
        valid = _is_official_popup_url(url) or (
            parsed.scheme == "https" and parsed.hostname == "mopsov.twse.com.tw"
            and parsed.username is None and parsed.password is None and parsed.port in (None, 443)
            and bool(re.fullmatch(r"/nas/t21/(?:sii|otc)/t21sc03_\d{1,3}_\d{1,2}_0\.html", parsed.path))
            and not parsed.query and not parsed.fragment
        )
    if not valid:
        raise MopsMonthlyRevenueHistoryError("transport_hop_request_url_not_allowlisted")


def _validate_transport_mode(mode: str) -> None:
    if mode not in MOPS_MONTHLY_REVENUE_HISTORY_TRANSPORT_MODES:
        raise MopsMonthlyRevenueHistoryError("transport_mode_invalid")


def _validate_redirect_chain(*, market: MopsHistoryMarket, period: str, requested_url: str,
                             response_url: str, request_started_at: datetime,
                             final_capture: DailySourceTransportCapture,
                             hops: tuple[MopsMonthlyRevenueTransportHop, ...]) -> None:
    if type(hops) is not tuple or len(hops) != 3:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_hop_count_invalid")
    first, second, third = hops
    _reject_known_challenge(first)
    _reject_known_challenge(second)
    _reject_known_challenge(third)
    _require_hop_success(first, expected_url=MOPS_REDIRECT_API_URL, expected_status=200)
    if first.method != "POST" or first.request_url != MOPS_REDIRECT_API_URL:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_first_hop_invalid")
    if first.response_status != 200 or first.response_url != MOPS_REDIRECT_API_URL:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_first_response_invalid")
    if (_header_value(first.response_headers, "content-type") or "").split(";", 1)[0].strip().lower() != "application/json":
        raise MopsMonthlyRevenueHistoryError("redirect_response_content_type_not_json")
    try:
        post_payload = json.loads(first.request_body.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_post_body_invalid") from exc
    params = post_payload.get("parameters") if isinstance(post_payload, dict) else None
    expected_params = {
        "TYPEK": MOPS_STATIC_TYPEK[market],
        "year": str(int(period[:4]) - 1911),
        "month": period[5:7],
        "encodeURIComponent": 1,
        "firstin": 1,
        "step": 1,
        "off": 1,
    }
    if (
        not isinstance(post_payload, dict)
        or set(post_payload) != {"apiName", "parameters"}
        or post_payload.get("apiName") != "ajax_t21sc04_ifrs"
        or params != expected_params
    ):
        raise MopsMonthlyRevenueHistoryError("redirect_chain_post_market_period_mismatch")
    try:
        redirect_payload = json.loads(first.raw_response_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_response_json_invalid") from exc
    result = redirect_payload.get("result") if isinstance(redirect_payload, dict) else None
    popup_url = result.get("url") if isinstance(result, dict) else None
    if not isinstance(popup_url, str) or second.method != "GET" or second.request_url != popup_url or not _is_official_popup_url(popup_url):
        raise MopsMonthlyRevenueHistoryError("redirect_chain_popup_url_mismatch")
    _require_hop_success(second, expected_url=popup_url, expected_status=200)
    if second.response_status != 200 or second.response_url != popup_url or not second.eof_observed:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_popup_response_invalid")
    if _header_value(second.response_headers, "content-encoding") not in {None, "", "identity"}:
        raise MopsMonthlyRevenueHistoryError("popup_content_encoding_not_identity")
    if (_header_value(second.response_headers, "content-type") or "").split(";", 1)[0].strip().lower() not in {"text/html", "application/xhtml+xml"}:
        raise MopsMonthlyRevenueHistoryError("popup_content_type_not_html")
    popup = _decode_hop_html(second)
    popup_path = _extract_mops_static_path(popup)
    if popup_path is None or not _valid_static_path_for_period(popup_path, market, period):
        raise MopsMonthlyRevenueHistoryError("redirect_chain_static_market_period_mismatch")
    expected_static_url = f"https://mopsov.twse.com.tw{popup_path}"
    if third.method != "GET" or third.request_url != expected_static_url or third.response_url != expected_static_url:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_static_url_mismatch")
    _require_hop_success(third, expected_url=expected_static_url, expected_status=200)
    if not third.eof_observed or third.response_status != 200:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_static_response_invalid")
    if (_header_value(third.response_headers, "content-type") or "").split(";", 1)[0].strip().lower() not in {"text/html", "application/xhtml+xml"}:
        raise MopsMonthlyRevenueHistoryError("static_content_type_not_html")
    if _header_value(third.response_headers, "content-encoding") not in {None, "", "identity"}:
        raise MopsMonthlyRevenueHistoryError("static_content_encoding_not_identity")
    if requested_url != expected_static_url or response_url != expected_static_url:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_report_url_mismatch")
    if first.request_started_at != request_started_at:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_started_at_mismatch")
    if final_capture.raw_response_bytes != third.raw_response_bytes or final_capture.transport_sha256 != third.complete_raw_sha256:
        raise MopsMonthlyRevenueHistoryError("redirect_chain_final_raw_mismatch")
    if _hop_bytes(hops) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_BYTES:
        raise MopsMonthlyRevenueHistoryError("transport_chain_body_exceeds_limit")
    if len(_canonical_json_bytes([hop.to_dict() for hop in hops])) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_CHAIN_JSON_BYTES:
        raise MopsMonthlyRevenueHistoryError("transport_chain_metadata_exceeds_limit")


def parse_mops_monthly_revenue_history_capture(
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> tuple[dict[str, str], ...]:
    """重新驗證原件與 transport 後，回傳既有 MOPS snapshot parser rows。"""
    if type(capture) is not MopsMonthlyRevenueHistoricalCapture:
        raise MopsMonthlyRevenueHistoryError("capture_type_invalid")
    _verify_capture(capture)
    return capture.rows


def rebuild_mops_monthly_revenue_history_capture_from_transport_chain(
    *, market: MopsHistoryMarket, period: str, transport_mode: str,
    transport_hops: Sequence[object],
    final_transport_capture: DailySourceTransportCapture,
) -> MopsMonthlyRevenueHistoricalCapture:
    """從archive中的逐跳JSON與raw blob重建capture並重新驗證全鏈。"""
    if transport_mode != "redirect_chain_v1":
        raise MopsMonthlyRevenueHistoryError("transport_chain_mode_unsupported")
    if type(final_transport_capture) is not DailySourceTransportCapture:
        raise MopsMonthlyRevenueHistoryError("final_transport_capture_type_invalid")
    if type(transport_hops) not in (tuple, list):
        raise MopsMonthlyRevenueHistoryError("transport_hops_collection_invalid")
    hops = tuple(
        item if type(item) is MopsMonthlyRevenueTransportHop else _transport_hop_from_dict(item)
        for item in transport_hops
    )
    if not hops:
        raise MopsMonthlyRevenueHistoryError("transport_chain_empty")
    response_url = final_transport_capture.response_url
    if not response_url:
        raise MopsMonthlyRevenueHistoryError("final_transport_response_url_missing")
    capture = MopsMonthlyRevenueHistoricalCapture(
        market=market,
        period=period,
        requested_url=final_transport_capture.official_source_url,
        response_url=response_url,
        request_started_at=hops[0].request_started_at,
        transport_capture=final_transport_capture,
        transport_mode=transport_mode,
        transport_hops=hops,
    )
    _verify_capture(capture)
    return capture


def write_mops_monthly_revenue_history_capture_create_only(
    path: Path | str, capture: MopsMonthlyRevenueHistoricalCapture
) -> Path:
    if type(capture) is not MopsMonthlyRevenueHistoricalCapture:
        raise MopsMonthlyRevenueHistoryError("capture_type_invalid")
    _verify_capture(capture)
    target = Path(path).expanduser()
    if not target.is_absolute() or target.parent.resolve(strict=True) != target.parent:
        raise MopsMonthlyRevenueHistoryError("artifact_path_invalid")
    payload = capture.canonical_bytes()
    if len(payload) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_ARTIFACT_BYTES:
        raise MopsMonthlyRevenueHistoryError("artifact_size_exceeds_limit")
    try:
        descriptor = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            if stream.write(payload) != len(payload):
                raise MopsMonthlyRevenueHistoryError("artifact_short_write")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise MopsMonthlyRevenueHistoryError("artifact_create_only_conflict") from exc
    except OSError as exc:
        raise MopsMonthlyRevenueHistoryError("artifact_write_failed") from exc
    return target


def read_mops_monthly_revenue_history_capture(
    path: Path | str, *, expected_sha256: str
) -> MopsMonthlyRevenueHistoricalCapture:
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise MopsMonthlyRevenueHistoryError("expected_sha256_invalid")
    target = Path(path).expanduser()
    if (
        not target.is_absolute()
        or target.parent.resolve(strict=True) != target.parent
        or target.is_symlink()
    ):
        raise MopsMonthlyRevenueHistoryError("artifact_path_invalid")
    try:
        before = target.lstat()
    except OSError as exc:
        raise MopsMonthlyRevenueHistoryError("artifact_missing_or_unreadable") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_MOPS_MONTHLY_REVENUE_HISTORY_ARTIFACT_BYTES
    ):
        raise MopsMonthlyRevenueHistoryError("artifact_file_invalid_or_exceeds_limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (before.st_dev, before.st_ino, before.st_size)
                or opened.st_size > MAX_MOPS_MONTHLY_REVENUE_HISTORY_ARTIFACT_BYTES
            ):
                raise MopsMonthlyRevenueHistoryError("artifact_open_file_identity_mismatch")
            raw = stream.read(MAX_MOPS_MONTHLY_REVENUE_HISTORY_ARTIFACT_BYTES + 1)
            if len(raw) != opened.st_size or stream.read(1):
                raise MopsMonthlyRevenueHistoryError("artifact_size_changed_during_read")
    except OSError as exc:
        raise MopsMonthlyRevenueHistoryError("artifact_read_failed") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise MopsMonthlyRevenueHistoryError("artifact_sha256_mismatch")
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique_pairs)
        if _canonical_json_bytes(payload) != raw:
            raise MopsMonthlyRevenueHistoryError("artifact_not_canonical")
        base_keys = {
            "schema_version", "dataset_id", "market", "period", "source_id", "source_version",
            "revision_id", "parent_revision_id", "requested_url", "response_url", "request_started_at",
            "body_completed_at", "body_observation_ended_at", "raw_response_sha256", "raw_response_bytes",
            "transport_capture", "parser_version", "reused_row_parser", "printed_report_date",
            "observed_unit_annotations", "source_unit", "normalized_currency_unit", "availability_at",
            "availability_basis", "historical_pit_eligible", "license_status", "rows",
            "raw_source_values_by_stock_code",
        }
        redirect_keys = base_keys | {"transport_mode", "transport_hops"}
        payload_keys = frozenset(payload) if isinstance(payload, dict) else frozenset()
        if not isinstance(payload, dict) or payload_keys not in {frozenset(base_keys), frozenset(redirect_keys)}:
            raise MopsMonthlyRevenueHistoryError("artifact_schema_invalid")
        schema_version = payload.get("schema_version")
        is_redirect = schema_version == MOPS_MONTHLY_REVENUE_HISTORY_REDIRECT_SCHEMA_VERSION
        if is_redirect != (payload_keys == frozenset(redirect_keys)):
            raise MopsMonthlyRevenueHistoryError("artifact_schema_mode_mismatch")
        if schema_version not in {
            MOPS_MONTHLY_REVENUE_HISTORY_SCHEMA_VERSION,
            MOPS_MONTHLY_REVENUE_HISTORY_REDIRECT_SCHEMA_VERSION,
        }:
            raise MopsMonthlyRevenueHistoryError("artifact_schema_version_mismatch")
        transport_value = payload["transport_capture"]
        transport = _transport_capture_from_dict(transport_value)
        hops: tuple[MopsMonthlyRevenueTransportHop, ...] = ()
        mode = "direct_static_v1"
        if is_redirect:
            mode = payload["transport_mode"]
            raw_hops = payload["transport_hops"]
            if type(raw_hops) is not list:
                raise MopsMonthlyRevenueHistoryError("artifact_transport_hops_invalid")
            hops = tuple(_transport_hop_from_dict(item) for item in raw_hops)
        capture = MopsMonthlyRevenueHistoricalCapture(
            market=payload["market"],
            period=payload["period"],
            requested_url=payload["requested_url"],
            response_url=payload["response_url"],
            request_started_at=_parse_aware_datetime(payload["request_started_at"]),
            transport_capture=transport,
            transport_mode=mode,
            transport_hops=hops,
        )
        if capture.canonical_bytes() != raw:
            raise MopsMonthlyRevenueHistoryError("artifact_content_revalidation_mismatch")
        return capture
    except MopsMonthlyRevenueHistoryError:
        raise
    except (DailySourceSnapshotError, UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
        raise MopsMonthlyRevenueHistoryError("artifact_invalid") from exc


def _verify_capture(capture: MopsMonthlyRevenueHistoricalCapture) -> None:
    if capture.raw_response_sha256 != hashlib.sha256(capture.raw_response_bytes).hexdigest():
        raise MopsMonthlyRevenueHistoryError("raw_response_sha256_mismatch")
    if capture.source_version != _expected_capture_source_version(capture):
        raise MopsMonthlyRevenueHistoryError("source_version_mismatch")
    if capture.revision_id != f"sha256:{capture.raw_response_sha256}":
        raise MopsMonthlyRevenueHistoryError("revision_id_mismatch")
    _ = capture.rows


def _expected_capture_source_version(capture: MopsMonthlyRevenueHistoricalCapture) -> str:
    completed = _datetime_text(capture.transport_capture.body_completed_at)
    if capture.transport_mode == "redirect_chain_v1":
        chain_sha = hashlib.sha256(_canonical_json_bytes(
            [hop.to_dict() for hop in capture.transport_hops]
        )).hexdigest()
        return (
            f"{capture.source_id}.redirect-chain.v1:{capture.period}:captured_at:{completed}"
            f":chain-sha256:{chain_sha}:sha256:{capture.raw_response_sha256}"
        )
    return f"{capture.source_id}.v1:{capture.period}:captured_at:{completed}:sha256:{capture.raw_response_sha256}"


def _transport_hop_from_dict(value: object) -> MopsMonthlyRevenueTransportHop:
    expected = {
        "method", "request_url", "request_headers", "request_body_base64", "request_body_sha256",
        "request_started_at", "response_url", "response_status", "response_headers",
        "response_body_semantics",
        "raw_response_bytes_base64", "raw_response_sha256", "observed_prefix_sha256", "response_body_completed_at",
        "body_observation_ended_at", "eof_observed", "body_truncated",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise MopsMonthlyRevenueHistoryError("artifact_transport_hop_schema_invalid")
    if value["response_body_semantics"] != MOPS_HTTP_ENTITY_BODY_SEMANTICS:
        raise MopsMonthlyRevenueHistoryError("artifact_transport_body_semantics_invalid")
    try:
        request_body = base64.b64decode(value["request_body_base64"], validate=True)
        raw_body = base64.b64decode(value["raw_response_bytes_base64"], validate=True)
        if hashlib.sha256(request_body).hexdigest() != value["request_body_sha256"]:
            raise MopsMonthlyRevenueHistoryError("artifact_transport_request_body_sha_mismatch")
        expected_response_sha = value["observed_prefix_sha256"] if value["eof_observed"] is True else None
        if value["raw_response_sha256"] != expected_response_sha:
            raise MopsMonthlyRevenueHistoryError("artifact_transport_full_sha_eof_mismatch")
        return MopsMonthlyRevenueTransportHop(
            method=value["method"], request_url=value["request_url"],
            request_headers=_header_pairs_from_dict(value["request_headers"]),
            request_body=request_body,
            request_started_at=_parse_aware_datetime(value["request_started_at"]),
            response_url=value["response_url"], response_status=value["response_status"],
            response_headers=_header_pairs_from_dict(value["response_headers"]),
            raw_response_bytes=raw_body, observed_bytes_sha256=value["observed_prefix_sha256"],
            response_body_completed_at=_parse_aware_datetime(value["response_body_completed_at"]),
            body_observation_ended_at=_parse_aware_datetime(value["body_observation_ended_at"]),
            eof_observed=value["eof_observed"], body_truncated=value["body_truncated"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, MopsMonthlyRevenueHistoryError):
            raise
        raise MopsMonthlyRevenueHistoryError("artifact_transport_hop_invalid") from exc


def _header_pairs_from_dict(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not list:
        raise MopsMonthlyRevenueHistoryError("artifact_transport_headers_invalid")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if type(item) is not list or len(item) != 2 or any(type(part) is not str for part in item):
            raise MopsMonthlyRevenueHistoryError("artifact_transport_headers_invalid")
        pairs.append((item[0], item[1]))
    return tuple(pairs)


def _official_history_url(market: MopsHistoryMarket, period: str) -> str:
    _validate_period(period)
    folder = MOPS_STATIC_MARKET_PATH.get(market)
    if folder is None:
        raise MopsMonthlyRevenueHistoryError("market_unsupported")
    year_text, month_text = period.split("-")
    roc_year = int(year_text) - 1911
    if not 1 <= roc_year <= 999:
        raise MopsMonthlyRevenueHistoryError("roc_year_out_of_bounds")
    return (
        "https://mopsov.twse.com.tw/nas/t21/"
        f"{folder}/t21sc03_{roc_year}_{int(month_text)}_0.html"
    )


def _bounded_periods(start_period: str, end_period: str) -> tuple[str, ...]:
    periods = _all_bounded_periods(start_period, end_period)
    if len(periods) > MAX_MOPS_MONTHLY_REVENUE_HISTORY_PERIODS_PER_MARKET:
        raise MopsMonthlyRevenueHistoryError("period_range_exceeds_two_month_limit")
    return periods


def _all_bounded_periods(start_period: str, end_period: str) -> tuple[str, ...]:
    _validate_period(start_period)
    _validate_period(end_period)
    start_year, start_month = (int(part) for part in start_period.split("-"))
    end_year, end_month = (int(part) for part in end_period.split("-"))
    if (start_year, start_month) > (end_year, end_month):
        raise MopsMonthlyRevenueHistoryError("period_range_reversed")
    delta = (end_year - start_year) * 12 + end_month - start_month + 1
    if delta > MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLANNED_PERIODS:
        raise MopsMonthlyRevenueHistoryError("period_range_exceeds_240_month_limit")
    return tuple(
        f"{start_year + (start_month - 1 + offset) // 12:04d}-"
        f"{(start_month - 1 + offset) % 12 + 1:02d}"
        for offset in range(delta)
    )


def _validate_period(value: str) -> None:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise MopsMonthlyRevenueHistoryError("period_invalid")


def _plan_cursor(plan: MopsMonthlyRevenueHistoryCapturePlan, index: int) -> str:
    return f"mops-monthly-revenue-plan.v1:{plan.plan_sha256}:{index}"


def _plan_cursor_index(
    plan: MopsMonthlyRevenueHistoryCapturePlan, cursor: str | None
) -> int:
    expected_plan = plan_mops_monthly_revenue_history_capture(
        start_period=plan.start_period,
        end_period=plan.end_period,
        markets=plan.markets,
    )
    if expected_plan.plan_sha256 != plan.plan_sha256 or expected_plan.chunks != plan.chunks:
        raise MopsMonthlyRevenueHistoryError("plan_content_sha256_mismatch")
    if cursor is None:
        return 0
    prefix = f"mops-monthly-revenue-plan.v1:{plan.plan_sha256}:"
    if not isinstance(cursor, str) or not cursor.startswith(prefix):
        raise MopsMonthlyRevenueHistoryError("plan_cursor_identity_mismatch")
    index_text = cursor[len(prefix):]
    if not index_text.isascii() or not index_text.isdigit():
        raise MopsMonthlyRevenueHistoryError("plan_cursor_invalid")
    index = int(index_text)
    if index < 0 or index >= len(plan.chunks):
        raise MopsMonthlyRevenueHistoryError("plan_cursor_out_of_bounds")
    return index


def _set_response_socket_deadline(response: object, remaining_seconds: float) -> None:
    response_file = getattr(response, "fp", None)
    body_stream = getattr(response_file, "fp", response_file)
    raw_stream = getattr(body_stream, "raw", None)
    response_socket = getattr(raw_stream, "_sock", None)
    if response_socket is None or not callable(getattr(response_socket, "settimeout", None)):
        raise MopsMonthlyRevenueHistoryError("response_socket_deadline_control_unavailable")
    response_socket.settimeout(remaining_seconds)


def _http_response_framing_complete(response: object) -> bool | None:
    """判斷標準HTTPResponse是否依協定parser已消耗完整body framing。"""
    http_response: HTTPResponse | None = None
    if isinstance(response, HTTPResponse):
        http_response = response
    else:
        wrapped = getattr(response, "fp", None)
        if isinstance(wrapped, HTTPResponse):
            http_response = wrapped
    if http_response is None:
        return None
    if http_response.closed or http_response.fp is not None:
        return False
    if http_response.chunked:
        return http_response.chunk_left is None
    if http_response.length == 0:
        return True
    return http_response.length is None and http_response.will_close is True


def _read_bounded_eof(
    response,
    *,
    started_monotonic: float,
    timeout_seconds: float,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    deadline = started_monotonic + timeout_seconds
    # 使用 HTTPResponse 高層reader，讓標準庫依原始header解碼 transfer framing。
    read_once = getattr(response, "read1", None)
    if not callable(read_once):
        raise MopsMonthlyRevenueHistoryError("bounded_single_read_unavailable")
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MopsMonthlyRevenueHistoryError("absolute_body_deadline_exceeded")
        try:
            _set_response_socket_deadline(response, remaining)
        except MopsMonthlyRevenueHistoryError:
            if _http_response_framing_complete(response) is not True:
                raise
        chunk = read_once(
            min(64 * 1024, MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES + 1 - total)
        )
        if time.monotonic() >= deadline:
            raise MopsMonthlyRevenueHistoryError("absolute_body_deadline_exceeded")
        if not chunk:
            if _http_response_framing_complete(response) is False:
                raise MopsMonthlyRevenueHistoryError("response_body_incomplete")
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES:
            raise MopsMonthlyRevenueHistoryError("body_exceeds_limit")
    body = b"".join(chunks)
    if not body:
        raise MopsMonthlyRevenueHistoryError("body_empty")
    return body


def _parse_aware_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise MopsMonthlyRevenueHistoryError("datetime_invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MopsMonthlyRevenueHistoryError("datetime_invalid") from exc
    _require_aware(result, "artifact_datetime")
    return result


def _require_aware(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MopsMonthlyRevenueHistoryError(f"{label}_timezone_missing_or_invalid")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise MopsMonthlyRevenueHistoryError(f"{label}_missing_or_invalid")
    return value


def _datetime_text(value: datetime) -> str:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MopsMonthlyRevenueHistoryError("artifact_duplicate_json_key")
        result[key] = value
    return result


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}:{str(exc)[:240]}"


__all__ = [
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_BYTES",
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_CAPTURES",
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLANNED_PERIODS",
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_PERIODS_PER_MARKET",
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_PLAN_ARTIFACT_BYTES",
    "MAX_MOPS_MONTHLY_REVENUE_HISTORY_TIMEOUT_SECONDS",
    "MOPS_MONTHLY_REVENUE_HISTORY_DATASET_ID",
    "MOPS_MONTHLY_REVENUE_HISTORY_LICENSE_STATUS",
    "MOPS_MONTHLY_REVENUE_HISTORY_PARSER_VERSION",
    "MOPS_MONTHLY_REVENUE_HISTORY_SCHEMA_VERSION",
    "MOPS_MONTHLY_REVENUE_HISTORY_REDIRECT_SCHEMA_VERSION",
    "MOPS_MONTHLY_REVENUE_HISTORY_TRANSPORT_MODES",
    "MOPS_MONTHLY_REVENUE_HISTORY_SOURCE_IDS",
    "MopsMonthlyRevenueTransportHop",
    "MopsMonthlyRevenueHistoryFailureReceipt",
    "MopsMonthlyRevenueHistoricalCapture",
    "MopsMonthlyRevenueHistoryCapturePlan",
    "MopsMonthlyRevenueHistoryBatch",
    "MopsMonthlyRevenueHistoryError",
    "MopsMonthlyRevenueHistoryPlanChunkResult",
    "capture_mops_monthly_revenue_history_plan_chunk",
    "capture_mops_monthly_revenue_history_batch",
    "capture_mops_monthly_revenue_history_period",
    "parse_mops_monthly_revenue_history_capture",
    "rebuild_mops_monthly_revenue_history_capture_from_transport_chain",
    "plan_mops_monthly_revenue_history_capture",
    "write_mops_monthly_revenue_history_plan_chunk_receipt_create_only",
    "write_mops_monthly_revenue_history_plan_create_only",
    "read_mops_monthly_revenue_history_capture",
    "write_mops_monthly_revenue_history_capture_create_only",
]
