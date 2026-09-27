"""R027 新版驗收使用的來源呼叫階段紀錄器。"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
from pathlib import Path
import time
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "r027-logical-publication-phase-port.v1"


class LogicalPublicationPhasePort:
    """保存應用來源實際呼叫的邏輯 token 與原始 OS 時鐘觀測。"""

    def __init__(
        self,
        *,
        case: str,
        mode: str,
        phase: str,
        source_sha256: str,
    ) -> None:
        self._identity = {
            "case": case,
            "mode": mode,
            "scenario_phase": phase,
            "source_sha256": source_sha256,
        }
        self._events: list[dict[str, Any]] = []

    def __call__(self, phase_name: str) -> int:
        if not isinstance(phase_name, str) or not phase_name:
            raise ValueError("來源階段名稱必須是非空字串")

        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        if caller is not None and caller.f_code.co_name == "record_publication_phase":
            caller = caller.f_back
        caller_function = caller.f_code.co_name if caller else None
        caller_line = caller.f_lineno if caller else None
        try:
            caller_path = Path(caller.f_code.co_filename).resolve() if caller else None
            try:
                source_path = (
                    caller_path.relative_to(REPOSITORY_ROOT).as_posix()
                    if caller_path is not None
                    else None
                )
            except ValueError:
                source_path = caller_path.name if caller_path is not None else None
        finally:
            del caller
            del frame

        token = len(self._events) + 1
        self._events.append(
            {
                "sequence": token,
                "logical_token": token,
                "phase": phase_name,
                "source_callsite": {
                    "path": source_path,
                    "raw_path": str(caller_path) if caller_path is not None else None,
                    "function": caller_function,
                    "line": caller_line,
                    "source_sha256": self._identity["source_sha256"],
                },
                "raw_os_observations": {
                    "wall_time_utc": datetime.now(timezone.utc).isoformat(),
                    "perf_counter_ns": time.perf_counter_ns(),
                },
            }
        )
        return token

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            **self._identity,
            "call_count": len(self._events),
            "events": list(self._events),
        }
