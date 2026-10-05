"""以有界 DTO 建立並發布可驗證的研究用每日市場快照。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Iterator, Mapping, Sequence
import weakref
from zoneinfo import ZoneInfo

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
    DailyMarketFeatureSnapshot,
    DailyMarketFeatureSnapshotService,
    daily_market_feature_input_fingerprint,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES,
    DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
    DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_snapshot_json_bytes,
    cohort_identity_sha256,
    current_method_contract_binding,
    snapshot_artifact_relpath,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
from app_module.stock_research_report_dtos import (
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)
from data_module.ml_storage_capacity import (
    MLStorageCapacityBudget,
    evaluate_capacity,
    filesystem_usage,
    resolve_heavy_chain_safety_reserve,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_MAX_STOCKS = 16
_MAX_PRICE_POINTS_PER_STOCK = 120
_MAX_NEW_BYTES_PER_RUN = 8 * 1024 * 1024
_MAX_TEMPORARY_BYTES_PER_RUN = 8 * 1024 * 1024
_MAX_RETENTION_BYTES = 64 * 1024 * 1024
_MAX_RETENTION_ENTRIES = 4096
_MAX_SOURCE_REF_TEXT = 4096
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROCESS_LOCKS: weakref.WeakValueDictionary[str, threading.Lock] = (
    weakref.WeakValueDictionary()
)
_PROCESS_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True, slots=True)
class DailyMarketSnapshotInput:
    """已讀入的單一股票來源資料；此 DTO 不開啟任何資料來源。"""

    stock_code: str
    scope_identity: str
    price_points: Sequence[StockPricePointDTO]
    technical: StockTechnicalSnapshotDTO | None
    source_refs: Mapping[str, str]

    def __post_init__(self) -> None:
        stock_code = str(self.stock_code).strip()
        scope_identity = str(self.scope_identity).strip()
        if not stock_code or len(stock_code) > 32:
            raise ValueError("stock_code 必須是 1 至 32 字元的非空代碼")
        if not scope_identity or len(scope_identity) > _MAX_SOURCE_REF_TEXT:
            raise ValueError("scope_identity 必須是有界非空字串")
        if isinstance(self.price_points, (str, bytes)) or not isinstance(
            self.price_points, Sequence
        ):
            raise TypeError("price_points 必須是有界的 StockPricePointDTO 序列")
        if len(self.price_points) > _MAX_PRICE_POINTS_PER_STOCK:
            raise ValueError(
                f"每股 price_points 不可超過 {_MAX_PRICE_POINTS_PER_STOCK} 筆"
            )
        if not isinstance(self.source_refs, Mapping):
            raise TypeError("source_refs 必須是 mapping")
        if len(self.source_refs) != 4:
            raise ValueError("source_refs 必須剛好包含 daily-market-snapshot.v1 四個欄位")
        source_refs = dict(self.source_refs)
        required_refs = {"database", "schema_identity_sha256", "price", "technical"}
        if set(source_refs) != required_refs:
            raise ValueError("source_refs 欄位不符合 daily-market-snapshot.v1")
        for value in source_refs.values():
            if not isinstance(value, str) or not value.strip() or len(value) > _MAX_SOURCE_REF_TEXT:
                raise ValueError("source_refs 必須是有界非空字串")
        if _SHA256_RE.fullmatch(source_refs["schema_identity_sha256"]) is None:
            raise ValueError("schema_identity_sha256 必須是 lowercase SHA-256")
        object.__setattr__(self, "stock_code", stock_code)
        object.__setattr__(self, "scope_identity", scope_identity)
        object.__setattr__(self, "price_points", tuple(self.price_points))
        object.__setattr__(self, "source_refs", source_refs)


@dataclass(frozen=True, slots=True)
class DailyMarketSnapshotProductionResult:
    status: str
    cohort_id: str
    decision_date: str
    declared_stock_codes: tuple[str, ...] = ()
    reused_stock_codes: tuple[str, ...] = ()
    recomputed_stock_codes: tuple[str, ...] = ()
    missing_stock_codes: tuple[str, ...] = ()
    source_errors: Mapping[str, str] = field(default_factory=dict)
    manifest_sha256: str = ""
    manifest_identity_sha256: str = ""
    published: bool = False
    persistent_new_bytes: int = 0
    temporary_peak_bytes: int = 0
    total_retention_bytes: int = 0
    capacity_preflight: Mapping[str, Any] = field(default_factory=dict)
    rebuild_reason: str = ""
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cohort_id": self.cohort_id,
            "decision_date": self.decision_date,
            "declared_stock_codes": list(self.declared_stock_codes),
            "reused_stock_codes": list(self.reused_stock_codes),
            "recomputed_stock_codes": list(self.recomputed_stock_codes),
            "missing_stock_codes": list(self.missing_stock_codes),
            "source_errors": dict(self.source_errors),
            "manifest_sha256": self.manifest_sha256,
            "manifest_identity_sha256": self.manifest_identity_sha256,
            "published": self.published,
            "persistent_new_bytes": self.persistent_new_bytes,
            "temporary_peak_bytes": self.temporary_peak_bytes,
            "total_retention_bytes": self.total_retention_bytes,
            "capacity_preflight": dict(self.capacity_preflight),
            "rebuild_reason": self.rebuild_reason,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


SourceLoader = Callable[[str, date], DailyMarketSnapshotInput]
CapacityProbe = Callable[[Path], Mapping[str, Any]]
Clock = Callable[[], datetime]


class DailyMarketSnapshotProducer:
    """從有界 DTO 建立並發布小型不可變特徵產物。"""

    def __init__(
        self,
        root: str | Path,
        *,
        capacity_probe: CapacityProbe = filesystem_usage,
        reserve_bytes: int | None = None,
        clock: Clock | None = None,
        feature_service: DailyMarketFeatureSnapshotService | None = None,
        repository: DailyMarketSnapshotRepository | None = None,
    ) -> None:
        if root is None or not str(root).strip():
            raise ValueError("producer root is required")
        self.root = Path(root).expanduser().resolve()
        self.capacity_probe = capacity_probe
        self.reserve_bytes = resolve_heavy_chain_safety_reserve(reserve_bytes)
        self.clock = clock or (lambda: datetime.now(_TAIPEI))
        self.feature_service = feature_service or DailyMarketFeatureSnapshotService(max_entries=4)
        self.repository = repository or DailyMarketSnapshotRepository(self.root)

    def produce(
        self,
        *,
        cohort_id: str,
        decision_cutoff: datetime,
        stock_codes: Sequence[str],
        source_loader: SourceLoader,
        before_publish: Callable[[], None] | None = None,
    ) -> DailyMarketSnapshotProductionResult:
        logical_cohort = str(cohort_id).strip()
        if not logical_cohort:
            raise ValueError("cohort_id 不可為空")
        cutoff = _normalise_cutoff(decision_cutoff)
        decision_date = cutoff.date()
        declared_codes = _normalise_stock_codes(stock_codes)
        if len(declared_codes) > _MAX_STOCKS:
            raise ValueError(f"stock_codes 最多 {_MAX_STOCKS} 檔")
        if not declared_codes:
            raise ValueError("stock_codes 必須明示至少一檔股票")
        if not callable(source_loader):
            raise TypeError("source_loader 必須可呼叫")

        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("producer clock 必須是 timezone-aware datetime")
        if cutoff > now.astimezone(_TAIPEI):
            return self._result(
                "future_decision_cutoff",
                logical_cohort,
                decision_date,
                declared_stock_codes=declared_codes,
                error_code="future_decision_cutoff",
                error_message="decision_cutoff 晚於目前時間，拒絕產生未來快照。",
            )

        with _producer_lock(self.root) as acquired:
            if not acquired:
                return self._result(
                    "busy",
                    logical_cohort,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    error_code="producer_busy",
                    error_message="同一 snapshot root 正由另一個 producer 使用。",
                )
            return self._produce_locked(
                cohort_id=logical_cohort,
                cutoff=cutoff,
                decision_date=decision_date,
                declared_codes=declared_codes,
                source_loader=source_loader,
                before_publish=before_publish,
            )

    def _produce_locked(
        self,
        *,
        cohort_id: str,
        cutoff: datetime,
        decision_date: date,
        declared_codes: tuple[str, ...],
        source_loader: SourceLoader,
        before_publish: Callable[[], None] | None,
    ) -> DailyMarketSnapshotProductionResult:
        previous, rebuild_reason, previous_error = self._load_previous(
            cohort_id=cohort_id,
            decision_date=decision_date,
        )
        if previous_error:
            return self._result(
                "prior_snapshot_invalid",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                rebuild_reason=rebuild_reason,
                error_code=previous_error[0],
                error_message=previous_error[1],
                total_retention_bytes=self._retained_bytes(),
            )

        try:
            contracts, contracts_sha256 = current_method_contract_binding()
        except DailyMarketSnapshotVerificationError as exc:
            return self._result(
                "prior_snapshot_invalid",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                rebuild_reason="method_contract_registry_invalid",
                error_code=exc.code,
                error_message=str(exc),
                total_retention_bytes=self._retained_bytes(),
            )

        previous_records = {
            str(item["stock_code"]): item
            for item in (previous.manifest.get("stocks", ()) if previous else ())
            if isinstance(item, Mapping) and isinstance(item.get("stock_code"), str)
        }
        inputs: dict[str, DailyMarketSnapshotInput] = {}
        input_hashes: dict[str, str] = {}
        source_errors: dict[str, str] = {}
        reused_codes: list[str] = []
        recomputed_codes: list[str] = []
        missing_codes: list[str] = []
        snapshots: dict[str, dict[str, Any]] = {}
        records: dict[str, dict[str, Any]] = {}

        for stock_code in declared_codes:
            try:
                item = source_loader(stock_code, decision_date)
                self._validate_input(item, stock_code)
                input_hash = daily_market_feature_input_fingerprint(
                    stock_code=item.stock_code,
                    decision_date=decision_date,
                    scope_identity=item.scope_identity,
                    price_points=item.price_points,
                    technical=item.technical,
                )
            except Exception as exc:
                source_errors[stock_code] = f"{type(exc).__name__}: {exc}"
                return self._result(
                    "source_unavailable",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    missing_stock_codes=(stock_code,),
                    source_errors=source_errors,
                    rebuild_reason=rebuild_reason,
                    total_retention_bytes=self._retained_bytes(),
                    error_code="source_input_invalid",
                    error_message=f"{stock_code} 來源 DTO 載入或驗證失敗；未發布快照。",
                )

            inputs[stock_code] = item
            input_hashes[stock_code] = input_hash

        for stock_code in declared_codes:
            item = inputs[stock_code]
            input_hash = input_hashes[stock_code]
            old_record = previous_records.get(stock_code)
            old_snapshot = (previous.stock_snapshots.get(stock_code) if previous else None)
            if (
                old_record is not None
                and old_snapshot is not None
                and old_record.get("input_fingerprint_sha256") == input_hash
                and old_record.get("source_identity") == item.scope_identity
                and old_record.get("source_refs") == dict(item.source_refs)
            ):
                snapshots[stock_code] = old_snapshot
                records[stock_code] = dict(old_record)
                reused_codes.append(stock_code)
                continue

            try:
                snapshot = self.feature_service.project(
                    stock_code=item.stock_code,
                    decision_date=decision_date,
                    scope_identity=item.scope_identity,
                    price_points=item.price_points,
                    technical=item.technical,
                )
                payload = snapshot.to_dict()
                _validate_projected_snapshot(
                    snapshot,
                    payload,
                    stock_code=stock_code,
                    decision_date=decision_date,
                    scope_identity=item.scope_identity,
                    input_hash=input_hash,
                    method_contracts=contracts,
                    method_contracts_sha256=contracts_sha256,
                )
            except Exception as exc:
                return self._result(
                    "projection_failed",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    recomputed_stock_codes=tuple(recomputed_codes),
                    source_errors={stock_code: f"{type(exc).__name__}: {exc}"},
                    rebuild_reason=rebuild_reason,
                    total_retention_bytes=self._retained_bytes(),
                    error_code="feature_projection_failed",
                    error_message=f"{stock_code} 既有特徵投影失敗；未發布快照。",
                )
            artifact_bytes = canonical_snapshot_json_bytes(payload)
            artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
            records[stock_code] = {
                "stock_code": stock_code,
                "source_identity": item.scope_identity,
                "input_fingerprint_sha256": input_hash,
                "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
                "artifact_sha256": artifact_sha,
                "artifact_relpath": snapshot_artifact_relpath(artifact_sha),
                "source_refs": dict(item.source_refs),
            }
            snapshots[stock_code] = payload
            recomputed_codes.append(stock_code)

        unchanged = (
            previous is not None
            and not recomputed_codes
            and tuple(previous.manifest.get("declared_stock_codes", ())) == declared_codes
            and previous.manifest.get("decision_cutoff") == cutoff.isoformat()
        )
        if unchanged and previous is not None:
            try:
                if before_publish is not None:
                    before_publish()
            except Exception as exc:
                return self._result(
                    "source_changed",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    source_errors=source_errors,
                    rebuild_reason=rebuild_reason,
                    manifest_sha256=previous.manifest_sha256,
                    manifest_identity_sha256=previous.manifest_identity_sha256,
                    total_retention_bytes=self._retained_bytes(),
                    error_code="source_stability_check_failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            return self._result(
                "unchanged",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                source_errors=source_errors,
                manifest_sha256=previous.manifest_sha256,
                manifest_identity_sha256=previous.manifest_identity_sha256,
                total_retention_bytes=self._retained_bytes(),
                rebuild_reason=rebuild_reason,
            )

        publish_time = _normalise_clock(self.clock())
        if cutoff > publish_time:
            return self._result(
                "future_decision_cutoff",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                error_code="future_decision_cutoff",
                error_message="source 讀取期間 decision_cutoff 變成未來時間；未發布快照。",
            )

        artifact_writes: dict[str, bytes] = {}
        for stock_code in recomputed_codes:
            payload = snapshots[stock_code]
            artifact_bytes = canonical_snapshot_json_bytes(payload)
            artifact_sha = str(records[stock_code]["artifact_sha256"])
            artifact_path = self.root / snapshot_artifact_relpath(artifact_sha)
            if artifact_path.exists():
                existing = _read_bounded_file(artifact_path, DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES)
                if hashlib.sha256(existing).hexdigest() != artifact_sha or existing != artifact_bytes:
                    return self._result(
                        "immutable_artifact_conflict",
                        cohort_id,
                        decision_date,
                        declared_stock_codes=declared_codes,
                        reused_stock_codes=tuple(reused_codes),
                        recomputed_stock_codes=tuple(recomputed_codes),
                        missing_stock_codes=tuple(missing_codes),
                        source_errors=source_errors,
                        rebuild_reason=rebuild_reason,
                        total_retention_bytes=self._retained_bytes(),
                        error_code="immutable_artifact_conflict",
                        error_message=f"既有 artifact 路徑內容不符：{artifact_path.name}",
                    )
            else:
                artifact_writes[artifact_path.as_posix()] = artifact_bytes

        ordered_records = [records[code] for code in sorted(records)]
        manifest: dict[str, Any] = {
            "schema_version": DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
            "manifest_identity_sha256": "0" * 64,
            "cohort_id": cohort_id,
            "cohort_identity": cohort_identity_sha256(cohort_id, declared_codes),
            "declared_stock_codes": list(declared_codes),
            "decision_date": decision_date.isoformat(),
            "decision_cutoff": cutoff.isoformat(),
            "decision_timezone": "Asia/Taipei",
            "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
            "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
            "method_contracts": contracts,
            "method_contracts_sha256": contracts_sha256,
            "stocks": ordered_records,
            "counts": {
                "declared": len(declared_codes),
                "published": len(ordered_records),
                "missing": 0,
            },
            "missing_stocks": [],
            "completeness": "complete_declared_cohort",
            "published_at": publish_time.isoformat(),
            "policy": {"research_only": True, "historical_pit_eligible": False},
        }
        manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
        manifest_bytes = canonical_snapshot_json_bytes(manifest)
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = self.root / snapshot_manifest_relpath(manifest_sha)
        if manifest_path.exists():
            existing_manifest = _read_bounded_file(manifest_path, DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES)
            if hashlib.sha256(existing_manifest).hexdigest() != manifest_sha or existing_manifest != manifest_bytes:
                return self._result(
                    "immutable_manifest_conflict",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    recomputed_stock_codes=tuple(recomputed_codes),
                    missing_stock_codes=tuple(missing_codes),
                    source_errors=source_errors,
                    rebuild_reason=rebuild_reason,
                    total_retention_bytes=self._retained_bytes(),
                    error_code="immutable_manifest_conflict",
                    error_message=f"既有 manifest 路徑內容不符：{manifest_path.name}",
                )
        else:
            artifact_writes[manifest_path.as_posix()] = manifest_bytes

        pointer_payload = {
            "schema_version": DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
            "manifest_sha256": manifest_sha,
        }
        pointer_bytes = canonical_snapshot_json_bytes(pointer_payload)
        if len(pointer_bytes) > DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES:
            return self._result(
                "write_budget_exceeded",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                error_code="pointer_write_budget_exceeded",
                error_message="latest pointer 超過 reader 的固定 byte 上限。",
            )
        object_total = sum(len(value) for key, value in artifact_writes.items() if "/objects/" in key)
        manifest_total = 0 if manifest_path.exists() else len(manifest_bytes)
        persistent_new_bytes = object_total + manifest_total
        temporary_peak_bytes = max(
            [len(pointer_bytes), *(len(value) for value in artifact_writes.values())]
        )
        current_retention = self._retained_bytes(
            additional_entries=len(artifact_writes) + 1
        )
        old_pointer = _read_optional_bounded_file(
            self.root / "latest.json", DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES
        )
        projected_retention = (
            current_retention
            - len(old_pointer or b"")
            + persistent_new_bytes
            + len(pointer_bytes)
        )
        if persistent_new_bytes > _MAX_NEW_BYTES_PER_RUN:
            return self._result(
                "write_budget_exceeded",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=current_retention,
                error_code="persistent_write_budget_exceeded",
                error_message="本次持久新增 bytes 超過固定 8 MiB 預算。",
            )
        if temporary_peak_bytes > _MAX_TEMPORARY_BYTES_PER_RUN:
            return self._result(
                "write_budget_exceeded",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=current_retention,
                error_code="temporary_write_budget_exceeded",
                error_message="本次暫存峰值 bytes 超過固定 8 MiB 預算。",
            )
        for path_text, immutable_bytes in artifact_writes.items():
            maximum = (
                DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES
                if "/objects/" in path_text
                else DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES
            )
            if len(immutable_bytes) > maximum:
                return self._result(
                    "write_budget_exceeded",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    recomputed_stock_codes=tuple(recomputed_codes),
                    persistent_new_bytes=persistent_new_bytes,
                    temporary_peak_bytes=temporary_peak_bytes,
                    total_retention_bytes=current_retention,
                    error_code="immutable_file_budget_exceeded",
                    error_message="snapshot artifact 或 manifest 超過 reader byte 上限。",
                )
        if projected_retention > _MAX_RETENTION_BYTES:
            return self._result(
                "retention_limit_exceeded",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=current_retention,
                error_code="retention_budget_exceeded",
                error_message="不可變 objects/manifests/staging 累積將超過 64 MiB；未清理任何舊證據。",
            )

        try:
            preflight = self._capacity_preflight(
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                stage="before_immutable_writes",
                persistent_existing_bytes=current_retention,
            )
        except Exception as exc:
            return self._result(
                "capacity_probe_failed",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=current_retention,
                error_code="capacity_preflight_failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )
        if not preflight["within_budget"]:
            return self._result(
                "capacity_blocked",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=current_retention,
                capacity_preflight=preflight,
                error_code="capacity_reserve_unavailable",
                error_message="實測自由空間未符合 200 GiB safety reserve 與固定寫入 headroom。",
            )

        staging_dir = self.root / ".staging"
        try:
            for absolute_path, immutable_bytes in artifact_writes.items():
                self._write_immutable(
                    Path(absolute_path), immutable_bytes, staging_dir
                )

            candidate = self.repository.load_manifest(
                manifest_sha256=manifest_sha,
                cohort_id=cohort_id,
                decision_date=decision_date,
                expected_stock_codes=declared_codes,
                expected_input_hashes={
                    code: str(record["input_fingerprint_sha256"])
                    for code, record in records.items()
                },
            )
            if set(candidate.stock_snapshots) != set(records):
                raise DailyMarketSnapshotVerificationError(
                    "snapshot_candidate_scope_mismatch",
                    "候選 manifest reader 回讀股票集合不符。",
                )

            # 發布前重測容量，並為 pointer 暫存保留一個項目額度。
            current_retention = self._retained_bytes(additional_entries=1)
            try:
                publish_preflight = self._capacity_preflight(
                    persistent_new_bytes=0,
                    temporary_peak_bytes=len(pointer_bytes),
                    stage="before_latest_pointer",
                    persistent_existing_bytes=current_retention,
                )
            except Exception as exc:
                return self._result(
                    "capacity_probe_failed",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    recomputed_stock_codes=tuple(recomputed_codes),
                    missing_stock_codes=tuple(missing_codes),
                    source_errors=source_errors,
                    rebuild_reason=rebuild_reason,
                    manifest_sha256=manifest_sha,
                    manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
                    persistent_new_bytes=persistent_new_bytes,
                    temporary_peak_bytes=temporary_peak_bytes,
                    total_retention_bytes=current_retention,
                    capacity_preflight=preflight,
                    error_code="publish_capacity_preflight_failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            if not publish_preflight["within_budget"]:
                return self._result(
                    "capacity_blocked",
                    cohort_id,
                    decision_date,
                    declared_stock_codes=declared_codes,
                    reused_stock_codes=tuple(reused_codes),
                    recomputed_stock_codes=tuple(recomputed_codes),
                    missing_stock_codes=tuple(missing_codes),
                    source_errors=source_errors,
                    rebuild_reason=rebuild_reason,
                    manifest_sha256=manifest_sha,
                    manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
                    persistent_new_bytes=persistent_new_bytes,
                    temporary_peak_bytes=temporary_peak_bytes,
                    total_retention_bytes=current_retention,
                    capacity_preflight=publish_preflight,
                    error_code="capacity_reserve_unavailable_before_publish",
                    error_message="latest.json 發布前可用 headroom 已低於政策門檻。",
                )
            if before_publish is not None:
                try:
                    before_publish()
                except Exception as exc:
                    return self._result(
                        "source_changed",
                        cohort_id,
                        decision_date,
                        declared_stock_codes=declared_codes,
                        reused_stock_codes=tuple(reused_codes),
                        recomputed_stock_codes=tuple(recomputed_codes),
                        manifest_sha256=manifest_sha,
                        manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
                        persistent_new_bytes=persistent_new_bytes,
                        temporary_peak_bytes=temporary_peak_bytes,
                        total_retention_bytes=current_retention,
                        capacity_preflight=publish_preflight,
                        error_code="source_stability_check_failed",
                        error_message=f"{type(exc).__name__}: {exc}",
                    )

            # 候選 manifest 已由正式 reader 驗證；latest 原子替換是提交邊界。
            pointer_path = self.root / "latest.json"
            self._write_pointer(pointer_path, pointer_bytes, staging_dir)
        except DailyMarketSnapshotVerificationError as exc:
            return self._result(
                "verification_failed",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                manifest_sha256=manifest_sha,
                manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=self._retained_bytes(),
                capacity_preflight=preflight,
                error_code=exc.code,
                error_message=str(exc),
            )
        except Exception as exc:
            return self._result(
                "publish_failed",
                cohort_id,
                decision_date,
                declared_stock_codes=declared_codes,
                reused_stock_codes=tuple(reused_codes),
                recomputed_stock_codes=tuple(recomputed_codes),
                missing_stock_codes=tuple(missing_codes),
                source_errors=source_errors,
                rebuild_reason=rebuild_reason,
                manifest_sha256=manifest_sha,
                manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
                persistent_new_bytes=persistent_new_bytes,
                temporary_peak_bytes=temporary_peak_bytes,
                total_retention_bytes=self._retained_bytes(),
                capacity_preflight=preflight,
                error_code="publish_failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        return self._result(
            "published_complete",
            cohort_id,
            decision_date,
            declared_stock_codes=declared_codes,
            reused_stock_codes=tuple(reused_codes),
            recomputed_stock_codes=tuple(recomputed_codes),
            missing_stock_codes=tuple(missing_codes),
            source_errors=source_errors,
            manifest_sha256=manifest_sha,
            manifest_identity_sha256=str(manifest["manifest_identity_sha256"]),
            published=True,
            persistent_new_bytes=persistent_new_bytes,
            temporary_peak_bytes=temporary_peak_bytes,
            total_retention_bytes=projected_retention,
            capacity_preflight=publish_preflight,
            rebuild_reason=rebuild_reason,
        )

    def _load_previous(
        self, *, cohort_id: str, decision_date: date
    ) -> tuple[Any | None, str, tuple[str, str] | None]:
        try:
            previous = self.repository.load_latest(
                cohort_id=cohort_id,
                decision_date=decision_date,
                expected_stock_codes=None,
                expected_input_hashes=None,
            )
            return previous, "", None
        except DailyMarketSnapshotVerificationError as exc:
            if exc.code == "snapshot_pointer_missing":
                return None, "", None
            if exc.code == "snapshot_manifest_legacy_v1":
                # 只有明確呼叫 producer 才可重投影 v2；reader 不會自動遷移舊版。
                return None, "legacy_v1_requires_explicit_reproduction", None
            if exc.code in {"snapshot_cohort_mismatch", "snapshot_decision_date_mismatch"}:
                # 日期或 cohort 不同時允許明確重建，並保留差異原因。
                return None, exc.code, None
            return None, "", (exc.code, str(exc))
        except Exception as exc:
            return None, "", ("prior_snapshot_read_failed", f"{type(exc).__name__}: {exc}")

    def _validate_input(self, item: DailyMarketSnapshotInput, expected_code: str) -> None:
        if not isinstance(item, DailyMarketSnapshotInput):
            raise TypeError("source_loader 必須回傳 DailyMarketSnapshotInput")
        if item.stock_code != expected_code:
            raise ValueError("source_loader 回傳的 stock_code 與要求代碼不同")
        if not item.scope_identity:
            raise ValueError("scope_identity 不可為空")
        if len(item.price_points) > _MAX_PRICE_POINTS_PER_STOCK:
            raise ValueError(f"每股 price_points 不可超過 {_MAX_PRICE_POINTS_PER_STOCK} 筆")
        if item.technical is not None and not isinstance(item.technical, StockTechnicalSnapshotDTO):
            raise TypeError("technical 必須是 StockTechnicalSnapshotDTO 或 None")
        if item.technical is not None and len(item.technical.indicators) > _MAX_PRICE_POINTS_PER_STOCK:
            raise ValueError("每股 technical indicators 不可超過 120 筆")
        if any(not isinstance(point, StockPricePointDTO) for point in item.price_points):
            raise TypeError("price_points 僅接受 StockPricePointDTO")
        if set(item.source_refs) != {"database", "schema_identity_sha256", "price", "technical"}:
            raise ValueError("source_refs 欄位不符合 daily-market-snapshot.v1")
        for value in item.source_refs.values():
            if not isinstance(value, str) or not value.strip() or len(value) > _MAX_SOURCE_REF_TEXT:
                raise ValueError("source_refs 必須是有界非空字串")
        if _SHA256_RE.fullmatch(item.source_refs["schema_identity_sha256"]) is None:
            raise ValueError("schema_identity_sha256 必須是 lowercase SHA-256")

    def _capacity_preflight(
        self,
        *,
        persistent_new_bytes: int,
        temporary_peak_bytes: int,
        stage: str,
        persistent_existing_bytes: int,
    ) -> dict[str, Any]:
        usage = self.capacity_probe(self.root)
        budget = MLStorageCapacityBudget(
            persistent_new_bytes_budget=_MAX_NEW_BYTES_PER_RUN,
            temporary_peak_bytes_budget=_MAX_TEMPORARY_BYTES_PER_RUN,
            safety_reserve_bytes=self.reserve_bytes,
        )
        return evaluate_capacity(
            budget=budget,
            usage=usage,
            stage=stage,
            persistent_existing_bytes=persistent_existing_bytes,
            persistent_new_bytes_estimate=persistent_new_bytes,
            temporary_peak_bytes_observed=temporary_peak_bytes,
        ).as_dict()

    def _retained_bytes(self, *, additional_entries: int = 0) -> int:
        total = 0
        entries_seen = 0
        for relative in ("objects", "manifests", ".staging"):
            root = self.root / relative
            if root.is_symlink():
                raise OSError(f"producer retention path 不接受 symbolic link: {root}")
            if not root.exists():
                continue
            if root.is_symlink() or not root.is_dir():
                raise OSError(f"producer retention path 不是一般目錄: {root}")
            pending = [root]
            while pending:
                directory = pending.pop()
                try:
                    with os.scandir(directory) as iterator:
                        for entry in iterator:
                            entries_seen += 1
                            if entries_seen + additional_entries > _MAX_RETENTION_ENTRIES:
                                raise OSError("producer retention 項目數超過固定 4096 上限")
                            if entry.is_symlink():
                                raise OSError(f"producer retention 不接受 symbolic link: {entry.path}")
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                                continue
                            if entry.is_file(follow_symlinks=False):
                                try:
                                    total += entry.stat(follow_symlinks=False).st_size
                                except OSError as exc:
                                    raise OSError(
                                        f"無法計算 producer retention bytes: {entry.path}"
                                    ) from exc
                                if total > _MAX_RETENTION_BYTES:
                                    return total
                except OSError:
                    raise
        pointer_path = self.root / "latest.json"
        if pointer_path.is_symlink():
            raise OSError("producer latest.json 不接受 symbolic link")
        pointer = _read_optional_bounded_file(
            pointer_path, DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES
        )
        if pointer is not None:
            entries_seen += 1
        if entries_seen + additional_entries > _MAX_RETENTION_ENTRIES:
            raise OSError("producer retention 項目數超過固定 4096 上限")
        return total + len(pointer or b"")

    def _write_immutable(self, final_path: Path, payload: bytes, staging_dir: Path) -> None:
        if "objects" in final_path.parts:
            maximum = DAILY_MARKET_SNAPSHOT_MAX_ARTIFACT_BYTES
        elif "manifests" in final_path.parts:
            maximum = DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES
        else:
            raise ValueError("immutable snapshot path 不在 objects 或 manifests")
        if len(payload) > maximum:
            raise ValueError("immutable snapshot 檔案超過 reader 固定 byte 上限")
        if final_path.exists():
            existing = _read_bounded_file(final_path, maximum)
            if existing != payload:
                raise FileExistsError(f"immutable output already exists with different bytes: {final_path}")
            return
        _atomic_write_bytes(final_path, payload, staging_dir)

    def _write_pointer(self, final_path: Path, payload: bytes, staging_dir: Path) -> None:
        _atomic_write_bytes(final_path, payload, staging_dir)

    @staticmethod
    def _result(
        status: str,
        cohort_id: str,
        decision_date: date,
        **kwargs: Any,
    ) -> DailyMarketSnapshotProductionResult:
        return DailyMarketSnapshotProductionResult(
            status=status,
            cohort_id=cohort_id,
            decision_date=decision_date.isoformat(),
            **kwargs,
        )


def _normalise_cutoff(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
    return value.astimezone(_TAIPEI)


def _normalise_clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("producer clock 必須是 timezone-aware datetime")
    return value.astimezone(_TAIPEI)


def _normalise_stock_codes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("stock_codes 必須是明示代碼序列")
    if len(values) > _MAX_STOCKS:
        raise ValueError(f"stock_codes 最多 {_MAX_STOCKS} 檔")
    if any(not isinstance(value, str) for value in values):
        raise TypeError("stock_codes 僅接受字串代碼")
    codes = tuple(value.strip() for value in values)
    if any(not code for code in codes):
        raise ValueError("stock_codes 不可含空代碼")
    if len(set(codes)) != len(codes):
        raise ValueError("stock_codes 不可重複")
    if any(len(code) > 32 for code in codes):
        raise ValueError("stock_code 長度超過上限")
    return tuple(sorted(codes))


def _validate_projected_snapshot(
    snapshot: DailyMarketFeatureSnapshot,
    payload: Mapping[str, Any],
    *,
    stock_code: str,
    decision_date: date,
    scope_identity: str,
    input_hash: str,
    method_contracts: Mapping[str, Any],
    method_contracts_sha256: str,
) -> None:
    if (
        snapshot.stock_code != stock_code
        or snapshot.decision_date != decision_date
        or snapshot.scope_identity != scope_identity
        or snapshot.input_fingerprint_sha256 != input_hash
    ):
        raise ValueError("projector 回傳的 snapshot identity 與 bounded input 不一致")
    if payload.get("historical_pit_eligible") is True:
        raise ValueError("daily market snapshot 不可宣稱 historical PIT eligible")
    if payload.get("features") is None or payload.get("conditions") is None:
        raise ValueError("projector payload 缺少 features 或 conditions")
    if payload.get("method_contracts") != method_contracts:
        raise ValueError("projector snapshot method_contracts 與 producer registry 不一致")
    if payload.get("method_contracts_sha256") != method_contracts_sha256:
        raise ValueError("projector snapshot method_contracts_sha256 與 producer registry 不一致")
    if getattr(snapshot, "method_contracts_sha256", None) != method_contracts_sha256:
        raise ValueError("projector snapshot identity 未綁定目前 method contract hash")


def _atomic_write_bytes(final_path: Path, payload: bytes, staging_dir: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="daily_market_snapshot_",
        suffix=".tmp",
        dir=str(staging_dir),
    )
    temporary_path = Path(temporary_name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, final_path)
    _fsync_directory(final_path.parent)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    stat_size = path.stat().st_size
    if stat_size > maximum_bytes:
        raise ValueError(f"file exceeds bounded read size: {path}")
    with path.open("rb") as stream:
        payload = stream.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError(f"file exceeds bounded read size: {path}")
    return payload


def _read_optional_bounded_file(path: Path, maximum_bytes: int) -> bytes | None:
    try:
        return _read_bounded_file(path, maximum_bytes)
    except FileNotFoundError:
        return None


@contextmanager
def _producer_lock(root: Path) -> Iterator[bool]:
    root_key = os.path.normcase(str(root.resolve()))
    with _PROCESS_LOCKS_GUARD:
        thread_lock = _PROCESS_LOCKS.setdefault(root_key, threading.Lock())
    if not thread_lock.acquire(blocking=False):
        yield False
        return
    handle: int | None = None
    fallback_handle: Any = None
    acquired = False
    try:
        if os.name == "nt":
            handle, acquired = _acquire_windows_mutex(root_key)
        else:
            fallback_handle, acquired = _acquire_file_lock(root_key)
        yield acquired
    finally:
        if handle is not None and acquired:
            _release_windows_mutex(handle)
        if fallback_handle is not None:
            _release_file_lock(fallback_handle)
        thread_lock.release()


def _acquire_windows_mutex(root_key: str) -> tuple[int | None, bool]:
    digest = hashlib.sha256(root_key.encode("utf-8")).hexdigest()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    wait_single = kernel32.WaitForSingleObject
    wait_single.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    wait_single.restype = ctypes.c_uint32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = create_mutex(None, 0, f"Local\\BaldrDailyMarketSnapshot_{digest}")
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    result = int(wait_single(handle, 0))
    if result in {0x00000000, 0x00000080}:  # WAIT_OBJECT_0 / WAIT_ABANDONED
        return int(handle), True
    close_handle(handle)
    if result == 0x00000102:  # WAIT_TIMEOUT
        return None, False
    raise OSError(ctypes.get_last_error(), f"WaitForSingleObject failed: {result:#x}")


def _release_windows_mutex(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    release = kernel32.ReleaseMutex
    release.argtypes = [ctypes.c_void_p]
    release.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    release(ctypes.c_void_p(handle))
    close_handle(ctypes.c_void_p(handle))


def _acquire_file_lock(root_key: str) -> tuple[Any | None, bool]:
    digest = hashlib.sha256(root_key.encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"daily_market_snapshot_{digest}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
                fcntl_api: Any = __import__("fcntl")
                fcntl_api.flock(
                    handle.fileno(), fcntl_api.LOCK_EX | fcntl_api.LOCK_NB
                )
    except (OSError, BlockingIOError):
        handle.close()
        return None, False
    return handle, True


def _release_file_lock(handle: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl_api: Any = __import__("fcntl")
            fcntl_api.flock(handle.fileno(), fcntl_api.LOCK_UN)
    finally:
        handle.close()
