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
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, TypedDict, cast
import uuid
from urllib.error import HTTPError
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
from data_module.pit_inactive_security_termination_evidence import (
    InactiveTerminationEvidenceError,
    OfficialTerminationSourceSpec,
    PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES,
    parse_official_termination_notice,
    validate_official_termination_proof_readback,
)
from data_module.prospective_formal_clock import canonical_json
from data_module.prospective_official_pit_source import (
    OFFICIAL_COMPANY_SOURCE_DEFINITIONS,
    build_official_first_seen_capture,
)
from data_module.pit_prospective_denominator import validate_prospective_pit_denominator
from data_module.wp5_official_daily_capture_validator import (
    CaptureValidationError,
    _read_regular_single_link_file,
)


PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION = "pit-industry-taxonomy-daily-bundle.v1"
PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v3"
PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION = "pit-industry-taxonomy-source.v2"
PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION = "pit-industry-taxonomy-daily-bundle.v2"
PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v4"
PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION = "pit-industry-taxonomy-source.v3"
PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION = "pit-industry-taxonomy-scope-binding.v1"
PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION = "pit-industry-taxonomy-raw-manifest.v1"
PIT_TAXONOMY_BUNDLE_PRODUCER_VERSION = "official-pit-taxonomy-daily-producer.v1"
PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION = "pit-industry-taxonomy-source-config.v1"
PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION = "pit-industry-taxonomy-capture-attempt.v1"
PIT_TAXONOMY_CAPTURE_ATTEMPT_BINDING_SCHEMA_VERSION = "pit-industry-taxonomy-capture-attempt-binding.v1"
PIT_TAXONOMY_SOURCE_CONFIG_ENV = "PIT_TAXONOMY_SOURCE_CONFIG"
PIT_TAXONOMY_SOURCE_CONFIG_PROOF_SCHEMA_VERSION = "pit-taxonomy-source-config-proof.v1"
PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES = 1024 * 1024
PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH = (
    "output/qa/pit_taxonomy_split_candidate_20261001/source_config_saved_notice.json"
)
PIT_TAXONOMY_CUTOFF = time(8, 30)
PIT_TAXONOMY_FETCH_TIMEOUT_SECONDS = 30
PIT_TAXONOMY_MAX_SOURCE_BYTES = 64 * 1024 * 1024
PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS = 16
PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES = 128 * 1024 * 1024
PIT_TAXONOMY_CAPTURE_MIN_FREE_BYTES = 16 * 1024 * 1024
PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD = "inactive_security_overlay_by_symbol"
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
    schema_version: str = PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION
    capture_attempt_id: str | None = None
    capture_attempt_path: Path | None = None
    capture_attempt_result_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
        if self.schema_version != PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION:
            payload["schema_version"] = self.schema_version
        if self.schema_version == PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION:
            payload["capture_attempt_id"] = self.capture_attempt_id
            payload["capture_attempt_path"] = (
                str(self.capture_attempt_path)
                if self.capture_attempt_path is not None
                else None
            )
            payload["capture_attempt_result_path"] = (
                str(self.capture_attempt_result_path)
                if self.capture_attempt_result_path is not None
                else None
            )
        return payload


@dataclass(frozen=True)
class PITTaxonomySourceResponse:
    """一份 taxonomy response 的原始 bytes 與實際完成 metadata。"""

    body: bytes
    metadata: Mapping[str, object]


class _PITTaxonomyCaptureAttempt:
    """split candidate 的前解析原始回應 custody；所有檔案均 create-only。"""

    def __init__(
        self,
        *,
        publication_root: Path,
        capture_date: date,
        attempt_id: str,
        started_at: datetime,
        scope_binding: Mapping[str, object],
        universe_hash: str,
        clock_id: str,
        clock_manifest_hash: str,
        source_config_hash: str,
        planned_sources: Sequence[Mapping[str, object]],
        custody_now: Callable[[], datetime],
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None:
            raise PITTaxonomySourceError("capture attempt id must be a 32-character UUID hex")
        raw_publication_root = Path(os.path.abspath(str(publication_root.expanduser())))
        _assert_no_link_path(raw_publication_root, allow_missing=True)
        self.publication_root = raw_publication_root
        self.capture_date = capture_date
        self.attempt_id = attempt_id
        self.started_at = _aware(started_at, "capture_attempt.started_at")
        self.planned_sources = [dict(item) for item in planned_sources]
        self.custody_now = custody_now
        self.components: list[dict[str, object]] = []
        self.rejected_components: list[dict[str, object]] = []
        self.total_raw_bytes = 0
        self.root = (
            self.publication_root
            / "pit_taxonomy_capture_attempts"
            / capture_date.isoformat()
            / attempt_id
        )
        _assert_no_link_path(self.publication_root, allow_missing=True)
        _assert_no_link_path(self.root, allow_missing=True, confine_to=self.publication_root)
        if self.root.exists() or self.root.is_symlink():
            raise PITTaxonomySourceError("capture attempt root already exists")
        parent = self.root.parent
        parent.mkdir(parents=True, exist_ok=True)
        _assert_no_link_path(parent, allow_missing=False, confine_to=self.publication_root)
        self._require_free_space(0)
        self.root.mkdir(exist_ok=False)
        self.components_root = self.root / "components"
        self.components_root.mkdir(exist_ok=False)
        binding = _split_scope_binding_fields(scope_binding)
        self.descriptor: dict[str, object] = {
            "schema_version": PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "capture_date": capture_date.isoformat(),
            "cutoff_at": datetime.combine(
                capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI
            ).isoformat(),
            "started_at": self.started_at.isoformat(),
            "source_config_sha256": source_config_hash,
            "scope_binding": binding,
            "scope_binding_sha256": _sha256_json(binding),
            "universe_hash": universe_hash,
            "clock_id": clock_id,
            "clock_manifest_hash": clock_manifest_hash,
            "planned_sources": self.planned_sources,
            "planned_component_count": len(self.planned_sources),
            "max_component_count": PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS,
            "max_component_raw_bytes": PIT_TAXONOMY_MAX_SOURCE_BYTES,
            "max_aggregate_raw_bytes": PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES,
            "minimum_free_bytes": PIT_TAXONOMY_CAPTURE_MIN_FREE_BYTES,
            "candidate_only": True,
            "research_only": True,
            "formal_consumer_compatible": False,
            "formal_credit": False,
        }
        descriptor_path = self.root / "attempt_descriptor.json"
        self._write_json(descriptor_path, self.descriptor)
        self.descriptor_sha256 = _file_sha256(descriptor_path)
        if len(self.planned_sources) > PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
            error = PITTaxonomySourceError(
                "capture attempt source plan exceeds component-count limit"
            )
            self.finish_failure(error)
            setattr(
                error,
                "capture_attempt",
                {
                    "attempt_id": attempt_id,
                    "path": str(self.root),
                    "result_path": str(self.result_path),
                    "components_saved_count": 0,
                    "aggregate_raw_bytes": 0,
                },
            )
            raise error

    @property
    def relative_root(self) -> str:
        return self.root.relative_to(self.publication_root).as_posix()

    @property
    def result_path(self) -> Path:
        return self.root / "capture_result.json"

    def _require_free_space(self, incoming_bytes: int) -> None:
        try:
            free_bytes = shutil.disk_usage(self.publication_root).free
        except OSError as error:
            raise PITTaxonomySourceError("capture attempt cannot inspect free disk space") from error
        if free_bytes - incoming_bytes < PIT_TAXONOMY_CAPTURE_MIN_FREE_BYTES:
            raise PITTaxonomySourceError("capture attempt free-space reserve would be breached")

    def _write_bytes(self, path: Path, value: bytes) -> None:
        _assert_no_link_path(path.parent, allow_missing=False, confine_to=self.root)
        self._require_free_space(len(value))
        _write_create_only_bytes(path, value)

    def _write_json(self, path: Path, value: object) -> None:
        encoded = (canonical_json(value) + "\n").encode("utf-8")
        if len(encoded) > 1024 * 1024:
            raise PITTaxonomySourceError("capture attempt metadata exceeds byte bound")
        self._write_bytes(path, encoded)

    def record_component(
        self,
        source_name: str,
        raw: bytes,
        metadata: Mapping[str, object] | None,
        *,
        fetched: bool,
    ) -> dict[str, object]:
        if not isinstance(raw, bytes) or not raw:
            raise PITTaxonomySourceError(f"{source_name}.body must be non-empty bytes")
        body = raw
        if len(self.components) >= PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
            self._record_rejected_component(
                source_name,
                body,
                metadata,
                reason="component_count_limit",
            )
            raise PITTaxonomySourceError("capture attempt exceeds component-count limit")
        if len(body) > PIT_TAXONOMY_MAX_SOURCE_BYTES:
            self._record_rejected_component(
                source_name,
                body,
                metadata,
                reason="per_source_byte_limit",
            )
            raise PITTaxonomySourceError("capture attempt component exceeds per-source byte limit")
        if self.total_raw_bytes + len(body) > PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES:
            self._record_rejected_component(
                source_name,
                body,
                metadata,
                reason="aggregate_raw_byte_limit",
            )
            raise PITTaxonomySourceError("capture attempt exceeds aggregate raw-byte limit")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_name).strip("._")[:72]
        if not safe_name:
            raise PITTaxonomySourceError("capture attempt source name is invalid")
        ordinal = len(self.components) + 1
        stem = f"{ordinal:02d}_{safe_name}"
        raw_relative = Path("components") / f"{stem}.raw"
        metadata_relative = Path("components") / f"{stem}.metadata.json"
        raw_path = self.root / raw_relative
        metadata_path = self.root / metadata_relative
        metadata_body: dict[str, object] = {
            "source_name": source_name,
            "fetched": fetched,
            "custodied_at": _aware(self.custody_now(), "capture_attempt.custodied_at").isoformat(),
            "raw_sha256": _sha256_bytes(body),
            "raw_bytes": len(body),
            "http_metadata": (
                {str(key): value for key, value in metadata.items()}
                if isinstance(metadata, Mapping)
                else None
            ),
            "metadata_valid": isinstance(metadata, Mapping),
        }
        metadata_encoded = (canonical_json(metadata_body) + "\n").encode("utf-8")
        if len(metadata_encoded) > 1024 * 1024:
            raise PITTaxonomySourceError("capture attempt HTTP metadata exceeds byte bound")
        self._require_free_space(len(body) + len(metadata_encoded))
        self._write_bytes(raw_path, body)
        self._write_bytes(metadata_path, metadata_encoded)
        item = {
            "source_name": source_name,
            "fetched": fetched,
            "raw_path": raw_relative.as_posix(),
            "raw_sha256": _sha256_bytes(body),
            "raw_bytes": len(body),
            "metadata_path": metadata_relative.as_posix(),
            "metadata_sha256": _sha256_bytes(metadata_encoded),
        }
        self.components.append(item)
        self.total_raw_bytes += len(body)
        return dict(item)

    def _record_rejected_component(
        self,
        source_name: str,
        body: bytes,
        metadata: Mapping[str, object] | None,
        *,
        reason: str,
    ) -> None:
        self.rejected_components.append(
            {
                "source_name": source_name,
                "reason": reason,
                "bytes_seen": min(len(body), PIT_TAXONOMY_MAX_SOURCE_BYTES + 1),
                "truncated": (
                    metadata.get("body_truncated") is True
                    if isinstance(metadata, Mapping)
                    else len(body) > PIT_TAXONOMY_MAX_SOURCE_BYTES
                ),
                "full_body_saved": False,
            }
        )

    def seal_inputs(self) -> dict[str, object]:
        if len(self.planned_sources) > PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
            raise PITTaxonomySourceError("capture attempt source plan exceeds component-count limit")
        if len(self.components) != len(self.planned_sources):
            raise PITTaxonomySourceError("capture attempt component set is incomplete")
        receipt_body: dict[str, object] = {
            "schema_version": PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION,
            "attempt_id": self.attempt_id,
            "capture_date": self.capture_date.isoformat(),
            "started_at": self.started_at.isoformat(),
            "descriptor_path": "attempt_descriptor.json",
            "descriptor_sha256": self.descriptor_sha256,
            "scope_binding_sha256": self.descriptor["scope_binding_sha256"],
            "components": list(self.components),
            "component_count": len(self.components),
            "aggregate_raw_bytes": self.total_raw_bytes,
            "candidate_only": True,
            "research_only": True,
            "formal_consumer_compatible": False,
            "formal_credit": False,
        }
        path = self.root / "capture_receipt.json"
        self._write_json(path, receipt_body)
        receipt_sha256 = _file_sha256(path)
        return {
            "schema_version": PIT_TAXONOMY_CAPTURE_ATTEMPT_BINDING_SCHEMA_VERSION,
            "attempt_id": self.attempt_id,
            "path": self.relative_root,
            "descriptor_sha256": self.descriptor_sha256,
            "receipt_path": (Path(self.relative_root) / "capture_receipt.json").as_posix(),
            "receipt_sha256": receipt_sha256,
            "component_count": len(self.components),
            "aggregate_raw_bytes": self.total_raw_bytes,
        }

    def finish_success(self, *, bundle_manifest_path: Path) -> None:
        bundle = _read_json_object(bundle_manifest_path, "taxonomy bundle manifest")
        self._write_json(
            self.result_path,
            {
                "schema_version": PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION,
                "attempt_id": self.attempt_id,
                "capture_date": self.capture_date.isoformat(),
                "status": "success",
                "descriptor_sha256": self.descriptor_sha256,
                "receipt_sha256": _file_sha256(self.root / "capture_receipt.json"),
                "components": list(self.components),
                "rejected_components": list(self.rejected_components),
                "components_saved_count": len(self.components),
                "aggregate_raw_bytes": self.total_raw_bytes,
                "bundle_manifest_path": _relative_path(
                    self.publication_root, bundle_manifest_path
                ),
                "bundle_hash": bundle.get("bundle_hash"),
                "completed_at": _aware(self.custody_now(), "capture_attempt.completed_at").isoformat(),
            },
        )

    def finish_failure(self, error: Exception) -> None:
        if self.result_path.exists():
            return
        payload: dict[str, object] = {
                "schema_version": PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION,
                "attempt_id": self.attempt_id,
                "capture_date": self.capture_date.isoformat(),
                "status": "failed",
                "descriptor_sha256": self.descriptor_sha256,
                "components_saved_count": len(self.components),
                "aggregate_raw_bytes": self.total_raw_bytes,
                "components": list(self.components),
                "rejected_components": list(self.rejected_components),
                "error_type": type(error).__name__,
                "error": str(error).splitlines()[0][:400],
                "completed_at": _aware(self.custody_now(), "capture_attempt.completed_at").isoformat(),
            }
        receipt_path = self.root / "capture_receipt.json"
        if receipt_path.is_file():
            payload["receipt_sha256"] = _file_sha256(receipt_path)
        self._write_json(self.result_path, payload)


