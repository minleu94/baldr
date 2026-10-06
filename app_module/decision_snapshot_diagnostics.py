"""快照非私人階段診斷；不改保存 payload 或來源時間。

啟用時逐筆 flush 至 stderr，讓子程序超時前的進度仍進入原 artifact。
只輸出固定 stage、整數耗時與例外類型，不輸出資料或例外訊息。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import sys
from time import monotonic_ns
from typing import Any, Callable, Iterator, TextIO, TypeVar, cast

PREFIX = "BALDR_SNAPSHOT_STAGE "
SCHEMA = "decision-snapshot-stage.v1"
MAX_EVENTS = 160
STAGES = frozenset({
    "config", "composition", "snapshot", "serialize", "repository", "save", "readback",
    "market_regime", "market_breadth", "sector_rotation",
    "relative_strength_liquidity", "watchlist_triggers", "portfolio_alerts",
    "risk_prompts", "market_data_visibility", "recommendations", "portfolio_ledger",
    "smart_money", "dashboard", "market_frame", "market_frame_dates_sql",
    "market_frame_rows_sql", "broker_events", "broker_events_group",
    "RegimeService", "PortfolioService", "WatchlistService", "BrokerFlowService",
    "MarketBreadthService", "IndustryStrengthService", "SectorRotationService",
    "RelativeStrengthLiquidityService", "WatchlistTriggerService",
    "PortfolioAlertService", "PortfolioChipService", "SmartMoneySemanticService",
})


class _Recorder:
    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.count = 0

    def emit(self, stage: str, state: str, elapsed_ms: int, error_type: str = "") -> None:
        if self.count >= MAX_EVENTS:
            return
        self.count += 1
        payload: dict[str, Any] = {"schema": SCHEMA, "sequence": self.count,
                                   "stage": stage, "state": state, "elapsed_ms": elapsed_ms}
        if error_type:
            payload["error_type"] = error_type[:80]
        try:
            self.stream.write(PREFIX + json.dumps(payload, separators=(",", ":")) + "\n")
            self.stream.flush()
        except (OSError, ValueError):
            # 診斷不可變更原 producer 的成功／失敗結果。
            pass


_RECORDER: ContextVar[_Recorder | None] = ContextVar("snapshot_stage_recorder", default=None)


@contextmanager
def snapshot_diagnostics(*, enabled: bool, stream: TextIO | None = None) -> Iterator[None]:
    token = _RECORDER.set(_Recorder(stream or sys.stderr) if enabled else None)
    try:
        yield
    finally:
        _RECORDER.reset(token)


@contextmanager
def snapshot_stage(stage: str) -> Iterator[None]:
    if stage not in STAGES:
        raise ValueError("unknown snapshot diagnostic stage")
    recorder = _RECORDER.get()
    if recorder is None:
        yield
        return
    start = monotonic_ns()
    recorder.emit(stage, "started", 0)
    try:
        yield
    except BaseException as exc:
        recorder.emit(stage, "failed", (monotonic_ns() - start) // 1_000_000, type(exc).__name__)
        raise
    else:
        recorder.emit(stage, "completed", (monotonic_ns() - start) // 1_000_000)


F = TypeVar("F", bound=Callable[..., Any])


def trace_snapshot_stage(stage: str) -> Callable[[F], F]:
    def decorate(fn: F) -> F:
        @wraps(fn)
        def traced(*args: Any, **kwargs: Any) -> Any:
            with snapshot_stage(stage):
                return fn(*args, **kwargs)
        return cast(F, traced)
    return decorate


def summarize_snapshot_diagnostics(stderr: str) -> dict[str, Any]:
    """只解析封閉 schema，不把任意 stderr／資料內容抄入診斷 DTO。"""
    events: list[dict[str, Any]] = []
    active: list[str] = []
    for line in stderr.splitlines():
        if not line.startswith(PREFIX) or len(line) > 1024 or len(events) >= MAX_EVENTS:
            continue
        try:
            item = json.loads(line[len(PREFIX):])
        except (ValueError, TypeError):
            continue
        if not isinstance(item, dict) or item.get("schema") != SCHEMA:
            continue
        stage, state, elapsed = item.get("stage"), item.get("state"), item.get("elapsed_ms")
        if not isinstance(stage, str) or not isinstance(state, str):
            continue
        if stage not in STAGES or state not in {"started", "completed", "failed"}:
            continue
        if type(elapsed) is not int or elapsed < 0:
            continue
        event = {"stage": stage, "state": state, "elapsed_ms": elapsed}
        error = item.get("error_type")
        if isinstance(error, str) and error.isidentifier() and len(error) <= 80:
            event["error_type"] = error
        events.append(event)
        if state == "started":
            active.append(stage)
        elif stage in active:
            active.remove(stage)
    return {"schema": SCHEMA, "events": events, "bounded": len(events) >= MAX_EVENTS,
            "unfinished_stages": active, "last_stage": events[-1]["stage"] if events else None}
