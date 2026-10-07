"""將完整固定母體分段送入既有 parent producer 並發布 research-only run。

此協調器只呼叫既有 query-only SQLite source、parent producer 與 verified-run
writer；不讀正式資料根目錄、不計算新的金融數值，也不改變 parent 的16批×16檔上限。

Look-ahead 自查：cutoff、source main/WAL revision pin、schema identity、feature/method
contract 在首次讀取時固定；每段 parent 與發布前再核對同一 source clock。父層 child
只由既有 cutoff-bounded producer 產生，這裡不以 cutoff 之後資料補值。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Protocol, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from app_module.daily_market_feature_snapshot import feature_contract_for_version
from app_module.daily_market_snapshot_repository import current_method_contract_binding
from app_module.daily_market_snapshot_source import (
    SQLiteDailyMarketSnapshotSource,
    _source_pin,
)
from app_module.daily_market_universe_run import (
    DailyMarketParentCaptureReference,
    DailyMarketParentSourceClock,
    DailyMarketUniverseRunDescriptor,
    DailyMarketUniverseRunError,
    DailyMarketUniverseRunReader,
    DailyMarketUniverseRunWriter,
    create_daily_market_universe_run_writer,
    parent_source_clock_from_reference,
    plan_daily_market_universe_run,
    verify_parent_capture_reference,
)
from app_module.rule_research_parent_capture import (
    PARENT_UNIVERSE_SCHEMA,
    BoundedRuleResearchParentWriter,
    _source_binding,
    load_parent_universe,
    produce_parent_rule_samples,
)
from app_module.rule_research_sample_capture import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURES,
    BoundedRuleResearchCaptureWriter,
    ResearchCaptureWriteScope,
    _safe_path,
)


DAILY_MARKET_UNIVERSE_PRODUCER_PLAN_SCHEMA = "daily-market-universe-producer-plan.v1"
DAILY_MARKET_UNIVERSE_PRODUCER_PROGRESS_SCHEMA = "daily-market-universe-producer-progress.v1"
DAILY_MARKET_UNIVERSE_PRODUCER_STRATEGY_VERSION = "daily-market-universe-producer.v1"
DAILY_MARKET_UNIVERSE_PRODUCER_MAX_INPUT_CODES = 100_000
DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PLAN_BYTES = 32 * 1024 * 1024
DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PROGRESS_BYTES = 16 * 1024 * 1024
DAILY_MARKET_UNIVERSE_PRODUCER_MAX_CAPTURE_ENTRIES = MAX_CAPTURES
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_UNIVERSE_ID = 96
_MAX_POPULATION_VERSION = 128
_MAX_REASON_CHARS = 512


class DailyMarketUniverseProductionError(ValueError):
    """producer 對外使用穩定錯誤碼；底層錯誤碼另存於 cause_code。"""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        cause_code: str = "",
    ) -> None:
        self.code = code
        self.cause_code = cause_code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseProductionRequest:
    """一次固定母體與 source clock 的 producer 請求。"""

    db_path: Path | str
    universe_id: str
    population_version: str
    raw_stock_codes: Sequence[str]
    excluded_stock_codes: Mapping[str, str] | Sequence[tuple[str, str]]
    decision_date: date
    decision_cutoff: datetime
    contract_version: str
    output_root: Path | str
    cancel_callback: Callable[[], bool] | None = None
    strategy_version: str = DAILY_MARKET_UNIVERSE_PRODUCER_STRATEGY_VERSION
    research_scope: ResearchCaptureWriteScope | None = None


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseProductionPreflight:
    """唯讀 source 與隔離路徑預檢結果；不建立輸出檔案。"""

    db_path: Path
    output_root: Path
    job_root: Path
    input_identity_sha256: str
    plan: Any
    source_binding: Mapping[str, Any]
    source_clock: DailyMarketParentSourceClock
    contract_version: str


@dataclass(frozen=True, slots=True)
class DailyMarketUniverseProductionResult:
    status: str
    step: str
    processed_segments: int
    total_segments: int
    counts: Mapping[str, int]
    error_code: str
    cause_code: str
    generation_identity_sha256: str | None
    manifest_path: Path | None
    job_root: Path | None
    parent_references: tuple[DailyMarketParentCaptureReference, ...]


class _PosixFileLockAPI(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


class _JobLock:
    """跨 process advisory lock；程序退出時由 OS 釋放，支援 crash resume。"""

    def __init__(self, job_root: Path) -> None:
        self.path = job_root / ".producer.lock"
        self._handle: Any = None

    def __enter__(self) -> _JobLock:
        _safe_path(self.path)
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                lock_api = cast(_PosixFileLockAPI, fcntl)
                lock_api.flock(
                    handle.fileno(), lock_api.LOCK_EX | lock_api.LOCK_NB
                )
        except OSError as exc:
            handle.close()
            raise DailyMarketUniverseProductionError("producer_job_busy") from exc
        self._handle = handle
        return self

    def __exit__(self, *_args: object) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                lock_api = cast(_PosixFileLockAPI, fcntl)
                lock_api.flock(handle.fileno(), lock_api.LOCK_UN)
        finally:
            handle.close()


def preflight_daily_market_universe_run(
    request: DailyMarketUniverseProductionRequest,
) -> DailyMarketUniverseProductionPreflight:
    """唯讀驗 source pin、contract、母體和現行隔離輸出政策。"""

    _validate_request_shape(request)
    db_path = _resolve_input_path(request.db_path, "source_path_invalid")
    output_root = _resolve_input_path(request.output_root, "output_root_invalid")
    _check_root_preflight(db_path, output_root, input_identity="0" * 64,
                          research_scope=request.research_scope)
    cutoff = _normalized_cutoff(request.decision_cutoff, request.decision_date)
    contract = feature_contract_for_version(request.contract_version)
    method_payload, method_sha = current_method_contract_binding(
        contract_version=contract.version
    )
    if method_payload != contract.method_contracts or method_sha != contract.method_contracts_sha256:
        raise DailyMarketUniverseProductionError("method_contract_binding_mismatch")
    try:
        with SQLiteDailyMarketSnapshotSource(db_path, request.decision_date) as source:
            source_binding = _source_binding(source)
            source.validate_source_stable()
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "source_preflight_failed", cause_code=_exception_code(exc)
        ) from exc
    encoded_binding = _canonical_json(source_binding)
    source_clock = DailyMarketParentSourceClock(
        decision_date=request.decision_date.isoformat(),
        decision_cutoff=cutoff,
        source_binding_json=encoded_binding,
        source_binding_sha256=_sha256_bytes(encoded_binding.encode("utf-8")),
        feature_contract_version=contract.version,
        method_contracts_sha256=method_sha,
    )
    try:
        plan = plan_daily_market_universe_run(
            universe_id=request.universe_id,
            population_version=request.population_version,
            raw_stock_codes=request.raw_stock_codes,
            excluded_stock_codes=request.excluded_stock_codes,
            decision_date=request.decision_date,
            decision_cutoff=request.decision_cutoff,
            strategy_version=request.strategy_version,
            source_clock=source_clock,
        )
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            _exception_code(exc) or "population_plan_invalid"
        ) from exc
    frozen_identity = {
        "schema_version": DAILY_MARKET_UNIVERSE_PRODUCER_PLAN_SCHEMA,
        "db_path": str(db_path),
        "output_root": str(output_root),
        "contract_version": contract.version,
        "method_contracts_sha256": method_sha,
        "source_clock": source_clock.to_dict(),
        "plan": plan.to_dict(),
    }
    frozen_bytes = _canonical_json(frozen_identity).encode("utf-8")
    if len(frozen_bytes) > DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PLAN_BYTES:
        raise DailyMarketUniverseProductionError("producer_plan_byte_limit")
    input_identity = _sha256_bytes(frozen_bytes)
    job_root = output_root.parent / "universe_jobs" / _job_directory_key(input_identity)
    _check_root_preflight(db_path, output_root, input_identity=input_identity,
                          research_scope=request.research_scope)
    if _paths_overlap(job_root, db_path):
        raise DailyMarketUniverseProductionError("source_output_overlap")
    return DailyMarketUniverseProductionPreflight(
        db_path=db_path,
        output_root=output_root,
        job_root=job_root,
        input_identity_sha256=input_identity,
        plan=plan,
        source_binding=source_binding,
        source_clock=source_clock,
        contract_version=contract.version,
    )


def produce_daily_market_universe_run(
    request: DailyMarketUniverseProductionRequest,
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> DailyMarketUniverseProductionResult:
    """建立或續跑同一 frozen job；只有所有 included segments verified 後發布。"""

    try:
        preflight = preflight_daily_market_universe_run(request)
    except DailyMarketUniverseProductionError as exc:
        step = "root_preflight" if exc.code == "root_preflight_failed" else "preflight"
        return _failed_result(
            request,
            step=step,
            error_code=exc.code,
            cause_code=exc.cause_code,
        )
    except Exception as exc:
        return _failed_result(
            request,
            step="preflight",
            error_code="preflight_failed",
            cause_code=_exception_code(exc),
        )

    plan = preflight.plan
    generation_id = plan.generation_identity_sha256
    total_segments = len(plan.segments)
    existing = _read_published_run(preflight)
    if existing is not None:
        return existing
    try:
        _safe_path(preflight.job_root)
        preflight.job_root.mkdir(parents=True, exist_ok=True)
        _safe_path(preflight.job_root)
        with _JobLock(preflight.job_root):
            plan_payload = _plan_payload(preflight)
            _load_or_write_immutable_envelope(
                preflight.job_root / "plan.json",
                plan_payload,
                DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PLAN_BYTES,
                "job_plan_invalid",
            )
            progress_path = preflight.job_root / "progress.json"
            progress = _load_or_initialize_progress(progress_path, preflight)
            refs_by_index = _refs_from_progress(progress, preflight)
            processed = set(progress["processed_segment_indices"])
            if _is_cancelled(request.cancel_callback):
                progress = _save_progress(
                    progress_path,
                    _update_progress(
                        progress,
                        status="cancelled",
                        error_code="cancelled_before_first_segment",
                    ),
                )
                _emit_progress(progress_callback, progress)
                return _result_from_progress(
                    preflight,
                    progress,
                    status="cancelled",
                    step="cancelled_before_first_segment",
                    error_code="cancelled_before_first_segment",
                    parent_refs=refs_by_index,
                )

            run_writer: DailyMarketUniverseRunWriter | None = None
            current_run_progress: Mapping[str, Any] | None = None
            try:
                run_writer = create_daily_market_universe_run_writer(
                    preflight.output_root,
                    plan,
                    cancel_callback=request.cancel_callback,
                )
                current_run_progress = run_writer.progress
                run_segments = _run_segment_map(current_run_progress)
                for index in processed:
                    if run_segments.get(index) != "processed":
                        raise DailyMarketUniverseProductionError(
                            "job_progress_conflict"
                        )
                progress = _update_progress(
                    progress,
                    status="running",
                    error_code="",
                    processed_segment_indices=sorted(processed),
                    counts=_counts_from_run_progress(current_run_progress, plan),
                )
                progress = _save_progress(progress_path, progress)
                _emit_progress(progress_callback, progress)

                for segment in plan.segments:
                    if not segment.included_stock_codes:
                        continue
                    _raise_if_cancelled(request.cancel_callback)
                    _assert_current_source_clock(request, preflight.source_clock)
                    reference = refs_by_index.get(segment.segment_index)
                    if reference is None:
                        reference = _discover_completed_parent(preflight, segment)
                    if reference is None:
                        reference = _produce_parent_segment(
                            request, preflight, segment
                        )
                    _verify_parent_for_segment(
                        reference, preflight, segment
                    )
                    refs_by_index[segment.segment_index] = reference
                    progress = _update_progress(
                        progress,
                        status="running",
                        error_code="",
                        parent_references=_serialize_parent_references(refs_by_index),
                    )
                    progress = _save_progress(progress_path, progress)
                    _emit_progress(
                        progress_callback,
                        {
                            **progress,
                            "event": "parent_verified",
                            "segment_index": segment.segment_index,
                        },
                    )
                    _raise_if_cancelled(request.cancel_callback)
                    if segment.segment_index not in processed:
                        run_writer.append_parent_segment(
                            segment.segment_index, reference
                        )
                        processed.add(segment.segment_index)
                        current_run_progress = run_writer.progress
                        progress = _update_progress(
                            progress,
                            status="running",
                            error_code="",
                            processed_segment_indices=sorted(processed),
                            counts=_counts_from_run_progress(
                                current_run_progress, plan
                            ),
                        )
                        progress = _save_progress(progress_path, progress)
                        _emit_progress(
                            progress_callback,
                            {
                                **progress,
                                "event": "segment_saved",
                                "segment_index": segment.segment_index,
                            },
                        )
                    elif run_segments.get(segment.segment_index) != "processed":
                        # 外層 journal 可能在 append 原子保存前中斷；重送由底層
                        # verified writer 作同內容冪等核驗。
                        run_writer.append_parent_segment(
                            segment.segment_index, reference
                        )
                        current_run_progress = run_writer.progress

                _raise_if_cancelled(request.cancel_callback)
                _assert_current_source_clock(request, preflight.source_clock)
                descriptor = run_writer.finalize()
                with DailyMarketUniverseRunReader.open(
                    preflight.output_root, generation_id
                ) as reader:
                    if reader.manifest.get("plan") != plan.to_dict():
                        raise DailyMarketUniverseProductionError(
                            "published_run_plan_mismatch"
                        )
                    persisted_refs = _references_from_manifest(reader.manifest)
                    counts = dict(reader.counts)
                    if counts.get("processed_count") != len(plan.included_stock_codes):
                        raise DailyMarketUniverseProductionError(
                            "published_run_count_mismatch"
                        )
                progress = _update_progress(
                    progress,
                    status="complete",
                    error_code="",
                    processed_segment_indices=sorted(processed),
                    parent_references=_serialize_parent_references(refs_by_index),
                    counts=counts,
                )
                progress = _save_progress(progress_path, progress)
                _emit_progress(progress_callback, progress)
                return DailyMarketUniverseProductionResult(
                    status="complete",
                    step="published_and_readback_verified",
                    processed_segments=sum(
                        bool(segment.included_stock_codes) for segment in plan.segments
                    ),
                    total_segments=total_segments,
                    counts=counts,
                    error_code="",
                    cause_code="",
                    generation_identity_sha256=generation_id,
                    manifest_path=descriptor.output_path / "manifest.json",
                    job_root=preflight.job_root,
                    parent_references=persisted_refs,
                )
            except Exception as exc:
                code = _exception_code(exc) or "producer_failed"
                status = "cancelled" if _is_cancel_code(code) or _cancel_callback_true(request.cancel_callback) else "incomplete"
                if run_writer is not None:
                    try:
                        if status == "cancelled":
                            run_writer.cancel()
                        current_run_progress = run_writer.progress
                    except Exception:
                        pass
                counts = (
                    _counts_from_run_progress(current_run_progress, plan)
                    if current_run_progress is not None
                    else _initial_counts(plan)
                )
                progress = _update_progress(
                    progress,
                    status=status,
                    error_code=code,
                    processed_segment_indices=sorted(processed),
                    parent_references=_serialize_parent_references(refs_by_index),
                    counts=counts,
                )
                try:
                    progress = _save_progress(progress_path, progress)
                    _emit_progress(progress_callback, progress)
                except Exception:
                    # 保留原始失敗碼；journal失敗不可能把不完整 run 變成 complete。
                    pass
                return _result_from_progress(
                    preflight,
                    progress,
                    status=status,
                    step="production",
                    error_code=code,
                    cause_code=_exception_cause(exc),
                    parent_refs=refs_by_index,
                )
            finally:
                if run_writer is not None:
                    run_writer.close()
    except DailyMarketUniverseProductionError as exc:
        return _failed_result(
            request,
            step="job_journal",
            error_code=exc.code,
            cause_code=exc.cause_code,
            preflight=preflight,
        )
    except Exception as exc:
        return _failed_result(
            request,
            step="job_journal",
            error_code="job_journal_failed",
            cause_code=_exception_code(exc),
            preflight=preflight,
        )


def resume_daily_market_universe_run(
    request: DailyMarketUniverseProductionRequest,
    *,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> DailyMarketUniverseProductionResult:
    """以同一輸入與 source pin 尋回 frozen job；新 source pin 會形成不同 job。"""

    return produce_daily_market_universe_run(
        request, progress_callback=progress_callback
    )


def _validate_request_shape(request: DailyMarketUniverseProductionRequest) -> None:
    if not isinstance(request, DailyMarketUniverseProductionRequest):
        raise DailyMarketUniverseProductionError("request_invalid")
    for value, name, limit in (
        (request.universe_id, "universe_id", _MAX_UNIVERSE_ID),
        (request.population_version, "population_version", _MAX_POPULATION_VERSION),
        (request.strategy_version, "strategy_version", _MAX_POPULATION_VERSION),
        (request.contract_version, "contract_version", 128),
    ):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise DailyMarketUniverseProductionError(f"{name}_invalid")
    if isinstance(request.decision_date, datetime) or not isinstance(request.decision_date, date):
        raise DailyMarketUniverseProductionError("decision_date_invalid")
    codes = request.raw_stock_codes
    if isinstance(codes, (str, bytes)) or not isinstance(codes, Sequence) or not codes:
        raise DailyMarketUniverseProductionError("universe_empty")
    if len(codes) > DAILY_MARKET_UNIVERSE_PRODUCER_MAX_INPUT_CODES:
        raise DailyMarketUniverseProductionError("population_member_limit")
    for raw in codes:
        if not isinstance(raw, str) or not _STOCK_CODE_RE.fullmatch(raw.strip().upper()):
            raise DailyMarketUniverseProductionError("stock_code_invalid")
    if isinstance(request.excluded_stock_codes, Mapping):
        exclusion_items = list(request.excluded_stock_codes.items())
    else:
        if isinstance(request.excluded_stock_codes, (str, bytes)) or not isinstance(
            request.excluded_stock_codes, Sequence
        ):
            raise DailyMarketUniverseProductionError("exclusions_invalid")
        exclusion_items = list(request.excluded_stock_codes)
    if len(exclusion_items) > DAILY_MARKET_UNIVERSE_PRODUCER_MAX_INPUT_CODES:
        raise DailyMarketUniverseProductionError("population_member_limit")
    seen: set[str] = set()
    for item in exclusion_items:
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes)) or len(item) != 2:
            raise DailyMarketUniverseProductionError("exclusion_invalid")
        raw_code, reason = item
        if (
            not isinstance(raw_code, str)
            or not _STOCK_CODE_RE.fullmatch(raw_code.strip().upper())
            or not isinstance(reason, str)
            or not reason.strip()
            or len(reason.strip()) > _MAX_REASON_CHARS
        ):
            raise DailyMarketUniverseProductionError("exclusion_invalid")
        code = raw_code.strip().upper()
        if code in seen:
            raise DailyMarketUniverseProductionError("duplicate_exclusion")
        seen.add(code)


def _resolve_input_path(value: Path | str, code: str) -> Path:
    try:
        raw = Path(value).expanduser().absolute()
        _safe_path(raw)
        resolved = raw.resolve(strict=False)
        if not resolved.is_absolute():
            raise ValueError(code)
        return resolved
    except Exception as exc:
        raise DailyMarketUniverseProductionError(code, cause_code=_exception_code(exc)) from exc


def _check_root_preflight(
    db_path: Path,
    output_root: Path,
    *,
    input_identity: str,
    research_scope: ResearchCaptureWriteScope | None = None,
) -> None:
    """未明示 scope 沿用隔離政策；明示時重驗來源及派生保存範圍。"""

    job_root = output_root.parent / "universe_jobs" / _job_directory_key(input_identity)
    try:
        for path in (db_path, output_root, job_root):
            _safe_path(path)
            if path.exists() and not path.is_dir() and path != db_path:
                raise DailyMarketUniverseProductionError("output_root_invalid")
        if research_scope is None:
            _require_isolated_root(output_root)
            _require_isolated_root(job_root)
        else:
            research_scope.validate()
            if db_path != research_scope.source_database:
                raise DailyMarketUniverseProductionError("research_scope_source_mismatch")
            for target in (output_root, job_root):
                if target == research_scope.root or not target.is_relative_to(research_scope.root):
                    raise DailyMarketUniverseProductionError("research_scope_output_outside_root")
        if _paths_overlap(output_root, db_path) or _paths_overlap(job_root, db_path):
            raise DailyMarketUniverseProductionError("source_output_overlap")
        if _paths_overlap(output_root, job_root):
            raise DailyMarketUniverseProductionError("output_roots_overlap")
        # 讓共用 writer 自己判定其目前既有 guard；不改寫、不繞過 guard。
        snapshot_root, capture_root, _universe_path = _segment_storage_roots(
            job_root, "segment-000001"
        )
        BoundedRuleResearchCaptureWriter(snapshot_root / "guard", research_scope=research_scope)
        BoundedRuleResearchCaptureWriter(capture_root / "parents", research_scope=research_scope)
    except DailyMarketUniverseProductionError as exc:
        if exc.code == "source_output_overlap" or exc.code == "output_roots_overlap":
            raise
        raise DailyMarketUniverseProductionError(
            "root_preflight_failed", cause_code=exc.code
        ) from exc
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "root_preflight_failed", cause_code=_exception_code(exc)
        ) from exc


def _require_isolated_root(path: Path) -> None:
    allowed = (
        Path(__file__).resolve().parents[1] / "output" / "qa",
        Path(tempfile.gettempdir()).resolve(),
    )
    resolved = path.resolve(strict=False)
    if not any(
        resolved != root and resolved.is_relative_to(root.resolve())
        for root in allowed
    ):
        raise DailyMarketUniverseProductionError(
            "isolated_output_required", cause_code="isolated_output_required"
        )


def _paths_overlap(first: Path, second: Path) -> bool:
    a = first.resolve(strict=False)
    b = second.resolve(strict=False)
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _job_directory_key(input_identity: str) -> str:
    """Windows 路徑使用 96 位元識別碼；完整 SHA-256 保留於受驗 journal。"""

    if not _SHA256_RE.fullmatch(input_identity):
        raise DailyMarketUniverseProductionError("input_identity_invalid")
    return input_identity[:24]


def _normalized_cutoff(value: datetime, day: date) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMarketUniverseProductionError("decision_cutoff_timezone_missing")
    local = value.astimezone(ZoneInfo("Asia/Taipei"))
    if local.date() != day:
        raise DailyMarketUniverseProductionError("decision_cutoff_date_mismatch")
    if local.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise DailyMarketUniverseProductionError("decision_cutoff_future")
    return local.isoformat()


def _assert_current_source_clock(
    request: DailyMarketUniverseProductionRequest,
    expected: DailyMarketParentSourceClock,
) -> None:
    contract = feature_contract_for_version(request.contract_version)
    try:
        with SQLiteDailyMarketSnapshotSource(
            Path(expected.source_binding["database"]), request.decision_date
        ) as source:
            binding = _source_binding(source)
            source.validate_source_stable()
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "source_changed", cause_code=_exception_code(exc)
        ) from exc
    encoded = _canonical_json(binding)
    actual = DailyMarketParentSourceClock(
        decision_date=request.decision_date.isoformat(),
        decision_cutoff=expected.decision_cutoff,
        source_binding_json=encoded,
        source_binding_sha256=_sha256_bytes(encoded.encode("utf-8")),
        feature_contract_version=contract.version,
        method_contracts_sha256=current_method_contract_binding(
            contract_version=contract.version
        )[1],
    )
    if actual.to_dict() != expected.to_dict():
        raise DailyMarketUniverseProductionError("source_changed")


def _produce_parent_segment(
    request: DailyMarketUniverseProductionRequest,
    preflight: DailyMarketUniverseProductionPreflight,
    segment: Any,
) -> DailyMarketParentCaptureReference:
    snapshot_root, capture_root, universe_path = _segment_storage_roots(
        preflight.job_root, segment.segment_id
    )
    payload = {
        "schema_version": PARENT_UNIVERSE_SCHEMA,
        "universe_id": request.universe_id.strip(),
        "version": request.population_version.strip(),
        "as_of_date": request.decision_date.isoformat(),
        "method": "daily-market-close-ma.v1",
        "scope": "bounded_multibatch_research_cohort",
        "included_stock_codes": list(segment.included_stock_codes),
        "excluded_stock_codes": [],
        "population_count": len(segment.included_stock_codes),
        "research_only": True,
        "complete_fixed_cohort": True,
    }
    _write_immutable_json(universe_path, payload, MAX_CAPTURE_BYTES)
    loaded = load_parent_universe(universe_path)
    if loaded["value"] != payload:
        raise DailyMarketUniverseProductionError("segment_universe_binding_mismatch")
    result = produce_parent_rule_samples(
        db_path=preflight.db_path,
        snapshot_root=snapshot_root,
        capture_root=capture_root,
        universe_path=universe_path,
        decision_cutoff=request.decision_cutoff,
        cancel_callback=request.cancel_callback,
        contract_version=preflight.contract_version,
        research_scope=request.research_scope,
    )
    if result.get("status") != "complete" or result.get("sample_readiness_status") != "verified":
        code = _parent_result_error_code(result)
        if _cancel_callback_true(request.cancel_callback) and code in {"", "parent_incomplete"}:
            code = "parent_cancelled"
        raise DailyMarketUniverseProductionError("parent_incomplete", cause_code=code)
    parent_capture = result.get("parent_capture")
    receipt = parent_capture.get("receipt") if isinstance(parent_capture, Mapping) else None
    identity = receipt.get("capture_identity_sha256") if isinstance(receipt, Mapping) else None
    if not isinstance(identity, str) or not _SHA256_RE.fullmatch(identity):
        raise DailyMarketUniverseProductionError("parent_identity_missing")
    return DailyMarketParentCaptureReference(
        snapshot_root,
        capture_root,
        universe_path,
        identity,
    ).resolved()


def _parent_result_error_code(result: Mapping[str, Any]) -> str:
    explicit = result.get("error_code") or result.get("cohort_attempt_status")
    if explicit:
        return str(explicit)[:256]
    production = result.get("production")
    if isinstance(production, list):
        failures = [
            item
            for item in production
            if isinstance(item, Mapping) and item.get("status") != "captured"
        ]
        if failures:
            first = failures[0]
            detail = ":".join(
                str(first.get(key) or "")
                for key in ("batch_id", "status", "error_code", "production_status", "sample_capture_status")
            )
            errors = first.get("source_errors")
            if isinstance(errors, Mapping) and errors:
                detail = f"{detail}:{next(iter(errors.values()))}"
            return detail[:256]
    return str(result.get("status") or result.get("sample_readiness_status") or "parent_incomplete")


def _segment_root(job_root: Path, segment_id: str) -> Path:
    if not re.fullmatch(r"segment-[0-9]{6}", segment_id):
        raise DailyMarketUniverseProductionError("segment_id_invalid")
    # 保持內部路徑簡短，兼容未啟用一般長路徑的 Windows 安裝。
    segment_number = int(segment_id[-6:]) - 1
    if not 0 <= segment_number <= 999:
        raise DailyMarketUniverseProductionError("segment_id_invalid")
    root = job_root / f"s{_base36(segment_number)}"
    _safe_path(root)
    if not root.resolve(strict=False).is_relative_to(job_root.resolve(strict=False)):
        raise DailyMarketUniverseProductionError("segment_path_escape")
    return root


def _segment_storage_roots(
    job_root: Path, segment_id: str
) -> tuple[Path, Path, Path]:
    segment_root = _segment_root(job_root, segment_id)
    segment_number = int(segment_id[-6:]) - 1
    if not 0 <= segment_number <= 999:
        raise DailyMarketUniverseProductionError("segment_id_invalid")
    segment_key = _base36(segment_number)
    capture_root = job_root / f"c{segment_key}"
    universe_path = job_root / f"u{segment_key}.json"
    for path in (segment_root, capture_root, universe_path):
        _safe_path(path)
        if not path.resolve(strict=False).is_relative_to(job_root.resolve(strict=False)):
            raise DailyMarketUniverseProductionError("segment_path_escape")
    return segment_root, capture_root, universe_path


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value < 0:
        raise DailyMarketUniverseProductionError("segment_id_invalid")
    if value == 0:
        return "0"
    digits = ""
    while value:
        value, remainder = divmod(value, 36)
        digits = alphabet[remainder] + digits
    return digits


def _discover_completed_parent(
    preflight: DailyMarketUniverseProductionPreflight,
    segment: Any,
) -> DailyMarketParentCaptureReference | None:
    snapshot_root, capture_root, universe_path = _segment_storage_roots(
        preflight.job_root, segment.segment_id
    )
    store_root = capture_root / "parents"
    if not store_root.is_dir():
        return None
    _safe_path(store_root)
    entries = sorted(store_root.iterdir(), key=lambda path: path.name)
    if len(entries) > DAILY_MARKET_UNIVERSE_PRODUCER_MAX_CAPTURE_ENTRIES + 1:
        raise DailyMarketUniverseProductionError("parent_capture_inventory_limit")
    writer = BoundedRuleResearchParentWriter(store_root, read_only=True)
    for entry in entries:
        _safe_path(entry)
        if entry.name == ".writer.lock":
            continue
        if not entry.is_dir() or not _SHA256_RE.fullmatch(entry.name):
            raise DailyMarketUniverseProductionError("parent_capture_inventory_invalid")
        try:
            package = writer.read(entry.name)
        except Exception as exc:
            raise DailyMarketUniverseProductionError(
                "parent_capture_inventory_corrupt", cause_code=_exception_code(exc)
            ) from exc
        body = package.get("capture")
        if not isinstance(body, Mapping) or body.get("status") != "complete":
            continue
        reference = DailyMarketParentCaptureReference(
            snapshot_root, capture_root, universe_path, entry.name
        ).resolved()
        _verify_parent_for_segment(reference, preflight, segment)
        return reference
    return None


def _verify_parent_for_segment(
    reference: DailyMarketParentCaptureReference,
    preflight: DailyMarketUniverseProductionPreflight,
    segment: Any,
) -> Mapping[str, Any]:
    expected = DailyMarketParentCaptureReference(
        *_segment_storage_roots(preflight.job_root, segment.segment_id),
        reference.capture_identity_sha256,
    ).resolved()
    actual = reference.resolved()
    if (
        actual.snapshot_root != expected.snapshot_root
        or actual.capture_root != expected.capture_root
        or actual.universe_path != expected.universe_path
    ):
        raise DailyMarketUniverseProductionError("parent_reference_path_mismatch")
    try:
        descriptor = verify_parent_capture_reference(actual)
        clock = parent_source_clock_from_reference(actual)
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "parent_verification_failed", cause_code=_exception_code(exc)
        ) from exc
    if (
        descriptor.get("status") != "complete"
        or descriptor.get("readiness", {}).get("status") != "saved_verified_complete"
        or descriptor.get("universe_id") != preflight.plan.universe_id
        or descriptor.get("population_version") != preflight.plan.population_version
        or descriptor.get("decision_date") != preflight.plan.decision_date.isoformat()
        or descriptor.get("decision_cutoff") != preflight.plan.decision_cutoff
        or tuple(descriptor.get("included_stock_codes", ()))
        != segment.included_stock_codes
        or descriptor.get("excluded_stock_codes") != ()
        or clock.to_dict() != preflight.source_clock.to_dict()
        or descriptor.get("feature_contract_version") != preflight.contract_version
    ):
        raise DailyMarketUniverseProductionError("parent_segment_contract_mismatch")
    if len(segment.included_stock_codes) > 256:
        raise DailyMarketUniverseProductionError("parent_segment_bound")
    return descriptor


def _plan_payload(
    preflight: DailyMarketUniverseProductionPreflight,
) -> dict[str, Any]:
    return {
        "schema_version": DAILY_MARKET_UNIVERSE_PRODUCER_PLAN_SCHEMA,
        "input_identity_sha256": preflight.input_identity_sha256,
        "generation_identity_sha256": preflight.plan.generation_identity_sha256,
        "db_path": str(preflight.db_path),
        "output_root": str(preflight.output_root),
        "job_root": str(preflight.job_root),
        "contract_version": preflight.contract_version,
        # JSON 讀回會把 tuple revision pins 轉為 list；記憶體中的不可變
        # payload 採相同 canonical JSON 形狀，讓新程序續跑能逐值核對。
        "source_binding": json.loads(_canonical_json(dict(preflight.source_binding))),
        "source_clock": preflight.source_clock.to_dict(),
        "run_plan": preflight.plan.to_dict(),
    }


def _initial_progress(
    preflight: DailyMarketUniverseProductionPreflight,
) -> dict[str, Any]:
    return {
        "schema_version": DAILY_MARKET_UNIVERSE_PRODUCER_PROGRESS_SCHEMA,
        "input_identity_sha256": preflight.input_identity_sha256,
        "generation_identity_sha256": preflight.plan.generation_identity_sha256,
        "status": "pending",
        "error_code": "",
        "processed_segment_indices": [],
        "parent_references": [],
        "counts": _initial_counts(preflight.plan),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_or_initialize_progress(path: Path, preflight: DailyMarketUniverseProductionPreflight) -> dict[str, Any]:
    if not path.exists():
        return _save_progress(path, _initial_progress(preflight))
    payload = _read_envelope(path, DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PROGRESS_BYTES)
    required = {
        "schema_version", "input_identity_sha256", "generation_identity_sha256",
        "status", "error_code", "processed_segment_indices", "parent_references",
        "counts", "updated_at",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise DailyMarketUniverseProductionError("job_progress_invalid")
    if (
        payload["schema_version"] != DAILY_MARKET_UNIVERSE_PRODUCER_PROGRESS_SCHEMA
        or payload["input_identity_sha256"] != preflight.input_identity_sha256
        or payload["generation_identity_sha256"] != preflight.plan.generation_identity_sha256
        or payload["status"] not in {"pending", "running", "cancelled", "incomplete", "complete"}
        or not isinstance(payload["error_code"], str)
        or not isinstance(payload["updated_at"], str)
        or not isinstance(payload["counts"], dict)
        or not isinstance(payload["processed_segment_indices"], list)
        or not isinstance(payload["parent_references"], list)
    ):
        raise DailyMarketUniverseProductionError("job_progress_binding_mismatch")
    processed = payload["processed_segment_indices"]
    if any(type(index) is not int or not 0 <= index < len(preflight.plan.segments) for index in processed):
        raise DailyMarketUniverseProductionError("job_progress_segment_invalid")
    if processed != sorted(set(processed)):
        raise DailyMarketUniverseProductionError("job_progress_segment_invalid")
    payload["parent_references"] = _validated_reference_records(
        payload["parent_references"], preflight
    )
    return payload


def _refs_from_progress(
    progress: Mapping[str, Any],
    preflight: DailyMarketUniverseProductionPreflight,
) -> dict[int, DailyMarketParentCaptureReference]:
    refs: dict[int, DailyMarketParentCaptureReference] = {}
    for record in progress["parent_references"]:
        index = int(record["segment_index"])
        segment = preflight.plan.segments[index]
        reference = _reference_for_segment(
            preflight, segment.segment_id, record["capture_identity_sha256"]
        )
        _verify_parent_for_segment(reference, preflight, segment)
        refs[index] = reference
    return refs


def _validated_reference_records(
    records: Any,
    preflight: DailyMarketUniverseProductionPreflight,
) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise DailyMarketUniverseProductionError("job_parent_references_invalid")
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"segment_index", "capture_identity_sha256"}:
            raise DailyMarketUniverseProductionError("job_parent_references_invalid")
        index = record["segment_index"]
        identity = record["capture_identity_sha256"]
        if (
            type(index) is not int
            or index in seen
            or not 0 <= index < len(preflight.plan.segments)
            or not preflight.plan.segments[index].included_stock_codes
            or not isinstance(identity, str)
            or not _SHA256_RE.fullmatch(identity)
        ):
            raise DailyMarketUniverseProductionError("job_parent_references_invalid")
        seen.add(index)
        normalized.append({"segment_index": index, "capture_identity_sha256": identity})
    return sorted(normalized, key=lambda item: item["segment_index"])


def _serialize_parent_references(
    references: Mapping[int, DailyMarketParentCaptureReference],
) -> list[dict[str, Any]]:
    return [
        {
            "segment_index": index,
            "capture_identity_sha256": references[index].capture_identity_sha256,
        }
        for index in sorted(references)
    ]


def _reference_for_segment(
    preflight: DailyMarketUniverseProductionPreflight,
    segment_id: str,
    capture_identity: str,
) -> DailyMarketParentCaptureReference:
    snapshot_root, capture_root, universe_path = _segment_storage_roots(
        preflight.job_root, segment_id
    )
    return DailyMarketParentCaptureReference(
        snapshot_root,
        capture_root,
        universe_path,
        capture_identity,
    ).resolved()


def _run_segment_map(progress: Mapping[str, Any]) -> dict[int, str]:
    segments = progress.get("segments")
    if not isinstance(segments, list):
        raise DailyMarketUniverseProductionError("run_progress_invalid")
    result: dict[int, str] = {}
    for item in segments:
        if not isinstance(item, Mapping) or type(item.get("segment_index")) is not int:
            raise DailyMarketUniverseProductionError("run_progress_invalid")
        result[item["segment_index"]] = str(item.get("status"))
    return result


def _counts_from_run_progress(
    progress: Mapping[str, Any], plan: Any
) -> dict[str, int]:
    counts = progress.get("counts")
    if not isinstance(counts, Mapping):
        return _initial_counts(plan)
    keys = (
        "declared_unique_count", "raw_stock_code_count", "duplicate_stock_count",
        "duplicate_occurrence_count", "included_count", "excluded_count",
        "processed_count", "pending_count", "snapshot_missing_stock_count",
        "unknown_evidence_stock_count", "missing_data_stock_count",
    )
    return {
        key: int(counts.get(key, 0))
        for key in keys
        if type(counts.get(key, 0)) is int
    }


def _initial_counts(plan: Any) -> dict[str, int]:
    duplicate_count = len(plan.duplicate_stock_codes)
    return {
        "declared_unique_count": len(plan.declared_stock_codes),
        "raw_stock_code_count": plan.raw_stock_code_count,
        "duplicate_stock_count": duplicate_count,
        "duplicate_occurrence_count": sum(count - 1 for _code, count in plan.duplicate_stock_codes),
        "included_count": len(plan.included_stock_codes),
        "excluded_count": len(plan.excluded_stock_codes),
        "processed_count": 0,
        "pending_count": len(plan.included_stock_codes),
        "snapshot_missing_stock_count": 0,
        "unknown_evidence_stock_count": 0,
        "missing_data_stock_count": 0,
    }


def _update_progress(
    current: Mapping[str, Any],
    *,
    status: str,
    error_code: str,
    processed_segment_indices: list[int] | None = None,
    parent_references: list[dict[str, Any]] | None = None,
    counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    updated = dict(current)
    updated.update(
        {
            "status": status,
            "error_code": error_code,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if processed_segment_indices is not None:
        updated["processed_segment_indices"] = processed_segment_indices
    if parent_references is not None:
        updated["parent_references"] = parent_references
    if counts is not None:
        updated["counts"] = dict(counts)
    return updated


def _save_progress(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_envelope(
        path,
        payload,
        DAILY_MARKET_UNIVERSE_PRODUCER_MAX_PROGRESS_BYTES,
        replace=True,
    )
    return payload


def _load_or_write_immutable_envelope(
    path: Path,
    payload: dict[str, Any],
    limit: int,
    error_code: str,
) -> None:
    if path.exists():
        existing = _read_envelope(path, limit)
        if existing != payload:
            raise DailyMarketUniverseProductionError(error_code)
        return
    _write_envelope(path, payload, limit, replace=False)


def _write_immutable_json(path: Path, payload: Mapping[str, Any], limit: int) -> None:
    raw = _canonical_json(dict(payload)).encode("utf-8")
    if len(raw) > limit:
        raise DailyMarketUniverseProductionError("segment_universe_byte_limit")
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = _read_limited(path, limit)
        if existing != raw:
            raise DailyMarketUniverseProductionError("segment_universe_changed")
        return
    _atomic_write(path, raw, replace=False)


def _write_envelope(path: Path, payload: Mapping[str, Any], limit: int, *, replace: bool) -> None:
    envelope = {
        "payload": dict(payload),
        "payload_sha256": _sha256_bytes(_canonical_json(dict(payload)).encode("utf-8")),
    }
    raw = _canonical_json(envelope).encode("utf-8")
    if len(raw) > limit:
        raise DailyMarketUniverseProductionError("job_envelope_byte_limit")
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, raw, replace=replace)


def _read_envelope(path: Path, limit: int) -> dict[str, Any]:
    raw = _read_limited(path, limit)
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyMarketUniverseProductionError("job_envelope_invalid") from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"payload", "payload_sha256"}
        or not isinstance(envelope.get("payload"), dict)
        or _canonical_json(envelope).encode("utf-8") != raw
        or envelope.get("payload_sha256")
        != _sha256_bytes(_canonical_json(envelope["payload"]).encode("utf-8"))
    ):
        raise DailyMarketUniverseProductionError("job_envelope_digest_mismatch")
    return envelope["payload"]


def _read_limited(path: Path, limit: int) -> bytes:
    _safe_path(path)
    try:
        before = path.stat()
        if not path.is_file() or before.st_nlink != 1 or before.st_size > limit:
            raise DailyMarketUniverseProductionError("job_file_budget_or_link")
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        current = path.stat()
    except DailyMarketUniverseProductionError:
        raise
    except OSError as exc:
        raise DailyMarketUniverseProductionError("job_file_unreadable") from exc
    if (
        len(raw) > limit
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise DailyMarketUniverseProductionError("job_file_changed_during_read")
    return raw


def _atomic_write(path: Path, raw: bytes, *, replace: bool) -> None:
    temp_path = path.with_name(f".w{uuid4().hex[:8]}")
    _safe_path(temp_path)
    try:
        with temp_path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and (path.exists() or path.is_symlink()):
            raise DailyMarketUniverseProductionError("immutable_job_file_exists")
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _references_from_manifest(manifest: Mapping[str, Any]) -> tuple[DailyMarketParentCaptureReference, ...]:
    references: list[DailyMarketParentCaptureReference] = []
    segments = manifest.get("segments")
    if not isinstance(segments, list):
        raise DailyMarketUniverseProductionError("published_parent_references_invalid")
    for item in segments:
        if not isinstance(item, Mapping) or item.get("status") != "processed":
            continue
        value = item.get("parent_reference")
        if not isinstance(value, Mapping):
            raise DailyMarketUniverseProductionError("published_parent_reference_invalid")
        try:
            reference = DailyMarketParentCaptureReference(
                value["snapshot_root"],
                value["capture_root"],
                value["universe_path"],
                value["capture_identity_sha256"],
            ).resolved()
        except (KeyError, TypeError, ValueError) as exc:
            raise DailyMarketUniverseProductionError("published_parent_reference_invalid") from exc
        references.append(reference)
    return tuple(references)


def _read_published_run(
    preflight: DailyMarketUniverseProductionPreflight,
) -> DailyMarketUniverseProductionResult | None:
    run_path = preflight.output_root / "generations" / preflight.plan.generation_identity_sha256
    if not run_path.exists():
        return None
    try:
        with DailyMarketUniverseRunReader.open(
            preflight.output_root, preflight.plan.generation_identity_sha256
        ) as reader:
            if reader.manifest.get("plan") != preflight.plan.to_dict():
                raise DailyMarketUniverseProductionError("published_run_plan_mismatch")
            counts = dict(reader.counts)
            references = _references_from_manifest(reader.manifest)
            return DailyMarketUniverseProductionResult(
                status="complete",
                step="existing_publication_readback_verified",
                processed_segments=sum(
                    bool(segment.included_stock_codes)
                    for segment in preflight.plan.segments
                ),
                total_segments=len(preflight.plan.segments),
                counts=counts,
                error_code="",
                cause_code="",
                generation_identity_sha256=preflight.plan.generation_identity_sha256,
                manifest_path=run_path / "manifest.json",
                job_root=preflight.job_root,
                parent_references=references,
            )
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "published_run_verification_failed", cause_code=_exception_code(exc)
        ) from exc


def _result_from_progress(
    preflight: DailyMarketUniverseProductionPreflight,
    progress: Mapping[str, Any],
    *,
    status: str,
    step: str,
    error_code: str,
    cause_code: str = "",
    parent_refs: Mapping[int, DailyMarketParentCaptureReference],
) -> DailyMarketUniverseProductionResult:
    processed = progress.get("processed_segment_indices", [])
    return DailyMarketUniverseProductionResult(
        status=status,
        step=step,
        processed_segments=len(processed) if isinstance(processed, list) else 0,
        total_segments=len(preflight.plan.segments),
        counts=dict(progress.get("counts", _initial_counts(preflight.plan))),
        error_code=error_code,
        cause_code=cause_code,
        generation_identity_sha256=preflight.plan.generation_identity_sha256,
        manifest_path=None,
        job_root=preflight.job_root,
        parent_references=tuple(parent_refs[index] for index in sorted(parent_refs)),
    )


def _failed_result(
    request: DailyMarketUniverseProductionRequest,
    *,
    step: str,
    error_code: str,
    cause_code: str = "",
    preflight: DailyMarketUniverseProductionPreflight | None = None,
) -> DailyMarketUniverseProductionResult:
    plan = preflight.plan if preflight is not None else None
    return DailyMarketUniverseProductionResult(
        status="incomplete",
        step=step,
        processed_segments=0,
        total_segments=len(plan.segments) if plan is not None else 0,
        counts=_initial_counts(plan) if plan is not None else {},
        error_code=error_code,
        cause_code=cause_code,
        generation_identity_sha256=(plan.generation_identity_sha256 if plan is not None else None),
        manifest_path=None,
        job_root=(preflight.job_root if preflight is not None else None),
        parent_references=(),
    )


def _emit_progress(
    callback: Callable[[Mapping[str, Any]], None] | None,
    payload: Mapping[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(dict(payload))
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "progress_callback_failed", cause_code=_exception_code(exc)
        ) from exc


def _raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if _is_cancelled(callback):
        raise DailyMarketUniverseProductionError("producer_cancelled")


def _is_cancelled(callback: Callable[[], bool] | None) -> bool:
    if callback is None:
        return False
    try:
        return bool(callback())
    except Exception as exc:
        raise DailyMarketUniverseProductionError(
            "cancel_callback_failed", cause_code=_exception_code(exc)
        ) from exc


def _cancel_callback_true(callback: Callable[[], bool] | None) -> bool:
    try:
        return bool(callback()) if callback is not None else False
    except Exception:
        return False


def _is_cancel_code(code: str) -> bool:
    return code in {
        "producer_cancelled",
        "parent_cancelled",
        "run_cancelled",
        "cancelled_before_first_segment",
    } or code.endswith("_cancelled")


def _exception_code(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if isinstance(code, str) and code:
        return code
    text = str(exc)
    if ":" in text:
        prefix = text.split(":", 1)[0]
        if re.fullmatch(r"[a-z][a-z0-9_]{1,100}", prefix):
            return prefix
    return type(exc).__name__


def _exception_cause(exc: BaseException) -> str:
    cause = getattr(exc, "cause_code", "")
    return cause if isinstance(cause, str) else ""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketUniverseProductionError("json_value_invalid") from exc


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
