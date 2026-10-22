"""以 repository state 執行 Paper 盤前 snapshot producer。

這是 ``baldr-paper-portfolio-daily`` 的正式 scheduled adapter。D 槽既有
Paper snapshot 與 baseline 只以 SQLite ``mode=ro``／檔案 hash 作為來源；首次
執行會透過一致 backup 建立 repository copy，之後不再將 D snapshot 當 writer
target。盤前、EOD replay 與 Formal reader 共用
``output/paper_execution_eod_replay/paper_portfolio/paper_portfolio.sqlite``，
而市場 SQLite 仍只讀。所有這些結果都是 research／candidate scope，不會
產生正式信用、券商委託或歷史回填。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from collections.abc import Callable
from datetime import date, datetime, time as datetime_time, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time as time_module
from uuid import uuid4


ROOT = Path(os.path.abspath(__file__)).parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.official_trading_calendar import OfficialTradingCalendar  # noqa: E402
from app_module.paper_daily_status_contract import (  # noqa: E402
    PAPER_DAILY_STATUS_SCHEMA_VERSION,
)
from runtime.console_encoding import configure_utf8_console  # noqa: E402
from scripts.run_paper_portfolio_daily import (  # noqa: E402
    TAIPEI,
    _latest_reached_decision_at,
    run as run_paper_portfolio_daily,
)
from scripts.scheduled.paper_portfolio_state_isolation import (  # noqa: E402
    ensure_repo_state_from_readonly_source,
    publish_repo_state_head,
)
from runtime.repository_output import (  # noqa: E402
    RepositoryOutputBoundaryError,
    is_repository_output_path,
    resolve_repository_output_path,
    validate_repository_root,
)


DEFAULT_DATA_ROOT = Path(r"F:\Min\Python\Project\FA_Data")
SOURCE_STATE_DB = (
    DEFAULT_DATA_ROOT / "output" / "paper_portfolio" / "paper_portfolio.sqlite"
)
SOURCE_BASELINE_PATH = (
    DEFAULT_DATA_ROOT / "output" / "paper_portfolio" / "baseline_20260712.json"
)
OPERATIONAL_ROOT = ROOT / "output" / "paper_execution_eod_replay"
PAPER_STATE_ROOT = OPERATIONAL_ROOT / "paper_portfolio"
STATE_DB = PAPER_STATE_ROOT / "paper_portfolio.sqlite"
STATE_SEED_MANIFEST = PAPER_STATE_ROOT / "state_seed_manifest.json"
MARKET_DB = DEFAULT_DATA_ROOT / "sqlite" / "twstock.db"
LEDGER_DB = OPERATIONAL_ROOT / "paper_trade_ledger.sqlite"
SCHEMA_VERSION = "paper-portfolio-daily-isolated-scope.v1"
TAIPEI_PREOPEN_CUTOFF = datetime_time(8, 30)
SCHEDULED_WAKE_LOCAL_TIME = "08:25"
SCHEDULED_WAKE_TIMEZONE = "Asia/Taipei"
RUN_STATE_SCHEMA_VERSION = "paper-portfolio-isolated-run-state.v1"
RUN_STATE_HEARTBEAT_INTERVAL_SECONDS = 60
RUN_STATE_STALE_AFTER_SECONDS = 180
RUN_STATE_TERMINAL_PHASES = frozenset({"terminal"})
CALENDAR_CACHE_ROOT = OPERATIONAL_ROOT / "calendar_cache"


def _parse_calendar_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name}_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


class _DecisionBoundOfficialCalendar:
    """將 official calendar source custody 綁定至 Paper decision clock。"""

    def __init__(
        self,
        delegate: OfficialTradingCalendar,
        *,
        decision_at: datetime,
    ) -> None:
        self._delegate = delegate
        self._decision_at = decision_at.astimezone(timezone.utc)

    def is_official_trading_day(
        self,
        target_date: date,
        allow_online_probe: bool = True,
    ) -> tuple[bool | None, str]:
        # Wrapper 對 Paper producer 固定使用已保存的 official cache；若 cache
        # 不可用，不能在 08:30 之後用 live response 補成因果日曆。
        is_trading_day, reason = self._delegate.is_official_trading_day(
            target_date,
            allow_online_probe=False,
        )
        if target_date.weekday() >= 5:
            return is_trading_day, reason
        evidence_for = getattr(self._delegate, "evidence_for", None)
        if not callable(evidence_for):
            return None, "official_calendar_evidence_missing"
        try:
            evidence = evidence_for(target_date)
        except Exception as error:  # noqa: BLE001 - producer must fail closed
            return None, f"official_calendar_evidence_exception:{type(error).__name__}"
        if not isinstance(evidence, Mapping):
            return None, "official_calendar_evidence_missing"
        available_at = evidence.get("available_at")
        if available_at is None:
            available_at = evidence.get("captured_at")
        if available_at is None:
            return None, "official_calendar_capture_missing"
        try:
            captured_at = _parse_calendar_timestamp(
                available_at,
                "official_calendar_available_at",
            )
        except ValueError as error:
            return None, f"official_calendar_capture_invalid:{error}"
        if captured_at > self._decision_at:
            return None, "official_calendar_capture_after_decision_at"
        return is_trading_day, reason


def _bind_calendar_to_decision(
    calendar: OfficialTradingCalendar | object | None,
    *,
    decision_at: datetime,
) -> object | None:
    if isinstance(calendar, OfficialTradingCalendar):
        return _DecisionBoundOfficialCalendar(calendar, decision_at=decision_at)
    return calendar


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _resolved(path: Path) -> Path:
    candidate = Path(os.path.abspath(path.expanduser()))
    try:
        if candidate == ROOT:
            return validate_repository_root(candidate)
        if is_repository_output_path(candidate, repository_root=ROOT):
            return resolve_repository_output_path(
                candidate,
                repository_root=ROOT,
            )
    except RepositoryOutputBoundaryError as error:
        raise RuntimeError(f"repository output boundary rejected path: {error}") from error
    return candidate.resolve()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    resolved = _resolved(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        import os

        os.fsync(stream.fileno())
    os.replace(temporary, resolved)


def _parse_run_state_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name}_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _run_state_root(operation_root: Path) -> Path:
    return _resolved(
        operation_root
        / "scheduled"
        / "paper_portfolio_isolated"
        / "run_state"
    )


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping):
        return None
    return dict(raw)


def _stale_previous_run_state(
    previous: Mapping[str, object] | None,
    *,
    observed_at: datetime,
) -> dict[str, object] | None:
    """Classify only stale non-terminal state; do not identify a terminator."""

    if previous is None:
        return None
    phase = str(previous.get("phase") or "").strip()
    if previous.get("terminal") is True or phase in RUN_STATE_TERMINAL_PHASES:
        return None
    heartbeat_value = previous.get("last_heartbeat_at") or previous.get(
        "heartbeat_at"
    )
    if heartbeat_value is None:
        return {
            "classification": "stale_nonterminal_run",
            "reason": "heartbeat_missing",
            "terminator": "unknown",
            "run_id": previous.get("run_id"),
            "phase": phase or None,
            "last_heartbeat_at": None,
        }
    try:
        heartbeat_at = _parse_run_state_timestamp(
            heartbeat_value,
            "previous_run_last_heartbeat_at",
        )
    except ValueError:
        return {
            "classification": "stale_nonterminal_run",
            "reason": "heartbeat_invalid",
            "terminator": "unknown",
            "run_id": previous.get("run_id"),
            "phase": phase or None,
            "last_heartbeat_at": heartbeat_value,
        }
    observed = observed_at.astimezone(timezone.utc)
    age_seconds = int((observed - heartbeat_at).total_seconds())
    if age_seconds < RUN_STATE_STALE_AFTER_SECONDS:
        return None
    return {
        "classification": "stale_nonterminal_run",
        "reason": "heartbeat_expired",
        "terminator": "unknown",
        "run_id": previous.get("run_id"),
        "phase": phase or None,
        "last_heartbeat_at": heartbeat_at.isoformat(),
        "observed_at": observed.isoformat(),
        "age_seconds": age_seconds,
        "stale_after_seconds": RUN_STATE_STALE_AFTER_SECONDS,
    }


class _PaperRunState:
    """Persist wrapper lifecycle state separately from the Paper status schema."""

    def __init__(self, operation_root: Path) -> None:
        self.operation_root = _resolved(operation_root)
        self.root = _run_state_root(self.operation_root)
        self.latest_path = self.root / "latest.json"
        self.receipt_root = self.root / "receipts"
        self.run_id = uuid4().hex
        self.state: dict[str, object] = {}

    def _write_event(self, event: str, *, state: Mapping[str, object]) -> None:
        self.receipt_root.mkdir(parents=True, exist_ok=True)
        body = {"event": event, **dict(state)}
        encoded = (_canonical_json(body) + "\n").encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()[:20]
        event_name = {
            "waiting_for_taipei_cutoff": "waiting",
            "stale_previous_run": "stale",
        }.get(event, event)
        # Keep the immutable receipt name short enough for Windows Task
        # Scheduler workspaces whose temporary/test roots may already be long.
        target = self.receipt_root / f"{event_name}_{self.run_id[:12]}_{digest[:12]}.json"
        temporary = self.receipt_root / (
            f".{event_name}_{self.run_id[:12]}_{uuid4().hex[:12]}.tmp"
        )

        def _mark_existing() -> None:
            try:
                existing = target.read_bytes()
            except OSError as error:
                self._mark_event_write(
                    event,
                    "incomplete",
                    error=f"{type(error).__name__}:{error}",
                )
            else:
                self._mark_event_write(
                    event,
                    "already_present_verified"
                    if existing == encoded
                    else "conflict",
                    error=(
                        None
                        if existing == encoded
                        else "immutable_event_receipt_bytes_mismatch"
                    ),
                )

        try:
            if target.exists():
                _mark_existing()
                return

            # 絕不直接寫入 immutable final path。partial stream 或 fsync 中斷
            # 只能留下可丟棄的暫存檔，讓後續 retry 以 create-only 發布同一份 bytes。
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # hard-link publish 是 create-only，因此不會取代競爭 instance
                # 已經發布的 receipt。
                os.link(temporary, target)
            except FileExistsError:
                _mark_existing()
            else:
                published = target.read_bytes()
                if published != encoded:
                    self._mark_event_write(
                        event,
                        "conflict",
                        error="immutable_event_receipt_readback_mismatch",
                    )
                else:
                    self._mark_event_write(event, "persisted")
        except OSError as error:
            self._mark_event_write(
                event,
                "incomplete",
                error=f"{type(error).__name__}:{error}",
            )
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                # cleanup 失敗會在下一輪保留為可觀測狀態；不可因此移除或
                # 覆寫 immutable final receipt。
                pass

    def _mark_event_write(
        self,
        event: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        self.state["last_event"] = event
        self.state["event_write_status"] = status
        self.state.pop("pending_event", None)
        if error is None:
            self.state.pop("event_write_error", None)
        else:
            self.state["event_write_error"] = error
        try:
            _atomic_write_json(self.latest_path, self.state)
        except OSError:
            # The event status is best-effort diagnostics.  The earlier
            # lifecycle write remains the durable evidence if this follow-up
            # status write is itself interrupted.
            return

    def _persist(self, *, event: str | None = None) -> None:
        if event is not None:
            self.state["pending_event"] = event
            self.state["event_write_status"] = "pending"
        _atomic_write_json(self.latest_path, self.state)
        if event is not None:
            self._write_event(event, state=self.state)

    def start(self, *, observed_at: datetime) -> None:
        observed = observed_at.astimezone(timezone.utc)
        previous = _read_json_object(self.latest_path)
        stale = _stale_previous_run_state(previous, observed_at=observed)
        self.state = {
            "schema_version": RUN_STATE_SCHEMA_VERSION,
            "task": "baldr-paper-portfolio-daily",
            "run_id": self.run_id,
            "status": "running",
            "phase": "starting",
            "terminal": False,
            "started_at": observed.isoformat(),
            "last_heartbeat_at": observed.isoformat(),
            "heartbeat_interval_seconds": RUN_STATE_HEARTBEAT_INTERVAL_SECONDS,
            "stale_after_seconds": RUN_STATE_STALE_AFTER_SECONDS,
            "operation_root": str(self.operation_root),
            "latest_status_path": str(
                self.operation_root
                / "scheduled"
                / "paper_portfolio_isolated"
                / "latest_status.json"
            ),
            "candidate_only": True,
            "writes_D_source": False,
            "writes_market_database": False,
            "formal_credit": False,
            "broker_execution": False,
            "terminator": "unknown",
        }
        if stale is not None:
            self.state["previous_run"] = stale
        self._persist(event="starting")
        if stale is not None:
            self._write_event("stale_previous_run", state=stale)

    def heartbeat(self, *, observed_at: datetime, phase: str) -> None:
        if self.state.get("terminal") is True:
            return
        observed = observed_at.astimezone(timezone.utc)
        previous_phase = str(self.state.get("phase") or "")
        heartbeat_count = self.state.get("heartbeat_count", 0)
        if isinstance(heartbeat_count, bool) or not isinstance(heartbeat_count, int) or heartbeat_count < 0:
            raise ValueError("invalid run-state heartbeat_count")
        self.state.update(
            {
                "status": "running",
                "phase": phase,
                "last_heartbeat_at": observed.isoformat(),
                "heartbeat_count": heartbeat_count + 1,
            }
        )
        self._persist(event=phase if phase != previous_phase else None)

    def transition(
        self,
        *,
        phase: str,
        observed_at: datetime,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if self.state.get("terminal") is True:
            return
        observed = observed_at.astimezone(timezone.utc)
        self.state.update(
            {
                "status": "running",
                "phase": phase,
                "last_heartbeat_at": observed.isoformat(),
            }
        )
        if details is not None:
            self.state.update(dict(details))
        self._persist(event=phase)

    def finish(
        self,
        *,
        observed_at: datetime,
        result: Mapping[str, object],
    ) -> None:
        observed = observed_at.astimezone(timezone.utc)
        self.state.update(
            {
                "status": "terminal",
                "phase": "terminal",
                "terminal": True,
                "terminal_status": str(result.get("status") or "unknown"),
                "finished_at": observed.isoformat(),
                "last_heartbeat_at": observed.isoformat(),
                "result_decision_date": result.get("decision_date"),
                "result_snapshot_id": result.get("snapshot_id"),
            }
        )
        self._persist(event="terminal")

    def fail(self, *, observed_at: datetime, error: BaseException) -> None:
        observed = observed_at.astimezone(timezone.utc)
        self.state.update(
            {
                "status": "terminal",
                "phase": "terminal",
                "terminal": True,
                "terminal_status": "wrapper_exception",
                "error_type": type(error).__name__,
                "error": str(error),
                "finished_at": observed.isoformat(),
                "last_heartbeat_at": observed.isoformat(),
            }
        )
        self._persist(event="terminal")


def _scope_paths() -> dict[str, Path]:
    return {
        "repository_root": _resolved(ROOT),
        "repository_output": _resolved(ROOT / "output"),
        "operation_root": _resolved(OPERATIONAL_ROOT),
        "paper_state_root": _resolved(PAPER_STATE_ROOT),
        "state_db": _resolved(STATE_DB),
        "state_seed_manifest": _resolved(STATE_SEED_MANIFEST),
        "ledger_db": _resolved(LEDGER_DB),
        "source_data_root": _resolved(DEFAULT_DATA_ROOT),
        "source_state_db": _resolved(SOURCE_STATE_DB),
        "source_baseline": _resolved(SOURCE_BASELINE_PATH),
        "market_db": _resolved(MARKET_DB),
    }


def _validate_scope() -> dict[str, Path]:
    paths = _scope_paths()
    repository_output = paths["repository_output"]
    operation = paths["operation_root"]
    if repository_output == paths["repository_root"]:
        raise RuntimeError("isolated Paper repository output cannot equal repository root")
    if operation == repository_output or not _is_under(operation, repository_output):
        raise RuntimeError("isolated Paper operation root escaped repository output")
    # _resolved 只容許根 output junction；operation 下層的 alias 會在解析前拒絕。
    writable = (
        ("operation_root", operation),
        ("paper_state_root", paths["paper_state_root"]),
        ("state_db", paths["state_db"]),
        ("state_seed_manifest", paths["state_seed_manifest"]),
    )
    for name, target in writable:
        if not _is_under(target, operation):
            raise RuntimeError(f"isolated Paper write target escaped operation:{name}")
        if _is_under(target, paths["source_data_root"]):
            raise RuntimeError(f"isolated Paper write target overlaps D source:{name}")
    if paths["source_state_db"] == paths["state_db"]:
        raise RuntimeError("isolated Paper state source and target are identical")
    for name in ("source_state_db", "source_baseline", "market_db"):
        source = paths[name]
        if source.expanduser().is_symlink():
            raise RuntimeError(f"isolated Paper source must not be a symlink:{name}")
        if not _is_under(source, paths["source_data_root"]):
            raise RuntimeError(f"isolated Paper source escaped D data root:{name}")
        if _is_under(source, operation):
            raise RuntimeError(f"isolated Paper source overlaps writer operation:{name}")
    if not paths["source_baseline"].is_file() or paths["source_baseline"].is_symlink():
        raise RuntimeError(f"isolated Paper baseline source is unavailable:{paths['source_baseline']}")
    if not paths["market_db"].is_file() or paths["market_db"].is_symlink():
        raise RuntimeError(f"isolated Paper market source is unavailable:{paths['market_db']}")
    return paths


def _observe_baseline(path: Path) -> dict[str, object]:
    """以唯讀檔案 hash 保存 public runner 所需 baseline 的來源證據。"""

    resolved = _resolved(path)
    before = _file_hash(resolved)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("isolated Paper baseline source is not an object")
    after = _file_hash(resolved)
    if before != after:
        raise RuntimeError("isolated Paper baseline changed during read")
    return {
        "path": str(resolved),
        "read_mode": "read_only_file",
        "file_sha256": before,
        "source_result_id": payload.get("source_result_id"),
        "decision_date": payload.get("decision_date"),
    }


def _observe_market(path: Path) -> dict[str, object]:
    """只驗證市場 SQLite 可以 query-only 開啟；不向其寫入。"""

    resolved = _resolved(path)
    before = _file_hash(resolved)
    try:
        with sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "daily_prices" not in tables:
                raise RuntimeError("isolated Paper market source lacks daily_prices")
    except sqlite3.Error as error:
        raise RuntimeError(f"isolated Paper market source read failed:{type(error).__name__}") from error
    after = _file_hash(resolved)
    if before != after:
        raise RuntimeError("isolated Paper market source changed during read")
    return {
        "path": str(resolved),
        "read_mode": "sqlite_uri_mode_ro_and_query_only",
        "file_sha256": before,
        "required_tables": ["daily_prices"],
    }


def _scope_manifest(paths: Mapping[str, Path]) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "scope_id": "research-paper-preopen-repository-state-v1",
        "source": {
            "state_db": str(paths["source_state_db"]),
            "baseline": str(paths["source_baseline"]),
            "market_db": str(paths["market_db"]),
            "read_mode": "D_read_only_seed_then_repository_state",
        },
        "repository_state": {
            "state_db": str(paths["state_db"]),
            "seed_manifest": str(paths["state_seed_manifest"]),
            "operation_root": str(paths["operation_root"]),
            "writer": "scripts.run_paper_portfolio_daily.run",
            "ledger_read_mode": "sqlite_mode_ro_query_only",
        },
        "safety": {
            "writes_D_source": False,
            "writes_market_database": False,
            "formal_credit": False,
            "broker_execution": False,
            "training_started": False,
            "historical_backfill_claimed": False,
        },
    }
    return body


def _write_or_verify_scope_manifest(paths: Mapping[str, Path]) -> tuple[Path, str]:
    manifest_path = paths["operation_root"] / "paper_portfolio_scope_manifest.json"
    body = _scope_manifest(paths)
    payload = {**body, "content_sha256": _payload_hash(body)}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("isolated Paper preopen scope manifest is unreadable") from error
        if not isinstance(existing, Mapping):
            raise RuntimeError("isolated Paper preopen scope manifest is not an object")
        existing_body = dict(existing)
        declared = existing_body.pop("content_sha256", None)
        if declared != _payload_hash(existing_body) or existing_body != body:
            raise RuntimeError("isolated Paper preopen scope manifest changed")
    else:
        _atomic_write_json(manifest_path, payload)
    return manifest_path, _file_hash(manifest_path)


def _blocked_result(
    *,
    paths: Mapping[str, Path] | None,
    observed: datetime,
    blockers: list[str],
) -> dict[str, object]:
    operation = None if paths is None else paths.get("operation_root")
    result: dict[str, object] = {
        "schema_version": PAPER_DAILY_STATUS_SCHEMA_VERSION,
        "isolated_scope_schema_version": SCHEMA_VERSION,
        "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "status": "blocked",
        "blockers": blockers,
        "candidate_only": True,
        "formal_credit": False,
        "writes_D_source": False,
        "writes_market_database": False,
        "broker_execution": False,
        "historical_backfill_claimed": False,
        "state_db": None if paths is None else str(paths["state_db"]),
        "source_state_db": None if paths is None else str(paths["source_state_db"]),
    }
    if operation is not None:
        result["status_path"] = str(operation / "scheduled" / "paper_portfolio_isolated" / "latest_status.json")
    return result


def _taipei_cutoff_for(value: datetime) -> datetime:
    """回傳 value 所在台北自然日的 08:30 cutoff。"""

    taipei = value.astimezone(TAIPEI)
    return datetime.combine(taipei.date(), TAIPEI_PREOPEN_CUTOFF, tzinfo=TAIPEI)


def _waiting_for_taipei_cutoff(
    *,
    observed: datetime,
) -> dict[str, object]:
    """在自然 cutoff 前只回報等待，不開啟任何 D 或 repository SQLite。"""

    taipei = observed.astimezone(TAIPEI)
    cutoff = _taipei_cutoff_for(observed)
    return {
        "schema_version": PAPER_DAILY_STATUS_SCHEMA_VERSION,
        "isolated_scope_schema_version": SCHEMA_VERSION,
        "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "taipei_now": taipei.isoformat(),
        "taipei_cutoff": cutoff.isoformat(),
        "status": "waiting_for_taipei_cutoff",
        "blockers": ["taipei_preopen_cutoff_not_reached"],
        "candidate_only": True,
        "formal_credit": False,
        "writes_D_source": False,
        "writes_market_database": False,
        "broker_execution": False,
        "historical_backfill_claimed": False,
        "state_db": str(_resolved(STATE_DB)),
        "source_state_db": str(_resolved(SOURCE_STATE_DB)),
        "guard": "taipei_08:30_natural_clock",
    }


def _wait_until_taipei_cutoff(
    *,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    heartbeat_fn: Callable[[datetime], None] | None = None,
) -> datetime:
    """在排程的早期喚醒後等待真實台北 08:30，再回傳可用時間。

    排程設在 timezone-aware Asia/Taipei 08:25（+08:00）。準時啟動時只等待
    五分鐘到 08:30 cutoff；此 guard 只在真實 cutoff 後讀取來源；
    測試可注入 clock/sleep，正式入口使用實際系統時間。
    """

    clock = now_fn or (lambda: datetime.now(TAIPEI))
    sleeper = sleep_fn or time_module.sleep
    while True:
        current_raw = clock()
        if current_raw.tzinfo is None or current_raw.utcoffset() is None:
            raise ValueError("scheduled Taipei clock must include timezone")
        current = current_raw.astimezone(TAIPEI)
        if heartbeat_fn is not None:
            heartbeat_fn(current)
        cutoff = _taipei_cutoff_for(current)
        if current >= cutoff:
            return current
        remaining = (cutoff - current).total_seconds()
        # 每次最多等待一分鐘，讓作業系統時鐘跳變及終止訊號能被觀察。
        sleeper(min(max(remaining, 0.1), 60.0))


def run_isolated(
    *,
    now: datetime | None = None,
    decision_at: datetime | None = None,
    calendar: OfficialTradingCalendar | None = None,
) -> dict[str, object]:
    """執行一次自然時間盤前 snapshot；``now`` 僅供隔離測試傳入。"""

    observed_raw = now or datetime.now(timezone.utc)
    if observed_raw.tzinfo is None or observed_raw.utcoffset() is None:
        raise ValueError("now must include timezone")
    observed = observed_raw.astimezone(timezone.utc)
    if observed.astimezone(TAIPEI) < _taipei_cutoff_for(observed):
        return _waiting_for_taipei_cutoff(observed=observed)
    paths: dict[str, Path] | None = None
    try:
        paths = _validate_scope()
        manifest_path, manifest_hash = _write_or_verify_scope_manifest(paths)
        seed = ensure_repo_state_from_readonly_source(
            source=paths["source_state_db"],
            target=paths["state_db"],
            manifest_path=paths["state_seed_manifest"],
            observed_at=observed,
        )
        baseline_observation = _observe_baseline(paths["source_baseline"])
        market_observation = _observe_market(paths["market_db"])
        resolved_decision = decision_at or _latest_reached_decision_at(
            None,
            now=observed.astimezone(TAIPEI),
        )
        calendar_service = calendar or OfficialTradingCalendar(
            db_path=paths["market_db"],
            calendar_cache_path=CALENDAR_CACHE_ROOT,
            temporary_closure_path=CALENDAR_CACHE_ROOT,
        )
        decision_bound_calendar = _bind_calendar_to_decision(
            calendar_service,
            decision_at=resolved_decision,
        )
        result = run_paper_portfolio_daily(
            baseline_path=paths["source_baseline"],
            state_db=paths["state_db"],
            market_db=paths["market_db"],
            output_root=paths["operation_root"],
            decision_at=resolved_decision,
            calendar=decision_bound_calendar,  # type: ignore[arg-type]
            now=observed.astimezone(TAIPEI),
            ledger_db=paths["ledger_db"],
        )
        state_head = publish_repo_state_head(
            target=paths["state_db"],
            manifest_path=paths["state_seed_manifest"],
            observed_at=observed,
        )
        preopen_coverage: dict[str, object] | None = None
        if result.get("status") == "passed":
            preopen_coverage = {
                "schema_version": "paper-preopen-coverage.v1",
                "status": "passed",
                "portfolio_id": result.get("portfolio_id"),
                "snapshot_id": result.get("snapshot_id"),
                "decision_date": result.get("decision_date"),
                "snapshot_relation": (
                    "current_decision_date_producer_receipt"
                ),
                "snapshot_appended": result.get("snapshot_appended"),
                "snapshot_semantics": result.get("snapshot_semantics"),
                "trading_calendar_validated": result.get(
                    "trading_calendar_validated"
                ),
                "trading_calendar_is_open": result.get(
                    "trading_calendar_is_open"
                ),
                "state_db": str(paths["state_db"]),
                "ledger_db": str(paths["ledger_db"]),
                "state_head": state_head,
                "write_scope": "repository_paper_snapshot_append_only",
                "writer": "scripts.run_paper_portfolio_daily.run",
            }
            write_contract = result.get("paper_state_write_contract")
            if not isinstance(write_contract, Mapping):
                raise RuntimeError(
                    "paper preopen writer did not publish its write contract"
                )
        combined: dict[str, object] = {
            **result,
            # The outer receipt is the canonical Paper daily-status contract
            # consumed by position-health and evidence.  The isolated custody
            # envelope retains its own version in a separate field so the
            # consumer contract is not silently replaced by wrapper metadata.
            "schema_version": PAPER_DAILY_STATUS_SCHEMA_VERSION,
            "isolated_scope_schema_version": SCHEMA_VERSION,
            "producer": "scripts.scheduled.run_paper_portfolio_daily_isolated",
            "candidate_only": True,
            "formal_credit": False,
            "writes_D_source": False,
            "writes_market_database": False,
            "broker_execution": False,
            "historical_backfill_claimed": False,
            "isolated_scope": {
                "scope_manifest_path": str(manifest_path),
                "scope_manifest_file_sha256": manifest_hash,
                "source_state_db": str(paths["source_state_db"]),
                "source_state_read_mode": "sqlite_uri_mode_ro_and_query_only",
                "repository_state_db": str(paths["state_db"]),
                "repository_state_scope": "repository_output_only",
                "state_seed": seed,
                "state_head": state_head,
                "baseline": baseline_observation,
                "market": market_observation,
                "ledger_db": str(paths["ledger_db"]),
                "formal_credit": False,
                "writes_D_source": False,
                "writes_market_database": False,
                "broker_execution": False,
            },
        }
        if preopen_coverage is not None:
            combined["preopen_coverage"] = preopen_coverage
            combined["snapshot_relation"] = preopen_coverage["snapshot_relation"]
        _atomic_write_json(
            paths["operation_root"]
            / "scheduled"
            / "paper_portfolio_isolated"
            / "latest_status.json",
            combined,
        )
        return combined
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        blocked = _blocked_result(
            paths=paths,
            observed=observed,
            blockers=[f"isolated_paper_preopen_failed:{type(error).__name__}:{error}"],
        )
        if paths is not None:
            _atomic_write_json(
                paths["operation_root"]
                / "scheduled"
                / "paper_portfolio_isolated"
                / "latest_status.json",
                blocked,
            )
        return blocked


def _print_json(value: Mapping[str, object]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        sys.stdout.write(encoded.decode())
    except UnicodeEncodeError:
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is None:
            sys.stdout.write(encoded.decode("utf-8"))
        else:
            buffer.write(encoded)
            buffer.flush()


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__)
    # 只保留受控測試／人工診斷所需的明確 cutoff；scheduled cmd 不傳入，
    # 因此 production 永遠使用此刻已到達的 Taipei 08:30。
    parser.add_argument("--decision-at", default=None)
    args = parser.parse_args(argv)
    explicit_decision = None
    if args.decision_at is not None:
        explicit_decision = datetime.fromisoformat(str(args.decision_at).replace("Z", "+00:00"))
    # Task Scheduler uses an explicit Asia/Taipei +08:00 08:25 boundary.
    # This waits only for the real 08:30 clock, never selecting yesterday as
    # today's input when a task starts before the cutoff.
    run_state = _PaperRunState(OPERATIONAL_ROOT)
    run_state.start(observed_at=datetime.now(timezone.utc))
    try:
        reached_taipei = _wait_until_taipei_cutoff(
            heartbeat_fn=lambda current: run_state.heartbeat(
                observed_at=current,
                phase="waiting_for_taipei_cutoff",
            )
        )
        run_state.transition(
            phase="cutoff_reached",
            observed_at=reached_taipei,
            details={"taipei_cutoff": _taipei_cutoff_for(reached_taipei).isoformat()},
        )
        run_state.transition(
            phase="producer_starting",
            observed_at=datetime.now(timezone.utc),
        )
        result = run_isolated(
            now=reached_taipei,
            decision_at=explicit_decision,
        )
        run_state.transition(
            phase="producer_completed",
            observed_at=datetime.now(timezone.utc),
            details={"producer_status": result.get("status")},
        )
        run_state.finish(
            observed_at=datetime.now(timezone.utc),
            result=result,
        )
    except BaseException as error:
        run_state.fail(observed_at=datetime.now(timezone.utc), error=error)
        raise
    _print_json(result)
    return 0 if str(result.get("status")) in {
        "passed",
        "skipped_non_trading_day",
        "skipped_future_decision",
        "waiting_for_taipei_cutoff",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
