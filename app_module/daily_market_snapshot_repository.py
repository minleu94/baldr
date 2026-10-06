"""不可變研究快照的有界唯讀驗證器。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, NoReturn, Sequence

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_research_universe import (
    ResearchUniverseContractError,
    load_research_universe_spec,
    validate_research_universe_manifest_binding,
)
from app_module.research_run_dtos import canonical_json
from app_module.saved_stock_technical_chart import read_saved_technical_chart


DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA = "daily-market-snapshot-pointer.v1"
DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA = "daily-market-snapshot-manifest.v2"
DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA = "daily-market-snapshot-manifest.v1"
DAILY_MARKET_SNAPSHOT_MAX_STOCKS = 16
DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES = 4 * 1024
DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES = 1024 * 1024
DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FEATURE_WINDOWS = {"MA20": 20, "MA60": 60}
_POLICY = {
    "usage": "current_observed_research_only",
    "official_availability_state": "unknown",
    "market_calendar_completeness": "unknown",
    "historical_pit_eligible": False,
    "warmup_is_formal_or_calendar_qualification": False,
}


class DailyMarketSnapshotVerificationError(ValueError):
    """以穩定錯誤碼回報研究快照驗證失敗。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class VerifiedDailyMarketSnapshot:
    """經驗證的 manifest 與逐股內層 snapshot payload。"""

    cohort_id: str
    decision_date: date
    manifest_sha256: str
    manifest_identity_sha256: str
    completeness: str
    manifest: Mapping[str, Any]
    stock_snapshots: Mapping[str, dict[str, Any]]


def canonical_json_bytes(value: Any) -> bytes:
    """以既有 canonical_json 編碼 JSON，不附加換行。"""

    return canonical_json(value).encode("utf-8")


def canonical_snapshot_json_bytes(value: Any) -> bytes:
    """提供明確的 snapshot 命名別名，供 producer 統一雜湊 bytes。"""

    return canonical_json_bytes(value)


def canonical_snapshot_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_snapshot_json_bytes(value)).hexdigest()


def snapshot_manifest_identity_sha256(manifest: Mapping[str, Any]) -> str:
    """排除自身雜湊與發布時間後，計算穩定 manifest identity。"""

    identity_payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_identity_sha256", "published_at"}
    }
    return canonical_snapshot_sha256(identity_payload)


def cohort_identity_sha256(cohort_id: str, declared_stock_codes: Sequence[str]) -> str:
    """將 cohort 名稱與排序後的明示股票分母綁定成穩定 identity。"""

    return canonical_snapshot_sha256(
        {
            "cohort_id": cohort_id,
            "declared_stock_codes": sorted(set(declared_stock_codes)),
        }
    )


def validate_research_universe_binding(
    binding: Mapping[str, Any] | None,
    *,
    decision_date: date,
    cohort_id: str | None = None,
    declared_stock_codes: Sequence[str] | None = None,
) -> dict[str, Any] | None:
    """Reopen and verify a pinned optional research-universe binding."""

    if binding is None:
        return None
    if not isinstance(binding, Mapping):
        _fail(
            "snapshot_research_universe_binding_invalid",
            "research_universe must be an object",
        )
    source_ref = binding.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref.strip():
        _fail(
            "snapshot_research_universe_binding_invalid",
            "research_universe source_ref is required",
        )
    try:
        spec = load_research_universe_spec(source_ref)
    except ResearchUniverseContractError as exc:
        source_codes = {
            "universe_source_missing": "snapshot_research_universe_source_missing",
            "universe_source_changed": "snapshot_research_universe_source_changed",
        }
        _fail(
            source_codes.get(
                exc.code, "snapshot_research_universe_binding_invalid"
            ),
            str(exc),
        )
    except (OSError, TypeError, ValueError) as exc:
        _fail(
            "snapshot_research_universe_binding_invalid",
            f"research_universe source cannot be read: {exc}",
        )
    try:
        validate_research_universe_manifest_binding(spec, binding)
    except ResearchUniverseContractError as exc:
        code = (
            "snapshot_research_universe_source_changed"
            if exc.code == "universe_binding_mismatch"
            and binding.get("source_sha256") != spec.source_sha256
            else "snapshot_research_universe_binding_invalid"
        )
        _fail(code, str(exc))
    except (TypeError, ValueError) as exc:
        _fail("snapshot_research_universe_binding_invalid", str(exc))
    if spec.as_of_date != decision_date:
        _fail(
            "snapshot_research_universe_date_mismatch",
            "research_universe as_of_date must match decision_date",
        )
    if cohort_id is not None and spec.universe_id != cohort_id:
        _fail(
            "snapshot_research_universe_cohort_mismatch",
            "research_universe universe_id must match cohort_id",
        )
    if declared_stock_codes is not None and tuple(
        spec.included_stock_codes
    ) != tuple(declared_stock_codes):
        _fail(
            "snapshot_research_universe_membership_mismatch",
            "included_stock_codes must match declared_stock_codes",
        )
    try:
        spec.assert_source_stable()
    except ResearchUniverseContractError as exc:
        code = (
            "snapshot_research_universe_source_missing"
            if exc.code == "universe_source_missing"
            else "snapshot_research_universe_source_changed"
            if exc.code == "universe_source_changed"
            else "snapshot_research_universe_binding_invalid"
        )
        _fail(code, str(exc))
    return dict(spec.to_manifest_binding())


