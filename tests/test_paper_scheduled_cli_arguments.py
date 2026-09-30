from __future__ import annotations

from types import ModuleType

import pytest

from scripts.scheduled import run_paper_event_source_capture_daily as event_capture
from scripts.scheduled import run_paper_execution_daily_isolated as eod_replay


@pytest.mark.parametrize(
    ("module", "runner_name"),
    [
        (event_capture, "run_capture"),
        (eod_replay, "run_isolated"),
    ],
    ids=["event-capture", "eod-replay"],
)
@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        (["--help"], 0),
        (["--unexpected-option"], 2),
    ],
    ids=["help", "unknown-option"],
)
def test_paper_scheduled_cli_arguments_exit_before_running_or_writing(
    module: ModuleType,
    runner_name: str,
    arguments: list[str],
    expected_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def runner_must_not_start() -> dict[str, object]:
        calls.append(runner_name)
        raise AssertionError("argument parsing must finish before the runtime starts")

    monkeypatch.setattr(module, runner_name, runner_must_not_start)

    with pytest.raises(SystemExit) as exit_info:
        module.main(arguments)

    assert exit_info.value.code == expected_code
    assert calls == []
    output = capsys.readouterr()
    if expected_code == 0:
        assert "usage:" in output.out
    else:
        assert "unrecognized arguments" in output.err
