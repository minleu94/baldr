"""Paper 官方行情採集的根目錄相容入口。

公開函式沿用 data_module.paper_event_source_capture 的唯一實作；命令列
沿用 scripts.capture_paper_event_source，支援 symbols 與凍結推薦來源。
原始 HTTP bytes、失敗嘗試收據與 durable custody 均由正式模組處理。
"""

from pathlib import Path
from io import TextIOWrapper
import sys

from data_module.paper_event_source_capture import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    PAPER_EVENT_CAPTURE_BINDING_SCHEMA_VERSION,
    PAPER_EVENT_CAPTURE_DURABLE_SCHEMA_VERSION,
    PAPER_EVENT_CAPTURE_PRODUCER_VERSION,
    PaperEventSourceCaptureError,
    bind_paper_candidate_file_to_capture,
    bind_paper_execution_result_to_capture,
    capture_twse_session_open_prices,
    capture_twse_session_open_prices_for_recommendation,
    load_persisted_twse_event_source_capture,
    persist_twse_event_source_capture,
    resolve_persisted_twse_event_source_capture_for_recommendation,
)
from data_module.paper_event_source_capture import __all__ as _CAPTURE_EXPORTS
from scripts.capture_paper_event_source import main

ROOT = Path(__file__).resolve().parent
__all__ = [*_CAPTURE_EXPORTS, "main"]


if __name__ == "__main__":
    # Windows 重導向輸出時沿用 UTF-8，讓中文 help／JSON 收據可正常輸出。
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
