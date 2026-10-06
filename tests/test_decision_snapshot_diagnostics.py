"""快照診斷須在超時前保存，且不可改保存／取消契約。"""
from __future__ import annotations

from io import StringIO
import json
import sys

import pytest

from app_module.decision_snapshot_diagnostics import (
    MAX_EVENTS, PREFIX, SCHEMA, snapshot_diagnostics, snapshot_stage,
    summarize_snapshot_diagnostics,
)
from scripts.scheduled import run_scheduled_decision_evidence_capture as runner


def test_failed_nested_stage_keeps_original_exception_without_private_message():
    stream = StringIO()
    error = ValueError("私人持倉與來源參數不可記錄")
    with pytest.raises(ValueError) as caught, snapshot_diagnostics(enabled=True, stream=stream):
        with snapshot_stage("snapshot"), snapshot_stage("market_frame_rows_sql"):
            raise error
    assert caught.value is error
    assert "私人" not in stream.getvalue()
    parsed = summarize_snapshot_diagnostics(stream.getvalue())
    assert parsed["unfinished_stages"] == []
    assert [e["stage"] for e in parsed["events"]] == [
        "snapshot", "market_frame_rows_sql", "market_frame_rows_sql", "snapshot",
    ]
    assert parsed["events"][2]["error_type"] == "ValueError"
    assert all(type(e["elapsed_ms"]) is int for e in parsed["events"])


def test_disabled_diagnostics_and_failed_sink_do_not_change_result():
    stream = StringIO()
    with snapshot_diagnostics(enabled=False, stream=stream), snapshot_stage("save"):
        value = "原結果"
    assert value == "原結果" and not stream.getvalue()
    stream.close()
    with snapshot_diagnostics(enabled=True, stream=stream), snapshot_stage("save"):
        value = "仍可完成"
    assert value == "仍可完成"


@pytest.mark.parametrize("bad", [
    {"stage": {"secret": "不可帶入"}}, {"stage": "private_account"},
    {"state": []}, {"elapsed_ms": True}, {"elapsed_ms": -1},
    {"schema": "other"},
])
def test_parser_rejects_untrusted_schema_without_raising(bad):
    event = {"schema": SCHEMA, "stage": "snapshot", "state": "started", "elapsed_ms": 0}
    event.update(bad)
    text = PREFIX + json.dumps(event)
    assert summarize_snapshot_diagnostics(text)["events"] == []


def test_parser_whitelists_fields_and_bounds_event_count():
    event = {"schema": SCHEMA, "stage": "save", "state": "completed", "elapsed_ms": 4,
             "portfolio": "secret", "error_type": "私人 內容"}
    parsed = summarize_snapshot_diagnostics((PREFIX + json.dumps(event) + "\n") * (MAX_EVENTS + 2))
    assert len(parsed["events"]) == MAX_EVENTS
    assert parsed["events"][0] == {"stage": "save", "state": "completed", "elapsed_ms": 4}


def test_real_child_timeout_retains_flushed_stage_and_unknown_write_state():
    code = (
        "from app_module.decision_snapshot_diagnostics import snapshot_diagnostics,snapshot_stage; "
        "import time\n"
        "with snapshot_diagnostics(enabled=True), snapshot_stage('broker_events'):\n"
        " time.sleep(3)\n"
    )
    result = runner._run_json_cli([sys.executable, "-c", code], timeout_seconds=1)
    step, failures = runner._snapshot_step(result)
    assert result.timed_out is True and result.returncode is None
    assert step["saved"] is None
    assert failures == ["snapshot_cli_timeout", "snapshot_json_invalid"]
    assert step["stage_diagnostics"]["unfinished_stages"] == ["broker_events"]
    assert PREFIX.encode() in result.stderr_artifact