def read_pit_taxonomy_capture_attempt(
    attempt_root: Path,
    *,
    verify_complete: bool = False,
) -> dict[str, object]:
    """唯讀檢查 attempt 的描述檔、已保存 component 與終態；失敗 body 仍可取回。"""

    raw_root = Path(os.path.abspath(str(attempt_root.expanduser())))
    _assert_no_link_path(raw_root, allow_missing=False)
    root = raw_root.resolve(strict=True)
    descriptor_path = root / "attempt_descriptor.json"
    descriptor_raw = _proof_file_bytes(descriptor_path, "capture attempt descriptor", 1024 * 1024)
    descriptor = _decode_json_object(descriptor_raw, "capture attempt descriptor")
    if descriptor.get("schema_version") != PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION:
        raise PITTaxonomySourceError("capture attempt descriptor schema is unsupported")
    attempt_id = descriptor.get("attempt_id")
    if root.name != attempt_id or re.fullmatch(r"[0-9a-f]{32}", str(attempt_id)) is None:
        raise PITTaxonomySourceError("capture attempt id/path mismatch")
    components_root = root / "components"
    _assert_no_link_path(components_root, allow_missing=False, confine_to=root)
    discovered_raw = sorted(components_root.glob("*.raw"))
    verified_components: list[dict[str, object]] = []
    aggregate = 0
    for raw_path in discovered_raw:
        metadata_path = raw_path.with_suffix(".metadata.json")
        raw = _proof_file_bytes(raw_path, "capture attempt raw component", PIT_TAXONOMY_MAX_SOURCE_BYTES)
        metadata_raw = _proof_file_bytes(metadata_path, "capture attempt component metadata", 1024 * 1024)
        metadata = _decode_json_object(metadata_raw, "capture attempt component metadata")
        http_metadata = metadata.get("http_metadata")
        if not isinstance(http_metadata, Mapping):
            raise PITTaxonomySourceError("capture attempt component HTTP metadata is missing")
        if metadata.get("source_name") is None:
            raise PITTaxonomySourceError("capture attempt component source name is missing")
        if (
            metadata.get("raw_sha256") != _sha256_bytes(raw)
            or metadata.get("raw_bytes") != len(raw)
        ):
            raise PITTaxonomySourceError("capture attempt raw bytes differ from pinned component metadata")
        aggregate += len(raw)
        verified_components.append(
            {
                "source_name": metadata["source_name"],
                "fetched": metadata.get("fetched"),
                "raw_path": raw_path.relative_to(root).as_posix(),
                "raw_sha256": _sha256_bytes(raw),
                "raw_bytes": len(raw),
                "metadata_path": metadata_path.relative_to(root).as_posix(),
                "metadata_sha256": _sha256_bytes(metadata_raw),
                "http_metadata": dict(http_metadata),
            }
        )
    if len(verified_components) > PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
        raise PITTaxonomySourceError("capture attempt component-count limit exceeded")
    if aggregate > PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES:
        raise PITTaxonomySourceError("capture attempt aggregate raw-byte limit exceeded")
    result_path = root / "capture_result.json"
    result: dict[str, object] = {
        "status": "partial_untrusted",
        "attempt_id": attempt_id,
        "components": verified_components,
        "component_count": len(verified_components),
        "aggregate_raw_bytes": aggregate,
        "descriptor_sha256": _sha256_bytes(descriptor_raw),
    }
    if result_path.is_file():
        _assert_no_link_path(result_path, allow_missing=False, confine_to=root)
        result_raw = _proof_file_bytes(
            result_path, "capture attempt result", 1024 * 1024
        )
        result_value = _decode_json_object(result_raw, "capture attempt result")
        if (
            result_value.get("schema_version")
            != PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION
            or result_value.get("attempt_id") != attempt_id
            or result_value.get("capture_date") != descriptor.get("capture_date")
            or result_value.get("status") not in {"success", "failed"}
        ):
            raise PITTaxonomySourceError("capture attempt result id mismatch")
        if result_value.get("descriptor_sha256") != result["descriptor_sha256"]:
            raise PITTaxonomySourceError("capture attempt terminal descriptor hash mismatch")
        terminal_components = result_value.get("components")
        observed_component_pins = [
            {
                "source_name": item["source_name"],
                "fetched": item.get("fetched"),
                "raw_path": item["raw_path"],
                "raw_sha256": item["raw_sha256"],
                "raw_bytes": item["raw_bytes"],
                "metadata_path": item["metadata_path"],
                "metadata_sha256": item["metadata_sha256"],
            }
            for item in verified_components
        ]
        if terminal_components != observed_component_pins:
            raise PITTaxonomySourceError("capture attempt terminal component hashes mismatch")
        if (
            result_value.get("components_saved_count") != len(verified_components)
            or result_value.get("aggregate_raw_bytes") != aggregate
        ):
            raise PITTaxonomySourceError("capture attempt terminal component counts mismatch")
        rejected_value = result_value.get("rejected_components", [])
        if not isinstance(rejected_value, list) or any(
            not isinstance(item, Mapping)
            or not isinstance(item.get("source_name"), str)
            or not isinstance(item.get("reason"), str)
            or isinstance(item.get("bytes_seen"), bool)
            or not isinstance(item.get("bytes_seen"), int)
            or item.get("bytes_seen", -1) < 0
            or item.get("full_body_saved") is not False
            or not isinstance(item.get("truncated"), bool)
            for item in rejected_value
        ):
            raise PITTaxonomySourceError("capture attempt rejected-component diagnostics are invalid")
        result["rejected_components"] = [dict(item) for item in rejected_value]
        result["terminal_result"] = result_value
        result["status"] = str(result_value.get("status"))
    receipt_path = root / "capture_receipt.json"
    if receipt_path.is_file():
        _assert_no_link_path(receipt_path, allow_missing=False, confine_to=root)
        receipt_raw = _proof_file_bytes(receipt_path, "capture attempt receipt", 4 * 1024 * 1024)
        receipt = _decode_json_object(receipt_raw, "capture attempt receipt")
        if receipt.get("attempt_id") != attempt_id:
            raise PITTaxonomySourceError("capture attempt receipt id mismatch")
        result["receipt"] = receipt
        result["receipt_sha256"] = _sha256_bytes(receipt_raw)
        terminal_value = result.get("terminal_result")
        if isinstance(terminal_value, Mapping) and terminal_value.get("receipt_sha256") != result["receipt_sha256"]:
            raise PITTaxonomySourceError("capture attempt terminal receipt hash mismatch")
        _verify_capture_attempt_files(root, descriptor, receipt)
    if verify_complete or result.get("status") == "success":
        if result.get("status") != "success" or "receipt" not in result:
            raise PITTaxonomySourceError("capture attempt is not a successful complete attempt")
        terminal_value = result.get("terminal_result")
        if (
            not isinstance(terminal_value, Mapping)
            or terminal_value.get("receipt_sha256") != result.get("receipt_sha256")
        ):
            raise PITTaxonomySourceError("capture attempt terminal receipt hash mismatch")
        _verify_capture_attempt_files(root, descriptor, cast(Mapping[str, object], result["receipt"]))
    return result


def load_pit_taxonomy_source_config(
    path: Path | None = None,
    *,
    bounded_read: bool = False,
) -> dict[str, object]:
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
        configured_value = os.environ.get(PIT_TAXONOMY_SOURCE_CONFIG_ENV)
        if not isinstance(configured_value, str) or not configured_value.strip():
            raise PITTaxonomySourceError(
                f"{PIT_TAXONOMY_SOURCE_CONFIG_ENV} is not configured"
            )
        configured = Path(configured_value.strip())
    if bounded_read:
        bounded_config_path = Path(os.path.abspath(str(configured.expanduser())))
        _assert_no_link_path(bounded_config_path, allow_missing=False)
        raw = _proof_file_bytes(
            bounded_config_path,
            "PIT taxonomy source config",
            PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
        )
        value = _decode_json_object_no_duplicates(raw, "PIT taxonomy source config")
    else:
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


def _source_config_canonical_sha256(config: Mapping[str, object]) -> str:
    return _sha256_bytes(canonical_json(dict(config)).encode("utf-8"))


def _source_config_semantic_value(config: Mapping[str, object]) -> dict[str, object]:
    """只忽略 inactive saved-evidence 的運送路徑，其餘設定逐欄保留。"""

    value = json.loads(canonical_json(dict(config)))
    if not isinstance(value, dict):
        raise PITTaxonomySourceError("PIT taxonomy source config must be an object")
    inactive = value.get("inactive_security", {})
    if not isinstance(inactive, dict):
        raise PITTaxonomySourceError("PIT taxonomy inactive_security section is invalid")
    for key, spec in inactive.items():
        if not isinstance(spec, dict):
            raise PITTaxonomySourceError(
                f"PIT taxonomy inactive security config is invalid: {key}"
            )
        saved = spec.get("saved_evidence")
        if saved is None:
            continue
        if not isinstance(saved, dict) or set(saved) != {"raw_path", "metadata_path"}:
            raise PITTaxonomySourceError(
                f"inactive_security.{key}.saved_evidence fields are invalid"
            )
        if any(
            not isinstance(saved.get(field), str) or not str(saved[field]).strip()
            for field in ("raw_path", "metadata_path")
        ):
            raise PITTaxonomySourceError(
                f"inactive_security.{key}.saved_evidence paths are invalid"
            )
        spec.pop("saved_evidence")
    return value


def _source_config_proof_cache_root(repository_root: Path) -> Path:
    # Keep the root short enough for Windows MAX_PATH even when nested under
    # a pytest temp directory; the one child is still a full SHA-256 address.
    return Path(os.path.abspath(str(repository_root.expanduser()))) / "output" / "qa" / "pit_cfg_proofs"


def _source_config_proof_cache_path(
    repository_root: Path,
    *,
    capture_date: date,
    attempt_id: str,
    source_config_sha256: str,
) -> Path:
    canonical_hash = _require_sha256(source_config_sha256, "source_config_sha256")
    if re.fullmatch(r"[0-9a-f]{32}", attempt_id) is None:
        raise PITTaxonomySourceError("source config proof attempt id is invalid")
    cache_key = _sha256_json(
        {
            "capture_date": capture_date.isoformat(),
            "attempt_id": attempt_id,
            "source_config_canonical_sha256": canonical_hash,
        }
    ).removeprefix("sha256:")
    return _source_config_proof_cache_root(repository_root) / cache_key


def _bounded_repo_source_config_bytes(
    source_config_path: Path,
    *,
    repository_root: Path,
) -> tuple[Path, bytes, dict[str, object]]:
    repo = Path(os.path.abspath(str(repository_root.expanduser())))
    _assert_no_link_path(repo, allow_missing=False)
    repo = repo.resolve(strict=True)
    source = Path(os.path.abspath(str(source_config_path.expanduser())))
    _assert_no_link_path(source, allow_missing=False, confine_to=repo)
    try:
        source.resolve(strict=True).relative_to(repo)
    except (OSError, ValueError) as error:
        raise PITTaxonomySourceError(
            "saved taxonomy source config must be a no-link repository file"
        ) from error
    raw = _proof_file_bytes(
        source,
        "saved PIT taxonomy source config",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
    )
    config = _decode_json_object_no_duplicates(raw, "saved PIT taxonomy source config")
    return source, raw, config


def _read_split_config_proof_bundle(
    bundle_manifest_path: Path,
    *,
    publication_root: Path,
    now: datetime,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], Path, bytes]:
    """在實際同日 cutoff 前完整驗證既有 split candidate 與 attempt。"""

    observed = _aware(now, "split_config_proof.now")
    bundle_path = Path(os.path.abspath(str(bundle_manifest_path.expanduser())))
    publication = Path(os.path.abspath(str(publication_root.expanduser())))
    _assert_no_link_path(publication, allow_missing=False)
    publication = publication.resolve(strict=True)
    _assert_no_link_path(bundle_path, allow_missing=False, confine_to=publication)
    try:
        bundle_path.resolve(strict=True).relative_to(publication)
    except (OSError, ValueError) as error:
        raise PITTaxonomySourceError("split candidate bundle escapes publication root") from error
    bundle_raw = _proof_file_bytes(
        bundle_path, "split candidate bundle manifest", 16 * 1024 * 1024
    )
    bundle = _decode_json_object_no_duplicates(bundle_raw, "split candidate bundle manifest")
    capture_date = _required_date(bundle.get("capture_date"), "bundle.capture_date")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if observed.astimezone(TAIPEI).date() != capture_date or observed >= cutoff:
        raise PITTaxonomySourceError(
            "split config proof must be materialized on the candidate date before Taipei 08:30"
        )
    if bundle.get("schema_version") != "pit-industry-taxonomy-daily-bundle.v2":
        raise PITTaxonomySourceError("split config proof requires the v2 taxonomy candidate")
    if (
        bundle.get("taxonomy_coverage_complete") is not True
        or bundle.get("rule_scope_compatible") is not False
        or bundle.get("formal_oos_allowed") is not False
        or bundle.get("production_action_allowed") is not False
        or bundle.get("promotion_eligible") is not False
    ):
        raise PITTaxonomySourceError("split taxonomy candidate has unsafe consumer flags")
    expected_bundle_path = (
        publication
        / "pit_taxonomy_preopen_split_v2"
        / capture_date.isoformat()
        / "bundle_manifest.json"
    )
    if bundle_path.resolve(strict=True) != expected_bundle_path.resolve(strict=False):
        raise PITTaxonomySourceError(
            "split taxonomy candidate is outside its canonical immutable root"
        )
    bundle_hash = _require_sha256(bundle.get("bundle_hash"), "bundle_hash")
    bundle_body = dict(bundle)
    bundle_body.pop("bundle_hash", None)
    if _sha256_json(bundle_body) != bundle_hash:
        raise PITTaxonomySourceError("split candidate bundle hash mismatch")
    expected_decision = cutoff
    try:
        validated = validate_daily_pit_taxonomy_bundle(
            bundle_path,
            decision_at=expected_decision,
            now=observed,
        )
    except Exception as error:  # validator is the authoritative full readback
        raise PITTaxonomySourceError(
            f"split candidate full validation failed:{type(error).__name__}"
        ) from error
    if validated.get("schema_version") != "pit-industry-taxonomy-daily-bundle.v2":
        raise PITTaxonomySourceError("split candidate full validator did not return v2")
    if _proof_file_bytes(
        bundle_path, "split candidate bundle manifest recheck", 16 * 1024 * 1024
    ) != bundle_raw:
        raise PITTaxonomySourceError("split candidate bundle changed during validation")
    attempt_binding = bundle.get("capture_attempt_binding")
    if not isinstance(attempt_binding, Mapping):
        raise PITTaxonomySourceError("split candidate capture-attempt binding is missing")
    fields = _capture_attempt_binding_fields(attempt_binding)
    attempt_path = _proof_child(
        publication,
        fields.get("path"),
        required_prefix=f"pit_taxonomy_capture_attempts/{capture_date.isoformat()}/",
        label="split candidate capture attempt",
    )
    attempt = read_pit_taxonomy_capture_attempt(attempt_path, verify_complete=True)
    if attempt.get("status") != "success" or attempt.get("attempt_id") != fields.get("attempt_id"):
        raise PITTaxonomySourceError("split candidate capture attempt is not a successful match")
    if attempt.get("descriptor_sha256") != fields.get("descriptor_sha256"):
        raise PITTaxonomySourceError("split candidate descriptor hash differs from bundle binding")
    if attempt.get("receipt_sha256") != fields.get("receipt_sha256"):
        raise PITTaxonomySourceError("split candidate receipt hash differs from bundle binding")
    descriptor_path = _proof_child(
        attempt_path,
        "attempt_descriptor.json",
        required_prefix=None,
        label="split candidate descriptor",
    )
    descriptor_raw = _proof_file_bytes(
        descriptor_path, "split candidate descriptor", 1024 * 1024
    )
    if _sha256_bytes(descriptor_raw) != fields.get("descriptor_sha256"):
        raise PITTaxonomySourceError("split candidate descriptor changed during readback")
    descriptor = _decode_json_object_no_duplicates(descriptor_raw, "split candidate descriptor")
    if descriptor.get("source_config_sha256") is None:
        raise PITTaxonomySourceError("split candidate descriptor has no source config hash")
    return bundle, validated, attempt, descriptor_path, bundle_raw


