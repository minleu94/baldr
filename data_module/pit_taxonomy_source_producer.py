"""每日 PIT taxonomy 的官方來源產製與 raw custody。

這個 producer 是 preopen side 的獨立 component producer。它把父層提供的
score-bearing full universe、clock 與 L/O company raw，和 market-scoped
分類定義、官方 ISIN security evidence 組成 immutable bundle；postcutoff
publisher 只讀這個 bundle，不會重新抓取同一自然日的 HTTP source。

本模組不修改正式資料、SQLite 或 ``companies.csv``。所有輸出都是新日期／
新 bundle 目錄中的 create-only bytes；retry 只允許重讀相同 bytes。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, TypedDict, cast
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from data_module.pit_taxonomy_definition_adapter import (
    PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION,
    PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND,
    OfficialClassificationDefinition,
    OfficialTaxonomyDefinitionError,
    parse_official_classification_definition,
    parse_official_twse_b1212_composite_classification_definition,
)
from data_module.pit_taxonomy_security_adapter import (
    OfficialSecurityRecord,
    OfficialSecurityTypingError,
    build_security_evidence_map,
    parse_official_isin_security_source,
)
from data_module.prospective_formal_clock import canonical_json
from data_module.prospective_official_pit_source import (
    OFFICIAL_COMPANY_SOURCE_DEFINITIONS,
    build_official_first_seen_capture,
)


PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION = "pit-industry-taxonomy-daily-bundle.v1"
PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v3"
PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION = "pit-industry-taxonomy-source.v2"
PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION = "pit-industry-taxonomy-raw-manifest.v1"
PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION = "official-pit-taxonomy-daily-producer.v1"
PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION = "pit-industry-taxonomy-source-config.v1"
PIT_TAXONOMY_SOURCE_CONFIG_ENV = "PIT_TAXONOMY_SOURCE_CONFIG"
PIT_TAXONOMY_CUTOFF = time(8, 30)
PIT_TAXONOMY_FETCH_TIMEOUT_SECONDS = 30
PIT_TAXONOMY_MAX_SOURCE_BYTES = 64 * 1024 * 1024
TAIPEI = ZoneInfo("Asia/Taipei")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_COMMON_TYPES = frozenset(
    {"common_equity", "common_stock", "ordinary_share", "ordinary_stock", "普通股"}
)


class PITTaxonomySourceError(ValueError):
    """每日 taxonomy bundle 不符合 source/custody/clock 契約。"""


class _NormalizedDefinitions(TypedDict):
    definitions: dict[str, OfficialClassificationDefinition]
    sources: dict[str, dict[str, object]]
    mapping_by_market: dict[str, dict[str, str]]
    completion: dict[str, datetime]


@dataclass(frozen=True)
class PITTaxonomyBundleResult:
    bundle_root: Path
    bundle_manifest_path: Path
    taxonomy_identity_path: Path
    taxonomy_source_path: Path
    raw_manifest_path: Path
    row_count: int
    full_symbol_count: int
    eligible_symbol_count: int
    excluded_symbol_count: int
    unknown_symbol_count: int
    security_type_counts: Mapping[str, int] = field(default_factory=dict)
    market_scope_counts: Mapping[str, int] = field(default_factory=dict)
    status: str = "preopen_captured"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION,
            "status": self.status,
            "bundle_root": str(self.bundle_root),
            "bundle_manifest_path": str(self.bundle_manifest_path),
            "taxonomy_identity_path": str(self.taxonomy_identity_path),
            "taxonomy_source_path": str(self.taxonomy_source_path),
            "raw_manifest_path": str(self.raw_manifest_path),
            "row_count": self.row_count,
            "full_symbol_count": self.full_symbol_count,
            "eligible_symbol_count": self.eligible_symbol_count,
            "excluded_symbol_count": self.excluded_symbol_count,
            "unknown_symbol_count": self.unknown_symbol_count,
            "security_type_counts": dict(self.security_type_counts),
            "market_scope_counts": dict(self.market_scope_counts),
        }


@dataclass(frozen=True)
class PITTaxonomySourceResponse:
    """一份 taxonomy response 的原始 bytes 與實際完成 metadata。"""

    body: bytes
    metadata: Mapping[str, object]


def load_pit_taxonomy_source_config(path: Path | None = None) -> dict[str, object]:
    """讀取 preopen 的 static definition／security source 設定。

    設定只描述官方 source URL、版本與「分類適用日」；``http.captured_at``
    只代表來源可取得時間，不能冒充分類適用日。PDF 分類來源還必須帶
    ``effective_date_basis``／``effective_date_evidence``，明確指出官方
    實施／附錄紀錄；分類 mapping 不得放在設定內，mapping 必須由同一次
    保存的 raw bytes 經 adapter 重新解析。每個 source 也可指定已保存的
    ``path``，但必須同時帶完整 HTTP completion metadata，不能以檔案 mtime
    冒充 ``available_at``。
    """

    configured = path
    if configured is None:
        raw_path = os.environ.get(PIT_TAXONOMY_SOURCE_CONFIG_ENV)
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PITTaxonomySourceError(
                f"{PIT_TAXONOMY_SOURCE_CONFIG_ENV} is not configured"
            )
        configured = Path(raw_path.strip())
    resolved = configured.expanduser().resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError("PIT taxonomy source config is unreadable") from error
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy source config must be an object")
    payload = {str(key): item for key, item in value.items()}
    if payload.get("schema_version") != PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION:
        raise PITTaxonomySourceError("PIT taxonomy source config schema is unsupported")
    for field in ("classification", "security"):
        if not isinstance(payload.get(field), Mapping):
            raise PITTaxonomySourceError(
                f"PIT taxonomy source config {field} section is missing"
            )
    license_scope = payload.get("license_scope")
    if license_scope is not None and not isinstance(license_scope, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy source config license_scope is invalid")
    return payload


def capture_configured_daily_pit_taxonomy_bundle(
    *,
    config: Mapping[str, object],
    bundle_root: Path,
    capture_date: date,
    decision_at: datetime,
    now: datetime,
    expected_symbols: Sequence[str],
    universe_hash: str,
    universe_hash_symbols: Sequence[str],
    scores_bp: Sequence[int],
    rank_order: Sequence[str],
    clock_id: str,
    clock_manifest_hash: str,
    clock_payload: Mapping[str, object],
    universe_identity_payload: Mapping[str, object],
    company_raw_payloads: Mapping[str, bytes],
    company_http: Mapping[str, Mapping[str, object]],
    universe_symbols_payload: object | None = None,
    fetch_source: Callable[[str], object] | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> PITTaxonomyBundleResult:
    """由明確 source config 在 cutoff 前抓取並建立 taxonomy bundle。

    這是 preopen wrapper 使用的唯一便利入口。它不接受設定檔中的手寫
    ``mapping``；分類名稱由保存的官方 bytes 產生。``fetch_source`` 僅是
    隔離測試 seam，正式執行會使用 bounded HTTPS GET。``now`` 代表
    request start；有 URL source 時，所有 fetch 完成後才以 ``now_provider``
    （正式執行預設 real UTC clock）取得 bundle completion，不能把 source
    metadata 的 completion 回寫成 start。classification config 的
    ``effective_from`` 是官方分類適用日，不是 HTTP／頁面 publication date；
    PDF 必須另外提供可重驗的 applicability evidence，否則 runtime 拒絕。
    """

    request_started_at = _aware(now, "request_started_at")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if request_started_at.astimezone(TAIPEI).date() != capture_date:
        raise PITTaxonomySourceError(
            "taxonomy request start date does not match capture_date"
        )
    if request_started_at >= cutoff:
        raise PITTaxonomySourceError("taxonomy request must start before Taipei 08:30")
    if now_provider is not None and not callable(now_provider):
        raise PITTaxonomySourceError("now_provider must be callable")
    live_fetch_performed = False
    if not isinstance(config, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy source config must be an object")
    classification_config = config.get("classification")
    security_config = config.get("security")
    if not isinstance(classification_config, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy classification config is missing")
    if not isinstance(security_config, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy security config is missing")
    definitions: dict[str, OfficialClassificationDefinition] = {}
    classification_payloads: dict[str, bytes] = {}
    classification_http: dict[str, Mapping[str, object]] = {}
    classification_component_payloads: dict[str, dict[str, bytes]] = {}
    classification_component_http: dict[
        str, dict[str, Mapping[str, object]]
    ] = {}
    company_market_scopes = {
        OFFICIAL_COMPANY_SOURCE_DEFINITIONS[str(key)].market
        for key in company_raw_payloads
        if str(key) in OFFICIAL_COMPANY_SOURCE_DEFINITIONS
    }
    for market in sorted(company_market_scopes):
        spec = classification_config.get(market)
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError(
                f"PIT taxonomy classification config missing: {market}"
            )
        if "mapping" in spec:
            raise PITTaxonomySourceError(
                f"PIT taxonomy classification config cannot contain hand-written mapping: {market}"
            )
        source_kind = str(spec.get("source_kind") or "").strip()
        if source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            (
                raw,
                http,
                fetched,
                component_payloads,
                component_http,
            ) = _capture_configured_composite_source(
                spec,
                source_name=f"classification:{market}",
                fetch_source=fetch_source,
            )
            classification_component_payloads[market] = component_payloads
            classification_component_http[market] = component_http
        else:
            raw, http, fetched = _capture_configured_source(
                spec,
                source_name=f"classification:{market}",
                fetch_source=fetch_source,
            )
        live_fetch_performed = live_fetch_performed or fetched
        if fetched and _component_available(http, f"classification:{market}") < request_started_at:
            raise PITTaxonomySourceError(
                f"classification:{market} completion predates request start"
            )
        if fetched and source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            for component_name, component_metadata in component_http.items():
                if _component_available(component_metadata, f"classification:{market}:{component_name}") < request_started_at:
                    raise PITTaxonomySourceError(
                        f"classification:{market}:{component_name} completion predates request start"
                    )
        classification_payloads[market] = raw
        classification_http[market] = http
        source_id = _required_text(spec.get("source_id"), f"classification.{market}.source_id")
        source_version = _required_text(
            spec.get("source_version"), f"classification.{market}.source_version"
        )
        classification_version = _required_text(
            spec.get("classification_version"),
            f"classification.{market}.classification_version",
        )
        effective_from = _required_date(
            spec.get("effective_from"), f"classification.{market}.effective_from"
        )
        effective_date_basis = _optional_text(
            spec.get("effective_date_basis"),
            f"classification.{market}.effective_date_basis",
        )
        effective_date_evidence = _optional_mapping(
            spec.get("effective_date_evidence"),
            f"classification.{market}.effective_date_evidence",
        )
        try:
            if source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
                definitions[market] = parse_official_twse_b1212_composite_classification_definition(
                    base_raw_payload=raw,
                    change_raw_payload=component_payloads["change_notice"],
                    revision_history_raw_payload=component_payloads["revision_history"],
                    current_regulation_raw_payload=component_payloads["current_regulation"],
                    classification_version=classification_version,
                    source_id=source_id,
                    source_version=source_version,
                    effective_from=effective_from,
                    effective_date_basis=effective_date_basis,
                    effective_date_evidence=effective_date_evidence,
                    require_effective_date_evidence=True,
                )
            else:
                parser_version = str(
                    spec.get("parser_version") or PIT_TAXONOMY_DEFINITION_ADAPTER_VERSION
                )
                definitions[market] = parse_official_classification_definition(
                    raw,
                    market_scope=market,
                    classification_version=classification_version,
                    source_id=source_id,
                    source_version=source_version,
                    effective_from=effective_from,
                    parser_version=parser_version,
                    effective_date_basis=effective_date_basis,
                    effective_date_evidence=effective_date_evidence,
                    require_effective_date_evidence=raw.startswith(b"%PDF"),
                )
        except OfficialTaxonomyDefinitionError as error:
            raise PITTaxonomySourceError(
                f"official classification definition cannot be parsed: {market}"
            ) from error

    security_payloads: dict[str, bytes] = {}
    security_http: dict[str, Mapping[str, object]] = {}
    for key, value in sorted(security_config.items(), key=lambda item: str(item[0])):
        payload_key = _required_text(str(key), "security source key")
        if not isinstance(value, Mapping):
            raise PITTaxonomySourceError(
                f"PIT taxonomy security config is invalid: {payload_key}"
            )
        raw, http, fetched = _capture_configured_source(
            value,
            source_name=f"security:{payload_key}",
            fetch_source=fetch_source,
        )
        live_fetch_performed = live_fetch_performed or fetched
        if fetched and _component_available(http, f"security:{payload_key}") < request_started_at:
            raise PITTaxonomySourceError(
                f"security:{payload_key} completion predates request start"
            )
        security_payloads[payload_key] = raw
        security_http[payload_key] = http
    if not security_payloads:
        raise PITTaxonomySourceError("PIT taxonomy security config is empty")

    license_scope_value = config.get("license_scope")
    license_scope = (
        {str(key): item for key, item in license_scope_value.items()}
        if isinstance(license_scope_value, Mapping)
        else None
    )
    if license_scope and license_scope.get("formal_acceptance_granted") is True:
        for field in ("acceptance_id", "accepted_by", "decision_at"):
            if not isinstance(license_scope.get(field), str) or not str(
                license_scope.get(field)
            ).strip():
                raise PITTaxonomySourceError(
                    "formal taxonomy license acceptance requires named decision evidence"
                )
    completion_now = request_started_at
    if live_fetch_performed or now_provider is not None:
        completion_value = (
            now_provider()
            if now_provider is not None
            else datetime.now(timezone.utc)
        )
        completion_now = _aware(completion_value, "completion_now")
        if completion_now < request_started_at:
            raise PITTaxonomySourceError(
                "taxonomy completion clock moved before request start"
            )
    return build_daily_pit_taxonomy_bundle(
        bundle_root=bundle_root,
        capture_date=capture_date,
        decision_at=decision_at,
        now=completion_now,
        expected_symbols=expected_symbols,
        universe_hash=universe_hash,
        universe_hash_symbols=universe_hash_symbols,
        scores_bp=scores_bp,
        rank_order=rank_order,
        clock_id=clock_id,
        clock_manifest_hash=clock_manifest_hash,
        clock_payload=clock_payload,
        universe_identity_payload=universe_identity_payload,
        company_raw_payloads=company_raw_payloads,
        company_http=company_http,
        classification_payloads=classification_payloads,
        classification_definitions=definitions,
        classification_http=classification_http,
        classification_component_payloads=classification_component_payloads,
        classification_component_http=classification_component_http,
        security_raw_payloads=security_payloads,
        security_http=security_http,
        license_scope=license_scope,
        universe_symbols_payload=universe_symbols_payload,
        capture_started_at=request_started_at,
    )


def fetch_official_pit_taxonomy_source(url: str) -> PITTaxonomySourceResponse:
    """以 bounded HTTPS GET 取得官方 static／security bytes。"""

    endpoint = _required_text(url, "source URL")
    request = Request(
        endpoint,
        headers={
            "Accept": "application/json, text/html, application/pdf, */*",
            "User-Agent": "technical-analysis-pit-taxonomy-producer/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=PIT_TAXONOMY_FETCH_TIMEOUT_SECONDS) as response:
            body = response.read(PIT_TAXONOMY_MAX_SOURCE_BYTES + 1)
            completed_at = datetime.now(timezone.utc)
            final_url = response.geturl()
            status = response.status
            headers = response.headers
    except Exception as error:  # noqa: BLE001 - transport boundary is fail closed
        raise PITTaxonomySourceError(
            f"official PIT taxonomy source fetch failed: {endpoint}"
        ) from error
    if not body:
        raise PITTaxonomySourceError("official PIT taxonomy source body is empty")
    if len(body) > PIT_TAXONOMY_MAX_SOURCE_BYTES:
        raise PITTaxonomySourceError("official PIT taxonomy source exceeds byte bound")
    if isinstance(status, bool) or not isinstance(status, int) or status != 200:
        raise PITTaxonomySourceError("official PIT taxonomy source HTTP status is not 200")
    metadata: dict[str, object] = {
        "requested_url": endpoint,
        "final_url": str(final_url),
        "http_status": status,
        "content_type": str(headers.get("Content-Type") or "application/octet-stream"),
        "http_date": headers.get("Date"),
        "http_last_modified": headers.get("Last-Modified"),
        "captured_at": completed_at.isoformat(),
    }
    return PITTaxonomySourceResponse(body=body, metadata=metadata)


def _capture_configured_source(
    spec: Mapping[str, object],
    *,
    source_name: str,
    fetch_source: Callable[[str], object] | None,
) -> tuple[bytes, Mapping[str, object], bool]:
    url_value = spec.get("url")
    path_value = spec.get("path")
    has_url = isinstance(url_value, str) and bool(url_value.strip())
    has_path = isinstance(path_value, str) and bool(path_value.strip())
    if has_url == has_path:
        raise PITTaxonomySourceError(
            f"{source_name} must configure exactly one of url or path"
        )
    if has_path:
        raw_path = Path(str(path_value)).expanduser().resolve()
        try:
            raw = raw_path.read_bytes()
        except OSError as error:
            raise PITTaxonomySourceError(
                f"{source_name} saved source bytes are unreadable"
            ) from error
        saved_metadata_value = spec.get("http")
        if not isinstance(saved_metadata_value, Mapping):
            raise PITTaxonomySourceError(
                f"{source_name} saved source requires HTTP completion metadata"
            )
        metadata = {str(key): item for key, item in saved_metadata_value.items()}
        fetched = False
    else:
        endpoint = _required_text(url_value, f"{source_name}.url")
        response = (
            fetch_source(endpoint)
            if fetch_source is not None
            else fetch_official_pit_taxonomy_source(endpoint)
        )
        body_value: object
        metadata_value: object
        if isinstance(response, PITTaxonomySourceResponse):
            body_value = response.body
            metadata_value = response.metadata
        elif isinstance(response, tuple) and len(response) == 2:
            body_value, metadata_value = response
        else:
            body_value = getattr(response, "body", None)
            metadata_value = getattr(response, "metadata", None)
        raw = _require_bytes(body_value, f"{source_name}.body")
        if not isinstance(metadata_value, Mapping):
            raise PITTaxonomySourceError(
                f"{source_name} fetcher returned invalid metadata"
            )
        metadata = {str(key): item for key, item in metadata_value.items()}
        if metadata.get("requested_url") != endpoint:
            raise PITTaxonomySourceError(
                f"{source_name} requested URL differs from configured URL"
            )
        fetched = True
    raw = _require_bytes(raw, f"{source_name}.body")
    if len(raw) > PIT_TAXONOMY_MAX_SOURCE_BYTES:
        raise PITTaxonomySourceError(f"{source_name} exceeds bounded source bytes")
    _component_available(metadata, source_name)
    return raw, metadata, fetched


_TWSE_B1212_COMPOSITE_COMPONENTS = (
    "base_definition",
    "change_notice",
    "revision_history",
    "current_regulation",
)


def _capture_configured_composite_source(
    spec: Mapping[str, object],
    *,
    source_name: str,
    fetch_source: Callable[[str], object] | None,
) -> tuple[
    bytes,
    Mapping[str, object],
    bool,
    dict[str, bytes],
    dict[str, Mapping[str, object]],
]:
    """Capture each raw component of a re-derived official definition."""

    components_value = spec.get("components")
    if not isinstance(components_value, Mapping):
        raise PITTaxonomySourceError(f"{source_name}.components is missing")
    components = {str(key): value for key, value in components_value.items()}
    expected = set(_TWSE_B1212_COMPOSITE_COMPONENTS)
    if set(components) != expected:
        missing = sorted(expected - set(components))
        extra = sorted(set(components) - expected)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("unsupported=" + ",".join(extra))
        raise PITTaxonomySourceError(
            f"{source_name}.components must contain the four official raw components"
            + (" (" + ";".join(detail) + ")" if detail else "")
        )
    payloads: dict[str, bytes] = {}
    metadata: dict[str, Mapping[str, object]] = {}
    fetched = False
    for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS:
        component_spec = components[component_name]
        if not isinstance(component_spec, Mapping):
            raise PITTaxonomySourceError(
                f"{source_name}:{component_name} config is invalid"
            )
        raw, component_metadata, component_fetched = _capture_configured_source(
            component_spec,
            source_name=f"{source_name}:{component_name}",
            fetch_source=fetch_source,
        )
        payloads[component_name] = raw
        metadata[component_name] = component_metadata
        fetched = fetched or component_fetched
    # The primary classification source is the actual base HTTP response.
    # The latest component timestamp is only a derived bundle completion and
    # must not be projected as a synthetic HTTP response.
    base_metadata = dict(metadata["base_definition"])
    component_times = {
        name: _component_available(item, f"{source_name}:{name}")
        for name, item in metadata.items()
    }
    aggregate_at = max(component_times.values())
    derived_metadata: dict[str, object] = {
        "metadata_kind": "derived_composite",
        "derived_at": aggregate_at.isoformat(),
        "component_count": len(payloads),
        "derived_from_components": list(_TWSE_B1212_COMPOSITE_COMPONENTS),
        "component_captured_at": {
            name: item.isoformat() for name, item in sorted(component_times.items())
        },
    }
    base_metadata["derived_metadata"] = derived_metadata
    return (
        payloads["base_definition"],
        base_metadata,
        fetched,
        payloads,
        metadata,
    )


def build_daily_pit_taxonomy_bundle(
    *,
    bundle_root: Path,
    capture_date: date,
    decision_at: datetime,
    now: datetime,
    expected_symbols: Sequence[str],
    universe_hash: str,
    universe_hash_symbols: Sequence[str],
    scores_bp: Sequence[int],
    rank_order: Sequence[str],
    clock_id: str,
    clock_manifest_hash: str,
    clock_payload: Mapping[str, object],
    universe_identity_payload: Mapping[str, object],
    company_raw_payloads: Mapping[str, bytes],
    company_http: Mapping[str, Mapping[str, object]],
    classification_payloads: Mapping[str, bytes],
    classification_definitions: Mapping[str, OfficialClassificationDefinition],
    classification_http: Mapping[str, Mapping[str, object]],
    classification_component_payloads: Mapping[str, Mapping[str, bytes]] | None = None,
    classification_component_http: Mapping[
        str, Mapping[str, Mapping[str, object]]
    ]
    | None = None,
    security_raw_payloads: Mapping[str, bytes],
    security_http: Mapping[str, Mapping[str, object]],
    license_scope: Mapping[str, object] | None = None,
    company_license_ids: Mapping[str, str] | None = None,
    company_license_urls: Mapping[str, str] | None = None,
    universe_symbols_payload: object | None = None,
    capture_started_at: datetime | None = None,
) -> PITTaxonomyBundleResult:
    """建立一份當日 preopen 完成的 PIT taxonomy bundle。

    ``company_raw_payloads`` 的 key 使用既有 producer 的 ``twse``／``tpex``
   （必要時可有 ``emerging``）；classification/security 則以
   ``twse_listed``、``tpex_otc`` 等 market scope 命名。security payload 也
    可只提供 ``all``，代表一份涵蓋兩市場的官方 all-securities response。
    ``capture_started_at`` 若提供，會與最終 ``now`` 分別保存於 bundle
    envelope；它不會改動各 source raw 的實際 available/completion time。
    """

    expected = _normalize_symbols(expected_symbols, "expected_symbols")
    hash_symbols = _normalize_symbols(universe_hash_symbols, "universe_hash_symbols")
    if set(expected) != set(hash_symbols):
        raise PITTaxonomySourceError(
            "full universe symbols and universe_hash_symbols must have the same set"
        )
    scores = _normalize_scores(scores_bp, len(hash_symbols))
    supplied_rank = _normalize_symbols(rank_order, "rank_order")
    if set(supplied_rank) != set(expected):
        raise PITTaxonomySourceError("rank_order must cover the full denominator exactly")
    _require_sha256(universe_hash, "universe_hash")
    expected_universe_hash = _sha256_json(
        {
            "schema_version": "manual-rule-only-universe.v1",
            "symbols": list(hash_symbols),
            "scores_bp": scores,
        }
    )
    if universe_hash != expected_universe_hash:
        raise PITTaxonomySourceError(
            "universe_hash does not reconstruct from universe_hash_symbols and scores_bp"
        )
    _require_sha256(clock_manifest_hash, "clock_manifest_hash")
    _required_text(clock_id, "clock_id")
    decision = _aware(decision_at, "decision_at")
    observed = _aware(now, "now")
    started = (
        _aware(capture_started_at, "capture_started_at")
        if capture_started_at is not None
        else observed
    )
    if started > observed:
        raise PITTaxonomySourceError(
            "capture_started_at cannot be after bundle completion"
        )
    local_capture = datetime.combine(capture_date, time.min, tzinfo=TAIPEI)
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if observed.astimezone(TAIPEI).date() != capture_date:
        raise PITTaxonomySourceError("preopen observation date does not match capture_date")
    if observed.astimezone(TAIPEI) >= cutoff:
        raise PITTaxonomySourceError("taxonomy capture must complete before Taipei 08:30")
    if decision.astimezone(TAIPEI).date() != capture_date:
        raise PITTaxonomySourceError("decision_at date does not match capture_date")
    if decision.astimezone(TAIPEI) < cutoff:
        raise PITTaxonomySourceError("decision_at must be the Taipei 08:30 taxonomy boundary")
    _validate_clock_payload(clock_payload, clock_id, clock_manifest_hash, universe_hash, capture_date)
    _validate_universe_identity(
        universe_identity_payload,
        expected=expected,
        hash_symbols=hash_symbols,
        scores=scores,
        universe_hash=universe_hash,
    )

    company_payloads = {
        str(key): _require_bytes(value, f"company_raw_payloads[{key}]")
        for key, value in company_raw_payloads.items()
    }
    company_markets = set(company_payloads)
    if not company_markets:
        raise PITTaxonomySourceError("both official company market payloads are required")
    unknown_company = company_markets - set(OFFICIAL_COMPANY_SOURCE_DEFINITIONS)
    if unknown_company:
        raise PITTaxonomySourceError(
            "unknown official company market: " + ",".join(sorted(unknown_company))
        )
    company_completion = {
        market: _component_available(company_http.get(market), market)
        for market in company_markets
    }
    _validate_component_times(company_completion, observed, cutoff, "company")
    company_available_at = max(company_completion.values())
    publication_at = {
        market: _publication_datetime(payload, market)
        for market, payload in company_payloads.items()
    }
    company_license_default = {
        "twse": "twse-open-data-license-v1",
        "tpex": "tpex-open-data-license-v1",
        "emerging": "tpex-open-data-license-v1",
    }
    company_url_default = {
        market: definition.endpoint
        for market, definition in OFFICIAL_COMPANY_SOURCE_DEFINITIONS.items()
    }
    license_ids = {**company_license_default, **dict(company_license_ids or {})}
    license_urls = {**company_url_default, **dict(company_license_urls or {})}
    try:
        company_capture = build_official_first_seen_capture(
            raw_payloads=company_payloads,
            license_ids=license_ids,
            license_urls=license_urls,
            publication_at=publication_at,
            expected_symbols=expected,
            clock_id=clock_id,
            clock_manifest_hash=clock_manifest_hash,
            universe_hash=universe_hash,
            available_at=company_available_at,
            effective_from=capture_date,
            now=observed,
        )
    except Exception as error:  # noqa: BLE001 - preserve bounded source error
        raise PITTaxonomySourceError(str(error)) from error

    source_by_id = {
        str(entry["source_id"]): dict(entry)
        for entry in company_capture.source_registry
    }
    company_source_by_market: dict[str, dict[str, object]] = {}
    for market, definition in OFFICIAL_COMPANY_SOURCE_DEFINITIONS.items():
        if market not in company_payloads:
            continue
        source = source_by_id.get(definition.source_id)
        if source is None:
            raise PITTaxonomySourceError(f"company source registry is missing: {market}")
        source["raw_path"] = f"raw/{definition.dataset_id}.raw.json"
        source["http"] = _http_projection(company_http[market], market)
        source["source_registry_hash"] = _sha256_json(
            {key: value for key, value in source.items() if key != "source_registry_hash"}
        )
        company_source_by_market[market] = source

    normalized_definitions = _normalize_definitions(
        classification_definitions,
        company_source_by_market=company_source_by_market,
        classification_payloads=classification_payloads,
        classification_http=classification_http,
        classification_component_payloads=classification_component_payloads,
        classification_component_http=classification_component_http,
        observed=observed,
        cutoff=cutoff,
        capture_date=capture_date,
    )
    classification_sources = normalized_definitions["sources"]
    mapping_by_market = normalized_definitions["mapping_by_market"]
    definitions_by_market = normalized_definitions["definitions"]
    classification_completion = normalized_definitions["completion"]

    security_payloads = {
        str(key): _require_bytes(value, f"security_raw_payloads[{key}]")
        for key, value in security_raw_payloads.items()
    }
    if not security_payloads:
        raise PITTaxonomySourceError("at least one official security payload is required")
    security_completion = {
        market: _component_available(security_http.get(market), market)
        for market in security_payloads
    }
    _validate_component_times(security_completion, observed, cutoff, "security")
    security_records: list[OfficialSecurityRecord] = []
    for key, payload in security_payloads.items():
        try:
            security_records.extend(
                parse_official_isin_security_source(
                    payload,
                    default_market_scope=(None if key == "all" else key),
                )
            )
        except OfficialSecurityTypingError as error:
            raise PITTaxonomySourceError(str(error)) from error
    market_by_symbol = _market_by_symbol(company_capture.rows, company_source_by_market)
    try:
        security_types, eligibility, selected_security = build_security_evidence_map(
            security_records,
            expected_symbols=expected,
            market_by_symbol=market_by_symbol,
        )
    except OfficialSecurityTypingError as error:
        raise PITTaxonomySourceError(str(error)) from error
    unknown_symbols = sorted(
        symbol
        for symbol, evidence in eligibility.items()
        if evidence.get("eligible") is not True
        and str(evidence.get("reason", "")).startswith("unknown")
    )
    eligible_symbols = sorted(
        symbol for symbol in expected if eligibility[symbol].get("eligible") is True
    )
    excluded_symbols = sorted(set(expected) - set(eligible_symbols) - set(unknown_symbols))
    if set(eligible_symbols) | set(excluded_symbols) | set(unknown_symbols) != set(expected):
        raise PITTaxonomySourceError("security projection does not cover full denominator")
    if (
        set(eligible_symbols) & set(excluded_symbols)
        or set(eligible_symbols) & set(unknown_symbols)
        or set(excluded_symbols) & set(unknown_symbols)
    ):
        raise PITTaxonomySourceError("security eligible/excluded/unknown sets overlap")
    if unknown_symbols:
        raise PITTaxonomySourceError(
            "unknown security typing cannot be hidden as excluded: "
            + ",".join(unknown_symbols[:16])
        )

    root = bundle_root.expanduser().resolve()
    _ensure_bundle_root(root)
    raw_root = root / "raw"
    metadata_root = root / "metadata"
    clock_root = root / "clock"
    for directory in (raw_root, metadata_root, clock_root):
        directory.mkdir(parents=True, exist_ok=True)

    raw_files: list[dict[str, object]] = []
    for market, payload in sorted(company_payloads.items()):
        company_definition = OFFICIAL_COMPANY_SOURCE_DEFINITIONS[market]
        relative = Path("raw") / f"{company_definition.dataset_id}.raw.json"
        target = root / relative
        _write_create_only_bytes(target, payload)
        raw_files.append(
            _raw_entry(
                role="company_classification_rows",
                market_scope=company_definition.market,
                source_id=company_definition.source_id,
                source_version=source_by_id[company_definition.source_id]["source_version"],
                path=relative,
                raw_payload=payload,
                http=company_http[market],
                available_at=company_completion[market],
                effective_from=capture_date,
                parser_version="prospective-official-pit-source.v1",
                source_kind="official_company_basic_first_seen",
            )
        )
    for market, payload in sorted(classification_payloads.items()):
        classification_definition = definitions_by_market[market]
        if classification_definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            relative = _classification_component_relative_path(
                market,
                "base_definition",
                payload,
            )
        else:
            suffix = ".pdf" if payload.startswith(b"%PDF") else ".raw"
            relative = Path("raw") / f"{market}_industry_definition{suffix}"
        target = root / relative
        _write_create_only_bytes(target, payload)
        raw_files.append(
            _raw_entry(
                role="classification_definition",
                market_scope=market,
                source_id=classification_definition.source_id,
                source_version=classification_definition.source_version,
                path=relative,
                raw_payload=payload,
                http=classification_http[market],
                available_at=classification_completion[market],
                effective_from=classification_definition.effective_from,
                parser_version=classification_definition.parser_version,
                source_kind=classification_definition.source_kind,
                effective_date_basis=classification_definition.effective_date_basis,
                effective_date_evidence=classification_definition.effective_date_evidence,
                source_lineage=classification_definition.source_lineage,
            )
        )
    for market, components in sorted(
        (classification_component_payloads or {}).items()
    ):
        component_definition = definitions_by_market.get(market)
        if component_definition is None:
            raise PITTaxonomySourceError(
                f"classification component market is not defined: {market}"
            )
        component_http_by_name = (classification_component_http or {}).get(market)
        if not isinstance(component_http_by_name, Mapping):
            raise PITTaxonomySourceError(
                f"classification component HTTP metadata is missing: {market}"
            )
        for component_name, payload in sorted(components.items()):
            if component_name == "base_definition":
                # The base PDF is already the primary classification raw file;
                # retaining one custody path avoids duplicate bytes while the
                # source lineage still names it as a composite component.
                continue
            component_metadata = component_http_by_name.get(component_name)
            if not isinstance(component_metadata, Mapping):
                raise PITTaxonomySourceError(
                    f"classification component HTTP metadata is missing: {market}:{component_name}"
                )
            component_available = _component_available(
                component_metadata,
                f"classification:{market}:{component_name}",
            )
            relative = _classification_component_relative_path(
                market,
                component_name,
                payload,
            )
            target = root / relative
            _write_create_only_bytes(target, payload)
            raw_files.append(
                _raw_entry(
                    role="classification_definition_component",
                    market_scope=market,
                    source_id=(
                        f"{component_definition.source_id}:component:{component_name}"
                    ),
                    source_version=_classification_component_source_version(
                        component_definition,
                        component_name,
                    ),
                    path=relative,
                    raw_payload=payload,
                    http=component_metadata,
                    available_at=component_available,
                    effective_from=component_definition.effective_from,
                    parser_version=component_definition.parser_version,
                    source_kind=component_definition.source_kind,
                )
            )
    selected_security_by_payload: dict[str, list[OfficialSecurityRecord]] = defaultdict(list)
    for key, payload in sorted(security_payloads.items()):
        suffix = ".html" if b"<html" in payload.lower() or b"<table" in payload.lower() else ".raw"
        relative = Path("raw") / f"{key}_isin_all_securities{suffix}"
        target = root / relative
        _write_create_only_bytes(target, payload)
        matching = [record for record in selected_security.values() if _security_payload_key(record, key)]
        selected_security_by_payload[key] = matching
        for market in sorted({record.market_scope for record in matching} or {key}):
            source_id = _security_source_id(key, market)
            raw_files.append(
                _raw_entry(
                    role="security_typing",
                    market_scope=market,
                    source_id=source_id,
                    source_version=f"{PIT_TAXONOMY_SECURITY_VERSION}:{capture_date.isoformat()}",
                    path=relative,
                    raw_payload=payload,
                    http=security_http[key],
                    available_at=security_completion[key],
                    effective_from=capture_date,
                    parser_version="official-isin-security-adapter.v1",
                    source_kind="official_isin_security_typing",
                )
            )
    raw_files.sort(key=lambda item: (str(item["role"]), str(item["market_scope"]), str(item["path"])))
    raw_manifest_body: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION,
        "producer_version": PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION,
        "capture_date": capture_date.isoformat(),
        "decision_at": decision.isoformat(),
        "cutoff_at": cutoff.isoformat(),
        "capture_started_at": started.isoformat(),
        "captured_at": observed.isoformat(),
        "universe_hash": universe_hash,
        "clock_id": clock_id,
        "clock_manifest_hash": clock_manifest_hash,
        "files": raw_files,
    }
    raw_manifest = {**raw_manifest_body, "manifest_hash": _sha256_json(raw_manifest_body)}
    raw_manifest_path = metadata_root / "raw_manifest.json"
    _write_create_only_json(raw_manifest_path, raw_manifest)
    raw_manifest_hash = _file_sha256(raw_manifest_path)

    source_available_at = max(
        [*company_completion.values(), *classification_completion.values(), *security_completion.values()]
    )
    source_version = f"daily:{capture_date.isoformat()}"
    security_sources_by_market = _security_sources(
        security_payloads,
        security_http,
        security_completion,
        capture_date,
        selected_security,
    )
    classification_sources_by_market = {
        market: dict(value) for market, value in classification_sources.items()
    }
    source_body: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION,
        "producer_version": PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION,
        "capture_date": capture_date.isoformat(),
        "source_id": "official:pit-industry-taxonomy-daily",
        "source_version": source_version,
        "available_at": source_available_at.isoformat(),
        "effective_from": capture_date.isoformat(),
        "universe_hash": universe_hash,
        "symbols": list(expected),
        "universe_hash_symbols": list(hash_symbols),
        "scores_bp": scores,
        "rank_order": list(supplied_rank),
        "mapping_by_market": mapping_by_market,
        "classification_sources_by_market": classification_sources,
        "security_sources_by_market": security_sources_by_market,
        "market_by_symbol": market_by_symbol,
        "security_type_by_symbol": security_types,
        "security_eligibility_by_symbol": eligibility,
        "eligible_symbols": eligible_symbols,
        "excluded_by_security": excluded_symbols,
        "unknown_symbols": unknown_symbols,
        "license_scope": dict(
            license_scope
            or {
                "status": "declared_official_research_scope",
                "formal_acceptance_granted": False,
                "allowed_use_cases": ["research_shadow", "diagnostics"],
                "redistribution_allowed": False,
            }
        ),
        "raw_manifest_path": "raw_manifest.json",
        "raw_manifest_hash": raw_manifest_hash,
    }
    taxonomy_source_path = metadata_root / "taxonomy_source.json"
    _write_create_only_json(taxonomy_source_path, source_body)
    taxonomy_source_hash = _file_sha256(taxonomy_source_path)
    identity_body: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION,
        "classification_version_by_market": {
            market: definitions_by_market[market].classification_version
            for market in sorted(definitions_by_market)
        },
        "source_id": source_body["source_id"],
        "source_version": source_version,
        "source_hash": taxonomy_source_hash,
        "source_path": "taxonomy_source.json",
        "available_at": source_available_at.isoformat(),
        "effective_from": capture_date.isoformat(),
        "universe_hash": universe_hash,
        "symbols": list(expected),
        "universe_hash_symbols": list(hash_symbols),
        "scores_bp": scores,
        "rank_order": list(supplied_rank),
        "mapping_by_market": mapping_by_market,
        "classification_sources_by_market": classification_sources_by_market,
        "security_sources_by_market": security_sources_by_market,
        "market_by_symbol": market_by_symbol,
        "security_type_by_symbol": security_types,
        "security_eligibility_by_symbol": eligibility,
        "eligible_symbols": eligible_symbols,
        "excluded_by_security": excluded_symbols,
        "unknown_symbols": unknown_symbols,
        "license_scope": source_body["license_scope"],
        "raw_manifest_path": "raw_manifest.json",
        "raw_manifest_hash": raw_manifest_hash,
    }
    identity = {**identity_body, "mapping_hash": _sha256_json(identity_body)}
    taxonomy_identity_path = metadata_root / "taxonomy_identity.json"
    _write_create_only_json(taxonomy_identity_path, identity)

    clock_path = clock_root / "manifest.json"
    _write_create_only_json(clock_path, dict(clock_payload))
    if universe_symbols_payload is None:
        universe_symbols_payload = list(expected)
    _write_create_only_json(metadata_root / "universe_symbols.json", universe_symbols_payload)
    _write_create_only_json(metadata_root / "universe_identity.json", dict(universe_identity_payload))
    _write_create_only_json(metadata_root / "rank_order.json", {"symbols": list(supplied_rank)})

    source_registry = [dict(source_by_id[key]) for key in sorted(source_by_id)]
    membership_rows = []
    classification_by_company_market = {
        market: definitions_by_market[market].classification_version
        for market in definitions_by_market
    }
    market_to_source = {
        source["market"]: source
        for source in source_registry
        if isinstance(source.get("market"), str)
    }
    for row in company_capture.rows:
        source = next(
            (
                item
                for item in source_registry
                if item.get("source_id") == row.get("source_id")
            ),
            None,
        )
        if source is None:
            raise PITTaxonomySourceError(f"membership source is missing: {row.get('symbol')}")
        market = str(source["market"])
        membership_rows.append(
            {
                **dict(row),
                "market_scope": market,
                "classification_version": classification_by_company_market.get(
                    market, ""
                ),
            }
        )
    membership_rows.sort(
        key=lambda row: (
            str(row["symbol"]),
            str(row["effective_from"]),
            str(row["available_at"]),
            str(row["sector_id"]),
        )
    )
    bundle_body: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION,
        "status": "preopen_captured",
        "producer": "data_module.pit_taxonomy_source_producer",
        "producer_version": PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION,
        "capture_date": capture_date.isoformat(),
        "decision_at": decision.isoformat(),
        "cutoff_at": cutoff.isoformat(),
        "capture_started_at": started.isoformat(),
        "captured_at": observed.isoformat(),
        "preopen_completed_before_cutoff": True,
        "post_cutoff_refetch_forbidden": True,
        "clock_id": clock_id,
        "clock_manifest_hash": clock_manifest_hash,
        "universe_hash": universe_hash,
        "symbols": list(expected),
        "universe_hash_symbols": list(hash_symbols),
        "scores_bp": scores,
        "rank_order": list(supplied_rank),
        "raw_manifest_path": "metadata/raw_manifest.json",
        "raw_manifest_hash": raw_manifest_hash,
        "taxonomy_source_path": "metadata/taxonomy_source.json",
        "taxonomy_source_hash": taxonomy_source_hash,
        "taxonomy_identity_path": "metadata/taxonomy_identity.json",
        "taxonomy_identity_hash": _file_sha256(taxonomy_identity_path),
        "source_registry": source_registry,
        "rows": membership_rows,
        "row_count": len(membership_rows),
        "full_symbol_count": len(expected),
        "eligible_symbols": eligible_symbols,
        "excluded_by_security": excluded_symbols,
        "unknown_symbols": unknown_symbols,
        "market_by_symbol": market_by_symbol,
        "security_type_by_symbol": security_types,
        "security_eligibility_by_symbol": eligibility,
        "security_type_counts": _value_counts(security_types.values()),
        "market_scope_counts": _value_counts(market_by_symbol.values()),
        "license_scope": source_body["license_scope"],
        "formal_oos_allowed": False,
        "promotion_eligible": False,
        "broker_order_allowed": False,
        "production_action_allowed": False,
        "historical_backfill_claimed": False,
    }
    bundle_manifest_path = root / "bundle_manifest.json"
    _write_create_only_json(
        bundle_manifest_path,
        {**bundle_body, "bundle_hash": _sha256_json(bundle_body)},
    )
    return PITTaxonomyBundleResult(
        bundle_root=root,
        bundle_manifest_path=bundle_manifest_path,
        taxonomy_identity_path=taxonomy_identity_path,
        taxonomy_source_path=taxonomy_source_path,
        raw_manifest_path=raw_manifest_path,
        row_count=len(membership_rows),
        full_symbol_count=len(expected),
        eligible_symbol_count=len(eligible_symbols),
        excluded_symbol_count=len(excluded_symbols),
        unknown_symbol_count=len(unknown_symbols),
        security_type_counts=_value_counts(security_types.values()),
        market_scope_counts=_value_counts(market_by_symbol.values()),
    )


def validate_daily_pit_taxonomy_bundle(
    bundle_manifest_path: Path,
    *,
    decision_at: datetime,
    now: datetime | None = None,
) -> dict[str, object]:
    """postcutoff 只讀驗證 bundle envelope、hash、raw component 與 cutoff。"""

    path = bundle_manifest_path.expanduser().resolve()
    payload = _read_json_object(path, "taxonomy bundle manifest")
    bundle_hash = _require_sha256(payload.get("bundle_hash"), "bundle_hash")
    body = dict(payload)
    body.pop("bundle_hash", None)
    if _sha256_json(body) != bundle_hash:
        raise PITTaxonomySourceError("taxonomy bundle hash mismatch")
    if payload.get("schema_version") != PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION:
        raise PITTaxonomySourceError("taxonomy bundle schema_version is unsupported")
    if payload.get("status") != "preopen_captured":
        raise PITTaxonomySourceError("taxonomy bundle is not a preopen capture")
    decision = _aware(decision_at, "decision_at")
    capture_date = _required_date(payload.get("capture_date"), "capture_date")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    captured_at_value = payload.get("captured_at")
    if captured_at_value is not None:
        captured_at = _aware(captured_at_value, "bundle.captured_at")
        if captured_at >= cutoff:
            raise PITTaxonomySourceError(
                "taxonomy bundle completion is at/after Taipei 08:30"
            )
        started_value = payload.get("capture_started_at", captured_at_value)
        started_at = _aware(started_value, "bundle.capture_started_at")
        if started_at > captured_at:
            raise PITTaxonomySourceError(
                "taxonomy bundle capture start is after completion"
            )
    if decision.astimezone(TAIPEI) < cutoff:
        raise PITTaxonomySourceError("postcutoff bundle validation is before Taipei 08:30")
    if payload.get("decision_at") != decision.isoformat() and _aware(
        payload.get("decision_at"), "bundle.decision_at"
    ) > decision:
        raise PITTaxonomySourceError("taxonomy bundle decision_at is after consumer decision")
    root = path.parent
    raw_manifest_path = _resolve_relative(root, payload.get("raw_manifest_path"))
    raw_manifest = _read_json_object(raw_manifest_path, "taxonomy raw manifest")
    raw_manifest_hash = _require_sha256(payload.get("raw_manifest_hash"), "raw_manifest_hash")
    if _file_sha256(raw_manifest_path) != raw_manifest_hash:
        raise PITTaxonomySourceError("taxonomy raw manifest file hash mismatch")
    raw_body = dict(raw_manifest)
    declared_raw_hash = _require_sha256(raw_body.pop("manifest_hash", None), "raw manifest_hash")
    if _sha256_json(raw_body) != declared_raw_hash:
        raise PITTaxonomySourceError("taxonomy raw manifest logical hash mismatch")
    files = raw_manifest.get("files")
    if not isinstance(files, list) or not files:
        raise PITTaxonomySourceError("taxonomy raw manifest files are missing")
    for item in files:
        if not isinstance(item, Mapping):
            raise PITTaxonomySourceError("taxonomy raw manifest file entry is invalid")
        relative = item.get("path")
        file_path = _resolve_relative(root, relative)
        expected_hash = _require_sha256(item.get("source_file_hash"), "raw source_file_hash")
        if _file_sha256(file_path) != expected_hash:
            raise PITTaxonomySourceError(f"taxonomy raw file hash mismatch: {relative}")
        available_at = _aware(item.get("available_at"), "raw.available_at")
        if available_at >= cutoff or available_at > decision:
            raise PITTaxonomySourceError(f"taxonomy raw component is after cutoff: {relative}")
        if item.get("content_bytes") != file_path.stat().st_size:
            raise PITTaxonomySourceError(f"taxonomy raw byte count mismatch: {relative}")
    source_path = _resolve_relative(root, payload.get("taxonomy_source_path"))
    identity_path = _resolve_relative(root, payload.get("taxonomy_identity_path"))
    source_hash = _require_sha256(payload.get("taxonomy_source_hash"), "taxonomy_source_hash")
    identity_hash = _require_sha256(payload.get("taxonomy_identity_hash"), "taxonomy_identity_hash")
    if _file_sha256(source_path) != source_hash or _file_sha256(identity_path) != identity_hash:
        raise PITTaxonomySourceError("taxonomy source or identity file hash mismatch")
    rows = payload.get("rows")
    symbols = payload.get("symbols")
    if not isinstance(rows, list) or not isinstance(symbols, list):
        raise PITTaxonomySourceError("taxonomy bundle rows or symbols are invalid")
    if payload.get("row_count") != len(rows) or payload.get("full_symbol_count") != len(symbols):
        raise PITTaxonomySourceError("taxonomy bundle row/full counts are inconsistent")
    row_symbols = sorted(str(row.get("symbol")) for row in rows if isinstance(row, Mapping))
    if row_symbols != sorted(str(item) for item in symbols):
        raise PITTaxonomySourceError("taxonomy bundle rows do not cover full symbols")
    eligible = _string_list(payload.get("eligible_symbols"), "eligible_symbols")
    excluded = _string_list(payload.get("excluded_by_security"), "excluded_by_security")
    unknown = _string_list(payload.get("unknown_symbols"), "unknown_symbols")
    full_set = set(str(item) for item in symbols)
    if set(eligible) | set(excluded) | set(unknown) != full_set:
        raise PITTaxonomySourceError("taxonomy bundle eligibility union is incomplete")
    if (set(eligible) & set(excluded)) or (set(eligible) & set(unknown)) or (set(excluded) & set(unknown)):
        raise PITTaxonomySourceError("taxonomy bundle eligibility sets overlap")
    if unknown:
        raise PITTaxonomySourceError("taxonomy bundle has unknown security symbols")
    security_types = _strict_string_map(
        payload.get("security_type_by_symbol"),
        "security_type_by_symbol",
    )
    market_by_symbol = _strict_string_map(
        payload.get("market_by_symbol"),
        "market_by_symbol",
    )
    if set(security_types) != full_set:
        raise PITTaxonomySourceError("taxonomy bundle security type map is incomplete")
    if set(market_by_symbol) != full_set:
        raise PITTaxonomySourceError("taxonomy bundle market map is incomplete")
    security_type_counts = _strict_count_map(
        payload.get("security_type_counts"),
        "security_type_counts",
    )
    market_scope_counts = _strict_count_map(
        payload.get("market_scope_counts"),
        "market_scope_counts",
    )
    if security_type_counts != _value_counts(security_types.values()):
        raise PITTaxonomySourceError("taxonomy bundle security type counts mismatch")
    if market_scope_counts != _value_counts(market_by_symbol.values()):
        raise PITTaxonomySourceError("taxonomy bundle market scope counts mismatch")
    return {
        "status": "preopen_captured_verified",
        "bundle_manifest_path": str(path),
        "bundle_hash": bundle_hash,
        "capture_date": capture_date.isoformat(),
        "decision_at": decision.isoformat(),
        "raw_manifest_path": str(raw_manifest_path),
        "taxonomy_source_path": str(source_path),
        "taxonomy_identity_path": str(identity_path),
        "row_count": len(rows),
        "full_symbol_count": len(full_set),
        "eligible_symbol_count": len(eligible),
        "excluded_symbol_count": len(excluded),
        "unknown_symbol_count": len(unknown),
        "security_type_counts": security_type_counts,
        "market_scope_counts": market_scope_counts,
        "post_cutoff_refetch_forbidden": True,
    }


def read_daily_pit_taxonomy_bundle(bundle_manifest_path: Path) -> dict[str, object]:
    """讀取 bundle JSON，不做網路請求；publisher 另行呼叫 validator。"""

    return _read_json_object(bundle_manifest_path.expanduser().resolve(), "taxonomy bundle manifest")


def _normalize_definitions(
    value: Mapping[str, OfficialClassificationDefinition],
    *,
    company_source_by_market: Mapping[str, Mapping[str, object]],
    classification_payloads: Mapping[str, bytes],
    classification_http: Mapping[str, Mapping[str, object]],
    classification_component_payloads: Mapping[str, Mapping[str, bytes]] | None = None,
    classification_component_http: Mapping[
        str, Mapping[str, Mapping[str, object]]
    ]
    | None = None,
    observed: datetime,
    cutoff: datetime,
    capture_date: date,
) -> _NormalizedDefinitions:
    if not isinstance(value, Mapping) or not value:
        raise PITTaxonomySourceError("classification definitions are required per market")
    raw_market_scopes = {
        company_source.get("market") for company_source in company_source_by_market.values()
    }
    if any(not isinstance(market, str) for market in raw_market_scopes):
        raise PITTaxonomySourceError("company source market scope is invalid")
    market_scopes = {str(market) for market in raw_market_scopes}
    missing = market_scopes - set(value)
    if missing:
        raise PITTaxonomySourceError(
            "classification definition missing for market: " + ",".join(sorted(missing))
        )
    sources: dict[str, dict[str, object]] = {}
    mappings: dict[str, dict[str, str]] = {}
    completion: dict[str, datetime] = {}
    definitions: dict[str, OfficialClassificationDefinition] = {}
    for market in sorted(market_scopes):
        definition = value.get(market)
        payload = classification_payloads.get(market)
        if not isinstance(definition, OfficialClassificationDefinition) or payload is None:
            raise PITTaxonomySourceError(f"classification source component is incomplete: {market}")
        if definition.market_scope != market:
            raise PITTaxonomySourceError(
                f"classification definition market scope mismatch: {market}"
            )
        try:
            # Re-derive the mapping from the exact bytes that will be placed in
            # custody.  A caller-provided mapping is only a consistency claim;
            # it must not become an unverified hand-written taxonomy source.
            if definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
                component_payloads = (classification_component_payloads or {}).get(market)
                component_http = (classification_component_http or {}).get(market)
                if not isinstance(component_payloads, Mapping) or not isinstance(
                    component_http, Mapping
                ):
                    raise PITTaxonomySourceError(
                        f"classification composite components are incomplete: {market}"
                    )
                if set(component_payloads) != set(_TWSE_B1212_COMPOSITE_COMPONENTS):
                    raise PITTaxonomySourceError(
                        f"classification composite raw components are incomplete: {market}"
                    )
                if set(component_http) != set(_TWSE_B1212_COMPOSITE_COMPONENTS):
                    raise PITTaxonomySourceError(
                        f"classification composite HTTP components are incomplete: {market}"
                    )
                base_component_payload = component_payloads.get("base_definition")
                if not isinstance(base_component_payload, bytes):
                    raise PITTaxonomySourceError(
                        f"classification composite base component is invalid: {market}"
                    )
                if payload != base_component_payload:
                    raise PITTaxonomySourceError(
                        f"classification composite base_definition payload does not match primary: {market}"
                    )
                base_http = component_http.get("base_definition")
                primary_http = classification_http.get(market)
                if not isinstance(base_http, Mapping) or not isinstance(primary_http, Mapping):
                    raise PITTaxonomySourceError(
                        f"classification composite base HTTP metadata is incomplete: {market}"
                    )
                if _http_projection(
                    base_http,
                    f"classification:{market}:base_definition",
                ) != _http_projection(primary_http, f"classification:{market}"):
                    raise PITTaxonomySourceError(
                        f"classification composite base HTTP metadata does not match primary: {market}"
                    )
                component_times = {
                    component_name: _component_available(
                        component_http[component_name],
                        f"classification:{market}:{component_name}",
                    )
                    for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS
                }
                _validate_component_times(
                    component_times,
                    observed,
                    cutoff,
                    "classification composite",
                )
                definition = parse_official_twse_b1212_composite_classification_definition(
                    base_raw_payload=payload,
                    change_raw_payload=component_payloads["change_notice"],
                    revision_history_raw_payload=component_payloads["revision_history"],
                    current_regulation_raw_payload=component_payloads["current_regulation"],
                    classification_version=definition.classification_version,
                    source_id=definition.source_id,
                    source_version=definition.source_version,
                    effective_from=definition.effective_from,
                    mapping=definition.mapping,
                    effective_date_basis=definition.effective_date_basis,
                    effective_date_evidence=definition.effective_date_evidence,
                    require_effective_date_evidence=True,
                )
            else:
                definition = parse_official_classification_definition(
                    payload,
                    market_scope=market,
                    classification_version=definition.classification_version,
                    source_id=definition.source_id,
                    source_version=definition.source_version,
                    effective_from=definition.effective_from,
                    mapping=definition.mapping,
                    parser_version=definition.parser_version,
                    effective_date_basis=definition.effective_date_basis,
                    effective_date_evidence=definition.effective_date_evidence,
                    require_effective_date_evidence=payload.startswith(b"%PDF"),
                )
        except OfficialTaxonomyDefinitionError as error:
            raise PITTaxonomySourceError(
                f"classification mapping cannot be re-derived from raw bytes: {market}"
            ) from error
        available = _component_available(classification_http.get(market), market)
        all_available = [available]
        if definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            component_http = (classification_component_http or {}).get(market)
            if isinstance(component_http, Mapping):
                all_available.extend(
                    _component_available(item, f"classification:{market}:{name}")
                    for name, item in component_http.items()
                )
        available = max(all_available)
        _validate_component_times({market: available}, observed, cutoff, "classification")
        if definition.effective_from > capture_date:
            raise PITTaxonomySourceError(f"classification definition is not effective: {market}")
        raw_hash = _sha256_bytes(payload)
        if definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            path = _classification_component_relative_path(
                market,
                "base_definition",
                payload,
            ).as_posix()
        else:
            path = f"raw/{market}_industry_definition.{ 'pdf' if payload.startswith(b'%PDF') else 'raw' }"
        entry: dict[str, object] = {
            "source_id": definition.source_id,
            "source_version": definition.source_version,
            "classification_version": definition.classification_version,
            "market_scope": market,
            "path": path,
            "source_file_hash": raw_hash,
            "raw_hash": raw_hash,
            "content_bytes": len(payload),
            "http": _http_projection(classification_http[market], market),
            "available_at": available.isoformat(),
            "effective_from": definition.effective_from.isoformat(),
            "parser_version": definition.parser_version,
            "source_kind": definition.source_kind,
            "mapping": dict(definition.mapping),
        }
        if definition.effective_date_basis is not None:
            entry["effective_date_basis"] = definition.effective_date_basis
        if definition.effective_date_evidence is not None:
            entry["effective_date_evidence"] = dict(definition.effective_date_evidence)
        derived_metadata = classification_http[market].get("derived_metadata")
        if isinstance(derived_metadata, Mapping):
            entry["derived_metadata"] = dict(derived_metadata)
        if definition.source_lineage is not None:
            entry["source_lineage"] = dict(definition.source_lineage)
        if definition.source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
            component_payloads = (classification_component_payloads or {}).get(market)
            if not isinstance(component_payloads, Mapping):
                raise PITTaxonomySourceError(
                    f"classification composite raw components are missing: {market}"
                )
            entry["component_raw_paths"] = {
                component_name: _classification_component_relative_path(
                    market,
                    component_name,
                    component_payloads[component_name],
                ).as_posix()
                for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS
            }
        sources[market] = entry
        mappings[market] = dict(definition.mapping)
        completion[market] = available
        definitions[market] = definition
    return {
        "definitions": definitions,
        "sources": sources,
        "mapping_by_market": mappings,
        "completion": completion,
    }


def _classification_component_relative_path(
    market: str,
    component_name: str,
    payload: bytes,
) -> Path:
    suffix = ".pdf" if payload.startswith(b"%PDF") else ".html"
    return Path("raw") / f"{market}_industry_definition_{component_name}{suffix}"


def _classification_component_source_version(
    definition: OfficialClassificationDefinition,
    component_name: str,
) -> str:
    lineage = definition.source_lineage
    if isinstance(lineage, Mapping):
        components = lineage.get("components")
        if isinstance(components, Mapping):
            component = components.get(component_name)
            if isinstance(component, Mapping):
                value = component.get("source_version")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return f"{definition.source_version}:{component_name}"


def _security_sources(
    payloads: Mapping[str, bytes],
    http: Mapping[str, Mapping[str, object]],
    completion: Mapping[str, datetime],
    capture_date: date,
    selected: Mapping[str, OfficialSecurityRecord],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for market in sorted({record.market_scope for record in selected.values()}):
        payload_key = next(
            key for key in payloads if key == "all" or key == market
        )
        payload = payloads[payload_key]
        result[market] = {
            "source_id": _security_source_id(payload_key, market),
            "source_version": f"{PIT_TAXONOMY_SECURITY_VERSION}:{capture_date.isoformat()}",
            "market_scope": market,
            "path": f"raw/{payload_key}_isin_all_securities.{ 'html' if b'<html' in payload.lower() or b'<table' in payload.lower() else 'raw' }",
            "source_file_hash": _sha256_bytes(payload),
            "raw_hash": _sha256_bytes(payload),
            "content_bytes": len(payload),
            "http": _http_projection(http[payload_key], payload_key),
            "available_at": completion[payload_key].isoformat(),
            "effective_from": capture_date.isoformat(),
            "parser_version": "official-isin-security-adapter.v1",
            "source_kind": "official_isin_security_typing",
        }
    return result


def _raw_entry(
    *,
    role: str,
    market_scope: str,
    source_id: str,
    source_version: object,
    path: Path,
    raw_payload: bytes,
    http: Mapping[str, object],
    available_at: datetime,
    effective_from: date,
    parser_version: str,
    source_kind: str,
    effective_date_basis: str | None = None,
    effective_date_evidence: Mapping[str, object] | None = None,
    source_lineage: Mapping[str, object] | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "role": role,
        "market_scope": market_scope,
        "source_id": source_id,
        "source_version": str(source_version),
        "path": path.as_posix(),
        "source_file_hash": _sha256_bytes(raw_payload),
        "content_bytes": len(raw_payload),
        "http": _http_projection(http, str(source_id)),
        "available_at": available_at.isoformat(),
        "effective_from": effective_from.isoformat(),
        "parser_version": parser_version,
        "source_kind": source_kind,
    }
    if effective_date_basis is not None:
        entry["effective_date_basis"] = effective_date_basis
    if effective_date_evidence is not None:
        entry["effective_date_evidence"] = dict(effective_date_evidence)
    if source_lineage is not None:
        entry["source_lineage"] = dict(source_lineage)
    derived_metadata = http.get("derived_metadata")
    if isinstance(derived_metadata, Mapping):
        entry["derived_metadata"] = dict(derived_metadata)
    return entry


def _market_by_symbol(
    rows: Sequence[Mapping[str, object]],
    source_by_market: Mapping[str, Mapping[str, object]],
) -> dict[str, str]:
    source_market = {
        str(source.get("source_id")): str(source.get("market"))
        for source in source_by_market.values()
    }
    result: dict[str, str] = {}
    for row in rows:
        symbol = str(row.get("symbol"))
        market = source_market.get(str(row.get("source_id")))
        if market is None:
            raise PITTaxonomySourceError(f"company row market is missing: {symbol}")
        if symbol in result and result[symbol] != market:
            raise PITTaxonomySourceError(f"company row market conflict: {symbol}")
        result[symbol] = market
    return dict(sorted(result.items()))


def _security_payload_key(record: OfficialSecurityRecord, key: str) -> bool:
    return key == "all" or record.market_scope == key


PIT_TAXONOMY_SECURITY_VERSION = "official-isin-security.v1"


def _security_source_id(payload_key: str, market: str) -> str:
    return f"official:isin:{payload_key}:{market}"


def _validate_clock_payload(
    payload: Mapping[str, object],
    clock_id: str,
    clock_hash: str,
    universe_hash: str,
    capture_date: date,
) -> None:
    if payload.get("clock_id") != clock_id:
        raise PITTaxonomySourceError("clock payload clock_id mismatch")
    if payload.get("manifest_hash") != clock_hash:
        raise PITTaxonomySourceError("clock payload manifest_hash mismatch")
    if payload.get("universe_hash") != universe_hash:
        raise PITTaxonomySourceError("clock payload universe_hash mismatch")
    if payload.get("activation_trading_day") != capture_date.isoformat():
        raise PITTaxonomySourceError("clock payload activation date mismatch")


def _validate_universe_identity(
    payload: Mapping[str, object],
    *,
    expected: Sequence[str],
    hash_symbols: Sequence[str],
    scores: Sequence[int],
    universe_hash: str,
) -> None:
    if payload.get("schema_version") != "manual-rule-only-universe.v1":
        raise PITTaxonomySourceError("parent universe identity schema is invalid")
    if payload.get("universe_hash") != universe_hash:
        raise PITTaxonomySourceError("parent universe identity hash mismatch")
    identity_symbols = payload.get("symbols")
    if identity_symbols != list(expected):
        raise PITTaxonomySourceError("parent universe identity does not cover full symbols")
    if payload.get("universe_hash_symbols") != list(hash_symbols):
        raise PITTaxonomySourceError("parent universe hash symbol order changed")
    if payload.get("scores_bp") != list(scores):
        raise PITTaxonomySourceError("parent universe score vector changed")
    if payload.get("candidate_count") != len(expected):
        raise PITTaxonomySourceError("parent universe candidate_count mismatch")
    if payload.get("source_id") != "daily_prices":
        raise PITTaxonomySourceError("parent universe source_id is unsupported")


def _component_available(value: Mapping[str, object] | None, name: str) -> datetime:
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{name} HTTP metadata is missing")
    completion = value.get("captured_at", value.get("available_at", value.get("completed_at")))
    parsed = _aware(completion, f"{name}.captured_at")
    _required_text(value.get("requested_url"), f"{name}.requested_url")
    _required_text(value.get("final_url"), f"{name}.final_url")
    status = value.get("http_status", value.get("status"))
    if isinstance(status, bool) or not isinstance(status, int) or status != 200:
        raise PITTaxonomySourceError(f"{name}.http_status must be 200")
    _required_text(value.get("content_type"), f"{name}.content_type")
    return parsed


def _http_projection(value: Mapping[str, object], name: str) -> dict[str, object]:
    available = _component_available(value, name)
    status = value.get("http_status", value.get("status", 0))
    if isinstance(status, bool) or not isinstance(status, int):
        raise PITTaxonomySourceError(f"{name}.http_status must be an integer")
    content_type = value.get("content_type")
    if not isinstance(content_type, str):
        raise PITTaxonomySourceError(f"{name}.content_type must be text")
    projection: dict[str, object] = {
        "requested_url": str(value["requested_url"]),
        "final_url": str(value["final_url"]),
        "http_status": status,
        "content_type": content_type,
        "captured_at": available.isoformat(),
    }
    for header_field in ("http_date", "http_last_modified"):
        if header_field in value:
            projection[header_field] = value[header_field]
    return projection


def _validate_component_times(
    values: Mapping[str, datetime],
    observed: datetime,
    cutoff: datetime,
    role: str,
) -> None:
    for name, value in values.items():
        if value > observed:
            raise PITTaxonomySourceError(f"{role} completion is after capture now: {name}")
        if value >= cutoff:
            raise PITTaxonomySourceError(f"{role} completion is at/after Taipei 08:30: {name}")
        if value.astimezone(TAIPEI).date() != cutoff.date():
            raise PITTaxonomySourceError(f"{role} completion date is not capture date: {name}")


def _publication_datetime(payload: bytes, market: str) -> datetime:
    definition = OFFICIAL_COMPANY_SOURCE_DEFINITIONS[market]
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError(f"company source is not JSON: {market}") from error
    if not isinstance(value, list) or not value or not isinstance(value[0], Mapping):
        raise PITTaxonomySourceError(f"company source rows are invalid: {market}")
    raw = value[0].get(definition.publication_field)
    if not isinstance(raw, str):
        raise PITTaxonomySourceError(f"company publication date is missing: {market}")
    text = raw.strip().replace("/", "-")
    if re.fullmatch(r"[0-9]{7}", text):
        text = f"{int(text[:3]) + 1911:04d}-{text[3:5]}-{text[5:7]}"
    elif re.fullmatch(r"[0-9]{3}-[0-9]{2}-[0-9]{2}", text):
        text = f"{int(text[:3]) + 1911:04d}-{text[4:6]}-{text[7:9]}"
    elif re.fullmatch(r"[0-9]{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise PITTaxonomySourceError(f"company publication date is invalid: {market}") from error
    return datetime.combine(parsed, time.min, tzinfo=TAIPEI)


def _ensure_bundle_root(root: Path) -> None:
    if root.exists():
        if not root.is_dir():
            raise PITTaxonomySourceError("taxonomy bundle root is not a directory")
        # A retry may have stopped after a subset of the immutable files was
        # written.  Every individual file below is still create-only and is
        # compared byte-for-byte, so allowing an existing directory here does
        # not permit replacement or backfill.  The final bundle manifest and
        # reader readback remain the acceptance gate.
    else:
        root.mkdir(parents=True, exist_ok=False)


def _write_create_only_json(path: Path, payload: object) -> None:
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    _write_create_only_bytes(path, encoded)


def _write_create_only_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        if path.read_bytes() != payload:
            raise PITTaxonomySourceError(f"immutable taxonomy file differs on retry: {path}") from error


def _read_json_object(path: Path, name: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError(f"{name} is unreadable") from error
    if not isinstance(value, dict):
        raise PITTaxonomySourceError(f"{name} must be an object")
    return {str(key): item for key, item in value.items()}


def _resolve_relative(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PITTaxonomySourceError("taxonomy relative path is missing")
    relative = Path(value)
    if relative.is_absolute():
        raise PITTaxonomySourceError("taxonomy path must be relative")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise PITTaxonomySourceError("taxonomy path escapes bundle root") from error
    if not resolved.is_file():
        raise PITTaxonomySourceError(f"taxonomy file is missing: {relative}")
    return resolved


def _normalize_symbols(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise PITTaxonomySourceError(f"{field_name} must be a non-empty array")
    normalized = tuple(str(item).strip() for item in value)
    if any(_SYMBOL_RE.fullmatch(item) is None for item in normalized):
        raise PITTaxonomySourceError(f"{field_name} contains an invalid symbol")
    if normalized != tuple(dict.fromkeys(normalized)):
        raise PITTaxonomySourceError(f"{field_name} must be unique")
    if field_name not in {"rank_order", "universe_hash_symbols"} and normalized != tuple(sorted(normalized)):
        raise PITTaxonomySourceError(f"{field_name} must be sorted")
    return normalized


def _normalize_scores(value: Sequence[int], expected_length: int) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != expected_length:
        raise PITTaxonomySourceError("scores_bp length does not match universe_hash_symbols")
    if any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 10000 for item in value):
        raise PITTaxonomySourceError("scores_bp must contain integer basis points")
    return [int(item) for item in value]


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PITTaxonomySourceError(f"{field_name} must be a string array")
    result = sorted(set(str(item) for item in value))
    if len(result) != len(value):
        raise PITTaxonomySourceError(f"{field_name} must be unique")
    return result


def _strict_string_map(value: object, field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{field_name} must be a string map")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise PITTaxonomySourceError(f"{field_name} must be a string map")
        result[key] = item
    return result


def _strict_count_map(value: object, field_name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{field_name} must be an integer map")
    result: dict[str, int] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or isinstance(item, bool)
            or not isinstance(item, int)
            or item < 0
        ):
            raise PITTaxonomySourceError(f"{field_name} must be an integer map")
        result[key] = item
    return result


def _value_counts(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _aware(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise PITTaxonomySourceError(f"{field_name} is invalid") from error
    else:
        raise PITTaxonomySourceError(f"{field_name} must be timezone-aware")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PITTaxonomySourceError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(TAIPEI)


def _required_date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise PITTaxonomySourceError(f"{field_name} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise PITTaxonomySourceError(f"{field_name} is invalid") from error


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PITTaxonomySourceError(f"{field_name} must be non-empty text")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _optional_mapping(
    value: object,
    field_name: str,
) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise PITTaxonomySourceError(f"{field_name} keys must be text")
    return {str(key): item for key, item in value.items()}


def _require_bytes(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise PITTaxonomySourceError(f"{field_name} must be non-empty bytes")
    if len(value) > 64 * 1024 * 1024:
        raise PITTaxonomySourceError(f"{field_name} exceeds 64 MiB bound")
    return value


def _require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PITTaxonomySourceError(f"{field_name} must be sha256")
    return value


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_json(value: object) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


__all__ = [
    "PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION",
    "PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION",
    "PIT_TAXONOMY_CUTOFF",
    "PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION",
    "PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_CONFIG_ENV",
    "PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION",
    "PITTaxonomyBundleResult",
    "PITTaxonomySourceResponse",
    "PITTaxonomySourceError",
    "build_daily_pit_taxonomy_bundle",
    "capture_configured_daily_pit_taxonomy_bundle",
    "fetch_official_pit_taxonomy_source",
    "load_pit_taxonomy_source_config",
    "read_daily_pit_taxonomy_bundle",
    "validate_daily_pit_taxonomy_bundle",
]