def snapshot_manifest_relpath(manifest_sha256: str) -> str:
    """依 manifest 內容雜湊取得 immutable 相對路徑。"""

    _require_sha256(manifest_sha256, "manifest_sha256")
    return f"manifests/{manifest_sha256}.json"


def snapshot_artifact_relpath(artifact_sha256: str) -> str:
    """依 artifact 內容雜湊取得 immutable 相對路徑。"""

    _require_sha256(artifact_sha256, "artifact_sha256")
    return f"objects/{artifact_sha256}.json"


def snapshot_identity_sha256(
    *,
    contract_version: str,
    stock_code: str,
    decision_date: str,
    scope_identity: str,
    input_fingerprint_sha256: str,
    method_contracts_sha256: str | None = None,
) -> str:
    """依 feature snapshot 既有穩定識別欄位重算雜湊。"""

    identity_payload = {
        "contract_version": contract_version,
        "stock_code": stock_code,
        "decision_date": decision_date,
        "scope_identity": scope_identity,
        "input_fingerprint_sha256": input_fingerprint_sha256,
    }
    if method_contracts_sha256 is not None:
        identity_payload["method_contracts_sha256"] = method_contracts_sha256
    return canonical_snapshot_sha256(identity_payload)


class DailyMarketSnapshotRepository:
    """每次讀取並核驗 latest pin 與有界不可變快照檔。"""

    def __init__(self, output_root: str | Path) -> None:
        if output_root is None:
            raise ValueError("必須明確提供唯讀 snapshot output_root")
        self.output_root = Path(output_root)

    def load_latest(
        self,
        cohort_id: str,
        decision_date: date,
        *,
        expected_stock_codes: Sequence[str] | None = None,
        expected_input_hashes: Mapping[str, str] | None = None,
    ) -> VerifiedDailyMarketSnapshot:
        """每次讀取並核驗 latest pointer 所指的 manifest 與 artifacts。"""

        requested_cohort = str(cohort_id).strip()
        if not requested_cohort:
            raise ValueError("cohort_id 不可為空")
        if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
            raise ValueError("decision_date 必須是 date")
        expected_codes = _normalize_expected_codes(expected_stock_codes)
        expected_hashes = _normalize_expected_hashes(expected_input_hashes)

        pointer_bytes, pointer = self._read_json_file(
            Path("latest.json"),
            limit=DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
            missing_code="snapshot_pointer_missing",
            invalid_code="snapshot_pointer_invalid",
        )
        if set(pointer) != {"schema_version", "manifest_sha256"}:
            _fail("snapshot_pointer_invalid", "latest pointer 欄位不符合 v1 契約")
        if pointer.get("schema_version") != DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA:
            _fail("snapshot_pointer_schema_mismatch", "latest pointer schema 不相容")
        manifest_sha = _require_sha256(
            pointer.get("manifest_sha256"), "manifest_sha256"
        )
        verified = self.load_manifest(
            manifest_sha256=manifest_sha,
            cohort_id=requested_cohort,
            decision_date=decision_date,
            expected_stock_codes=expected_codes,
            expected_input_hashes=expected_hashes,
        )

        # 重讀小型pointer，避免並行原子發布後仍把舊版本回報為latest。
        second_pointer_bytes, _ = self._read_json_file(
            Path("latest.json"),
            limit=DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
            missing_code="snapshot_pointer_missing",
            invalid_code="snapshot_pointer_invalid",
        )
        if second_pointer_bytes != pointer_bytes:
            _fail("snapshot_pointer_changed_during_read", "讀取期間 latest pointer 已更新")
        return verified

    def load_manifest(
        self,
        manifest_sha256: str,
        cohort_id: str,
        decision_date: date,
        *,
        expected_stock_codes: Sequence[str] | None = None,
        expected_input_hashes: Mapping[str, str] | None = None,
    ) -> VerifiedDailyMarketSnapshot:
        """按 manifest digest 驗證候選版本，不讀 latest pointer。"""

        requested_cohort = str(cohort_id).strip()
        if not requested_cohort:
            raise ValueError("cohort_id 不可為空")
        if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
            raise ValueError("decision_date 必須是 date")
        expected_codes = _normalize_expected_codes(expected_stock_codes)
        expected_hashes = _normalize_expected_hashes(expected_input_hashes)
        manifest_sha = _require_sha256(manifest_sha256, "manifest_sha256")
        manifest_bytes, manifest = self._read_json_file(
            Path(snapshot_manifest_relpath(manifest_sha)),
            limit=DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
            missing_code="snapshot_manifest_missing",
            invalid_code="snapshot_manifest_invalid",
        )
        if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha:
            _fail("snapshot_manifest_hash_mismatch", "manifest 內容與指定 pin 不符")
        if canonical_snapshot_json_bytes(manifest) != manifest_bytes:
            _fail("snapshot_manifest_noncanonical", "manifest 必須使用 canonical JSON bytes")

        _declared_codes, records = self._validate_manifest(
            manifest,
            cohort_id=requested_cohort,
            decision_date=decision_date,
            expected_codes=expected_codes,
        )
        record_by_code = {record["stock_code"]: record for record in records}
        if expected_hashes is not None:
            unknown_hash_codes = set(expected_hashes) - set(record_by_code)
            if unknown_hash_codes:
                _fail(
                    "snapshot_expected_input_missing",
                    "提供了輸入 hash，但 manifest 沒有對應股票 artifact",
                )

        stock_snapshots: dict[str, dict[str, Any]] = {}
        for stock_code in sorted(record_by_code):
            record = record_by_code[stock_code]
            payload = self._load_stock_artifact(
                record,
                stock_code=stock_code,
                decision_date=decision_date,
                manifest=manifest,
            )
            expected_hash = (expected_hashes or {}).get(stock_code)
            if expected_hash is not None and payload["input_fingerprint_sha256"] != expected_hash:
                _fail(
                    "snapshot_input_hash_mismatch",
                    f"{stock_code} 的當前輸入 fingerprint 與已發布快照不同",
                )
            stock_snapshots[stock_code] = payload
        return VerifiedDailyMarketSnapshot(
            cohort_id=requested_cohort,
            decision_date=decision_date,
            manifest_sha256=manifest_sha,
            manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
            completeness=str(manifest["completeness"]),
            manifest=deepcopy(manifest),
            stock_snapshots=stock_snapshots,
        )

    def _validate_manifest(
        self,
        manifest: dict[str, Any],
        *,
        cohort_id: str,
        decision_date: date,
        expected_codes: tuple[str, ...] | None,
    ) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
        if manifest.get("schema_version") == DAILY_MARKET_SNAPSHOT_LEGACY_MANIFEST_SCHEMA:
            claimed_identity = _require_sha256(
                manifest.get("manifest_identity_sha256"), "manifest_identity_sha256"
            )
            if snapshot_manifest_identity_sha256(manifest) != claimed_identity:
                _fail("snapshot_manifest_identity_mismatch", "manifest stable identity 不符")
            _fail(
                "snapshot_manifest_legacy_v1",
                "本地 v1 快照沒有方法契約綁定，reader 拒絕讀取；請明示重新產生 v2 快照。",
            )
        required_fields = {
            "schema_version",
            "manifest_identity_sha256",
            "cohort_id",
            "cohort_identity",
            "declared_stock_codes",
            "decision_date",
            "decision_cutoff",
            "decision_timezone",
            "feature_contract_version",
            "feature_keys",
            "method_contracts",
            "method_contracts_sha256",
            "stocks",
            "missing_stocks",
            "counts",
            "completeness",
            "published_at",
            "policy",
        }
        allowed_fields = required_fields | {"source_ref", "research_universe"}
        if not required_fields.issubset(manifest) or not set(manifest).issubset(allowed_fields):
            _fail("snapshot_manifest_invalid", "manifest 欄位不符合 v2 契約")
        if manifest.get("schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
            _fail("snapshot_manifest_schema_mismatch", "manifest schema 不相容")
        claimed_identity = _require_sha256(
            manifest.get("manifest_identity_sha256"), "manifest_identity_sha256"
        )
        if snapshot_manifest_identity_sha256(manifest) != claimed_identity:
            _fail("snapshot_manifest_identity_mismatch", "manifest stable identity 不符")
        if manifest.get("cohort_id") != cohort_id:
            _fail("snapshot_cohort_mismatch", "snapshot cohort_id 與呼叫端不同")
        manifest_date = _parse_iso_date(manifest.get("decision_date"), "decision_date")
        if manifest_date != decision_date:
            _fail("snapshot_decision_date_mismatch", "snapshot decision_date 與呼叫端不同")
        cutoff = _validate_cutoff(manifest.get("decision_cutoff"), manifest_date)
        if manifest.get("decision_timezone") != "Asia/Taipei":
            _fail("snapshot_cutoff_invalid", "決策 cutoff 必須聲明 Asia/Taipei")
        published_at = _validate_aware_timestamp(manifest.get("published_at"), "published_at")
        if cutoff > published_at:
            _fail("snapshot_cutoff_invalid", "decision_cutoff 不可晚於 published_at")

        declared_raw = manifest.get("declared_stock_codes")
        if not isinstance(declared_raw, list) or not declared_raw:
            _fail("snapshot_stock_scope_invalid", "manifest 必須明示非空 cohort 股票清單")
        if len(declared_raw) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
            _fail("snapshot_stock_scope_too_large", "cohort 股票數超過 reader 上限")
        if any(not isinstance(code, str) or not code.strip() for code in declared_raw):
            _fail("snapshot_stock_scope_invalid", "cohort 股票代碼必須是非空字串")
        declared_codes = tuple(declared_raw)
        if declared_codes != tuple(sorted(set(declared_codes))):
            _fail("snapshot_stock_scope_invalid", "cohort 股票清單必須排序且不可重複")
        claimed_cohort_identity = _require_sha256(
            manifest.get("cohort_identity"), "cohort_identity"
        )
        if cohort_identity_sha256(cohort_id, declared_codes) != claimed_cohort_identity:
            _fail("snapshot_cohort_identity_mismatch", "cohort identity 與明示股票分母不符")
        if expected_codes is not None and declared_codes != expected_codes:
            _fail("snapshot_stock_scope_mismatch", "manifest cohort 股票分母與呼叫端不同")

        if manifest.get("feature_contract_version") != DAILY_MARKET_FEATURE_CONTRACT_VERSION:
            _fail("snapshot_contract_version_mismatch", "feature contract version 不相容")
        if manifest.get("feature_keys") != list(DAILY_MARKET_FEATURE_KEYS):
            _fail("snapshot_feature_keys_mismatch", "manifest features 不符合 reader 契約")
        _validate_method_contract_binding(
            manifest.get("method_contracts"),
            manifest.get("method_contracts_sha256"),
        )
        manifest_policy = manifest.get("policy")
        if (
            not isinstance(manifest_policy, dict)
            or set(manifest_policy) != {"research_only", "historical_pit_eligible"}
            or manifest_policy.get("research_only") is not True
            or manifest_policy.get("historical_pit_eligible") is not False
        ):
            _fail("snapshot_policy_invalid", "snapshot 必須明示 research-only 且 PIT=false")

        if "source_ref" in manifest and not isinstance(manifest["source_ref"], dict):
            _fail("snapshot_source_ref_invalid", "manifest source_ref 必須是 object")
        if "research_universe" in manifest:
            if manifest.get("research_universe") is None:
                _fail(
                    "snapshot_research_universe_binding_invalid",
                    "research_universe extension cannot be null",
                )
            validate_research_universe_binding(
                manifest.get("research_universe"),
                decision_date=manifest_date,
                cohort_id=cohort_id,
                declared_stock_codes=declared_codes,
            )
        records_raw = manifest.get("stocks")
        if not isinstance(records_raw, list) or len(records_raw) > len(declared_codes):
            _fail("snapshot_stock_records_invalid", "manifest stocks 數量無效")
        records: list[dict[str, Any]] = []
        record_codes: list[str] = []
        for item in records_raw:
            if not isinstance(item, dict):
                _fail("snapshot_stock_records_invalid", "manifest stock record 必須是 object")
            required_record_fields = {
                "stock_code",
                "source_identity",
                "input_fingerprint_sha256",
                "snapshot_identity_sha256",
                "artifact_sha256",
                "artifact_relpath",
                "source_refs",
            }
            if set(item) != required_record_fields:
                _fail("snapshot_stock_records_invalid", "manifest v2 stock record 欄位不符合契約")
            stock_code = item.get("stock_code")
            if not isinstance(stock_code, str) or stock_code not in declared_codes:
                _fail("snapshot_stock_scope_invalid", "manifest artifact 超出 declared cohort")
            record_codes.append(stock_code)
            for field_name in (
                "input_fingerprint_sha256",
                "snapshot_identity_sha256",
                "artifact_sha256",
            ):
                _require_sha256(item.get(field_name), field_name)
            if not isinstance(item.get("source_identity"), str) or not item["source_identity"].strip():
                _fail("snapshot_source_ref_invalid", "source_identity 必須是非空字串")
            expected_relpath = snapshot_artifact_relpath(item["artifact_sha256"])
            if item.get("artifact_relpath") != expected_relpath:
                _fail("snapshot_artifact_path_invalid", "artifact path 必須以內容 hash 命名")
            self._validate_source_refs(item.get("source_refs"))
            records.append(item)
        if record_codes != sorted(set(record_codes)):
            _fail("snapshot_stock_records_invalid", "manifest stock records 必須排序且不可重複")

        missing_raw = manifest.get("missing_stocks")
        if not isinstance(missing_raw, list) or len(missing_raw) > len(declared_codes):
            _fail("snapshot_missing_diagnostics_invalid", "missing_stocks 必須是有界 list")
        missing_codes: list[str] = []
        for item in missing_raw:
            if (
                not isinstance(item, dict)
                or set(item) != {"stock_code", "reason"}
                or not isinstance(item.get("stock_code"), str)
                or not isinstance(item.get("reason"), str)
                or not item["reason"].strip()
            ):
                _fail("snapshot_missing_diagnostics_invalid", "每筆 missing stock 必須有股票代碼與原因")
            missing_codes.append(item["stock_code"])
        expected_missing_codes = sorted(set(declared_codes) - set(record_codes))
        if missing_codes != expected_missing_codes:
            _fail("snapshot_missing_diagnostics_invalid", "missing_stocks 必須逐一說明缺少的 declared stocks")

        expected_counts = {
            "declared": len(declared_codes),
            "published": len(records),
            "missing": len(declared_codes) - len(records),
        }
        counts = manifest.get("counts")
        if (
            not isinstance(counts, dict)
            or set(counts) != set(expected_counts)
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in counts.values()
            )
            or counts != expected_counts
        ):
            _fail("snapshot_counts_mismatch", "manifest counts 與明示 cohort/artifacts 不符")
        expected_completeness = (
            "complete_declared_cohort"
            if len(records) == len(declared_codes)
            else "partial_research"
        )
        if manifest.get("completeness") != expected_completeness:
            _fail("snapshot_completeness_mismatch", "manifest completeness 與 artifacts 不符")
        return declared_codes, records

    def _validate_source_refs(self, source_refs: Any) -> None:
        required = {"database", "schema_identity_sha256", "price", "technical"}
        if not isinstance(source_refs, dict) or set(source_refs) != required:
            _fail("snapshot_source_ref_invalid", "每股 source_refs 欄位不符合 reader 契約")
        database = source_refs.get("database")
        price = source_refs.get("price")
        technical = source_refs.get("technical")
        if not isinstance(database, str) or not database.strip():
            _fail("snapshot_source_ref_invalid", "database source ref 必須是 resolved path")
        _require_sha256(source_refs.get("schema_identity_sha256"), "schema_identity_sha256")
        if (
            not isinstance(price, str)
            or not isinstance(technical, str)
            or not price.strip()
            or not technical.strip()
            or not price.endswith("#daily_prices")
            or not technical.endswith("#technical_indicators")
            or price.rsplit("#", 1)[0] != database
            or technical.rsplit("#", 1)[0] != database
        ):
            _fail("snapshot_source_ref_invalid", "price/technical refs 必須指向同一 DB 與具名資料表")

    def _load_stock_artifact(
        self,
        record: dict[str, Any],
        *,
        stock_code: str,
        decision_date: date,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_hash = str(record["artifact_sha256"])
        artifact_bytes, payload = self._read_json_file(
            Path(snapshot_artifact_relpath(artifact_hash)),
            limit=DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES,
            missing_code="snapshot_artifact_missing",
            invalid_code="snapshot_artifact_invalid",
        )
        if hashlib.sha256(artifact_bytes).hexdigest() != artifact_hash:
            _fail("snapshot_artifact_hash_mismatch", f"{stock_code} artifact hash 不符")
        if canonical_snapshot_json_bytes(payload) != artifact_bytes:
            _fail("snapshot_artifact_noncanonical", f"{stock_code} artifact 必須是 canonical JSON")
        self._validate_snapshot_payload(
            payload,
            record=record,
            stock_code=stock_code,
            decision_date=decision_date,
            manifest=manifest,
        )
        return payload

    def _validate_snapshot_payload(
        self,
        payload: dict[str, Any],
        *,
        record: dict[str, Any],
        stock_code: str,
        decision_date: date,
        manifest: dict[str, Any],
    ) -> None:
        required_fields = {
            "contract_version",
            "snapshot_identity_sha256",
            "input_fingerprint_sha256",
            "stock_code",
            "decision_date",
            "scope_identity",
            "market_date",
            "features",
            "conditions",
            "method_contracts",
            "method_contracts_sha256",
            "policy",
        }
        if set(payload) not in (required_fields, required_fields | {"saved_technical_chart"}):
            _fail("snapshot_artifact_schema_mismatch", f"{stock_code} artifact 欄位不符合 feature DTO")
        if payload.get("contract_version") != manifest["feature_contract_version"]:
            _fail("snapshot_contract_version_mismatch", f"{stock_code} feature version 不符")
        if payload.get("stock_code") != stock_code:
            _fail("snapshot_stock_mismatch", "artifact stock_code 與 manifest 不符")
        if payload.get("decision_date") != decision_date.isoformat():
            _fail("snapshot_decision_date_mismatch", f"{stock_code} artifact 日期不符")
        if payload.get("scope_identity") != record["source_identity"]:
            _fail("snapshot_scope_identity_mismatch", f"{stock_code} scope identity 不符")
        if "saved_technical_chart" in payload:
            try:
                chart = read_saved_technical_chart(
                    payload["saved_technical_chart"], stock_code=stock_code, decision_date=decision_date,
                    scope_identity=str(payload["scope_identity"]),
                    input_fingerprint_sha256=str(payload["input_fingerprint_sha256"]),
                )
                if chart.decision_cutoff != manifest["decision_cutoff"]:
                    raise ValueError("chart_manifest_cutoff_mismatch")
            except (ValueError, TypeError, KeyError) as exc:
                _fail("snapshot_saved_chart_invalid", f"{stock_code} 保存圖表拒絕：{exc}")
        if payload.get("method_contracts") != manifest.get("method_contracts"):
            _fail(
                "snapshot_method_contract_binding_mismatch",
                f"{stock_code} 內層 method_contracts 與 manifest 不符",
            )
        if payload.get("method_contracts_sha256") != manifest.get(
            "method_contracts_sha256"
        ):
            _fail(
                "snapshot_method_contract_hash_mismatch",
                f"{stock_code} 內層 method_contracts_sha256 與 manifest 不符",
            )
        _validate_method_contract_binding(
            payload.get("method_contracts"),
            payload.get("method_contracts_sha256"),
        )
        if payload.get("input_fingerprint_sha256") != record["input_fingerprint_sha256"]:
            _fail("snapshot_input_hash_mismatch", f"{stock_code} artifact input hash 與 manifest 不符")
        if payload.get("snapshot_identity_sha256") != record["snapshot_identity_sha256"]:
            _fail("snapshot_identity_mismatch", f"{stock_code} snapshot identity 與 manifest 不符")
        _require_sha256(payload.get("input_fingerprint_sha256"), "input_fingerprint_sha256")
        recomputed_identity = snapshot_identity_sha256(
            contract_version=str(payload["contract_version"]),
            stock_code=stock_code,
            decision_date=decision_date.isoformat(),
            scope_identity=str(payload["scope_identity"]),
            input_fingerprint_sha256=str(payload["input_fingerprint_sha256"]),
            method_contracts_sha256=str(payload["method_contracts_sha256"]),
        )
        if payload.get("snapshot_identity_sha256") != recomputed_identity:
            _fail("snapshot_identity_mismatch", f"{stock_code} snapshot identity 重算不符")
        artifact_policy = payload.get("policy")
        if (
            not isinstance(artifact_policy, dict)
            or set(artifact_policy) != set(_POLICY)
            or any(
                artifact_policy.get(key) is not expected
                if isinstance(expected, bool)
                else artifact_policy.get(key) != expected
                for key, expected in _POLICY.items()
            )
        ):
            _fail("snapshot_policy_invalid", f"{stock_code} artifact 必須是 research-only/PIT=false")

        market_date = payload.get("market_date")
        if market_date is not None:
            parsed_market_date = _parse_iso_date(market_date, "market_date")
            if parsed_market_date > decision_date:
                _fail("snapshot_future_market_date", f"{stock_code} market_date 晚於 decision_date")
        features = payload.get("features")
        conditions = payload.get("conditions")
        if not isinstance(features, dict) or set(features) != set(DAILY_MARKET_FEATURE_KEYS):
            _fail("snapshot_feature_schema_mismatch", f"{stock_code} features 欄位無效")
        if not isinstance(conditions, dict) or set(conditions) != set(DAILY_MARKET_CONDITION_KEYS):
            _fail("snapshot_condition_schema_mismatch", f"{stock_code} conditions 欄位無效")
        for key in DAILY_MARKET_FEATURE_KEYS:
            source_ref = (
                record["source_refs"]["price"]
                if key == "close"
                else record["source_refs"]["technical"]
            )
            self._validate_feature(features[key], key, market_date, source_ref)
        for condition_key, feature_key in zip(
            DAILY_MARKET_CONDITION_KEYS, ("MA20", "MA60")
        ):
            self._validate_condition(
                conditions[condition_key],
                condition_key,
                features["close"],
                features[feature_key],
                market_date,
                decision_date,
                manifest["method_contracts"][condition_key],
            )

    def _validate_feature(
        self,
        feature: Any,
        key: str,
        market_date: Any,
        source_ref: str,
    ) -> None:
        required_fields = {
            "key",
            "value",
            "unit",
            "state",
            "data_date",
            "source_id",
            "source_fingerprint_sha256",
            "reason",
            "warmup_required_count",
            "warmup_observed_count",
            "warmup_state",
            "warmup_basis",
        }
        if not isinstance(feature, dict) or set(feature) != required_fields:
            _fail("snapshot_feature_schema_mismatch", f"{key} feature 欄位無效")
        if feature.get("key") != key or feature.get("unit") != "TWD/share":
            _fail("snapshot_feature_schema_mismatch", f"{key} feature key/unit 不符")
        _require_sha256(
            feature.get("source_fingerprint_sha256"), f"{key}.source_fingerprint_sha256"
        )
        source_id = feature.get("source_id")
        if source_id is not None and not isinstance(source_id, str):
            _fail("snapshot_source_ref_mismatch", f"{key} source_id 欄位無效")
        expected_table = "daily_prices" if key == "close" else "technical_indicators"
        expected_source_id = f"sqlite.{expected_table}"
        if source_ref.rsplit("#", 1)[-1] != expected_table:
            _fail("snapshot_source_ref_mismatch", f"{key} source table ref 不符")
        if source_id is not None and source_id != expected_source_id:
            _fail("snapshot_source_ref_mismatch", f"{key} source_id 與具名 table 不符")
        if feature.get("state") == "observed" and not source_id:
            _fail("snapshot_source_ref_mismatch", f"{key} observed feature 必須具 source_id")
        state = feature.get("state")
        if state not in {"observed", "unknown"}:
            _fail("snapshot_feature_state_invalid", f"{key} feature state 無效")
        raw_value = feature.get("value")
        value: Decimal | None = None
        if raw_value is not None:
            if not isinstance(raw_value, str):
                _fail("snapshot_feature_value_invalid", f"{key} 金額必須用 Decimal 字串保存")
            try:
                value = Decimal(raw_value)
            except InvalidOperation:
                _fail("snapshot_feature_value_invalid", f"{key} Decimal 值格式錯誤")
            if not value.is_finite() or value <= 0:
                _fail("snapshot_feature_value_invalid", f"{key} Decimal 值必須有限且為正")
        if (state == "observed") != (value is not None):
            _fail("snapshot_feature_state_invalid", f"{key} state/value 組合無效")
        if state == "unknown" and not isinstance(feature.get("reason"), str):
            _fail("snapshot_feature_state_invalid", f"{key} unknown 必須有原因碼")
        feature_date = feature.get("data_date")
        if feature_date is not None:
            parsed_feature_date = _parse_iso_date(feature_date, f"{key}.data_date")
            if market_date is not None and parsed_feature_date > _parse_iso_date(
                market_date, "market_date"
            ):
                _fail("snapshot_feature_date_mismatch", f"{key} data_date 晚於 market_date")
        if state == "observed" and feature_date != market_date:
            _fail("snapshot_feature_date_mismatch", f"{key} observed data_date 必須等於 market_date")
        if key in _FEATURE_WINDOWS:
            self._validate_warmup(feature, key)

    def _validate_warmup(self, feature: dict[str, Any], key: str) -> None:
        required = _FEATURE_WINDOWS[key]
        observed = feature.get("warmup_observed_count")
        if feature.get("warmup_required_count") != required:
            _fail("snapshot_warmup_invalid", f"{key} warmup required count 不符")
        if observed is not None and (
            isinstance(observed, bool) or not isinstance(observed, int) or observed < 0
        ):
            _fail("snapshot_warmup_invalid", f"{key} warmup observed count 無效")
        if feature.get("warmup_basis") is None or not isinstance(feature.get("warmup_basis"), str):
            _fail("snapshot_warmup_invalid", f"{key} warmup basis 必須具名")
        if feature.get("state") == "observed":
            if (
                observed is None
                or observed < required
                or feature.get("warmup_state") != "sufficient_observed_prefix"
            ):
                _fail("snapshot_warmup_invalid", f"{key} observed feature 暖機資格不足")
        elif feature.get("warmup_state") not in {"unknown", "sufficient_observed_prefix"}:
            _fail("snapshot_warmup_invalid", f"{key} unknown 暖機狀態無效")

    def _validate_condition(
        self,
        condition: Any,
        key: str,
        close_feature: dict[str, Any],
        average_feature: dict[str, Any],
        market_date: Any,
        decision_date: date,
        method_contract: Mapping[str, Any],
    ) -> None:
        required_fields = {
            "name",
            "state",
            "relation",
            "close_value",
            "reference_value",
            "unit",
            "data_date",
            "reason",
            "semantics",
            "method_id",
            "family",
            "version",
            "parameters",
            "decision_date",
            "eligibility",
            "unknown_reason",
        }
        if not isinstance(condition, dict) or set(condition) != required_fields:
            _fail("snapshot_condition_schema_mismatch", f"{key} condition 欄位無效")
        if (
            condition.get("name") != key
            or condition.get("unit") != "TWD/share"
            or condition.get("semantics") != "existing_observation"
        ):
            _fail("snapshot_condition_schema_mismatch", f"{key} condition semantics 不符")
        if condition.get("method_id") != method_contract.get("method_id"):
            _fail("snapshot_method_id_mismatch", f"{key} method_id 與 canonical contract 不符")
        if condition.get("family") != method_contract.get("family"):
            _fail("snapshot_method_family_mismatch", f"{key} method family 與 canonical contract 不符")
        if condition.get("version") != method_contract.get("version"):
            _fail("snapshot_method_version_mismatch", f"{key} method version 與 canonical contract 不符")
        if condition.get("parameters") != method_contract.get("parameters"):
            _fail("snapshot_method_parameters_mismatch", f"{key} method parameters 與 canonical contract 不符")
        if condition.get("decision_date") != decision_date.isoformat():
            _fail("snapshot_condition_decision_date_mismatch", f"{key} decision_date 與 snapshot 不符")
        if condition.get("data_date") != market_date:
            _fail("snapshot_condition_date_mismatch", f"{key} condition 日期不符")
        close_value = close_feature.get("value")
        reference_value = average_feature.get("value")
        if (
            condition.get("close_value") != close_value
            or condition.get("reference_value") != reference_value
        ):
            _fail("snapshot_condition_value_mismatch", f"{key} condition 值與 feature 不符")
        if close_feature.get("state") != "observed" or average_feature.get("state") != "observed":
            if (
                condition.get("state") != "unknown"
                or condition.get("relation") != "unknown"
                or condition.get("eligibility") != "unknown"
            ):
                _fail("snapshot_condition_state_invalid", f"{key} input unknown 時 condition 必須 unknown")
            self._validate_unknown_condition_reason(condition, key)
            return
        try:
            close_decimal = Decimal(str(close_value))
            reference_decimal = Decimal(str(reference_value))
        except InvalidOperation:
            _fail("snapshot_condition_value_invalid", f"{key} condition Decimal 值無效")
        expected_relation = (
            "above" if close_decimal > reference_decimal
            else "below" if close_decimal < reference_decimal
            else "equal"
        )
        expected_state = "match" if expected_relation == "above" else "no_match"
        if (
            condition.get("relation") != expected_relation
            or condition.get("state") != expected_state
            or condition.get("eligibility") != "eligible"
            or condition.get("unknown_reason") != ""
        ):
            _fail("snapshot_condition_state_invalid", f"{key} relation/state 與 Decimal 比較不符")

    @staticmethod
    def _validate_unknown_condition_reason(condition: Mapping[str, Any], key: str) -> None:
        reason = condition.get("reason")
        unknown_reason = condition.get("unknown_reason")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or condition.get("eligibility") != "unknown"
            or unknown_reason != reason
        ):
            _fail("snapshot_condition_unknown_reason_invalid", f"{key} unknown condition 必須保存穩定理由碼")

    def _read_json_file(
        self,
        relative_path: Path,
        *,
        limit: int,
        missing_code: str,
        invalid_code: str,
    ) -> tuple[bytes, dict[str, Any]]:
        path = self._resolve_local_path(relative_path, missing_code)
        try:
            with path.open("rb") as stream:
                raw = stream.read(limit + 1)
        except OSError as exc:
            _fail(missing_code, f"無法讀取 snapshot 檔案：{exc}")
        if len(raw) > limit:
            _fail("snapshot_file_too_large", "snapshot 檔案超過 reader 有界上限")
        try:
            loaded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(invalid_code, f"snapshot JSON 無效：{exc}")
        if not isinstance(loaded, dict):
            _fail(invalid_code, "snapshot JSON root 必須是 object")
        return raw, loaded

    def _resolve_local_path(self, relative_path: Path, missing_code: str) -> Path:
        try:
            root = self.output_root.resolve(strict=True)
            path = (root / relative_path).resolve(strict=True)
            path.relative_to(root)
        except (OSError, ValueError) as exc:
            _fail(missing_code, f"snapshot 檔案不存在或超出 output_root：{exc}")
        if not path.is_file():
            _fail(missing_code, "snapshot 路徑不是一般檔案")
        return path


