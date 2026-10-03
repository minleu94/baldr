from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_decision_desk_evidence_source import (
    PaperDecisionDeskEvidenceSource,
)
from app_module.position_health_daily_refresh_service import (
    PositionHealthDailyRefreshService,
)
from scripts.scheduled import run_paper_execution_daily_isolated as eod_adapter
from scripts.scheduled import run_paper_portfolio_daily_isolated as preopen_adapter
from scripts.scheduled import run_formal_input_producer_daily as formal_adapter

TAIPEI = ZoneInfo("Asia/Taipei")


class _OpenCalendar:
    def is_official_trading_day(self, _target_date):
        return True, "test_official_schedule_open"


def _make_source_state(
    path: Path,
    *,
    decision_date: str = "2026-07-12",
) -> None:
    repository = PaperPortfolioSnapshotRepository(path)
    repository.append(
        PaperPortfolioSnapshot(
            snapshot_id=f"paper-main-{decision_date.replace('-', '')}-baseline",
            portfolio_id="paper-main",
            decision_date=decision_date,
            source_result_id="source-baseline-1",
            cash=Decimal("80000.00"),
            total_value=Decimal("100000.00"),
            positions=(
                PaperPortfolioPositionSnapshot(
                    stock_code="2330",
                    quantity=1000,
                    mark_price=Decimal("20.00"),
                    market_value=Decimal("20000.00"),
                    weight_bp=2000,
                ),
            ),
        )
    )


def _make_baseline(
    path: Path,
    *,
    decision_date: str = "2026-07-12",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "decision_date": decision_date,
                "source_result_id": "source-baseline-1",
                "residual_cash": "80000.00",
                "allocations": [
                    {
                        "stock_code": "2330",
                        "executable_shares": 1000,
                        "reference_price": "20.00",
                        "executable_amount": "20000.00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _make_market(
    path: Path,
    *,
    price_date: str = "20260713",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 TEXT)"
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?)",
            (price_date, "2330", "21.00"),
        )


