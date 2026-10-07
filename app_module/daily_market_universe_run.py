"""完整研究母體 run 聚合、保存與全域唯讀查詢。

此層只聚合已保存且經驗證的 parent capture，保存既有 snapshot 投影和查詢索引。
它不開啟正式行情資料庫、不呼叫 producer，也不重算金融數值。

Look-ahead 自查：所有列值來自固定 decision_date/cutoff 的 parent child manifest，
並由既有 strict repository 驗證；不讀取或補入 cutoff 之後的行情，也不使用最新資料。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import heapq
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from app_module.daily_market_feature_snapshot import feature_contract_for_version
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.rule_research_parent_capture import (
    BoundedRuleResearchParentWriter,
    RuleResearchParentCapture,
    read_parent_rule_sample_readiness,
)


DAILY_MARKET_UNIVERSE_RUN_PLAN_SCHEMA = "daily-market-universe-run-plan.v1"
DAILY_MARKET_UNIVERSE_RUN_SCHEMA = "daily-market-universe-run.v1"
DAILY_MARKET_UNIVERSE_RUN_RECEIPT_SCHEMA = "daily-market-universe-run-receipt.v1"
DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_STOCKS = 256
DAILY_MARKET_UNIVERSE_RUN_MAX_BATCH_STOCKS = 16
DAILY_MARKET_UNIVERSE_RUN_MAX_PLAN_BYTES = 16 * 1024 * 1024
DAILY_MARKET_UNIVERSE_RUN_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES = 16 * 1024 * 1024
DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES = 256 * 1024 * 1024
DAILY_MARKET_UNIVERSE_RUN_MAX_PAGE_SIZE = 200
DAILY_MARKET_UNIVERSE_RUN_MAX_PAGE_OFFSET = 1_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_SORT_COLUMNS = {
    "stock_code": "stock_code",
    "data_date": "data_date",
    "close": "close_value",
    "ma20": "ma20_value",
    "ma60": "ma60_value",
    "bbands30_upper": "bbands30_upper_value",
    "combined_state": "combined_state",
}
_CONDITION_COLUMNS = {
    "close_above_ma20": "state_close_above_ma20",
    "close_above_ma60": "state_close_above_ma60",
    "close_above_bbands30_upper": "state_close_above_bbands30_upper",
}
_STATES = {"match", "no_match", "unknown"}


class DailyMarketUniverseRunError(ValueError):
    """以穩定錯誤碼回報 run 契約或保存錯誤。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class DailyMarketUniverseRunCancelled(DailyMarketUniverseRunError):
    """run 收到取消後停止新增 segment。"""


class DailyMarketUniverseRunIncomplete(DailyMarketUniverseRunError):
    """仍有 included segment 缺件，不能發布 complete root。"""


@dataclass(frozen=True, slots=True)
class DailyMarketParentCaptureReference:
    """指向既有 parent capture 的唯讀參照；identity 由保存來源列提供。"""

    snapshot_root: Path | str
    capture_root: Path | str
    universe_path: Path | str
    capture_identity_sha256: str

    def resolved(self) -> DailyMarketParentCaptureReference:
        return DailyMarketParentCaptureReference(
            Path(self.snapshot_root).expanduser().resolve(),
            Path(self.capture_root).expanduser().resolve(),
            Path(self.universe_path).expanduser().resolve(),
            self.capture_identity_sha256,
        )


@dataclass(frozen=True, slots=True)
class DailyMarketParentSourceClock:
    """由 complete parent capture 派生的來源時計與 feature 契約。"""

    decision_date: str
    decision_cutoff: str
    source_binding_json: str
    source_binding_sha256: str
    feature_contract_version: str
    method_contracts_sha256: str

    @property
    def source_binding(self) -> dict[str, Any]:
        value = json.loads(self.source_binding_json)
        if not isinstance(value, dict):
            raise DailyMarketUniverseRunError("source_clock_invalid")
        return value

    @property
    def identity_sha256(self) -> str:
        return _sha256_bytes(_canonical_json(self.to_dict()).encode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_date": self.decision_date,
            "decision_cutoff": self.decision_cutoff,
            "source_binding": self.source_binding,
            "source_binding_sha256": self.source_binding_sha256,
            "feature_contract_version": self.feature_contract_version,
            "method_contracts_sha256": self.method_contracts_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseSegmentPlan:
    """完整宣告母體中的一段；excluded 也計入256檔 segment 邊界。"""

    segment_index: int
    declared_stock_codes: tuple[str, ...]
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]

    @property
    def segment_id(self) -> str:
        return f"segment-{self.segment_index + 1:06d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_index": self.segment_index,
            "segment_id": self.segment_id,
            "declared_stock_codes": list(self.declared_stock_codes),
            "included_stock_codes": list(self.included_stock_codes),
            "excluded_stock_codes": list(self.excluded_stock_codes),
        }


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseRunPlan:
    """固定全母體、decision/source clock、策略版本及 generation 身分。"""

    universe_id: str
    population_version: str
    decision_date: date
    decision_cutoff: str
    strategy_version: str
    source_clock: DailyMarketParentSourceClock | None
    raw_stock_code_count: int
    declared_stock_codes: tuple[str, ...]
    duplicate_stock_codes: tuple[tuple[str, int], ...]
    excluded_stock_codes: tuple[tuple[str, str], ...]
    included_stock_codes: tuple[str, ...]
    segments: tuple[DailyMarketUniverseSegmentPlan, ...]
    generation_identity_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DAILY_MARKET_UNIVERSE_RUN_PLAN_SCHEMA,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff,
            "strategy_version": self.strategy_version,
            "source_clock": self.source_clock.to_dict() if self.source_clock else None,
            "raw_stock_code_count": self.raw_stock_code_count,
            "declared_stock_codes": list(self.declared_stock_codes),
            "duplicate_stock_codes": [
                {"stock_code": code, "occurrences": count}
                for code, count in self.duplicate_stock_codes
            ],
            "excluded_stock_codes": [
                {"stock_code": code, "reason": reason}
                for code, reason in self.excluded_stock_codes
            ],
            "included_stock_codes": list(self.included_stock_codes),
            "segments": [segment.to_dict() for segment in self.segments],
            "generation_identity_sha256": self.generation_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseRunPage:
    generation_identity_sha256: str
    rows: tuple[Mapping[str, Any], ...]
    total_count: int
    filtered_count: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseRunDescriptor:
    generation_identity_sha256: str
    status: str
    output_path: Path
    manifest_sha256: str | None = None
    universe_id: str = ""
    population_version: str = ""
    strategy_version: str = ""
    feature_contract_version: str = ""
    decision_date: str = ""
    decision_cutoff: str = ""
    source_clock: Mapping[str, Any] | None = None
    saved_at: str = ""
    counts: Mapping[str, int] | None = None
    data_completeness: str = "unknown"
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseRunListing:
    items: tuple[DailyMarketUniverseRunDescriptor, ...]
    next_cursor: str | None
    has_more: bool


def parent_source_clock_from_reference(
    reference: DailyMarketParentCaptureReference,
) -> DailyMarketParentSourceClock:
    """從現有 verified parent 派生固定來源時計，不要求輸入 digest。"""

    context = _load_parent_context(reference)
    return context["source_clock"]


def verify_parent_capture_reference(
    reference: DailyMarketParentCaptureReference,
) -> Mapping[str, Any]:
    """strict 核驗 parent→receipt→child pins，回傳可供來源目錄使用的 descriptor。"""

    context = _load_parent_context(reference)
    body = context["body"]
    universe = body["universe"]["value"]
    return {
        "capture_identity_sha256": body["capture_identity_sha256"],
        "capture_sha256": context["receipt"]["capture_sha256"],
        "universe_id": universe["universe_id"],
        "population_version": universe["version"],
        "decision_date": universe["as_of_date"],
        "decision_cutoff": body["decision_cutoff"],
        "feature_contract_version": context["feature_contract_version"],
        "method_contracts_sha256": body["method_contracts_sha256"],
        "source_clock_sha256": context["source_clock"].identity_sha256,
        "included_stock_codes": tuple(universe["included_stock_codes"]),
        "excluded_stock_codes": tuple(
            (item["stock_code"], item["reason"])
            for item in universe["excluded_stock_codes"]
        ),
        "status": body["status"],
        "readiness": context["readiness"],
    }


def plan_daily_market_universe_run(
    *,
    universe_id: str,
    population_version: str,
    raw_stock_codes: Sequence[str],
    excluded_stock_codes: Mapping[str, str] | Sequence[tuple[str, str]] = (),
    decision_date: date,
    decision_cutoff: datetime,
    strategy_version: str,
    source_clock: DailyMarketParentSourceClock | None,
) -> DailyMarketUniverseRunPlan:
    """凍結正規化母體並切成<=256碼 segments；每個 parent 仍最多16個 child batch。"""

    universe_name = _required_text(universe_id, "universe_id", 96)
    population_revision = _required_text(population_version, "population_version", 128)
    strategy_revision = _required_text(strategy_version, "strategy_version", 128)
    if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
        raise DailyMarketUniverseRunError("decision_date_invalid")
    cutoff = _normalize_cutoff(decision_cutoff, decision_date)
    if isinstance(raw_stock_codes, (str, bytes)) or not isinstance(raw_stock_codes, Sequence):
        raise TypeError("raw_stock_codes 必須是股票代碼序列")
    if not raw_stock_codes:
        raise DailyMarketUniverseRunError("universe_empty")

    normalized: list[str] = []
    for raw in raw_stock_codes:
        normalized.append(_normalize_stock_code(raw))
    counts: dict[str, int] = {}
    for code in normalized:
        counts[code] = counts.get(code, 0) + 1
    declared = tuple(sorted(counts))
    duplicates = tuple(sorted((code, count) for code, count in counts.items() if count > 1))
    exclusions = _normalize_exclusions(excluded_stock_codes, declared)
    excluded_codes = {code for code, _reason in exclusions}
    included = tuple(code for code in declared if code not in excluded_codes)
    if included and source_clock is None:
        raise DailyMarketUniverseRunError("source_clock_required")
    if source_clock is not None:
        _validate_source_clock(source_clock)
        if source_clock.decision_date != decision_date.isoformat():
            raise DailyMarketUniverseRunError("source_clock_date_mismatch")
        if source_clock.decision_cutoff != cutoff:
            raise DailyMarketUniverseRunError("source_clock_cutoff_mismatch")
    segments = _partition_population(declared, included, exclusions)
    provisional = {
        "schema_version": DAILY_MARKET_UNIVERSE_RUN_PLAN_SCHEMA,
        "universe_id": universe_name,
        "population_version": population_revision,
        "decision_date": decision_date.isoformat(),
        "decision_cutoff": cutoff,
        "strategy_version": strategy_revision,
        "source_clock": source_clock.to_dict() if source_clock else None,
        "raw_stock_code_count": len(normalized),
        "declared_stock_codes": list(declared),
        "duplicate_stock_codes": [
            {"stock_code": code, "occurrences": count} for code, count in duplicates
        ],
        "excluded_stock_codes": [
            {"stock_code": code, "reason": reason} for code, reason in exclusions
        ],
        "included_stock_codes": list(included),
        "segments": [segment.to_dict() for segment in segments],
    }
    identity = _generation_identity(provisional)
    plan = DailyMarketUniverseRunPlan(
        universe_name,
        population_revision,
        decision_date,
        cutoff,
        strategy_revision,
        source_clock,
        len(normalized),
        declared,
        duplicates,
        exclusions,
        included,
        segments,
        identity,
    )
    if len(_canonical_json(plan.to_dict()).encode("utf-8")) > DAILY_MARKET_UNIVERSE_RUN_MAX_PLAN_BYTES:
        raise DailyMarketUniverseRunError("run_plan_byte_limit")
    return plan


