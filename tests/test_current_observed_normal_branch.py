from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DAY = date(2026, 10, 5)


def _write_hash_bound_calendar(tmp_path: Path, session_day: date = SESSION_DAY) -> Path:
    """建立隔離且可重新驗證原始回應雜湊的官方年曆快取。"""
    from data_module.official_trading_calendar_cache import (
        build_twse_calendar_cache,
        write_twse_calendar_cache,
    )

    cache_root = tmp_path / "calendar"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = cache_root / f"twse_holiday_schedule_{session_day.year}_fixture.json"
    # Keep the fixture's availability clock deterministic. The consumers below
    # verify against explicit 2026-10-05 Taipei clocks, so a wall-clock capture
    # would become a future-dated cache once the test is run after those clocks.
    captured_at = datetime(
        session_day.year,
        session_day.month,
        session_day.day,
        11,
        0,
        tzinfo=TAIPEI,
    )
    raw_response = json.dumps(
        [
            {
                "Date": f"{session_day.year - 1911:03d}0101",
                "Name": "元旦",
                "Weekday": "Thursday",
                "Description": "市場休市",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=session_day.year,
        raw_response=raw_response,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_url=(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
            f"?queryYear={session_day.year - 1911}"
        ),
    )
    write_twse_calendar_cache(cache_path, cache, allowed_root=tmp_path)
    return cache_root


def _freeze_official_calendar_clock(
    monkeypatch: pytest.MonkeyPatch,
    observed_at: datetime,
) -> None:
    from data_module import official_trading_calendar

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return observed_at.replace(tzinfo=None)
            return observed_at.astimezone(tz)

    monkeypatch.setattr(official_trading_calendar, "datetime", _FrozenDateTime)


class _CaptureProvider:
    def __init__(self, database_path: Path, trading_dates: tuple[str, ...]) -> None:
        self.database_path = database_path
        self.trading_dates = trading_dates
        self.date_queries: list[tuple[str, ...]] = []
        self.load_calls: list[dict[str, object]] = []

    def list_trading_dates(self, *, start_date: str, end_date: str, symbols: tuple[str, ...]):
        self.date_queries.append(tuple(symbols))
        return self.trading_dates

    def load(self, **kwargs):
        self.load_calls.append(dict(kwargs))
        return SimpleNamespace()


def _capture_args(session_day: date, cache_root: Path | None) -> SimpleNamespace:
    return SimpleNamespace(
        capture_current=True,
        decision_date=session_day.isoformat(),
        fixed_round_trip_cost_bp=50,
        calendar_cache_path=cache_root,
        temporary_closure_cache_path=None,
    )


def _invoke_capture(
    tmp_path: Path,
    provider: _CaptureProvider,
    *,
    session_day: date,
    cache_root: Path | None,
    checked_at: datetime,
) -> dict[str, object]:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    source_db = provider.database_path
    return daily_learning._capture_current_if_requested(
        args=_capture_args(session_day, cache_root),
        config=SimpleNamespace(data_root=tmp_path / "data"),
        output_root=tmp_path / "output",
        source_db=source_db,
        provider=provider,
        symbols=("1477",),
        run_result=SimpleNamespace(candidate_root=None, candidate_id=None),
        replay_config=SimpleNamespace(history_start_date="2025-01-01"),
        source_contract_audit={"source_contract": {"status": "ready"}},
        observed_at=checked_at,
    )


def test_pre_close_capture_waits_before_querying_same_day_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    cache_root = _write_hash_bound_calendar(tmp_path)
    source_db = tmp_path / "source.sqlite"
    sqlite3.connect(source_db).close()
    provider = _CaptureProvider(source_db, (SESSION_DAY.isoformat(),))
    checked_at = datetime(2026, 10, 5, 12, 0, tzinfo=TAIPEI)
    _freeze_official_calendar_clock(monkeypatch, checked_at)
    monkeypatch.setattr(
        daily_learning,
        "_capture_source_contract_binding",
        lambda _: ({"decision_date": SESSION_DAY.isoformat(), "symbols": ["1477"]}, None),
    )

    result = _invoke_capture(
        tmp_path,
        provider,
        session_day=SESSION_DAY,
        cache_root=cache_root,
        checked_at=checked_at,
    )

    assert result["status"] == "pending"
    assert result["reason"] == "official_session_not_closed_yet_wait_for_scheduled_close"
    assert result["same_day_rows_consulted"] is False
    assert provider.date_queries == []
    assert provider.load_calls == []


def test_after_close_uses_hash_bound_cache_before_reading_symbol_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    cache_root = _write_hash_bound_calendar(tmp_path)
    source_db = tmp_path / "source.sqlite"
    sqlite3.connect(source_db).close()
    provider = _CaptureProvider(source_db, (SESSION_DAY.isoformat(),))
    checked_at = datetime(2026, 10, 5, 14, 0, tzinfo=TAIPEI)
    _freeze_official_calendar_clock(monkeypatch, checked_at)
    binding_calls: list[object] = []

    class _EmptyFeatureBuilder:
        def __init__(self, registry) -> None:
            pass

        def compute(self, snapshot, *, industry_index_name_by_symbol):
            return ()

    def _binding(audit):
        binding_calls.append(audit)
        return {"decision_date": SESSION_DAY.isoformat(), "symbols": ["1477"]}, None

    monkeypatch.setattr(daily_learning, "_capture_source_contract_binding", _binding)
    monkeypatch.setattr(daily_learning, "HistoricalFeatureBuilder", _EmptyFeatureBuilder)

    result = _invoke_capture(
        tmp_path,
        provider,
        session_day=SESSION_DAY,
        cache_root=cache_root,
        checked_at=checked_at,
    )

    assert binding_calls
    assert provider.date_queries == [("1477",)]
    assert provider.load_calls
    assert result["status"] == "skipped"
    assert result["reason"] == "live_capture_feature_rows_missing"


@pytest.mark.parametrize(
    ("has_local_session", "expected_reason"),
    [
        (False, "official_trading_calendar_unresolved_fail_closed"),
        (True, "official_trading_calendar_evidence_unverified_fail_closed"),
    ],
)
def test_unknown_or_unverified_calendar_fails_before_row_query(
    tmp_path: Path,
    has_local_session: bool,
    expected_reason: str,
) -> None:
    source_db = tmp_path / "source.sqlite"
    with sqlite3.connect(source_db) as connection:
        if has_local_session:
            connection.execute('CREATE TABLE market_indices ("日期" TEXT)')
            connection.execute(
                'INSERT INTO market_indices("日期") VALUES (?)',
                (SESSION_DAY.strftime("%Y%m%d"),),
            )
    provider = _CaptureProvider(source_db, (SESSION_DAY.isoformat(),))
    cache_root = tmp_path / "empty-calendar"
    cache_root.mkdir()

    result = _invoke_capture(
        tmp_path,
        provider,
        session_day=SESSION_DAY,
        cache_root=cache_root,
        checked_at=datetime(2026, 10, 5, 14, 0, tzinfo=TAIPEI),
    )

    assert result["status"] == "failed"
    assert result["reason"] == expected_reason
    assert provider.date_queries == []
    assert provider.load_calls == []


def test_after_close_without_exact_symbol_row_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    cache_root = _write_hash_bound_calendar(tmp_path)
    source_db = tmp_path / "source.sqlite"
    sqlite3.connect(source_db).close()
    provider = _CaptureProvider(source_db, ())
    checked_at = datetime(2026, 10, 5, 14, 0, tzinfo=TAIPEI)
    _freeze_official_calendar_clock(monkeypatch, checked_at)
    monkeypatch.setattr(
        daily_learning,
        "_capture_source_contract_binding",
        lambda _: ({"decision_date": SESSION_DAY.isoformat(), "symbols": ["1477"]}, None),
    )

    result = _invoke_capture(
        tmp_path,
        provider,
        session_day=SESSION_DAY,
        cache_root=cache_root,
        checked_at=checked_at,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "official_trading_day_explicit_symbol_rows_missing_fail_closed"
    assert provider.date_queries == [("1477",)]
    assert provider.load_calls == []


def _main_test_sample(decision_day: date):
    from ml_module.recommendation_calibration_training import RecommendationCalibrationSample

    sample_day = (decision_day - timedelta(days=45)).isoformat()
    feature_day = (date.fromisoformat(sample_day) - timedelta(days=1)).isoformat()
    label_day = (date.fromisoformat(sample_day) + timedelta(days=20)).isoformat()
    return RecommendationCalibrationSample.from_forward_return(
        row_id=f"fixture-{sample_day}-1101",
        symbol="1101",
        decision_date=sample_day,
        feature_as_of_date=feature_day,
        feature_available_date=feature_day,
        label_end_date=label_day,
        label_available_date=label_day,
        feature_values=(0, 1),
        stock_return_bp=100,
        benchmark_return_bp=50,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=20,
        rule_probability_bp=5_000,
        rule_after_cost_probability_bp=5_000,
    )


def _prepare_main_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    decision_day: date,
    checked_at: datetime,
    replay_samples: tuple[object, ...],
    use_real_current_snapshot: bool = False,
    raise_revision_error: bool = False,
) -> tuple[object, dict[str, list[object]]]:
    import scripts.scheduled.run_daily_recommendation_learning as daily_learning

    from data_module.ml_daily_price_revision_gate import DailyPriceSourceRevisionError

    data_root = tmp_path / "formal-data"
    output_root = tmp_path / "learning-shadow"
    source_db = tmp_path / "source.sqlite"
    source_db.touch()
    state: dict[str, list[object]] = {
        "runner_calls": [],
        "capture_persist_calls": [],
        "fit_calls": [],
        "audit_snapshots": [],
        "provider_date_queries": [],
    }

    class _Config:
        def __init__(self, *, data_root=None, output_root=None) -> None:
            self.data_root = Path(data_root or tmp_path / "formal-data")
            self.output_root = Path(output_root or tmp_path / "learning-shadow")
            self.db_file = source_db

    class _Provider:
        def __init__(self, database_path: Path) -> None:
            self.database_path = Path(database_path)

        def list_trading_dates(self, **kwargs):
            state["provider_date_queries"].append(dict(kwargs))
            return ()

    class _ReplayResult:
        source_fingerprint = "sha256:" + "a" * 64
        dataset_id = "fixture-replay"
        dataset_hash = "sha256:" + "b" * 64

        def __init__(self) -> None:
            self.samples = replay_samples
            self.decision_dates = tuple(sorted({row.decision_date for row in replay_samples}))

        def persist(self, root: Path) -> Path:
            return Path(root) / "replay-manifest.json"

        def to_dict(self) -> dict[str, int]:
            return {"sample_count": len(self.samples)}

    class _ReplayService:
        def __init__(self, provider) -> None:
            self.provider = provider

        def build(self, config):
            if raise_revision_error:
                raise DailyPriceSourceRevisionError("fixture source revision gate")
            return _ReplayResult()

    class _Runner:
        def run(self, **kwargs):
            state["runner_calls"].append(dict(kwargs))
            return SimpleNamespace(
                run_id="fixture-run",
                status="completed",
                reason="fixture_only",
                receipt_path=str(tmp_path / "run-receipt.json"),
                latest_status_path=str(tmp_path / "latest-status.json"),
                dataset_id="fixture-dataset",
                dataset_hash="sha256:" + "c" * 64,
                candidate_id=None,
                candidate_root=None,
                decision="retain_current",
                decision_reason="fixture_only",
                training_lineage_manifest_hash=None,
                training_lineage_manifest_path=None,
                training_lineage_status="not_created",
                idempotent_replay=False,
            )

    monkeypatch.setattr(daily_learning, "_taipei_now", lambda: checked_at)
    monkeypatch.setattr(daily_learning, "TWStockConfig", _Config)
    monkeypatch.setattr(
        daily_learning,
        "resolve_recommendation_learning_output_root",
        lambda *, data_root, explicit_output_root: Path(explicit_output_root),
    )
    monkeypatch.setattr(daily_learning, "_cost_scenario_root_conflict", lambda *_: None)
    monkeypatch.setattr(
        daily_learning,
        "_resolve_symbols",
        lambda **_: (("1101",), "explicit_test_symbols"),
    )
    monkeypatch.setattr(daily_learning, "_build_runner", lambda *args, **kwargs: _Runner())
    monkeypatch.setattr(daily_learning, "MLHistoricalSnapshotProvider", _Provider)
    monkeypatch.setattr(daily_learning, "RecommendationHistoricalReplayService", _ReplayService)
    monkeypatch.setattr(
        daily_learning,
        "_audit_source_contract",
        lambda **kwargs: (
            state["audit_snapshots"].append(kwargs["current_observed_snapshot"])
            or {"source_contract": {"status": "ready"}}
        ),
    )
    monkeypatch.setattr(
        daily_learning,
        "_inspect_dependencies",
        lambda **_: {
            "data_status": "ready",
            "outcome_status": "ready",
            "drift_status": "clean",
            "recovery_policy": "normal",
            "source_contract": {"status": "ready"},
            "model_performance": {"status": "clean"},
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(daily_learning, "_read_challenger_pointer", lambda _: None)
    monkeypatch.setattr(daily_learning, "_load_frozen_challenger", lambda _: None)
    monkeypatch.setattr(daily_learning, "_load_natural_training_samples", lambda **_: ())
    monkeypatch.setattr(daily_learning, "_build_training_quality", lambda **_: {})
    if not use_real_current_snapshot:
        monkeypatch.setattr(
            daily_learning,
            "_current_observed_feature_snapshot_for_learning",
            lambda **_: {
                "status": "pending",
                "reason": "fixture_exact_current_snapshot_not_present",
                "research_only": True,
                "historical_pit_eligible": False,
                "formal_training_allowed": False,
            },
        )
    if not use_real_current_snapshot:
        monkeypatch.setattr(
            daily_learning,
            "_capture_current_if_requested",
            lambda **_: {"status": "pending", "reason": "fixture_entry_pending"},
        )
    monkeypatch.setattr(
        daily_learning,
        "_persist_current_observed_input_capture",
        lambda **kwargs: (
            state["capture_persist_calls"].append(dict(kwargs))
            or {
                "status": "pending",
                "reason": "entry_observation_pending",
                "capture_eligible": False,
                "historical_pit_eligible": False,
                "formal_training_allowed": False,
                "promotion_credit_created": False,
            }
        ),
    )

    def _fit_current_research(**kwargs):
        state["fit_calls"].append(dict(kwargs))
        return {
            "status": "completed",
            "reason": "older_immutable_receipts_scanned",
            "matured_sample_count": 3,
            "matured_training_row_count": 3,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "promotion_credit_created": False,
        }

    monkeypatch.setattr(daily_learning, "_current_observed_natural_research_fit", _fit_current_research)
    monkeypatch.setattr(daily_learning, "_scan_active_model_evidence", lambda **_: {"status": "pending", "matured_sample_count": 0})
    monkeypatch.setattr(daily_learning, "_inspect_active_model_performance", lambda **_: {"status": "clean", "diagnostics": []})
    monkeypatch.setattr(daily_learning, "_dependencies_require_emergency", lambda _: False)
    monkeypatch.setattr(daily_learning, "NaturalMaturitySessionResolver", lambda **_: object())
    monkeypatch.setattr(daily_learning, "_natural_maturity_calendar_paths", lambda **_: (tmp_path / "calendar", None))
    monkeypatch.setattr(daily_learning, "_natural_maturity_context", lambda **_: {"evaluation_date": decision_day.isoformat()})
    monkeypatch.setattr(
        daily_learning,
        "_cli_payload",
        lambda **kwargs: {
            "decision_date": kwargs["decision_day"].isoformat(),
            "live_capture": dict(kwargs["live_capture"]),
            "dependencies": dict(kwargs["dependencies"]),
            "replay": kwargs["replay_result"].to_dict()
            if hasattr(kwargs["replay_result"], "to_dict")
            else None,
        },
    )

    args = [
        "--data-root", str(data_root),
        "--output-root", str(output_root),
        "--source-db", str(source_db),
        "--symbols", "1101",
        "--history-start-date", "2025-01-01",
        "--replay-start-date", (decision_day - timedelta(days=60)).isoformat(),
        "--replay-end-date", decision_day.isoformat(),
        "--decision-date", decision_day.isoformat(),
        "--training-as-of", decision_day.isoformat(),
        "--max-decision-dates", "1",
        "--current-observed-expected-raw-run-id", "fixture-raw-run",
        "--current-observed-expected-cycle-terminal", str(tmp_path / "terminal.json"),
        "--current-observed-expected-cycle-terminal-sha256", "sha256:" + "d" * 64,
    ]
    return SimpleNamespace(module=daily_learning, args=args), state


@pytest.mark.parametrize("replay_sample_count", [0, 1])
def test_normal_and_empty_replay_keep_current_research_out_of_formal_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    replay_sample_count: int,
) -> None:
    checked_at = datetime.now(TAIPEI)
    decision_day = checked_at.date()
    replay_samples = (_main_test_sample(decision_day),) if replay_sample_count else ()
    harness, state = _prepare_main_lane(
        tmp_path,
        monkeypatch,
        decision_day=decision_day,
        checked_at=checked_at,
        replay_samples=replay_samples,
    )

    assert harness.module.main(harness.args) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert len(state["runner_calls"]) == 1
    assert tuple(state["runner_calls"][0]["samples"]) == replay_samples
    assert payload["training_sample_count"] == replay_sample_count
    assert payload["natural_training_sample_count"] == 0
    assert len(state["capture_persist_calls"]) == 1
    assert len(state["fit_calls"]) == 1
    lane = payload["current_observed_natural_lane"]
    assert lane["current_observed_input_capture"]["status"] == "pending"
    assert lane["current_observed_natural_research"]["matured_training_row_count"] == 3
    for field in ("historical_pit_eligible", "formal_training_allowed", "promotion_credit_created"):
        assert lane["current_observed_natural_research"][field] is False
    assert payload["live_capture"]["current_observed_input_capture"] == lane[
        "current_observed_input_capture"
    ]
    assert payload["live_capture"]["current_observed_natural_research"] == lane[
        "current_observed_natural_research"
    ]


def test_legacy_source_revision_failure_keeps_current_research_status_separate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checked_at = datetime.now(TAIPEI)
    harness, state = _prepare_main_lane(
        tmp_path,
        monkeypatch,
        decision_day=checked_at.date(),
        checked_at=checked_at,
        replay_samples=(),
        raise_revision_error=True,
    )

    assert harness.module.main(harness.args) == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["dependencies"]["current_observed_input_capture"]["status"] == "pending"
    assert payload["dependencies"]["current_observed_natural_research"]["matured_training_row_count"] == 3
    assert state["runner_calls"][0]["samples"] == ()
    assert state["fit_calls"]
    for field in ("historical_pit_eligible", "formal_training_allowed", "promotion_credit_created"):
        assert payload["dependencies"]["current_observed_natural_research"][field] is False


def test_skip_capture_still_scans_older_matured_current_observed_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checked_at = datetime.now(TAIPEI)
    harness, state = _prepare_main_lane(
        tmp_path,
        monkeypatch,
        decision_day=checked_at.date(),
        checked_at=checked_at,
        replay_samples=(),
    )
    harness.args.append("--skip-capture-current")

    assert harness.module.main(harness.args) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    live_capture = payload["live_capture"]
    input_capture = live_capture["current_observed_input_capture"]
    research = live_capture["current_observed_natural_research"]

    assert input_capture["status"] == "not_requested"
    assert input_capture["reason"] == "current_capture_disabled_by_caller"
    assert state["capture_persist_calls"] == []
    assert len(state["fit_calls"]) == 1
    assert research["reason"] == "older_immutable_receipts_scanned"
    assert research["matured_training_row_count"] == 3
    assert payload["training_sample_count"] == 0
    assert payload["natural_training_sample_count"] == 0
    for field in ("historical_pit_eligible", "formal_training_allowed", "promotion_credit_created"):
        assert research[field] is False


def test_historical_main_run_never_captures_or_fits_current_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checked_at = datetime.now(TAIPEI)
    decision_day = checked_at.date() - timedelta(days=1)
    harness, state = _prepare_main_lane(
        tmp_path,
        monkeypatch,
        decision_day=decision_day,
        checked_at=checked_at,
        replay_samples=(),
        use_real_current_snapshot=True,
    )

    assert harness.module.main(harness.args) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    snapshot = state["audit_snapshots"][0]
    assert snapshot["status"] == "pending"
    assert snapshot["reason"] == "current_observation_date_differs_from_decision_date"
    assert state["provider_date_queries"] == []
    assert state["capture_persist_calls"] == []
    assert state["fit_calls"] == []
    assert payload["live_capture"]["reason"] == "capture_current_requires_current_asia_taipei_date"
    assert payload["current_observed_natural_lane"]["reason"] == "current_evaluation_date_required"
    assert payload["training_sample_count"] == 0
    assert payload["natural_training_sample_count"] == 0


def test_normal_lane_preserves_fitted_research_only_status(tmp_path, monkeypatch, capsys):
    checked_at = datetime.now(TAIPEI)
    harness, state = _prepare_main_lane(tmp_path, monkeypatch, decision_day=checked_at.date(),
                                      checked_at=checked_at, replay_samples=())
    monkeypatch.setattr(harness.module, "_current_observed_natural_research_fit", lambda **kwargs: {
        "status": "fitted_research_only", "historical_pit_eligible": False,
        "formal_training_allowed": False, "promotion_credit_created": False})
    assert harness.module.main(harness.args) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    lane = payload["current_observed_natural_lane"]
    assert lane["status"] == "fitted_research_only"
    assert lane["current_observed_natural_research"]["formal_training_allowed"] is False