def _make_calendar_cache(
    path: Path,
    *,
    captured_at: datetime | None = None,
    max_age: timedelta = timedelta(days=7),
) -> None:
    captured = captured_at or (datetime.now(timezone.utc) - timedelta(hours=1))
    raw = json.dumps(
        [
            {
                "Name": "中華民國開國紀念日",
                "Date": "1150101",
                "Weekday": "四",
                "Description": "依規定放假1日。",
            },
            {
                "Name": "國曆新年開始交易日",
                "Date": "1150102",
                "Weekday": "五",
                "Description": "國曆新年開始交易。",
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured - timedelta(seconds=1),
        captured_at=captured,
        response_status=200,
        max_age=max_age,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_twse_calendar_cache(path, cache, allowed_root=path.parents[1])


def _recent_test_decision_at() -> datetime:
    """Choose a recent weekday 08:30 whose 31-day cache remains fresh."""

    current = datetime.now(timezone.utc).astimezone(TAIPEI)
    candidate = current.date()
    if current.timetz().replace(tzinfo=None) < time(8, 35):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return datetime.combine(candidate, time(8, 30), tzinfo=TAIPEI)


def _patch_preopen_paths(
    monkeypatch: pytest.MonkeyPatch,
    *,
    data_root: Path,
    operation_root: Path,
    source_decision_date: str = "2026-07-12",
    market_price_date: str = "20260713",
) -> tuple[Path, Path, Path, Path]:
    source_state = data_root / "output" / "paper_portfolio" / "paper_portfolio.sqlite"
    baseline = data_root / "output" / "paper_portfolio" / "baseline_20260712.json"
    market = data_root / "sqlite" / "twstock.db"
    state = operation_root / "paper_portfolio" / "paper_portfolio.sqlite"
    manifest = operation_root / "paper_portfolio" / "state_seed_manifest.json"
    ledger = operation_root / "paper_trade_ledger.sqlite"
    _make_source_state(source_state, decision_date=source_decision_date)
    _make_baseline(baseline, decision_date=source_decision_date)
    _make_market(market, price_date=market_price_date)
    monkeypatch.setattr(preopen_adapter, "ROOT", operation_root.parents[1])
    monkeypatch.setattr(preopen_adapter, "DEFAULT_DATA_ROOT", data_root)
    monkeypatch.setattr(preopen_adapter, "SOURCE_STATE_DB", source_state)
    monkeypatch.setattr(preopen_adapter, "SOURCE_BASELINE_PATH", baseline)
    monkeypatch.setattr(preopen_adapter, "OPERATIONAL_ROOT", operation_root)
    monkeypatch.setattr(preopen_adapter, "PAPER_STATE_ROOT", state.parent)
    monkeypatch.setattr(preopen_adapter, "STATE_DB", state)
    monkeypatch.setattr(preopen_adapter, "STATE_SEED_MANIFEST", manifest)
    monkeypatch.setattr(preopen_adapter, "MARKET_DB", market)
    monkeypatch.setattr(preopen_adapter, "LEDGER_DB", ledger)
    return source_state, baseline, market, state


def test_isolated_preopen_seeds_readonly_source_then_calls_public_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    source_state, baseline, market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
    )
    source_bytes = source_state.read_bytes()
    baseline_bytes = baseline.read_bytes()
    market_bytes = market.read_bytes()
    decision_at = datetime.fromisoformat("2026-07-14T08:30:00+08:00")
    observed = datetime.fromisoformat("2026-07-14T08:31:00+08:00")

    first = preopen_adapter.run_isolated(
        now=observed,
        decision_at=decision_at,
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )
    assert first["status"] == "passed"
    assert first["schema_version"] == "paper-portfolio-daily-status.v1"
    assert first["isolated_scope_schema_version"] == preopen_adapter.SCHEMA_VERSION
    assert first["state_db"] == str(state)
    coverage = first["preopen_coverage"]
    assert isinstance(coverage, dict)
    assert coverage["schema_version"] == "paper-preopen-coverage.v1"
    assert coverage["state_db"] == str(state.resolve())
    write_contract = first["paper_state_write_contract"]
    assert isinstance(write_contract, dict)
    assert write_contract["write_scope"] == (
        "repository_paper_snapshot_append_only"
    )
    scope = first["isolated_scope"]
    assert isinstance(scope, dict)
    seed = scope["state_seed"]
    assert isinstance(seed, dict)
    assert seed["status"] == "seeded"
    assert seed["seed_method"] == "sqlite_readonly_consistent_backup"
    assert source_state.read_bytes() == source_bytes
    assert baseline.read_bytes() == baseline_bytes
    assert market.read_bytes() == market_bytes
    assert state.is_file()
    seed_manifest_path = operation_root / "paper_portfolio" / "state_seed_manifest.json"
    assert seed_manifest_path.is_file()
    seed_manifest = json.loads(seed_manifest_path.read_text(encoding="utf-8"))
    assert seed_manifest["source"]["read_mode"] == (
        "sqlite_uri_mode_ro_and_query_only"
    )
    assert seed_manifest["source"]["bundle"]["files"][0]["path"] == str(
        source_state.resolve()
    )
    assert seed_manifest["target"]["seed_file_sha256"] == seed["target_file_sha256"]
    state_head_path = operation_root / "paper_portfolio" / "state_head_manifest.json"
    assert state_head_path.is_file()
    state_head = json.loads(state_head_path.read_text(encoding="utf-8"))
    assert state_head["target_file_sha256"] == preopen_adapter._file_hash(state)
    assert state_head["target_file_sha256"] != seed["target_file_sha256"]
    snapshot = PaperPortfolioSnapshotRepository(state).get("paper-main-20260714")
    assert snapshot is not None
    assert snapshot.total_value == Decimal("101000.00")

    status_path = (
        operation_root / "scheduled" / "paper_portfolio_isolated" / "latest_status.json"
    )
    health_output = tmp_path / "position-health"
    health_receipt = PositionHealthDailyRefreshService(
        state_db_path=state,
        status_path=status_path,
        ledger_db_path=operation_root / "paper_trade_ledger.sqlite",
        coverage_status_path=status_path,
    ).refresh(
        as_of_date=decision_at.date(),
        output_dir=health_output,
        observed_at=observed,
    )
    assert health_receipt["status"] == "passed"
    assert "paper_daily_status_schema_mismatch" not in health_receipt["blockers"]

    evidence = PaperDecisionDeskEvidenceSource(
        state_db_path=state,
        health_baseline_path=health_receipt["latest_path"],
        status_path=status_path,
    ).build(decision_at.date())
    assert "paper_daily_status_schema_mismatch" not in evidence.blockers
    assert not any(
        item.startswith("paper_health_baseline_unavailable:")
        for item in evidence.blockers
    )

    # Rolling compatibility for the previous wrapper receipt: it is accepted
    # only while the complete isolated custody envelope remains intact.
    legacy_status = json.loads(status_path.read_text(encoding="utf-8"))
    legacy_status["schema_version"] = preopen_adapter.SCHEMA_VERSION
    legacy_status.pop("isolated_scope_schema_version", None)
    status_path.write_text(json.dumps(legacy_status), encoding="utf-8")
    legacy_health = PositionHealthDailyRefreshService(
        state_db_path=state,
        status_path=status_path,
        ledger_db_path=operation_root / "paper_trade_ledger.sqlite",
        coverage_status_path=status_path,
    ).refresh(
        as_of_date=decision_at.date(),
        output_dir=tmp_path / "legacy-position-health",
        observed_at=observed,
    )
    assert legacy_health["status"] == "passed"

    legacy_status["writes_D_source"] = True
    status_path.write_text(json.dumps(legacy_status), encoding="utf-8")
    unsafe_health = PositionHealthDailyRefreshService(
        state_db_path=state,
        status_path=status_path,
        ledger_db_path=operation_root / "paper_trade_ledger.sqlite",
        coverage_status_path=status_path,
    ).refresh(
        as_of_date=decision_at.date(),
        output_dir=tmp_path / "unsafe-position-health",
        observed_at=observed,
    )
    assert unsafe_health["status"] == "blocked"
    assert "paper_daily_status_schema_mismatch" in unsafe_health["blockers"]

    second = preopen_adapter.run_isolated(
        now=observed,
        decision_at=decision_at,
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )
    second_scope = second["isolated_scope"]
    assert isinstance(second_scope, dict)
    second_seed = second_scope["state_seed"]
    assert isinstance(second_seed, dict)
    assert second_seed["status"] == "existing_verified"
    assert second["snapshot_appended"] is False
    assert source_state.read_bytes() == source_bytes
    assert baseline.read_bytes() == baseline_bytes
    assert market.read_bytes() == market_bytes


def test_scheduled_adapter_main_waits_then_calls_public_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    _source_state, _baseline, _market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
    )
    public_runner = preopen_adapter.run_paper_portfolio_daily

    def _run_public_runner(**kwargs):
        kwargs["calendar"] = _OpenCalendar()
        return public_runner(**kwargs)

    monkeypatch.setattr(preopen_adapter, "run_paper_portfolio_daily", _run_public_runner)
    monkeypatch.setattr(
        preopen_adapter,
        "_wait_until_taipei_cutoff",
        lambda **_kwargs: datetime.fromisoformat("2026-07-14T08:31:00+08:00"),
    )

    assert preopen_adapter.main([]) == 0
    assert PaperPortfolioSnapshotRepository(state).get("paper-main-20260714") is not None
    run_state = json.loads(
        (
            operation_root
            / "scheduled"
            / "paper_portfolio_isolated"
            / "run_state"
            / "latest.json"
        ).read_text(encoding="utf-8")
    )
    assert run_state["phase"] == "terminal"
    assert run_state["terminal"] is True
    assert run_state["terminal_status"] == "passed"


def test_isolated_preopen_rejects_missing_source_without_creating_repo_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    source_state, _baseline, _market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
    )
    monkeypatch.setattr(preopen_adapter, "SOURCE_STATE_DB", source_state.with_name("missing.sqlite"))
    result = preopen_adapter.run_isolated(
        now=datetime.fromisoformat("2026-07-14T08:31:00+08:00"),
        decision_at=datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )
    assert result["status"] == "blocked"
    assert any("source" in str(item) for item in result["blockers"])
    assert not state.exists()


