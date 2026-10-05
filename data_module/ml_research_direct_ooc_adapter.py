"""將研究來源轉成經驗證的數值 observations，並交接既有 Direct/OOC builder。

落實 ML revision-aware rebuild 方案中第 3 項工程缺口：
1. 解決既有 Direct/OOC raw-manifest contract 不接受 daily source-row research schema
   或 revision-aware raw candidate 的問題。
2. 新增明確的 research-only adapter 與 manifest，轉換來源列為 typed 數值觀察，
   同時嚴格保存整數尺度、來源 availability 與修訂摘要。
3. 在 adapter 與 consumer receipt 中精確綁定同一 candidate raw manifest hash、
   row count、training-as-of 與 market revision digest。
4. 明確保證 release_v4 pointer 與正式 D: 資料根目錄完全不動（release_v4 pointer 保持不變）。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.ml_revision_aware_raw_candidate import (
    REVISION_AWARE_RAW_SCHEMA_VERSION,
    TAIPEI_TZ,
    RevisionAwareCandidateError,
    _assert_no_float,
    _aware_utc,
    _canonical_json_bytes,
    _check_isolation,
    _file_fingerprint,
    _now_utc,
    _parse_decision_at,
    _reject_links,
    _sha256_bytes,
    _sha256_file,
)
from data_module.ml_research_output_boundary import (
    MLResearchOutputBoundaryError,
    resolve_ml_research_output_path,
)


RESEARCH_ADAPTED_RAW_SCHEMA_VERSION = "ml-research-adapted-raw-manifest.v1"
RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION = (
    "ml-research-direct-ooc-adapter-receipt.v1"
)
RESEARCH_DIRECT_STORE_RECEIPT_SCHEMA_VERSION = (
    "ml-research-direct-numeric-receipt.v1"
)

DAILY_PRICE_FEATURE_IDS: Mapping[str, str] = MappingProxyType(
    {
        "open": "daily_prices.開盤價",
        "high": "daily_prices.最高價",
        "low": "daily_prices.最低價",
        "close": "daily_prices.收盤價",
        "volume": "daily_prices.成交股數",
        "amount": "daily_prices.成交金額",
        "trade_count": "daily_prices.成交筆數",
    }
)
DAILY_PRICE_FEATURE_INFO: Mapping[str, tuple[int, str]] = MappingProxyType(
    {
        DAILY_PRICE_FEATURE_IDS["open"]: (2, "TWD/share"),
        DAILY_PRICE_FEATURE_IDS["high"]: (2, "TWD/share"),
        DAILY_PRICE_FEATURE_IDS["low"]: (2, "TWD/share"),
        DAILY_PRICE_FEATURE_IDS["close"]: (2, "TWD/share"),
        DAILY_PRICE_FEATURE_IDS["volume"]: (0, "share"),
        DAILY_PRICE_FEATURE_IDS["amount"]: (0, "TWD"),
        DAILY_PRICE_FEATURE_IDS["trade_count"]: (0, "trade"),
    }
)
_PROJECTION_DAILY_SOURCE_FIELD_ALIASES: Mapping[
    str, Mapping[str, tuple[str, ...]]
] = MappingProxyType(
    {
        "twse": MappingProxyType(
            {
                DAILY_PRICE_FEATURE_IDS["open"]: ("開盤價",),
                DAILY_PRICE_FEATURE_IDS["high"]: ("最高價",),
                DAILY_PRICE_FEATURE_IDS["low"]: ("最低價",),
                DAILY_PRICE_FEATURE_IDS["close"]: ("收盤價",),
                DAILY_PRICE_FEATURE_IDS["volume"]: ("成交股數",),
                DAILY_PRICE_FEATURE_IDS["amount"]: ("成交金額",),
                DAILY_PRICE_FEATURE_IDS["trade_count"]: ("成交筆數",),
            }
        ),
        "tpex": MappingProxyType(
            {
                DAILY_PRICE_FEATURE_IDS["open"]: ("開盤",),
                DAILY_PRICE_FEATURE_IDS["high"]: ("最高",),
                DAILY_PRICE_FEATURE_IDS["low"]: ("最低",),
                DAILY_PRICE_FEATURE_IDS["close"]: ("收盤",),
                DAILY_PRICE_FEATURE_IDS["volume"]: ("成交股數",),
                # TPEx labels amount units explicitly. Do not infer a unit from
                # an unknown or abbreviated heading such as 「成交金額(千元)」.
                DAILY_PRICE_FEATURE_IDS["amount"]: ("成交金額(元)",),
                DAILY_PRICE_FEATURE_IDS["trade_count"]: ("成交筆數",),
            }
        ),
    }
)


class ResearchAdapterError(RevisionAwareCandidateError):
    """Direct/OOC 研究適配器校驗或轉換失敗。"""


def _resolve_research_path(path: Path, label: str) -> Path:
    try:
        return resolve_ml_research_output_path(path, access="write")
    except MLResearchOutputBoundaryError as exc:
        raise ResearchAdapterError(f"{label}: {exc}") from exc


def _strict_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResearchAdapterError(f"{field_name} must be a strict integer; bool is rejected")
    return value


def _normalized_projection_field_name(value: str) -> str:
    """Normalize whitespace only; raw projection keys remain untouched."""

    return "".join(value.split())


def _projection_exact_value(
    exact_values: Mapping[str, Any], *, venue: object, feature_id: str
) -> tuple[str, Any] | None:
    if not isinstance(venue, str) or venue not in _PROJECTION_DAILY_SOURCE_FIELD_ALIASES:
        raise ResearchAdapterError("projection venue is missing or unsupported")
    aliases = _PROJECTION_DAILY_SOURCE_FIELD_ALIASES[venue].get(feature_id)
    if not aliases:
        raise ResearchAdapterError("projection feature has no venue-specific source mapping")
    normalized_aliases = {_normalized_projection_field_name(alias) for alias in aliases}
    matches = [
        key
        for key in exact_values
        if isinstance(key, str)
        and _normalized_projection_field_name(key) in normalized_aliases
    ]
    if len(matches) > 1:
        raise ResearchAdapterError(
            f"projection source fields are ambiguous for {feature_id} at {venue}"
        )
    if not matches:
        return None
    source_name = matches[0]
    return source_name, exact_values[source_name]


def _strict_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ResearchAdapterError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _json_hash(payload: Any) -> str:
    return f"sha256:{_sha256_bytes(_canonical_json_bytes(payload))}"


def _deep_freeze(value: Any) -> Any:
    """將已驗證載荷轉為遞迴不可變 mapping/tuple。"""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _deep_plain(value: Any) -> Any:
    """明確複製為 JSON 相容 dict/list，不替未知物件呼叫 str。"""
    if isinstance(value, Mapping):
        return {key: _deep_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_deep_plain(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ResearchAdapterError(f"artifact audit payload contains unsupported value type: {type(value).__name__}")


def _write_owned_failure_receipt(
    output_dir: Path,
    *,
    owned: bool,
    schema_version: str,
    exc: Exception,
) -> None:
    """只在本次新建目錄內以 exclusive-create 留下失敗記錄。"""
    if not owned:
        return
    try:
        path = output_dir / "failure_receipt.json"
        with path.open("xb") as stream:
            stream.write(_canonical_json_bytes({
                "schema_version": schema_version,
                "status": "failed_closed",
                "error_type": type(exc).__name__,
                "message": str(exc),
                "recorded_at": _now_utc().isoformat(),
                "research_only": True,
                "formal_credit": False,
            }))
    except OSError:
        # 不覆寫既有內容；主錯誤仍由 caller 原樣傳回。
        return


def _verify_stored_gzip_jsonl(
    path: Path,
    *,
    expected_compressed_sha256: str,
    expected_uncompressed_sha256: str,
    expected_row_count: int,
) -> None:
    """驗證複製後 shard 的 gzip bytes、解壓 bytes、列數與基本 row schema。"""
    if f"sha256:{_sha256_file(path)}" != _normalized_pin(expected_compressed_sha256, "stored compressed shard pin"):
        raise ResearchAdapterError("stored shard compressed SHA-256 mismatch")
    hasher = hashlib.sha256()
    row_count = 0
    try:
        with gzip.open(path, "rb") as stream:
            while line := stream.readline():
                hasher.update(line)
                row = json.loads(line.decode("utf-8"))
                if not isinstance(row, dict) or row.get("schema_version") != "ml-pit-observation.v1":
                    raise ResearchAdapterError("stored shard row schema is invalid")
                if row.get("historical_pit_eligible") is not False:
                    raise ResearchAdapterError("stored shard overstates historical PIT eligibility")
                values = row.get("values")
                if not isinstance(values, list):
                    raise ResearchAdapterError("stored shard values are not a list")
                for value in values:
                    if not isinstance(value, dict):
                        raise ResearchAdapterError("stored shard numeric value is not an object")
                    _strict_int(value.get("value_int"), "stored value_int")
                    _strict_int(value.get("scale"), "stored value scale")
                row_count += 1
    except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchAdapterError("stored gzip JSONL shard is truncated or malformed") from exc
    if row_count != expected_row_count:
        raise ResearchAdapterError("stored shard row_count mismatch")
    if f"sha256:{hasher.hexdigest()}" != _normalized_pin(expected_uncompressed_sha256, "stored uncompressed shard pin"):
        raise ResearchAdapterError("stored shard uncompressed SHA-256 mismatch")


@dataclass(frozen=True)
class VerifiedNumericObservation:
    """經 bytes/schema/pin 驗證的 current-observed 整數列。"""

    symbol: str
    event_date: str
    available_at: datetime
    values: tuple[Mapping[str, Any], ...]
    missing_mask: tuple[str, ...]
    quality_blocked_mask: tuple[str, ...]
    staleness_mask: tuple[str, ...]
    source_projection_row_identity_hash: str


@dataclass(frozen=True)
class VerifiedMLResearchNumericArtifact:
    """不宣稱 historical PIT 或 OOC 完成的研究數值 artifact。"""

    status: str
    observations: tuple[VerifiedNumericObservation, ...]
    feature_registry: tuple[Mapping[str, Any], ...]
    feature_registry_sha256: str
    candidate_manifest_bytes_sha256: str
    adapted_manifest_bytes_sha256: str
    adapted_manifest_canonical_sha256: str
    source_pins: Mapping[str, Any]
    current_observation_freeze: datetime
    freeze_identity: str
    historical_pit_eligible: bool = False

    def audit_payload(self) -> dict[str, Any]:
        """回傳可序列化的唯讀稽核副本；修改副本不會更動已驗證 artifact。"""
        return {
            "status": self.status,
            "observations": [
                {
                    "symbol": row.symbol,
                    "event_date": row.event_date,
                    "available_at": row.available_at.isoformat(),
                    "values": _deep_plain(row.values),
                    "missing_mask": list(row.missing_mask),
                    "quality_blocked_mask": list(row.quality_blocked_mask),
                    "staleness_mask": list(row.staleness_mask),
                    "source_projection_row_identity_hash": row.source_projection_row_identity_hash,
                }
                for row in self.observations
            ],
            "feature_registry": _deep_plain(self.feature_registry),
            "feature_registry_sha256": self.feature_registry_sha256,
            "candidate_manifest_bytes_sha256": self.candidate_manifest_bytes_sha256,
            "adapted_manifest_bytes_sha256": self.adapted_manifest_bytes_sha256,
            "adapted_manifest_canonical_sha256": self.adapted_manifest_canonical_sha256,
            "source_pins": _deep_plain(self.source_pins),
            "current_observation_freeze": self.current_observation_freeze.isoformat(),
            "freeze_identity": self.freeze_identity,
            "historical_pit_eligible": self.historical_pit_eligible,
        }


@dataclass(frozen=True)
class ResearchAdaptRequest:
    """研究原始候選轉 Direct/OOC 相容格式請求。"""

    raw_candidate_manifest_path: Path
    output_dir: Path
    training_as_of: str | datetime
    expected_raw_manifest_sha256: str | None = None
    expected_candidate_manifest_bytes_sha256: str | None = None
    benchmark_entity_id: str = "TAIEX"
    preview_only: bool = False
    now_provider: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if not self.raw_candidate_manifest_path.exists():
            raise ResearchAdapterError(
                f"raw_candidate_manifest_path does not exist: {self.raw_candidate_manifest_path}"
            )
        _resolve_research_path(self.output_dir, "adapter output_dir")


@dataclass(frozen=True)
class ResearchAdaptResult:
    """研究適配結果。"""

    status: str
    adapted_manifest_path: Path
    adapted_manifest_hash: str
    adapter_receipt_path: Path
    candidate_raw_manifest_hash: str
    row_count: int
    shard_count: int
    market_revision_digest: str
    formal_release_v4_pointer_untouched: bool = True


class ResearchDirectOOCAdapter:
    """產生 hash 驗證的研究數值 observations；不宣稱 Direct/OOC 已就緒。"""

    def __init__(self, request: ResearchAdaptRequest) -> None:
        self.request = request
        raw_freeze = request.training_as_of
        if isinstance(raw_freeze, str):
            try:
                raw_freeze = datetime.fromisoformat(raw_freeze)
            except ValueError as exc:
                raise ResearchAdapterError("training_as_of must be an ISO-8601 timestamp with timezone") from exc
        self.training_as_of_utc = _strict_aware_utc(raw_freeze, "training_as_of")
        supplied_now = request.now_provider() if request.now_provider else _now_utc()
        self.now = _strict_aware_utc(supplied_now, "now_provider result")
        if self.training_as_of_utc > self.now:
            raise ResearchAdapterError("training_as_of freeze cannot be in the future")
        self._request_output_owned = False

    def adapt(self) -> ResearchAdaptResult:
        self._request_output_owned = False
        try:
            return self._adapt_once()
        except Exception as exc:
            _write_owned_failure_receipt(
                self.request.output_dir,
                owned=self._request_output_owned,
                schema_version="ml-research-adapter-failure.v1",
                exc=exc,
            )
            raise

    def _adapt_once(self) -> ResearchAdaptResult:
        req = self.request
        root = Path(__file__).resolve().parents[1]

        # 1. 隔離性與連結檢查
        _resolve_research_path(req.output_dir, "adapter output_dir")
        _reject_links(req.raw_candidate_manifest_path, root, "raw_candidate_manifest")

        # 2. 讀取並校驗候選 Manifest
        raw_manifest_bytes = req.raw_candidate_manifest_path.read_bytes()
        candidate_manifest = json.loads(raw_manifest_bytes.decode("utf-8"))
        actual_raw_manifest_file_sha = f"sha256:{_sha256_bytes(raw_manifest_bytes)}"
        expected_candidate = req.expected_candidate_manifest_bytes_sha256 or req.expected_raw_manifest_sha256
        if not expected_candidate:
            raise ResearchAdapterError("an explicit candidate manifest actual-bytes SHA-256 pin is required")
        expected = expected_candidate.lower()
        if not expected.startswith("sha256:"):
            expected = f"sha256:{expected}"
        if actual_raw_manifest_file_sha != expected:
            raise ResearchAdapterError(
                f"candidate manifest bytes SHA-256 mismatch: file={actual_raw_manifest_file_sha}, expected={expected}"
            )

        schema = str(candidate_manifest.get("schema_version") or "")
        if schema not in (
            REVISION_AWARE_RAW_SCHEMA_VERSION,
            "ml-daily-source-row-research-projection.v1",
        ):
            raise ResearchAdapterError(
                f"unsupported candidate schema for research adapter: {schema}"
            )

        canonical_candidate = dict(candidate_manifest)
        candidate_declared_canonical = canonical_candidate.pop("manifest_hash", None)
        if schema == "ml-daily-source-row-research-projection.v1":
            candidate_declared_canonical = canonical_candidate.pop("content_sha256", None)
        actual_candidate_canonical = _json_hash(canonical_candidate)
        if candidate_declared_canonical != actual_candidate_canonical:
            raise ResearchAdapterError("candidate manifest canonical self-hash mismatch")

        # 驗證研究標記：必須為 research_only
        safety = candidate_manifest.get("safety", {})
        if not candidate_manifest.get("research_only", False) and not safety.get("research_only", False):
            raise ResearchAdapterError(
                "candidate is not research_only; adapter only accepts research-only candidates"
            )
        if candidate_manifest.get("formal_dataset", False) or safety.get("formal_dataset", False):
            raise ResearchAdapterError(
                "candidate declares formal_dataset=true; adapter refuses formal datasets"
            )

        # 提取 candidate raw manifest hash 與 market revision digest
        candidate_raw_manifest_hash = str(candidate_declared_canonical or actual_raw_manifest_file_sha)
        input_pins = candidate_manifest.get("input_pins", {})
        market_rev_info = input_pins.get("market_revision", {})
        market_revision_digest = _json_hash(market_rev_info)
        # Candidate 自述不能自行提升 strict revision qualification；此 B path 尚未載入 A 的驗證 bundle。
        source_revision_qualification = "unverified_requires_separate_strict_inspection"
        snapshot_context = input_pins.get("snapshot_context", {})
        original_source_identity = snapshot_context.get("original_source_identity") if isinstance(snapshot_context, dict) else None

        # 3. 預覽模式
        if req.preview_only:
            return ResearchAdaptResult(
                status="preview_only",
                adapted_manifest_path=req.output_dir / "all_field_enriched" / "manifest.json",
                adapted_manifest_hash="",
                adapter_receipt_path=req.output_dir / "adapter_receipt.json",
                candidate_raw_manifest_hash=candidate_raw_manifest_hash,
                row_count=_strict_int(candidate_manifest.get("row_count", 0), "candidate row_count"),
                shard_count=len(candidate_manifest.get("shards", [])),
                market_revision_digest=market_revision_digest,
                formal_release_v4_pointer_untouched=True,
            )

        # 4. 準備輸出目錄 (create-only)
        if req.output_dir.exists():
            raise ResearchAdapterError(f"adapter output directory already exists; use a new request-owned path: {req.output_dir}")
        req.output_dir.mkdir(parents=True, exist_ok=False)
        self._request_output_owned = True
        child_manifest_dir = req.output_dir / "all_field_enriched"
        child_manifest_dir.mkdir(parents=False, exist_ok=False)

        # 5. 解析並轉換 Observation Rows
        adapted_shards_info, total_rows = self._transform_candidate_to_shards(
            candidate_manifest=candidate_manifest,
            manifest_path=req.raw_candidate_manifest_path,
            output_dir=child_manifest_dir,
        )

        # 6. 以標準十進位 exponent 建立 feature registry（raw scale denominator 已在輸入邊界正規化）。
        features_manifest = [
            {"feature_id": f"daily_prices.{name}", "table_name": "daily_prices", "source_id": "daily_prices", "family": "daily_prices", "scale": scale, "unit": unit, "value_type": "scaled_integer", "staleness_days": 10, "record_hash": "sha256:" + hashlib.sha256(feature_id.encode("utf-8")).hexdigest()}
            for name, feature_id, scale, unit in (
                ("開盤價", "daily_prices.open", 2, "TWD/share"),
                ("最高價", "daily_prices.high", 2, "TWD/share"),
                ("最低價", "daily_prices.low", 2, "TWD/share"),
                ("收盤價", "daily_prices.close", 2, "TWD/share"),
                ("成交股數", "daily_prices.volume", 0, "share"),
                ("成交金額", "daily_prices.amount", 0, "TWD"),
                ("成交筆數", "daily_prices.trade_count", 0, "trade"),
            )
        ]
        feature_registry_sha256 = _json_hash(features_manifest)
        freeze_identity = _json_hash({
            "available_at_or_before": self.training_as_of_utc.isoformat(),
            "candidate_manifest_bytes_sha256": actual_raw_manifest_file_sha,
            "source_manifest_content_hash": candidate_raw_manifest_hash,
        })

        adapted_manifest_payload: dict[str, Any] = {
            "schema_version": RESEARCH_ADAPTED_RAW_SCHEMA_VERSION,
            "stage": "verified_numeric_observations",
            "dataset_id": "all_field_enriched",
            "decision_at": self.training_as_of_utc.isoformat(),
            "history_start_date": "2014-01-01",
            "format": "gzip_jsonl",
            "candidate_raw_manifest_path": str(req.raw_candidate_manifest_path.resolve()),
            "candidate_raw_manifest_hash": candidate_raw_manifest_hash,
            "candidate_manifest_bytes_sha256": actual_raw_manifest_file_sha,
            "candidate_schema_version": schema,
            "training_as_of": self.training_as_of_utc.isoformat(),
            "current_observation_freeze": {
                "available_at_or_before": self.training_as_of_utc.isoformat(),
                "identity": freeze_identity,
            },
            "temporal_semantics": {
                "event_date_distinct_from_available_at": True,
                "current_restated": True,
                "historical_pit_eligible": False,
                "source_revision_qualification": source_revision_qualification,
            },
            "source_revision_qualification": source_revision_qualification,
            "original_source_identity": original_source_identity,
            "market_revision_digest": market_revision_digest,
            "created_at": self.now.isoformat(),
            "benchmark_entity_id": req.benchmark_entity_id,
            "row_count": total_rows,
            "feature_count": len(features_manifest),
            "features": features_manifest,
            "feature_registry_sha256": feature_registry_sha256,
            "shard_count": len(adapted_shards_info),
            "shards": adapted_shards_info,
            "row_schema": "ml-pit-observation.v1",
            "direct_ooc_readiness": {
                "status": "blocked_insufficient_context_or_mature_history",
                "reasons": ["single-day-or-short-history candidate has no verified TAIEX/context features or mature labels"],
                "folds_created": False,
            },
            "safety": {
                "research_only": True,
                "candidate_only": True,
                "formal_dataset": False,
                "formal_oos_allowed": False,
                "formal_training_allowed": False,
                "direct_ooc_research_compatible": False,
                "raw_float_persistence_allowed": False,
                "research_shadow_isolated": True,
                "unreviewed_included": False,
                "excluded_leakage_included": False,
                "production_alpha_bp": 0,
            },
        }

        _assert_no_float(adapted_manifest_payload, "adapted_manifest_payload")

        adapted_manifest_hash = _json_hash(adapted_manifest_payload)
        adapted_manifest_payload["manifest_hash"] = adapted_manifest_hash

        manifest_path = child_manifest_dir / "manifest.json"
        manifest_bytes = _canonical_json_bytes(adapted_manifest_payload)
        with manifest_path.open("xb") as stream:
            stream.write(manifest_bytes)
        manifest_bytes_sha256 = f"sha256:{_sha256_bytes(manifest_bytes)}"
        root_manifest = {
            "schema_version": "ml-research-adapted-raw-root.v1",
            "child_dataset_manifests": [{
                "dataset_id": "all_field_enriched",
                "path": "all_field_enriched/manifest.json",
                "canonical_sha256": adapted_manifest_hash,
                "bytes_sha256": manifest_bytes_sha256,
            }],
        }
        root_manifest["manifest_hash"] = _json_hash(root_manifest)
        with (req.output_dir / "manifest.json").open("xb") as stream:
            stream.write(_canonical_json_bytes(root_manifest))

        # 7. 全部讀回驗證通過後才建立成功 adapter receipt。
        self._verify_readback(manifest_path, manifest_bytes, adapted_shards_info)
        receipt_payload = {
            "schema_version": RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION,
            "status": "verified_numeric_observations_ready",
            "candidate_raw_manifest_path": str(req.raw_candidate_manifest_path.resolve()),
            "candidate_manifest_bytes_sha256": actual_raw_manifest_file_sha,
            "candidate_raw_manifest_hash": candidate_raw_manifest_hash,
            "adapted_manifest_path": str(manifest_path.resolve()),
            "adapted_manifest_bytes_sha256": manifest_bytes_sha256,
            "adapted_manifest_hash": adapted_manifest_hash,
            "feature_registry_sha256": feature_registry_sha256,
            "current_observation_freeze": self.training_as_of_utc.isoformat(),
            "freeze_identity": freeze_identity,
            "market_revision_digest": market_revision_digest,
            "training_as_of": self.training_as_of_utc.isoformat(),
            "row_count": total_rows,
            "shard_count": len(adapted_shards_info),
            "completed_at": _now_utc().isoformat(),
            "formal_release_v4_pointer_untouched": True,
            "formal_d_root_untouched": True,
            "research_only": True,
            "formal_credit": False,
            "historical_pit_eligible": False,
            "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
            "source_revision_qualification": source_revision_qualification,
            "original_source_identity": original_source_identity,
        }
        receipt_path = req.output_dir / "adapter_receipt.json"
        with receipt_path.open("xb") as stream:
            stream.write(_canonical_json_bytes(receipt_payload))

        return ResearchAdaptResult(
            status="verified_numeric_observations_ready",
            adapted_manifest_path=manifest_path,
            adapted_manifest_hash=adapted_manifest_hash,
            adapter_receipt_path=receipt_path,
            candidate_raw_manifest_hash=candidate_raw_manifest_hash,
            row_count=total_rows,
            shard_count=len(adapted_shards_info),
            market_revision_digest=market_revision_digest,
            formal_release_v4_pointer_untouched=True,
        )

    def _transform_candidate_to_shards(
        self,
        candidate_manifest: Mapping[str, Any],
        manifest_path: Path,
        output_dir: Path,
    ) -> tuple[list[dict[str, Any]], int]:
        """串流轉換已釘選來源列；事件日與 current availability 各自保存。"""
        schema = str(candidate_manifest.get("schema_version") or "")
        parent_dir = manifest_path.parent
        feature_info = DAILY_PRICE_FEATURE_INFO

        def observations() -> Sequence[tuple[int, dict[str, Any]]]:
            # 目前候選只涵蓋有限研究窗口；所有列會逐列驗證後落盤，禁止把零列當已支援。
            out: list[tuple[int, dict[str, Any]]] = []
            if schema == "ml-daily-source-row-research-projection.v1":
                obs_info = candidate_manifest.get("observations_file")
                if not isinstance(obs_info, dict):
                    raise ResearchAdapterError("projection observations_file descriptor is required")
                obs_path = parent_dir / str(obs_info.get("path") or "")
                if not obs_path.is_file() or _sha256_file(obs_path) != str(obs_info.get("sha256", "")).removeprefix("sha256:"):
                    raise ResearchAdapterError("projection observations bytes SHA-256 mismatch")
                if obs_path.stat().st_size != _strict_int(obs_info.get("bytes"), "observations_file.bytes"):
                    raise ResearchAdapterError("projection observations byte length mismatch")
                input_files = candidate_manifest.get("input_files")
                if not isinstance(input_files, dict) or not input_files:
                    raise ResearchAdapterError("projection input_files pins are missing")
                for relative, pin in input_files.items():
                    input_path = (parent_dir / relative).resolve()
                    if not input_path.is_relative_to(parent_dir.resolve()) or not input_path.is_file():
                        raise ResearchAdapterError("projection input file is missing or escapes its root")
                    if _sha256_file(input_path) != str(pin.get("sha256", "")).removeprefix("sha256:"):
                        raise ResearchAdapterError(f"projection copied input pin mismatch: {relative}")
                terminal_path = parent_dir / "runner_terminal_verification_receipt.json"
                if not terminal_path.is_file():
                    raise ResearchAdapterError("projection has no terminal verification receipt")
                terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
                if terminal.get("terminal_status") != "completed_research_only" or terminal.get("historical_pit_eligible") is not False:
                    raise ResearchAdapterError("projection terminal receipt does not qualify as current-observed input")
                row_count = 0
                with obs_path.open("r", encoding="utf-8") as stream:
                    for line_no, line in enumerate(stream, 1):
                        if not line.endswith("\n") or not line.strip():
                            raise ResearchAdapterError(f"projection line {line_no} is empty or unterminated")
                        item = json.loads(line)
                        sym = item.get("symbol")
                        if not isinstance(sym, str) or not re.fullmatch(r"\d{4,6}[A-Za-z]?[A-Za-z0-9]*", sym):
                            raise ResearchAdapterError(f"projection symbol is invalid at line {line_no}")
                        raw_date = item.get("source_date")
                        try:
                            event_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
                        except ValueError as exc:
                            raise ResearchAdapterError("projection source_date is invalid") from exc
                        if event_date is None:
                            raise ResearchAdapterError("projection source_date must be ISO YYYY-MM-DD")
                        raw_avail = item.get("source_available_at")
                        try:
                            available_at = _strict_aware_utc(datetime.fromisoformat(raw_avail), "source_available_at")
                        except (ValueError, TypeError) as exc:
                            raise ResearchAdapterError("projection source_available_at is invalid") from exc
                        if available_at > self.training_as_of_utc:
                            raise ResearchAdapterError("projection source availability is after the explicit freeze")
                        exact = item.get("exact_numeric_values")
                        if not isinstance(exact, dict):
                            raise ResearchAdapterError("projection exact_numeric_values is not an object")
                        venue = item.get("venue")
                        source_pin = {
                            "raw_response_sha256": item.get("source_raw_response_sha256"),
                            "source_receipt_sha256": item.get("source_receipt_sha256"),
                            "source_row_index": _strict_int(item.get("source_row_index"), "source_row_index"),
                        }
                        if not isinstance(source_pin["raw_response_sha256"], str) or not isinstance(source_pin["source_receipt_sha256"], str):
                            raise ResearchAdapterError("projection source row pins are incomplete")
                        if not all(str(source_pin[key]) in {str(pin.get("sha256")) for pin in input_files.values()} for key in ("raw_response_sha256", "source_receipt_sha256")):
                            raise ResearchAdapterError("projection row source pins do not match copied source bytes")
                        values: list[dict[str, Any]] = []
                        missing: list[str] = []
                        for feature_id in DAILY_PRICE_FEATURE_INFO:
                            selected = _projection_exact_value(
                                exact, venue=venue, feature_id=feature_id
                            )
                            if selected is None:
                                missing.append(feature_id)
                                continue
                            source_name, raw_value = selected
                            if not isinstance(raw_value, dict):
                                if raw_value is None:
                                    missing.append(feature_id)
                                    continue
                                raise ResearchAdapterError(f"projection numeric {source_name} has invalid schema")
                            if raw_value.get("state") == "source_missing":
                                missing.append(feature_id)
                                continue
                            if raw_value.get("state") not in (None, "numeric"):
                                raise ResearchAdapterError(
                                    f"projection numeric {source_name} has a non-numeric source state"
                                )
                            source_int = _strict_int(raw_value.get("value_int"), f"{source_name}.value_int")
                            denominator = _strict_int(raw_value.get("scale"), f"{source_name}.scale")
                            exponent = 0
                            rest = denominator
                            while rest > 1 and rest % 10 == 0:
                                exponent += 1
                                rest //= 10
                            if rest != 1 or exponent != feature_info[feature_id][0]:
                                raise ResearchAdapterError(f"projection {source_name} denominator does not match standard exponent")
                            values.append(self._feature_value(feature_id, source_int, exponent, source_pin, feature_info[feature_id][1]))
                        if not values and not missing:
                            raise ResearchAdapterError("projection observation has neither numeric values nor typed missing masks")
                        row = self._build_adapted_record(sym, event_date, available_at, values, missing, source_pin)
                        out.append((event_date.year, row))
                        row_count += 1
                if row_count != _strict_int(obs_info.get("row_count"), "observations_file.row_count"):
                    raise ResearchAdapterError("projection observations declared row count mismatch")
            elif schema == REVISION_AWARE_RAW_SCHEMA_VERSION:
                shards = candidate_manifest.get("shards")
                if not isinstance(shards, list) or not shards:
                    raise ResearchAdapterError("revision-aware candidate shards are missing")
                for meta in shards:
                    if not isinstance(meta, dict) or not isinstance(meta.get("path"), str):
                        raise ResearchAdapterError("candidate shard metadata is invalid")
                    shard = (parent_dir / meta["path"]).resolve()
                    if not shard.is_relative_to(parent_dir.resolve()) or not shard.is_file():
                        raise ResearchAdapterError("candidate shard missing or path escapes manifest root")
                    compressed_expected = str(meta.get("compressed_sha256") or meta.get("file_sha256") or "")
                    if not compressed_expected or f"sha256:{_sha256_file(shard)}" != compressed_expected:
                        raise ResearchAdapterError("candidate compressed shard SHA-256 mismatch")
                    shard_count = 0
                    digest = hashlib.sha256()
                    try:
                        with gzip.open(shard, "rb") as stream:
                            while line_bytes := stream.readline():
                                digest.update(line_bytes)
                                row = json.loads(line_bytes.decode("utf-8"))
                                event_raw = row.get("event_date") or str(row.get("event_at", ""))[:10]
                                event_date = date.fromisoformat(event_raw)
                                available = _strict_aware_utc(datetime.fromisoformat(row.get("available_at", "")), "available_at")
                                if available > self.training_as_of_utc:
                                    raise ResearchAdapterError("candidate row availability is after the explicit freeze")
                                sym = row.get("symbol")
                                if not isinstance(sym, str) or not sym:
                                    raise ResearchAdapterError("candidate row symbol is missing")
                                source_provenance = row.get("source_version")
                                if not isinstance(source_provenance, dict) or not source_provenance:
                                    raise ResearchAdapterError("candidate row source version metadata is missing")
                                value_rows = row.get("values")
                                if not isinstance(value_rows, list):
                                    raise ResearchAdapterError("candidate row values schema is invalid")
                                values = []
                                seen_ids: set[str] = set()
                                for raw_value in value_rows:
                                    if not isinstance(raw_value, dict):
                                        raise ResearchAdapterError("candidate feature value is invalid")
                                    candidate_feature_id = raw_value.get("feature_id")
                                    if not isinstance(candidate_feature_id, str) or not candidate_feature_id:
                                        raise ResearchAdapterError("candidate feature id is missing or invalid")
                                    feature_id = candidate_feature_id
                                    if feature_id not in feature_info or feature_id in seen_ids:
                                        raise ResearchAdapterError("candidate feature id is unsupported or duplicated")
                                    seen_ids.add(feature_id)
                                    value_int = _strict_int(raw_value.get("value_int"), "candidate value_int")
                                    exponent = _strict_int(raw_value.get("scale"), "candidate scale")
                                    expected_exp = feature_info[feature_id][0]
                                    if exponent != expected_exp:
                                        raise ResearchAdapterError("candidate feature exponent does not match registry")
                                    values.append(self._feature_value(feature_id, value_int, exponent, source_provenance, feature_info[feature_id][1]))
                                missing = row.get("missing_mask", [])
                                if not isinstance(missing, list) or any(not isinstance(x, str) for x in missing):
                                    raise ResearchAdapterError("candidate missing mask schema is invalid")
                                adapted = self._build_adapted_record(sym, event_date, available, values, missing, source_provenance)
                                out.append((event_date.year, adapted))
                                shard_count += 1
                    except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ResearchAdapterError(f"candidate gzip shard is truncated or malformed: {shard}") from exc
                    if shard_count != _strict_int(meta.get("row_count"), "candidate shard row_count"):
                        raise ResearchAdapterError("candidate shard row_count mismatch")
                    expected_uncompressed = str(meta.get("uncompressed_sha256") or meta.get("observations_sha256") or "")
                    if expected_uncompressed and f"sha256:{digest.hexdigest()}" != expected_uncompressed:
                        raise ResearchAdapterError("candidate uncompressed shard SHA-256 mismatch")
            if not out:
                raise ResearchAdapterError("candidate produced zero verified numeric observations")
            return out

        converted = observations()
        by_year: dict[int, list[dict[str, Any]]] = {}
        for year, row in converted:
            by_year.setdefault(year, []).append(row)
        adapted_shards: list[dict[str, Any]] = []
        total = 0
        for year, rows in sorted(by_year.items()):
            rel_path = f"shards/{year}/observations.jsonl.gz"
            shard_path = output_dir / rel_path
            shard_path.parent.mkdir(parents=True, exist_ok=True)
            uncompressed = hashlib.sha256()
            min_avail: str | None = None
            max_avail: str | None = None
            with shard_path.open("xb") as raw:
                with gzip.GzipFile(filename="", mode="wb", compresslevel=6, fileobj=raw, mtime=0) as gz:
                    for row in rows:
                        encoded = _canonical_json_bytes(row) + b"\n"
                        gz.write(encoded)
                        uncompressed.update(encoded)
                        available = row["available_at"]
                        min_avail = available if min_avail is None else min(min_avail, available)
                        max_avail = available if max_avail is None else max(max_avail, available)
            compressed_sha = f"sha256:{_sha256_file(shard_path)}"
            uncompressed_sha = f"sha256:{uncompressed.hexdigest()}"
            adapted_shards.append({
                "year": year,
                "path": rel_path,
                "compressed_sha256": compressed_sha,
                "uncompressed_sha256": uncompressed_sha,
                "file_sha256": compressed_sha,
                "observations_sha256": uncompressed_sha,
                "row_count": len(rows),
                "min_available_at": min_avail,
                "max_available_at": max_avail,
                "row_schema": "ml-pit-observation.v1",
            })
            total += len(rows)
        return adapted_shards, total

    @staticmethod
    def _feature_value(feature_id: str, value_int: int, exponent: int, source: Mapping[str, Any], unit: str) -> dict[str, Any]:
        identity = {
            "feature_id": feature_id,
            "value_int": value_int,
            "scale": exponent,
            "source_pin": dict(source),
        }
        return {
            "feature_id": feature_id,
            "value_int": value_int,
            "scale": exponent,
            "unit": unit,
            "source_value_hash": _json_hash(identity),
            "source_value_hash_semantics": "derived_from_verified_candidate_row_and_source_pins",
            "formal_training_eligible": False,
        }

    @staticmethod
    def _build_adapted_record(
        symbol: str,
        event_date: date,
        available_at: datetime,
        values: list[dict[str, Any]],
        missing_mask: list[str],
        source_provenance: Mapping[str, Any],
    ) -> dict[str, Any]:
        identity = {
            "symbol": symbol,
            "event_date": event_date.isoformat(),
            "available_at": available_at.isoformat(),
            "source_provenance": dict(source_provenance),
            "values": values,
        }
        return {
            "schema_version": "ml-pit-observation.v1",
            "dataset_id": "all_field_enriched",
            "pit_status": "current_observed_non_pit",
            "current_restated": True,
            "historical_pit_eligible": False,
            "entity_id": symbol,
            "symbol": symbol,
            "source_table": "daily_prices",
            "table_name": "daily_prices",
            "source_id": "daily_prices",
            "family": "daily_prices",
            "event_date": event_date.isoformat(),
            "event_at": event_date.isoformat(),
            "available_at": available_at.isoformat(),
            "source_available_at": available_at.isoformat(),
            "source_version": dict(source_provenance),
            "values": values,
            "missing_mask": missing_mask,
            "quality_blocked_mask": [],
            "staleness_mask": [],
            "source_projection_row_identity_hash": _json_hash(identity),
            "source_row_hash_semantics": "derived_candidate_row_identity_not_original_source_row_hash",
        }

    def _verify_readback(
        self,
        manifest_path: Path,
        manifest_bytes: bytes,
        shards_info: list[dict[str, Any]],
    ) -> None:
        """串流讀回校驗 adapted 產物。"""
        if manifest_path.read_bytes() != manifest_bytes:
            raise ResearchAdapterError("adapted manifest readback mismatch")

        base_dir = manifest_path.parent
        for shard in shards_info:
            shard_path = base_dir / shard["path"]
            if not shard_path.exists():
                raise ResearchAdapterError(f"adapted shard file missing: {shard_path}")

            actual_file_sha = f"sha256:{_sha256_file(shard_path)}"
            if actual_file_sha != shard["file_sha256"] or actual_file_sha != shard.get("compressed_sha256"):
                raise ResearchAdapterError(
                    f"adapted shard file sha mismatch: {shard_path}"
                )

            obs_hasher = hashlib.sha256()
            read_count = 0
            try:
                with gzip.open(shard_path, "rb") as gz:
                    while line := gz.readline():
                        obs_hasher.update(line)
                        row = json.loads(line.decode("utf-8"))
                        if row.get("schema_version") != "ml-pit-observation.v1":
                            raise ResearchAdapterError("adapted row schema version mismatch")
                        if row.get("historical_pit_eligible") is not False or row.get("current_restated") is not True:
                            raise ResearchAdapterError("adapted row temporal semantics are invalid")
                        if not isinstance(row.get("missing_mask"), list) or not isinstance(row.get("quality_blocked_mask"), list) or not isinstance(row.get("staleness_mask"), list):
                            raise ResearchAdapterError("adapted row masks are missing")
                        if not row.get("source_projection_row_identity_hash"):
                            raise ResearchAdapterError("adapted row source identity hash is missing")
                        try:
                            available = datetime.fromisoformat(row["available_at"])
                        except (KeyError, TypeError, ValueError) as exc:
                            raise ResearchAdapterError("adapted row available_at is invalid") from exc
                        _strict_aware_utc(available, "adapted row available_at")
                        values = row.get("values")
                        if not isinstance(values, list) or (not values and not row.get("missing_mask")):
                            raise ResearchAdapterError("adapted row must contain values or typed missing masks")
                        for value in values:
                            if not isinstance(value, dict):
                                raise ResearchAdapterError("adapted feature value is invalid")
                            _strict_int(value.get("value_int"), "adapted value_int")
                            scale = _strict_int(value.get("scale"), "adapted scale")
                            if scale < 0 or scale > 12 or not str(value.get("source_value_hash", "")).startswith("sha256:"):
                                raise ResearchAdapterError("adapted feature scale or source hash is invalid")
                        read_count += 1
            except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ResearchAdapterError(f"adapted gzip shard is truncated or malformed: {shard_path}") from exc

            actual_obs_sha = f"sha256:{obs_hasher.hexdigest()}"
            if actual_obs_sha != shard["observations_sha256"] or actual_obs_sha != shard.get("uncompressed_sha256"):
                raise ResearchAdapterError(
                    f"adapted shard observations sha mismatch: {shard_path}"
                )
            if read_count != shard["row_count"]:
                raise ResearchAdapterError(
                    f"adapted shard row count mismatch: {read_count} != {shard['row_count']}"
                )


class ResearchDirectNumericStoreConsumer:
    """隔離的研究 Direct Numeric Store 消費器。

    使用 adapter receipt 與 adapted manifest 進行隔離消費，生成研究用數值 store，
    絕不修改 formal release_v4 pointer 或正式 D: 資料根目錄。
    """

    def __init__(
        self,
        adapter_receipt_path: Path,
        output_store_dir: Path,
        training_as_of: str | datetime,
        benchmark_entity_id: str = "TAIEX",
    ) -> None:
        self.adapter_receipt_path = adapter_receipt_path
        self.output_store_dir = output_store_dir
        raw_freeze = training_as_of
        if isinstance(raw_freeze, str):
            try:
                raw_freeze = datetime.fromisoformat(raw_freeze)
            except ValueError as exc:
                raise ResearchAdapterError("training_as_of must be an ISO-8601 timestamp with timezone") from exc
        self.training_as_of_utc = _strict_aware_utc(raw_freeze, "training_as_of")
        self.benchmark_entity_id = benchmark_entity_id
        self._request_output_owned = False

    def build_store(self) -> dict[str, Any]:
        self._request_output_owned = False
        try:
            return self._build_store_once()
        except Exception as exc:
            _write_owned_failure_receipt(
                self.output_store_dir,
                owned=self._request_output_owned,
                schema_version="ml-research-numeric-store-failure.v1",
                exc=exc,
            )
            raise

    def _build_store_once(self) -> dict[str, Any]:
        _resolve_research_path(self.output_store_dir, "consumer output_store_dir")
        raw_receipt = self.adapter_receipt_path.read_bytes()
        adapter_receipt = json.loads(raw_receipt.decode("utf-8"))
        if adapter_receipt.get("schema_version") != RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION:
            raise ResearchAdapterError("invalid adapter receipt schema")
        if adapter_receipt.get("status") != "verified_numeric_observations_ready":
            raise ResearchAdapterError("adapter receipt has no verified numeric observations")
        artifact = _load_verified_adapter_artifact(
            self.adapter_receipt_path,
            expected_candidate_manifest_bytes_sha256=str(adapter_receipt.get("candidate_manifest_bytes_sha256") or ""),
            expected_adapted_manifest_canonical_sha256=str(adapter_receipt.get("adapted_manifest_hash") or ""),
            expected_feature_registry_sha256=str(adapter_receipt.get("feature_registry_sha256") or ""),
            available_at_or_before=self.training_as_of_utc,
        )
        if self.output_store_dir.exists():
            raise ResearchAdapterError("consumer output already exists; safe retry requires a new request-owned path")
        self.output_store_dir.mkdir(parents=True, exist_ok=False)
        self._request_output_owned = True
        (self.output_store_dir / "shards").mkdir()
        registry_bytes = _canonical_json_bytes(_deep_plain(artifact.feature_registry))
        with (self.output_store_dir / "feature_registry.json").open("xb") as stream:
            stream.write(registry_bytes)

        adapted_path = Path(str(adapter_receipt["adapted_manifest_path"]))
        stored_shards: list[dict[str, Any]] = []
        for shard_meta in json.loads(adapted_path.read_text(encoding="utf-8")).get("shards", []):
            source = adapted_path.parent / shard_meta["path"]
            relative = Path("shards") / Path(shard_meta["path"]).name if len(Path(shard_meta["path"]).parts) == 1 else Path("shards") / Path(shard_meta["path"]).parts[-2] / Path(shard_meta["path"]).name
            target = self.output_store_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not source.is_file():
                raise ResearchAdapterError("adapted numeric shard disappeared before store copy")
            with source.open("rb") as src, target.open("xb") as stream:
                shutil.copyfileobj(src, stream, length=1024 * 1024)
            target_sha = f"sha256:{_sha256_file(target)}"
            source_sha = f"sha256:{_sha256_file(source)}"
            if target_sha != source_sha:
                raise ResearchAdapterError("copied numeric shard readback SHA-256 mismatch")
            if target_sha != _normalized_pin(str(shard_meta.get("compressed_sha256") or ""), "source compressed shard pin"):
                raise ResearchAdapterError("copied numeric shard differs from verified source descriptor")
            _verify_stored_gzip_jsonl(
                target,
                expected_compressed_sha256=target_sha,
                expected_uncompressed_sha256=str(shard_meta["uncompressed_sha256"]),
                expected_row_count=_strict_int(shard_meta["row_count"], "shard row_count"),
            )
            stored_shards.append({
                "path": relative.as_posix(),
                "bytes_sha256": target_sha,
                "compressed_sha256": shard_meta["compressed_sha256"],
                "uncompressed_sha256": shard_meta["uncompressed_sha256"],
                "row_count": _strict_int(shard_meta["row_count"], "shard row_count"),
            })

        store_meta = {
            "schema_version": "ml-research-verified-numeric-observations.v1",
            "status": "verified_numeric_observations_ready",
            "candidate_manifest_bytes_sha256": artifact.candidate_manifest_bytes_sha256,
            "adapted_manifest_bytes_sha256": artifact.adapted_manifest_bytes_sha256,
            "adapted_manifest_canonical_sha256": artifact.adapted_manifest_canonical_sha256,
            "feature_registry_sha256": artifact.feature_registry_sha256,
            "feature_registry_path": "feature_registry.json",
            "record_count": len(artifact.observations),
            "feature_value_count": sum(len(row.values) for row in artifact.observations),
            "stored_shards": stored_shards,
            "benchmark_entity_id": self.benchmark_entity_id,
            "current_observation_freeze": artifact.current_observation_freeze.isoformat(),
            "freeze_identity": artifact.freeze_identity,
            "historical_pit_eligible": False,
            "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
            "source_revision_qualification": artifact.source_pins["source_revision_qualification"],
            "original_source_identity": _deep_plain(artifact.source_pins["original_source_identity"]),
            "research_only": True,
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
        }
        meta_bytes = _canonical_json_bytes(store_meta)
        with (self.output_store_dir / "store_metadata.json").open("xb") as stream:
            stream.write(meta_bytes)
        if (self.output_store_dir / "store_metadata.json").read_bytes() != meta_bytes:
            raise ResearchAdapterError("store metadata readback differs from bytes written")
        registry_readback = json.loads((self.output_store_dir / "feature_registry.json").read_text(encoding="utf-8"))
        if _json_hash(registry_readback) != artifact.feature_registry_sha256:
            raise ResearchAdapterError("stored feature registry readback hash mismatch")

        consumption_receipt = {
            "schema_version": RESEARCH_DIRECT_STORE_RECEIPT_SCHEMA_VERSION,
            "status": "verified_numeric_observations_ready",
            "adapter_receipt_path": str(self.adapter_receipt_path.resolve()),
            "adapter_receipt_bytes_sha256": f"sha256:{_sha256_bytes(raw_receipt)}",
            "candidate_manifest_bytes_sha256": artifact.candidate_manifest_bytes_sha256,
            "adapted_manifest_bytes_sha256": artifact.adapted_manifest_bytes_sha256,
            "adapted_manifest_canonical_sha256": artifact.adapted_manifest_canonical_sha256,
            "feature_registry_sha256": artifact.feature_registry_sha256,
            "store_metadata_sha256": f"sha256:{_sha256_bytes(meta_bytes)}",
            "current_observation_freeze": artifact.current_observation_freeze.isoformat(),
            "freeze_identity": artifact.freeze_identity,
            "record_count": len(artifact.observations),
            "feature_value_count": sum(len(row.values) for row in artifact.observations),
            "stored_shards": stored_shards,
            "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
            "direct_ooc_blockers": ["verified TAIEX/context features and mature labels are not present in this candidate"],
            "historical_pit_eligible": False,
            "source_revision_qualification": artifact.source_pins["source_revision_qualification"],
            "original_source_identity": _deep_plain(artifact.source_pins["original_source_identity"]),
            "formal_release_v4_pointer_untouched": True,
            "formal_d_root_untouched": True,
            "research_only": True,
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
            "completed_at": _now_utc().isoformat(),
        }
        receipt_path = self.output_store_dir / "consumption_receipt.json"
        with receipt_path.open("xb") as stream:
            stream.write(_canonical_json_bytes(consumption_receipt))
        return consumption_receipt


def _normalized_pin(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchAdapterError(f"{field_name} is required")
    normalized = value.strip().lower()
    if not normalized.startswith("sha256:"):
        normalized = f"sha256:{normalized}"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized):
        raise ResearchAdapterError(f"{field_name} must be a SHA-256 pin")
    return normalized


def _verify_candidate_input_bytes(candidate_path: Path, candidate: Mapping[str, Any]) -> None:
    schema = candidate.get("schema_version")
    if schema == "ml-daily-source-row-research-projection.v1":
        input_files = candidate.get("input_files")
        if not isinstance(input_files, dict) or not input_files:
            raise ResearchAdapterError("candidate projection has no input bytes pins")
        root = candidate_path.parent.resolve()
        for relative, pin in input_files.items():
            if not isinstance(relative, str) or not isinstance(pin, dict):
                raise ResearchAdapterError("candidate projection input pin schema is invalid")
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ResearchAdapterError(f"candidate projection input missing or outside root: {relative}")
            expected_hash = _normalized_pin(str(pin.get("sha256", "")), f"input_files.{relative}.sha256")
            if f"sha256:{_sha256_file(path)}" != expected_hash:
                raise ResearchAdapterError(f"candidate projection input bytes mismatch: {relative}")
            if path.stat().st_size != _strict_int(pin.get("bytes"), f"input_files.{relative}.bytes"):
                raise ResearchAdapterError(f"candidate projection input length mismatch: {relative}")
    elif schema == REVISION_AWARE_RAW_SCHEMA_VERSION:
        for item in candidate.get("input_pins", {}).get("source_custody", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ResearchAdapterError("candidate source custody pin is invalid")
            path = Path(item["path"])
            if not path.is_file() or _sha256_file(path) != str(item.get("sha256", "")):
                raise ResearchAdapterError("candidate source custody manifest bytes changed")


def _load_verified_adapter_artifact(
    adapter_receipt_path: Path,
    *,
    expected_candidate_manifest_bytes_sha256: str,
    expected_adapted_manifest_canonical_sha256: str,
    expected_feature_registry_sha256: str,
    available_at_or_before: datetime,
) -> VerifiedMLResearchNumericArtifact:
    freeze = _strict_aware_utc(available_at_or_before, "available_at_or_before")
    receipt_bytes = adapter_receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if receipt.get("schema_version") != RESEARCH_ADAPTER_RECEIPT_SCHEMA_VERSION:
        raise ResearchAdapterError("adapter receipt schema is invalid")
    if receipt.get("status") != "verified_numeric_observations_ready":
        raise ResearchAdapterError("adapter receipt status is not verified_numeric_observations_ready")

    candidate_expected = _normalized_pin(expected_candidate_manifest_bytes_sha256, "expected_candidate_manifest_bytes_sha256")
    candidate_actual = _normalized_pin(str(receipt.get("candidate_manifest_bytes_sha256", "")), "receipt candidate_manifest_bytes_sha256")
    if candidate_expected != candidate_actual:
        raise ResearchAdapterError("caller candidate manifest bytes pin differs from adapter receipt")
    candidate_path = Path(str(receipt.get("candidate_raw_manifest_path") or ""))
    if not candidate_path.is_file():
        raise ResearchAdapterError("candidate raw manifest is missing")
    candidate_bytes = candidate_path.read_bytes()
    if f"sha256:{_sha256_bytes(candidate_bytes)}" != candidate_expected:
        raise ResearchAdapterError("candidate raw manifest actual bytes SHA-256 mismatch")
    candidate = json.loads(candidate_bytes.decode("utf-8"))
    canonical = dict(candidate)
    schema = candidate.get("schema_version")
    declared = canonical.pop("manifest_hash", None)
    if schema == "ml-daily-source-row-research-projection.v1":
        declared = canonical.pop("content_sha256", None)
    if declared != _json_hash(canonical):
        raise ResearchAdapterError("candidate canonical hash does not match actual manifest content")
    _verify_candidate_input_bytes(candidate_path, candidate)

    adapted_path = Path(str(receipt.get("adapted_manifest_path") or ""))
    if not adapted_path.is_file():
        raise ResearchAdapterError("adapted child manifest is missing")
    adapted_bytes = adapted_path.read_bytes()
    adapted_bytes_sha = f"sha256:{_sha256_bytes(adapted_bytes)}"
    expected_adapted = _normalized_pin(expected_adapted_manifest_canonical_sha256, "expected_adapted_manifest_canonical_sha256")
    receipt_adapted = _normalized_pin(str(receipt.get("adapted_manifest_hash", "")), "receipt adapted_manifest_hash")
    if expected_adapted != receipt_adapted:
        raise ResearchAdapterError("caller adapted canonical hash differs from adapter receipt")
    if adapted_bytes_sha != _normalized_pin(str(receipt.get("adapted_manifest_bytes_sha256", "")), "receipt adapted_manifest_bytes_sha256"):
        raise ResearchAdapterError("adapted manifest bytes SHA-256 mismatch")
    adapted = json.loads(adapted_bytes.decode("utf-8"))
    adapted_body = dict(adapted)
    declared_adapted = adapted_body.pop("manifest_hash", None)
    canonical_adapted = _json_hash(adapted_body)
    if declared_adapted != canonical_adapted or canonical_adapted != expected_adapted:
        raise ResearchAdapterError("adapted manifest canonical SHA-256 mismatch")
    candidate_input_pins = candidate.get("input_pins", {})
    candidate_snapshot_context = candidate_input_pins.get("snapshot_context", {}) if isinstance(candidate_input_pins, dict) else {}
    original_source_identity = (
        candidate_snapshot_context.get("original_source_identity")
        if isinstance(candidate_snapshot_context, dict)
        else None
    )
    source_revision_qualification = "unverified_requires_separate_strict_inspection"
    if (
        adapted.get("source_revision_qualification") != source_revision_qualification
        or adapted.get("temporal_semantics", {}).get("source_revision_qualification") != source_revision_qualification
        or adapted.get("original_source_identity") != original_source_identity
    ):
        raise ResearchAdapterError("adapted source revision qualification/context differs from pinned candidate")

    registry = adapted.get("features")
    if not isinstance(registry, list) or not registry:
        raise ResearchAdapterError("adapted feature registry is missing")
    registry_hash = _json_hash(registry)
    expected_registry = _normalized_pin(expected_feature_registry_sha256, "expected_feature_registry_sha256")
    if registry_hash != expected_registry or registry_hash != _normalized_pin(str(receipt.get("feature_registry_sha256", "")), "receipt feature_registry_sha256"):
        raise ResearchAdapterError("feature registry canonical SHA-256 mismatch")
    registry_by_id: dict[str, Mapping[str, Any]] = {}
    for entry in registry:
        if not isinstance(entry, dict) or not isinstance(entry.get("feature_id"), str):
            raise ResearchAdapterError("feature registry entry schema is invalid")
        scale = _strict_int(entry.get("scale"), "feature registry scale")
        if scale < 0 or scale > 12:
            raise ResearchAdapterError("feature registry scale is outside the supported range")
        if entry["feature_id"] in registry_by_id:
            raise ResearchAdapterError("feature registry contains duplicate feature IDs")
        registry_by_id[entry["feature_id"]] = entry

    freeze_text = receipt.get("current_observation_freeze")
    if not isinstance(freeze_text, str):
        raise ResearchAdapterError("adapter receipt lacks explicit current-observation freeze")
    try:
        receipt_freeze = _strict_aware_utc(datetime.fromisoformat(freeze_text), "receipt freeze")
    except ValueError as exc:
        raise ResearchAdapterError("adapter receipt freeze is invalid") from exc
    if receipt_freeze != freeze:
        raise ResearchAdapterError("caller available_at_or_before does not match immutable artifact freeze")
    freeze_identity = _normalized_pin(str(receipt.get("freeze_identity", "")), "receipt freeze_identity")

    shard_rows_total = 0
    observations: list[VerifiedNumericObservation] = []
    for shard_meta in adapted.get("shards", []):
        if not isinstance(shard_meta, dict) or not isinstance(shard_meta.get("path"), str):
            raise ResearchAdapterError("adapted shard descriptor is invalid")
        shard_path = (adapted_path.parent / shard_meta["path"]).resolve()
        if not shard_path.is_relative_to(adapted_path.parent.resolve()) or not shard_path.is_file():
            raise ResearchAdapterError("adapted shard is missing or escapes child manifest root")
        compressed = _normalized_pin(str(shard_meta.get("compressed_sha256") or ""), "shard compressed_sha256")
        uncompressed = _normalized_pin(str(shard_meta.get("uncompressed_sha256") or ""), "shard uncompressed_sha256")
        if f"sha256:{_sha256_file(shard_path)}" != compressed:
            raise ResearchAdapterError("adapted compressed shard actual bytes SHA-256 mismatch")
        row_count = 0
        hasher = hashlib.sha256()
        try:
            with gzip.open(shard_path, "rb") as stream:
                while line := stream.readline():
                    hasher.update(line)
                    row = json.loads(line.decode("utf-8"))
                    if row.get("schema_version") != "ml-pit-observation.v1" or row.get("historical_pit_eligible") is not False:
                        raise ResearchAdapterError("adapted observation row typed schema or PIT status is invalid")
                    sym = row.get("symbol")
                    if not isinstance(sym, str) or not sym:
                        raise ResearchAdapterError("adapted observation symbol is missing")
                    event_date = row.get("event_date")
                    if not isinstance(event_date, str) or len(event_date) != 10 or date.fromisoformat(event_date).isoformat() != event_date:
                        raise ResearchAdapterError("adapted event_date is not normalized ISO YYYY-MM-DD")
                    available = _strict_aware_utc(datetime.fromisoformat(row.get("available_at", "")), "observation available_at")
                    if available > freeze:
                        raise ResearchAdapterError("observation source clock is after the immutable freeze")
                    if row.get("event_at") != event_date:
                        raise ResearchAdapterError("event_at must preserve the normalized event date without invented time")
                    masks = {key: row.get(key) for key in ("missing_mask", "quality_blocked_mask", "staleness_mask")}
                    if any(not isinstance(mask, list) or any(not isinstance(item, str) for item in mask) for mask in masks.values()):
                        raise ResearchAdapterError("observation masks have invalid typed shape")
                    values = row.get("values")
                    if not isinstance(values, list) or (not values and not masks["missing_mask"]):
                        raise ResearchAdapterError("observation must contain values or typed missing masks")
                    normalized_values: list[Mapping[str, Any]] = []
                    seen_ids: set[str] = set()
                    for value in values:
                        if not isinstance(value, dict):
                            raise ResearchAdapterError("numeric value typed row is invalid")
                        feature_id = value.get("feature_id")
                        if not isinstance(feature_id, str) or feature_id not in registry_by_id or feature_id in seen_ids:
                            raise ResearchAdapterError("numeric value feature ID is absent or duplicated")
                        seen_ids.add(feature_id)
                        integer = _strict_int(value.get("value_int"), "numeric value_int")
                        scale = _strict_int(value.get("scale"), "numeric value scale")
                        if scale != _strict_int(registry_by_id[feature_id].get("scale"), "registry scale"):
                            raise ResearchAdapterError("numeric value exponent differs from verified feature registry")
                        if value.get("formal_training_eligible") is not False or not str(value.get("source_value_hash", "")).startswith("sha256:"):
                            raise ResearchAdapterError("numeric value source hash or research eligibility is invalid")
                        normalized_values.append({**value, "value_int": integer, "scale": scale})
                    identity_hash = row.get("source_projection_row_identity_hash")
                    if not isinstance(identity_hash, str) or not identity_hash.startswith("sha256:"):
                        raise ResearchAdapterError("observation source row identity hash is missing")
                    observations.append(VerifiedNumericObservation(
                        symbol=sym,
                        event_date=event_date,
                        available_at=available,
                        values=tuple(_deep_freeze(value) for value in normalized_values),
                        missing_mask=tuple(masks["missing_mask"]),
                        quality_blocked_mask=tuple(masks["quality_blocked_mask"]),
                        staleness_mask=tuple(masks["staleness_mask"]),
                        source_projection_row_identity_hash=identity_hash,
                    ))
                    row_count += 1
        except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, ResearchAdapterError):
                raise
            raise ResearchAdapterError(f"adapted shard is truncated or malformed: {shard_path}") from exc
        if row_count != _strict_int(shard_meta.get("row_count"), "adapted shard row_count"):
            raise ResearchAdapterError("adapted shard row_count mismatch")
        if f"sha256:{hasher.hexdigest()}" != uncompressed:
            raise ResearchAdapterError("adapted decompressed shard SHA-256 mismatch")
        shard_rows_total += row_count
    if not observations or shard_rows_total != _strict_int(adapted.get("row_count"), "adapted manifest row_count"):
        raise ResearchAdapterError("adapted numeric artifact has zero rows or a row_count mismatch")

    source_pins = {
        "candidate_manifest_bytes_sha256": candidate_expected,
        "candidate_raw_manifest_canonical_sha256": str(declared),
        "adapted_manifest_bytes_sha256": adapted_bytes_sha,
        "adapted_manifest_canonical_sha256": canonical_adapted,
        "feature_registry_sha256": registry_hash,
        "adapter_receipt_bytes_sha256": f"sha256:{_sha256_bytes(receipt_bytes)}",
        "market_revision_digest": receipt.get("market_revision_digest"),
        "source_revision_qualification": source_revision_qualification,
        "original_source_identity": original_source_identity,
    }
    return VerifiedMLResearchNumericArtifact(
        status="verified_numeric_observations_ready",
        observations=tuple(observations),
        feature_registry=tuple(_deep_freeze(entry) for entry in registry),
        feature_registry_sha256=registry_hash,
        candidate_manifest_bytes_sha256=candidate_expected,
        adapted_manifest_bytes_sha256=adapted_bytes_sha,
        adapted_manifest_canonical_sha256=canonical_adapted,
        source_pins=_deep_freeze(source_pins),
        current_observation_freeze=freeze,
        freeze_identity=freeze_identity,
        historical_pit_eligible=False,
    )


def load_verified_ml_research_numeric_artifact(
    consumption_receipt_path: Path,
    *,
    expected_consumption_receipt_sha256: str,
    expected_candidate_manifest_bytes_sha256: str,
    expected_adapted_manifest_canonical_sha256: str,
    expected_feature_registry_sha256: str,
    available_at_or_before: datetime,
) -> VerifiedMLResearchNumericArtifact:
    """載入已釘選研究數值 artifact；freeze 必須由 caller 以 aware UTC identity 明確提供。"""
    freeze = _strict_aware_utc(available_at_or_before, "available_at_or_before")
    receipt_bytes = consumption_receipt_path.read_bytes()
    expected_receipt = _normalized_pin(expected_consumption_receipt_sha256, "expected_consumption_receipt_sha256")
    if f"sha256:{_sha256_bytes(receipt_bytes)}" != expected_receipt:
        raise ResearchAdapterError("consumption receipt actual bytes SHA-256 mismatch")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if receipt.get("schema_version") != RESEARCH_DIRECT_STORE_RECEIPT_SCHEMA_VERSION or receipt.get("status") != "verified_numeric_observations_ready":
        raise ResearchAdapterError("consumption receipt schema/status is not verified numeric observations")
    if receipt.get("historical_pit_eligible") is not False or receipt.get("direct_ooc_status") != "blocked_insufficient_context_or_mature_history":
        raise ResearchAdapterError("consumption receipt overstates historical PIT or Direct/OOC readiness")
    if _normalized_pin(str(receipt.get("candidate_manifest_bytes_sha256", "")), "receipt candidate manifest pin") != _normalized_pin(expected_candidate_manifest_bytes_sha256, "expected candidate manifest pin"):
        raise ResearchAdapterError("consumption receipt candidate manifest pin mismatch")
    if _normalized_pin(str(receipt.get("adapted_manifest_canonical_sha256", "")), "receipt adapted canonical pin") != _normalized_pin(expected_adapted_manifest_canonical_sha256, "expected adapted canonical pin"):
        raise ResearchAdapterError("consumption receipt adapted manifest canonical pin mismatch")
    if _normalized_pin(str(receipt.get("feature_registry_sha256", "")), "receipt registry pin") != _normalized_pin(expected_feature_registry_sha256, "expected feature registry pin"):
        raise ResearchAdapterError("consumption receipt feature registry pin mismatch")
    try:
        receipt_freeze = _strict_aware_utc(datetime.fromisoformat(receipt.get("current_observation_freeze", "")), "consumption receipt freeze")
    except (TypeError, ValueError) as exc:
        raise ResearchAdapterError("consumption receipt freeze is missing or invalid") from exc
    if receipt_freeze != freeze:
        raise ResearchAdapterError("caller freeze differs from consumption receipt freeze")

    store_root = consumption_receipt_path.parent.resolve()
    metadata_path = store_root / "store_metadata.json"
    if not metadata_path.is_file():
        raise ResearchAdapterError("numeric store metadata is missing")
    metadata_bytes = metadata_path.read_bytes()
    if f"sha256:{_sha256_bytes(metadata_bytes)}" != _normalized_pin(str(receipt.get("store_metadata_sha256", "")), "store metadata bytes pin"):
        raise ResearchAdapterError("numeric store metadata actual bytes SHA-256 mismatch")
    store_metadata = json.loads(metadata_bytes.decode("utf-8"))
    if store_metadata.get("schema_version") != "ml-research-verified-numeric-observations.v1" or store_metadata.get("status") != "verified_numeric_observations_ready":
        raise ResearchAdapterError("numeric store metadata schema/status is invalid")
    if store_metadata.get("candidate_manifest_bytes_sha256") != receipt.get("candidate_manifest_bytes_sha256") or store_metadata.get("adapted_manifest_canonical_sha256") != receipt.get("adapted_manifest_canonical_sha256"):
        raise ResearchAdapterError("numeric store metadata manifest pins differ from receipt")
    if store_metadata.get("historical_pit_eligible") is not False or store_metadata.get("direct_ooc_status") != "blocked_insufficient_context_or_mature_history":
        raise ResearchAdapterError("numeric store metadata overstates PIT or Direct/OOC readiness")

    registry_relative = Path(str(store_metadata.get("feature_registry_path") or ""))
    if registry_relative.is_absolute() or ".." in registry_relative.parts:
        raise ResearchAdapterError("stored feature registry path is not relative")
    registry_path = (store_root / registry_relative).resolve()
    if not registry_path.is_relative_to(store_root) or not registry_path.is_file():
        raise ResearchAdapterError("stored feature registry is missing or escapes its store")
    stored_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_pin = _normalized_pin(expected_feature_registry_sha256, "expected_feature_registry_sha256")
    if _json_hash(stored_registry) != registry_pin:
        raise ResearchAdapterError("stored feature registry canonical SHA-256 mismatch")

    stored_shards = receipt.get("stored_shards")
    if not isinstance(stored_shards, list) or not stored_shards:
        raise ResearchAdapterError("consumption receipt has no stored shard descriptors")
    verified_stored_shards: list[dict[str, Any]] = []
    stored_rows_total = 0
    for shard_meta in stored_shards:
        if not isinstance(shard_meta, dict):
            raise ResearchAdapterError("stored shard descriptor is invalid")
        relative = Path(str(shard_meta.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ResearchAdapterError("stored shard path is not relative")
        stored = (store_root / relative).resolve()
        if not stored.is_relative_to(store_root) or not stored.is_file():
            raise ResearchAdapterError("stored numeric shard is missing or escapes its store")
        expected_bytes = _normalized_pin(str(shard_meta.get("bytes_sha256", "")), "stored shard bytes pin")
        if f"sha256:{_sha256_file(stored)}" != expected_bytes:
            raise ResearchAdapterError("stored numeric shard actual bytes hash mismatch")
        row_count = _strict_int(shard_meta.get("row_count"), "stored shard row_count")
        _verify_stored_gzip_jsonl(
            stored,
            expected_compressed_sha256=str(shard_meta.get("compressed_sha256") or ""),
            expected_uncompressed_sha256=str(shard_meta.get("uncompressed_sha256") or ""),
            expected_row_count=row_count,
        )
        verified_stored_shards.append(shard_meta)
        stored_rows_total += row_count
    if stored_rows_total != _strict_int(receipt.get("record_count"), "consumption record_count"):
        raise ResearchAdapterError("stored shard row counts differ from consumption receipt")
    if _strict_int(store_metadata.get("record_count"), "store metadata record_count") != stored_rows_total:
        raise ResearchAdapterError("store metadata row count differs from stored shards")

    adapter_path = Path(str(receipt.get("adapter_receipt_path") or ""))
    adapter_bytes = adapter_path.read_bytes()
    if f"sha256:{_sha256_bytes(adapter_bytes)}" != _normalized_pin(str(receipt.get("adapter_receipt_bytes_sha256", "")), "adapter receipt pin"):
        raise ResearchAdapterError("adapter receipt bytes changed after consumption")
    artifact = _load_verified_adapter_artifact(
        adapter_path,
        expected_candidate_manifest_bytes_sha256=expected_candidate_manifest_bytes_sha256,
        expected_adapted_manifest_canonical_sha256=expected_adapted_manifest_canonical_sha256,
        expected_feature_registry_sha256=expected_feature_registry_sha256,
        available_at_or_before=freeze,
    )
    expected_count = _strict_int(receipt.get("record_count"), "consumption record_count")
    if len(artifact.observations) != expected_count:
        raise ResearchAdapterError("consumption receipt observation count differs from verified artifact")
    adapter_receipt = json.loads(adapter_bytes.decode("utf-8"))
    adapted_path = Path(str(adapter_receipt.get("adapted_manifest_path") or ""))
    adapted_manifest = json.loads(adapted_path.read_text(encoding="utf-8"))
    source_shards = adapted_manifest.get("shards")
    if not isinstance(source_shards, list) or len(source_shards) != len(verified_stored_shards):
        raise ResearchAdapterError("stored shard descriptors differ from adapted manifest")
    for stored_meta, source_meta in zip(verified_stored_shards, source_shards, strict=True):
        for key in ("compressed_sha256", "uncompressed_sha256", "row_count"):
            if stored_meta.get(key) != source_meta.get(key):
                raise ResearchAdapterError(f"stored shard {key} differs from adapted manifest")
    feature_count = sum(len(row.values) for row in artifact.observations)
    if _strict_int(receipt.get("feature_value_count"), "consumption feature_value_count") != feature_count:
        raise ResearchAdapterError("consumption receipt feature value count differs from verified artifact")
    if _strict_int(store_metadata.get("feature_value_count"), "store metadata feature_value_count") != feature_count:
        raise ResearchAdapterError("store metadata feature value count differs from verified artifact")
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a hash-verified research numeric artifact and report Direct/OOC readiness.",
    )
    parser.add_argument(
        "--raw-candidate-manifest",
        type=Path,
        required=True,
        help="Path to the candidate raw manifest or daily projection manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Target isolated output directory for adapted shards and manifest.",
    )
    parser.add_argument(
        "--training-as-of",
        type=str,
        required=True,
        help="Immutable current-observation freeze as timezone-aware ISO 8601 (e.g. 2026-10-03T00:30:00+00:00).",
    )
    parser.add_argument(
        "--expected-candidate-manifest-bytes-sha256",
        required=True,
        help="Required SHA-256 of the actual source candidate manifest bytes.",
    )
    parser.add_argument(
        "--benchmark-entity",
        type=str,
        default="TAIEX",
        help="Benchmark entity ID (default: TAIEX).",
    )
    parser.add_argument(
        "--consume-direct-store",
        type=Path,
        default=None,
        help="Optional output directory to immediately construct an isolated research direct numeric store.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        req = ResearchAdaptRequest(
            raw_candidate_manifest_path=args.raw_candidate_manifest,
            output_dir=args.output_dir,
            training_as_of=args.training_as_of,
            expected_candidate_manifest_bytes_sha256=args.expected_candidate_manifest_bytes_sha256,
            benchmark_entity_id=args.benchmark_entity,
        )
        adapter = ResearchDirectOOCAdapter(req)
        result = adapter.adapt()

        output_payload: dict[str, Any] = {
            "status": result.status,
            "adapted_manifest_path": str(result.adapted_manifest_path),
            "adapted_manifest_hash": result.adapted_manifest_hash,
            "adapter_receipt_path": str(result.adapter_receipt_path),
            "row_count": result.row_count,
            "market_revision_digest": result.market_revision_digest,
            "source_revision_qualification": "unverified_requires_separate_strict_inspection",
            "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
            "formal_release_v4_pointer_untouched": result.formal_release_v4_pointer_untouched,
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
        }

        if args.consume_direct_store:
            consumer = ResearchDirectNumericStoreConsumer(
                adapter_receipt_path=result.adapter_receipt_path,
                output_store_dir=args.consume_direct_store,
                training_as_of=args.training_as_of,
                benchmark_entity_id=args.benchmark_entity,
            )
            store_receipt = consumer.build_store()
            output_payload["direct_store_receipt"] = store_receipt

        print(json.dumps(output_payload, ensure_ascii=False, indent=2))
        return 0
    except (ResearchAdapterError, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "blocked",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "research_only": True,
            "formal_credit": False,
            "formal_oos_allowed": False,
            "production_alpha_bp": 0,
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
