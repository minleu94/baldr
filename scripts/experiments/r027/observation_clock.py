"""R027 觀測時鐘：保存可重現的事件時序與原始作業系統讀值。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from typing import Any


_SCHEMA = "r027-observation-clock.v1"
_BASE_WALL_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)
_BASE_MONOTONIC_NS = 1_000_000_000
_WALL_STEP_MICROSECONDS = 1_000
_MONOTONIC_STEP_NS = 1_000_000
_CASE_INDEX = {
    "clean": 0,
    "same_input_rerun": 1,
    "partial": 2,
    "unchanged": 3,
    "cancel_resume": 4,
    "source_changed_during_run": 5,
    "failure_recovery": 6,
    "publication_failure_recovery": 7,
}


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class R027ObservationClock:
    """讓觀測事件使用可重現的時鐘，同時保留實際作業系統讀值。

    腳本時鐘只控制 R027 harness ``event`` observer 輸出的時間戳，不會替換
    產品時鐘、檔案 mtime、SQLite 或系統時鐘。每次 observer 呼叫都會在 worker
    receipt 記錄事件種類、呼叫序號，以及原始 OS wall/performance clock 讀值。
    """

    def __init__(self, *, mode: str, case: str) -> None:
        if mode not in {"system", "deterministic"}:
            raise ValueError(f"unsupported R027 observer clock mode: {mode}")
        if case not in _CASE_INDEX:
            raise ValueError(f"unsupported R027 observer clock case: {case}")
        self.mode = mode
        self.case = case
        self._calls: list[dict[str, Any]] = []
        self._case_offset = _CASE_INDEX[case]
        self._schedule = {
            "wall_base_utc": (
                _BASE_WALL_TIME + timedelta(seconds=self._case_offset * 3_600)
            ).isoformat(),
            "wall_step_microseconds": _WALL_STEP_MICROSECONDS,
            "monotonic_base_ns": (
                _BASE_MONOTONIC_NS + self._case_offset * 100_000_000
            ),
            "monotonic_step_ns": _MONOTONIC_STEP_NS,
        }
        self._schedule_sha256 = _canonical_sha256(
            {"schema": _SCHEMA, "case": case, **self._schedule}
        )

    def stamp(self, event_kind: str) -> dict[str, Any]:
        if not event_kind:
            raise ValueError("R027 observer event kind cannot be empty")
        sequence = len(self._calls)
        raw_wall_time_utc = datetime.now(timezone.utc).isoformat()
        raw_perf_counter_ns = time.perf_counter_ns()
        if self.mode == "deterministic":
            wall_time_utc = (
                _BASE_WALL_TIME
                + timedelta(
                    seconds=self._case_offset * 3_600,
                    microseconds=sequence * _WALL_STEP_MICROSECONDS,
                )
            ).isoformat()
            monotonic_ns = (
                _BASE_MONOTONIC_NS
                + self._case_offset * 100_000_000
                + sequence * _MONOTONIC_STEP_NS
            )
        else:
            wall_time_utc = raw_wall_time_utc
            monotonic_ns = raw_perf_counter_ns

        self._calls.append(
            {
                "sequence": sequence,
                "kind": event_kind,
                "raw_os_wall_time_utc": raw_wall_time_utc,
                "raw_os_perf_counter_ns": raw_perf_counter_ns,
            }
        )
        return {
            "observer_clock_sequence": sequence,
            "wall_time_utc": wall_time_utc,
            "monotonic_ns": monotonic_ns,
        }

    def receipt(self) -> dict[str, Any]:
        sequence = [
            {"sequence": item["sequence"], "kind": item["kind"]}
            for item in self._calls
        ]
        return {
            "schema": _SCHEMA,
            "mode": self.mode,
            "case": self.case,
            "schedule": dict(self._schedule),
            "schedule_sha256": self._schedule_sha256,
            "call_count": len(self._calls),
            "call_sequence": sequence,
            "call_sequence_sha256": _canonical_sha256(sequence),
            "raw_os_observation_count": len(self._calls),
            "raw_os_observations": [dict(item) for item in self._calls],
            "all_raw_os_observations_present": all(
                bool(item.get("raw_os_wall_time_utc"))
                and isinstance(item.get("raw_os_perf_counter_ns"), int)
                for item in self._calls
            ),
        }