def test_isolated_preopen_rejects_changed_repository_state_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    _source_state, _baseline, _market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
    )
    observed = datetime.fromisoformat("2026-07-14T08:31:00+08:00")
    decision_at = datetime.fromisoformat("2026-07-14T08:30:00+08:00")
    assert preopen_adapter.run_isolated(
        now=observed,
        decision_at=decision_at,
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )["status"] == "passed"
    with state.open("ab") as stream:
        stream.write(b"tamper")
    result = preopen_adapter.run_isolated(
        now=observed,
        decision_at=decision_at,
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )
    assert result["status"] == "blocked"
    assert "target changed" in str(result["blockers"])


def test_registered_paths_use_one_repository_state_for_eod_and_formal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert preopen_adapter.STATE_DB == eod_adapter.STATE_DB
    assert preopen_adapter.LEDGER_DB == eod_adapter.LEDGER_DB
    monkeypatch.setenv("FORMAL_DAILY_PAPER_SNAPSHOT_DB", str(preopen_adapter.STATE_DB))
    paths = formal_adapter._build_paths(
        source_paths={},
        publication_root=Path("output") / "formal-test-publication",
    )
    assert paths.paper_snapshot_db_path == preopen_adapter.STATE_DB.resolve()
    assert paths.paper_trade_ledger_db_path == preopen_adapter.LEDGER_DB.resolve()


