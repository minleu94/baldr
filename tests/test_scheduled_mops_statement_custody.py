from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess

import pytest

from data_module.mops_ezsearch_statement_availability import MOPS_EZSEARCH_QUERY_URL
from tests.test_mops_success_response_custody import _Response, _response_payload
from scripts import fetch_mops_statement_availability as fetch_cli


def test_weekly_window_is_the_last_seven_complete_taipei_calendar_days() -> None:
    observed_at = datetime.fromisoformat("2026-10-04T10:00:00+00:00")

    start_date, end_date = fetch_cli._last_complete_taipei_7_day_window(observed_at)

    assert (start_date, end_date) == (date(2026, 9, 27), date(2026, 10, 3))
    assert (end_date - start_date).days == 6
    with pytest.raises(ValueError, match="timezone-aware"):
        fetch_cli._last_complete_taipei_7_day_window(datetime(2026, 10, 4))


@pytest.mark.parametrize(
    "override",
    [
        ["--start-date", "2026-09-20"],
        ["--end-date", "2026-09-27"],
        ["--markets", "sii"],
        ["--items", "F26"],
        ["--output-root", "output/other"],
        ["--artifact-name", "other.json"],
        ["--mapping-name", "other.csv"],
        ["--timeout-seconds", "30"],
        ["--query-retries", "0"],
        ["--query-window-days", "7"],
        ["--capture-success-response-custody"],
    ],
)
def test_weekly_preset_rejects_query_and_output_overrides(
    override: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network() -> None:
        raise AssertionError("override rejection must happen before any HTTP session is created")

    def deny_setup(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("override rejection must precede output-root/config setup")

    monkeypatch.setattr(fetch_cli, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_cli.requests, "Session", deny_network)
    monkeypatch.setattr(fetch_cli, "validate_development_output_root", deny_setup)
    with pytest.raises(SystemExit) as captured:
        fetch_cli.main(["--last-complete-taipei-7-days", *override])

    assert captured.value.code == 2
    assert not (tmp_path / "output" / "research" / "mops_statement_availability").exists()


@pytest.mark.parametrize(
    ("transport_failure_index", "expected_exit", "expected_status", "expected_failures"),
    [
        (None, 0, "official_no_data", 0),
        (5, 3, "partial_failure", 1),
    ],
)
def test_weekly_preset_makes_exact_six_fixed_bounded_queries_and_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transport_failure_index: int | None,
    expected_exit: int,
    expected_status: str,
    expected_failures: int,
) -> None:
    class _Session:
        def __init__(self) -> None:
            self.responses = [
                _Response(
                    _response_payload(status="fail"),
                    status_code=(503 if index == transport_failure_index else 200),
                )
                for index in range(6)
            ]
            self.calls: list[dict[str, object]] = []

        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, **kwargs: object) -> _Response:
            self.calls.append({"url": url, **kwargs})
            return self.responses.pop(0)

    session = _Session()
    monkeypatch.setattr(fetch_cli, "ROOT", tmp_path)
    monkeypatch.setattr(
        fetch_cli,
        "validate_development_output_root",
        lambda requested, **_kwargs: Path(requested).resolve(),
    )
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "guard-data-root"))
    monkeypatch.setattr(fetch_cli.requests, "Session", lambda: session)

    exit_code = fetch_cli.main(["--last-complete-taipei-7-days"])

    assert exit_code == expected_exit
    assert len(session.calls) == 6
    assert [call["url"] for call in session.calls] == [MOPS_EZSEARCH_QUERY_URL] * 6
    assert all(call["allow_redirects"] is False for call in session.calls)
    assert all(call["timeout"] == 30 for call in session.calls)
    assert [
        (call["data"]["TYPEK"], call["data"]["PRO_ITEM"])
        for call in session.calls
    ] == [
        (market, item)
        for market in ("sii", "otc")
        for item in ("F26", "F27", "F28")
    ]
    starts = {call["data"]["SDATE"] for call in session.calls}
    ends = {call["data"]["EDATE"] for call in session.calls}
    assert len(starts) == len(ends) == 1

    output = json.loads(capsys.readouterr().out)
    artifact_path = Path(output["artifact_path"])
    run_root = artifact_path.parent
    assert run_root.parent == tmp_path / "output" / "research" / "mops_statement_availability"
    status = json.loads((run_root / "weekly_research_status.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (run_root / "raw_success_responses" / "capture_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    readback = json.loads(
        (run_root / "raw_success_responses" / "source_readback.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["status"] == expected_status
    assert status["query_count"] == 6
    assert status["run_id"] == run_root.name
    assert status["selected_start_date"] == receipt["selected_start_date"]
    assert status["selected_end_date"] == receipt["selected_end_date"]
    assert status["collection_started_at_utc"] == receipt["collection_started_at_utc"]
    assert status["collection_completed_at_utc"] == receipt["collection_completed_at_utc"]
    assert status["source_readback_status"] == "verified"
    assert not (tmp_path / "guard-data-root").exists()
    assert readback["status"] == "verified"
    assert receipt["query_count"] == 6
    assert receipt["component_count"] == 6 - expected_failures
    assert status["failed_query_count"] == expected_failures
    assert status["official_no_data_query_count"] == 6 - expected_failures
    assert receipt["failure_prefix_count"] == expected_failures
    assert (receipt["aggregate_failure_prefix_bytes"] > 0) is (expected_failures > 0)
    assert receipt["formal_oos_allowed"] is False
    assert receipt["formal_credit_authorized"] is False


def test_weekly_wrapper_preserves_core_result_and_defaults_research_hook_on() -> None:
    wrapper = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "scheduled"
        / "run_v2_2_weekly_collection.cmd"
    ).read_text(encoding="utf-8")
    core_call = wrapper.index("collect_v2_2_weekly_evidence.py")
    research_call = wrapper.index("fetch_mops_statement_availability.py")
    assert core_call < wrapper.index('if not "%CORE_EXIT%"=="0" exit /b %CORE_EXIT%') < research_call
    assert 'if not defined BALDR_ENABLE_MOPS_STATEMENT_CUSTODY set "BALDR_ENABLE_MOPS_STATEMENT_CUSTODY=1"' in wrapper
    assert 'if /I "%BALDR_ENABLE_MOPS_STATEMENT_CUSTODY%"=="0" exit /b %CORE_EXIT%' in wrapper
    assert "--last-complete-taipei-7-days" in wrapper
    assert wrapper.rstrip().endswith("exit /b %CORE_EXIT%")


@pytest.mark.parametrize(
    ("core_exit", "research_exit", "capture_enabled", "expected_exit", "expected_calls"),
    [
        (5, 7, None, 5, 1),
        (0, 7, None, 0, 2),
        (0, 7, "0", 0, 1),
    ],
)
def test_weekly_wrapper_keeps_core_exit_when_child_fails_and_short_circuits(
    tmp_path: Path,
    core_exit: int,
    research_exit: int,
    capture_enabled: str | None,
    expected_exit: int,
    expected_calls: int,
) -> None:
    repo_root = tmp_path / "repo"
    wrapper_path = repo_root / "scripts" / "scheduled" / "run_v2_2_weekly_collection.cmd"
    wrapper_path.parent.mkdir(parents=True)
    wrapper_path.write_text(
        (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "scheduled"
            / "run_v2_2_weekly_collection.cmd"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    log_path = tmp_path / "python-calls.log"
    (fake_bin / "python.cmd").write_text(
        "@echo off\r\n"
        ">>\"%FAKE_PYTHON_LOG%\" echo %*\r\n"
        "if /I \"%~1\"==\"scripts\\collect_v2_2_weekly_evidence.py\" exit /b %FAKE_CORE_EXIT%\r\n"
        "if /I \"%~1\"==\"scripts\\fetch_mops_statement_availability.py\" exit /b %FAKE_RESEARCH_EXIT%\r\n"
        "exit /b 99\r\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
    environment["FAKE_PYTHON_LOG"] = str(log_path)
    environment["FAKE_CORE_EXIT"] = str(core_exit)
    environment["FAKE_RESEARCH_EXIT"] = str(research_exit)
    if capture_enabled is not None:
        environment["BALDR_ENABLE_MOPS_STATEMENT_CUSTODY"] = capture_enabled
    else:
        environment.pop("BALDR_ENABLE_MOPS_STATEMENT_CUSTODY", None)

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "scripts\\scheduled\\run_v2_2_weekly_collection.cmd"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_exit, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert len(calls) == expected_calls
    assert "collect_v2_2_weekly_evidence.py" in calls[0]
    if expected_calls == 1:
        assert "fetch_mops_statement_availability.py" not in calls[0]
    else:
        assert "fetch_mops_statement_availability.py" in calls[1]