def _validate_method_contract_binding(payload: Any, claimed_sha256: Any) -> None:
    """要求 manifest/artifact 綁定目前唯一 canonical 方法 registry。"""

    if not isinstance(payload, dict):
        _fail("snapshot_method_contracts_invalid", "method_contracts 必須是 object")
    expected_payload = method_contracts_payload()
    expected_sha256 = method_contracts_sha256()
    _require_sha256(expected_sha256, "canonical_method_contracts_sha256")
    _validate_fixed_method_semantics(expected_payload)
    if canonical_snapshot_sha256(expected_payload) != expected_sha256:
        _fail("snapshot_method_contract_registry_invalid", "canonical method registry hash 不一致")
    if payload != expected_payload:
        _fail(
            "snapshot_method_contract_mismatch",
            "method_contracts 與目前 canonical registry 不一致",
        )
    claimed = _require_sha256(claimed_sha256, "method_contracts_sha256")
    if claimed != expected_sha256 or canonical_snapshot_sha256(payload) != claimed:
        _fail(
            "snapshot_method_contract_hash_mismatch",
            "method_contracts_sha256 與 canonical payload 不一致",
        )


def current_method_contract_binding() -> tuple[dict[str, Any], str]:
    """回傳經固定 MA20/MA60 語義驗證的當前 canonical registry。"""

    payload = method_contracts_payload()
    claimed_sha256 = method_contracts_sha256(payload)
    _validate_method_contract_binding(payload, claimed_sha256)
    return payload, claimed_sha256