def test_eod_scope_preflight_reads_seeded_repository_state_after_preopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    source_state, _baseline, market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
    )
    recommendation_root = data_root / "output" / "recommendation" / "runs"
    recommendation_root.mkdir(parents=True)
    assert preopen_adapter.run_isolated(
        now=datetime.fromisoformat("2026-07-14T08:31:00+08:00"),
        decision_at=datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
        calendar=_OpenCalendar(),  # type: ignore[arg-type]
    )["status"] == "passed"

    monkeypatch.setattr(eod_adapter, "ROOT", operation_root.parents[1])
    monkeypatch.setattr(eod_adapter, "DEFAULT_DATA_ROOT", data_root)
    monkeypatch.setattr(eod_adapter, "SOURCE_STATE_DB", source_state)
    monkeypatch.setattr(eod_adapter, "OPERATIONAL_ROOT", operation_root)
    monkeypatch.setattr(eod_adapter, "PAPER_STATE_ROOT", state.parent)
    monkeypatch.setattr(eod_adapter, "STATE_DB", state)
    monkeypatch.setattr(
        eod_adapter,
        "STATE_SEED_MANIFEST",
        state.parent / "state_seed_manifest.json",
    )
    monkeypatch.setattr(eod_adapter, "MARKET_DB", market)
    monkeypatch.setattr(eod_adapter, "RECOMMENDATION_ROOT", recommendation_root)
    monkeypatch.setattr(eod_adapter, "CANDIDATE_ROOT", operation_root / "candidates")
    monkeypatch.setattr(eod_adapter, "RECEIPT_ROOT", operation_root / "receipts")
    monkeypatch.setattr(eod_adapter, "LEDGER_DB", operation_root / "paper_trade_ledger.sqlite")
    monkeypatch.setattr(eod_adapter, "SCOPE_MANIFEST", operation_root / "scope_manifest_v2.json")
    monkeypatch.setattr(eod_adapter, "EVENT_CAPTURE_ROOT", operation_root / "event_captures")
    observed = eod_adapter._scope_preflight()
    assert observed["state"]["path"] == str(state.resolve())  # type: ignore[index]
    assert observed["state_seed"]["status"] == "existing_verified"  # type: ignore[index]
    assert observed["market"]["path"] == str(market.resolve())  # type: ignore[index]


