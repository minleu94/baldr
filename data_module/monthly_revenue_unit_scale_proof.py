"""為固定的 MOPS 六月歷史 HTML 建立逐產業單位尺度證據。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping

from bs4 import BeautifulSoup, Tag

from data_module.mops_monthly_revenue_history import (
    MOPS_BIG5_CP950_DECODER_PROFILE,
    MOPS_MONTHLY_REVENUE_HISTORY_CP950_PARSER_VERSION,
    MopsMonthlyRevenueHistoricalCapture,
    parse_mops_monthly_revenue_history_capture,
)
from data_module.monthly_revenue_snapshot_harvester import (
    _cell_text,
    _has_required_headers,
    _normalize_header,
)
from data_module.ml_research_output_boundary import (
    MLResearchOutputBoundaryError,
    REPO_ROOT,
    _absolute_candidate,
    _is_reparse_or_link,
    _read_bounded_regular_file_no_follow,
)


MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA = (
    "mops-monthly-revenue-unit-scale-proof.v1"
)
MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_STOCK_CODE_RE = re.compile(r"\A\d{4,6}\Z")


@dataclass(frozen=True, slots=True)
class _SourcePin:
    source_id: str
    url: str
    raw_sha256: str
    raw_bytes: int
    row_count: int
    table_count: int


_JUNE_2026_SOURCE_PINS = {
    "twse": _SourcePin(
        source_id="mops.history.monthly_revenue.twse",
        url="https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_6_0.html",
        raw_sha256="116fa1f6b8a78e8b145b39c1b5048618a92a6df4399698a0d5669ed5c58a5c52",
        raw_bytes=454774,
        row_count=995,
        table_count=33,
    ),
    "tpex": _SourcePin(
        source_id="mops.history.monthly_revenue.tpex",
        url="https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_115_6_0.html",
        raw_sha256="a2e4340708c27b0c208b195a1f4f6829903f72b294d8f16337a0b5c2fd3a19e9",
        raw_bytes=394920,
        row_count=865,
        table_count=28,
    ),
}
_SOURCE_TO_PARSER_FIELDS = (
    ("公司代號", "stock_code", False),
    ("公司名稱", "company_name", False),
    ("當月營收", "current_month_revenue", True),
    ("上月營收", "previous_month_revenue", True),
    ("去年當月營收", "previous_year_month_revenue", True),
    ("上月比較增減(%)", "mom_pct", False),
    ("去年同月增減(%)", "yoy_pct", False),
    ("當月累計營收", "cumulative_revenue", True),
    ("去年累計營收", "previous_year_cumulative_revenue", True),
    ("前期比較增減(%)", "cumulative_yoy_pct", False),
)
_REQUIRED_TABLE_HEADERS = frozenset(item[0] for item in _SOURCE_TO_PARSER_FIELDS)
_UNIT_PREFIX_RE = re.compile(r"\A\s*(?:金額)?單位\s*[:：]")
_INDUSTRY_PREFIX_RE = re.compile(r"\A\s*產業別\s*[:：]")


class MonthlyRevenueUnitScaleProofError(ValueError):
    """MOPS 歷史 HTML 單位尺度證據無法通過固定來源契約。"""


@dataclass(frozen=True, slots=True)
class _TableScope:
    table_index: int
    industry_label: str
    unit_text: str
    headers: tuple[str, ...]
    stock_codes: tuple[str, ...]
    source_rows: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]


@dataclass(frozen=True, slots=True)
class MopsMonthlyRevenueUnitScaleProof:
    """只描述固定 MOPS 原件內明示的千元尺度，不宣稱幣別或用途。"""

    market: str
    source_id: str
    period: str
    official_url: str
    raw_source_sha256: str
    raw_source_bytes: int
    parser_version: str
    decoder_profile: str
    effective_decoding_encoding: str
    tables: tuple[_TableScope, ...]
    row_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA,
            "market": self.market,
            "source_id": self.source_id,
            "period": self.period,
            "official_url": self.official_url,
            "raw_source_sha256": self.raw_source_sha256,
            "raw_source_bytes": self.raw_source_bytes,
            "parser_version": self.parser_version,
            "decoder_profile": self.decoder_profile,
            "effective_decoding_encoding": self.effective_decoding_encoding,
            "unit_text": "千元",
            "scale_to_base_unit": 1000,
            "currency": "unknown",
            "historical_pit_eligible": False,
            "financial_qualification_created": False,
            "source_to_parser_field_mapping": [
                {
                    "source_header": source_header,
                    "parser_field": parser_field,
                    "unit_scale_applies": scale_applies,
                }
                for source_header, parser_field, scale_applies
                in _SOURCE_TO_PARSER_FIELDS
            ],
            "table_scopes": [
                {
                    "table_index": table.table_index,
                    "wrapper": {
                        "industry_label": table.industry_label,
                        "unit_text": table.unit_text,
                    },
                    "inner_table_headers": list(table.headers),
                    "stock_codes": list(table.stock_codes),
                }
                for table in self.tables
            ],
            "row_count": self.row_count,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_dict())

    @property
    def proof_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def build_mops_monthly_revenue_unit_scale_proof(
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> MopsMonthlyRevenueUnitScaleProof:
    """只為固定的2026-06官方原件建立HTML欄位的千元尺度證據。"""

    if type(capture) is not MopsMonthlyRevenueHistoricalCapture:
        raise MonthlyRevenueUnitScaleProofError("capture_type_invalid")
    pin = _JUNE_2026_SOURCE_PINS.get(capture.market)
    if pin is None:
        raise MonthlyRevenueUnitScaleProofError("market_not_pinned")
    if (
        capture.period != "2026-06"
        or capture.source_id != pin.source_id
        or capture.requested_url != pin.url
        or capture.response_url != pin.url
        or capture.transport_mode != "redirect_chain_v1"
        or capture.decoder_profile != MOPS_BIG5_CP950_DECODER_PROFILE
        or capture.effective_decoding_encoding != "cp950"
        or capture.parser_version != MOPS_MONTHLY_REVENUE_HISTORY_CP950_PARSER_VERSION
        or capture.transport_capture.official_source_url != pin.url
        or capture.transport_capture.effective_decoding_encoding != "cp950"
        or capture.raw_response_sha256 != pin.raw_sha256
        or len(capture.raw_response_bytes) != pin.raw_bytes
        or hashlib.sha256(capture.raw_response_bytes).hexdigest() != pin.raw_sha256
    ):
        raise MonthlyRevenueUnitScaleProofError("capture_identity_or_raw_sha_mismatch")

    try:
        parsed_rows = parse_mops_monthly_revenue_history_capture(capture)
        source_rows = capture.raw_source_values_by_stock_code
        html = capture.transport_capture.decoded_html
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MonthlyRevenueUnitScaleProofError("capture_revalidation_failed") from exc
    if capture.observed_unit_annotations != ("千元",):
        raise MonthlyRevenueUnitScaleProofError("global_unit_annotations_missing_or_conflicting")

    scopes = _extract_table_scopes(html)
    scoped_codes: list[str] = []
    for scope in scopes:
        if scope.unit_text != "千元":
            raise MonthlyRevenueUnitScaleProofError("table_unit_missing_or_conflicting")
        for stock_code, pairs in scope.source_rows:
            if stock_code in scoped_codes:
                raise MonthlyRevenueUnitScaleProofError("duplicate_stock_code_across_tables")
            scoped_codes.append(stock_code)
            source_values = source_rows.get(stock_code)
            if source_values is None or dict(pairs) != source_values:
                raise MonthlyRevenueUnitScaleProofError("table_source_values_disagree")

    parser_codes = [row["stock_code"] for row in parsed_rows]
    if (
        len(scopes) == 0
        or len(scopes) != pin.table_count
        or len(scoped_codes) != pin.row_count
        or len(parser_codes) != pin.row_count
        or len(set(scoped_codes)) != len(scoped_codes)
        or set(scoped_codes) != set(parser_codes)
        or set(scoped_codes) != set(source_rows)
    ):
        raise MonthlyRevenueUnitScaleProofError("table_scope_coverage_mismatch")

    return MopsMonthlyRevenueUnitScaleProof(
        market=capture.market,
        source_id=capture.source_id,
        period=capture.period,
        official_url=pin.url,
        raw_source_sha256=pin.raw_sha256,
        raw_source_bytes=len(capture.raw_response_bytes),
        parser_version=capture.parser_version,
        decoder_profile=MOPS_BIG5_CP950_DECODER_PROFILE,
        effective_decoding_encoding="cp950",
        tables=scopes,
        row_count=len(scoped_codes),
    )


def write_mops_monthly_revenue_unit_scale_proof_create_only(
    path: Path | str,
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> Path:
    """由已驗證capture重新推導並以create-only方式寫入proof候選。"""

    proof = build_mops_monthly_revenue_unit_scale_proof(capture)
    return _write_scale_proof_create_only(path, proof)


def _write_scale_proof_create_only(
    path: Path | str, proof: MopsMonthlyRevenueUnitScaleProof,
) -> Path:
    """共用有界且不覆寫的原件衍生證據寫入。"""
    raw = proof.canonical_bytes()
    if len(raw) > MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES:
        raise MonthlyRevenueUnitScaleProofError("proof_exceeds_size_limit")
    target = _resolve_proof_target(path)
    _assert_plain_parent_chain(target.parent)
    parent_identity = _parent_chain_identity(target.parent)
    try:
        descriptor = os.open(
            target,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            if stream.write(raw) != len(raw):
                raise MonthlyRevenueUnitScaleProofError("proof_short_write")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_create_only_conflict") from exc
    except OSError as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_write_failed") from exc
    if _parent_chain_identity(target.parent) != parent_identity:
        raise MonthlyRevenueUnitScaleProofError("proof_parent_changed_after_write")
    try:
        _require_nofollow_support()
        written_identity = _path_identity(target)
        written = _read_bounded_regular_file_no_follow(
            target, maximum_bytes=MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES
        )
        after_identity = _path_identity(target)
    except (OSError, MLResearchOutputBoundaryError) as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_readback_failed") from exc
    if written_identity != after_identity or written != raw:
        raise MonthlyRevenueUnitScaleProofError("proof_readback_identity_or_content_mismatch")
    return target


def read_mops_monthly_revenue_unit_scale_proof(
    path: Path | str,
    *,
    expected_sha256: str,
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> dict[str, object]:
    """由真實capture重建proof，並逐byte比對有界的create-only檔案。"""

    if not _SHA256_RE.fullmatch(expected_sha256):
        raise MonthlyRevenueUnitScaleProofError("expected_sha256_invalid")
    expected_proof = build_mops_monthly_revenue_unit_scale_proof(capture)
    expected_raw = expected_proof.canonical_bytes()
    if hashlib.sha256(expected_raw).hexdigest() != expected_sha256:
        raise MonthlyRevenueUnitScaleProofError("proof_sha256_not_bound_to_capture")
    pin = _JUNE_2026_SOURCE_PINS[expected_proof.market]
    target = _resolve_proof_target(path)
    _assert_plain_parent_chain(target.parent)
    parent_identity = _parent_chain_identity(target.parent)
    try:
        before = target.lstat()
    except OSError as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_missing_or_unreadable") from exc
    if (
        _is_reparse_or_link(target, before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES
    ):
        raise MonthlyRevenueUnitScaleProofError("proof_file_invalid_or_exceeds_limit")
    before_identity = _stat_identity(before)
    try:
        _require_nofollow_support()
        raw = _read_bounded_regular_file_no_follow(
            target, maximum_bytes=MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES
        )
        after_identity = _path_identity(target)
    except (OSError, MLResearchOutputBoundaryError) as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_read_failed") from exc
    if (
        before_identity != after_identity
        or _parent_chain_identity(target.parent) != parent_identity
        or len(raw) != before.st_size
    ):
        raise MonthlyRevenueUnitScaleProofError("proof_file_or_parent_changed_during_read")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise MonthlyRevenueUnitScaleProofError("proof_sha256_mismatch")
    if raw != expected_raw:
        raise MonthlyRevenueUnitScaleProofError("proof_bytes_not_derived_from_capture")
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_json_invalid") from exc
    if type(payload) is not dict or _canonical_json_bytes(payload) != raw:
        raise MonthlyRevenueUnitScaleProofError("proof_not_canonical")
    if set(payload) != {
        "schema_version", "market", "source_id", "period", "official_url",
        "raw_source_sha256", "raw_source_bytes", "parser_version", "decoder_profile",
        "effective_decoding_encoding", "unit_text", "scale_to_base_unit", "currency",
        "historical_pit_eligible", "financial_qualification_created",
        "source_to_parser_field_mapping", "table_scopes", "row_count",
    }:
        raise MonthlyRevenueUnitScaleProofError("proof_schema_invalid")
    if (
        payload["schema_version"] != MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA
        or payload["market"] != expected_proof.market
        or payload["source_id"] != pin.source_id
        or payload["period"] != "2026-06"
        or payload["official_url"] != pin.url
        or payload["raw_source_sha256"] != pin.raw_sha256
        or type(payload["raw_source_bytes"]) is not int
        or payload["raw_source_bytes"] != pin.raw_bytes
        or payload["parser_version"] != MOPS_MONTHLY_REVENUE_HISTORY_CP950_PARSER_VERSION
        or payload["decoder_profile"] != MOPS_BIG5_CP950_DECODER_PROFILE
        or payload["effective_decoding_encoding"] != "cp950"
        or payload["unit_text"] != "千元"
        or type(payload["scale_to_base_unit"]) is not int
        or payload["scale_to_base_unit"] != 1000
        or payload["currency"] != "unknown"
        or payload["historical_pit_eligible"] is not False
        or payload["financial_qualification_created"] is not False
        or payload["row_count"] != pin.row_count
    ):
        raise MonthlyRevenueUnitScaleProofError("proof_identity_or_scope_mismatch")
    expected_fields = [
        {
            "source_header": source_header,
            "parser_field": parser_field,
            "unit_scale_applies": scale_applies,
        }
        for source_header, parser_field, scale_applies in _SOURCE_TO_PARSER_FIELDS
    ]
    if payload["source_to_parser_field_mapping"] != expected_fields:
        raise MonthlyRevenueUnitScaleProofError("proof_field_mapping_mismatch")
    _validate_table_scope_payload(
        payload["table_scopes"],
        expected_rows=pin.row_count,
        expected_tables=pin.table_count,
    )
    return payload


def _extract_table_scopes(html: str) -> tuple[_TableScope, ...]:
    if type(html) is not str or not html:
        raise MonthlyRevenueUnitScaleProofError("html_invalid")
    soup = BeautifulSoup(html, "html.parser")
    all_unit_cells = [
        cell
        for cell in soup.find_all(["th", "td"])
        if _is_leaf_cell(cell) and _UNIT_PREFIX_RE.match(_cell_text(cell))
    ]
    scopes: list[_TableScope] = []
    all_seen_codes: set[str] = set()
    unit_cell_ids: set[int] = set()
    for wrapper_row in soup.find_all("tr"):
        direct_cells = wrapper_row.find_all(["th", "td"], recursive=False)
        if not direct_cells:
            continue
        leaf_indexes = [
            index for index, cell in enumerate(direct_cells) if _is_leaf_cell(cell)
        ]
        if not leaf_indexes:
            continue
        texts = [_cell_text(cell) if index in leaf_indexes else "" for index, cell in enumerate(direct_cells)]
        industry_cells = [
            (index, text)
            for index, text in enumerate(texts)
            if _INDUSTRY_PREFIX_RE.match(text)
        ]
        unit_cells = [
            (index, text)
            for index, text in enumerate(texts)
            if _UNIT_PREFIX_RE.match(text)
        ]
        if not industry_cells and not unit_cells:
            continue
        if len(industry_cells) != 1 or len(unit_cells) != 1 or len(direct_cells) != 2:
            raise MonthlyRevenueUnitScaleProofError("table_wrapper_header_invalid")
        industry_index, industry_text = industry_cells[0]
        unit_index, unit_text = unit_cells[0]
        if industry_index == unit_index:
            raise MonthlyRevenueUnitScaleProofError("table_wrapper_header_conflict")
        unit_value = re.sub(r"\s+", "", _UNIT_PREFIX_RE.sub("", unit_text))
        industry_value = re.sub(r"\s+", "", _INDUSTRY_PREFIX_RE.sub("", industry_text))
        if unit_value != "千元" or not industry_value:
            raise MonthlyRevenueUnitScaleProofError("table_unit_missing_or_conflicting")
        unit_cell_ids.add(id(direct_cells[unit_index]))

        data_row = wrapper_row.find_next_sibling("tr")
        if data_row is None:
            raise MonthlyRevenueUnitScaleProofError("table_wrapper_data_row_missing")
        data_cells = data_row.find_all(["th", "td"], recursive=False)
        if len(data_cells) != 1:
            raise MonthlyRevenueUnitScaleProofError("table_wrapper_data_cell_invalid")
        nested_tables = data_cells[0].find_all("table", recursive=False)
        if len(nested_tables) != 1:
            raise MonthlyRevenueUnitScaleProofError("table_inner_table_ambiguous")
        table = nested_tables[0]
        rows = table.find_all("tr", recursive=False)
        header_candidates: list[tuple[int, list[str]]] = []
        for row_index, row in enumerate(rows):
            cells = row.find_all(["th", "td"], recursive=False)
            headers = [_normalize_header(_cell_text(cell)) for cell in cells]
            if _has_required_headers(headers):
                header_candidates.append((row_index, headers))
        if len(header_candidates) != 1:
            raise MonthlyRevenueUnitScaleProofError("table_field_header_missing_or_ambiguous")
        header_index, headers = header_candidates[0]
        if (
            len(headers) != len(set(headers))
            or not _REQUIRED_TABLE_HEADERS.issubset(headers)
        ):
            raise MonthlyRevenueUnitScaleProofError("table_field_mapping_incomplete")
        if header_index == 0:
            raise MonthlyRevenueUnitScaleProofError("table_rowspan_note_header_missing")
        group_cells = rows[header_index - 1].find_all(["th", "td"], recursive=False)
        note_cells = [
            cell
            for cell in group_cells
            if _normalize_header(_cell_text(cell)) == "備註"
        ]
        if (
            len(note_cells) != 1
            or note_cells[0].get("rowspan") != "2"
            or "備註" in headers
        ):
            raise MonthlyRevenueUnitScaleProofError("table_rowspan_note_header_invalid")
        header_positions = {name: index for index, name in enumerate(headers)}
        stock_codes: list[str] = []
        source_rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for row in rows[header_index + 1 :]:
            cells = row.find_all(["th", "td"], recursive=False)
            values = [_cell_text(cell) for cell in cells]
            if len(values) != len(headers) + 1:
                continue
            mapped_values = values[: len(headers)]
            stock_code = mapped_values[header_positions["公司代號"]].strip()
            if not stock_code:
                continue
            if not _STOCK_CODE_RE.fullmatch(stock_code):
                raise MonthlyRevenueUnitScaleProofError("table_stock_code_invalid")
            if stock_code in all_seen_codes:
                raise MonthlyRevenueUnitScaleProofError("duplicate_stock_code_across_tables")
            all_seen_codes.add(stock_code)
            stock_codes.append(stock_code)
            source_rows.append(
                (stock_code, tuple(zip(headers, mapped_values, strict=True)))
            )
        if not stock_codes:
            if industry_value != "存託憑證" or not _is_exact_zero_empty_scope(
                rows[header_index + 1 :], expected_width=len(headers)
            ):
                raise MonthlyRevenueUnitScaleProofError("table_data_rows_missing")
        scopes.append(
            _TableScope(
                table_index=len(scopes),
                industry_label=industry_value,
                unit_text=unit_value,
                headers=tuple(headers),
                stock_codes=tuple(stock_codes),
                source_rows=tuple(source_rows),
            )
        )
    if not scopes or len(unit_cell_ids) != len(all_unit_cells):
        raise MonthlyRevenueUnitScaleProofError("unit_wrapper_scope_incomplete")
    return tuple(scopes)


def _validate_table_scope_payload(
    value: object, *, expected_rows: int, expected_tables: int
) -> None:
    if type(value) is not list or len(value) != expected_tables:
        raise MonthlyRevenueUnitScaleProofError("proof_table_scopes_invalid")
    seen_codes: set[str] = set()
    seen_industries: set[str] = set()
    total_rows = 0
    for index, scope in enumerate(value):
        if type(scope) is not dict or set(scope) != {
            "table_index", "wrapper", "inner_table_headers", "stock_codes"
        }:
            raise MonthlyRevenueUnitScaleProofError("proof_table_scope_schema_invalid")
        wrapper = scope["wrapper"]
        if (
            type(scope["table_index"]) is not int
            or scope["table_index"] != index
            or type(wrapper) is not dict
            or set(wrapper) != {"industry_label", "unit_text"}
            or type(wrapper["industry_label"]) is not str
            or not wrapper["industry_label"]
            or wrapper["unit_text"] != "千元"
        ):
            raise MonthlyRevenueUnitScaleProofError("proof_table_scope_identity_invalid")
        if wrapper["industry_label"] in seen_industries:
            raise MonthlyRevenueUnitScaleProofError("proof_industry_scope_duplicate")
        seen_industries.add(wrapper["industry_label"])
        headers = scope["inner_table_headers"]
        if (
            type(headers) is not list
            or any(type(header) is not str for header in headers)
            or len(headers) != len(set(headers))
            or set(headers) != _REQUIRED_TABLE_HEADERS
        ):
            raise MonthlyRevenueUnitScaleProofError("proof_table_headers_invalid")
        codes = scope["stock_codes"]
        if type(codes) is not list:
            raise MonthlyRevenueUnitScaleProofError("proof_table_stock_codes_invalid")
        if not codes:
            if wrapper["industry_label"] != "存託憑證":
                raise MonthlyRevenueUnitScaleProofError("proof_empty_scope_industry_invalid")
        for stock_code in codes:
            if type(stock_code) is not str or not _STOCK_CODE_RE.fullmatch(stock_code):
                raise MonthlyRevenueUnitScaleProofError("proof_table_stock_code_invalid")
            if stock_code in seen_codes:
                raise MonthlyRevenueUnitScaleProofError("proof_duplicate_stock_code")
            seen_codes.add(stock_code)
        total_rows += len(codes)
    if total_rows != expected_rows:
        raise MonthlyRevenueUnitScaleProofError("proof_table_row_count_mismatch")


def _canonical_json_bytes(value: Mapping[str, object] | object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_leaf_cell(cell: Tag) -> bool:
    return cell.find("table") is None


def _is_exact_zero_empty_scope(rows: list[Tag], *, expected_width: int) -> bool:
    """只接受六月來源中存託憑證產業的明確零合計列。"""

    if len(rows) != 1:
        return False
    cells = rows[0].find_all(["th", "td"], recursive=False)
    if len(cells) != expected_width:
        return False
    first = cells[0]
    if (
        first.name != "th"
        or first.get("colspan") != "2"
        or _normalize_header(_cell_text(first)) != "合計"
    ):
        return False
    # 公司代號與名稱由首格合併；八個欄位值再加一個備註欄。
    values = [_cell_text(cell).strip() for cell in cells[1:]]
    if len(values) != 9:
        return False
    amount_positions = (0, 1, 2, 5, 6)
    blank_positions = (3, 4, 7, 8)
    return all(values[index] == "0" for index in amount_positions) and all(
        values[index] == "" for index in blank_positions
    )


def _resolve_proof_target(path: Path | str) -> Path:
    try:
        target = _absolute_candidate(
            path,
            base=REPO_ROOT,
            label="monthly revenue unit proof path",
            allowed_repository_output=REPO_ROOT / "output",
        )
    except (MLResearchOutputBoundaryError, TypeError, ValueError, OSError) as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_path_invalid") from exc
    if not target.is_absolute() or not target.parent.is_dir():
        raise MonthlyRevenueUnitScaleProofError("proof_parent_missing_or_invalid")
    return target


def _require_nofollow_support() -> None:
    if os.name != "nt" and not hasattr(os, "O_NOFOLLOW"):
        raise MonthlyRevenueUnitScaleProofError("proof_no_follow_open_unavailable")


def _assert_plain_parent_chain(parent: Path) -> None:
    """寫入前逐層確認父目錄皆存在且不是連結或reparse alias。"""

    current = Path(parent.anchor)
    for part in parent.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise MonthlyRevenueUnitScaleProofError("proof_parent_uninspectable") from exc
        if _is_reparse_or_link(current, info) or not stat.S_ISDIR(info.st_mode):
            raise MonthlyRevenueUnitScaleProofError("proof_parent_not_plain_directory")


def _parent_chain_identity(parent: Path) -> tuple[tuple[int, int, int], ...]:
    _assert_plain_parent_chain(parent)
    current = Path(parent.anchor)
    identities = [_path_identity(current)[:3]]
    for part in parent.parts[1:]:
        current = current / part
        identities.append(_path_identity(current)[:3])
    return tuple(identities)


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
    )


def _path_identity(path: Path) -> tuple[int, int, int, int, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_path_identity_unavailable") from exc
    if _is_reparse_or_link(path, info):
        raise MonthlyRevenueUnitScaleProofError("proof_path_reparse_or_link")
    return _stat_identity(info)


def build_mops_monthly_revenue_period_scale_proof(
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> MopsMonthlyRevenueUnitScaleProof:
    """為任意已驗證之 MOPS 歷史 HTML 原件建立逐產業千元尺度證據（不宣稱幣別或 PIT）。"""

    if type(capture) is not MopsMonthlyRevenueHistoricalCapture:
        raise MonthlyRevenueUnitScaleProofError("capture_type_invalid")
    try:
        parsed_rows = parse_mops_monthly_revenue_history_capture(capture)
        source_rows = capture.raw_source_values_by_stock_code
        html = capture.transport_capture.decoded_html
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MonthlyRevenueUnitScaleProofError("capture_revalidation_failed") from exc
    if capture.observed_unit_annotations not in {("千元",), ("仟元",)}:
        raise MonthlyRevenueUnitScaleProofError("global_unit_annotations_missing_or_conflicting")

    scopes = _extract_table_scopes(html)
    scoped_codes: list[str] = []
    for scope in scopes:
        if scope.unit_text not in {"千元", "仟元"}:
            raise MonthlyRevenueUnitScaleProofError("table_unit_missing_or_conflicting")
        for stock_code, pairs in scope.source_rows:
            if stock_code in scoped_codes:
                raise MonthlyRevenueUnitScaleProofError("duplicate_stock_code_across_tables")
            scoped_codes.append(stock_code)
            source_values = source_rows.get(stock_code)
            if source_values is None or dict(pairs) != source_values:
                raise MonthlyRevenueUnitScaleProofError("table_source_values_disagree")

    parser_codes = [row["stock_code"] for row in parsed_rows]
    if (
        len(scopes) == 0
        or len(scoped_codes) != len(parser_codes)
        or len(set(scoped_codes)) != len(scoped_codes)
        or set(scoped_codes) != set(parser_codes)
        or set(scoped_codes) != set(source_rows)
    ):
        raise MonthlyRevenueUnitScaleProofError("table_scope_coverage_mismatch")

    return MopsMonthlyRevenueUnitScaleProof(
        market=capture.market,
        source_id=capture.source_id,
        period=capture.period,
        official_url=capture.requested_url,
        raw_source_sha256=capture.raw_response_sha256,
        raw_source_bytes=len(capture.raw_response_bytes),
        parser_version=capture.parser_version,
        decoder_profile=capture.decoder_profile or MOPS_BIG5_CP950_DECODER_PROFILE,
        effective_decoding_encoding=capture.effective_decoding_encoding or capture.transport_capture.effective_decoding_encoding,
        tables=scopes,
        row_count=len(scoped_codes),
    )


def write_mops_monthly_revenue_period_scale_proof_create_only(
    path: Path | str,
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> Path:
    """從完整原件重建任意月份尺度證據；不授幣別或用途資格。"""
    return _write_scale_proof_create_only(
        path, build_mops_monthly_revenue_period_scale_proof(capture)
    )


def read_mops_monthly_revenue_period_scale_proof(
    path: Path | str,
    *,
    expected_sha256: str,
    capture: MopsMonthlyRevenueHistoricalCapture,
) -> dict[str, object]:
    """外部 SHA、完整 capture 重播及原件 bytes 三者必須一致。"""
    if type(expected_sha256) is not str or not _SHA256_RE.fullmatch(expected_sha256):
        raise MonthlyRevenueUnitScaleProofError("expected_sha256_invalid")
    proof = build_mops_monthly_revenue_period_scale_proof(capture)
    expected_raw = proof.canonical_bytes()
    if len(expected_raw) > MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES:
        raise MonthlyRevenueUnitScaleProofError("proof_exceeds_size_limit")
    if hashlib.sha256(expected_raw).hexdigest() != expected_sha256:
        raise MonthlyRevenueUnitScaleProofError("proof_sha256_not_bound_to_capture")
    target = _resolve_proof_target(path)
    _assert_plain_parent_chain(target.parent)
    parent_identity = _parent_chain_identity(target.parent)
    try:
        before = target.lstat()
        if (
            _is_reparse_or_link(target, before)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES
        ):
            raise MonthlyRevenueUnitScaleProofError("proof_file_invalid_or_exceeds_limit")
        _require_nofollow_support()
        raw = _read_bounded_regular_file_no_follow(
            target, maximum_bytes=MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES
        )
        if (
            _stat_identity(before) != _path_identity(target)
            or parent_identity != _parent_chain_identity(target.parent)
            or len(raw) != before.st_size
        ):
            raise MonthlyRevenueUnitScaleProofError("proof_file_or_parent_changed_during_read")
    except (OSError, MLResearchOutputBoundaryError) as exc:
        raise MonthlyRevenueUnitScaleProofError("proof_read_failed") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise MonthlyRevenueUnitScaleProofError("proof_sha256_mismatch")
    if raw != expected_raw:
        raise MonthlyRevenueUnitScaleProofError("proof_bytes_not_derived_from_capture")
    return proof.to_dict()


def build_openapi_mops_cross_source_parity_proof(
    openapi_batch: object,
    mops_capture: MopsMonthlyRevenueHistoricalCapture,
) -> dict[str, object]:
    """交叉核對同市場、同期別之 OpenAPI JSON 與 MOPS 靜態 HTML 數值與千元尺度。"""
    from decimal import Decimal
    from data_module.opendata_monthly_revenue import (
        OpenApiMonthlyRevenueBatch, prepare_openapi_monthly_revenue_batch,
    )

    if type(openapi_batch) is not OpenApiMonthlyRevenueBatch:
        raise MonthlyRevenueUnitScaleProofError("openapi_batch_type_invalid")
    if type(mops_capture) is not MopsMonthlyRevenueHistoricalCapture:
        raise MonthlyRevenueUnitScaleProofError("mops_capture_type_invalid")
    # 此比較只需要來源單位原值；已帶轉換資格的 batch 必須先回到原始批次。
    if openapi_batch.unit_proof_sha256 is not None:
        raise MonthlyRevenueUnitScaleProofError("parity_requires_source_unit_batch")
    try:
        openapi_batch.capture.verify_transport()
        rebuilt = prepare_openapi_monthly_revenue_batch(
            capture=openapi_batch.capture,
            successful_batch_completed_at=openapi_batch.successful_batch_completed_at,
        )
        if rebuilt.canonical_bytes() != openapi_batch.canonical_bytes():
            raise MonthlyRevenueUnitScaleProofError("openapi_batch_raw_replay_mismatch")
    except (TypeError, ValueError) as exc:
        raise MonthlyRevenueUnitScaleProofError("openapi_batch_raw_revalidation_failed") from exc
    if openapi_batch.capture.market != mops_capture.market:
        raise MonthlyRevenueUnitScaleProofError("cross_source_market_mismatch")
    if openapi_batch.period != mops_capture.period:
        raise MonthlyRevenueUnitScaleProofError("cross_source_period_mismatch")

    scale_proof = build_mops_monthly_revenue_period_scale_proof(mops_capture)
    openapi_by_code = {row.stock_code: row for row in openapi_batch.rows}
    if len(openapi_by_code) != len(openapi_batch.rows):
        raise MonthlyRevenueUnitScaleProofError("openapi_duplicate_stock_code")
    mops_by_code = mops_capture.raw_source_values_by_stock_code
    common_codes = sorted(set(openapi_by_code).intersection(mops_by_code))
    openapi_only = sorted(set(openapi_by_code) - set(mops_by_code))
    mops_only = sorted(set(mops_by_code) - set(openapi_by_code))

    amount_field_pairs = (
        ("營業收入-當月營收", "當月營收"),
        ("營業收入-上月營收", "上月營收"),
        ("營業收入-去年當月營收", "去年當月營收"),
        ("累計營業收入-當月累計營收", "當月累計營收"),
        ("累計營業收入-去年累計營收", "去年累計營收"),
    )
    exact_matches = 0
    mismatches: list[dict[str, object]] = []
    for code in common_codes:
        oa_row = openapi_by_code[code]
        oa_amounts = dict(oa_row.amount_values_source_unit)
        mops_vals = mops_by_code[code]
        row_ok = True
        for oa_field, mops_field in amount_field_pairs:
            oa_val = oa_amounts.get(oa_field)
            mops_raw = (mops_vals.get(mops_field) or "").replace(",", "").strip()
            mops_val = Decimal(mops_raw) if mops_raw and mops_raw not in {"-", "N/A"} else None
            if oa_val != mops_val:
                row_ok = False
                mismatches.append({
                    "stock_code": code,
                    "openapi_field": oa_field,
                    "mops_field": mops_field,
                    "openapi_value": str(oa_val) if oa_val is not None else None,
                    "mops_value": str(mops_val) if mops_val is not None else None,
                })
        if row_ok:
            exact_matches += 1

    body: dict[str, object] = {
        "schema_version": "monthly-revenue-openapi-mops-cross-source-parity.v1",
        "market": mops_capture.market,
        "period": mops_capture.period,
        "openapi_source_id": openapi_batch.capture.source_id,
        "openapi_endpoint_url": openapi_batch.capture.requested_url,
        "openapi_raw_sha256": openapi_batch.capture.raw_response_sha256,
        "openapi_row_count": len(openapi_batch.rows),
        "mops_source_id": mops_capture.source_id,
        "mops_official_url": mops_capture.requested_url,
        "mops_raw_sha256": mops_capture.raw_response_sha256,
        "mops_row_count": scale_proof.row_count,
        "mops_scale_proof_sha256": scale_proof.proof_sha256,
        "common_stock_count": len(common_codes),
        "comparison_scope": "common_stock_codes_and_five_named_amount_fields_only",
        "compared_stock_codes": common_codes,
        "compared_amount_fields": [list(pair) for pair in amount_field_pairs],
        "unmatched_rows_unit_verified": False,
        "openapi_only_stock_codes": openapi_only,
        "mops_only_stock_codes": mops_only,
        "exact_amount_match_stock_count": exact_matches,
        "amount_mismatch_count": len(mismatches),
        "amount_mismatches": mismatches[:20],
        "mops_html_observed_unit_text": "千元",
        "cross_verified_scale_to_base_unit": 1000 if len(mismatches) == 0 and len(common_codes) > 0 else None,
        "currency": "unknown",
        "standalone_openapi_unit_status": "unknown_without_owner_accepted_cross_source_currency_proof",
        "historical_pit_eligible": False,
        "financial_qualification_created": False,
    }
    body["proof_sha256"] = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    return body


__all__ = [
    "MAX_MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_BYTES",
    "MOPS_MONTHLY_REVENUE_UNIT_SCALE_PROOF_SCHEMA",
    "MonthlyRevenueUnitScaleProofError",
    "MopsMonthlyRevenueUnitScaleProof",
    "build_mops_monthly_revenue_period_scale_proof",
    "build_mops_monthly_revenue_unit_scale_proof",
    "build_openapi_mops_cross_source_parity_proof",
    "read_mops_monthly_revenue_unit_scale_proof",
    "read_mops_monthly_revenue_period_scale_proof",
    "write_mops_monthly_revenue_period_scale_proof_create_only",
    "write_mops_monthly_revenue_unit_scale_proof_create_only",
]