def _validate_fixed_method_semantics(payload: Mapping[str, Any]) -> None:
    """固定既有 MA20/MA60 比較語義，避免 metadata 改寫實際公式。"""

    expected = {
        "close_above_ma20": (20, "MA20"),
        "close_above_ma60": (60, "MA60"),
    }
    if set(payload) != set(expected):
        _fail("snapshot_method_contract_registry_invalid", "canonical method registry keys 不符合固定條件")
    for key, (window, average_key) in expected.items():
        contract = payload.get(key)
        if not isinstance(contract, dict) or set(contract) != {
            "method_id",
            "family",
            "version",
            "parameters",
            "required_fields",
        }:
            _fail("snapshot_method_contract_registry_invalid", f"{key} canonical method contract 無效")
        parameters = contract.get("parameters")
        if (
            contract.get("method_id") != f"daily_market.{key}"
            or contract.get("family") != "close_vs_moving_average"
            or not isinstance(contract.get("version"), str)
            or not contract["version"].strip()
            or not isinstance(parameters, dict)
            or set(parameters) != {"window", "direction"}
            or type(parameters.get("window")) is not int
            or parameters.get("window") != window
            or parameters.get("direction") != "above"
            or contract.get("required_fields") != ["close", average_key]
        ):
            _fail(
                "snapshot_method_contract_registry_invalid",
                f"{key} registry 不可改變既有 MA{window} 條件語義",
            )