def test_isolated_adapter_blocks_before_taipei_cutoff_without_reading_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_source_access() -> dict[str, Path]:
        raise AssertionError("preopen source must not be opened before Taipei cutoff")

    monkeypatch.setattr(preopen_adapter, "_validate_scope", _unexpected_source_access)
    result = preopen_adapter.run_isolated(
        now=datetime.fromisoformat("2026-07-14T07:59:59+08:00"),
        decision_at=datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
    )
    assert result["status"] == "waiting_for_taipei_cutoff"
    assert result["blockers"] == ["taipei_preopen_cutoff_not_reached"]
    assert result["writes_D_source"] is False


def test_isolated_preopen_runs_through_hash_bound_official_calendar_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    decision_at = _recent_test_decision_at()
    decision_date = decision_at.date().isoformat()
    source_decision_date = (
        decision_at.date() - timedelta(days=2)
    ).isoformat()
    previous_price_date = (
        decision_at.date() - timedelta(days=1)
    ).strftime("%Y%m%d")
    _source_state, _baseline, market, _state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
        source_decision_date=source_decision_date,
        market_price_date=previous_price_date,
    )
    cache_path = operation_root / "calendar_cache" / (
        "twse_holiday_schedule_2026_isolated.json"
    )
    _make_calendar_cache(
        cache_path,
        captured_at=decision_at - timedelta(minutes=30),
        max_age=timedelta(days=31),
    )
    monkeypatch.setattr(preopen_adapter, "CALENDAR_CACHE_ROOT", cache_path.parent)

    def _network_is_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("valid official cache must avoid the network")

    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        _network_is_forbidden,
    )
    result = preopen_adapter.run_isolated(
        now=decision_at + timedelta(minutes=1),
        decision_at=decision_at,
    )

    assert result["status"] == "passed"
    assert result["trading_calendar_validated"] is True
    assert result["trading_calendar_is_open"] is True
    assert result["trading_calendar_reason"] == "twse_holiday_schedule_cache_open"
    coverage = result["preopen_coverage"]
    assert isinstance(coverage, dict)
    assert coverage["trading_calendar_validated"] is True


def test_isolated_preopen_rejects_late_official_calendar_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    decision_at = _recent_test_decision_at()
    decision_date = decision_at.date().isoformat()
    source_decision_date = (
        decision_at.date() - timedelta(days=2)
    ).isoformat()
    previous_price_date = (
        decision_at.date() - timedelta(days=1)
    ).strftime("%Y%m%d")
    _source_state, _baseline, market, state = _patch_preopen_paths(
        monkeypatch,
        data_root=data_root,
        operation_root=operation_root,
        source_decision_date=source_decision_date,
        market_price_date=previous_price_date,
    )
    cache_path = operation_root / "calendar_cache" / (
        "twse_holiday_schedule_2026_late_capture.json"
    )
    _make_calendar_cache(
        cache_path,
        captured_at=decision_at + timedelta(minutes=1),
        max_age=timedelta(days=31),
    )
    calendar = OfficialTradingCalendar(
        market,
        calendar_cache_path=cache_path.parent,
    )

    def _network_is_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("late-cache validation must not use the network")

    monkeypatch.setattr(
        "data_module.official_trading_calendar.safe_request",
        _network_is_forbidden,
    )
    result = preopen_adapter.run_isolated(
        now=decision_at + timedelta(minutes=2),
        decision_at=decision_at,
        calendar=calendar,
    )

    assert result["status"] == "degraded_calendar_unknown"
    assert result["trading_calendar_validated"] is False
    assert result["trading_calendar_is_open"] is None
    assert result["trading_calendar_reason"] == (
        "official_calendar_capture_after_decision_at"
    )
    assert PaperPortfolioSnapshotRepository(state).get(
        f"paper-main-{decision_date.replace('-', '')}"
    ) is None


