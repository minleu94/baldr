"""官方產業分類定義的 bounded、可重驗 adapter。

這個 adapter 不內建「所有股票都是普通股」或 current ``companies.csv``
映射。呼叫端必須提供實際保存的官方 bytes；官方靜態 PDF 由受控 parser
直接從同一份 bytes 產生 code/name projection，解析失敗即拒絕，不能以手寫
projection 冒充來源檔本身。PDF 的 mapping shape 可以在明確 research-only
模式下驗證；runtime 另外要求官方 applicability evidence，且不把 HTTP
publication／download timestamp 當作分類適用日。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import csv
import hashlib
import html
import io
import json
import re
from typing import Any


PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION = (
    "official-pit-taxonomy-definition-adapter.v4"
)
PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION = (
    "official-pit-taxonomy-composite-definition-adapter.v1"
)
PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND = (
    "official_twse_b1212_composite_rederived"
)
PIT_TAXONOMY_DEFINITION_SCHEMA_VERSION = "pit-industry-definition.v1"
_TWSE_B1212_COMPOSITE_SAFE_FROM = date(2026, 5, 1)
_CODE_RE = re.compile(r"^[0-9]{2}$")
_PDF_CODE_TOKEN_RE = re.compile(r"(?<![0-9])(?P<code>[0-9]{2})(?=\s)")
_EFFECTIVE_DATE_BASIS_VALUES = frozenset(
    {
        "official_manual_implementation_record",
    }
)
_EFFECTIVE_DATE_SCOPE_VALUES = frozenset(
    {
        "official_manual_revision_implementation",
    }
)
_EFFECTIVE_DATE_EVIDENCE_FIELDS = frozenset(
    {"scope", "source_id", "source_version", "effective_from", "evidence_url"}
)


class OfficialTaxonomyDefinitionError(ValueError):
    """官方分類定義 bytes 或 projection 不符合契約。"""


@dataclass(frozen=True)
class OfficialClassificationDefinition:
    """一個 market-scoped、effective-dated 的官方分類定義。"""

    market_scope: str
    classification_version: str
    source_id: str
    source_version: str
    effective_from: date
    mapping: Mapping[str, str]
    parser_version: str = PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION
    source_kind: str = "official_static_classification_definition"
    effective_date_basis: str | None = None
    effective_date_evidence: Mapping[str, object] | None = None
    source_lineage: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": PIT_TAXONOMY_DEFINITION_SCHEMA_VERSION,
            "market_scope": self.market_scope,
            "classification_version": self.classification_version,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "effective_from": self.effective_from.isoformat(),
            "mapping": dict(self.mapping),
            "parser_version": self.parser_version,
            "source_kind": self.source_kind,
        }
        if self.effective_date_basis is not None:
            payload["effective_date_basis"] = self.effective_date_basis
        if self.effective_date_evidence is not None:
            payload["effective_date_evidence"] = dict(self.effective_date_evidence)
        if self.source_lineage is not None:
            payload["source_lineage"] = dict(self.source_lineage)
        return payload


def parse_official_classification_definition(
    raw_payload: bytes,
    *,
    market_scope: str,
    classification_version: str,
    source_id: str,
    source_version: str,
    effective_from: date,
    mapping: Mapping[str, str] | None = None,
    parser_version: str = PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION,
    effective_date_basis: str | None = None,
    effective_date_evidence: Mapping[str, object] | None = None,
    require_effective_date_evidence: bool = True,
) -> OfficialClassificationDefinition:
    """解析保存的官方定義 bytes。

    JSON/CSV/TSV/pipe text 與可抽取的 PDF 可直接解析；``mapping`` 若由
    revalidation 呼叫端提供，只能作為同一份 raw bytes 的一致性 assertion，
    adapter 仍會先重新推導並比對，不能用來替代官方 bytes。這個邊界讓
    definition parser 可替換，同時保留「實際來源 bytes hash」的可驗證性。
    """

    _require_bytes(raw_payload, "classification raw payload")
    market = _required_text(market_scope, "market_scope")
    version = _required_text(classification_version, "classification_version")
    source = _required_text(source_id, "source_id")
    source_ver = _required_text(source_version, "source_version")
    if not isinstance(effective_from, date):
        raise OfficialTaxonomyDefinitionError("effective_from must be a date")
    parser = _required_text(parser_version, "parser_version")

    if not isinstance(require_effective_date_evidence, bool):
        raise OfficialTaxonomyDefinitionError(
            "require_effective_date_evidence must be bool"
        )
    normalized_basis, normalized_evidence = _normalize_effective_date_contract(
        effective_from=effective_from,
        effective_date_basis=effective_date_basis,
        effective_date_evidence=effective_date_evidence,
        required=raw_payload.startswith(b"%PDF") and require_effective_date_evidence,
    )

    parsed_mapping: Mapping[str, str]
    if raw_payload.startswith(b"%PDF"):
        # Extract once so the bounded mapping parser and the applicability
        # guard consume the same saved bytes/text.  The guard is deliberately
        # separate from HTTP availability: a publication/update timestamp is
        # never promoted to a classification effective date.
        extracted_pdf_text = _extract_pdf_text(raw_payload)
        _validate_pdf_effective_date(
            extracted_pdf_text,
            market_scope=market,
            source_id=source,
            source_version=source_ver,
            effective_from=effective_from,
            effective_date_basis=normalized_basis,
            effective_date_evidence=normalized_evidence,
            required=require_effective_date_evidence,
        )
        derived_mapping = _parse_mapping_from_pdf_text(
            extracted_pdf_text,
            market_scope=market,
        )
    else:
        derived_mapping = _parse_mapping_from_bytes(
            raw_payload,
            market_scope=market,
        )
    if mapping is not None:
        supplied_mapping = _normalize_mapping(mapping)
        if dict(supplied_mapping) != dict(derived_mapping):
            raise OfficialTaxonomyDefinitionError(
                "classification mapping does not derive from the supplied raw bytes"
            )
        parsed_mapping = supplied_mapping
    else:
        parsed_mapping = derived_mapping
    if not parsed_mapping:
        raise OfficialTaxonomyDefinitionError(
            "classification definition mapping is empty; no default mapping is allowed"
        )
    return OfficialClassificationDefinition(
        market_scope=market,
        classification_version=version,
        source_id=source,
        source_version=source_ver,
        effective_from=effective_from,
        mapping=dict(parsed_mapping),
        parser_version=parser,
        effective_date_basis=normalized_basis,
        effective_date_evidence=normalized_evidence,
    )


def parse_official_twse_b1212_composite_classification_definition(
    *,
    base_raw_payload: bytes,
    change_raw_payload: bytes,
    revision_history_raw_payload: bytes,
    current_regulation_raw_payload: bytes,
    classification_version: str,
    source_id: str,
    source_version: str,
    effective_from: date,
    effective_date_basis: str | None = None,
    effective_date_evidence: Mapping[str, object] | None = None,
    mapping: Mapping[str, str] | None = None,
    require_effective_date_evidence: bool = True,
) -> OfficialClassificationDefinition:
    """由官方原始元件重算 TWSE B12.12 時點的 33 碼分類。

    目前官方下載清單未提供可直接下載的 B12.12 完整 PDF；因此這條
    adapter 只接受四份保存的官方 bytes，並以 B12.00 附錄三為 base、
    2023-05-30 公告為明確 patch，再用 B12.13 所印版本歷程及現行法規
    頁作 bounded cross-check。normalized table、手寫 mapping 或現行
    ``companies.csv`` 都不會成為定義來源。
    """

    base = _require_bytes(base_raw_payload, "TWSE B12.00 base raw payload")
    change = _require_bytes(change_raw_payload, "TWSE 2023 change raw payload")
    history = _require_bytes(
        revision_history_raw_payload,
        "TWSE revision history raw payload",
    )
    regulation = _require_bytes(
        current_regulation_raw_payload,
        "TWSE current regulation raw payload",
    )
    if not base.startswith(b"%PDF") or not history.startswith(b"%PDF"):
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 composite base and revision history must be PDF bytes"
        )
    change_text = _decode_official_html(change, "TWSE 2023 change raw payload")
    regulation_text = _decode_official_html(
        regulation,
        "TWSE current regulation raw payload",
    )
    market = "twse_listed"
    version = _required_text(classification_version, "classification_version")
    source = _required_text(source_id, "source_id")
    source_ver = _required_text(source_version, "source_version")
    if not source.casefold().startswith("official:twse:"):
        raise OfficialTaxonomyDefinitionError(
            "TWSE composite source_id must use the official:twse: prefix"
        )
    if "b1212" not in _revision_token(source_ver):
        raise OfficialTaxonomyDefinitionError(
            "TWSE composite source_version must identify B12.12"
        )
    if not isinstance(effective_from, date):
        raise OfficialTaxonomyDefinitionError("effective_from must be a date")
    if effective_from != _TWSE_B1212_COMPOSITE_SAFE_FROM:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 composite effective_from must be the safe 2026-05-01 boundary"
        )
    if not isinstance(require_effective_date_evidence, bool):
        raise OfficialTaxonomyDefinitionError(
            "require_effective_date_evidence must be bool"
        )
    normalized_basis, normalized_evidence = _normalize_effective_date_contract(
        effective_from=effective_from,
        effective_date_basis=effective_date_basis,
        effective_date_evidence=effective_date_evidence,
        required=require_effective_date_evidence,
    )
    if require_effective_date_evidence:
        assert normalized_evidence is not None
        evidence_source = normalized_evidence["source_id"]
        evidence_version = normalized_evidence["source_version"]
        if not isinstance(evidence_source, str) or not evidence_source.casefold().startswith(
            "official:twse:"
        ):
            raise OfficialTaxonomyDefinitionError(
                "TWSE composite effective-date evidence source_id is invalid"
            )
        if not isinstance(evidence_version, str) or "b1212" not in _revision_token(
            evidence_version
        ):
            raise OfficialTaxonomyDefinitionError(
                "TWSE composite effective-date evidence must identify B12.12"
            )

    base_text = _extract_pdf_text(base)
    if _current_pdf_format_revision(base_text, "twse") != "B.12.00":
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 composite base must be the official B12.00 PDF"
        )
    base_mapping_raw = _parse_mapping_from_pdf_text(
        base_text,
        market_scope=market,
    )
    base_mapping = {
        code: _canonicalize_official_name(name)
        for code, name in base_mapping_raw.items()
    }
    if len(base_mapping) != 29:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.00 base Appendix 3 must contain exactly 29 codes"
        )
    if base_mapping.get("16") != "觀光事業":
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.00 base does not contain the expected 觀光事業 code 16"
        )

    additions, old_name, new_name = _parse_twse_2023_industry_change(change_text)
    if old_name != "觀光事業" or new_name != "觀光餐旅":
        raise OfficialTaxonomyDefinitionError(
            "TWSE 2023 raw change notice does not prove the code 16 rename"
        )
    if set(additions) != {"35", "36", "37", "38"}:
        raise OfficialTaxonomyDefinitionError(
            "TWSE 2023 raw change notice does not prove all four additions"
        )
    derived_mapping = dict(base_mapping)
    derived_mapping["16"] = new_name
    for code, name in additions.items():
        if code in derived_mapping:
            raise OfficialTaxonomyDefinitionError(
                f"TWSE 2023 addition collides with base code: {code}"
            )
        derived_mapping[code] = name
    derived_mapping = _normalize_mapping(derived_mapping)
    if len(derived_mapping) != 33:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 composite mapping must contain exactly 33 codes"
        )

    history_text = _extract_pdf_text(history)
    if _current_pdf_format_revision(history_text, "twse") != "B.12.13":
        raise OfficialTaxonomyDefinitionError(
            "TWSE revision-history evidence must be the official B12.13 PDF"
        )
    history_lineage = _validate_twse_b1212_revision_history(history_text)
    regulation_lineage = _validate_twse_current_regulation(
        regulation_text,
        derived_mapping,
    )
    if mapping is not None:
        supplied_mapping = _normalize_mapping(mapping)
        if dict(supplied_mapping) != dict(derived_mapping):
            raise OfficialTaxonomyDefinitionError(
                "classification mapping does not derive from the TWSE composite raw bytes"
            )
        final_mapping = supplied_mapping
    else:
        final_mapping = derived_mapping

    lineage: dict[str, object] = {
        "adapter_version": PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION,
        "composition": "B12.00_appendix3_plus_2023_industry_change_notice",
        "base_revision": "B.12.00",
        "patch_effective_from": "2023-07-03",
        "target_revision": "B.12.12",
        "components": {
            "base_definition": _raw_component_lineage(
                base,
                source_version="B.12.00",
            ),
            "change_notice": _raw_component_lineage(
                change,
                source_version="2023-05-30",
            ),
            "revision_history": _raw_component_lineage(
                history,
                source_version="B.12.13-history-only",
            ),
            "current_regulation": _raw_component_lineage(
                regulation,
                source_version="2026-09-14-current-page-cross-check",
            ),
        },
        "revision_history": history_lineage,
        "current_regulation_cross_check": regulation_lineage,
    }
    return OfficialClassificationDefinition(
        market_scope=market,
        classification_version=version,
        source_id=source,
        source_version=source_ver,
        effective_from=effective_from,
        mapping=dict(final_mapping),
        parser_version=PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION,
        source_kind=PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND,
        effective_date_basis=normalized_basis,
        effective_date_evidence=normalized_evidence,
        source_lineage=lineage,
    )


def _parse_mapping_from_bytes(
    raw_payload: bytes,
    *,
    market_scope: str,
) -> dict[str, str]:
    if raw_payload.startswith(b"%PDF"):
        return _parse_mapping_from_pdf(raw_payload, market_scope=market_scope)
    try:
        text = raw_payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = ""
    if not text.strip():
        raise OfficialTaxonomyDefinitionError(
            "classification definition is not UTF-8 text; mapping projection is required"
        )
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            value: Any = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError) as error:
            raise OfficialTaxonomyDefinitionError(
                "classification definition JSON is invalid"
            ) from error
        if isinstance(value, Mapping):
            for key in ("mapping", "industry_mapping", "code_to_name"):
                candidate = value.get(key)
                if isinstance(candidate, Mapping):
                    return _normalize_mapping(candidate)
            rows = value.get("rows")
            if isinstance(rows, list):
                return _mapping_from_rows(rows)
        elif isinstance(value, list):
            return _mapping_from_rows(value)
        raise OfficialTaxonomyDefinitionError(
            "classification definition JSON has no code/name mapping"
        )

    rows = _read_delimited_rows(text)
    if rows:
        return _mapping_from_rows(rows)
    raise OfficialTaxonomyDefinitionError(
        "classification definition text has no code/name mapping"
    )


def _decode_official_html(raw_payload: bytes, field_name: str) -> str:
    """Decode saved official HTML and expose only human-visible text."""

    try:
        text = raw_payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise OfficialTaxonomyDefinitionError(
            f"{field_name} must be UTF-8 HTML bytes"
        ) from error
    if "<" not in text or ">" not in text:
        raise OfficialTaxonomyDefinitionError(f"{field_name} is not HTML")
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(text)


def _parse_twse_2023_industry_change(
    visible_text: str,
) -> tuple[dict[str, str], str, str]:
    compact = " ".join(visible_text.split())
    if "112年7月3日新增四項產業類別" not in compact:
        raise OfficialTaxonomyDefinitionError(
            "TWSE 2023 raw change notice is missing the 112/07/03 industry-addition marker"
        )
    additions: dict[str, str] = {}
    for match in re.finditer(
        r"(?P<name>[\u4e00-\u9fff]{2,16})\s*[（(]\s*產業別代碼\s*[:：]\s*(?P<code>3[5-8])\s*[）)]",
        compact,
    ):
        code = match.group("code")
        name = _canonicalize_official_name(match.group("name"))
        previous = additions.get(code)
        if previous is not None and previous != name:
            raise OfficialTaxonomyDefinitionError(
                f"TWSE 2023 raw change notice has conflicting addition for code {code}"
            )
        additions[code] = name
    rename = re.search(
        r"「(?P<old>[^」]+)」\s*名稱調整為\s*「(?P<new>[^」]+)」\s*"
        r"[（(]\s*產業別代碼\s*[:：]\s*16\s*[）)]",
        compact,
    )
    if rename is None:
        raise OfficialTaxonomyDefinitionError(
            "TWSE 2023 raw change notice is missing the code 16 rename"
        )
    return (
        dict(sorted(additions.items())),
        _canonicalize_official_name(rename.group("old")),
        _canonicalize_official_name(rename.group("new")),
    )


def _validate_twse_b1212_revision_history(text: str) -> dict[str, object]:
    normalized = " ".join(text.split())
    compact = re.sub(r"[^a-z0-9]", "", normalized.casefold())
    revision_tokens = [f"b12{index:02d}" for index in range(14)]
    history_start = compact.find(revision_tokens[0])
    positions = [
        compact.find(token, history_start)
        for token in revision_tokens
    ]
    if (
        history_start < 0
        or any(position < 0 for position in positions)
        or positions != sorted(positions)
    ):
        raise OfficialTaxonomyDefinitionError(
            "TWSE revision-history evidence does not contain the ordered B12.00-B12.13 record"
        )
    b1207 = _bounded_revision_history_segment(normalized, "07", "08")
    b1212 = _bounded_revision_history_segment(normalized, "12", "13")
    b1207_compact = "".join(b1207.split())
    b1212_compact = "".join(b1212.split())
    for index in range(13):
        revision = f"{index:02d}"
        if revision == "07":
            continue
        segment = _bounded_revision_history_segment(
            normalized,
            revision,
            f"{index + 1:02d}",
        )
        segment_compact = "".join(segment.split())
        if any(marker in segment_compact for marker in _TWSE_INDUSTRY_HISTORY_MARKERS):
            raise OfficialTaxonomyDefinitionError(
                "TWSE revision-history evidence has an unsupported industry mapping change in "
                f"B12.{revision}"
            )
    required_b1207 = (
        "修改附錄三",
        "觀光事業",
        "觀光餐旅",
        "綠能環保",
        "數位雲端",
        "運動休閒",
        "居家生活",
    )
    missing_b1207 = [item for item in required_b1207 if item not in b1207_compact]
    if missing_b1207:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.07 history does not prove Appendix 3 change: "
            + ",".join(missing_b1207)
        )
    if "格式六" not in b1212_compact or "格式十七" not in b1212_compact:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 history does not prove the serial-number format change"
        )
    if "序號2.5" not in b1212_compact:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 history does not contain serial field 2.5"
        )
    if "附錄三" in b1212_compact or "產業別" in b1212_compact:
        raise OfficialTaxonomyDefinitionError(
            "TWSE B12.12 history unexpectedly contains an Appendix 3 industry change"
        )
    return {
        "evidence_revision": "B.12.13",
        "b1207_appendix3_change_proven": True,
        "b1212_appendix3_change_proven": False,
        "b1212_change_scope": "formats_6_17_20_23_24_serial_2_5",
    }


def _bounded_revision_history_segment(
    normalized_text: str,
    revision_number: str,
    next_revision_number: str,
) -> str:
    start = re.search(
        rf"B\s*\.?\s*12\s*\.\s*{re.escape(revision_number)}\b",
        normalized_text,
        flags=re.IGNORECASE,
    )
    stop = re.search(
        rf"B\s*\.?\s*12\s*\.\s*{re.escape(next_revision_number)}\b",
        normalized_text[start.end() :] if start else "",
        flags=re.IGNORECASE,
    )
    if start is None or stop is None:
        raise OfficialTaxonomyDefinitionError(
            f"TWSE revision-history segment B12.{revision_number} is missing"
        )
    segment_end = start.end() + stop.start()
    return normalized_text[start.start() : segment_end]


_TWSE_INDUSTRY_HISTORY_MARKERS = (
    "附錄三",
    "產業別",
    "產業別代碼",
    "產業類別",
)


def _validate_twse_current_regulation(
    visible_text: str,
    mapping: Mapping[str, str],
) -> dict[str, object]:
    compact = "".join(visible_text.split())
    if "三十三種產業類別" not in compact:
        raise OfficialTaxonomyDefinitionError(
            "TWSE current regulation cross-check does not state 33 industry categories"
        )
    missing = sorted(
        name for name in mapping.values() if _canonicalize_official_name(name) not in compact
    )
    if missing:
        raise OfficialTaxonomyDefinitionError(
            "TWSE current regulation cross-check is missing derived names: "
            + ",".join(missing)
        )
    return {
        "source_role": "current_regulation_cross_check_only",
        "declared_category_count": 33,
        "derived_name_count": len(mapping),
        "all_derived_names_present": True,
    }


def _canonicalize_official_name(value: str) -> str:
    return "".join(str(value).split())


def _raw_component_lineage(raw_payload: bytes, *, source_version: str) -> dict[str, object]:
    return {
        "source_version": source_version,
        "sha256": "sha256:" + hashlib.sha256(raw_payload).hexdigest(),
        "content_bytes": len(raw_payload),
    }


def _parse_mapping_from_pdf(
    raw_payload: bytes,
    *,
    market_scope: str = "tpex_otc",
) -> dict[str, str]:
    """從 market-scoped 官方規格書的產業代碼表範圍抽取 code/name。

    TWSE 與 TPEx 的附錄三表頭及排版不同，因此 PDF 必須依市場派送至
    對應的 bounded parser。兩者都只允許在明確附錄三表頭至附錄四的
    範圍內解析；找不到該市場的明確 table marker 時直接拒絕，不能退回
    全文件掃描兩位數字。
    """

    text = _extract_pdf_text(raw_payload)
    return _parse_mapping_from_pdf_text(text, market_scope=market_scope)


def _extract_pdf_text(raw_payload: bytes) -> str:
    """Extract text from saved PDF bytes with a bounded fail-closed boundary."""

    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as error:
        raise OfficialTaxonomyDefinitionError(
            "PDF classification requires the bundled pypdf parser"
        ) from error
    try:
        reader = PdfReader(io.BytesIO(raw_payload))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:  # noqa: BLE001 - parser boundary is fail closed
        raise OfficialTaxonomyDefinitionError(
            "official classification PDF text extraction failed"
        ) from error


def _normalize_effective_date_contract(
    *,
    effective_from: date,
    effective_date_basis: object,
    effective_date_evidence: object,
    required: bool,
) -> tuple[str | None, dict[str, object] | None]:
    """Normalize explicit applicability evidence; never infer it from HTTP."""

    if effective_date_basis is None and effective_date_evidence is None:
        if required:
            raise OfficialTaxonomyDefinitionError(
                "PDF classification requires explicit effective-date evidence"
            )
        return None, None
    if effective_date_basis is None or effective_date_evidence is None:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_basis and effective_date_evidence must be supplied together"
        )
    if not isinstance(effective_date_basis, str) or not effective_date_basis.strip():
        raise OfficialTaxonomyDefinitionError(
            "effective_date_basis must be non-empty text"
        )
    basis = effective_date_basis.strip()
    if basis not in _EFFECTIVE_DATE_BASIS_VALUES:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_basis must identify an official manual implementation record"
        )
    if not isinstance(effective_date_evidence, Mapping):
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence must be an object"
        )
    if any(not isinstance(key, str) for key in effective_date_evidence):
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence keys must be text"
        )
    evidence = {str(key): value for key, value in effective_date_evidence.items()}
    missing = sorted(_EFFECTIVE_DATE_EVIDENCE_FIELDS - set(evidence))
    if missing:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence is missing: " + ",".join(missing)
        )
    scope = evidence.get("scope")
    if not isinstance(scope, str) or scope.strip() not in _EFFECTIVE_DATE_SCOPE_VALUES:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence.scope is unsupported"
        )
    evidence["scope"] = scope.strip()
    expected_scope = {
        "official_manual_implementation_record":
        "official_manual_revision_implementation",
    }[basis]
    if evidence["scope"] != expected_scope:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence.scope does not match effective_date_basis"
        )
    for field_name in ("source_id", "source_version"):
        value = evidence.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise OfficialTaxonomyDefinitionError(
                f"effective_date_evidence.{field_name} must be non-empty text"
            )
        evidence[field_name] = value.strip()
    evidence_date_value = evidence.get("effective_from")
    if not isinstance(evidence_date_value, str):
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence.effective_from must be YYYY-MM-DD"
        )
    try:
        evidence_date = date.fromisoformat(evidence_date_value)
    except ValueError as error:
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence.effective_from is invalid"
        ) from error
    if evidence_date != effective_from:
        raise OfficialTaxonomyDefinitionError(
            "effective-date evidence does not match effective_from"
        )
    evidence["effective_from"] = evidence_date.isoformat()
    evidence_url = evidence.get("evidence_url")
    if not isinstance(evidence_url, str) or not evidence_url.strip().lower().startswith(
        "https://"
    ):
        raise OfficialTaxonomyDefinitionError(
            "effective_date_evidence.evidence_url must be an HTTPS URL"
        )
    evidence["evidence_url"] = evidence_url.strip()
    return basis, evidence


def _validate_pdf_effective_date(
    text: str,
    *,
    market_scope: str,
    source_id: str,
    source_version: str,
    effective_from: date,
    effective_date_basis: str | None,
    effective_date_evidence: Mapping[str, object] | None,
    required: bool,
) -> None:
    """Reject a known future manual even when a caller backdates the config.

    The exact implementation markers below are intentionally narrow and
    version-specific.  They are not a general Chinese date parser.  An
    unknown PDF still requires the structured evidence contract above, while
    a research-only parse may explicitly set ``required=False``.
    """

    if not required:
        return
    family = _classification_pdf_family(market_scope)
    known = _known_pdf_format_implementation(text, family)
    if known is None:
        # An evidence object is not a substitute for a controlled parser and
        # readback of the official revision.  Unknown PDF versions therefore
        # remain research-only until this adapter learns their exact marker.
        raise OfficialTaxonomyDefinitionError(
            "unknown PDF classification format is runtime-ineligible; use research-only parser"
        )
    revision, implementation_date = known
    source_token = re.sub(r"[^a-z0-9]+", "", source_version.casefold())
    revision_token = re.sub(r"[^a-z0-9]+", "", revision.casefold())
    if revision_token not in source_token:
        raise OfficialTaxonomyDefinitionError(
            f"PDF source_version does not identify parsed official format {revision}"
        )
    if effective_date_basis is None or effective_date_evidence is None:
        raise OfficialTaxonomyDefinitionError(
            "known PDF classification format requires explicit effective-date evidence"
        )
    evidence_version = effective_date_evidence.get("source_version")
    if not isinstance(evidence_version, str) or revision_token not in re.sub(
        r"[^a-z0-9]+", "", evidence_version.casefold()
    ):
        raise OfficialTaxonomyDefinitionError(
            f"effective-date evidence does not identify parsed official format {revision}"
        )
    evidence_source_id = effective_date_evidence.get("source_id")
    if not isinstance(evidence_source_id, str):
        raise OfficialTaxonomyDefinitionError(
            "effective-date evidence source_id is invalid"
        )
    expected_prefix = "official:twse:" if family == "twse" else "official:tpex:"
    if not source_id.casefold().startswith(expected_prefix):
        raise OfficialTaxonomyDefinitionError(
            "PDF source_id does not match PDF market"
        )
    if not evidence_source_id.casefold().startswith(expected_prefix):
        raise OfficialTaxonomyDefinitionError(
            "effective-date evidence source_id does not match PDF market"
        )
    if effective_from < implementation_date:
        raise OfficialTaxonomyDefinitionError(
            "official PDF format applicability is unresolved at supplied effective_from: "
            f"{revision} month-level implementation is only safe from {implementation_date.isoformat()}"
        )

def _known_pdf_format_implementation(
    text: str,
    family: str,
) -> tuple[str, date] | None:
    """Return the current known manual revision and its implementation date.

    Revision history pages contain many older versions.  The current revision
    is therefore selected from the cover/header first; searching the whole
    document for a known historical row would let an unknown new version
    masquerade as an older one.
    """

    compact = " ".join(text.split())
    current_revision = _current_pdf_format_revision(text, family)
    if current_revision is None:
        return None
    if family == "twse":
        candidates: dict[str, tuple[str, str, date]] = {
            "b1213": (
                "B.12.13",
                r"B\s*12\.13\s+115/05\s*修改.*?115/12\s*實施",
                # The official record gives only ROC 115/12.  The month is
                # an interval, not a precise day; only the next month's
                # boundary is safe for a no-early-use runtime decision.
                date(2027, 1, 1),
            ),
            "b1212": (
                "B.12.12",
                r"B\s*12\.12\s+115/04\s*修改\s+115/04\s*實施",
                # The official record gives only ROC 115/04; only the next
                # month's boundary is safe for a no-early-use decision.
                date(2026, 5, 1),
            ),
        }
    else:
        candidates = {
            "v1218": (
                "V.12.18",
                r"V\s*12\.18\s+115/4\s*修改.*?115/05/18\s*實施",
                date(2026, 5, 18),
            ),
        }
    candidate = candidates.get(_revision_token(current_revision))
    if candidate is None:
        return None
    revision, pattern, implementation_date = candidate
    return (revision, implementation_date) if re.search(pattern, compact) else None


def _current_pdf_format_revision(text: str, family: str) -> str | None:
    """Read only the cover/header revision, never a historical table row."""

    # The first page of both official manuals carries the current version;
    # 4,000 characters is enough for that cover/header and excludes the later
    # revision-history pages in the known sources.
    header = " ".join(text[:4000].split())
    match = re.search(
        r"(?:版\s*本|版本)\s*[︰:：]?\s*([BV]\s*\.?\s*12\s*\.\s*[0-9]{1,2})",
        header,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    raw_revision = match.group(1).replace(" ", "")
    normalized = raw_revision.upper().replace("．", ".")
    if family == "twse" and not normalized.startswith("B"):
        return None
    if family == "tpex" and not normalized.startswith("V"):
        return None
    return normalized


def _revision_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _parse_mapping_from_pdf_text(
    text: str,
    *,
    market_scope: str = "tpex_otc",
) -> dict[str, str]:
    """測試與 parser 共用的 market-scoped PDF extracted-text boundary。"""

    parser_family = _classification_pdf_family(market_scope)
    lines = text.splitlines()
    if parser_family == "twse":
        table_lines = _locate_twse_industry_table(lines)
        rows = _extract_twse_pdf_table_rows(table_lines)
        table_error_name = "TWSE"
    else:
        table_lines = _locate_tpex_industry_table(lines)
        rows = _extract_pdf_table_rows(table_lines)
        table_error_name = "TPEx"
    if not rows:
        raise OfficialTaxonomyDefinitionError(
            f"official {table_error_name} classification PDF industry-code table has no rows"
        )
    mapping = _mapping_from_rows(rows)
    if not mapping:
        raise OfficialTaxonomyDefinitionError(
            f"official {table_error_name} classification PDF industry-code table has no valid rows"
        )
    if len(rows) != len(mapping):
        raise OfficialTaxonomyDefinitionError(
            f"official {table_error_name} classification PDF industry-code table repeats a code"
        )
    return mapping


def _classification_pdf_family(market_scope: str) -> str:
    """將來源市場映射至官方 PDF parser family；未知市場拒絕猜測。"""

    normalized = "".join(str(market_scope).replace("-", "_").split()).casefold()
    if normalized.startswith("twse") or normalized in {
        "listed",
        "上市",
        "上市股票",
    }:
        return "twse"
    if normalized.startswith("tpex") or normalized in {
        "otc",
        "上櫃",
        "上櫃股票",
        "櫃買",
    }:
        return "tpex"
    raise OfficialTaxonomyDefinitionError(
        f"official classification PDF parser does not support market_scope: {market_scope}"
    )


def _locate_twse_industry_table(lines: Sequence[str]) -> list[str]:
    """回傳 TWSE 附錄三明確表頭後至附錄四前的 bounded lines。

    TWSE B.12.13 的 extracted text 形狀是四組 ``產業別代碼／產業別``
    欄位，且長名稱可能跨多行。只接受附錄三標題後的多欄表頭，藉此
    排除目錄、版本紀錄與附錄二中不相干的數字。
    """

    for appendix_index, line in enumerate(lines):
        compact = _pdf_compact(line)
        if "附錄三" not in compact or "證券產業別" not in compact:
            continue
        header_index = _find_pdf_line(
            lines,
            start=appendix_index + 1,
            stop=min(len(lines), appendix_index + 32),
            predicate=lambda value: (
                _pdf_compact(value).count("產業別代碼") >= 2
                and _pdf_compact(value).count("產業別") >= 4
            ),
        )
        if header_index is None:
            continue
        end_index = _find_pdf_line(
            lines,
            start=header_index + 1,
            stop=len(lines),
            predicate=lambda value: _pdf_compact(value).startswith("附錄四"),
        )
        if end_index is None:
            continue
        return list(lines[header_index + 1 : end_index])
    raise OfficialTaxonomyDefinitionError(
        "official classification PDF does not contain a supported TWSE industry-code table"
    )


def _extract_twse_pdf_table_rows(lines: Sequence[str]) -> list[dict[str, str]]:
    """解析 TWSE table，保留跨行名稱但仍只讀 bounded table lines。"""

    normalized_lines = [
        " ".join(raw_line.split())
        for raw_line in lines
        if raw_line.strip() and not _is_pdf_page_footer(raw_line)
    ]
    if not normalized_lines:
        return []
    return _extract_pdf_table_rows([" ".join(normalized_lines)])


def _locate_tpex_industry_table(lines: Sequence[str]) -> list[str]:
    """回傳 TPEx 附錄三表頭後至附錄四前的 bounded lines。"""

    for appendix_index, line in enumerate(lines):
        compact = _pdf_compact(line)
        if "附錄三" not in compact or "產業別代碼" not in compact:
            continue
        subheading_index = _find_pdf_line(
            lines,
            start=appendix_index + 1,
            stop=min(len(lines), appendix_index + 24),
            predicate=lambda value: "上櫃證券產業別代碼" in _pdf_compact(value),
        )
        if subheading_index is None:
            continue
        header_index = _find_pdf_line(
            lines,
            start=subheading_index + 1,
            stop=min(len(lines), subheading_index + 24),
            predicate=lambda value: (
                "代碼" in _pdf_compact(value)
                and "產業別" in _pdf_compact(value)
            ),
        )
        if header_index is None:
            continue
        end_index = _find_pdf_line(
            lines,
            start=header_index + 1,
            stop=len(lines),
            predicate=lambda value: _pdf_compact(value).startswith("附錄四"),
        )
        if end_index is None:
            continue
        return list(lines[header_index + 1 : end_index])
    raise OfficialTaxonomyDefinitionError(
        "official classification PDF does not contain a supported TPEx industry-code table"
    )


def _extract_pdf_table_rows(lines: Sequence[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in lines:
        line = " ".join(raw_line.split())
        if not line or _is_pdf_page_footer(line):
            continue
        matches = list(_PDF_CODE_TOKEN_RE.finditer(line))
        if not matches:
            continue
        for index, match in enumerate(matches):
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            code = match.group("code")
            name = line[match.end() : next_start].strip(" .、：:;-|")
            if code == "00" or not name:
                raise OfficialTaxonomyDefinitionError(
                    "official classification PDF industry-code row is malformed"
                )
            rows.append({"code": code, "name": name})
    return rows


def _find_pdf_line(
    lines: Sequence[str],
    *,
    start: int,
    stop: int,
    predicate: Any,
) -> int | None:
    for index in range(start, stop):
        if predicate(lines[index]):
            return index
    return None


def _pdf_compact(value: str) -> str:
    return "".join(value.replace("：", ":").split()).casefold()


def _is_pdf_page_footer(value: str) -> bool:
    compact = " ".join(value.split())
    return bool(re.search(r"第\s*[0-9]+\s*頁", compact))


def _read_delimited_rows(text: str) -> list[dict[str, object]]:
    nonempty = [line for line in text.splitlines() if line.strip()]
    if not nonempty:
        return []
    sample = "\n".join(nonempty[:8])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        dialect = csv.excel_tab
        has_header = False
    reader = csv.reader(io.StringIO(text), dialect)
    values = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
    if not values:
        return []
    if has_header:
        headers = [_normalize_header(item) for item in values[0]]
        return [
            {headers[index]: cell for index, cell in enumerate(row) if index < len(headers)}
            for row in values[1:]
        ]
    return [{"code": row[0], "name": row[1]} for row in values if len(row) >= 2]


def _mapping_from_rows(rows: Sequence[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise OfficialTaxonomyDefinitionError(
                "classification definition rows must be objects"
            )
        code = _first_value(
            raw,
            "code",
            "industry_code",
            "sector_id",
            "產業代號",
            "產業別代號",
        )
        name = _first_value(
            raw,
            "name",
            "industry_name",
            "category",
            "產業名稱",
            "產業別名稱",
        )
        if code is None or name is None:
            continue
        normalized_code = str(code).strip()
        normalized_name = str(name).strip()
        if not _CODE_RE.fullmatch(normalized_code) or normalized_code == "00":
            continue
        if not normalized_name:
            continue
        previous = result.get(normalized_code)
        if previous is not None and previous != normalized_name:
            raise OfficialTaxonomyDefinitionError(
                f"classification code has conflicting names: {normalized_code}"
            )
        result[normalized_code] = normalized_name
    return _normalize_mapping(result)


def _normalize_mapping(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise OfficialTaxonomyDefinitionError("classification mapping must be non-empty")
    result: dict[str, str] = {}
    for raw_code, raw_name in value.items():
        if not isinstance(raw_code, str) or not _CODE_RE.fullmatch(raw_code.strip()):
            raise OfficialTaxonomyDefinitionError("classification mapping code is invalid")
        code = raw_code.strip()
        if code == "00":
            raise OfficialTaxonomyDefinitionError("classification mapping cannot contain code 00")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise OfficialTaxonomyDefinitionError("classification mapping name is invalid")
        result[code] = raw_name.strip()
    return {key: result[key] for key in sorted(result)}


def _first_value(value: Mapping[object, object], *keys: str) -> object | None:
    normalized = {_normalize_header(str(key)): item for key, item in value.items()}
    for key in keys:
        candidate = normalized.get(_normalize_header(key))
        if candidate not in (None, ""):
            return candidate
    return None


def _normalize_header(value: str) -> str:
    return "".join(value.replace("\ufeff", "").split()).casefold()


def _require_bytes(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise OfficialTaxonomyDefinitionError(f"{field_name} must be non-empty bytes")
    if len(value) > 16 * 1024 * 1024:
        raise OfficialTaxonomyDefinitionError(f"{field_name} exceeds 16 MiB bound")
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfficialTaxonomyDefinitionError(f"{field_name} must be non-empty text")
    return value.strip()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "OfficialClassificationDefinition",
    "OfficialTaxonomyDefinitionError",
    "PIT_TAXONOMY_COMPOSITE_DEFINITION_ADAPTER_VERSION",
    "PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION",
    "PIT_TAXONOMY_DEFINITION_SCHEMA_VERSION",
    "PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND",
    "parse_official_classification_definition",
    "parse_official_twse_b1212_composite_classification_definition",
]