def _normalize_expected_codes(value: Sequence[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("expected_stock_codes 必須是股票代碼序列")
    if len(value) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
        raise ValueError("expected_stock_codes 超過有界股票清單上限")
    codes = tuple(str(code).strip() for code in value)
    if not codes or any(not code for code in codes) or len(codes) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
        raise ValueError("expected_stock_codes 必須是有界非空股票清單")
    if len(set(codes)) != len(codes):
        raise ValueError("expected_stock_codes 不可重複")
    return tuple(sorted(codes))


def _normalize_expected_hashes(
    value: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("expected_input_hashes 必須是 mapping")
    if len(value) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
        raise ValueError("expected_input_hashes 超過有界股票清單上限")
    result: dict[str, str] = {}
    for raw_code, raw_hash in value.items():
        code = str(raw_code).strip()
        if not code or code in result:
            raise ValueError("expected_input_hashes 股票代碼無效或重複")
        result[code] = _require_sha256(raw_hash, f"expected_input_hashes[{code}]")
    return result


def _parse_iso_date(value: Any, field_name: str) -> date:
    if not isinstance(value, str):
        _fail("snapshot_date_invalid", f"{field_name} 必須是 ISO date 字串")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("snapshot_date_invalid", f"{field_name} 必須是 ISO date 字串")
    if parsed.isoformat() != value:
        _fail("snapshot_date_invalid", f"{field_name} 必須使用 YYYY-MM-DD 格式")
    return parsed


def _validate_cutoff(value: Any, decision_date: date) -> datetime:
    parsed = _validate_aware_timestamp(value, "decision_cutoff")
    if parsed.utcoffset() != timedelta(hours=8) or parsed.date() != decision_date:
        _fail("snapshot_cutoff_invalid", "decision_cutoff 必須是當日 Asia/Taipei (+08:00)")
    return parsed


def _validate_aware_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        _fail("snapshot_timestamp_invalid", f"{field_name} 必須是 aware ISO datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail("snapshot_timestamp_invalid", f"{field_name} 必須是 aware ISO datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("snapshot_timestamp_invalid", f"{field_name} 必須帶 timezone offset")
    return parsed


def _require_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("snapshot_hash_invalid", f"{field_name} 必須是 lowercase SHA-256 hex")
    return value


def _fail(code: str, message: str) -> NoReturn:
    raise DailyMarketSnapshotVerificationError(code, message)