def test_scheduled_wakeup_waits_on_injected_clock_until_taipei_cutoff() -> None:
    readings = iter(
        (
            datetime.fromisoformat("2026-07-14T07:30:00+08:00"),
            datetime.fromisoformat("2026-07-14T08:29:59+08:00"),
            datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
        )
    )
    sleeps: list[float] = []

    reached = preopen_adapter._wait_until_taipei_cutoff(
        now_fn=lambda: next(readings),
        sleep_fn=sleeps.append,
    )

    assert reached == datetime.fromisoformat("2026-07-14T08:30:00+08:00")
    assert sleeps == [60.0, 1.0]


def test_scheduled_wakeup_emits_heartbeat_on_each_clock_observation() -> None:
    readings = iter(
        (
            datetime.fromisoformat("2026-07-14T07:30:00+08:00"),
            datetime.fromisoformat("2026-07-14T08:29:59+08:00"),
            datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
        )
    )
    heartbeats: list[datetime] = []

    reached = preopen_adapter._wait_until_taipei_cutoff(
        now_fn=lambda: next(readings),
        sleep_fn=lambda _seconds: None,
        heartbeat_fn=heartbeats.append,
    )

    assert reached == datetime.fromisoformat("2026-07-14T08:30:00+08:00")
    assert heartbeats == [
        datetime.fromisoformat("2026-07-14T07:30:00+08:00"),
        datetime.fromisoformat("2026-07-14T08:29:59+08:00"),
        datetime.fromisoformat("2026-07-14T08:30:00+08:00"),
    ]


def test_run_state_records_phases_and_marks_stale_nonterminal_previous_run(
    tmp_path: Path,
) -> None:
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    started = datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc)
    first = preopen_adapter._PaperRunState(operation_root)
    first.start(observed_at=started)
    first.heartbeat(
        observed_at=started + timedelta(minutes=1),
        phase="waiting_for_taipei_cutoff",
    )
    first.transition(
        phase="producer_starting",
        observed_at=started + timedelta(minutes=2),
    )

    second = preopen_adapter._PaperRunState(operation_root)
    second.start(observed_at=started + timedelta(minutes=6))

    latest = json.loads(
        (
            operation_root
            / "scheduled"
            / "paper_portfolio_isolated"
            / "run_state"
            / "latest.json"
        ).read_text(encoding="utf-8")
    )
    receipt_names = {
        item.name
        for item in (
            operation_root
            / "scheduled"
            / "paper_portfolio_isolated"
            / "run_state"
            / "receipts"
        ).iterdir()
    }

    assert latest["phase"] == "starting"
    assert latest["terminal"] is False
    previous = latest["previous_run"]
    assert previous["classification"] == "stale_nonterminal_run"
    assert previous["reason"] == "heartbeat_expired"
    assert previous["terminator"] == "unknown"
    assert previous["phase"] == "producer_starting"
    assert any(name.startswith("starting_") for name in receipt_names)
    assert any(name.startswith("waiting_") for name in receipt_names)
    assert any(name.startswith("producer_starting_") for name in receipt_names)
    assert any(name.startswith("stale_") for name in receipt_names)