def materialize_existing_split_source_config_proof(
    *,
    publication_root: Path,
    bundle_manifest_path: Path,
    source_config_path: Path,
    repository_root: Path,
    materialized_at: datetime,
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """為舊 split attempt late-bind 原設定 bytes；不改舊 bundle 或 attempt。"""

    bundle, validated, attempt, descriptor_path, bundle_raw = _read_split_config_proof_bundle(
        bundle_manifest_path,
        publication_root=publication_root,
        now=materialized_at,
    )
    source, source_raw, source_config = _bounded_repo_source_config_bytes(
        source_config_path,
        repository_root=repository_root,
    )
    repo = Path(os.path.abspath(str(repository_root.expanduser()))).resolve(strict=True)
    source_relative = source.resolve(strict=True).relative_to(repo).as_posix()
    if source_relative != PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH:
        raise PITTaxonomySourceError(
            "late source config proof source path is not the approved saved notice config"
        )
    canonical_hash = _source_config_canonical_sha256(source_config)
    attempt_root = descriptor_path.parent
    descriptor_raw = _proof_file_bytes(
        descriptor_path, "split candidate descriptor", 1024 * 1024
    )
    descriptor = _decode_json_object_no_duplicates(descriptor_raw, "split candidate descriptor")
    if canonical_hash != descriptor.get("source_config_sha256"):
        raise PITTaxonomySourceError(
            "saved source config canonical hash differs from original attempt descriptor"
        )
    capture_date = _required_date(bundle.get("capture_date"), "bundle.capture_date")
    capture_binding = bundle.get("capture_attempt_binding")
    if not isinstance(capture_binding, Mapping):
        raise PITTaxonomySourceError("split candidate attempt binding is missing")
    attempt_id = str(capture_binding.get("attempt_id"))
    bundle_hash = _require_sha256(bundle.get("bundle_hash"), "bundle_hash")
    materialized = _aware(materialized_at, "source_config_proof.materialized_at")
    captured_at = _aware(bundle.get("captured_at"), "bundle.captured_at")
    if materialized < captured_at:
        raise PITTaxonomySourceError("late source config proof predates bundle capture")
    publication = Path(os.path.abspath(str(publication_root.expanduser()))).resolve(strict=True)
    bundle_relative = Path(os.path.abspath(str(bundle_manifest_path.expanduser()))).resolve(strict=True).relative_to(publication).as_posix()
    attempt_relative = attempt_root.resolve(strict=True).relative_to(publication).as_posix()
    attempt_result = attempt.get("terminal_result")
    if not isinstance(attempt_result, Mapping):
        raise PITTaxonomySourceError("split candidate attempt terminal result is missing")
    proof_root = _source_config_proof_cache_path(
        repo,
        capture_date=capture_date,
        attempt_id=attempt_id,
        source_config_sha256=canonical_hash,
    )
    body: dict[str, object] = {
        "schema_version": PIT_TAXONOMY_SOURCE_CONFIG_PROOF_SCHEMA_VERSION,
        "capture_date": capture_date.isoformat(),
        "attempt_id": attempt_id,
        "bundle_path": bundle_relative,
        "bundle_file_sha256": _sha256_bytes(bundle_raw),
        "bundle_hash": bundle_hash,
        "attempt_path": attempt_relative,
        "descriptor_path": f"{attempt_relative}/attempt_descriptor.json",
        "descriptor_sha256": attempt.get("descriptor_sha256"),
        "receipt_path": f"{attempt_relative}/capture_receipt.json",
        "receipt_sha256": attempt.get("receipt_sha256"),
        "source_config_original_path": source_relative,
        "source_config_raw_path": "source_config.json",
        "source_config_raw_sha256": _sha256_bytes(source_raw),
        "source_config_raw_bytes": len(source_raw),
        "source_config_canonical_sha256": canonical_hash,
        "source_config_semantic_sha256": _sha256_json(
            _source_config_semantic_value(source_config)
        ),
        "materialization_started_at": materialized.isoformat(),
        "bundle_captured_at": captured_at.isoformat(),
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "research_only": True,
        "candidate_only": True,
        "formal_consumer_compatible": False,
        "formal_credit": False,
    }
    proof_payload = {**body, "proof_sha256": _sha256_json(body)}
    cache_raw_path = proof_root / "source_config.json"
    cache_proof_path = proof_root / "config_proof.json"
    cache_completion_path = proof_root / "completion_receipt.json"
    _assert_no_link_path(proof_root, allow_missing=True, confine_to=_source_config_proof_cache_root(repo))
    expected_cache_names = {
        "source_config.json",
        "config_proof.json",
        "completion_receipt.json",
    }
    if proof_root.exists():
        if not proof_root.is_dir() or {item.name for item in proof_root.iterdir()} != expected_cache_names:
            raise PITTaxonomySourceError("source config proof cache is partial or has unexpected files")
        existing = read_existing_split_source_config_proof(
            publication_root=publication_root,
            bundle_manifest_path=bundle_manifest_path,
            repository_root=repo,
            current_config=source_config,
            now=materialized,
        )
        return {
            "status": "late_source_config_proof_already_verified",
            "source_config_proof_root": str(proof_root),
            "source_config_proof_path": str(cache_proof_path),
            "source_config_raw_path": str(cache_raw_path),
            **{
                key: existing[key]
                for key in (
                    "proof_sha256",
                    "source_config_raw_sha256",
                    "source_config_canonical_sha256",
                    "materialized_at",
                    "historical_availability_proven",
                    "historical_pit_eligible",
                    "formal_credit",
                    "research_only",
                    "candidate_only",
                )
            },
        }
    proof_root.mkdir(parents=True, exist_ok=True)
    _assert_no_link_path(proof_root, allow_missing=False, confine_to=_source_config_proof_cache_root(repo))
    _write_bounded_create_only(cache_raw_path, source_raw, "source config proof raw", PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES, proof_root)
    _write_bounded_create_only(
        cache_proof_path,
        (canonical_json(proof_payload) + "\n").encode("utf-8"),
        "source config proof metadata",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
        proof_root,
    )
    raw_readback = _proof_file_bytes(
        cache_raw_path,
        "source config proof raw readback",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
    )
    proof_readback = _proof_file_bytes(
        cache_proof_path,
        "source config proof metadata readback",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
    )
    if raw_readback != source_raw or proof_readback != (canonical_json(proof_payload) + "\n").encode("utf-8"):
        raise PITTaxonomySourceError("source config proof create-only readback differs")
    completed_at = _aware(
        (now_provider or (lambda: datetime.now(timezone.utc)))(),
        "source_config_proof.completed_at",
    )
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if (
        completed_at.astimezone(TAIPEI).date() != capture_date
        or completed_at >= cutoff
        or completed_at < materialized
    ):
        raise PITTaxonomySourceError("source config proof completed outside same-day cutoff")
    completion_body: dict[str, object] = {
        "schema_version": "pit-taxonomy-source-config-proof-completion.v1",
        "capture_date": capture_date.isoformat(),
        "attempt_id": attempt_id,
        "source_config_canonical_sha256": canonical_hash,
        "source_config_raw_sha256": body["source_config_raw_sha256"],
        "proof_sha256": proof_payload["proof_sha256"],
        "materialization_started_at": materialized.isoformat(),
        "materialized_at": completed_at.isoformat(),
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "research_only": True,
        "candidate_only": True,
        "formal_credit": False,
    }
    completion_payload = {
        **completion_body,
        "completion_sha256": _sha256_json(completion_body),
    }
    _write_bounded_create_only(
        cache_completion_path,
        (canonical_json(completion_payload) + "\n").encode("utf-8"),
        "source config proof completion receipt",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
        proof_root,
    )
    completion_readback = _proof_file_bytes(
        cache_completion_path,
        "source config proof completion receipt readback",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
    )
    if completion_readback != (canonical_json(completion_payload) + "\n").encode("utf-8"):
        raise PITTaxonomySourceError("source config proof completion receipt readback differs")
    verification_completed_at = _aware(
        (now_provider or (lambda: datetime.now(timezone.utc)))(),
        "source_config_proof.verification_completed_at",
    )
    if (
        verification_completed_at.astimezone(TAIPEI).date() != capture_date
        or verification_completed_at >= cutoff
        or verification_completed_at < completed_at
    ):
        raise PITTaxonomySourceError("source config proof readback completed outside same-day cutoff")
    verified = read_existing_split_source_config_proof(
        publication_root=publication_root,
        bundle_manifest_path=bundle_manifest_path,
        repository_root=repo,
        current_config=source_config,
        now=verification_completed_at,
    )
    if verified.get("proof_sha256") != proof_payload["proof_sha256"]:
        raise PITTaxonomySourceError("source config proof linkage readback failed")
    return {
        "status": "late_source_config_proof_materialized",
        "source_config_proof_root": str(proof_root),
        "source_config_proof_path": str(cache_proof_path),
        "source_config_raw_path": str(cache_raw_path),
        "proof_sha256": proof_payload["proof_sha256"],
        "source_config_raw_sha256": body["source_config_raw_sha256"],
        "source_config_canonical_sha256": canonical_hash,
        "materialized_at": completed_at.isoformat(),
        "verification_completed_at": verification_completed_at.isoformat(),
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "formal_credit": False,
        "research_only": True,
        "candidate_only": True,
    }


def read_existing_split_source_config_proof(
    *,
    publication_root: Path,
    bundle_manifest_path: Path,
    repository_root: Path,
    current_config: Mapping[str, object],
    now: datetime,
) -> dict[str, object]:
    """只讀晚綁定的 hash-addressed config proof，並比對目前完整語意。"""

    bundle, _validated, attempt, descriptor_path, bundle_raw = _read_split_config_proof_bundle(
        bundle_manifest_path,
        publication_root=publication_root,
        now=now,
    )
    descriptor_raw = _proof_file_bytes(
        descriptor_path, "split candidate descriptor", 1024 * 1024
    )
    descriptor = _decode_json_object_no_duplicates(descriptor_raw, "split candidate descriptor")
    canonical_hash = _require_sha256(
        descriptor.get("source_config_sha256"), "descriptor.source_config_sha256"
    )
    capture_date = _required_date(bundle.get("capture_date"), "bundle.capture_date")
    bundle_attempt_binding = bundle.get("capture_attempt_binding")
    if not isinstance(bundle_attempt_binding, Mapping):
        raise PITTaxonomySourceError("split candidate attempt binding is missing")
    attempt_id = str(bundle_attempt_binding.get("attempt_id"))
    repo_input = Path(os.path.abspath(str(repository_root.expanduser())))
    _assert_no_link_path(repo_input, allow_missing=False)
    repo = repo_input.resolve(strict=True)
    proof_root = _source_config_proof_cache_path(
        repo,
        capture_date=capture_date,
        attempt_id=attempt_id,
        source_config_sha256=canonical_hash,
    )
    proof_cache_root = _source_config_proof_cache_root(repo)
    _assert_no_link_path(proof_root, allow_missing=True, confine_to=proof_cache_root)
    if not proof_root.exists():
        raise PITTaxonomySourceError("late source config proof is missing")
    expected_cache_names = {
        "source_config.json",
        "config_proof.json",
        "completion_receipt.json",
    }
    if not proof_root.is_dir() or {item.name for item in proof_root.iterdir()} != expected_cache_names:
        raise PITTaxonomySourceError("source config proof cache is partial or has unexpected files")
    raw_path = proof_root / "source_config.json"
    proof_path = proof_root / "config_proof.json"
    completion_path = proof_root / "completion_receipt.json"
    raw = _proof_file_bytes(
        raw_path, "hash-addressed source config proof raw", PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES
    )
    proof_raw = _proof_file_bytes(
        proof_path, "hash-addressed source config proof metadata", PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES
    )
    completion_raw = _proof_file_bytes(
        completion_path,
        "hash-addressed source config proof completion receipt",
        PIT_TAXONOMY_SOURCE_CONFIG_PROOF_MAX_BYTES,
    )
    proof = _decode_json_object_no_duplicates(proof_raw, "source config proof metadata")
    proof_hash = _require_sha256(proof.pop("proof_sha256", None), "source_config_proof.proof_sha256")
    if _sha256_json(proof) != proof_hash:
        raise PITTaxonomySourceError("source config proof metadata hash mismatch")
    completion = _decode_json_object_no_duplicates(
        completion_raw, "source config proof completion receipt"
    )
    completion_hash = _require_sha256(
        completion.pop("completion_sha256", None),
        "source_config_proof_completion.completion_sha256",
    )
    if _sha256_json(completion) != completion_hash:
        raise PITTaxonomySourceError("source config proof completion receipt hash mismatch")
    config = _decode_json_object_no_duplicates(raw, "hash-addressed source config proof raw")
    if proof.get("source_config_original_path") != PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH:
        raise PITTaxonomySourceError(
            "source config proof original path is not the approved saved notice config"
        )
    raw_hash = _sha256_bytes(raw)
    semantic_hash = _sha256_json(_source_config_semantic_value(config))
    if _source_config_canonical_sha256(config) != canonical_hash:
        raise PITTaxonomySourceError("source config proof does not match attempt canonical hash")
    if _source_config_semantic_value(config) != _source_config_semantic_value(current_config):
        raise PITTaxonomySourceError("current source config semantic contract differs from proof")
    started_at = _aware(
        proof.get("materialization_started_at"),
        "source_config_proof.materialization_started_at",
    )
    materialized_at = _aware(
        completion.get("materialized_at"),
        "source_config_proof_completion.materialized_at",
    )
    observed = _aware(now, "source_config_proof.now")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if materialized_at > observed or observed >= cutoff or observed.astimezone(TAIPEI).date() != capture_date:
        raise PITTaxonomySourceError("source config proof availability is outside same-day reuse window")
    if (
        started_at < _aware(bundle.get("captured_at"), "bundle.captured_at")
        or materialized_at < started_at
    ):
        raise PITTaxonomySourceError("source config proof claims pre-capture materialization")
    binding = bundle.get("capture_attempt_binding")
    if not isinstance(binding, Mapping):
        raise PITTaxonomySourceError("source config proof bundle binding is missing")
    binding_fields = _capture_attempt_binding_fields(binding)
    attempt_root = _proof_child(
        Path(os.path.abspath(str(publication_root.expanduser()))).resolve(strict=True),
        binding_fields.get("path"),
        required_prefix=f"pit_taxonomy_capture_attempts/{capture_date.isoformat()}/",
        label="source config proof attempt",
    )
    attempt = read_pit_taxonomy_capture_attempt(attempt_root, verify_complete=True)
    expected_proof = {
        "schema_version": PIT_TAXONOMY_SOURCE_CONFIG_PROOF_SCHEMA_VERSION,
        "capture_date": capture_date.isoformat(),
        "attempt_id": attempt_id,
        "bundle_path": Path(os.path.abspath(str(bundle_manifest_path.expanduser()))).resolve(strict=True).relative_to(Path(os.path.abspath(str(publication_root.expanduser()))).resolve(strict=True)).as_posix(),
        "bundle_file_sha256": _sha256_bytes(bundle_raw),
        "bundle_hash": bundle.get("bundle_hash"),
        "attempt_path": binding_fields.get("path"),
        "descriptor_path": f"{binding_fields.get('path')}/attempt_descriptor.json",
        "descriptor_sha256": attempt.get("descriptor_sha256"),
        "receipt_path": f"{binding_fields.get('path')}/capture_receipt.json",
        "receipt_sha256": attempt.get("receipt_sha256"),
        "source_config_original_path": PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH,
        "source_config_raw_path": "source_config.json",
        "source_config_raw_sha256": raw_hash,
        "source_config_raw_bytes": len(raw),
        "source_config_canonical_sha256": canonical_hash,
        "source_config_semantic_sha256": semantic_hash,
        "materialization_started_at": started_at.isoformat(),
        "bundle_captured_at": _aware(bundle.get("captured_at"), "bundle.captured_at").isoformat(),
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "research_only": True,
        "candidate_only": True,
        "formal_consumer_compatible": False,
        "formal_credit": False,
    }
    if proof != expected_proof:
        raise PITTaxonomySourceError("source config proof linkage differs from validated bundle/attempt")
    expected_completion = {
        "schema_version": "pit-taxonomy-source-config-proof-completion.v1",
        "capture_date": capture_date.isoformat(),
        "attempt_id": attempt_id,
        "source_config_canonical_sha256": canonical_hash,
        "source_config_raw_sha256": raw_hash,
        "proof_sha256": proof_hash,
        "materialization_started_at": started_at.isoformat(),
        "materialized_at": materialized_at.isoformat(),
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "research_only": True,
        "candidate_only": True,
        "formal_credit": False,
    }
    if completion != expected_completion:
        raise PITTaxonomySourceError("source config proof completion linkage differs")
    return {
        "status": "hash_addressed_source_config_proof_verified",
        "proof_sha256": proof_hash,
        "source_config_raw_sha256": raw_hash,
        "source_config_canonical_sha256": canonical_hash,
        "source_config_semantic_sha256": semantic_hash,
        "materialized_at": materialized_at.isoformat(),
        "materialization_started_at": started_at.isoformat(),
        "completion_receipt_sha256": completion_hash,
        "historical_availability_proven": False,
        "historical_pit_eligible": False,
        "research_only": True,
        "candidate_only": True,
        "formal_consumer_compatible": False,
        "formal_credit": False,
        "config": config,
    }


def _write_bounded_create_only(
    path: Path,
    payload: bytes,
    label: str,
    max_bytes: int,
    confinement_root: Path,
) -> None:
    if len(payload) > max_bytes:
        raise PITTaxonomySourceError(f"{label} exceeds byte bound")
    root = Path(os.path.abspath(str(confinement_root.expanduser())))
    target = Path(os.path.abspath(str(path.expanduser())))
    _assert_no_link_path(root, allow_missing=True)
    _assert_no_link_path(target, allow_missing=True, confine_to=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_link_path(target.parent, allow_missing=False, confine_to=root)
    try:
        with target.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        existing = _proof_file_bytes(target, label, max_bytes)
        if existing != payload:
            raise PITTaxonomySourceError(f"immutable {label} differs on retry")


def _plan_configured_components(
    config: Mapping[str, object],
    company_raw_payloads: Mapping[str, bytes],
    capture_date: date,
) -> list[dict[str, object]]:
    classification = config.get("classification")
    security = config.get("security")
    if not isinstance(classification, Mapping) or not isinstance(security, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy source sections are missing")
    company_markets = sorted(
        {
            OFFICIAL_COMPANY_SOURCE_DEFINITIONS[str(key)].market
            for key in company_raw_payloads
            if str(key) in OFFICIAL_COMPANY_SOURCE_DEFINITIONS
        }
    )
    plan: list[dict[str, object]] = []
    for market in company_markets:
        spec = classification.get(market)
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError(
                f"PIT taxonomy classification config missing: {market}"
            )
        components = spec.get("components")
        if isinstance(components, Mapping):
            for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS:
                component_spec = components.get(component_name)
                if not isinstance(component_spec, Mapping):
                    raise PITTaxonomySourceError(
                        f"PIT taxonomy composite component is invalid: {market}:{component_name}"
                    )
                mode = "url" if isinstance(component_spec.get("url"), str) else "path"
                plan.append(
                    {
                        "source_name": f"classification:{market}:{component_name}",
                        "mode": mode,
                    }
                )
        else:
            mode = "url" if isinstance(spec.get("url"), str) else "path"
            plan.append({"source_name": f"classification:{market}", "mode": mode})
    for key, spec in sorted(security.items(), key=lambda item: str(item[0])):
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError(f"PIT taxonomy security config is invalid: {key}")
        mode = "url" if isinstance(spec.get("url"), str) else "path"
        plan.append({"source_name": f"security:{str(key)}", "mode": mode})
    inactive_security = config.get("inactive_security", {})
    if not isinstance(inactive_security, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy inactive_security section is invalid")
    for key, value in sorted(inactive_security.items(), key=lambda item: str(item[0])):
        if not isinstance(value, Mapping):
            raise PITTaxonomySourceError(
                f"PIT taxonomy inactive security config is invalid: {key}"
            )
        termination_date = _required_date(
            value.get("termination_effective_on"),
            f"inactive_security.{key}.termination_effective_on",
        )
        if termination_date > capture_date:
            continue
        source_name = f"inactive_security:{str(key)}"
        saved_value = value.get("saved_evidence")
        if saved_value is not None:
            if not isinstance(saved_value, Mapping) or set(saved_value) != {
                "raw_path",
                "metadata_path",
            }:
                raise PITTaxonomySourceError(
                    f"{source_name}.saved_evidence fields are invalid"
                )
            plan.append({"source_name": source_name, "mode": "saved_evidence"})
            plan.append(
                {
                    "source_name": f"{source_name}:capture_metadata",
                    "mode": "saved_evidence_metadata",
                }
            )
        else:
            plan.append({"source_name": source_name, "mode": "url"})
    return plan


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
    scope_binding: Mapping[str, object] | None = None,
    fetch_source: Callable[[str], object] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    capture_attempt_id: str | None = None,
    capture_attempt_root: Path | None = None,
) -> PITTaxonomyBundleResult:
    """執行每日 capture；只有 split opt-in 會先建立獨立 raw custody。"""

    if scope_binding is None:
        if capture_attempt_id is not None or capture_attempt_root is not None:
            raise PITTaxonomySourceError(
                "legacy v1 capture cannot use split capture-attempt custody"
            )
        return _capture_configured_daily_pit_taxonomy_bundle_impl(
            config=config,
            bundle_root=bundle_root,
            capture_date=capture_date,
            decision_at=decision_at,
            now=now,
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
            universe_symbols_payload=universe_symbols_payload,
            scope_binding=None,
            fetch_source=fetch_source,
            now_provider=now_provider,
        )

    request_started_at = _aware(now, "request_started_at")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if request_started_at.astimezone(TAIPEI).date() != capture_date:
        raise PITTaxonomySourceError(
            "taxonomy request start date does not match capture_date"
        )
    if request_started_at >= cutoff:
        raise PITTaxonomySourceError("taxonomy request must start before Taipei 08:30")
    if not isinstance(config, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy source config must be an object")
    _assert_no_link_path(bundle_root, allow_missing=True)
    plan = _plan_configured_components(
        config, company_raw_payloads, capture_date
    )
    attempt_id = capture_attempt_id or uuid.uuid4().hex
    if capture_attempt_root is None:
        resolved_bundle_root = bundle_root.expanduser().resolve()
        if (
            resolved_bundle_root.parent.name != "pit_taxonomy_preopen_split_v2"
            or resolved_bundle_root.name != capture_date.isoformat()
        ):
            raise PITTaxonomySourceError(
                "split capture attempt requires the canonical dated v2 bundle root"
            )
        publication_root = resolved_bundle_root.parent.parent
        capture_attempt_root = (
            publication_root
            / "pit_taxonomy_capture_attempts"
            / capture_date.isoformat()
            / attempt_id
        )
    else:
        capture_attempt_root = capture_attempt_root.expanduser().resolve()
        if capture_attempt_root.name != attempt_id:
            raise PITTaxonomySourceError("capture attempt root does not match attempt id")
        if capture_attempt_root.parent.name != capture_date.isoformat():
            raise PITTaxonomySourceError("capture attempt root date does not match capture date")
        publication_root = capture_attempt_root.parent.parent.parent
    source_config_hash = _sha256_bytes(canonical_json(config).encode("utf-8"))
    attempt = _PITTaxonomyCaptureAttempt(
        publication_root=publication_root,
        capture_date=capture_date,
        attempt_id=attempt_id,
        started_at=request_started_at,
        scope_binding=scope_binding,
        universe_hash=universe_hash,
        clock_id=clock_id,
        clock_manifest_hash=clock_manifest_hash,
        source_config_hash=source_config_hash,
        planned_sources=plan,
        custody_now=(
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        ),
    )
    try:
        if len(plan) > PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
            raise PITTaxonomySourceError(
                "capture attempt source plan exceeds component-count limit"
            )
        result = _capture_configured_daily_pit_taxonomy_bundle_impl(
            config=config,
            bundle_root=bundle_root,
            capture_date=capture_date,
            decision_at=decision_at,
            now=now,
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
            universe_symbols_payload=universe_symbols_payload,
            scope_binding=scope_binding,
            fetch_source=fetch_source,
            now_provider=now_provider,
            attempt_writer=attempt,
        )
        attempt.finish_success(bundle_manifest_path=result.bundle_manifest_path)
        return replace(
            result,
            capture_attempt_id=attempt_id,
            capture_attempt_path=attempt.root,
            capture_attempt_result_path=attempt.result_path,
        )
    except Exception as error:
        try:
            attempt.finish_failure(error)
        except Exception as custody_error:  # noqa: BLE001 - preserve primary failure
            setattr(error, "capture_attempt_error", str(custody_error)[:300])
        setattr(
            error,
            "capture_attempt",
            {
                "attempt_id": attempt_id,
                "path": str(attempt.root),
                "result_path": str(attempt.result_path),
                "components_saved_count": len(attempt.components),
                "aggregate_raw_bytes": attempt.total_raw_bytes,
            },
        )
        raise


def _capture_configured_daily_pit_taxonomy_bundle_impl(
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
    scope_binding: Mapping[str, object] | None = None,
    fetch_source: Callable[[str], object] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    attempt_writer: _PITTaxonomyCaptureAttempt | None = None,
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
                attempt_writer=attempt_writer,
            )
            classification_component_payloads[market] = component_payloads
            classification_component_http[market] = component_http
        else:
            raw, http, fetched = _capture_configured_source(
                spec,
                source_name=f"classification:{market}",
                fetch_source=fetch_source,
                attempt_writer=attempt_writer,
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
            attempt_writer=attempt_writer,
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

    inactive_security_sources: dict[str, dict[str, object]] = {}
    if attempt_writer is not None:
        inactive_security_sources, inactive_live_fetch = (
            _capture_configured_inactive_security_sources(
                config=config,
                capture_date=capture_date,
                request_started_at=request_started_at,
                fetch_source=fetch_source,
                attempt_writer=attempt_writer,
            )
        )
        live_fetch_performed = live_fetch_performed or inactive_live_fetch

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
    capture_attempt_binding = (
        attempt_writer.seal_inputs() if attempt_writer is not None else None
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
        scope_binding=scope_binding,
        capture_started_at=request_started_at,
        capture_attempt_binding=capture_attempt_binding,
        inactive_security_sources=inactive_security_sources,
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
    except HTTPError as error:
        # HTTPError is itself a response: retain its bounded body and headers in
        # split-attempt custody before the status validator rejects it.
        body = error.read(PIT_TAXONOMY_MAX_SOURCE_BYTES + 1)
        completed_at = datetime.now(timezone.utc)
        final_url = error.geturl()
        status = error.code
        headers = error.headers
    except Exception as error:  # noqa: BLE001 - transport boundary is fail closed
        raise PITTaxonomySourceError(
            f"official PIT taxonomy source fetch failed: {endpoint}"
        ) from error
    metadata: dict[str, object] = {
        "requested_url": endpoint,
        "final_url": str(final_url),
        "http_status": status,
        "content_type": str(headers.get("Content-Type") or "application/octet-stream"),
        "http_date": headers.get("Date"),
        "http_last_modified": headers.get("Last-Modified"),
        "captured_at": completed_at.isoformat(),
        "body_bytes_seen": len(body),
        "body_truncated": len(body) > PIT_TAXONOMY_MAX_SOURCE_BYTES,
    }
    return PITTaxonomySourceResponse(body=body, metadata=metadata)


def _capture_configured_source(
    spec: Mapping[str, object],
    *,
    source_name: str,
    fetch_source: Callable[[str], object] | None,
    attempt_writer: _PITTaxonomyCaptureAttempt | None = None,
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
        configured_path = Path(str(path_value)).expanduser()
        if attempt_writer is not None:
            # The split/custody path must reject links before resolution and
            # bound the read itself; checking the size after read_bytes could
            # allocate an arbitrarily large local source into memory.
            _assert_no_link_path(configured_path, allow_missing=False)
            try:
                raw_path = configured_path.resolve(strict=True)
            except OSError as error:
                raise PITTaxonomySourceError(
                    f"{source_name} saved source path is unreadable"
                ) from error
            raw = _proof_file_bytes(
                raw_path,
                f"{source_name} saved source",
                PIT_TAXONOMY_MAX_SOURCE_BYTES,
            )
        else:
            # Preserve the legacy v1 saved-source behavior and payload shape.
            raw_path = configured_path.resolve()
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
        if attempt_writer is not None:
            attempt_writer.record_component(
                source_name, raw, metadata, fetched=fetched
            )
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
        metadata_is_valid = isinstance(metadata_value, Mapping)
        metadata = (
            {str(key): item for key, item in metadata_value.items()}
            if isinstance(metadata_value, Mapping)
            else {}
        )
        if attempt_writer is not None:
            attempt_writer.record_component(
                source_name,
                raw,
                metadata if metadata_is_valid else None,
                fetched=True,
            )
        if not metadata_is_valid:
            raise PITTaxonomySourceError(
                f"{source_name} fetcher returned invalid metadata"
            )
        if metadata.get("requested_url") != endpoint:
            raise PITTaxonomySourceError(
                f"{source_name} requested URL differs from configured URL"
            )
        fetched = True
    raw = _require_bytes(raw, f"{source_name}.body")
    if len(raw) > PIT_TAXONOMY_MAX_SOURCE_BYTES:
        raise PITTaxonomySourceError(f"{source_name} exceeds bounded source bytes")
    if not raw:
        raise PITTaxonomySourceError(f"{source_name} response body is empty")
    _component_available(metadata, source_name)
    return raw, metadata, fetched


def _capture_configured_inactive_security_sources(
    *,
    config: Mapping[str, object],
    capture_date: date,
    request_started_at: datetime,
    fetch_source: Callable[[str], object] | None,
    attempt_writer: _PITTaxonomyCaptureAttempt,
) -> tuple[dict[str, dict[str, object]], bool]:
    configured = config.get("inactive_security", {})
    if not isinstance(configured, Mapping):
        raise PITTaxonomySourceError("PIT taxonomy inactive_security section is invalid")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    inputs: dict[str, dict[str, object]] = {}
    live_fetch_performed = False
    for key, raw_spec in sorted(configured.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_spec, Mapping):
            raise PITTaxonomySourceError(
                f"inactive security source config is invalid: {key}"
            )
        source_version = _required_text(
            raw_spec.get("source_version"), f"inactive_security.{key}.source_version"
        )
        source_url = _required_text(
            raw_spec.get("source_url"), f"inactive_security.{key}.source_url"
        )
        spec = _inactive_termination_spec(raw_spec, f"inactive_security.{key}")
        if spec.termination_effective_on > capture_date:
            continue
        if spec.symbol in inputs:
            raise PITTaxonomySourceError(
                f"inactive security source duplicates symbol: {spec.symbol}"
            )
        source_name = f"inactive_security:{str(key)}"
        saved_value = raw_spec.get("saved_evidence")
        capture_metadata_source_name: str | None = None

        if saved_value is not None:
            if not isinstance(saved_value, Mapping) or set(saved_value) != {
                "raw_path",
                "metadata_path",
            }:
                raise PITTaxonomySourceError(
                    f"{source_name}.saved_evidence fields are invalid"
                )
            raw_source_path, metadata_source_path, raw, metadata_raw = (
                _read_saved_inactive_security_evidence(saved_value)
            )
            origin_metadata = _decode_json_object_no_duplicates(
                metadata_raw, f"{source_name} saved HTTP metadata"
            )
            capture_at = _validate_saved_inactive_security_http_metadata(
                origin_metadata,
                raw=raw,
                spec=spec,
                raw_path=raw_source_path,
                metadata_path=metadata_source_path,
            )
            capture_metadata_source_name = f"{source_name}:capture_metadata"
            attempt_metadata: dict[str, object] = {
                "request_url": source_url,
                "requested_url": source_url,
                "final_url": source_url,
                "status_code": 200,
                "http_status": 200,
                "content_type": str(origin_metadata["content_type"]),
                "charset": origin_metadata.get("charset"),
                "captured_at": capture_at.isoformat(),
                "raw_sha256": _sha256_bytes(raw),
                "raw_bytes": len(raw),
                "body_bytes_seen": len(raw),
                "body_truncated": False,
                "upstream_http_metadata": origin_metadata,
                "source_capture_metadata_sha256": _sha256_bytes(metadata_raw),
                "source_capture_metadata_bytes": len(metadata_raw),
                "source_capture_metadata_source_name": capture_metadata_source_name,
                "source_capture_raw_path": str(raw_source_path),
                "source_capture_metadata_path": str(metadata_source_path),
            }
            capture_http = {
                "requested_url": source_url,
                "final_url": source_url,
                "http_status": 200,
                "content_type": "application/json",
                "captured_at": capture_at.isoformat(),
                "metadata_role": "source_http_capture_metadata",
                "source_metadata_sha256": _sha256_bytes(metadata_raw),
            }
            attempt_writer.record_component(
                source_name,
                raw,
                attempt_metadata,
                fetched=False,
            )
            attempt_writer.record_component(
                capture_metadata_source_name,
                metadata_raw,
                capture_http,
                fetched=False,
            )
            fetched = False
        else:
            response = (
                fetch_source(source_url)
                if fetch_source is not None
                else fetch_official_pit_taxonomy_source(source_url)
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
            if not isinstance(body_value, bytes) or not body_value:
                raise PITTaxonomySourceError(
                    f"{source_name} fetcher returned an invalid body"
                )
            response_metadata = (
                {str(name): value for name, value in metadata_value.items()}
                if isinstance(metadata_value, Mapping)
                else None
            )
            if response_metadata is None:
                attempt_writer.record_component(
                    source_name,
                    body_value,
                    None,
                    fetched=True,
                )
                raise PITTaxonomySourceError(
                    f"{source_name} fetcher returned invalid metadata"
                )
            captured = response_metadata.get(
                "captured_at", response_metadata.get("completed_at")
            )
            attempt_metadata = {
                **response_metadata,
                "request_url": response_metadata.get(
                    "requested_url", response_metadata.get("request_url")
                ),
                "status_code": response_metadata.get(
                    "http_status", response_metadata.get("status_code")
                ),
                "captured_at": captured,
                "raw_sha256": _sha256_bytes(body_value),
                "raw_bytes": len(body_value),
                "body_bytes_seen": response_metadata.get(
                    "body_bytes_seen", len(body_value)
                ),
                "body_truncated": response_metadata.get("body_truncated") is True,
                "upstream_http_metadata": response_metadata,
            }
            attempt_writer.record_component(
                source_name,
                body_value,
                attempt_metadata,
                fetched=True,
            )
            if attempt_metadata["request_url"] != source_url:
                raise PITTaxonomySourceError(
                    f"{source_name} requested URL differs from configured URL"
                )
            if not isinstance(captured, str):
                raise PITTaxonomySourceError(
                    f"{source_name} captured-at time is missing"
                )
            capture_at = _aware(captured, f"{source_name}.captured_at")
            fetched = True
            live_fetch_performed = True

        if capture_at >= cutoff:
            raise PITTaxonomySourceError(
                f"{source_name} source capture is at/after Taipei 08:30"
            )
        if fetched and capture_at < request_started_at:
            raise PITTaxonomySourceError(
                f"{source_name} completion predates request start"
            )
        inputs[spec.symbol] = {
            "source_version": source_version,
            "spec": _inactive_spec_payload(spec),
            "attempt_source_name": source_name,
            "capture_metadata_source_name": capture_metadata_source_name,
        }
    return inputs, live_fetch_performed


def _read_saved_inactive_security_evidence(
    saved_evidence: Mapping[str, object],
) -> tuple[Path, Path, bytes, bytes]:
    repo_root = Path(__file__).resolve().parent.parent
    qa_root = repo_root / "output" / "qa"
    paths: list[Path] = []
    for field_name in ("raw_path", "metadata_path"):
        value = saved_evidence.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise PITTaxonomySourceError(
                f"inactive saved evidence {field_name} is missing"
            )
        candidate = Path(os.path.abspath(str(Path(value).expanduser())))
        _assert_no_link_path(candidate, allow_missing=False, confine_to=qa_root)
        try:
            candidate.resolve(strict=True).relative_to(qa_root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise PITTaxonomySourceError(
                "inactive saved evidence must remain under repository output/qa"
            ) from error
        paths.append(candidate)
    raw_path, metadata_path = paths
    if raw_path.parent != metadata_path.parent or metadata_path.name != "metadata.json":
        raise PITTaxonomySourceError(
            "inactive saved evidence raw and metadata must be sibling capture files"
        )
    raw = _proof_file_bytes(
        raw_path,
        "inactive termination notice raw",
        PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES,
    )
    metadata_raw = _proof_file_bytes(
        metadata_path, "inactive termination notice HTTP metadata", 1024 * 1024
    )
    return raw_path, metadata_path, raw, metadata_raw


def _validate_saved_inactive_security_http_metadata(
    metadata: Mapping[str, object],
    *,
    raw: bytes,
    spec: OfficialTerminationSourceSpec,
    raw_path: Path,
    metadata_path: Path,
) -> datetime:
    if (
        metadata.get("schema_version") != "pit-8183-bounded-http-diagnostic.v1"
        or metadata.get("method") != "GET"
        or metadata.get("request_url") != spec.source_url
        or metadata.get("final_url") != spec.source_url
        or metadata.get("redirects_followed") is not False
        or metadata.get("status_code") != 200
        or metadata.get("content_type") != "text/html"
        or metadata.get("body_complete") is not True
        or metadata.get("body_kind") != "official_announcement_candidate"
        or metadata.get("body_file") != raw_path.name
        or metadata.get("error") is not None
        or metadata.get("body_bytes") != len(raw)
        or metadata.get("body_sha256") != _sha256_bytes(raw)
        or metadata_path.parent != raw_path.parent
    ):
        raise PITTaxonomySourceError(
            "saved inactive termination source HTTP metadata is invalid"
        )
    completed = metadata.get("completed_at")
    if not isinstance(completed, str):
        raise PITTaxonomySourceError(
            "saved inactive termination capture time is missing"
        )
    try:
        return _aware(completed, "inactive_security.completed_at")
    except (TypeError, ValueError) as error:
        raise PITTaxonomySourceError(
            "saved inactive termination capture time is invalid"
        ) from error


def _inactive_termination_spec(
    value: Mapping[str, object], field_name: str
) -> OfficialTerminationSourceSpec:
    try:
        return OfficialTerminationSourceSpec(
            source_url=_required_text(value.get("source_url"), f"{field_name}.source_url"),
            symbol=_required_text(value.get("symbol"), f"{field_name}.symbol"),
            issuer_name=_required_text(
                value.get("issuer_name"), f"{field_name}.issuer_name"
            ),
            market_scope=_required_text(
                value.get("market_scope"), f"{field_name}.market_scope"
            ),
            published_on=_required_date(
                value.get("published_on"), f"{field_name}.published_on"
            ),
            suspension_effective_on=_required_date(
                value.get("suspension_effective_on"),
                f"{field_name}.suspension_effective_on",
            ),
            termination_effective_on=_required_date(
                value.get("termination_effective_on"),
                f"{field_name}.termination_effective_on",
            ),
        )
    except (InactiveTerminationEvidenceError, ValueError, TypeError) as error:
        raise PITTaxonomySourceError(
            f"inactive security source specification is invalid: {field_name}"
        ) from error


def _inactive_spec_payload(spec: OfficialTerminationSourceSpec) -> dict[str, object]:
    return {
        "source_url": spec.source_url,
        "symbol": spec.symbol,
        "issuer_name": spec.issuer_name,
        "market_scope": spec.market_scope,
        "published_on": spec.published_on.isoformat(),
        "suspension_effective_on": spec.suspension_effective_on.isoformat(),
        "termination_effective_on": spec.termination_effective_on.isoformat(),
    }


def _inactive_overlay_entry_from_attempt(
    symbol: str,
    entry: Mapping[str, object],
    *,
    capture_attempt_binding: Mapping[str, object],
    publication_root: Path,
    capture_date: date,
) -> dict[str, object]:
    allowed_input_keys = {
        "schema_version",
        "source_version",
        "spec",
        "attempt_source_name",
        "capture_metadata_source_name",
        "proof",
        "attempt_component",
        "capture_metadata_component",
    }
    if set(entry) - allowed_input_keys:
        raise PITTaxonomySourceError(
            f"inactive overlay contains unsupported binding fields: {symbol}"
        )
    if entry.get("schema_version") not in {
        None,
        "pit-inactive-security-overlay-binding.v1",
    }:
        raise PITTaxonomySourceError(
            f"inactive overlay schema is unsupported: {symbol}"
        )
    if entry.get("source_version") is None:
        raise PITTaxonomySourceError(
            f"inactive overlay source version is missing: {symbol}"
        )
    source_version = _required_text(
        entry.get("source_version"), f"inactive_security_overlay.{symbol}.source_version"
    )
    spec_value = entry.get("spec")
    if not isinstance(spec_value, Mapping):
        raise PITTaxonomySourceError(
            f"inactive overlay source specification is missing: {symbol}"
        )
    spec = _inactive_termination_spec(spec_value, f"inactive_security_overlay.{symbol}.spec")
    if spec.symbol != symbol or spec.termination_effective_on > capture_date:
        raise PITTaxonomySourceError(
            f"inactive overlay symbol or effective date is invalid: {symbol}"
        )
    source_name = _required_text(
        entry.get("attempt_source_name"),
        f"inactive_security_overlay.{symbol}.attempt_source_name",
    )
    metadata_source_value = entry.get("capture_metadata_source_name")
    metadata_source_name = (
        _required_text(
            metadata_source_value,
            f"inactive_security_overlay.{symbol}.capture_metadata_source_name",
        )
        if metadata_source_value is not None
        else None
    )

    binding = _capture_attempt_binding_fields(capture_attempt_binding)
    attempt_root = _proof_child(
        publication_root,
        binding.get("path"),
        required_prefix="pit_taxonomy_capture_attempts/",
        label="inactive overlay capture attempt",
    )
    attempt_readback = read_pit_taxonomy_capture_attempt(attempt_root)
    if (
        attempt_readback.get("attempt_id") != binding.get("attempt_id")
        or attempt_readback.get("receipt_sha256") != binding.get("receipt_sha256")
    ):
        raise PITTaxonomySourceError(
            f"inactive overlay attempt receipt differs: {symbol}"
        )
    components_value = attempt_readback.get("components")
    if not isinstance(components_value, list):
        raise PITTaxonomySourceError(
            f"inactive overlay attempt components are invalid: {symbol}"
        )
    components = [
        item
        for item in components_value
        if isinstance(item, Mapping)
    ]
    source_components = [
        item for item in components if item.get("source_name") == source_name
    ]
    if len(source_components) != 1:
        raise PITTaxonomySourceError(
            f"inactive overlay source component is missing or ambiguous: {symbol}"
        )
    source_component = dict(source_components[0])
    if source_component.get("fetched") not in {True, False}:
        raise PITTaxonomySourceError(
            f"inactive overlay source fetch state is invalid: {symbol}"
        )
    raw_path = _proof_child(
        attempt_root,
        source_component.get("raw_path"),
        required_prefix="components/",
        label="inactive overlay raw component",
    )
    raw = _proof_file_bytes(
        raw_path, "inactive overlay raw component", PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES
    )
    if (
        _sha256_bytes(raw) != source_component.get("raw_sha256")
        or len(raw) != source_component.get("raw_bytes")
    ):
        raise PITTaxonomySourceError(
            f"inactive overlay raw component pin differs: {symbol}"
        )
    source_http_value = source_component.get("http_metadata")
    if not isinstance(source_http_value, Mapping):
        raise PITTaxonomySourceError(
            f"inactive overlay HTTP metadata is missing: {symbol}"
        )
    source_http = dict(source_http_value)
    parser_metadata = {
        "request_url": source_http.get("request_url"),
        "final_url": source_http.get("final_url"),
        "status_code": source_http.get("status_code"),
        "content_type": source_http.get("content_type"),
        "charset": source_http.get("charset"),
        "captured_at": source_http.get("captured_at"),
        "raw_sha256": source_component.get("raw_sha256"),
        "raw_bytes": source_component.get("raw_bytes"),
        "raw_path": source_component.get("raw_path"),
    }
    origin_metadata_value = source_http.get("upstream_http_metadata")
    if not isinstance(origin_metadata_value, Mapping):
        raise PITTaxonomySourceError(
            f"inactive overlay upstream HTTP metadata is missing: {symbol}"
        )
    origin_metadata = dict(origin_metadata_value)

    metadata_component: dict[str, object] | None = None
    if metadata_source_name is not None:
        metadata_components = [
            item
            for item in components
            if item.get("source_name") == metadata_source_name
        ]
        if len(metadata_components) != 1:
            raise PITTaxonomySourceError(
                f"inactive overlay capture metadata component is missing: {symbol}"
            )
        metadata_component = dict(metadata_components[0])
        metadata_raw_path = _proof_child(
            attempt_root,
            metadata_component.get("raw_path"),
            required_prefix="components/",
            label="inactive overlay capture metadata component",
        )
        metadata_raw = _proof_file_bytes(
            metadata_raw_path,
            "inactive overlay capture metadata component",
            1024 * 1024,
        )
        if (
            _sha256_bytes(metadata_raw) != metadata_component.get("raw_sha256")
            or len(metadata_raw) != metadata_component.get("raw_bytes")
            or _sha256_bytes(metadata_raw)
            != source_http.get("source_capture_metadata_sha256")
            or len(metadata_raw) != source_http.get("source_capture_metadata_bytes")
        ):
            raise PITTaxonomySourceError(
                f"inactive overlay capture metadata pin differs: {symbol}"
            )
        origin_metadata = _decode_json_object_no_duplicates(
            metadata_raw, f"inactive overlay saved HTTP metadata {symbol}"
        )
        _validate_saved_inactive_security_http_metadata(
            origin_metadata,
            raw=raw,
            spec=spec,
            raw_path=Path(str(source_http.get("source_capture_raw_path"))),
            metadata_path=Path(str(source_http.get("source_capture_metadata_path"))),
        )
    elif source_http.get("source_capture_metadata_sha256") is not None:
        raise PITTaxonomySourceError(
            f"inactive overlay capture metadata binding has no component: {symbol}"
        )

    actual_capture_at = _aware(
        parser_metadata.get("captured_at"),
        f"inactive_security_overlay.{symbol}.captured_at",
    )
    real_cutoff = datetime.combine(
        capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI
    )
    serialized_proof_value = entry.get("proof")
    try:
        if serialized_proof_value is None:
            proof = parse_official_termination_notice(
                raw,
                parser_metadata,
                spec,
                actual_capture_at,
                real_cutoff,
            )
        elif isinstance(serialized_proof_value, Mapping):
            proof = validate_official_termination_proof_readback(
                raw,
                parser_metadata,
                spec,
                actual_capture_at,
                real_cutoff,
                serialized_proof_value,
            )
        else:
            raise PITTaxonomySourceError(
                f"inactive overlay serialized proof is invalid: {symbol}"
            )
    except InactiveTerminationEvidenceError as error:
        raise PITTaxonomySourceError(
            f"inactive overlay proof verification failed: {symbol}"
        ) from error

    expected_source_component = {
        "source_name": source_name,
        "fetched": source_component.get("fetched"),
        "raw_path": source_component.get("raw_path"),
        "raw_sha256": source_component.get("raw_sha256"),
        "raw_bytes": source_component.get("raw_bytes"),
        "metadata_path": source_component.get("metadata_path"),
        "metadata_sha256": source_component.get("metadata_sha256"),
    }
    expected_metadata_component = (
        {
            "source_name": metadata_source_name,
            "fetched": metadata_component.get("fetched"),
            "raw_path": metadata_component.get("raw_path"),
            "raw_sha256": metadata_component.get("raw_sha256"),
            "raw_bytes": metadata_component.get("raw_bytes"),
            "metadata_path": metadata_component.get("metadata_path"),
            "metadata_sha256": metadata_component.get("metadata_sha256"),
        }
        if metadata_component is not None
        else None
    )
    for field_name, observed in (
        ("attempt_component", expected_source_component),
        ("capture_metadata_component", expected_metadata_component),
    ):
        if field_name in entry and entry.get(field_name) != observed:
            raise PITTaxonomySourceError(
                f"inactive overlay {field_name} pin differs: {symbol}"
            )
    return {
        "schema_version": "pit-inactive-security-overlay-binding.v1",
        "source_version": source_version,
        "spec": _inactive_spec_payload(spec),
        "proof": proof.to_dict(),
        "attempt_source_name": source_name,
        "capture_metadata_source_name": metadata_source_name,
        "attempt_component": expected_source_component,
        "capture_metadata_component": expected_metadata_component,
    }


def _verified_inactive_overlay_map(
    configured: Mapping[str, Mapping[str, object]] | None,
    *,
    capture_attempt_binding: Mapping[str, object],
    publication_root: Path,
    capture_date: date,
    expected_symbols: Sequence[str],
    market_by_symbol: Mapping[str, str],
    security_records: Sequence[OfficialSecurityRecord],
) -> dict[str, dict[str, object]]:
    if not configured:
        return {}
    expected = set(expected_symbols)
    active_record_symbols = {item.symbol for item in security_records}
    verified: dict[str, dict[str, object]] = {}
    for symbol, entry in sorted(configured.items()):
        normalized_symbol = _normalize_symbols((symbol,), "inactive_security_overlay.symbol")[0]
        if normalized_symbol not in expected:
            raise PITTaxonomySourceError(
                f"inactive security proof symbol is outside the official denominator: {normalized_symbol}"
            )
        if normalized_symbol in verified:
            raise PITTaxonomySourceError(
                f"inactive security proof symbol is duplicated: {normalized_symbol}"
            )
        checked = _inactive_overlay_entry_from_attempt(
            normalized_symbol,
            entry,
            capture_attempt_binding=capture_attempt_binding,
            publication_root=publication_root,
            capture_date=capture_date,
        )
        proof = checked.get("proof")
        if not isinstance(proof, Mapping):
            raise PITTaxonomySourceError(
                f"inactive security proof readback is missing: {normalized_symbol}"
            )
        if proof.get("symbol") != normalized_symbol:
            raise PITTaxonomySourceError(
                f"inactive security proof symbol differs: {normalized_symbol}"
            )
        if proof.get("market_scope") != market_by_symbol.get(normalized_symbol):
            raise PITTaxonomySourceError(
                f"inactive security proof market differs from official denominator: {normalized_symbol}"
            )
        if normalized_symbol in active_record_symbols:
            raise PITTaxonomySourceError(
                f"inactive security overlay conflicts with active ISIN row: {normalized_symbol}"
            )
        verified[normalized_symbol] = checked
    return verified


def _validate_bundle_inactive_security_overlay(
    overlay_value: object,
    *,
    capture_attempt_binding: Mapping[str, object],
    publication_root: Path,
    capture_date: date,
    bundle_root: Path,
    raw_files: Sequence[Mapping[str, object]],
    symbols: Sequence[str],
    market_by_symbol: Mapping[str, str],
    security_type_by_symbol: Mapping[str, str],
    security_eligibility_by_symbol: Mapping[str, Mapping[str, object]],
    eligible_symbols: Sequence[str],
    excluded_symbols: Sequence[str],
    unknown_symbols: Sequence[str],
) -> dict[str, dict[str, object]]:
    if not isinstance(overlay_value, Mapping):
        raise PITTaxonomySourceError("inactive security overlay map is invalid")
    overlay_inputs: dict[str, Mapping[str, object]] = {}
    for symbol, entry in overlay_value.items():
        if not isinstance(symbol, str) or not isinstance(entry, Mapping):
            raise PITTaxonomySourceError("inactive security overlay entry is invalid")
        overlay_inputs[symbol] = entry

    security_records: list[OfficialSecurityRecord] = []
    seen_hashes: set[str] = set()
    for raw_entry in raw_files:
        if raw_entry.get("role") != "security_typing":
            continue
        raw_path = _resolve_relative(bundle_root, raw_entry.get("path"))
        market = str(raw_entry.get("market_scope") or "")
        try:
            records = parse_official_isin_security_source(
                _proof_file_bytes(
                    raw_path,
                    "official security raw component",
                    PIT_TAXONOMY_MAX_SOURCE_BYTES,
                ),
                default_market_scope=(None if market == "all" else market),
            )
        except (OfficialSecurityTypingError, ValueError) as error:
            raise PITTaxonomySourceError(
                "official security raw component cannot be re-parsed"
            ) from error
        for record in records:
            if record.row_hash not in seen_hashes:
                security_records.append(record)
                seen_hashes.add(record.row_hash)

    verified_overlay = _verified_inactive_overlay_map(
        overlay_inputs,
        capture_attempt_binding=capture_attempt_binding,
        publication_root=publication_root,
        capture_date=capture_date,
        expected_symbols=symbols,
        market_by_symbol=market_by_symbol,
        security_records=security_records,
    )
    for symbol, overlay in verified_overlay.items():
        proof = cast(Mapping[str, object], overlay["proof"])
        raw_hash = proof.get("source_raw_sha256")
        matches = [
            item
            for item in raw_files
            if item.get("role") == "security_inactive_termination"
            and item.get("source_id") == f"official:tpex:termination:{symbol}"
        ]
        if len(matches) != 1 or matches[0].get("source_file_hash") != raw_hash:
            raise PITTaxonomySourceError(
                f"inactive proof raw manifest binding differs: {symbol}"
            )
        copy_path = _resolve_relative(bundle_root, matches[0].get("path"))
        copied_raw = _proof_file_bytes(
            copy_path,
            "inactive termination notice bundle raw",
            PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES,
        )
        if (
            _sha256_bytes(copied_raw) != raw_hash
            or len(copied_raw) != proof.get("source_raw_bytes")
        ):
            raise PITTaxonomySourceError(
                f"inactive proof bundle raw differs from attempt custody: {symbol}"
            )

    expected = set(symbols)
    inactive_symbols = set(verified_overlay)
    active_expected = tuple(sorted(expected - inactive_symbols))
    if active_expected:
        try:
            expected_types, expected_eligibility, _selected = build_security_evidence_map(
                security_records,
                expected_symbols=active_expected,
                market_by_symbol={
                    symbol: market_by_symbol[symbol] for symbol in active_expected
                },
            )
        except OfficialSecurityTypingError as error:
            raise PITTaxonomySourceError(
                "active official security map has missing, unknown, or conflicting rows"
            ) from error
    else:
        expected_types, expected_eligibility = {}, {}
    for symbol, overlay in verified_overlay.items():
        proof = cast(Mapping[str, object], overlay["proof"])
        expected_types[symbol] = "inactive_common_stock"
        expected_eligibility[symbol] = {
            "eligible": False,
            "reason": "official_security_termination_inactive_research_only",
            "security_type": "inactive_common_stock",
            "market_scope": market_by_symbol[symbol],
            "state": proof.get("state"),
            "proof_sha256": _sha256_json(dict(proof)),
        }
    if dict(security_type_by_symbol) != expected_types:
        raise PITTaxonomySourceError("inactive/active security type map differs from source bytes")
    if dict(security_eligibility_by_symbol) != expected_eligibility:
        raise PITTaxonomySourceError("inactive/active security eligibility map differs from source bytes")
    if set(eligible_symbols) != {
        symbol for symbol, item in expected_eligibility.items() if item.get("eligible") is True
    }:
        raise PITTaxonomySourceError("inactive overlay eligible projection differs")
    if set(excluded_symbols) != {
        symbol for symbol, item in expected_eligibility.items() if item.get("eligible") is False
    }:
        raise PITTaxonomySourceError("inactive overlay excluded projection differs")
    if unknown_symbols:
        raise PITTaxonomySourceError("inactive overlay cannot suppress unknown security symbols")
    return verified_overlay


def _decode_json_object_no_duplicates(raw: bytes, label: str) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise PITTaxonomySourceError(f"{label} JSON is invalid") from error
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{label} is not an object")
    return {str(key): item for key, item in value.items()}


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
    attempt_writer: _PITTaxonomyCaptureAttempt | None = None,
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
            attempt_writer=attempt_writer,
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
    scope_binding: Mapping[str, object] | None = None,
    capture_attempt_binding: Mapping[str, object] | None = None,
    inactive_security_sources: Mapping[str, Mapping[str, object]] | None = None,
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
    split_contract = scope_binding is not None
    binding_fields = _split_scope_binding_fields(scope_binding) if split_contract else {}
    if split_contract:
        if not isinstance(capture_attempt_binding, Mapping):
            raise PITTaxonomySourceError(
                "split candidate requires verified capture-attempt custody"
            )
        capture_attempt_fields = _capture_attempt_binding_fields(
            capture_attempt_binding
        )
    else:
        if capture_attempt_binding is not None:
            raise PITTaxonomySourceError(
                "legacy v1 bundle cannot carry split capture-attempt custody"
            )
        capture_attempt_fields = {}
    if not split_contract and set(expected) != set(hash_symbols):
        raise PITTaxonomySourceError(
            "full universe symbols and universe_hash_symbols must have the same set"
        )
    scores = _normalize_scores(scores_bp, len(hash_symbols))
    supplied_rank = _normalize_symbols(rank_order, "rank_order")
    expected_rank_set = set(hash_symbols) if split_contract else set(expected)
    if set(supplied_rank) != expected_rank_set:
        raise PITTaxonomySourceError(
            "rank_order must cover the Rule candidate set exactly"
            if split_contract
            else "rank_order must cover the full denominator exactly"
        )
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
    if split_contract:
        _validate_split_scope_binding_claims(
            binding_fields,
            denominator_symbols=expected,
            candidate_symbols=hash_symbols,
            universe_hash=universe_hash,
            capture_date=capture_date,
            decision_at=decision,
        )
        _verify_split_scope_binding(
            {
                **binding_fields,
                "symbols": list(expected),
                "universe_hash_symbols": list(hash_symbols),
                "universe_hash": universe_hash,
                "clock_id": clock_id,
                "clock_manifest_hash": clock_manifest_hash,
                "rank_order": list(supplied_rank),
                "capture_started_at": started.isoformat(),
            },
            bundle_manifest_path=(
                bundle_root.expanduser().resolve() / "bundle_manifest.json"
            ),
            capture_date=capture_date,
            decision_at=decision,
            observed_at=observed,
        )
        _verify_capture_attempt_binding(
            capture_attempt_fields,
            publication_root=bundle_root.expanduser().resolve().parent.parent,
            capture_date=capture_date,
            capture_started_at=started,
            decision_at=decision,
            universe_hash=universe_hash,
            clock_id=clock_id,
            clock_manifest_hash=clock_manifest_hash,
            scope_binding=binding_fields,
            expected_bundle_hash=None,
            require_success=False,
        )
        _validate_universe_identity(
            universe_identity_payload,
            expected=tuple(sorted(hash_symbols)),
            hash_symbols=hash_symbols,
            scores=scores,
            universe_hash=universe_hash,
        )
    else:
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
    configured_inactive = inactive_security_sources or {}
    if configured_inactive and not split_contract:
        raise PITTaxonomySourceError(
            "inactive security overlay is supported only by split research candidates"
        )
    inactive_overlay_by_symbol = _verified_inactive_overlay_map(
        configured_inactive,
        capture_attempt_binding=capture_attempt_fields,
        publication_root=bundle_root.expanduser().resolve().parent.parent,
        capture_date=capture_date,
        expected_symbols=expected,
        market_by_symbol=market_by_symbol,
        security_records=security_records,
    )
    active_expected = tuple(
        symbol for symbol in expected if symbol not in inactive_overlay_by_symbol
    )
    if active_expected:
        try:
            security_types, eligibility, selected_security = build_security_evidence_map(
                security_records,
                expected_symbols=active_expected,
                market_by_symbol={
                    symbol: market_by_symbol[symbol] for symbol in active_expected
                },
            )
        except OfficialSecurityTypingError as error:
            raise PITTaxonomySourceError(str(error)) from error
    else:
        security_types, eligibility, selected_security = {}, {}, {}
    for symbol, overlay in inactive_overlay_by_symbol.items():
        proof = overlay["proof"]
        if not isinstance(proof, Mapping):
            raise PITTaxonomySourceError(
                f"inactive security proof is invalid: {symbol}"
            )
        proof_hash = _sha256_json(dict(proof))
        security_types[symbol] = "inactive_common_stock"
        eligibility[symbol] = {
            "eligible": False,
            "reason": "official_security_termination_inactive_research_only",
            "security_type": "inactive_common_stock",
            "market_scope": market_by_symbol[symbol],
            "state": proof.get("state"),
            "proof_sha256": proof_hash,
        }
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
    inactive_completion: list[datetime] = []
    if inactive_overlay_by_symbol:
        publication_root = bundle_root.expanduser().resolve().parent.parent
        attempt_root = _proof_child(
            publication_root,
            capture_attempt_fields.get("path"),
            required_prefix="pit_taxonomy_capture_attempts/",
            label="inactive overlay capture attempt",
        )
        for symbol, overlay in sorted(inactive_overlay_by_symbol.items()):
            proof = cast(Mapping[str, object], overlay["proof"])
            component = cast(Mapping[str, object], overlay["attempt_component"])
            attempt_raw_path = _proof_child(
                attempt_root,
                component.get("raw_path"),
                required_prefix="components/",
                label="inactive overlay attempt raw",
            )
            raw = _proof_file_bytes(
                attempt_raw_path,
                "inactive overlay attempt raw",
                PIT_INACTIVE_TERMINATION_MAX_SOURCE_BYTES,
            )
            if _sha256_bytes(raw) != proof.get("source_raw_sha256"):
                raise PITTaxonomySourceError(
                    f"inactive overlay raw hash differs before bundle write: {symbol}"
                )
            relative = Path("raw") / f"inactive_security_{symbol}_termination_notice.html"
            _write_create_only_bytes(root / relative, raw)
            available_at = _aware(
                proof.get("captured_at"), f"inactive_security_overlay.{symbol}.captured_at"
            )
            spec = _inactive_termination_spec(
                cast(Mapping[str, object], overlay["spec"]),
                f"inactive_security_overlay.{symbol}.spec",
            )
            inactive_completion.append(available_at)
            raw_files.append(
                _raw_entry(
                    role="security_inactive_termination",
                    market_scope=spec.market_scope,
                    source_id=f"official:tpex:termination:{symbol}",
                    source_version=overlay["source_version"],
                    path=relative,
                    raw_payload=raw,
                    http={
                        "requested_url": proof.get("source_url"),
                        "final_url": proof.get("source_url"),
                        "http_status": proof.get("response_status"),
                        "content_type": proof.get("content_type"),
                        "captured_at": available_at.isoformat(),
                    },
                    available_at=available_at,
                    effective_from=spec.termination_effective_on,
                    parser_version=str(proof.get("schema_version")),
                    source_kind="official_inactive_common_stock_termination_research",
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
        [
            *company_completion.values(),
            *classification_completion.values(),
            *security_completion.values(),
            *inactive_completion,
        ]
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
        "schema_version": (
            PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION
            if split_contract
            else PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION
        ),
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
    if split_contract:
        source_body.update(binding_fields)
        source_body["capture_attempt_binding"] = capture_attempt_fields
        source_body[PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD] = inactive_overlay_by_symbol
    taxonomy_source_path = metadata_root / "taxonomy_source.json"
    _write_create_only_json(taxonomy_source_path, source_body)
    taxonomy_source_hash = _file_sha256(taxonomy_source_path)
    identity_body: dict[str, object] = {
        "schema_version": (
            PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION
            if split_contract
            else PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION
        ),
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
    if split_contract:
        identity_body.update(binding_fields)
        identity_body["capture_attempt_binding"] = capture_attempt_fields
        identity_body[PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD] = inactive_overlay_by_symbol
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
        "schema_version": (
            PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION
            if split_contract
            else PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION
        ),
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
    if split_contract:
        bundle_body.update(binding_fields)
        bundle_body["capture_attempt_binding"] = capture_attempt_fields
        bundle_body[PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD] = inactive_overlay_by_symbol
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
        schema_version=(
            PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION
            if split_contract
            else PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION
        ),
    )


def validate_daily_pit_taxonomy_bundle(
    bundle_manifest_path: Path,
    *,
    decision_at: datetime,
    now: datetime | None = None,
) -> dict[str, object]:
    """postcutoff 只讀驗證 bundle envelope、hash、raw component 與 cutoff。"""

    raw_path = Path(os.path.abspath(str(bundle_manifest_path.expanduser())))
    _assert_no_link_path(raw_path, allow_missing=False)
    path = raw_path.resolve()
    payload = _read_json_object(path, "taxonomy bundle manifest")
    bundle_hash = _require_sha256(payload.get("bundle_hash"), "bundle_hash")
    body = dict(payload)
    body.pop("bundle_hash", None)
    if _sha256_json(body) != bundle_hash:
        raise PITTaxonomySourceError("taxonomy bundle hash mismatch")
    bundle_schema = payload.get("schema_version")
    if bundle_schema not in {
        PIT_TAXONOMY_BUNDLE_SCHEMA_VERSION,
        PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION,
    }:
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
    split_scope: dict[str, object] | None = None
    if bundle_schema == PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION:
        split_scope = _verify_split_scope_binding(
            payload,
            bundle_manifest_path=path,
            capture_date=capture_date,
            decision_at=decision,
            observed_at=(
                _aware(now, "now") if now is not None else datetime.now(timezone.utc)
            ),
        )
        capture_attempt_value = payload.get("capture_attempt_binding")
        if not isinstance(capture_attempt_value, Mapping):
            raise PITTaxonomySourceError("split candidate capture-attempt binding is missing")
        split_scope.update(
            _verify_capture_attempt_binding(
                capture_attempt_value,
                publication_root=path.parent.parent.parent.resolve(),
                capture_date=capture_date,
                capture_started_at=_aware(payload.get("capture_started_at"), "bundle.capture_started_at"),
                decision_at=decision,
                universe_hash=str(payload.get("universe_hash")),
                clock_id=str(payload.get("clock_id")),
                clock_manifest_hash=str(payload.get("clock_manifest_hash")),
                scope_binding={
                    field_name: payload.get(field_name)
                    for field_name in _SPLIT_SCOPE_BINDING_FIELDS
                },
                expected_bundle_hash=bundle_hash,
                require_success=True,
            )
        )
    elif any(
        field_name in payload
        for field_name in (
            "denominator_binding",
            "rule_candidate_binding",
            "scope_diff",
            "scope_binding_schema_version",
            "capture_attempt_binding",
            PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD,
        )
    ):
        raise PITTaxonomySourceError("v1 taxonomy bundle cannot carry split-scope fields")
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
    if bundle_schema == PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION:
        _verify_split_taxonomy_metadata(
            payload,
            source_path=source_path,
            identity_path=identity_path,
            source_hash=source_hash,
            identity_hash=identity_hash,
        )
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
    inactive_overlay_verified: dict[str, dict[str, object]] = {}
    if bundle_schema == PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION:
        capture_attempt_value = payload.get("capture_attempt_binding")
        if not isinstance(capture_attempt_value, Mapping):
            raise PITTaxonomySourceError("split inactive overlay capture-attempt binding is missing")
        eligibility_value = payload.get("security_eligibility_by_symbol")
        if not isinstance(eligibility_value, Mapping) or set(eligibility_value) != full_set:
            raise PITTaxonomySourceError("taxonomy bundle security eligibility map is invalid")
        eligibility_map: dict[str, Mapping[str, object]] = {}
        for symbol, detail in eligibility_value.items():
            if not isinstance(detail, Mapping):
                raise PITTaxonomySourceError("taxonomy bundle security eligibility entry is invalid")
            eligibility_map[str(symbol)] = dict(detail)
        inactive_overlay_verified = _validate_bundle_inactive_security_overlay(
            payload.get(PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD),
            capture_attempt_binding=capture_attempt_value,
            publication_root=path.parent.parent.parent.resolve(),
            capture_date=capture_date,
            bundle_root=root,
            raw_files=[item for item in files if isinstance(item, Mapping)],
            symbols=tuple(sorted(full_set)),
            market_by_symbol=market_by_symbol,
            security_type_by_symbol=security_types,
            security_eligibility_by_symbol=eligibility_map,
            eligible_symbols=eligible,
            excluded_symbols=excluded,
            unknown_symbols=unknown,
        )
    elif PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD in payload:
        raise PITTaxonomySourceError("v1 taxonomy bundle cannot carry inactive security overlays")
    result: dict[str, object] = {
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
    if split_scope is not None:
        result["schema_version"] = str(bundle_schema)
        result.update(split_scope)
        result[PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD] = inactive_overlay_verified
    return result


_SPLIT_SCOPE_BINDING_FIELDS = frozenset(
    {
        "scope_binding_schema_version",
        "denominator_binding",
        "rule_candidate_binding",
        "scope_diff",
        "taxonomy_coverage_complete",
        "rule_scope_compatible",
    }
)


def _split_scope_binding_fields(
    value: Mapping[str, object] | None,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _SPLIT_SCOPE_BINDING_FIELDS:
        raise PITTaxonomySourceError(
            "split-scope binding must contain exactly the approved binding fields"
        )
    return {str(key): item for key, item in value.items()}


def _validate_split_scope_binding_claims(
    value: Mapping[str, object],
    *,
    denominator_symbols: Sequence[str],
    candidate_symbols: Sequence[str],
    universe_hash: str,
    capture_date: date,
    decision_at: datetime,
) -> None:
    """檢查新契約的自我一致性；外部來源 bytes 另由讀回 validator 重驗。"""

    if set(value) != _SPLIT_SCOPE_BINDING_FIELDS:
        raise PITTaxonomySourceError("split-scope binding fields are invalid or reserved")
    if value.get("scope_binding_schema_version") != PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION:
        raise PITTaxonomySourceError("split-scope binding schema is missing or unsupported")
    denominator = _normalize_symbols(denominator_symbols, "denominator_symbols")
    candidates = _normalize_symbols(candidate_symbols, "universe_hash_symbols")
    if not set(candidates).issubset(set(denominator)):
        # Candidate-only symbols are preserved as explicit diagnostics, but
        # they are never considered compatible with the official denominator.
        compatible = False
    else:
        compatible = True
    if value.get("taxonomy_coverage_complete") is not True:
        raise PITTaxonomySourceError("split-scope taxonomy coverage must be explicitly complete")
    if value.get("rule_scope_compatible") is not compatible:
        raise PITTaxonomySourceError("split-scope Rule compatibility claim is inconsistent")
    denominator_binding = value.get("denominator_binding")
    candidate_binding = value.get("rule_candidate_binding")
    diff = value.get("scope_diff")
    if not isinstance(denominator_binding, Mapping) or not isinstance(candidate_binding, Mapping):
        raise PITTaxonomySourceError("split-scope denominator or Rule binding is missing")
    if not isinstance(diff, Mapping):
        raise PITTaxonomySourceError("split-scope bidirectional diff is missing")
    if candidate_binding.get("universe_hash") != universe_hash:
        raise PITTaxonomySourceError("split-scope Rule universe hash differs")
    if candidate_binding.get("candidate_count") != len(candidates):
        raise PITTaxonomySourceError("split-scope Rule candidate count differs")
    if denominator_binding.get("symbol_count") != len(denominator):
        raise PITTaxonomySourceError("split-scope denominator count differs")
    if denominator_binding.get("coverage_start") != capture_date.isoformat():
        raise PITTaxonomySourceError("split-scope denominator coverage date differs")
    if candidate_binding.get("activation_trading_day") != capture_date.isoformat():
        raise PITTaxonomySourceError("split-scope Rule clock date differs")
    if candidate_binding.get("decision_at") != decision_at.isoformat():
        raise PITTaxonomySourceError("split-scope Rule decision timestamp differs")
    expected_diff = _scope_diff(denominator, candidates)
    if dict(diff) != expected_diff:
        raise PITTaxonomySourceError("split-scope bidirectional diff claim differs")


def _verify_split_scope_binding(
    bundle: Mapping[str, object],
    *,
    bundle_manifest_path: Path,
    capture_date: date,
    decision_at: datetime,
    observed_at: datetime,
) -> dict[str, object]:
    """從固定 publication-root 相對位置重讀 denominator 與 Rule parent。"""

    _validate_split_scope_binding_claims(
        {field_name: bundle.get(field_name) for field_name in _SPLIT_SCOPE_BINDING_FIELDS},
        denominator_symbols=_string_list(bundle.get("symbols"), "symbols"),
        candidate_symbols=_string_list(
            bundle.get("universe_hash_symbols"), "universe_hash_symbols"
        ),
        universe_hash=str(bundle.get("universe_hash")),
        capture_date=capture_date,
        decision_at=decision_at,
    )
    bundle_root = bundle_manifest_path.parent.resolve()
    taxonomy_root = bundle_root.parent
    if taxonomy_root.name != "pit_taxonomy_preopen_split_v2":
        raise PITTaxonomySourceError("split-scope bundle is outside its immutable v2 root")
    if bundle_root.name != capture_date.isoformat():
        raise PITTaxonomySourceError("split-scope bundle directory differs from capture date")
    publication_root = taxonomy_root.parent.resolve()

    denominator_claim = bundle.get("denominator_binding")
    rule_claim = bundle.get("rule_candidate_binding")
    if not isinstance(denominator_claim, Mapping) or not isinstance(rule_claim, Mapping):
        raise PITTaxonomySourceError("split-scope source binding is invalid")
    denominator_path = _proof_child(
        publication_root,
        denominator_claim.get("path"),
        required_prefix="pit_denominator/",
        label="denominator",
    )
    denominator_raw = _proof_file_bytes(denominator_path, "denominator", 16 * 1024 * 1024)
    denominator_file_hash = _sha256_bytes(denominator_raw)
    if denominator_file_hash != denominator_claim.get("file_sha256"):
        raise PITTaxonomySourceError("split-scope denominator raw bytes changed")
    try:
        denominator_manifest = json.loads(denominator_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError("split-scope denominator JSON is invalid") from error
    if not isinstance(denominator_manifest, Mapping):
        raise PITTaxonomySourceError("split-scope denominator manifest is not an object")
    _precheck_denominator_child_custody(denominator_path.parent, denominator_manifest)
    try:
        verified_denominator = validate_prospective_pit_denominator(
            denominator_path,
            now=observed_at,
        )
    except Exception as error:  # validator provides the authoritative contract
        raise PITTaxonomySourceError(
            f"split-scope denominator revalidation failed:{type(error).__name__}"
        ) from error
    if _sha256_bytes(_proof_file_bytes(denominator_path, "denominator", 16 * 1024 * 1024)) != denominator_file_hash:
        raise PITTaxonomySourceError("split-scope denominator changed during revalidation")
    denominator_symbols = _normalize_symbols(
        _string_list(verified_denominator.get("symbols"), "denominator.symbols"),
        "verified denominator symbols",
    )
    denominator_expected = {
        "schema_version": "pit-prospective-pit-denominator-binding.v1",
        "path": denominator_claim.get("path"),
        "file_sha256": denominator_file_hash,
        "content_sha256": verified_denominator.get("content_sha256"),
        "symbols_hash": verified_denominator.get("symbols_hash"),
        "symbol_count": len(denominator_symbols),
        "scope": verified_denominator.get("scope"),
        "coverage_start": verified_denominator.get("coverage_start"),
        "observed_at": verified_denominator.get("observed_at"),
    }
    if dict(denominator_claim) != denominator_expected:
        raise PITTaxonomySourceError("split-scope denominator binding does not match verified source")
    if verified_denominator.get("scope") != "prospective_pit_sector_membership":
        raise PITTaxonomySourceError("split-scope denominator is not official PIT scope")
    if verified_denominator.get("coverage_start") != capture_date.isoformat():
        raise PITTaxonomySourceError("split-scope denominator is not same-day prospective")
    denominator_observed = _aware(verified_denominator.get("observed_at"), "denominator.observed_at")
    started_at = _aware(bundle.get("capture_started_at"), "bundle.capture_started_at")
    cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
    if denominator_observed > started_at or denominator_observed >= cutoff:
        raise PITTaxonomySourceError("split-scope denominator timestamp is after capture boundary")
    expected_denominator_symbols = _normalize_symbols(
        _string_list(bundle.get("symbols"), "bundle.symbols"), "bundle.symbols"
    )
    if denominator_symbols != expected_denominator_symbols:
        raise PITTaxonomySourceError("split-scope official denominator symbols changed")

    rule_bundle_path = _proof_child(
        publication_root,
        rule_claim.get("bundle_path"),
        required_prefix="rule_source/",
        label="Rule bundle",
    )
    if not rule_bundle_path.is_dir() or rule_bundle_path.is_symlink():
        raise PITTaxonomySourceError("split-scope Rule bundle directory is invalid")
    expected_relatives = {
        "identity": "metadata/universe_identity.json",
        "symbols": "metadata/universe_symbols.json",
        "clock": "clock/manifest.json",
        "source_window": "source/daily_price_window.json",
    }
    declared_hashes = rule_claim.get("file_hashes")
    if not isinstance(declared_hashes, Mapping) or set(declared_hashes) != set(expected_relatives):
        raise PITTaxonomySourceError("split-scope Rule raw file hash set is incomplete")
    raw_files: dict[str, bytes] = {}
    for key, relative in expected_relatives.items():
        file_path = _proof_child(
            rule_bundle_path,
            relative,
            required_prefix=None,
            label=f"Rule {key}",
        )
        raw = _proof_file_bytes(
            file_path,
            f"Rule {key}",
            128 * 1024 * 1024 if key == "source_window" else 16 * 1024 * 1024,
        )
        actual_hash = _sha256_bytes(raw)
        if actual_hash != declared_hashes.get(key):
            raise PITTaxonomySourceError(f"split-scope Rule {key} raw bytes changed")
        raw_files[key] = raw
    try:
        identity = json.loads(raw_files["identity"].decode("utf-8"))
        symbols_payload = json.loads(raw_files["symbols"].decode("utf-8"))
        clock = json.loads(raw_files["clock"].decode("utf-8"))
        source_window = json.loads(raw_files["source_window"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError("split-scope Rule parent JSON is invalid") from error
    if not all(isinstance(item, Mapping) for item in (identity, clock, source_window)):
        raise PITTaxonomySourceError("split-scope Rule parent payload is invalid")
    if not isinstance(symbols_payload, list):
        raise PITTaxonomySourceError("split-scope Rule symbols payload is invalid")
    identity = dict(identity)
    clock = dict(clock)
    source_window = dict(source_window)
    candidate_symbols = _normalize_symbols(
        _string_list(identity.get("symbols"), "rule identity symbols"),
        "rule identity symbols",
    )
    raw_hash_symbols = identity.get("universe_hash_symbols")
    if not isinstance(raw_hash_symbols, list) or any(
        not isinstance(item, str) for item in raw_hash_symbols
    ):
        raise PITTaxonomySourceError(
            "rule identity hash symbols must be a string array"
        )
    # This is the score-alignment order committed by the Rule producer.  Do
    # not route it through _string_list, which sorts the values and silently
    # detaches each score from its candidate.
    hash_symbols = _normalize_symbols(
        raw_hash_symbols,
        "universe_hash_symbols",
    )
    scores_value = identity.get("scores_bp")
    if not isinstance(scores_value, list):
        raise PITTaxonomySourceError("rule identity scores_bp must be an array")
    scores = _normalize_scores(scores_value, len(hash_symbols))
    if set(hash_symbols) != set(candidate_symbols) or symbols_payload != list(candidate_symbols):
        raise PITTaxonomySourceError("split-scope Rule candidate symbols do not reconstruct")
    if identity.get("schema_version") != "manual-rule-only-universe.v1" or identity.get("source_id") != "daily_prices":
        raise PITTaxonomySourceError("split-scope Rule identity schema/source is unsupported")
    candidate_hash = _sha256_json(
        {
            "schema_version": "manual-rule-only-universe.v1",
            "symbols": list(hash_symbols),
            "scores_bp": scores,
        }
    )
    if identity.get("universe_hash") != candidate_hash or bundle.get("universe_hash") != candidate_hash:
        raise PITTaxonomySourceError("split-scope Rule candidate score hash differs")
    identity_body = dict(identity)
    identity_hash = identity_body.pop("identity_hash", None)
    if identity_hash != _sha256_json(identity_body):
        raise PITTaxonomySourceError("split-scope Rule identity logical hash mismatch")
    clock_body = dict(clock)
    clock_hash = clock_body.pop("manifest_hash", None)
    if clock_hash != _sha256_json(clock_body):
        raise PITTaxonomySourceError("split-scope Rule clock logical hash mismatch")
    if (
        clock.get("clock_id") != bundle.get("clock_id")
        or clock_hash != bundle.get("clock_manifest_hash")
        or clock.get("universe_hash") != candidate_hash
        or clock.get("activation_trading_day") != capture_date.isoformat()
    ):
        raise PITTaxonomySourceError("split-scope Rule clock binding differs")
    # This field binds the upstream accepted clock used to derive the current
    # candidate clock; it is not the current bundle's clock file hash.  The
    # current bytes are independently pinned above and the current logical
    # clock hash is verified below.
    _require_sha256(
        identity.get("parent_clock_manifest_file_hash"),
        "parent_clock_manifest_file_hash",
    )
    if identity.get("source_window_file_hash") != declared_hashes.get("source_window"):
        raise PITTaxonomySourceError("split-scope Rule identity does not bind source-window bytes")
    source_hash = _require_sha256(source_window.get("source_window_hash"), "source_window_hash")
    source_payload = source_window.get("source_payload")
    if not isinstance(source_payload, Mapping) or _sha256_json(dict(source_payload)) != source_hash:
        raise PITTaxonomySourceError("split-scope Rule source-window payload hash mismatch")
    source_as_of = _required_date(
        source_window.get("data_as_of_date"),
        "rule.source_window.data_as_of_date",
    )
    source_max_available = _aware(
        source_window.get("max_available_timestamp"),
        "rule.source_window.max_available_timestamp",
    )
    if (
        identity.get("source_window_hash") != source_hash
        or source_window.get("schema_version") != "formal-rule-source-window.v1"
        or source_window.get("capture_boundary")
        != "daily_prices.date < decision_session"
        or source_payload.get("schema_version")
        != "manual-rule-only-daily-price-window.v1"
        or source_payload.get("source_id") != "daily_prices"
        or source_payload.get("decision_session") != capture_date.isoformat()
    ):
        raise PITTaxonomySourceError("split-scope Rule source-window identity differs")
    as_of = _required_date(identity.get("data_as_of_date"), "rule.data_as_of_date")
    max_available = _aware(identity.get("max_available_timestamp"), "rule.max_available_timestamp")
    if source_as_of != as_of or source_max_available != max_available:
        raise PITTaxonomySourceError(
            "split-scope Rule source-window availability metadata differs"
        )
    if as_of >= capture_date or max_available.astimezone(TAIPEI).date() >= capture_date:
        raise PITTaxonomySourceError("split-scope Rule data is not prior-session available")
    if max_available >= cutoff or max_available > decision_at:
        raise PITTaxonomySourceError("split-scope Rule availability is after cutoff")
    rank = identity.get("rank_order")
    if rank is not None:
        if not isinstance(rank, (list, tuple)) or any(
            not isinstance(item, str) for item in rank
        ):
            raise PITTaxonomySourceError("split-scope Rule rank order is invalid")
        bundle_rank = bundle.get("rank_order")
        if not isinstance(bundle_rank, (list, tuple)) or any(
            not isinstance(item, str) for item in bundle_rank
        ):
            raise PITTaxonomySourceError("split-scope bundle rank order is invalid")
        if _normalize_symbols(rank, "rank_order") != _normalize_symbols(
            bundle_rank, "rank_order"
        ):
            raise PITTaxonomySourceError("split-scope Rule rank-order binding differs")
    if rank is None and list(hash_symbols) != bundle.get("rank_order"):
        raise PITTaxonomySourceError("split-scope implicit Rule rank order differs")
    if int(identity.get("candidate_count", -1)) != len(candidate_symbols):
        raise PITTaxonomySourceError("split-scope Rule candidate count mismatch")

    candidate_expected = {
        "schema_version": "pit-rule-candidate-binding.v1",
        "bundle_path": rule_claim.get("bundle_path"),
        "file_hashes": dict(cast(Mapping[str, object], declared_hashes)),
        "identity_hash": identity_hash,
        "clock_id": clock.get("clock_id"),
        "clock_manifest_hash": clock_hash,
        "universe_hash": candidate_hash,
        "candidate_count": len(candidate_symbols),
        "candidate_symbols_hash": _sha256_json(list(candidate_symbols)),
        "activation_trading_day": capture_date.isoformat(),
        "decision_at": decision_at.isoformat(),
        "data_as_of_date": as_of.isoformat(),
        # Preserve the identity's original offset spelling in the binding;
        # the parsed instant is compared against cutoff above.
        "max_available_timestamp": identity.get("max_available_timestamp"),
        "source_window_hash": source_hash,
    }
    if dict(cast(Mapping[str, object], rule_claim)) != candidate_expected:
        raise PITTaxonomySourceError("split-scope Rule binding does not match revalidated parent")

    expected_diff = _scope_diff(denominator_symbols, candidate_symbols)
    diff_claim = bundle.get("scope_diff")
    if not isinstance(diff_claim, Mapping) or dict(
        cast(Mapping[str, object], diff_claim)
    ) != expected_diff:
        raise PITTaxonomySourceError("split-scope stored set diff differs from verified sources")
    expected_compatible = not expected_diff["rule_only_symbols"]
    if bundle.get("rule_scope_compatible") is not expected_compatible:
        raise PITTaxonomySourceError("split-scope Rule compatibility is not fail-closed")
    return {
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": expected_compatible,
        "denominator_symbols_hash": verified_denominator.get("symbols_hash"),
        "rule_candidate_symbols_hash": _sha256_json(list(candidate_symbols)),
        "scope_diff": expected_diff,
        "denominator_binding_verified": True,
        "rule_candidate_binding_verified": True,
    }


def _precheck_denominator_child_custody(
    root: Path,
    denominator: Mapping[str, object],
) -> None:
    registry = denominator.get("source_registry")
    if not isinstance(registry, list) or not registry:
        raise PITTaxonomySourceError("split-scope denominator source registry is missing")
    for entry in registry:
        if not isinstance(entry, Mapping):
            raise PITTaxonomySourceError("split-scope denominator source entry is invalid")
        for field_name in ("json_path", "csv_path", "metadata_path", "swagger_path_file"):
            path = _proof_child(root, entry.get(field_name), required_prefix=None, label=field_name)
            _proof_file_bytes(path, f"denominator {field_name}", 64 * 1024 * 1024)
    license_path = _proof_child(
        root,
        "government_open_data_license.html",
        required_prefix=None,
        label="denominator license",
    )
    _proof_file_bytes(license_path, "denominator license", 4 * 1024 * 1024)


def _verify_split_taxonomy_metadata(
    bundle: Mapping[str, object],
    *,
    source_path: Path,
    identity_path: Path,
    source_hash: str,
    identity_hash: str,
) -> None:
    if source_path.name != "taxonomy_source.json" or identity_path.name != "taxonomy_identity.json":
        raise PITTaxonomySourceError("split-scope taxonomy metadata path is unsupported")
    source_raw = _proof_file_bytes(source_path, "taxonomy source metadata", 16 * 1024 * 1024)
    identity_raw = _proof_file_bytes(identity_path, "taxonomy identity metadata", 16 * 1024 * 1024)
    if _sha256_bytes(source_raw) != source_hash or _sha256_bytes(identity_raw) != identity_hash:
        raise PITTaxonomySourceError("split-scope taxonomy metadata bytes changed")
    try:
        source_value = json.loads(source_raw.decode("utf-8"))
        identity_value = json.loads(identity_raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError("split-scope taxonomy metadata JSON is invalid") from error
    if not isinstance(source_value, Mapping) or not isinstance(identity_value, Mapping):
        raise PITTaxonomySourceError("split-scope taxonomy metadata is not an object")
    source = dict(source_value)
    identity = dict(identity_value)
    if (
        source.get("schema_version") != PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION
        or identity.get("schema_version") != PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION
    ):
        raise PITTaxonomySourceError("split-scope taxonomy metadata version mismatch")
    attempt_binding_value = bundle.get("capture_attempt_binding")
    if not isinstance(attempt_binding_value, Mapping):
        raise PITTaxonomySourceError("split-scope capture-attempt binding is missing")
    attempt_binding = _capture_attempt_binding_fields(attempt_binding_value)
    if (
        source.get("capture_attempt_binding") != attempt_binding
        or identity.get("capture_attempt_binding") != attempt_binding
    ):
        raise PITTaxonomySourceError("split-scope capture-attempt binding differs")
    binding_fields = _split_scope_binding_fields(
        {field_name: bundle.get(field_name) for field_name in _SPLIT_SCOPE_BINDING_FIELDS}
    )
    for field_name, expected in binding_fields.items():
        if source.get(field_name) != expected or identity.get(field_name) != expected:
            raise PITTaxonomySourceError(f"split-scope taxonomy {field_name} differs")
    identity_body = dict(identity)
    mapping_hash = identity_body.pop("mapping_hash", None)
    if mapping_hash != _sha256_json(identity_body):
        raise PITTaxonomySourceError("split-scope taxonomy identity mapping hash mismatch")
    for field_name in (
        "source_id",
        "source_version",
        "available_at",
        "effective_from",
        "universe_hash",
        "symbols",
        "universe_hash_symbols",
        "scores_bp",
        "rank_order",
        "mapping_by_market",
        "classification_sources_by_market",
        "security_sources_by_market",
        "market_by_symbol",
        "security_type_by_symbol",
        "security_eligibility_by_symbol",
        "eligible_symbols",
        "excluded_by_security",
        "unknown_symbols",
        "license_scope",
        "raw_manifest_path",
        "raw_manifest_hash",
        PIT_TAXONOMY_INACTIVE_OVERLAY_FIELD,
        "capture_attempt_binding",
    ):
        if source.get(field_name) != identity.get(field_name):
            raise PITTaxonomySourceError(f"split-scope taxonomy source {field_name} mismatch")
    if (
        identity.get("source_hash") != source_hash
        or identity.get("universe_hash") != bundle.get("universe_hash")
        or identity.get("symbols") != bundle.get("symbols")
        or identity.get("universe_hash_symbols") != bundle.get("universe_hash_symbols")
        or identity.get("scores_bp") != bundle.get("scores_bp")
        or identity.get("rank_order") != bundle.get("rank_order")
    ):
        raise PITTaxonomySourceError("split-scope taxonomy identity differs from bundle envelope")


def _proof_child(
    root: Path,
    value: object,
    *,
    required_prefix: str | None,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise PITTaxonomySourceError(f"{label} proof path is invalid")
    raw_parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in raw_parts):
        raise PITTaxonomySourceError(f"{label} proof path must be normalized and relative")
    relative = Path(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise PITTaxonomySourceError(f"{label} proof path must be normalized and relative")
    if required_prefix is not None and not value.startswith(required_prefix):
        raise PITTaxonomySourceError(f"{label} proof path has the wrong root")
    target = root.joinpath(relative)
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise PITTaxonomySourceError(f"{label} proof path escapes or is missing") from error
    return target


def _proof_file_bytes(path: Path, label: str, max_bytes: int) -> bytes:
    try:
        return _read_regular_single_link_file(path, label=label, max_bytes=max_bytes)
    except (CaptureValidationError, OSError) as error:
        raise PITTaxonomySourceError(f"{label} proof file custody failed") from error


def _assert_no_link_path(
    path: Path,
    *,
    allow_missing: bool,
    confine_to: Path | None = None,
) -> None:
    """拒絕 custody path 中的 symlink/junction，並可限制在單一根目錄內。"""

    absolute = Path(os.path.abspath(str(path.expanduser())))
    confinement = (
        Path(os.path.abspath(str(confine_to.expanduser())))
        if confine_to is not None
        else None
    )
    if confinement is not None:
        try:
            absolute.relative_to(confinement)
        except ValueError as error:
            raise PITTaxonomySourceError("capture attempt path escapes publication root") from error
    parts = absolute.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            is_link = current.is_symlink()
            is_junction = bool(
                getattr(current, "is_junction", lambda: False)()
            )
            exists = current.exists()
        except OSError as error:
            raise PITTaxonomySourceError("capture attempt path cannot be inspected") from error
        if is_link or is_junction:
            raise PITTaxonomySourceError("capture attempt path contains a link")
        if not exists and not allow_missing:
            raise PITTaxonomySourceError("capture attempt path is missing")


def _relative_path(root: Path, target: Path) -> str:
    try:
        relative = target.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise PITTaxonomySourceError("capture attempt bundle path is outside publication root") from error
    return relative.as_posix()


def _decode_json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError(f"{label} JSON is invalid") from error
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{label} is not an object")
    return {str(key): item for key, item in value.items()}


def _capture_attempt_binding_fields(value: Mapping[str, object]) -> dict[str, object]:
    expected = {
        "schema_version",
        "attempt_id",
        "path",
        "descriptor_sha256",
        "receipt_path",
        "receipt_sha256",
        "component_count",
        "aggregate_raw_bytes",
    }
    if set(value) != expected:
        raise PITTaxonomySourceError("capture-attempt binding fields are invalid or reserved")
    if value.get("schema_version") != PIT_TAXONOMY_CAPTURE_ATTEMPT_BINDING_SCHEMA_VERSION:
        raise PITTaxonomySourceError("capture-attempt binding schema is unsupported")
    if re.fullmatch(r"[0-9a-f]{32}", str(value.get("attempt_id"))) is None:
        raise PITTaxonomySourceError("capture-attempt binding id is invalid")
    for field_name in ("descriptor_sha256", "receipt_sha256"):
        _require_sha256(value.get(field_name), f"capture_attempt_binding.{field_name}")
    component_count = value.get("component_count")
    aggregate_raw_bytes = value.get("aggregate_raw_bytes")
    for field_name, item in (
        ("component_count", component_count),
        ("aggregate_raw_bytes", aggregate_raw_bytes),
    ):
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise PITTaxonomySourceError(f"capture-attempt binding {field_name} is invalid")
    if not isinstance(component_count, int) or isinstance(component_count, bool):
        raise PITTaxonomySourceError("capture-attempt binding component count is invalid")
    if not isinstance(aggregate_raw_bytes, int) or isinstance(aggregate_raw_bytes, bool):
        raise PITTaxonomySourceError("capture-attempt binding aggregate bytes are invalid")
    if component_count < 1 or component_count > PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
        raise PITTaxonomySourceError("capture-attempt binding component count is out of bounds")
    if aggregate_raw_bytes > PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES:
        raise PITTaxonomySourceError("capture-attempt binding aggregate bytes are out of bounds")
    attempt_id = str(value["attempt_id"])
    capture_path = value.get("path")
    receipt_path = value.get("receipt_path")
    expected_path = f"pit_taxonomy_capture_attempts/{_path_date_from_capture_path(capture_path)}/{attempt_id}"
    if capture_path != expected_path or receipt_path != f"{expected_path}/capture_receipt.json":
        raise PITTaxonomySourceError("capture-attempt binding paths are not canonical")
    return {str(key): item for key, item in value.items()}


def _path_date_from_capture_path(value: object) -> str:
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise PITTaxonomySourceError("capture-attempt path is invalid")
    parts = value.split("/")
    if len(parts) != 3 or parts[0] != "pit_taxonomy_capture_attempts":
        raise PITTaxonomySourceError("capture-attempt path has the wrong root")
    try:
        parsed = date.fromisoformat(parts[1])
    except ValueError as error:
        raise PITTaxonomySourceError("capture-attempt path date is invalid") from error
    if parsed.isoformat() != parts[1]:
        raise PITTaxonomySourceError("capture-attempt path date is not canonical")
    return parts[1]


def _verify_capture_attempt_files(
    attempt_root: Path,
    descriptor: Mapping[str, object],
    receipt: Mapping[str, object],
) -> None:
    if descriptor.get("schema_version") != PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION:
        raise PITTaxonomySourceError("capture-attempt descriptor schema is unsupported")
    attempt_id = descriptor.get("attempt_id")
    if attempt_root.name != attempt_id or receipt.get("attempt_id") != attempt_id:
        raise PITTaxonomySourceError("capture-attempt identity mismatch")
    planned = descriptor.get("planned_sources")
    components = receipt.get("components")
    if not isinstance(planned, list) or not isinstance(components, list):
        raise PITTaxonomySourceError("capture-attempt source plan or receipt is invalid")
    if len(planned) != len(components) or not 1 <= len(components) <= PIT_TAXONOMY_CAPTURE_MAX_COMPONENTS:
        raise PITTaxonomySourceError("capture-attempt component set is incomplete")
    aggregate = 0
    cutoff = _aware(descriptor.get("cutoff_at"), "capture_attempt.cutoff_at")
    started_at = _aware(descriptor.get("started_at"), "capture_attempt.started_at")
    for index, (planned_item, component) in enumerate(zip(planned, components), start=1):
        if not isinstance(planned_item, Mapping) or not isinstance(component, Mapping):
            raise PITTaxonomySourceError("capture-attempt component entry is invalid")
        source_name = str(planned_item.get("source_name"))
        if component.get("source_name") != source_name:
            raise PITTaxonomySourceError("capture-attempt component order/name mismatch")
        raw_relative = component.get("raw_path")
        metadata_relative = component.get("metadata_path")
        if not isinstance(raw_relative, str) or not isinstance(metadata_relative, str):
            raise PITTaxonomySourceError("capture-attempt component paths are missing")
        prefix = f"components/{index:02d}_"
        if not raw_relative.startswith(prefix) or not raw_relative.endswith(".raw"):
            raise PITTaxonomySourceError("capture-attempt raw path is not canonical")
        if metadata_relative != raw_relative[:-4] + ".metadata.json":
            raise PITTaxonomySourceError("capture-attempt metadata path does not match raw path")
        raw_path = _proof_child(attempt_root, raw_relative, required_prefix="components/", label="capture raw")
        metadata_path = _proof_child(attempt_root, metadata_relative, required_prefix="components/", label="capture metadata")
        raw = _proof_file_bytes(raw_path, "capture attempt raw component", PIT_TAXONOMY_MAX_SOURCE_BYTES)
        metadata_raw = _proof_file_bytes(metadata_path, "capture attempt component metadata", 1024 * 1024)
        if _sha256_bytes(raw) != component.get("raw_sha256") or len(raw) != component.get("raw_bytes"):
            raise PITTaxonomySourceError("capture-attempt raw component hash/size mismatch")
        if _sha256_bytes(metadata_raw) != component.get("metadata_sha256"):
            raise PITTaxonomySourceError("capture-attempt component metadata hash mismatch")
        metadata = _decode_json_object(metadata_raw, "capture attempt component metadata")
        if metadata.get("source_name") != source_name or metadata.get("metadata_valid") is not True:
            raise PITTaxonomySourceError("capture-attempt component metadata is invalid")
        if metadata.get("raw_sha256") != _sha256_bytes(raw) or metadata.get("raw_bytes") != len(raw):
            raise PITTaxonomySourceError("capture-attempt raw metadata hash/size mismatch")
        http_metadata = metadata.get("http_metadata")
        if not isinstance(http_metadata, Mapping):
            raise PITTaxonomySourceError("capture-attempt HTTP metadata is missing")
        available = _component_available(http_metadata, source_name)
        if available >= cutoff:
            raise PITTaxonomySourceError("capture-attempt source completed after cutoff")
        if metadata.get("fetched") is True and available < started_at:
            raise PITTaxonomySourceError("capture-attempt source completion predates actual start")
        custodied_at = _aware(metadata.get("custodied_at"), "capture_attempt.custodied_at")
        if custodied_at < started_at or custodied_at >= cutoff:
            raise PITTaxonomySourceError("capture-attempt custody time is outside cutoff")
        aggregate += len(raw)
    if aggregate > PIT_TAXONOMY_CAPTURE_MAX_TOTAL_RAW_BYTES:
        raise PITTaxonomySourceError("capture-attempt aggregate raw-byte limit exceeded")
    if receipt.get("component_count") != len(components):
        raise PITTaxonomySourceError("capture-attempt receipt component count mismatch")
    if receipt.get("aggregate_raw_bytes") != aggregate:
        raise PITTaxonomySourceError("capture-attempt receipt aggregate byte count mismatch")
    if descriptor.get("scope_binding_sha256") != receipt.get("scope_binding_sha256"):
        raise PITTaxonomySourceError("capture-attempt scope binding changed")


def _verify_capture_attempt_binding(
    binding: Mapping[str, object],
    *,
    publication_root: Path,
    capture_date: date,
    capture_started_at: datetime,
    decision_at: datetime,
    universe_hash: str,
    clock_id: str,
    clock_manifest_hash: str,
    scope_binding: Mapping[str, object],
    expected_bundle_hash: str | None,
    require_success: bool,
) -> dict[str, object]:
    fields = _capture_attempt_binding_fields(binding)
    attempt_id = str(fields["attempt_id"])
    if fields["path"] != f"pit_taxonomy_capture_attempts/{capture_date.isoformat()}/{attempt_id}":
        raise PITTaxonomySourceError("capture-attempt binding capture date mismatch")
    publication = Path(os.path.abspath(str(publication_root.expanduser())))
    _assert_no_link_path(publication, allow_missing=False)
    attempt_root = _proof_child(
        publication,
        fields.get("path"),
        required_prefix="pit_taxonomy_capture_attempts/",
        label="capture attempt",
    )
    _assert_no_link_path(attempt_root, allow_missing=False, confine_to=publication)
    descriptor_path = _proof_child(
        attempt_root,
        "attempt_descriptor.json",
        required_prefix=None,
        label="capture attempt descriptor",
    )
    receipt_path = _proof_child(
        attempt_root,
        "capture_receipt.json",
        required_prefix=None,
        label="capture attempt receipt",
    )
    descriptor_raw = _proof_file_bytes(descriptor_path, "capture attempt descriptor", 1024 * 1024)
    receipt_raw = _proof_file_bytes(receipt_path, "capture attempt receipt", 4 * 1024 * 1024)
    if _sha256_bytes(descriptor_raw) != fields.get("descriptor_sha256"):
        raise PITTaxonomySourceError("capture-attempt descriptor hash mismatch")
    if _sha256_bytes(receipt_raw) != fields.get("receipt_sha256"):
        raise PITTaxonomySourceError("capture-attempt receipt hash mismatch")
    descriptor = _decode_json_object(descriptor_raw, "capture attempt descriptor")
    receipt = _decode_json_object(receipt_raw, "capture attempt receipt")
    if descriptor.get("attempt_id") != attempt_id or receipt.get("attempt_id") != attempt_id:
        raise PITTaxonomySourceError("capture-attempt id differs from binding")
    if descriptor.get("capture_date") != capture_date.isoformat():
        raise PITTaxonomySourceError("capture-attempt date differs from bundle")
    if _aware(descriptor.get("started_at"), "capture_attempt.started_at") != capture_started_at:
        raise PITTaxonomySourceError("capture-attempt start differs from bundle")
    if descriptor.get("universe_hash") != universe_hash or descriptor.get("clock_id") != clock_id:
        raise PITTaxonomySourceError("capture-attempt Rule identity differs from bundle")
    if descriptor.get("clock_manifest_hash") != clock_manifest_hash:
        raise PITTaxonomySourceError("capture-attempt Rule clock hash differs from bundle")
    binding_hash = _sha256_json(_split_scope_binding_fields(scope_binding))
    if descriptor.get("scope_binding_sha256") != binding_hash:
        raise PITTaxonomySourceError("capture-attempt denominator/Rule binding differs")
    if fields.get("component_count") != receipt.get("component_count"):
        raise PITTaxonomySourceError("capture-attempt bound component count differs")
    if fields.get("aggregate_raw_bytes") != receipt.get("aggregate_raw_bytes"):
        raise PITTaxonomySourceError("capture-attempt bound aggregate byte count differs")
    _verify_capture_attempt_files(attempt_root, descriptor, receipt)
    if require_success:
        terminal_raw = _proof_file_bytes(
            _proof_child(
                attempt_root,
                "capture_result.json",
                required_prefix=None,
                label="capture attempt terminal result",
            ),
            "capture attempt terminal result",
            1024 * 1024,
        )
        terminal = _decode_json_object(
            terminal_raw, "capture attempt terminal result"
        )
        if (
            terminal.get("schema_version")
            != PIT_TAXONOMY_CAPTURE_ATTEMPT_SCHEMA_VERSION
            or terminal.get("attempt_id") != attempt_id
            or terminal.get("capture_date") != capture_date.isoformat()
            or terminal.get("status") != "success"
        ):
            raise PITTaxonomySourceError("capture-attempt terminal result is not successful")
        if terminal.get("descriptor_sha256") != fields.get("descriptor_sha256"):
            raise PITTaxonomySourceError("capture-attempt terminal descriptor hash mismatch")
        if terminal.get("receipt_sha256") != fields.get("receipt_sha256"):
            raise PITTaxonomySourceError("capture-attempt terminal receipt hash mismatch")
        terminal_at = _aware(terminal.get("completed_at"), "capture_attempt.completed_at")
        cutoff = datetime.combine(capture_date, PIT_TAXONOMY_CUTOFF, tzinfo=TAIPEI)
        if terminal_at >= cutoff or terminal_at < capture_started_at:
            raise PITTaxonomySourceError("capture-attempt terminal time is outside cutoff")
        if expected_bundle_hash is None or terminal.get("bundle_hash") != expected_bundle_hash:
            raise PITTaxonomySourceError("capture-attempt terminal bundle hash mismatch")
        if terminal.get("bundle_manifest_path") != f"pit_taxonomy_preopen_split_v2/{capture_date.isoformat()}/bundle_manifest.json":
            raise PITTaxonomySourceError("capture-attempt terminal bundle path mismatch")
        if terminal.get("components") != receipt.get("components"):
            raise PITTaxonomySourceError("capture-attempt terminal component pins differ from receipt")
        rejected = terminal.get("rejected_components", [])
        if rejected != []:
            raise PITTaxonomySourceError("successful capture attempt has rejected components")
    else:
        if expected_bundle_hash is not None:
            raise PITTaxonomySourceError("unexpected bundle hash check for prewrite validation")
        if (attempt_root / "capture_result.json").exists():
            raise PITTaxonomySourceError("capture-attempt already has a terminal result")
    return {
        "capture_attempt_id": attempt_id,
        "capture_attempt_path": str(attempt_root),
        "capture_attempt_receipt_sha256": fields["receipt_sha256"],
        "capture_attempt_component_count": fields["component_count"],
        "capture_attempt_aggregate_raw_bytes": fields["aggregate_raw_bytes"],
        "capture_attempt_verified": True,
    }


def _scope_diff(
    denominator_symbols: Sequence[str],
    candidate_symbols: Sequence[str],
) -> dict[str, object]:
    denominator = set(denominator_symbols)
    candidates = set(candidate_symbols)
    intersection = sorted(denominator & candidates)
    denominator_only = sorted(denominator - candidates)
    rule_only = sorted(candidates - denominator)
    return {
        "denominator_count": len(denominator),
        "candidate_count": len(candidates),
        "intersection_count": len(intersection),
        "denominator_only_count": len(denominator_only),
        "rule_only_count": len(rule_only),
        "intersection_symbols": intersection,
        "intersection_symbols_hash": _sha256_json(intersection),
        "denominator_only_symbols": denominator_only,
        "denominator_only_symbols_hash": _sha256_json(denominator_only),
        "rule_only_symbols": rule_only,
        "rule_only_symbols_hash": _sha256_json(rule_only),
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
    "PIT_TAXONOMY_SPLIT_BUNDLE_SCHEMA_VERSION",
    "PIT_TAXONOMY_CUTOFF",
    "PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION",
    "PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION",
    "PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_CONFIG_ENV",
    "PIT_TAXONOMY_SOURCE_CONFIG_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION",
    "PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION",
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