def create_daily_market_universe_run_writer(
    output_root: str | Path,
    plan: DailyMarketUniverseRunPlan,
    *,
    cancel_callback: Any = None,
) -> DailyMarketUniverseRunWriter:
    """建立或續跑同一 generation 的 writer。"""

    return DailyMarketUniverseRunWriter(output_root, plan, cancel_callback=cancel_callback)


class DailyMarketUniverseRunWriter:
    """只寫指定的研究輸出 root；以已驗證 parent refs 建立完整母體 run。"""

    def __init__(
        self,
        output_root: str | Path,
        plan: DailyMarketUniverseRunPlan,
        *,
        cancel_callback: Any = None,
    ) -> None:
        _validate_plan_object(plan)
        self.output_root = _resolve_output_root(output_root)
        self.plan = plan
        self.cancel_callback = cancel_callback
        self._cancel_event = threading.Event()
        self._mutex = threading.RLock()
        self._publication_gate = threading.Lock()
        self._lock_handle: Any = None
        self._staging_root = self.output_root / ".incomplete" / plan.generation_identity_sha256
        self._complete_root = self.output_root / "generations" / plan.generation_identity_sha256
        if self._complete_root.exists():
            raise DailyMarketUniverseRunError("generation_already_published")
        self._check_path_overlap()
        self.output_root.mkdir(parents=True, exist_ok=True)
        _reject_symlink_chain(self.output_root)
        self._acquire_generation_lock()
        try:
            self._staging_root.mkdir(parents=True, exist_ok=True)
            self._segment_results: dict[int, dict[str, Any]] = {}
            self._published = False
            self._load_or_start_progress()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> DailyMarketUniverseRunWriter:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @property
    def progress(self) -> Mapping[str, Any]:
        return self._progress_payload()

    def append_parent_segment(
        self,
        segment_index: int,
        reference: DailyMarketParentCaptureReference,
    ) -> Mapping[str, Any]:
        """驗證並原子保存一個 parent 分段的既有投影。"""

        with self._mutex:
            self._ensure_open()
            self._check_cancelled()
            segment = self._segment_by_index(segment_index)
            if not segment.included_stock_codes:
                raise DailyMarketUniverseRunError("segment_has_no_included_members")
            context = _load_parent_context(reference)
            self._check_cancelled()
            self._check_path_overlap(reference)
            self._validate_parent_context(context, segment)
            rows = _project_verified_parent(context)
            self._check_cancelled()
            row_codes = tuple(item["stock_code"] for item in rows)
            if row_codes != segment.included_stock_codes:
                raise DailyMarketUniverseRunError("parent_projected_membership_mismatch")
            parent_descriptor = _parent_reference_descriptor(context)
            segment_payload = {
                "schema_version": "daily-market-universe-segment-projection.v1",
                "generation_identity_sha256": self.plan.generation_identity_sha256,
                "segment_index": segment.segment_index,
                "segment_id": segment.segment_id,
                "declared_stock_codes": list(segment.declared_stock_codes),
                "included_stock_codes": list(segment.included_stock_codes),
                "excluded_stock_codes": [
                    {"stock_code": code, "reason": reason}
                    for code, reason in self.plan.excluded_stock_codes
                    if code in segment.excluded_stock_codes
                ],
                "parent_reference": parent_descriptor,
                "rows": rows,
            }
            raw = _canonical_json(segment_payload).encode("utf-8")
            if len(raw) > DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES:
                raise DailyMarketUniverseRunError("segment_projection_byte_limit")
            digest = _sha256_bytes(raw)
            existing = self._segment_results.get(segment_index)
            result = _segment_result(
                segment,
                rows,
                parent_descriptor,
                digest,
                context["contract"].condition_keys,
            )
            if existing is not None:
                if _canonical_json(existing) != _canonical_json(result):
                    raise DailyMarketUniverseRunError("segment_reference_conflict")
                self._check_existing_projection(existing, raw)
                return dict(existing)

            segment_file = self._staging_root / result["projection_relpath"]
            segment_file.parent.mkdir(parents=True, exist_ok=True)
            if segment_file.exists():
                _verify_file_digest(segment_file, digest, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
                _existing_raw, existing_payload = _read_json_limited(
                    segment_file, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES
                )
                if _canonical_json(existing_payload).encode("utf-8") != raw:
                    raise DailyMarketUniverseRunError("segment_projection_conflict")
            else:
                _atomic_write_new(segment_file, raw)
            self._check_cancelled()
            self._segment_results[segment_index] = result
            self._save_progress("running")
            return dict(result)

    def cancel(self) -> Mapping[str, Any]:
        """合作式停止；取消狀態保存在 staging，不發布 complete root。"""

        # The gate orders cancellation against the single atomic publication.
        # Release it before waiting on _mutex so a running finalize can observe
        # the accepted request at its final publication check.
        with self._publication_gate:
            self._ensure_open()
            if self._published or self._complete_root.exists():
                raise DailyMarketUniverseRunError("generation_already_published")
            self._cancel_event.set()
        with self._mutex:
            self._ensure_open()
            if self._published:
                raise DailyMarketUniverseRunError("generation_already_published")
            self._save_progress("cancelled")
            return self.progress

    def finalize(self) -> DailyMarketUniverseRunDescriptor:
        """完整 segment 全部核驗後，建立全域 SQLite index 並原子發布 root。"""

        with self._mutex:
            self._ensure_open()
            if self._published or self._complete_root.exists():
                raise DailyMarketUniverseRunError("generation_already_published")
            self._check_cancelled()
            pending = [
                segment.segment_index
                for segment in self.plan.segments
                if segment.included_stock_codes and segment.segment_index not in self._segment_results
            ]
            if pending:
                self._save_progress("incomplete")
                raise DailyMarketUniverseRunIncomplete(
                    "segments_pending", f"仍有 {len(pending)} 個納入分段未完成"
                )
            self._check_cancelled()
            index_path = self._staging_root / "index.sqlite"
            self._build_index(index_path)
            self._check_cancelled()
            index_sha, index_size = _hash_file(
                index_path, DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES
            )
            segment_statuses = self._complete_segment_statuses()
            missing_data = sorted(
                code
                for result in self._segment_results.values()
                for code in result["missing_data_stock_codes"]
            )
            snapshot_missing = sorted(
                code
                for result in self._segment_results.values()
                for code in result["snapshot_missing_stock_codes"]
            )
            unknown_evidence = sorted(
                code
                for result in self._segment_results.values()
                for code in result["unknown_evidence_stock_codes"]
            )
            unknown_counts: dict[str, int] = {}
            for result in self._segment_results.values():
                for key, count in result["condition_unknown_counts"].items():
                    unknown_counts[key] = unknown_counts.get(key, 0) + int(count)
            counts = self._counts(len(self.plan.included_stock_codes))
            source_clock = self.plan.source_clock.to_dict() if self.plan.source_clock else None
            manifest: dict[str, Any] = {
                "schema_version": DAILY_MARKET_UNIVERSE_RUN_SCHEMA,
                "manifest_identity_sha256": "",
                "generation_identity_sha256": self.plan.generation_identity_sha256,
                "plan": self.plan.to_dict(),
                "source_clock": source_clock,
                "source_clock_sha256": self.plan.source_clock.identity_sha256 if self.plan.source_clock else None,
                "strategy_version": self.plan.strategy_version,
                "feature_contract_version": (
                    self.plan.source_clock.feature_contract_version if self.plan.source_clock else None
                ),
                "method_contracts_sha256": (
                    self.plan.source_clock.method_contracts_sha256 if self.plan.source_clock else None
                ),
                "segments": segment_statuses,
                "index": {"relpath": "index.sqlite", "sha256": index_sha, "size_bytes": index_size},
                "counts": counts,
                "missing_data_stock_codes": missing_data,
                "snapshot_missing_stock_codes": snapshot_missing,
                "unknown_evidence_stock_codes": unknown_evidence,
                "condition_unknown_counts": dict(sorted(unknown_counts.items())),
                "data_completeness": "partial_research" if missing_data else "complete_declared_population",
                "status": "complete",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "policy": {
                    "research_only": True,
                    "historical_pit_eligible": False,
                    "natural_authority": False,
                    "formal_eligible": False,
                    "training_eligible": False,
                    "source_availability": "unknown",
                    "market_calendar": "unknown",
                    "outcome_maturity": "unknown",
                },
            }
            manifest["manifest_identity_sha256"] = _manifest_identity(manifest)
            manifest_raw = _canonical_json(manifest).encode("utf-8")
            if len(manifest_raw) > DAILY_MARKET_UNIVERSE_RUN_MAX_MANIFEST_BYTES:
                raise DailyMarketUniverseRunError("run_manifest_byte_limit")
            _atomic_write_replace(self._staging_root / "manifest.json", manifest_raw)
            receipt = {
                "schema_version": DAILY_MARKET_UNIVERSE_RUN_RECEIPT_SCHEMA,
                "generation_identity_sha256": self.plan.generation_identity_sha256,
                "manifest_sha256": _sha256_bytes(manifest_raw),
                "index_sha256": index_sha,
            }
            receipt_raw = _canonical_json(receipt).encode("utf-8")
            _atomic_write_replace(self._staging_root / "complete.json", receipt_raw)
            self._check_cancelled()
            self._complete_root.parent.mkdir(parents=True, exist_ok=True)
            if self._complete_root.exists():
                raise DailyMarketUniverseRunError("generation_already_published")
            publication_cancelled = False
            with self._publication_gate:
                if self._cancel_event.is_set() or (
                    self.cancel_callback is not None and bool(self.cancel_callback())
                ):
                    self._cancel_event.set()
                    publication_cancelled = True
                elif self._complete_root.exists():
                    raise DailyMarketUniverseRunError("generation_already_published")
                else:
                    os.replace(self._staging_root, self._complete_root)
                    self._published = True
            if publication_cancelled:
                self._save_progress("cancelled")
                raise DailyMarketUniverseRunCancelled("run_cancelled")
            self._save_progress_after_publish("complete")
            return _descriptor_from_complete(self._complete_root, manifest, receipt)

    def close(self) -> None:
        handle = self._lock_handle
        if handle is None:
            return
        self._lock_handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                getattr(fcntl, "flock")(handle.fileno(), getattr(fcntl, "LOCK_UN"))
        finally:
            handle.close()

    def _ensure_open(self) -> None:
        if self._lock_handle is None:
            raise DailyMarketUniverseRunError("writer_closed")

    def _acquire_generation_lock(self) -> None:
        lock_root = self.output_root / ".locks"
        lock_root.mkdir(parents=True, exist_ok=True)
        path = lock_root / f"{self.plan.generation_identity_sha256}.lock"
        handle = path.open("a+b")
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                handle.close()
                raise DailyMarketUniverseRunError("run_busy") from exc
        else:
            import fcntl

            try:
                getattr(fcntl, "flock")(
                    handle.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB")
                )
            except OSError as exc:
                handle.close()
                raise DailyMarketUniverseRunError("run_busy") from exc
        self._lock_handle = handle

    def _check_path_overlap(
        self, reference: DailyMarketParentCaptureReference | None = None
    ) -> None:
        candidates: list[Path] = []
        if self.plan.source_clock is not None:
            candidates.append(Path(self.plan.source_clock.source_binding["database"]).resolve())
        if reference is not None:
            resolved = reference.resolved()
            candidates.extend((
                Path(resolved.snapshot_root),
                Path(resolved.capture_root),
                Path(resolved.universe_path),
            ))
        for candidate in candidates:
            _require_disjoint_paths(self.output_root, candidate, "source_output_overlap")

    def _segment_by_index(self, segment_index: int) -> DailyMarketUniverseSegmentPlan:
        if type(segment_index) is not int or not 0 <= segment_index < len(self.plan.segments):
            raise DailyMarketUniverseRunError("segment_index_invalid")
        segment = self.plan.segments[segment_index]
        if segment.segment_index != segment_index:
            raise DailyMarketUniverseRunError("segment_plan_invalid")
        return segment

    def _validate_parent_context(
        self, context: Mapping[str, Any], segment: DailyMarketUniverseSegmentPlan
    ) -> None:
        body = context["body"]
        universe = body["universe"]["value"]
        if universe["universe_id"] != self.plan.universe_id:
            raise DailyMarketUniverseRunError("parent_universe_id_mismatch")
        if universe["version"] != self.plan.population_version:
            raise DailyMarketUniverseRunError("parent_population_version_mismatch")
        if universe["as_of_date"] != self.plan.decision_date.isoformat():
            raise DailyMarketUniverseRunError("parent_decision_date_mismatch")
        if body["decision_cutoff"] != self.plan.decision_cutoff:
            raise DailyMarketUniverseRunError("parent_decision_cutoff_mismatch")
        if tuple(universe["included_stock_codes"]) != segment.included_stock_codes:
            raise DailyMarketUniverseRunError("parent_segment_membership_mismatch")
        if universe["excluded_stock_codes"]:
            raise DailyMarketUniverseRunError("parent_exclusions_must_be_root_scoped")
        if self.plan.source_clock is None or context["source_clock"].to_dict() != self.plan.source_clock.to_dict():
            raise DailyMarketUniverseRunError("parent_source_clock_mismatch")
        if context["readiness"].get("status") != "saved_verified_complete":
            raise DailyMarketUniverseRunError("parent_not_complete")
        batches = body["batches"]
        if not batches or len(batches) > 16:
            raise DailyMarketUniverseRunError("parent_batch_bound")
        if any(len(batch["included_stock_codes"]) > DAILY_MARKET_UNIVERSE_RUN_MAX_BATCH_STOCKS for batch in batches):
            raise DailyMarketUniverseRunError("child_batch_bound")
        if tuple(sorted(code for batch in batches for code in batch["included_stock_codes"])) != segment.included_stock_codes:
            raise DailyMarketUniverseRunError("parent_child_membership_mismatch")

    def _load_or_start_progress(self) -> None:
        progress_path = self._staging_root / "progress.json"
        plan_dict = self.plan.to_dict()
        if progress_path.exists():
            raw, body = _read_json_limited(progress_path, DAILY_MARKET_UNIVERSE_RUN_MAX_PLAN_BYTES)
            if _canonical_json(body).encode("utf-8") != raw:
                raise DailyMarketUniverseRunError("progress_noncanonical")
            if body.get("schema_version") != DAILY_MARKET_UNIVERSE_RUN_SCHEMA:
                raise DailyMarketUniverseRunError("progress_schema_mismatch")
            if body.get("plan") != plan_dict:
                raise DailyMarketUniverseRunError("generation_plan_mismatch")
            segments = body.get("segments")
            if not isinstance(segments, list) or len(segments) != len(self.plan.segments):
                raise DailyMarketUniverseRunError("progress_segments_invalid")
            if set(body) != {
                "schema_version", "generation_identity_sha256", "plan", "segments",
                "counts", "updated_at", "status",
            } or body.get("status") not in {"incomplete", "running", "cancelled"}:
                raise DailyMarketUniverseRunError("progress_fields_invalid")
            for item, segment in zip(segments, self.plan.segments):
                if not isinstance(item, dict):
                    raise DailyMarketUniverseRunError("progress_segment_invalid")
                if (
                    item.get("segment_index") != segment.segment_index
                    or item.get("segment_id") != segment.segment_id
                ):
                    raise DailyMarketUniverseRunError("progress_segment_order_invalid")
                if item.get("status") == "excluded_only":
                    if item != {
                        "segment_index": segment.segment_index,
                        "segment_id": segment.segment_id,
                        "status": "excluded_only",
                        "included_count": 0,
                        "excluded_count": len(segment.excluded_stock_codes),
                    } or segment.included_stock_codes:
                        raise DailyMarketUniverseRunError("progress_excluded_segment_invalid")
                    continue
                if item.get("status") == "pending":
                    if item != {
                        "segment_index": segment.segment_index,
                        "segment_id": segment.segment_id,
                        "status": "pending",
                        "included_count": len(segment.included_stock_codes),
                        "excluded_count": len(segment.excluded_stock_codes),
                    } or not segment.included_stock_codes:
                        raise DailyMarketUniverseRunError("progress_pending_segment_invalid")
                    continue
                if item.get("status") != "processed" or not segment.included_stock_codes:
                    raise DailyMarketUniverseRunError("progress_segment_status_invalid")
                index = item.get("segment_index")
                if type(index) is not int:
                    raise DailyMarketUniverseRunError("progress_segment_index_invalid")
                segment = self._segment_by_index(index)
                loaded = self._load_and_verify_segment(item, segment)
                if index in self._segment_results:
                    raise DailyMarketUniverseRunError("progress_duplicate_segment")
                self._segment_results[index] = loaded
            expected_counts = self._counts(
                sum(len(segment.included_stock_codes) for segment in self.plan.segments
                    if segment.segment_index in self._segment_results)
            )
            if body.get("counts") != expected_counts:
                raise DailyMarketUniverseRunError("progress_counts_mismatch")
            return
        self._save_progress("incomplete")

    def _load_and_verify_segment(
        self,
        item: Mapping[str, Any],
        segment: DailyMarketUniverseSegmentPlan,
    ) -> dict[str, Any]:
        path = _resolve_generation_child(
            self._staging_root, item.get("projection_relpath"), "projection_relpath"
        )
        digest = _require_sha(item.get("projection_sha256"), "projection_sha256")
        raw, payload = _read_json_limited(path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
        if _sha256_bytes(raw) != digest or _canonical_json(payload).encode("utf-8") != raw:
            raise DailyMarketUniverseRunError("segment_projection_hash_mismatch")
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "generation_identity_sha256", "segment_index", "segment_id",
            "declared_stock_codes", "included_stock_codes", "excluded_stock_codes",
            "parent_reference", "rows",
        } or payload.get("schema_version") != "daily-market-universe-segment-projection.v1":
            raise DailyMarketUniverseRunError("segment_projection_fields_invalid")
        if payload.get("generation_identity_sha256") != self.plan.generation_identity_sha256:
            raise DailyMarketUniverseRunError("segment_generation_mismatch")
        expected_exclusions = [
            {"stock_code": code, "reason": reason}
            for code, reason in self.plan.excluded_stock_codes
            if code in segment.excluded_stock_codes
        ]
        if payload.get("segment_index") != segment.segment_index or payload.get("segment_id") != segment.segment_id:
            raise DailyMarketUniverseRunError("segment_index_mismatch")
        if (
            payload.get("declared_stock_codes") != list(segment.declared_stock_codes)
            or payload.get("included_stock_codes") != list(segment.included_stock_codes)
            or payload.get("excluded_stock_codes") != expected_exclusions
        ):
            raise DailyMarketUniverseRunError("segment_membership_mismatch")
        rows = payload.get("rows")
        if not isinstance(rows, list) or [row.get("stock_code") for row in rows] != list(segment.included_stock_codes):
            raise DailyMarketUniverseRunError("segment_rows_invalid")
        reference = _parent_reference_from_descriptor(payload.get("parent_reference"))
        context = _load_parent_context(reference)
        self._validate_parent_context(context, segment)
        expected_ref = _parent_reference_descriptor(context)
        if payload.get("parent_reference") != expected_ref:
            raise DailyMarketUniverseRunError("parent_reference_digest_mismatch")
        if _project_verified_parent(context) != rows:
            raise DailyMarketUniverseRunError("segment_projection_source_mismatch")
        expected = _segment_result(
            segment, rows, expected_ref, digest, context["contract"].condition_keys
        )
        if dict(item) != expected:
            raise DailyMarketUniverseRunError("progress_segment_metadata_mismatch")
        return expected

    def _check_existing_projection(self, item: Mapping[str, Any], raw: bytes) -> None:
        path = _resolve_generation_child(
            self._staging_root, item["projection_relpath"], "projection_relpath"
        )
        _verify_file_digest(path, item["projection_sha256"], DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
        _existing_raw, existing_payload = _read_json_limited(path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
        if _canonical_json(existing_payload).encode("utf-8") != raw:
            raise DailyMarketUniverseRunError("segment_projection_conflict")

    def _progress_payload(self) -> dict[str, Any]:
        segments: list[dict[str, Any]] = []
        for segment in self.plan.segments:
            result = self._segment_results.get(segment.segment_index)
            if result is not None:
                segments.append(dict(result))
            elif not segment.included_stock_codes:
                segments.append({
                    "segment_index": segment.segment_index,
                    "segment_id": segment.segment_id,
                    "status": "excluded_only",
                    "included_count": 0,
                    "excluded_count": len(segment.excluded_stock_codes),
                })
            else:
                segments.append({
                    "segment_index": segment.segment_index,
                    "segment_id": segment.segment_id,
                    "status": "pending",
                    "included_count": len(segment.included_stock_codes),
                    "excluded_count": len(segment.excluded_stock_codes),
                })
        processed = sum(int(item.get("row_count", 0)) for item in segments)
        return {
            "schema_version": DAILY_MARKET_UNIVERSE_RUN_SCHEMA,
            "generation_identity_sha256": self.plan.generation_identity_sha256,
            "plan": self.plan.to_dict(),
            "segments": segments,
            "counts": self._counts(processed),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _save_progress(self, status: str) -> None:
        body = self._progress_payload()
        body["status"] = status
        raw = _canonical_json(body).encode("utf-8")
        if len(raw) > DAILY_MARKET_UNIVERSE_RUN_MAX_PLAN_BYTES:
            raise DailyMarketUniverseRunError("progress_byte_limit")
        _atomic_write_replace(self._staging_root / "progress.json", raw)

    def _save_progress_after_publish(self, status: str) -> None:
        # 完成 receipt 已隨目錄 rename 發布；staging 內不保留第二份可變進度檔。
        self._published_status = status

    def _check_cancelled(self) -> None:
        if self._cancel_event.is_set() or (
            self.cancel_callback is not None and bool(self.cancel_callback())
        ):
            self._cancel_event.set()
            self._save_progress("cancelled")
            raise DailyMarketUniverseRunCancelled("run_cancelled")

    def _counts(self, processed_count: int) -> dict[str, int]:
        excluded_count = len(self.plan.excluded_stock_codes)
        included_count = len(self.plan.included_stock_codes)
        snapshot_missing = {
            code
            for result in self._segment_results.values()
            for code in result.get("snapshot_missing_stock_codes", ())
        }
        unknown_evidence = {
            code
            for result in self._segment_results.values()
            for code in result.get("unknown_evidence_stock_codes", ())
        }
        return {
            "declared_unique_count": len(self.plan.declared_stock_codes),
            "raw_stock_code_count": self.plan.raw_stock_code_count,
            "duplicate_stock_count": len(self.plan.duplicate_stock_codes),
            "duplicate_occurrence_count": sum(count - 1 for _code, count in self.plan.duplicate_stock_codes),
            "included_count": included_count,
            "excluded_count": excluded_count,
            "processed_count": processed_count,
            "pending_count": max(0, included_count - processed_count),
            "snapshot_missing_stock_count": len(snapshot_missing),
            "unknown_evidence_stock_count": len(unknown_evidence),
            "missing_data_stock_count": len(snapshot_missing | unknown_evidence),
        }

    def _complete_segment_statuses(self) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        for segment in self.plan.segments:
            result = self._segment_results.get(segment.segment_index)
            if result is not None:
                statuses.append(dict(result))
            elif not segment.included_stock_codes:
                statuses.append({
                    "segment_index": segment.segment_index,
                    "segment_id": segment.segment_id,
                    "status": "excluded_only",
                    "included_count": 0,
                    "excluded_count": len(segment.excluded_stock_codes),
                })
            else:
                raise DailyMarketUniverseRunIncomplete("segments_pending")
        return statuses

    def _build_index(self, index_path: Path) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".index-", suffix=".sqlite", dir=str(self._staging_root))
        os.close(fd)
        tmp_path = Path(tmp_name)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(tmp_path)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.create_collation("DECIMAL", _decimal_collation)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE universe_members ("
                "stock_code TEXT PRIMARY KEY, is_excluded INTEGER NOT NULL, excluded_reason TEXT, "
                "processed INTEGER NOT NULL, snapshot_missing INTEGER NOT NULL, combined_state TEXT, "
                "data_date TEXT, close_value TEXT COLLATE DECIMAL, ma20_value TEXT COLLATE DECIMAL, "
                "ma60_value TEXT COLLATE DECIMAL, bbands30_upper_value TEXT COLLATE DECIMAL, "
                "state_close_above_ma20 TEXT, state_close_above_ma60 TEXT, "
                "state_close_above_bbands30_upper TEXT, payload_json TEXT NOT NULL)"
            )
            connection.execute("CREATE INDEX ix_universe_date ON universe_members(data_date, stock_code)")
            connection.execute("CREATE INDEX ix_universe_close ON universe_members(close_value COLLATE DECIMAL, stock_code)")
            connection.execute("CREATE INDEX ix_universe_ma20 ON universe_members(ma20_value COLLATE DECIMAL, stock_code)")
            row_by_code: dict[str, dict[str, Any]] = {}
            for result in self._segment_results.values():
                path = _resolve_generation_child(
                    self._staging_root, result["projection_relpath"], "projection_relpath"
                )
                raw, projection = _read_json_limited(path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
                if _sha256_bytes(raw) != result["projection_sha256"]:
                    raise DailyMarketUniverseRunError("segment_projection_hash_mismatch")
                for row in projection["rows"]:
                    code = row["stock_code"]
                    if code in row_by_code:
                        raise DailyMarketUniverseRunError("duplicate_stock_across_segments")
                    row_by_code[code] = row
            if tuple(sorted(row_by_code)) != self.plan.included_stock_codes:
                raise DailyMarketUniverseRunError("processed_population_mismatch")
            exclusions = dict(self.plan.excluded_stock_codes)
            insert_rows = []
            for code in self.plan.declared_stock_codes:
                row = row_by_code.get(code)
                reason = exclusions.get(code)
                if reason is None and row is None:
                    raise DailyMarketUniverseRunError("processed_population_mismatch")
                insert_rows.append(_index_values(code, row, reason))
            connection.executemany(
                "INSERT INTO universe_members VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", insert_rows
            )
            connection.commit()
            connection.execute("PRAGMA optimize")
            connection.close()
            connection = None
            if tmp_path.stat().st_size > DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES:
                raise DailyMarketUniverseRunError("run_index_byte_limit")
            with tmp_path.open("r+b") as handle:
                os.fsync(handle.fileno())
            if index_path.exists():
                _verify_staging_index(index_path, insert_rows)
                tmp_path.unlink()
            else:
                os.replace(tmp_path, index_path)
        except BaseException:
            try:
                if connection is not None:
                    connection.close()
            except Exception:
                pass
            tmp_path.unlink(missing_ok=True)
            raise


class DailyMarketUniverseRunReader:
    """strict 唯讀 run reader；打開時驗 root、parent refs、projection 與 index digest。"""

    def __init__(self, output_root: Path, generation_identity_sha256: str) -> None:
        identity = _require_sha(generation_identity_sha256, "generation_identity_sha256")
        self.output_root = output_root.resolve()
        self.generation_identity_sha256 = identity
        self.run_root = self.output_root / "generations" / identity
        if not self.run_root.is_dir():
            raise DailyMarketUniverseRunError("complete_generation_missing")
        self.manifest, self.receipt, self.manifest_sha256 = _read_complete_generation(self.run_root, verify_index=True)
        self.plan = _validate_manifest_plan(self.manifest)
        self._verify_manifest_semantics()
        self._connection = _connect_readonly(self.run_root / "index.sqlite")
        try:
            self._connection.create_collation("DECIMAL", _decimal_collation)
            self._verify_index_rows()
        except BaseException:
            self._connection.close()
            raise

    @classmethod
    def open(
        cls,
        output_root: str | Path,
        generation_identity_sha256: str,
    ) -> DailyMarketUniverseRunReader:
        return cls(Path(output_root), generation_identity_sha256)

    @property
    def counts(self) -> Mapping[str, int]:
        return dict(self.manifest["counts"])

    @property
    def source_descriptor(self) -> Mapping[str, Any]:
        descriptor = _descriptor_from_complete(self.run_root, self.manifest, self.receipt)
        return {
            "generation_identity_sha256": descriptor.generation_identity_sha256,
            "status": descriptor.status,
            "output_path": str(descriptor.output_path),
            "manifest_sha256": descriptor.manifest_sha256,
            "universe_id": descriptor.universe_id,
            "population_version": descriptor.population_version,
            "strategy_version": descriptor.strategy_version,
            "feature_contract_version": descriptor.feature_contract_version,
            "decision_date": descriptor.decision_date,
            "decision_cutoff": descriptor.decision_cutoff,
            "source_clock": dict(descriptor.source_clock or {}),
            "saved_at": descriptor.saved_at,
            "counts": dict(descriptor.counts or {}),
            "data_completeness": descriptor.data_completeness,
            "error_code": descriptor.error_code,
        }

    def query(
        self,
        *,
        sort_key: str = "stock_code",
        descending: bool = False,
        page: int = 0,
        page_size: int = 50,
        condition_key: str | None = None,
        condition_keys: Sequence[str] | None = None,
        combine_mode: str = "AND",
        state_filter: str = "all",
        stock_filter: str = "",
    ) -> DailyMarketUniverseRunPage:
        if condition_keys is not None and condition_key is not None:
            raise DailyMarketUniverseRunError("query_condition_conflict")
        if sort_key not in _SORT_COLUMNS:
            raise DailyMarketUniverseRunError("query_sort_invalid")
        if type(descending) is not bool:
            raise TypeError("descending 必須是 bool")
        if type(page_size) is not int or not 1 <= page_size <= DAILY_MARKET_UNIVERSE_RUN_MAX_PAGE_SIZE:
            raise DailyMarketUniverseRunError("query_page_size_invalid")
        if type(page) is not int or page < 0 or page * page_size > DAILY_MARKET_UNIVERSE_RUN_MAX_PAGE_OFFSET:
            raise DailyMarketUniverseRunError("query_page_invalid")
        if condition_key is not None and condition_key not in _CONDITION_COLUMNS:
            raise DailyMarketUniverseRunError("query_condition_invalid")
        query_condition_keys: tuple[str, ...] | None = None
        query_combine_mode = "AND"
        if condition_keys is not None:
            query_condition_keys = _normalize_query_condition_keys(condition_keys)
            query_combine_mode = _normalize_query_combine_mode(combine_mode)
        allowed_states = _STATES | {"excluded", "processed", "pending", "all"}
        if state_filter not in allowed_states:
            raise DailyMarketUniverseRunError("query_state_invalid")
        if not isinstance(stock_filter, str) or len(stock_filter) > 128:
            raise DailyMarketUniverseRunError("query_stock_filter_invalid")
        predicates: list[str] = []
        parameters: list[Any] = []
        if query_condition_keys is not None:
            condition_state_sql = _combined_condition_state_sql(
                query_condition_keys,
                query_combine_mode,
                self._feature_condition_keys(),
            )
            if state_filter == "excluded":
                predicates.append("is_excluded = 1")
            elif state_filter == "processed":
                predicates.append("processed = 1 AND is_excluded = 0")
            elif state_filter == "pending":
                predicates.append("processed = 0 AND is_excluded = 0")
            elif state_filter in _STATES:
                # 被排除的代碼不是條件未知候選，必須先排除再套三值條件。
                predicates.append("is_excluded = 0")
                predicates.append(f"({condition_state_sql}) = ?")
                parameters.append(state_filter)
        elif condition_key is not None:
            condition_column = _CONDITION_COLUMNS[condition_key]
            if state_filter == "excluded":
                predicates.append("is_excluded = 1")
            elif state_filter == "processed":
                predicates.append("processed = 1 AND is_excluded = 0")
            elif state_filter == "pending":
                predicates.append("processed = 0 AND is_excluded = 0")
            elif state_filter != "all":
                predicates.append(f"{condition_column} = ?")
                parameters.append(state_filter)
        else:
            if state_filter == "excluded":
                predicates.append("is_excluded = 1")
            elif state_filter == "processed":
                predicates.append("processed = 1 AND is_excluded = 0")
            elif state_filter == "pending":
                predicates.append("processed = 0 AND is_excluded = 0")
            elif state_filter in _STATES:
                predicates.append("combined_state = ?")
                parameters.append(state_filter)
        if stock_filter:
            predicates.append("instr(upper(stock_code), upper(?)) > 0")
            parameters.append(stock_filter)
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        total_count = int(self._connection.execute("SELECT COUNT(*) FROM universe_members").fetchone()[0])
        filtered_count = int(self._connection.execute(
            f"SELECT COUNT(*) FROM universe_members{where}", parameters
        ).fetchone()[0])
        column = _SORT_COLUMNS[sort_key]
        if sort_key == "combined_state" and query_condition_keys is not None:
            # 動態查詢排序沿當次三態；排除列不借索引內的舊組合狀態。
            column = f"CASE WHEN is_excluded = 1 THEN NULL ELSE ({condition_state_sql}) END"
        direction = "DESC" if descending else "ASC"
        if sort_key == "stock_code":
            order = f"stock_code {direction}"
        else:
            collation = " COLLATE DECIMAL" if sort_key in {"close", "ma20", "ma60", "bbands30_upper"} else ""
            order = f"({column} IS NULL) ASC, {column}{collation} {direction}, stock_code ASC"
        offset = page * page_size
        rows = self._connection.execute(
            f"SELECT payload_json FROM universe_members{where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*parameters, page_size, offset],
        ).fetchall()
        decoded_rows = [json.loads(row[0]) for row in rows]
        if query_condition_keys is not None:
            from app_module.daily_market_research_screener import evaluate_daily_market_conditions

            for row in decoded_rows:
                if row.get("included") is False:
                    # 排除列保留母體狀態與原因，不算成條件未知候選。
                    continue
                raw_conditions = row.get("conditions")
                conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
                evaluation = evaluate_daily_market_conditions(
                    conditions,
                    query_condition_keys,
                    query_combine_mode,
                    expected_decision_date=self.plan.decision_date,
                )
                row["combined_state"] = evaluation.combined_state
                row["why"] = list(evaluation.why)
                row["why_not"] = list(evaluation.why_not)
        decoded = tuple(decoded_rows)
        return DailyMarketUniverseRunPage(
            self.generation_identity_sha256, decoded, total_count, filtered_count, page, page_size
        )

    def _feature_condition_keys(self) -> frozenset[str]:
        source_clock = self.plan.source_clock
        if source_clock is None:
            return frozenset()
        contract = feature_contract_for_version(source_clock.feature_contract_version)
        return frozenset(contract.condition_keys)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> DailyMarketUniverseRunReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _verify_manifest_semantics(self) -> None:
        manifest = self.manifest
        if manifest.get("status") != "complete" or manifest.get("generation_identity_sha256") != self.generation_identity_sha256:
            raise DailyMarketUniverseRunError("run_not_complete")
        if manifest.get("plan") != self.plan.to_dict():
            raise DailyMarketUniverseRunError("run_plan_binding_mismatch")
        counts = manifest.get("counts")
        expected_counts = {
            "declared_unique_count": len(self.plan.declared_stock_codes),
            "raw_stock_code_count": self.plan.raw_stock_code_count,
            "duplicate_stock_count": len(self.plan.duplicate_stock_codes),
            "duplicate_occurrence_count": sum(n - 1 for _code, n in self.plan.duplicate_stock_codes),
            "included_count": len(self.plan.included_stock_codes),
            "excluded_count": len(self.plan.excluded_stock_codes),
            "processed_count": len(self.plan.included_stock_codes),
            "pending_count": 0,
        }
        if manifest.get("data_completeness") not in {"complete_declared_population", "partial_research"}:
            raise DailyMarketUniverseRunError("run_data_completeness_invalid")
        if manifest.get("policy") != {
            "research_only": True,
            "historical_pit_eligible": False,
            "natural_authority": False,
            "formal_eligible": False,
            "training_eligible": False,
            "source_availability": "unknown",
            "market_calendar": "unknown",
            "outcome_maturity": "unknown",
        }:
            raise DailyMarketUniverseRunError("run_policy_invalid")
        segment_items = manifest.get("segments")
        if not isinstance(segment_items, list) or len(segment_items) != len(self.plan.segments):
            raise DailyMarketUniverseRunError("run_segments_invalid")
        snapshot_missing_codes: set[str] = set()
        unknown_evidence_codes: set[str] = set()
        missing_codes: set[str] = set()
        contract_keys = (
            tuple(feature_contract_for_version(self.plan.source_clock.feature_contract_version).condition_keys)
            if self.plan.source_clock is not None else ()
        )
        unknown_counts = {key: 0 for key in contract_keys}
        for item, segment in zip(segment_items, self.plan.segments):
            if not isinstance(item, Mapping):
                raise DailyMarketUniverseRunError("run_segment_invalid")
            if item.get("segment_index") != segment.segment_index or item.get("segment_id") != segment.segment_id:
                raise DailyMarketUniverseRunError("run_segment_order_invalid")
            if not segment.included_stock_codes:
                if (
                    item != {
                        "segment_index": segment.segment_index,
                        "segment_id": segment.segment_id,
                        "status": "excluded_only",
                        "included_count": 0,
                        "excluded_count": len(segment.excluded_stock_codes),
                    }
                ):
                    raise DailyMarketUniverseRunError("run_excluded_segment_invalid")
                continue
            if item.get("status") != "processed":
                raise DailyMarketUniverseRunError("run_segment_incomplete")
            result = self._verify_saved_segment(item, segment)
            for row in result["rows"]:
                code = row["stock_code"]
                if row.get("snapshot_missing") is True:
                    snapshot_missing_codes.add(code)
                if _unknown_evidence_codes([row], contract_keys):
                    unknown_evidence_codes.add(code)
            for key, count in _condition_unknown_counts(result["rows"], contract_keys).items():
                unknown_counts[key] += count
        missing_codes = snapshot_missing_codes | unknown_evidence_codes
        declared_missing = manifest.get("missing_data_stock_codes")
        if declared_missing != sorted(missing_codes):
            raise DailyMarketUniverseRunError("run_missing_data_count_mismatch")
        if manifest.get("snapshot_missing_stock_codes") != sorted(snapshot_missing_codes):
            raise DailyMarketUniverseRunError("run_snapshot_missing_count_mismatch")
        if manifest.get("unknown_evidence_stock_codes") != sorted(unknown_evidence_codes):
            raise DailyMarketUniverseRunError("run_unknown_evidence_count_mismatch")
        expected_counts.update({
            "snapshot_missing_stock_count": len(snapshot_missing_codes),
            "unknown_evidence_stock_count": len(unknown_evidence_codes),
            "missing_data_stock_count": len(missing_codes),
        })
        if counts != expected_counts:
            raise DailyMarketUniverseRunError("run_counts_mismatch")
        expected_completeness = "partial_research" if missing_codes else "complete_declared_population"
        if manifest.get("data_completeness") != expected_completeness:
            raise DailyMarketUniverseRunError("run_data_completeness_mismatch")
        if manifest.get("condition_unknown_counts") != dict(sorted(unknown_counts.items())):
            raise DailyMarketUniverseRunError("run_condition_unknown_counts_mismatch")

    def _verify_saved_segment(
        self, item: Mapping[str, Any], segment: DailyMarketUniverseSegmentPlan
    ) -> Mapping[str, Any]:
        digest = _require_sha(item.get("projection_sha256"), "projection_sha256")
        path = _resolve_generation_child(
            self.run_root, item.get("projection_relpath"), "projection_relpath"
        )
        raw, payload = _read_json_limited(path, DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_BYTES)
        if _sha256_bytes(raw) != digest or _canonical_json(payload).encode("utf-8") != raw:
            raise DailyMarketUniverseRunError("segment_projection_hash_mismatch")
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "generation_identity_sha256", "segment_index", "segment_id",
            "declared_stock_codes", "included_stock_codes", "excluded_stock_codes",
            "parent_reference", "rows",
        } or payload.get("schema_version") != "daily-market-universe-segment-projection.v1":
            raise DailyMarketUniverseRunError("segment_projection_fields_invalid")
        if payload.get("generation_identity_sha256") != self.generation_identity_sha256:
            raise DailyMarketUniverseRunError("segment_generation_mismatch")
        expected_exclusions = [
            {"stock_code": code, "reason": reason}
            for code, reason in self.plan.excluded_stock_codes
            if code in segment.excluded_stock_codes
        ]
        if (
            payload.get("segment_index") != segment.segment_index
            or payload.get("segment_id") != segment.segment_id
        ):
            raise DailyMarketUniverseRunError("segment_membership_mismatch")
        if (
            payload.get("declared_stock_codes") != list(segment.declared_stock_codes)
            or payload.get("included_stock_codes") != list(segment.included_stock_codes)
            or payload.get("excluded_stock_codes") != expected_exclusions
        ):
            raise DailyMarketUniverseRunError("segment_exclusion_mismatch")
        rows = payload.get("rows")
        if not isinstance(rows, list) or [row.get("stock_code") for row in rows] != list(segment.included_stock_codes):
            raise DailyMarketUniverseRunError("segment_rows_invalid")
        reference = _parent_reference_from_descriptor(payload.get("parent_reference"))
        context = _load_parent_context(reference)
        _validate_parent_context_for_reader(context, self.plan, segment)
        if payload.get("parent_reference") != _parent_reference_descriptor(context):
            raise DailyMarketUniverseRunError("parent_reference_digest_mismatch")
        if _project_verified_parent(context) != rows:
            raise DailyMarketUniverseRunError("segment_projection_source_mismatch")
        expected_item = _segment_result(
            segment,
            rows,
            _parent_reference_descriptor(context),
            digest,
            context["contract"].condition_keys,
        )
        if dict(item) != expected_item:
            raise DailyMarketUniverseRunError("segment_manifest_metadata_mismatch")
        return payload

    def _verify_index_rows(self) -> None:
        count = int(self._connection.execute("SELECT COUNT(*) FROM universe_members").fetchone()[0])
        if count != len(self.plan.declared_stock_codes):
            raise DailyMarketUniverseRunError("run_index_row_count_mismatch")
        columns = (
            "stock_code,is_excluded,excluded_reason,processed,snapshot_missing,combined_state,data_date,"
            "close_value,ma20_value,ma60_value,bbands30_upper_value,state_close_above_ma20,"
            "state_close_above_ma60,state_close_above_bbands30_upper,payload_json"
        )
        for segment in self.plan.segments:
            if not segment.included_stock_codes:
                continue
            segment_item = next(
                item for item in self.manifest["segments"] if item["segment_index"] == segment.segment_index
            )
            payload = self._verify_saved_segment(segment_item, segment)
            expected_rows = [_index_values(row["stock_code"], row, None) for row in payload["rows"]]
            actual_rows = self._select_index_rows(columns, segment.included_stock_codes)
            if actual_rows != expected_rows:
                raise DailyMarketUniverseRunError("run_index_projection_mismatch")
        for start in range(0, len(self.plan.excluded_stock_codes), DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_STOCKS):
            chunk = self.plan.excluded_stock_codes[start : start + DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_STOCKS]
            expected_rows = [
                _index_values(code, None, reason)
                for code, reason in chunk
            ]
            actual_rows = self._select_index_rows(columns, tuple(code for code, _reason in chunk))
            if actual_rows != expected_rows:
                raise DailyMarketUniverseRunError("run_index_projection_mismatch")
        declared_codes = tuple(row[0] for row in self._connection.execute(
            "SELECT stock_code FROM universe_members ORDER BY stock_code"
        ))
        if declared_codes != self.plan.declared_stock_codes:
            raise DailyMarketUniverseRunError("run_index_membership_mismatch")

    def _select_index_rows(self, columns: str, codes: Sequence[str]) -> list[tuple[Any, ...]]:
        placeholders = ",".join("?" for _ in codes)
        rows = self._connection.execute(
            f"SELECT {columns} FROM universe_members WHERE stock_code IN ({placeholders}) ORDER BY stock_code",
            list(codes),
        ).fetchall()
        return [tuple(row) for row in rows]


def list_completed_runs(
    output_root: str | Path,
    *,
    limit: int = 64,
    after_generation_identity: str | None = None,
) -> DailyMarketUniverseRunListing:
    """分頁列出已發布來源 descriptor；完整 index/parent 核驗留給選取後的 reader。"""

    if type(limit) is not int or not 1 <= limit <= 256:
        raise DailyMarketUniverseRunError("listing_limit_invalid")
    cursor = None if after_generation_identity is None else _require_sha(
        after_generation_identity, "after_generation_identity"
    )
    root = Path(output_root).expanduser().resolve()
    generations = root / "generations"
    if not generations.is_dir():
        return DailyMarketUniverseRunListing((), None, False)
    names = heapq.nsmallest(
        limit + 1,
        (
            entry.name
            for entry in os.scandir(generations)
            if entry.is_dir(follow_symlinks=False)
            and _SHA256_RE.fullmatch(entry.name)
            and (cursor is None or entry.name > cursor)
        ),
    )
    has_more = len(names) > limit
    chosen = names[:limit]
    items = tuple(_listed_descriptor(generations / name, name) for name in chosen)
    next_cursor = chosen[-1] if has_more and chosen else None
    return DailyMarketUniverseRunListing(items, next_cursor, has_more)


def _listed_descriptor(path: Path, identity: str) -> DailyMarketUniverseRunDescriptor:
    try:
        manifest, receipt, manifest_sha = _read_complete_generation(path, verify_index=False)
        plan = _validate_manifest_plan(manifest)
        if manifest.get("generation_identity_sha256") != identity:
            raise DailyMarketUniverseRunError("generation_identity_mismatch")
        return _descriptor_from_complete(path, manifest, receipt, manifest_sha)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        code = getattr(exc, "code", "run_manifest_invalid")
        return DailyMarketUniverseRunDescriptor(
            generation_identity_sha256=identity,
            status="corrupt",
            output_path=path,
            error_code=str(code),
        )


def _load_parent_context(reference: DailyMarketParentCaptureReference) -> dict[str, Any]:
    ref = reference.resolved()
    snapshot_root = Path(ref.snapshot_root)
    capture_root = Path(ref.capture_root)
    universe_path = Path(ref.universe_path)
    if not _SHA256_RE.fullmatch(ref.capture_identity_sha256):
        raise DailyMarketUniverseRunError("parent_capture_identity_invalid")
    for path in (snapshot_root, capture_root, universe_path):
        _reject_symlink_chain(path)
    parent_store = BoundedRuleResearchParentWriter(capture_root / "parents")
    package = parent_store.read(ref.capture_identity_sha256)
    body = package.get("capture")
    receipt = package.get("receipt")
    if not isinstance(body, dict) or not isinstance(receipt, dict):
        raise DailyMarketUniverseRunError("parent_receipt_invalid")
    parent = RuleResearchParentCapture(_canonical_json(body))
    body = parent.to_dict()
    if receipt.get("capture_identity_sha256") != body.get("capture_identity_sha256"):
        raise DailyMarketUniverseRunError("parent_receipt_identity_mismatch")
    if body.get("status") != "complete" or body.get("source_status") != "validated_transaction":
        raise DailyMarketUniverseRunError("parent_not_complete")
    feature_version = str(body.get("feature_contract_version") or "daily-market-feature-snapshot.v2")
    contract = feature_contract_for_version(feature_version)
    if body.get("method_contracts") != contract.method_contracts or body.get("method_contracts_sha256") != contract.method_contracts_sha256:
        raise DailyMarketUniverseRunError("parent_method_contract_invalid")
    readiness = read_parent_rule_sample_readiness(
        snapshot_root,
        capture_root,
        universe_path=universe_path,
        identity_sha256=ref.capture_identity_sha256,
        contract_version=feature_version,
    )
    if readiness.get("status") != "saved_verified_complete" or readiness.get("uncaptured_member_count") != 0:
        raise DailyMarketUniverseRunError("parent_readiness_incomplete")
    source = body.get("source_binding")
    if not isinstance(source, dict) or not isinstance(source.get("database"), str):
        raise DailyMarketUniverseRunError("parent_source_binding_missing")
    source_binding_json = _canonical_json(source)
    source_sha = _sha256_bytes(source_binding_json.encode("utf-8"))
    if source_sha != body.get("source_binding_sha256"):
        raise DailyMarketUniverseRunError("parent_source_binding_digest_mismatch")
    cutoff = str(body["decision_cutoff"])
    clock = DailyMarketParentSourceClock(
        body["universe"]["value"]["as_of_date"],
        cutoff,
        source_binding_json,
        source_sha,
        feature_version,
        body["method_contracts_sha256"],
    )
    return {
        "reference": DailyMarketParentCaptureReference(
            snapshot_root, capture_root, universe_path, ref.capture_identity_sha256
        ),
        "body": body,
        "receipt": receipt,
        "readiness": readiness,
        "feature_contract_version": feature_version,
        "contract": contract,
        "source_clock": clock,
    }


def _project_verified_parent(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """只讀已釘選 artifacts，再沿既有 screener/cohort projection 產生列。"""

    from app_module.daily_market_cohort_projection import project_daily_market_cohort
    from app_module.daily_market_research_screener import DailyMarketResearchScreenerService

    body = context["body"]
    ref = context["reference"]
    source_database = body["source_binding"]["database"]
    service_config = SimpleNamespace(db_file=source_database, output_root=None)
    decision_day = date.fromisoformat(body["universe"]["value"]["as_of_date"])
    condition_keys = tuple(context["contract"].condition_keys)
    projected: dict[str, dict[str, Any]] = {}
    for batch in body["batches"]:
        if batch.get("status") != "captured":
            raise DailyMarketUniverseRunError("parent_batch_not_captured")
        batch_root = ref.snapshot_root / "batches" / body["plan_sha256"] / batch["batch_id"]
        repository = DailyMarketSnapshotRepository(batch_root)
        snapshot = repository.load_manifest(
            manifest_sha256=batch["manifest_sha256"],
            cohort_id=batch["cohort_id"],
            decision_date=decision_day,
            expected_stock_codes=batch["included_stock_codes"],
        )
        if snapshot.manifest.get("feature_contract_version") != context["feature_contract_version"]:
            raise DailyMarketUniverseRunError("child_feature_contract_mismatch")
        service = DailyMarketResearchScreenerService(
            service_config,
            snapshot_root=batch_root,
        )
        screen_rows = service.filter_rows(snapshot, condition_keys, "AND")
        projection = project_daily_market_cohort(
            snapshot,
            screen_rows,
            expected_snapshot_root=batch_root,
        )
        screen_by_code = {row.stock_code: row for row in screen_rows}
        for member in projection.members:
            screen = screen_by_code.get(member.stock_code)
            conditions = {condition.key: condition.to_dict() for condition in member.conditions}
            row = {
                "stock_code": member.stock_code,
                "data_date": member.data_date,
                "close": _decimal_text(member.close),
                "ma20": _decimal_text(member.ma20),
                "ma60": _decimal_text(member.ma60),
                "bbands30_upper": _decimal_text(member.bbands30_upper),
                "conditions": conditions,
                "combined_state": screen.combined_state if screen is not None else "unknown",
                "why": list(screen.why) if screen is not None else [],
                "why_not": list(screen.why_not) if screen is not None else [],
                "source_refs": [list(pair) for pair in member.source_refs],
                "snapshot_missing": bool(member.snapshot_missing),
                "source_snapshot_id": projection.source_snapshot_id,
                "source_snapshot_sha256": projection.source_snapshot_hash,
                "parent_capture_identity_sha256": body["capture_identity_sha256"],
            }
            if member.stock_code in projected:
                raise DailyMarketUniverseRunError("duplicate_stock_inside_parent")
            projected[member.stock_code] = row
    return [projected[code] for code in sorted(projected)]


def _segment_result(
    segment: DailyMarketUniverseSegmentPlan,
    rows: Sequence[Mapping[str, Any]],
    parent_reference: Mapping[str, Any],
    projection_sha256: str,
    condition_keys: Sequence[str],
) -> dict[str, Any]:
    snapshot_missing = sorted(
        str(row["stock_code"]) for row in rows if row.get("snapshot_missing") is True
    )
    unknown_evidence = _unknown_evidence_codes(rows, condition_keys)
    return {
        "segment_index": segment.segment_index,
        "segment_id": segment.segment_id,
        "status": "processed",
        "included_count": len(segment.included_stock_codes),
        "excluded_count": len(segment.excluded_stock_codes),
        "projection_relpath": f"segments/{segment.segment_id}-{projection_sha256}.json",
        "projection_sha256": projection_sha256,
        "row_count": len(rows),
        "parent_reference": dict(parent_reference),
        "snapshot_missing_stock_codes": snapshot_missing,
        "unknown_evidence_stock_codes": unknown_evidence,
        "missing_data_stock_codes": sorted(set(snapshot_missing) | set(unknown_evidence)),
        "condition_unknown_counts": _condition_unknown_counts(rows, condition_keys),
    }


def _validate_parent_context_for_reader(
    context: Mapping[str, Any],
    plan: DailyMarketUniverseRunPlan,
    segment: DailyMarketUniverseSegmentPlan,
) -> None:
    body = context["body"]
    universe = body["universe"]["value"]
    if plan.source_clock is None:
        raise DailyMarketUniverseRunError("parent_reference_source_clock_missing")
    if (
        universe["universe_id"] != plan.universe_id
        or universe["version"] != plan.population_version
        or universe["as_of_date"] != plan.decision_date.isoformat()
        or body["decision_cutoff"] != plan.decision_cutoff
        or tuple(universe["included_stock_codes"]) != segment.included_stock_codes
        or universe["excluded_stock_codes"]
        or context["source_clock"].to_dict() != plan.source_clock.to_dict()
        or context["readiness"].get("status") != "saved_verified_complete"
    ):
        raise DailyMarketUniverseRunError("parent_reference_contract_mismatch")
    if len(body["batches"]) > 16 or any(
        len(batch["included_stock_codes"]) > DAILY_MARKET_UNIVERSE_RUN_MAX_BATCH_STOCKS
        for batch in body["batches"]
    ):
        raise DailyMarketUniverseRunError("parent_or_child_batch_bound")
    if tuple(sorted(code for batch in body["batches"] for code in batch["included_stock_codes"])) != segment.included_stock_codes:
        raise DailyMarketUniverseRunError("parent_child_membership_mismatch")


def _parent_reference_descriptor(context: Mapping[str, Any]) -> dict[str, Any]:
    ref = context["reference"]
    return {
        "snapshot_root": str(ref.snapshot_root),
        "capture_root": str(ref.capture_root),
        "universe_path": str(ref.universe_path),
        "capture_identity_sha256": context["body"]["capture_identity_sha256"],
        "capture_sha256": context["receipt"]["capture_sha256"],
        "source_clock_sha256": context["source_clock"].identity_sha256,
    }


def _parent_reference_from_descriptor(value: Any) -> DailyMarketParentCaptureReference:
    if not isinstance(value, Mapping) or set(value) != {
        "snapshot_root", "capture_root", "universe_path", "capture_identity_sha256", "capture_sha256", "source_clock_sha256"
    }:
        raise DailyMarketUniverseRunError("parent_reference_invalid")
    return DailyMarketParentCaptureReference(
        value["snapshot_root"], value["capture_root"], value["universe_path"], value["capture_identity_sha256"]
    )


def _partition_population(
    declared: tuple[str, ...],
    included: tuple[str, ...],
    exclusions: tuple[tuple[str, str], ...],
) -> tuple[DailyMarketUniverseSegmentPlan, ...]:
    included_set = set(included)
    excluded_set = {code for code, _reason in exclusions}
    segments: list[DailyMarketUniverseSegmentPlan] = []
    for index, start in enumerate(range(0, len(declared), DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_STOCKS)):
        members = declared[start : start + DAILY_MARKET_UNIVERSE_RUN_MAX_SEGMENT_STOCKS]
        segment_included = tuple(code for code in members if code in included_set)
        segment_excluded = tuple(code for code in members if code in excluded_set)
        if len(segment_included) > 16 * DAILY_MARKET_UNIVERSE_RUN_MAX_BATCH_STOCKS:
            raise DailyMarketUniverseRunError("parent_segment_member_bound")
        segments.append(DailyMarketUniverseSegmentPlan(index, members, segment_included, segment_excluded))
    return tuple(segments)


def _normalize_exclusions(
    values: Mapping[str, str] | Sequence[tuple[str, str]],
    declared: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    if isinstance(values, Mapping):
        pairs = list(values.items())
    elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        pairs = list(values)
    else:
        raise TypeError("excluded_stock_codes 必須是代碼到理由的 mapping 或 pair 序列")
    normalized: dict[str, str] = {}
    for item in pairs:
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes)) or len(item) != 2:
            raise DailyMarketUniverseRunError("exclusion_entry_invalid")
        code = _normalize_stock_code(item[0])
        reason = _required_text(item[1], "exclusion_reason", 512)
        if code in normalized:
            raise DailyMarketUniverseRunError("duplicate_exclusion")
        normalized[code] = reason
    unknown = set(normalized) - set(declared)
    if unknown:
        raise DailyMarketUniverseRunError("excluded_stock_outside_population")
    return tuple(sorted(normalized.items()))


def _normalize_stock_code(value: Any) -> str:
    if not isinstance(value, str):
        raise DailyMarketUniverseRunError("stock_code_invalid")
    code = value.strip().upper()
    if not _STOCK_CODE_RE.fullmatch(code):
        raise DailyMarketUniverseRunError("stock_code_invalid")
    return code


def _normalize_cutoff(value: datetime, day: date) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMarketUniverseRunError("decision_cutoff_timezone_missing")
    local = value.astimezone(ZoneInfo("Asia/Taipei"))
    if local.date() != day:
        raise DailyMarketUniverseRunError("decision_cutoff_date_mismatch")
    return local.isoformat()


def _validate_source_clock(clock: DailyMarketParentSourceClock) -> None:
    if not isinstance(clock, DailyMarketParentSourceClock):
        raise TypeError("source_clock 必須由 parent_source_clock_from_reference 取得")
    try:
        day = date.fromisoformat(clock.decision_date)
        cutoff = datetime.fromisoformat(clock.decision_cutoff)
    except (TypeError, ValueError) as exc:
        raise DailyMarketUniverseRunError("source_clock_invalid") from exc
    if day.isoformat() != clock.decision_date or _normalize_cutoff(cutoff, day) != clock.decision_cutoff:
        raise DailyMarketUniverseRunError("source_clock_invalid")
    source = clock.source_binding
    if set(source) != {"mode", "database", "schema_identity_sha256", "revision_pin"}:
        raise DailyMarketUniverseRunError("source_clock_binding_invalid")
    if source.get("mode") != "query_only_transaction_main_wal_stat_pin":
        raise DailyMarketUniverseRunError("source_clock_mode_invalid")
    encoded = _canonical_json(source).encode("utf-8")
    if _sha256_bytes(encoded) != clock.source_binding_sha256:
        raise DailyMarketUniverseRunError("source_clock_digest_mismatch")
    if not isinstance(source.get("database"), str) or not Path(source["database"]).is_absolute():
        raise DailyMarketUniverseRunError("source_clock_database_invalid")
    _require_sha(source.get("schema_identity_sha256"), "schema_identity_sha256")
    pins = source.get("revision_pin")
    if (
        not isinstance(pins, list)
        or len(pins) != 2
        or any(not isinstance(pin, list) or len(pin) not in {1, 5} for pin in pins)
        or pins[0][0] != source["database"]
        or pins[1][0] != source["database"] + "-wal"
        or len(pins[0]) != 5
        or any(type(value) is not int or value < 0 for pin in pins for value in pin[1:])
    ):
        raise DailyMarketUniverseRunError("source_clock_revision_pin_invalid")
    _require_sha(clock.method_contracts_sha256, "method_contracts_sha256")
    contract = feature_contract_for_version(clock.feature_contract_version)
    if contract.method_contracts_sha256 != clock.method_contracts_sha256:
        raise DailyMarketUniverseRunError("source_clock_method_contract_mismatch")


def _validate_plan_object(plan: DailyMarketUniverseRunPlan) -> None:
    if not isinstance(plan, DailyMarketUniverseRunPlan):
        raise TypeError("plan 必須由 plan_daily_market_universe_run 建立")
    body = plan.to_dict()
    _validate_plan_payload(body)


def _validate_plan_payload(value: Any) -> DailyMarketUniverseRunPlan:
    if not isinstance(value, Mapping) or value.get("schema_version") != DAILY_MARKET_UNIVERSE_RUN_PLAN_SCHEMA:
        raise DailyMarketUniverseRunError("run_plan_schema_invalid")
    required = {
        "schema_version", "universe_id", "population_version", "decision_date", "decision_cutoff",
        "strategy_version", "source_clock", "raw_stock_code_count", "declared_stock_codes",
        "duplicate_stock_codes", "excluded_stock_codes", "included_stock_codes", "segments",
        "generation_identity_sha256",
    }
    if set(value) != required:
        raise DailyMarketUniverseRunError("run_plan_fields_invalid")
    declared_raw = value["declared_stock_codes"]
    if not isinstance(declared_raw, list) or not declared_raw:
        raise DailyMarketUniverseRunError("run_plan_population_invalid")
    declared = tuple(_normalize_stock_code(code) for code in declared_raw)
    if list(declared) != sorted(set(declared)):
        raise DailyMarketUniverseRunError("run_plan_population_not_canonical")
    if type(value["raw_stock_code_count"]) is not int or value["raw_stock_code_count"] < len(declared):
        raise DailyMarketUniverseRunError("run_plan_raw_count_invalid")
    duplicates_raw = value["duplicate_stock_codes"]
    if not isinstance(duplicates_raw, list):
        raise DailyMarketUniverseRunError("run_plan_duplicates_invalid")
    duplicates: list[tuple[str, int]] = []
    for item in duplicates_raw:
        if not isinstance(item, Mapping) or set(item) != {"stock_code", "occurrences"}:
            raise DailyMarketUniverseRunError("run_plan_duplicates_invalid")
        code = _normalize_stock_code(item["stock_code"])
        count = item["occurrences"]
        if type(count) is not int or count < 2 or code not in declared:
            raise DailyMarketUniverseRunError("run_plan_duplicates_invalid")
        duplicates.append((code, count))
    if duplicates != sorted(duplicates) or value["raw_stock_code_count"] != len(declared) + sum(n - 1 for _code, n in duplicates):
        raise DailyMarketUniverseRunError("run_plan_duplicate_counts_mismatch")
    exclusions_raw = value["excluded_stock_codes"]
    if not isinstance(exclusions_raw, list):
        raise DailyMarketUniverseRunError("run_plan_exclusions_invalid")
    exclusions: list[tuple[str, str]] = []
    for item in exclusions_raw:
        if not isinstance(item, Mapping) or set(item) != {"stock_code", "reason"}:
            raise DailyMarketUniverseRunError("run_plan_exclusions_invalid")
        exclusions.append((_normalize_stock_code(item["stock_code"]), _required_text(item["reason"], "reason", 512)))
    if exclusions != sorted(exclusions) or len({code for code, _reason in exclusions}) != len(exclusions):
        raise DailyMarketUniverseRunError("run_plan_exclusions_not_canonical")
    if not {code for code, _reason in exclusions} <= set(declared):
        raise DailyMarketUniverseRunError("run_plan_exclusion_outside_population")
    included = tuple(code for code in declared if code not in {x[0] for x in exclusions})
    if value["included_stock_codes"] != list(included):
        raise DailyMarketUniverseRunError("run_plan_included_mismatch")
    try:
        decision_day = date.fromisoformat(value["decision_date"])
    except (TypeError, ValueError) as exc:
        raise DailyMarketUniverseRunError("run_plan_date_invalid") from exc
    if decision_day.isoformat() != value["decision_date"]:
        raise DailyMarketUniverseRunError("run_plan_date_invalid")
    cutoff = datetime.fromisoformat(value["decision_cutoff"])
    if _normalize_cutoff(cutoff, decision_day) != value["decision_cutoff"]:
        raise DailyMarketUniverseRunError("run_plan_cutoff_invalid")
    source_clock = _source_clock_from_dict(value["source_clock"])
    if included and source_clock is None:
        raise DailyMarketUniverseRunError("run_plan_source_clock_missing")
    if source_clock is not None:
        _validate_source_clock(source_clock)
        if source_clock.decision_date != decision_day.isoformat() or source_clock.decision_cutoff != value["decision_cutoff"]:
            raise DailyMarketUniverseRunError("run_plan_source_clock_mismatch")
    expected_segments = _partition_population(declared, included, tuple(exclusions))
    if value["segments"] != [segment.to_dict() for segment in expected_segments]:
        raise DailyMarketUniverseRunError("run_plan_segments_mismatch")
    if _generation_identity(value) != value["generation_identity_sha256"]:
        raise DailyMarketUniverseRunError("run_generation_identity_mismatch")
    return DailyMarketUniverseRunPlan(
        _required_text(value["universe_id"], "universe_id", 96),
        _required_text(value["population_version"], "population_version", 128),
        decision_day,
        value["decision_cutoff"],
        _required_text(value["strategy_version"], "strategy_version", 128),
        source_clock,
        value["raw_stock_code_count"],
        declared,
        tuple(duplicates),
        tuple(exclusions),
        included,
        expected_segments,
        value["generation_identity_sha256"],
    )


def _source_clock_from_dict(value: Any) -> DailyMarketParentSourceClock | None:
    if value is None:
        return None
    required = {
        "decision_date", "decision_cutoff", "source_binding", "source_binding_sha256",
        "feature_contract_version", "method_contracts_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise DailyMarketUniverseRunError("source_clock_fields_invalid")
    clock = DailyMarketParentSourceClock(
        value["decision_date"],
        value["decision_cutoff"],
        _canonical_json(value["source_binding"]),
        value["source_binding_sha256"],
        value["feature_contract_version"],
        value["method_contracts_sha256"],
    )
    if clock.to_dict() != dict(value):
        raise DailyMarketUniverseRunError("source_clock_noncanonical")
    return clock


def _validate_manifest_plan(manifest: Mapping[str, Any]) -> DailyMarketUniverseRunPlan:
    if manifest.get("schema_version") != DAILY_MARKET_UNIVERSE_RUN_SCHEMA:
        raise DailyMarketUniverseRunError("run_manifest_schema_mismatch")
    identity = _require_sha(manifest.get("manifest_identity_sha256"), "manifest_identity_sha256")
    if _manifest_identity(dict(manifest)) != identity:
        raise DailyMarketUniverseRunError("run_manifest_identity_mismatch")
    plan = _validate_plan_payload(manifest.get("plan"))
    if manifest.get("generation_identity_sha256") != plan.generation_identity_sha256:
        raise DailyMarketUniverseRunError("run_generation_identity_mismatch")
    if manifest.get("source_clock") != (plan.source_clock.to_dict() if plan.source_clock else None):
        raise DailyMarketUniverseRunError("run_source_clock_mismatch")
    expected_clock_sha = plan.source_clock.identity_sha256 if plan.source_clock else None
    if manifest.get("source_clock_sha256") != expected_clock_sha:
        raise DailyMarketUniverseRunError("run_source_clock_digest_mismatch")
    if manifest.get("strategy_version") != plan.strategy_version:
        raise DailyMarketUniverseRunError("run_strategy_version_mismatch")
    expected_feature = plan.source_clock.feature_contract_version if plan.source_clock else None
    expected_method_sha = plan.source_clock.method_contracts_sha256 if plan.source_clock else None
    if manifest.get("feature_contract_version") != expected_feature or manifest.get("method_contracts_sha256") != expected_method_sha:
        raise DailyMarketUniverseRunError("run_feature_contract_mismatch")
    return plan


def _manifest_identity(manifest: Mapping[str, Any]) -> str:
    stable = {key: value for key, value in manifest.items() if key not in {"manifest_identity_sha256", "published_at"}}
    return _sha256_bytes(_canonical_json(stable).encode("utf-8"))


def _generation_identity(plan: Mapping[str, Any]) -> str:
    stable = {key: value for key, value in plan.items() if key != "generation_identity_sha256"}
    return _sha256_bytes(_canonical_json(stable).encode("utf-8"))


def _read_complete_generation(
    root: Path,
    *,
    verify_index: bool,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    _reject_symlink_chain(root)
    receipt_path = root / "complete.json"
    _raw_receipt, receipt = _read_json_limited(receipt_path, 4 * 1024)
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema_version", "generation_identity_sha256", "manifest_sha256", "index_sha256"
    }:
        raise DailyMarketUniverseRunError("run_receipt_fields_invalid")
    if receipt.get("schema_version") != DAILY_MARKET_UNIVERSE_RUN_RECEIPT_SCHEMA:
        raise DailyMarketUniverseRunError("run_receipt_schema_mismatch")
    if receipt.get("generation_identity_sha256") != root.name:
        raise DailyMarketUniverseRunError("run_receipt_generation_mismatch")
    manifest_raw, manifest = _read_json_limited(root / "manifest.json", DAILY_MARKET_UNIVERSE_RUN_MAX_MANIFEST_BYTES)
    if not isinstance(manifest, dict):
        raise DailyMarketUniverseRunError("run_manifest_invalid")
    manifest_sha = _sha256_bytes(manifest_raw)
    if manifest_sha != receipt.get("manifest_sha256"):
        raise DailyMarketUniverseRunError("run_manifest_hash_mismatch")
    if _canonical_json(manifest).encode("utf-8") != manifest_raw:
        raise DailyMarketUniverseRunError("run_manifest_noncanonical")
    plan = _validate_manifest_plan(manifest)
    if plan.generation_identity_sha256 != root.name:
        raise DailyMarketUniverseRunError("run_directory_identity_mismatch")
    index = manifest.get("index")
    if not isinstance(index, Mapping) or set(index) != {"relpath", "sha256", "size_bytes"}:
        raise DailyMarketUniverseRunError("run_index_reference_invalid")
    if index.get("relpath") != "index.sqlite" or receipt.get("index_sha256") != index.get("sha256"):
        raise DailyMarketUniverseRunError("run_index_reference_mismatch")
    _require_sha(index.get("sha256"), "index_sha256")
    if type(index.get("size_bytes")) is not int or not 0 <= index["size_bytes"] <= DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES:
        raise DailyMarketUniverseRunError("run_index_reference_invalid")
    index_path = root / "index.sqlite"
    if verify_index:
        digest, size = _hash_file(index_path, DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES)
        if digest != index["sha256"] or size != index["size_bytes"]:
            raise DailyMarketUniverseRunError("run_index_hash_mismatch")
    else:
        try:
            stat = index_path.stat()
        except OSError as exc:
            raise DailyMarketUniverseRunError("run_index_missing") from exc
        if stat.st_nlink != 1 or stat.st_size != index["size_bytes"] or stat.st_size > DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES:
            raise DailyMarketUniverseRunError("run_index_budget_or_link")
    return manifest, receipt, manifest_sha


def _descriptor_from_complete(
    path: Path,
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manifest_sha: str | None = None,
) -> DailyMarketUniverseRunDescriptor:
    plan = _validate_manifest_plan(manifest)
    clock = plan.source_clock
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise DailyMarketUniverseRunError("run_counts_invalid")
    return DailyMarketUniverseRunDescriptor(
        generation_identity_sha256=plan.generation_identity_sha256,
        status="complete",
        output_path=path,
        manifest_sha256=manifest_sha or str(receipt.get("manifest_sha256")),
        universe_id=plan.universe_id,
        population_version=plan.population_version,
        strategy_version=plan.strategy_version,
        feature_contract_version=clock.feature_contract_version if clock else "",
        decision_date=plan.decision_date.isoformat(),
        decision_cutoff=plan.decision_cutoff,
        source_clock=clock.to_dict() if clock else None,
        saved_at=str(manifest.get("published_at") or ""),
        counts={str(key): int(value) for key, value in counts.items()},
        data_completeness=str(manifest.get("data_completeness") or "unknown"),
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    _reject_symlink_chain(path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise DailyMarketUniverseRunError("run_index_missing") from exc
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > DAILY_MARKET_UNIVERSE_RUN_MAX_INDEX_BYTES:
        raise DailyMarketUniverseRunError("run_index_budget_or_link")
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _decimal_collation(left: str, right: str) -> int:
    try:
        a, b = Decimal(left), Decimal(right)
        if not a.is_finite() or not b.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return (left > right) - (left < right)
    return (a > b) - (a < b)


def _condition_unknown_counts(
    rows: Sequence[Mapping[str, Any]], condition_keys: Sequence[str]
) -> dict[str, int]:
    keys = tuple(condition_keys)
    counts = {key: 0 for key in keys}
    for row in rows:
        conditions = row.get("conditions", {})
        for key in keys:
            condition = conditions.get(key) if isinstance(conditions, Mapping) else None
            if not isinstance(condition, Mapping) or condition.get("state") == "unknown":
                counts[key] += 1
    return counts


def _unknown_evidence_codes(
    rows: Sequence[Mapping[str, Any]], condition_keys: Sequence[str]
) -> list[str]:
    result: list[str] = []
    for row in rows:
        conditions = row.get("conditions", {})
        if any(
            not isinstance(conditions, Mapping)
            or not isinstance(conditions.get(key), Mapping)
            or conditions[key].get("state") == "unknown"
            for key in condition_keys
        ):
            result.append(str(row["stock_code"]))
    return sorted(set(result))


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DailyMarketUniverseRunError("projection_decimal_invalid")
    return str(value)


def _required_text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > limit:
        raise DailyMarketUniverseRunError(f"{name}_invalid")
    return value


def _require_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DailyMarketUniverseRunError(f"{name}_invalid")
    return value


def _required_relpath(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or "\x00" in value
    ):
        raise DailyMarketUniverseRunError(f"{name}_invalid")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or posix_path.as_posix() != value
        or any(part in {"..", "."} for part in posix_path.parts)
    ):
        raise DailyMarketUniverseRunError(f"{name}_invalid")
    return value


def _resolve_generation_child(root: Path, value: Any, name: str) -> Path:
    """拒絕平台路徑語法、symlink 與解析後離開 generation 的參照。"""

    relpath = _required_relpath(value, name)
    resolved_root = root.resolve()
    candidate = resolved_root / relpath
    _reject_symlink_chain(candidate)
    resolved_candidate = candidate.resolve()
    if resolved_candidate == resolved_root or not resolved_candidate.is_relative_to(resolved_root):
        raise DailyMarketUniverseRunError(f"{name}_outside_generation")
    return resolved_candidate


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DailyMarketUniverseRunError("json_value_invalid") from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json_limited(path: Path, limit: int) -> tuple[bytes, Any]:
    _reject_symlink_chain(path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise DailyMarketUniverseRunError("run_file_missing") from exc
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > limit:
        raise DailyMarketUniverseRunError("run_file_budget_or_link")
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise DailyMarketUniverseRunError("run_file_budget_or_link")
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except DailyMarketUniverseRunError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise DailyMarketUniverseRunError("run_json_invalid") from exc
    return raw, body


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _hash_file(path: Path, limit: int) -> tuple[str, int]:
    _reject_symlink_chain(path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise DailyMarketUniverseRunError("run_file_missing") from exc
    if not path.is_file() or stat.st_nlink != 1 or stat.st_size > limit:
        raise DailyMarketUniverseRunError("run_file_budget_or_link")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > limit:
                raise DailyMarketUniverseRunError("run_file_budget_or_link")
            digest.update(block)
    return digest.hexdigest(), size


def _verify_file_digest(path: Path, expected_sha: str, limit: int) -> None:
    digest, _size = _hash_file(path, limit)
    if digest != expected_sha:
        raise DailyMarketUniverseRunError("run_file_hash_mismatch")


def _atomic_write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise DailyMarketUniverseRunError("immutable_run_file_exists")
    _atomic_write(path, raw, replace=False)


def _atomic_write_replace(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, raw, replace=True)


def _atomic_write(path: Path, raw: bytes, *, replace: bool) -> None:
    _reject_symlink_chain(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and (path.exists() or path.is_symlink()):
            raise DailyMarketUniverseRunError("immutable_run_file_exists")
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _resolve_output_root(value: str | Path) -> Path:
    if value is None:
        raise DailyMarketUniverseRunError("output_root_required")
    raw = Path(value).expanduser().absolute()
    _reject_symlink_chain(raw)
    return raw.resolve()


def _index_values(
    stock_code: str,
    row: Mapping[str, Any] | None,
    excluded_reason: str | None,
) -> tuple[Any, ...]:
    if excluded_reason is not None:
        payload: dict[str, Any] = {
            "stock_code": stock_code,
            "included": False,
            "excluded_reason": excluded_reason,
            "processed": False,
            "snapshot_missing": False,
            "data_date": None,
            "close": None,
            "ma20": None,
            "ma60": None,
            "bbands30_upper": None,
            "combined_state": "excluded",
            "conditions": {},
            "why": [],
            "why_not": [excluded_reason],
            "source_refs": [],
        }
        return (
            stock_code, 1, excluded_reason, 0, 0, "excluded", None, None, None, None, None,
            "unknown", "unknown", "unknown", _canonical_json(payload),
        )
    if row is None:
        raise DailyMarketUniverseRunError("processed_population_mismatch")
    payload = {**row, "included": True, "excluded_reason": None, "processed": True}
    conditions = payload.get("conditions", {})
    state_values = {
        "close_above_ma20": "unknown",
        "close_above_ma60": "unknown",
        "close_above_bbands30_upper": "unknown",
    }
    if isinstance(conditions, Mapping):
        for key in state_values:
            condition = conditions.get(key)
            if isinstance(condition, Mapping) and condition.get("state") in _STATES:
                state_values[key] = str(condition["state"])
    return (
        stock_code, 0, None, 1, int(bool(row["snapshot_missing"])), row.get("combined_state"),
        row.get("data_date"), row.get("close"), row.get("ma20"), row.get("ma60"),
        row.get("bbands30_upper"), state_values["close_above_ma20"],
        state_values["close_above_ma60"], state_values["close_above_bbands30_upper"],
        _canonical_json(payload),
    )


def _normalize_query_condition_keys(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DailyMarketUniverseRunError("query_condition_invalid")
    keys = tuple(values)
    if (
        not keys
        or len(keys) > len(_CONDITION_COLUMNS)
        or any(not isinstance(key, str) or key not in _CONDITION_COLUMNS for key in keys)
        or len(set(keys)) != len(keys)
    ):
        raise DailyMarketUniverseRunError("query_condition_invalid")
    return keys


def _normalize_query_combine_mode(value: str) -> str:
    if not isinstance(value, str):
        raise DailyMarketUniverseRunError("query_combine_mode_invalid")
    mode = value.strip().upper()
    if mode not in {"AND", "OR"}:
        raise DailyMarketUniverseRunError("query_combine_mode_invalid")
    return mode


def _combined_condition_state_sql(
    condition_keys: Sequence[str],
    combine_mode: str,
    feature_condition_keys: frozenset[str],
) -> str:
    """建立固定白名單欄位的三值組合式，供全域篩選先於分頁執行。"""

    states = [
        f"COALESCE({_CONDITION_COLUMNS[key]}, 'unknown')"
        if key in feature_condition_keys
        else "'unknown'"
        for key in condition_keys
    ]
    if combine_mode == "AND":
        no_match = " OR ".join(f"({state}) = 'no_match'" for state in states)
        match = " AND ".join(f"({state}) = 'match'" for state in states)
        return f"CASE WHEN ({no_match}) THEN 'no_match' WHEN ({match}) THEN 'match' ELSE 'unknown' END"
    match = " OR ".join(f"({state}) = 'match'" for state in states)
    no_match = " AND ".join(f"({state}) = 'no_match'" for state in states)
    return f"CASE WHEN ({match}) THEN 'match' WHEN ({no_match}) THEN 'no_match' ELSE 'unknown' END"


def _verify_staging_index(path: Path, expected_rows: Sequence[tuple[Any, ...]]) -> None:
    """取消後重試只沿用列內容相同的 staging index，不覆寫既有檔。"""

    connection = _connect_readonly(path)
    try:
        connection.create_collation("DECIMAL", _decimal_collation)
        check = connection.execute("PRAGMA quick_check").fetchone()
        if check is None or check[0] != "ok":
            raise DailyMarketUniverseRunError("staging_index_corrupt")
        actual_rows = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM universe_members ORDER BY stock_code"
            ).fetchall()
        ]
        if actual_rows != list(expected_rows):
            raise DailyMarketUniverseRunError("staging_index_conflict")
    finally:
        connection.close()


def _reject_symlink_chain(path: Path) -> None:
    absolute = path.expanduser().absolute()
    for item in (absolute, *absolute.parents):
        if item.is_symlink():
            raise DailyMarketUniverseRunError("run_symlink_refused")


def _require_disjoint_paths(left: Path, right: Path, code: str) -> None:
    a = left.expanduser().resolve()
    b = right.expanduser().resolve()
    if a == b or a.is_relative_to(b) or b.is_relative_to(a):
        raise DailyMarketUniverseRunError(code)