def test_run_state_diagnoses_event_receipt_conflict_and_incomplete_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    run_state = preopen_adapter._PaperRunState(operation_root)
    run_state.start(observed_at=datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc))

    event_state = dict(run_state.state)
    run_state._write_event("manual_diagnostic", state=event_state)
    receipt = next(
        (
            operation_root
            / "scheduled"
            / "paper_portfolio_isolated"
            / "run_state"
            / "receipts"
        ).glob("manual_diagnostic_*.json")
    )
    receipt.write_bytes(b"tampered\n")

    run_state._write_event("manual_diagnostic", state=event_state)
    latest = json.loads(run_state.latest_path.read_text(encoding="utf-8"))
    assert latest["event_write_status"] == "conflict"
    assert latest["event_write_error"] == "immutable_event_receipt_bytes_mismatch"

    original_open = Path.open

    class _PartialWriter:
        def __init__(self, stream):
            self._stream = stream
            self._raised = False

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            self._stream.close()

        def write(self, payload: bytes) -> int:
            if not self._raised:
                self._raised = True
                self._stream.write(payload[: max(1, len(payload) // 2)])
                self._stream.flush()
                raise OSError("simulated_partial_event_write")
            return self._stream.write(payload)

        def flush(self) -> None:
            self._stream.flush()

        def fileno(self) -> int:
            return self._stream.fileno()

    def _partial_event_write(
        path: Path,
        mode: str = "r",
        *args: object,
        **kwargs: object,
    ):
        stream = original_open(path, mode, *args, **kwargs)
        if path.parent == run_state.receipt_root and mode == "xb":
            return _PartialWriter(stream)
        return stream

    monkeypatch.setattr(Path, "open", _partial_event_write)
    run_state._write_event("partial_diagnostic", state=event_state)
    latest = json.loads(run_state.latest_path.read_text(encoding="utf-8"))
    assert latest["event_write_status"] == "incomplete"
    assert latest["event_write_error"] == "OSError:simulated_partial_event_write"
    assert not list(run_state.receipt_root.glob("partial_diagnostic_*.json"))
    assert not list(run_state.receipt_root.glob(".partial_diagnostic_*.tmp"))

    monkeypatch.setattr(Path, "open", original_open)
    run_state._write_event("partial_diagnostic", state=event_state)
    receipt = next(run_state.receipt_root.glob("partial_diagnostic_*.json"))
    published = receipt.read_bytes()
    assert json.loads(published.decode("utf-8"))["event"] == "partial_diagnostic"
    latest = json.loads(run_state.latest_path.read_text(encoding="utf-8"))
    assert latest["event_write_status"] == "persisted"

    run_state._write_event("partial_diagnostic", state=event_state)
    assert receipt.read_bytes() == published
    latest = json.loads(run_state.latest_path.read_text(encoding="utf-8"))
    assert latest["event_write_status"] == "already_present_verified"

    original_fsync = preopen_adapter.os.fsync
    fsync_calls = 0

    def _interrupt_fsync(file_descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError("simulated_fsync_interruption")
        original_fsync(file_descriptor)

    monkeypatch.setattr(preopen_adapter.os, "fsync", _interrupt_fsync)
    run_state._write_event("fsync_diagnostic", state=event_state)
    latest = json.loads(run_state.latest_path.read_text(encoding="utf-8"))
    assert latest["event_write_status"] == "incomplete"
    assert latest["event_write_error"] == "OSError:simulated_fsync_interruption"
    assert not list(run_state.receipt_root.glob("fsync_diagnostic_*.json"))
    assert not list(run_state.receipt_root.glob(".fsync_diagnostic_*.tmp"))

    monkeypatch.setattr(preopen_adapter.os, "fsync", original_fsync)
    run_state._write_event("fsync_diagnostic", state=event_state)
    fsync_receipt = next(run_state.receipt_root.glob("fsync_diagnostic_*.json"))
    fsync_bytes = fsync_receipt.read_bytes()
    assert json.loads(fsync_bytes.decode("utf-8"))["event"] == "fsync_diagnostic"
    run_state._write_event("fsync_diagnostic", state=event_state)
    assert fsync_receipt.read_bytes() == fsync_bytes


def test_paper_portfolio_taipei_wake_is_five_minutes_before_cutoff_in_both_dst_modes() -> None:
    pacific = ZoneInfo("America/Los_Angeles")
    taipei_zone = ZoneInfo(preopen_adapter.SCHEDULED_WAKE_TIMEZONE)
    for local_date, expected_pacific_time in (
        ("2026-01-13", "16:25"),
        ("2026-07-14", "17:25"),
    ):
        trigger = datetime.fromisoformat(
            f"{local_date}T{preopen_adapter.SCHEDULED_WAKE_LOCAL_TIME}:00+08:00"
        )
        taipei = trigger.astimezone(taipei_zone)
        pacific_time = trigger.astimezone(pacific)
        cutoff = taipei.replace(hour=8, minute=30)

        assert taipei.strftime("%H:%M%z") == "08:25+0800"
        assert cutoff - taipei == timedelta(minutes=5)
        assert pacific_time.strftime("%H:%M") == expected_pacific_time
        assert pacific_time.date() < taipei.date()
