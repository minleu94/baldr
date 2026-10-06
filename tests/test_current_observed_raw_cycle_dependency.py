from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from data_module.ml_storage_capacity import (
    acquire_heavy_chain_reservation,
    heavy_chain_lock_path,
    release_heavy_chain_reservation,
)
from scripts.scheduled import current_observed_raw_cycle_dependency as dependency
from scripts.scheduled import run_daily_recommendation_learning_pipeline as pipeline


DECISION_DATE = date(2026, 9, 30)
SOURCE_DATE = "2026-09-29"
RAW_RUN_ID = "raw-pit-20260930T124500000000Z-1234-aabbccddeeff"
NOW = datetime(2026, 9, 30, 21, 0, tzinfo=dependency.TAIPEI)


class _FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.tick = 0.0
        self.now = now

    def monotonic(self) -> float:
        return self.tick

    def sleep(self, seconds: float) -> None:
        self.tick += seconds
        self.now += timedelta(seconds=seconds)


def _write_json(path: Path, payload: dict[str, Any]) -> bytes:
    content = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


@pytest.fixture(autouse=True)
def _read_fixture_files_inside_the_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The native Windows ancestor-handle API is blocked by this sandbox."""

    def read_regular_file(path: Path, root: Path, *, max_bytes: int | None = None) -> bytes:
        if path.is_symlink():
            raise OSError("fixture symlink rejected")
        target = path.resolve(strict=True)
        target.relative_to(root.resolve(strict=True))
        if not target.is_file():
            raise OSError("fixture is not a regular file")
        content = target.read_bytes()
        if max_bytes is not None and len(content) > max_bytes:
            raise OSError("fixture exceeds bound")
        return content

    monkeypatch.setattr(dependency, "_read_regular_file_no_follow", read_regular_file)


def _terminal_fixture(
    research_root: Path,
    *,
    run_id: str = RAW_RUN_ID,
    source_date: str = SOURCE_DATE,
    status: str = "completed",
) -> tuple[Path, str]:
    terminal = research_root / "current_stock_cycles" / "2026-09-29" / run_id / "terminal_receipt.json"
    raw = _write_json(
        terminal,
        {
            "schema_version": "current-stock-research-cycle-terminal.v1",
            "status": status,
            "raw_run_id": run_id,
            "cycle_id": run_id,
            "source_date": source_date,
        },
    )
    return terminal, "sha256:" + hashlib.sha256(raw).hexdigest()


def _raw_status(
    output_root: Path,
    terminal: Path,
    terminal_sha: str,
    *,
    run_id: str = RAW_RUN_ID,
    status: str = "completed",
    cycle_status: str = "completed",
    source_date: str = SOURCE_DATE,
    started_at: str = "2026-09-30T20:45:00+08:00",
) -> dict[str, Any]:
    return {
        "schema_version": "ml-raw-pit-refresh-status.v1",
        "task": "baldr-ml-raw-pit-refresh-daily",
        "status": status,
        "output_root": str(output_root.resolve()),
        "run_id": run_id,
        "started_at": started_at,
        "latest_core_date": source_date,
        "source_date": source_date,
        "current_stock_research_cycle": {
            "status": cycle_status,
            "raw_run_id": run_id,
            "cycle_id": run_id,
            "source_date": source_date,
            "terminal_receipt_path": str(terminal.resolve()),
            "terminal_receipt_sha256": terminal_sha,
        },
    }


def _status_path(output_root: Path) -> Path:
    return output_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"


def _wait(
    output_root: Path,
    research_root: Path,
    *,
    clock: _FakeClock | None = None,
    **overrides: Any,
) -> dependency.CurrentObservedRawCyclePin | dependency.CurrentObservedRawCycleBlocked:
    selected_clock = clock or _FakeClock()
    selected_sleep = overrides.pop("sleep", selected_clock.sleep)
    return dependency.wait_for_current_observed_raw_cycle(
        source_output_root=output_root,
        research_root=research_root,
        repository_root=research_root.parent.parent,
        decision_date=DECISION_DATE,
        expected_source_date=SOURCE_DATE,
        deadline_monotonic=120.0,
        max_wait_seconds=120.0,
        poll_seconds=1.0,
        monotonic=selected_clock.monotonic,
        sleep=selected_sleep,
        now_provider=lambda: selected_clock.now,
        **overrides,
    )


def test_wait_accepts_same_run_after_running_status_and_emits_exact_consumer_pins(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    status_path = _status_path(output_root)
    _write_json(
        status_path,
        _raw_status(output_root, terminal, terminal_sha, status="running", cycle_status="running"),
    )
    clock = _FakeClock()

    def finish_run(_seconds: float) -> None:
        clock.tick += _seconds
        clock.now += timedelta(seconds=_seconds)
        _write_json(status_path, _raw_status(output_root, terminal, terminal_sha))

    result = dependency.wait_for_current_observed_raw_cycle(
        source_output_root=output_root,
        research_root=research_root,
        repository_root=research_root.parent.parent,
        decision_date=DECISION_DATE,
        expected_source_date=SOURCE_DATE,
        deadline_monotonic=120,
        max_wait_seconds=120,
        poll_seconds=1,
        monotonic=clock.monotonic,
        sleep=finish_run,
        now_provider=lambda: clock.now,
    )

    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.raw_run_id == RAW_RUN_ID
    assert result.source_date == SOURCE_DATE
    assert result.terminal_path == str(terminal.resolve())
    assert result.terminal_sha256 == terminal_sha
    arguments = result.learning_arguments(source_output_root=output_root)
    assert arguments == [
        "--current-observed-source-output-root",
        str(output_root),
        "--current-observed-expected-raw-run-id",
        RAW_RUN_ID,
        "--current-observed-expected-cycle-terminal",
        str(terminal.resolve()),
        "--current-observed-expected-cycle-terminal-sha256",
        terminal_sha,
    ]


def test_wait_never_follows_a_replacement_latest_raw_run(tmp_path: Path) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    status_path = _status_path(output_root)
    _write_json(
        status_path,
        _raw_status(output_root, terminal, terminal_sha, status="running", cycle_status="running"),
    )
    clock = _FakeClock()

    def replace_run(seconds: float) -> None:
        clock.tick += seconds
        clock.now += timedelta(seconds=seconds)
        _write_json(
            status_path,
            _raw_status(
                output_root,
                terminal,
                terminal_sha,
                run_id="raw-pit-replacement",
                status="running",
                cycle_status="running",
            ),
        )

    result = _wait(output_root, research_root, clock=clock, sleep=replace_run)
    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == "canonical_raw_status_pointer_changed_after_run_pin"
    assert result.pinned_raw_run_id == RAW_RUN_ID


@pytest.mark.parametrize(
    ("raw_status", "cycle_status", "expected_reason"),
    [
        ("failed", "completed", "pinned_raw_run_terminal_status_not_eligible"),
        ("completed", "failed", "pinned_raw_run_cycle_is_not_same_run_date_success"),
    ],
)
def test_wait_blocks_failed_parent_or_cycle_even_if_other_status_looks_successful(
    tmp_path: Path,
    raw_status: str,
    cycle_status: str,
    expected_reason: str,
) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    _write_json(
        _status_path(output_root),
        _raw_status(
            output_root,
            terminal,
            terminal_sha,
            status=raw_status,
            cycle_status=cycle_status,
        ),
    )

    result = _wait(output_root, research_root)
    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == expected_reason


def test_wait_allows_only_the_typed_source_revision_block_with_completed_cycle(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    blocked = _raw_status(output_root, terminal, terminal_sha, status="blocked_source_revision")
    blocked.update(
        {
            "error_type": "DailyPriceSourceRevisionError",
            "source_revision_gate": {
                "blocker_kind": "temporal_source_revision",
                "status": "blocked",
                "guard": "data_module.ml_daily_price_revision_gate.check_daily_price_source_revision",
                "receipt_reference_is_immutable_evidence": False,
            },
        }
    )
    _write_json(_status_path(output_root), blocked)

    result = _wait(output_root, research_root)
    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.raw_status == "blocked_source_revision"
    assert result.cycle_status == "completed"


def test_wait_rejects_generic_source_block_even_with_completed_cycle(tmp_path: Path) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    _write_json(
        _status_path(output_root),
        _raw_status(
            output_root,
            terminal,
            terminal_sha,
            status="blocked_source_revision",
        ),
    )

    result = _wait(output_root, research_root)
    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == "pinned_raw_run_terminal_status_not_eligible"


def test_wait_rejects_terminal_hash_or_source_date_drift(tmp_path: Path) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    bad_status = _raw_status(output_root, terminal, "sha256:" + "0" * 64)
    _write_json(_status_path(output_root), bad_status)

    result = _wait(output_root, research_root)
    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == "pinned_raw_run_cycle_terminal_sha256_mismatch"

    _write_json(
        _status_path(output_root),
        _raw_status(output_root, terminal, terminal_sha, source_date="2026-09-28"),
    )
    result = _wait(output_root, research_root)
    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == "raw_run_latest_core_date_differs_from_expected_session"


def test_wait_times_out_typed_and_stops_at_taipei_decision_date_boundary(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(research_root)
    status_path = _status_path(output_root)
    _write_json(
        status_path,
        _raw_status(output_root, terminal, terminal_sha, status="running", cycle_status="running"),
    )
    clock = _FakeClock()
    timeout = _wait(output_root, research_root, clock=clock)
    assert isinstance(timeout, dependency.CurrentObservedRawCycleBlocked)
    assert timeout.reason == "current_stock_cycle_wait_deadline_exhausted"
    assert timeout.pinned_raw_run_id == RAW_RUN_ID

    crossing_clock = _FakeClock()

    def cross_day(seconds: float) -> None:
        crossing_clock.tick += seconds
        crossing_clock.now = datetime(2026, 10, 1, 0, 0, tzinfo=dependency.TAIPEI)

    crossed = _wait(output_root, research_root, clock=crossing_clock, sleep=cross_day)
    assert isinstance(crossed, dependency.CurrentObservedRawCycleBlocked)
    assert crossed.reason == "current_stock_cycle_wait_crossed_decision_date"


@pytest.mark.parametrize(
    ("pacific_clock", "sessions_by_calendar_end", "expected_source_date"),
    [
        # Sunday G9 runs use Friday's last verified market session.
        (
            datetime(2026, 10, 4, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 10, 4): "2026-10-02"},
            "2026-10-02",
        ),
        # Before the shared 04:30 Pacific cutoff, Monday is still pinned to Friday.
        (
            datetime(2026, 10, 5, 4, 29, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 10, 4): "2026-10-02"},
            "2026-10-02",
        ),
        # After cutoff, the verified calendar may include Monday's completed session.
        (
            datetime(2026, 10, 5, 4, 31, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 10, 5): "2026-10-05"},
            "2026-10-05",
        ),
        (
            datetime(2026, 10, 5, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 10, 5): "2026-10-05"},
            "2026-10-05",
        ),
        # A verified calendar can mark a weekday closed; no weekday arithmetic.
        (
            datetime(2026, 10, 6, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 10, 6): "2026-10-05"},
            "2026-10-05",
        ),
        # Pacific Standard Time uses the same wall-clock cutoff with its own offset.
        (
            datetime(2026, 12, 7, 4, 31, tzinfo=ZoneInfo("America/Los_Angeles")),
            {date(2026, 12, 7): "2026-12-07"},
            "2026-12-07",
        ),
    ],
)
def test_source_date_resolution_uses_shared_cutoff_and_verified_calendar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pacific_clock: datetime,
    sessions_by_calendar_end: dict[date, str],
    expected_source_date: str,
) -> None:
    calls: list[date] = []

    class FakeCalendar:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def get_recent_official_trading_days(
            self,
            reference_date: date,
            count: int,
            *,
            include_reference: bool,
            allow_online_probe: bool,
        ) -> list[dict[str, object]]:
            assert count == 1
            assert include_reference is True
            assert allow_online_probe is False
            calls.append(reference_date)
            session = sessions_by_calendar_end.get(reference_date)
            assert session is not None, f"unexpected calendar endpoint {reference_date}"
            return [{"date_str": session}]

    monkeypatch.setattr(dependency, "OfficialTradingCalendar", FakeCalendar)
    decision_date = pacific_clock.astimezone(dependency.TAIPEI).date()
    result = dependency.expected_current_observed_source_date(
        decision_date=decision_date,
        observed_at=pacific_clock,
        source_db=tmp_path / "twstock.db",
    )
    assert result == expected_source_date
    assert calls == [dependency.resolve_project_market_session_boundary(pacific_clock).calendar_end_date]


@pytest.mark.parametrize(
    ("pacific_clock", "latest_session"),
    [
        (
            datetime(2026, 10, 4, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles")),
            "2026-10-02",
        ),
        (
            datetime(2026, 10, 5, 4, 29, tzinfo=ZoneInfo("America/Los_Angeles")),
            "2026-10-02",
        ),
        (
            datetime(2026, 10, 5, 4, 31, tzinfo=ZoneInfo("America/Los_Angeles")),
            "2026-10-05",
        ),
        (
            datetime(2026, 12, 7, 4, 31, tzinfo=ZoneInfo("America/Los_Angeles")),
            "2026-12-07",
        ),
    ],
)
def test_producer_to_waiter_date_matrix_accepts_exact_completed_source_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pacific_clock: datetime,
    latest_session: str,
) -> None:
    source_output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    decision_date = pacific_clock.astimezone(dependency.TAIPEI).date()
    calendar_end = dependency.resolve_project_market_session_boundary(
        pacific_clock
    ).calendar_end_date

    class FakeCalendar:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def get_recent_official_trading_days(
            self,
            reference_date: date,
            count: int,
            *,
            include_reference: bool,
            allow_online_probe: bool,
        ) -> list[dict[str, object]]:
            assert reference_date == calendar_end
            assert count == 1 and include_reference and not allow_online_probe
            return [{"date_str": latest_session}]

    monkeypatch.setattr(dependency, "OfficialTradingCalendar", FakeCalendar)
    expected_source = dependency.expected_current_observed_source_date(
        decision_date=decision_date,
        observed_at=pacific_clock,
        source_db=tmp_path / "twstock.db",
    )
    run_id = f"raw-pit-{decision_date:%Y%m%d}-matrix"
    terminal, terminal_sha = _terminal_fixture(
        research_root,
        run_id=run_id,
        source_date=expected_source,
    )
    _write_json(
        _status_path(source_output_root),
        _raw_status(
            source_output_root,
            terminal,
            terminal_sha,
            run_id=run_id,
            source_date=expected_source,
            started_at=pacific_clock.isoformat(),
        ),
    )

    result = dependency.wait_for_current_observed_raw_cycle(
        source_output_root=source_output_root,
        research_root=research_root,
        repository_root=research_root.parent.parent,
        decision_date=decision_date,
        expected_source_date=expected_source,
        deadline_monotonic=1.0,
        max_wait_seconds=1.0,
        poll_seconds=0.1,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        now_provider=lambda: pacific_clock,
    )
    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.source_date == latest_session
    assert result.raw_run_id == run_id


def test_source_date_resolution_fails_closed_without_verified_calendar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import official_trading_calendar
    from data_module.official_trading_calendar import OfficialTradingCalendarError

    online_calls: list[object] = []

    def reject_online_probe(*args: object, **kwargs: object) -> object:
        online_calls.append((args, kwargs))
        raise AssertionError("offline source-date resolution attempted an online probe")

    monkeypatch.setattr(official_trading_calendar, "safe_request", reject_online_probe)
    clock = datetime(2026, 10, 4, 5, 45, tzinfo=ZoneInfo("America/Los_Angeles"))
    with pytest.raises(OfficialTradingCalendarError):
        dependency.expected_current_observed_source_date(
            decision_date=clock.astimezone(dependency.TAIPEI).date(),
            observed_at=clock,
            source_db=tmp_path / "missing.sqlite",
            calendar_cache_path=tmp_path / "missing_calendar",
        )
    assert online_calls == []


def test_pacific_started_at_is_converted_to_taipei_decision_date_without_string_date_guess(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "FA_Data" / "output"
    research_root = tmp_path / "repo" / "output" / "ml_research"
    terminal, terminal_sha = _terminal_fixture(
        research_root,
        run_id="raw-pit-20261004T061213000000Z-1234-aabbccddeeff",
        source_date="2026-10-02",
    )
    payload = _raw_status(
        output_root,
        terminal,
        terminal_sha,
        run_id="raw-pit-20261004T061213000000Z-1234-aabbccddeeff",
        source_date="2026-10-02",
        started_at="2026-10-03T23:12:13-07:00",
    )
    _write_json(_status_path(output_root), payload)
    clock = _FakeClock(datetime(2026, 10, 4, 14, 15, tzinfo=dependency.TAIPEI))

    result = dependency.wait_for_current_observed_raw_cycle(
        source_output_root=output_root,
        research_root=research_root,
        repository_root=research_root.parent.parent,
        decision_date=date(2026, 10, 4),
        expected_source_date="2026-10-02",
        deadline_monotonic=120,
        max_wait_seconds=120,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        now_provider=lambda: clock.now,
    )

    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.source_date == "2026-10-02"
    assert result.raw_run_id == "raw-pit-20261004T061213000000Z-1234-aabbccddeeff"


def test_learning_arguments_keep_shadow_snapshot_root_separate_from_raw_root(
    tmp_path: Path,
) -> None:
    shadow_root = tmp_path / "FA_Data_Shadow"
    raw_root = tmp_path / "FA_Data" / "output"
    pin = dependency.CurrentObservedRawCyclePin(
        raw_run_id=RAW_RUN_ID,
        source_date=SOURCE_DATE,
        terminal_path=str(tmp_path / "terminal.json"),
        terminal_sha256="sha256:" + "a" * 64,
        status_path=str(raw_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"),
        status_sha256="sha256:" + "b" * 64,
        raw_status="completed",
        cycle_status="completed",
        wait_started_at=NOW.isoformat(),
        wait_completed_at=NOW.isoformat(),
        wait_deadline_at=NOW.isoformat(),
        wait_seconds=0.0,
    )
    args = pipeline.build_parser().parse_args(
        ["--data-root", str(tmp_path / "FA_Data"), "--output-root", str(shadow_root)]
    )
    learning = pipeline._learning_child_arguments(
        args=args,
        data_root=tmp_path / "FA_Data",
        output_root=shadow_root,
        source_db=tmp_path / "FA_Data" / "sqlite" / "twstock.db",
        decision_date="2026-09-30",
        snapshot_result_id="snapshot-1",
        snapshot_cohort_hash="sha256:" + "c" * 64,
        snapshot_invocation_output_sha256="sha256:" + "d" * 64,
        snapshot_invocation_output_path=str(shadow_root / "snapshot.json"),
        current_cycle_pin=pin,
        current_observed_source_output_root=raw_root,
    )

    assert learning[learning.index("--output-root") + 1] == str(shadow_root)
    assert learning[learning.index("--snapshot-output-root") + 1] == str(shadow_root)
    assert learning[learning.index("--current-observed-source-output-root") + 1] == str(raw_root)
    assert learning[learning.index("--current-observed-expected-raw-run-id") + 1] == RAW_RUN_ID
    assert learning[learning.index("--current-observed-expected-cycle-terminal-sha256") + 1] == pin.terminal_sha256

    cmd = (
        Path(__file__).parents[1]
        / "scripts"
        / "scheduled"
        / "run_recommendation_calibration_learning.cmd"
    ).read_text(encoding="utf-8")
    assert "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT=%OUTPUT_ROOT%" in cmd
    assert "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT=%DATA_ROOT%\\output" in cmd
    assert "--current-observed-source-output-root \"%CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT%\"" in cmd
    assert "--pipeline-timeout-seconds \"%RECOMMENDATION_PIPELINE_TIMEOUT_SECONDS%\"" in cmd


def test_pipeline_terminal_projection_keeps_g6_same_run_pins() -> None:
    pin = dependency.CurrentObservedRawCyclePin(
        raw_run_id=RAW_RUN_ID,
        source_date=SOURCE_DATE,
        terminal_path="C:/repo/output/ml_research/cycle/terminal_receipt.json",
        terminal_sha256="sha256:" + "a" * 64,
        status_path="D:/FA_Data/output/scheduled/ml_raw_pit_refresh/latest_status.json",
        status_sha256="sha256:" + "b" * 64,
        raw_status="completed",
        cycle_status="completed",
        wait_started_at=NOW.isoformat(),
        wait_completed_at=NOW.isoformat(),
        wait_deadline_at=NOW.isoformat(),
        wait_seconds=1.0,
    )
    projected = pipeline._terminal_receipt_projection(
        {
            "steps": {
                "current_observed_source_cycle_wait": pin.as_step(),
            },
            "current_observed_source_output_root": "D:/FA_Data/output",
            "pipeline_timeout_seconds": 10_800,
            "current_observed_wait_max_seconds": 10_500,
        }
    )
    step = projected["steps"]["current_observed_source_cycle_wait"]
    assert step["raw_run_id"] == RAW_RUN_ID
    assert step["source_date"] == SOURCE_DATE
    assert step["terminal_receipt_sha256"] == pin.terminal_sha256
    assert step["raw_status_sha256"] == pin.status_sha256
    assert projected["current_observed_source_output_root"] == "D:/FA_Data/output"
    assert projected["pipeline_timeout_seconds"] == 10_800


def test_pipeline_budget_and_bank_wait_contract_are_explicit() -> None:
    defaults = pipeline.build_parser().parse_args(
        ["--data-root", "D:/FA_Data", "--output-root", "D:/FA_Data_Shadow"]
    )
    assert defaults.pipeline_timeout_seconds == 10_800
    assert defaults.current_observed_wait_max_seconds == 10_500
    assert defaults.child_timeout_seconds == 3_600


@pytest.mark.parametrize(
    ("g6_available", "pipeline_timeout_seconds", "quick_lock_available"),
    [
        (True, 10_800.0, True),
        (True, 10_800.0, False),
        (False, 10_800.0, True),
        (False, 60.0, True),
    ],
    ids=[
        "g6-completed-lock-released",
        "g6-completed-lock-timeout",
        "g6-blocked",
        "wait-budget-insufficient",
    ],
)
def test_pipeline_waits_before_quick_and_passes_exact_g6_pins_to_learning_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    g6_available: bool,
    pipeline_timeout_seconds: float,
    quick_lock_available: bool,
) -> None:
    decision_clock = datetime(2026, 10, 4, 14, 15, tzinfo=dependency.TAIPEI)
    post_wait_clock = decision_clock + timedelta(seconds=37)
    clock_state = [decision_clock]
    events: list[str] = []
    observed_source_date_calls: list[dict[str, object]] = []
    learning_arguments: list[str] = []
    learning_capture_clocks: list[datetime] = []
    raw_root = tmp_path / "FA_Data" / "output"
    shadow_root = tmp_path / "FA_Data_Shadow"
    pin = dependency.CurrentObservedRawCyclePin(
        raw_run_id="raw-pit-20261004T061213000000Z-1234-aabbccddeeff",
        source_date="2026-10-02",
        terminal_path=str(
            tmp_path
            / "repo"
            / "output"
            / "ml_research"
            / "current_stock_cycles"
            / "2026-10-02"
            / "cycle"
            / "terminal_receipt.json"
        ),
        terminal_sha256="sha256:" + "a" * 64,
        status_path=str(raw_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"),
        status_sha256="sha256:" + "b" * 64,
        raw_status="completed",
        cycle_status="completed",
        wait_started_at=decision_clock.isoformat(),
        wait_completed_at=post_wait_clock.isoformat(),
        wait_deadline_at=(decision_clock + timedelta(hours=3)).isoformat(),
        wait_seconds=37.0,
    )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            current = clock_state[0]
            return current if tz is None else current.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FrozenDateTime)
    monkeypatch.setattr(pipeline, "parse_current_restated_research_invocation", lambda _args: None)
    def resolve_source_date(**kwargs: object) -> str:
        observed_source_date_calls.append(dict(kwargs))
        return "2026-10-02"

    monkeypatch.setattr(pipeline, "expected_current_observed_source_date", resolve_source_date)

    def wait_for_cycle(
        **kwargs: object,
    ) -> dependency.CurrentObservedRawCyclePin | dependency.CurrentObservedRawCycleBlocked:
        assert kwargs["source_output_root"] == raw_root.resolve()
        assert kwargs["decision_date"] == date(2026, 10, 4)
        assert kwargs["expected_source_date"] == "2026-10-02"
        assert float(kwargs["max_wait_seconds"]) <= 3_300.0
        if pipeline_timeout_seconds <= 300.0 + 2.0 * 3_600.0:
            assert float(kwargs["max_wait_seconds"]) == 0.0
        events.append("g6_wait_returned")
        clock_state[0] = post_wait_clock
        if g6_available:
            return pin
        return dependency.CurrentObservedRawCycleBlocked(
            reason=(
                "current_stock_cycle_wait_budget_exhausted_before_start"
                if pipeline_timeout_seconds < 10_800.0
                else "current_stock_cycle_exact_terminal_unavailable"
            ),
            wait_started_at=decision_clock.isoformat(),
            wait_completed_at=post_wait_clock.isoformat(),
            wait_deadline_at=(decision_clock + timedelta(hours=3)).isoformat(),
            wait_seconds=37.0,
            expected_source_date="2026-10-02",
        )

    monkeypatch.setattr(pipeline, "wait_for_current_observed_raw_cycle", wait_for_cycle)

    def probe_quick_lock(
        lock_path: Path,
        *,
        max_wait_seconds: float,
        **_kwargs: object,
    ) -> dict[str, object]:
        assert max_wait_seconds <= 30.0
        events.append("quick_lock_barrier")
        return {
            "status": "released" if quick_lock_available else "timed_out",
            "reason": None
            if quick_lock_available
            else "quick_heavy_chain_lock_release_wait_timed_out",
            "lock_path": str(lock_path.resolve()),
            "attempt_count": 1,
            "started_at_utc": decision_clock.astimezone(timezone.utc).isoformat(),
            "finished_at_utc": decision_clock.astimezone(timezone.utc).isoformat(),
            "waited_seconds": 0.0 if quick_lock_available else 30.0,
            "max_wait_seconds": max_wait_seconds,
            "reservation_proof": "exclusive_reservation_acquired_and_released"
            if quick_lock_available
            else "reservation_unavailable_until_deadline",
        }

    monkeypatch.setattr(pipeline, "_wait_for_quick_lock_release", probe_quick_lock)

    def fake_child(**kwargs: object) -> dict[str, object]:
        name = str(kwargs["name"])
        if name == "recommendation_learning":
            assert g6_available, "learning must remain blocked without the exact G6 pin"
            events.append("learning_child_started")
            learning_arguments.extend(str(value) for value in kwargs["arguments"])
            learning_capture_clocks.append(FrozenDateTime.now(ZoneInfo("Asia/Taipei")))
            child_status: dict[str, object] | None = {"status": "passed"}
        elif name == "data_update_quick":
            assert g6_available, "Quick writer must not start without the exact G6 pin"
            events.append("quick_child_started")
            arguments = [str(value) for value in kwargs["arguments"]]
            assert arguments[arguments.index("--start-date") + 1] == pin.source_date
            assert arguments[arguments.index("--end-date") + 1] == pin.source_date
            assert arguments[arguments.index("--output-root") + 1] == str(raw_root.resolve())
            assert arguments[arguments.index("--formal-output-root") + 1] == str(raw_root.resolve())
            child_environment = kwargs["environment"]
            assert isinstance(child_environment, dict)
            assert child_environment["OUTPUT_ROOT"] == str(raw_root.resolve())
            child_status = {"status": "passed"}
        elif name == "official_market_events":
            events.append("official_child_started")
            child_status = {"status": "passed"}
        elif name == "recommendation_snapshot":
            events.append("snapshot_child_started")
            child_status = {
                "status": "passed",
                "decision_date": "2026-10-04",
                "result_id": "snapshot-20261004",
                "snapshot_cohort": {
                    "cohort_hash": "sha256:" + "c" * 64,
                    "requested_symbols": ["1477"],
                    "eligible_symbols": ["1477"],
                    "missing_symbols": [],
                    "degraded_symbols": [],
                    "excluded_symbols": [],
                },
            }
        else:
            child_status = {"status": "passed"}
        return {
            "name": name,
            "script": str(kwargs["script"]),
            "command": [],
            "returncode": 0,
            "status": "passed",
            "status_path": str(tmp_path / f"{name}.json"),
            "child_status": child_status,
            "child_warnings": [],
            "child_blockers": [],
            "stdout_stderr_tail": "",
            "timeout_seconds": kwargs.get("timeout_seconds"),
            "recoverable": False,
            "child_stdout_sha256": "sha256:" + "d" * 64,
            "child_stdout_artifact_path": str(tmp_path / "snapshot.stdout.json"),
        }

    monkeypatch.setattr(pipeline, "_run_child", fake_child)

    exit_code = pipeline.main(
        [
            "--data-root",
            str(tmp_path / "FA_Data"),
            "--output-root",
            str(shadow_root),
            "--current-observed-source-output-root",
            str(raw_root),
            "--pipeline-timeout-seconds",
            str(pipeline_timeout_seconds),
        ]
    )

    assert exit_code == (0 if g6_available and quick_lock_available else 1)
    assert observed_source_date_calls
    assert observed_source_date_calls[0]["decision_date"] == date(2026, 10, 4)
    assert observed_source_date_calls[0]["observed_at"] == decision_clock
    if g6_available:
        expected_events = ["g6_wait_returned", "quick_lock_barrier"]
        if quick_lock_available:
            expected_events.append("quick_child_started")
        expected_events.extend(
            [
                "official_child_started",
                "snapshot_child_started",
                "learning_child_started",
            ]
        )
        assert events == expected_events
        assert learning_capture_clocks == [post_wait_clock]
        required_arguments = {
            "--current-observed-source-output-root": str(raw_root.resolve()),
            "--current-observed-expected-raw-run-id": pin.raw_run_id,
            "--current-observed-expected-cycle-terminal": pin.terminal_path,
            "--current-observed-expected-cycle-terminal-sha256": pin.terminal_sha256,
        }
        for flag, value in required_arguments.items():
            assert learning_arguments[learning_arguments.index(flag) + 1] == value
        assert learning_arguments[learning_arguments.index("--snapshot-output-root") + 1] == str(shadow_root.resolve())
        if not quick_lock_available:
            latest_status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
            latest_status = json.loads(latest_status_path.read_text(encoding="utf-8"))
            quick_step = latest_status["steps"]["data_update_quick"]
            assert quick_step["status"] == "timed_out"
            assert quick_step["lock_release_barrier"]["reservation_proof"] == (
                "reservation_unavailable_until_deadline"
            )
    elif pipeline_timeout_seconds <= 300.0 + 2.0 * 3_600.0:
        assert events == ["g6_wait_returned"]
        assert learning_capture_clocks == []
        latest_status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
        latest_status = json.loads(latest_status_path.read_text(encoding="utf-8"))
        assert latest_status["steps"]["data_update_quick"]["status"] == "blocked"
        assert latest_status["steps"]["official_market_events"]["status"] == "timed_out"
        assert latest_status["steps"]["recommendation_snapshot"]["status"] == "timed_out"
        assert latest_status["steps"]["recommendation_learning"]["status"] == "blocked"
    else:
        assert events == [
            "g6_wait_returned",
            "official_child_started",
            "snapshot_child_started",
        ]
        assert learning_capture_clocks == []
        latest_status_path = shadow_root / "scheduled" / "recommendation_calibration_learning" / "latest_status.json"
        latest_status = json.loads(latest_status_path.read_text(encoding="utf-8"))
        assert latest_status["steps"]["data_update_quick"]["status"] == "blocked"
        assert latest_status["steps"]["recommendation_learning"]["status"] == "blocked"


def test_pipeline_child_budgets_keep_learning_and_terminal_flush_reserves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_clock = datetime(2026, 10, 4, 14, 15, tzinfo=dependency.TAIPEI)
    clock_state = [decision_clock]
    fake_monotonic = _FakeClock(decision_clock)
    durations = {
        "data_update_quick": 3_500.0,
        "official_market_events": 3_300.0,
        "recommendation_snapshot": 70.0,
        "recommendation_learning": 3_300.0,
    }
    started: list[str] = []
    child_timeouts: dict[str, float] = {}
    barrier_calls: list[dict[str, object]] = []
    raw_root = (tmp_path / "FA_Data" / "output").resolve()
    shadow_root = (tmp_path / "FA_Data_Shadow").resolve()
    pin = dependency.CurrentObservedRawCyclePin(
        raw_run_id=RAW_RUN_ID,
        source_date="2026-10-02",
        terminal_path=str(tmp_path / "research" / "terminal_receipt.json"),
        terminal_sha256="sha256:" + "a" * 64,
        status_path=str(raw_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"),
        status_sha256="sha256:" + "b" * 64,
        raw_status="completed",
        cycle_status="completed",
        wait_started_at=decision_clock.isoformat(),
        wait_completed_at=decision_clock.isoformat(),
        wait_deadline_at=(decision_clock + timedelta(hours=1)).isoformat(),
        wait_seconds=0.0,
    )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            current = clock_state[0]
            return current if tz is None else current.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        pipeline,
        "time",
        SimpleNamespace(
            monotonic=fake_monotonic.monotonic,
            sleep=fake_monotonic.sleep,
        ),
    )
    monkeypatch.setattr(pipeline, "parse_current_restated_research_invocation", lambda _args: None)
    monkeypatch.setattr(
        pipeline,
        "expected_current_observed_source_date",
        lambda **_kwargs: "2026-10-02",
    )
    monkeypatch.setattr(pipeline, "wait_for_current_observed_raw_cycle", lambda **_kwargs: pin)

    def pass_quick_lock_barrier(
        lock_path: Path,
        *,
        max_wait_seconds: float,
        **_kwargs: object,
    ) -> dict[str, object]:
        waited = min(30.0, max_wait_seconds)
        barrier_calls.append({"lock_path": lock_path, "max_wait_seconds": max_wait_seconds})
        fake_monotonic.sleep(waited)
        return {
            "status": "released",
            "reason": None,
            "lock_path": str(lock_path.resolve()),
            "attempt_count": 2,
            "started_at_utc": "2026-10-04T14:15:00+00:00",
            "finished_at_utc": "2026-10-04T14:15:30+00:00",
            "waited_seconds": waited,
            "max_wait_seconds": max_wait_seconds,
            "reservation_proof": "exclusive_reservation_acquired_and_released",
        }

    monkeypatch.setattr(pipeline, "_wait_for_quick_lock_release", pass_quick_lock_barrier)

    def fake_child(**kwargs: object) -> dict[str, object]:
        name = str(kwargs["name"])
        started.append(name)
        child_timeouts[name] = float(kwargs["timeout_seconds"])
        fake_monotonic.sleep(durations[name])
        clock_state[0] += timedelta(seconds=durations[name])
        child_status: dict[str, object] = {"status": "passed", "warnings": [], "blockers": []}
        if name == "recommendation_snapshot":
            child_status.update(
                {
                    "decision_date": "2026-10-04",
                    "result_id": "snapshot-budget-test",
                    "snapshot_cohort": {
                        "cohort_hash": "sha256:" + "c" * 64,
                        "requested_symbols": ["1477"],
                        "eligible_symbols": ["1477"],
                        "missing_symbols": [],
                        "degraded_symbols": [],
                        "excluded_symbols": [],
                    },
                }
            )
        return {
            "name": name,
            "script": str(kwargs["script"]),
            "command": [],
            "returncode": 0,
            "status": "passed",
            "status_path": str(tmp_path / f"{name}.json"),
            "child_status": child_status,
            "child_warnings": [],
            "child_blockers": [],
            "stdout_stderr_tail": "",
            "timeout_seconds": kwargs["timeout_seconds"],
            "recoverable": False,
            "child_stdout_sha256": "sha256:" + "d" * 64,
            "child_stdout_artifact_path": str(tmp_path / "snapshot.stdout.json"),
        }

    monkeypatch.setattr(pipeline, "_run_child", fake_child)
    result = pipeline.main(
        [
            "--data-root",
            str(tmp_path / "FA_Data"),
            "--output-root",
            str(shadow_root),
            "--current-observed-source-output-root",
            str(raw_root),
        ]
    )

    assert result == 0
    assert started == [
        "data_update_quick",
        "official_market_events",
        "recommendation_snapshot",
        "recommendation_learning",
    ]
    assert child_timeouts == {
        "data_update_quick": 3_570.0,
        "official_market_events": 3_370.0,
        "recommendation_snapshot": 70.0,
        "recommendation_learning": 3_600.0,
    }
    assert barrier_calls[0]["max_wait_seconds"] == 30.0
    assert barrier_calls[0]["lock_path"] == heavy_chain_lock_path(
        raw_root / "release_v4"
    )
    assert 10_800.0 - fake_monotonic.tick == 600.0
    status_path = (
        shadow_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["steps"]["recommendation_learning"]["budget_reservation"][
        "terminal_receipt_flush_reserve_seconds"
    ] == 300.0
    assert status["steps"]["recommendation_snapshot"]["budget_reservation"][
        "learning_child_timeout_reserve_seconds"
    ] == 3_600.0
    assert status["steps"]["data_update_quick"]["lock_release_barrier"][
        "reservation_proof"
    ] == "exclusive_reservation_acquired_and_released"


def test_pipeline_does_not_start_quick_when_only_reserved_budget_remains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_clock = datetime(2026, 10, 4, 14, 15, tzinfo=dependency.TAIPEI)
    clock_state = [decision_clock]
    raw_root = (tmp_path / "FA_Data" / "output").resolve()
    shadow_root = (tmp_path / "FA_Data_Shadow").resolve()
    pin = dependency.CurrentObservedRawCyclePin(
        raw_run_id=RAW_RUN_ID,
        source_date="2026-10-02",
        terminal_path=str(tmp_path / "research" / "terminal_receipt.json"),
        terminal_sha256="sha256:" + "a" * 64,
        status_path=str(raw_root / "scheduled" / "ml_raw_pit_refresh" / "latest_status.json"),
        status_sha256="sha256:" + "b" * 64,
        raw_status="completed",
        cycle_status="completed",
        wait_started_at=decision_clock.isoformat(),
        wait_completed_at=decision_clock.isoformat(),
        wait_deadline_at=(decision_clock + timedelta(hours=1)).isoformat(),
        wait_seconds=0.0,
    )
    fake_monotonic = _FakeClock(decision_clock)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            current = clock_state[0]
            return current if tz is None else current.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        pipeline,
        "time",
        SimpleNamespace(
            monotonic=fake_monotonic.monotonic,
            sleep=fake_monotonic.sleep,
        ),
    )
    monkeypatch.setattr(pipeline, "parse_current_restated_research_invocation", lambda _args: None)
    monkeypatch.setattr(
        pipeline,
        "expected_current_observed_source_date",
        lambda **_kwargs: "2026-10-02",
    )
    monkeypatch.setattr(pipeline, "wait_for_current_observed_raw_cycle", lambda **_kwargs: pin)
    monkeypatch.setattr(
        pipeline,
        "_wait_for_quick_lock_release",
        lambda *_args, **_kwargs: pytest.fail("no child budget means no lock attempt"),
    )
    calls: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "_run_child",
        lambda **kwargs: calls.append(str(kwargs["name"]))
        or pytest.fail("no child process may start without budget"),
    )

    result = pipeline.main(
        [
            "--data-root",
            str(tmp_path / "FA_Data"),
            "--output-root",
            str(shadow_root),
            "--current-observed-source-output-root",
            str(raw_root),
            "--child-timeout-seconds",
            "3600",
            "--pipeline-timeout-seconds",
            "3900",
        ]
    )

    assert result == 1
    assert calls == []
    status_path = (
        shadow_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "latest_status.json"
    )
    status = json.loads(status_path.read_text(encoding="utf-8"))
    quick = status["steps"]["data_update_quick"]
    assert quick["status"] == "timed_out"
    assert quick["child_blockers"] == ["pipeline_reserved_budget_exhausted:data_update_quick"]
    assert quick["lock_release_barrier"]["status"] == "not_attempted"
    assert status["steps"]["official_market_events"]["status"] == "timed_out"
    assert status["steps"]["recommendation_snapshot"]["status"] == "timed_out"
    assert status["steps"]["recommendation_learning"]["status"] == "blocked"


def test_quick_lock_barrier_hands_off_after_real_os_reservation_release(
    tmp_path: Path,
) -> None:
    lock_path = heavy_chain_lock_path(tmp_path / "output" / "release_v4")
    held_reservation = acquire_heavy_chain_reservation(lock_path)
    assert held_reservation is not None
    clock = _FakeClock()

    def release_during_wait(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.tick >= 0.5:
            release_heavy_chain_reservation(held_reservation)

    try:
        result = pipeline._wait_for_quick_lock_release(
            lock_path,
            max_wait_seconds=2.0,
            poll_seconds=0.25,
            monotonic=clock.monotonic,
            sleep=release_during_wait,
        )
    finally:
        release_heavy_chain_reservation(held_reservation)

    assert result["status"] == "released"
    assert result["lock_path"] == str(lock_path.resolve())
    assert result["attempt_count"] >= 3
    assert result["waited_seconds"] == 0.5
    assert result["reservation_proof"] == "exclusive_reservation_acquired_and_released"
    probe = acquire_heavy_chain_reservation(lock_path)
    assert probe is not None, "the barrier must not leave its probe reservation held"
    release_heavy_chain_reservation(probe)


def test_quick_lock_barrier_fails_closed_at_its_bounded_deadline(
    tmp_path: Path,
) -> None:
    lock_path = heavy_chain_lock_path(tmp_path / "output" / "release_v4")
    held_reservation = acquire_heavy_chain_reservation(lock_path)
    assert held_reservation is not None
    clock = _FakeClock()
    try:
        result = pipeline._wait_for_quick_lock_release(
            lock_path,
            max_wait_seconds=30.0,
            poll_seconds=0.25,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
    finally:
        release_heavy_chain_reservation(held_reservation)

    assert result["status"] == "timed_out"
    assert result["reason"] == "quick_heavy_chain_lock_release_wait_timed_out"
    assert result["max_wait_seconds"] == 30.0
    assert result["waited_seconds"] == 30.0
    assert result["reservation_proof"] == "reservation_unavailable_until_deadline"


def _write_formal_capacity_wait_case(
    tmp_path: Path,
    *,
    child_status: str = "completed",
    run_id: str = RAW_RUN_ID,
    source_date: str = SOURCE_DATE,
    terminal_mutator: Any = None,
) -> tuple[Path, Path, Path, date, str]:
    """Use the shared verified capacity fixture, then exercise the real waiter."""

    import importlib

    capacity_fixtures = importlib.import_module(
        "test_current_observed_capacity_eligibility"
    )
    formal_root = (tmp_path / "FA_Data" / "output").resolve()
    research_root = (tmp_path / "repo" / "output" / "ml_research").resolve()
    terminal_path = (
        research_root
        / "current_stock_cycles"
        / source_date
        / run_id
        / "terminal_receipt.json"
    )
    terminal = capacity_fixtures._current_cycle_terminal(
        research_root,
        formal_root,
        status="failed" if child_status == "failed" else "completed",
        raw_run_id=run_id,
        source_date=source_date,
    )
    terminal["cycle_output_root"] = str(terminal_path.parent.resolve())
    terminal["same_run_pins"]["research_output_root"] = str(research_root)
    if terminal_mutator is not None:
        terminal_mutator(terminal, formal_root, research_root)
    terminal_bytes = _write_json(terminal_path, terminal)
    terminal_sha = "sha256:" + hashlib.sha256(terminal_bytes).hexdigest()

    raw_status = capacity_fixtures._formal_capacity_block(
        tmp_path,
        child_status=child_status,
    )
    raw_status.update(
        {
            "output_root": str(formal_root),
            "raw_output_root": str(
                formal_root / "release_v4" / "ml_pit_year_shards"
            ),
            "run_id": run_id,
            "latest_core_date": source_date,
            "source_date": source_date,
            "started_at": "2026-09-30T20:45:00+08:00",
        }
    )
    child = raw_status["current_stock_research_cycle"]
    child.update(
        {
            "raw_run_id": run_id,
            "cycle_id": run_id,
            "source_date": source_date,
            "terminal_receipt_path": str(terminal_path.resolve()),
            "terminal_receipt_sha256": terminal_sha,
        }
    )
    status_path = _status_path(formal_root)
    _write_json(status_path, raw_status)
    return formal_root, research_root, status_path, DECISION_DATE, source_date


def _wait_for_capacity_exception_case(
    *,
    formal_root: Path,
    research_root: Path,
    decision_date: date,
    source_date: str,
) -> dependency.CurrentObservedRawCyclePin | dependency.CurrentObservedRawCycleBlocked:
    clock_now = datetime.fromisoformat(
        f"{decision_date.isoformat()}T20:45:00+08:00"
    )
    clock = _FakeClock(clock_now)
    return dependency.wait_for_current_observed_raw_cycle(
        source_output_root=formal_root,
        research_root=research_root,
        repository_root=research_root.parent.parent,
        decision_date=decision_date,
        expected_source_date=source_date,
        deadline_monotonic=120.0,
        max_wait_seconds=120.0,
        poll_seconds=1.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        now_provider=lambda: clock.now,
    )


def test_wait_accepts_formal_bootstrap_capacity_block_with_real_completed_capacity_proof(
    tmp_path: Path,
) -> None:
    formal_root, research_root, _status_path_value, decision_date, source_date = (
        _write_formal_capacity_wait_case(tmp_path)
    )

    result = _wait_for_capacity_exception_case(
        formal_root=formal_root,
        research_root=research_root,
        decision_date=decision_date,
        source_date=source_date,
    )

    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.raw_run_id == RAW_RUN_ID
    assert result.raw_status == "blocked_insufficient_storage"
    assert result.cycle_status == "completed"
    assert result.source_date == SOURCE_DATE


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("failed_child", "pinned_raw_run_terminal_status_not_eligible"),
        ("forged_capacity_root", "formal_capacity_block_g6_terminal_capacity_unverified"),
        ("bad_budget", "formal_capacity_block_g6_terminal_capacity_unverified"),
        ("forged_raw_root", "canonical_raw_status_root_mismatch"),
    ],
)
def test_wait_rejects_invalid_formal_capacity_exception_proofs(
    tmp_path: Path,
    case: str,
    expected_reason: str,
) -> None:
    def mutate_terminal(
        terminal: dict[str, Any], formal_root: Path, _research_root: Path
    ) -> None:
        if case == "forged_capacity_root":
            terminal["same_run_pins"]["research_output_root"] = str(formal_root)
        elif case == "bad_budget":
            terminal["capacity"]["check"]["within_budget"] = False

    child_status = "failed" if case == "failed_child" else "completed"
    formal_root, research_root, status_path, decision_date, source_date = (
        _write_formal_capacity_wait_case(
            tmp_path,
            child_status=child_status,
            terminal_mutator=mutate_terminal,
        )
    )
    if case == "forged_raw_root":
        raw_status = json.loads(status_path.read_text(encoding="utf-8"))
        raw_status["output_root"] = str(tmp_path / "different-output-root")
        _write_json(status_path, raw_status)

    result = _wait_for_capacity_exception_case(
        formal_root=formal_root,
        research_root=research_root,
        decision_date=decision_date,
        source_date=source_date,
    )

    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == expected_reason


def _write_skipped_capacity_reuse_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    original_capacity_proof: bool,
) -> tuple[Path, Path, Path, date, str]:
    import importlib

    capacity_fixtures = importlib.import_module(
        "test_current_observed_capacity_eligibility"
    )
    reuse_fixtures = importlib.import_module("test_current_observed_learning_capture")
    reuse_path, _initial_reuse_sha, _registry_path = reuse_fixtures._reuse_cycle_fixture(
        tmp_path,
        monkeypatch,
    )
    research_root = reuse_path.parents[2].resolve()
    formal_root = (tmp_path / "FA_Data" / "output").resolve()
    source_date = "2026-10-05"
    original_path = research_root / "current_stock_cycles" / "original" / "terminal_receipt.json"
    if original_capacity_proof:
        original = json.loads(original_path.read_text(encoding="utf-8"))
        original["research_only"] = True
        original["formal_oos_allowed"] = False
        original["formal_credit"] = False
        original["cycle_output_root"] = str(original_path.parent.resolve())
        original["same_run_pins"]["research_output_root"] = str(research_root)
        original["capacity"] = capacity_fixtures._current_cycle_terminal(
            research_root,
            formal_root,
            raw_run_id="raw-original",
            source_date=source_date,
        )["capacity"]
        original_sha = reuse_fixtures._write_json_pin(original_path, original)
        reuse_payload = json.loads(reuse_path.read_text(encoding="utf-8"))
        reuse_payload["reused_from"]["terminal_receipt_sha256"] = original_sha
        reuse_sha = reuse_fixtures._write_json_pin(reuse_path, reuse_payload)
    else:
        reuse_sha = reuse_fixtures._file_sha256(reuse_path)

    raw_status = capacity_fixtures._formal_capacity_block(
        tmp_path,
        child_status="skipped_same_inputs",
    )
    raw_status.update(
        {
            "output_root": str(formal_root),
            "raw_output_root": str(
                formal_root / "release_v4" / "ml_pit_year_shards"
            ),
            "run_id": "raw-reuse",
            "latest_core_date": source_date,
            "source_date": source_date,
            "started_at": "2026-10-05T20:45:00+08:00",
        }
    )
    raw_status["current_stock_research_cycle"].update(
        {
            "raw_run_id": "raw-reuse",
            "cycle_id": "raw-reuse",
            "source_date": source_date,
            "terminal_receipt_path": str(reuse_path.resolve()),
            "terminal_receipt_sha256": reuse_sha,
        }
    )
    status_path = _status_path(formal_root)
    _write_json(status_path, raw_status)
    return formal_root, research_root, status_path, date(2026, 10, 5), source_date


def test_wait_accepts_capacity_block_with_skipped_same_inputs_and_original_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formal_root, research_root, _status_path_value, decision_date, source_date = (
        _write_skipped_capacity_reuse_case(
            tmp_path,
            monkeypatch,
            original_capacity_proof=True,
        )
    )

    result = _wait_for_capacity_exception_case(
        formal_root=formal_root,
        research_root=research_root,
        decision_date=decision_date,
        source_date=source_date,
    )

    assert isinstance(result, dependency.CurrentObservedRawCyclePin)
    assert result.raw_run_id == "raw-reuse"
    assert result.cycle_status == "skipped_same_inputs"
    assert result.raw_status == "blocked_insufficient_storage"


def test_wait_rejects_skipped_capacity_reuse_without_original_capacity_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formal_root, research_root, _status_path_value, decision_date, source_date = (
        _write_skipped_capacity_reuse_case(
            tmp_path,
            monkeypatch,
            original_capacity_proof=False,
        )
    )

    result = _wait_for_capacity_exception_case(
        formal_root=formal_root,
        research_root=research_root,
        decision_date=decision_date,
        source_date=source_date,
    )

    assert isinstance(result, dependency.CurrentObservedRawCycleBlocked)
    assert result.reason == "formal_capacity_block_g6_reuse_or_original_capacity_unverified"
