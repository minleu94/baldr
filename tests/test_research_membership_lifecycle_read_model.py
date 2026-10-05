from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
    DailyMarketFeatureSnapshotService,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DailyMarketSnapshotRepository,
    VerifiedDailyMarketSnapshot,
    canonical_snapshot_json_bytes,
    cohort_identity_sha256,
    snapshot_artifact_relpath,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
from app_module.research_membership_lifecycle import (
    ExpectedSession,
    HistoryCoverage,
    LifecycleStatus,
)
from app_module.research_membership_lifecycle_read_model import (
    read_membership_lifecycle,
)
from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)


TAIPEI = timezone(timedelta(hours=8))
SCHEMA_SHA = "a" * 64
CONDITION_KEYS = ("close_above_ma20",)


def _snapshot_payload(
    stock_code: str, decision_date: date, *, matches: bool
) -> dict[str, Any]:
    market_dates: list[date] = []
    cursor = decision_date
    while len(market_dates) < 60:
        if cursor.weekday() < 5:
            market_dates.append(cursor)
        cursor -= timedelta(days=1)
    market_dates.reverse()
    points = []
    for index, market_date in enumerate(market_dates):
        close = Decimal(100 + index)
        points.append(
            StockPricePointDTO(
                data_date=market_date.isoformat(),
                open_price=close,
                high_price=close + Decimal("2"),
                low_price=close - Decimal("2"),
                close_price=close,
                volume=1000 + index,
                turnover=close * Decimal(1000 + index),
                change=Decimal("0"),
                available_at=f"{decision_date.isoformat()}T14:00:00+08:00",
                source_id="sqlite.daily_prices",
                source_snapshot_hash=f"{stock_code}-{decision_date}-{index:03d}",
                quality="observed",
            )
        )
    market_close = points[-1].close_price
    assert market_close is not None
    ma20 = market_close - Decimal("1") if matches else market_close + Decimal("1")
    technical = StockTechnicalSnapshotDTO(
        data_date=decision_date.isoformat(),
        indicators=(
            StockMetricDTO(
                key="MA20",
                label="MA20",
                value=ma20,
                unit="TWD/share",
                data_as_of=decision_date.isoformat(),
                source_id="sqlite.technical_indicators",
                quality="observed",
            ),
            StockMetricDTO(
                key="MA60",
                label="MA60",
                value=market_close - Decimal("2"),
                unit="TWD/share",
                data_as_of=decision_date.isoformat(),
                source_id="sqlite.technical_indicators",
                quality="observed",
            ),
        ),
        available_at=f"{decision_date.isoformat()}T14:00:00+08:00",
        source_id="fixture.technical_indicators",
        quality="observed",
    )
    return DailyMarketFeatureSnapshotService().project(
        stock_code=stock_code,
        decision_date=decision_date,
        scope_identity=f"fixture:{SCHEMA_SHA}:stock:{stock_code}",
        price_points=points,
        technical=technical,
    ).to_dict()


def _write_snapshot(
    root: Path,
    decision_date: date,
    *,
    matches: bool,
    published_at: datetime | None = None,
    cohort_id: str = "ux09-lifecycle-fixture",
    stock_code: str = "2382",
) -> VerifiedDailyMarketSnapshot:
    payload = _snapshot_payload(stock_code, decision_date, matches=matches)
    artifact_bytes = canonical_snapshot_json_bytes(payload)
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_relpath = snapshot_artifact_relpath(artifact_sha)
    artifact_path = root / Path(artifact_relpath)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    source_refs = {
        "database": r"C:\fixture\market.sqlite",
        "schema_identity_sha256": SCHEMA_SHA,
        "price": r"C:\fixture\market.sqlite#daily_prices",
        "technical": r"C:\fixture\market.sqlite#technical_indicators",
    }
    manifest: dict[str, Any] = {
        "schema_version": DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
        "manifest_identity_sha256": "0" * 64,
        "cohort_id": cohort_id,
        "cohort_identity": cohort_identity_sha256(cohort_id, (stock_code,)),
        "declared_stock_codes": [stock_code],
        "decision_date": decision_date.isoformat(),
        "decision_cutoff": datetime.combine(
            decision_date, datetime.min.time(), tzinfo=TAIPEI
        ).replace(hour=15).isoformat(),
        "decision_timezone": "Asia/Taipei",
        "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
        "method_contracts": method_contracts_payload(),
        "method_contracts_sha256": method_contracts_sha256(),
        "stocks": [
            {
                "stock_code": stock_code,
                "source_identity": payload["scope_identity"],
                "input_fingerprint_sha256": payload["input_fingerprint_sha256"],
                "snapshot_identity_sha256": payload["snapshot_identity_sha256"],
                "artifact_sha256": artifact_sha,
                "artifact_relpath": artifact_relpath,
                "source_refs": source_refs,
            }
        ],
        "missing_stocks": [],
        "counts": {"declared": 1, "published": 1, "missing": 0},
        "completeness": "complete_declared_cohort",
        "published_at": (
            published_at
            or datetime.combine(
                decision_date, datetime.min.time(), tzinfo=TAIPEI
            ).replace(hour=16)
        ).isoformat(),
        "policy": {"research_only": True, "historical_pit_eligible": False},
    }
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(
        manifest
    )
    manifest_bytes = canonical_snapshot_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = root / Path(snapshot_manifest_relpath(manifest_sha))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    return DailyMarketSnapshotRepository(root).load_manifest(
        manifest_sha, cohort_id, decision_date, expected_stock_codes=(stock_code,)
    )


class _VerifiedSessions:
    def __init__(self, previous: dict[date, date | None]) -> None:
        self.previous = previous
        self.as_of_by_date: list[tuple[date, datetime]] = []

    def expected_session(self, target_date: date, *, as_of: datetime) -> ExpectedSession:
        self.as_of_by_date.append((target_date, as_of))
        return ExpectedSession(
            calendar_key="fixture.calendar",
            calendar_version="v1",
            expected_previous_date=self.previous.get(target_date),
            verified=target_date in self.previous,
            calendar_manifest_id="fixture-calendar-v1",
            calendar_manifest_sha256="b" * 64,
        )


def _read(
    root: Path,
    current: VerifiedDailyMarketSnapshot,
    sessions: _VerifiedSessions,
):
    return read_membership_lifecycle(
        DailyMarketSnapshotRepository(root),
        current,
        CONDITION_KEYS,
        "AND",
        session_provider=sessions,
    )


def test_read_model_replays_three_complete_sessions_with_pinned_sources(tmp_path: Path) -> None:
    day1, day2, day3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
    _write_snapshot(tmp_path, day1, matches=True)
    _write_snapshot(tmp_path, day2, matches=False)
    current = _write_snapshot(tmp_path, day3, matches=True)
    sessions = _VerifiedSessions({day1: None, day2: day1, day3: day2})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]
    replay = result.to_dict()

    assert result.history_coverage is HistoryCoverage.COMPLETE
    assert row.status is LifecycleStatus.RESELECTED
    assert row.previous_date == day2
    assert len(row.source_refs) == 3
    assert len(replay["rows_by_stock"]["2382"]["classification"]["source_observations"]) == 3
    assert replay["result_id"] == result.to_dict()["result_id"]
    assert result.current_manifest_sha256 == current.manifest_sha256
    assert result.current_manifest_identity_sha256 == current.manifest_identity_sha256
    assert result.rows == (row,)
    assert all(observed_at.date() == target for target, observed_at in sessions.as_of_by_date)


def test_other_cohort_does_not_enter_current_membership_history(tmp_path: Path) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    _write_snapshot(
        tmp_path, day1, matches=False, cohort_id="different-research-cohort"
    )
    current = _write_snapshot(tmp_path, day2, matches=True)
    sessions = _VerifiedSessions({day2: day1})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]

    assert row.status is LifecycleStatus.FIRST_OBSERVATION
    assert row.history_observation_ids == ()
    assert result.history_manifest_ids == (current.manifest_sha256,)


def test_stock_scope_change_is_not_treated_as_first_selection(tmp_path: Path) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    previous = _write_snapshot(tmp_path, day1, matches=False, stock_code="1101")
    current = _write_snapshot(tmp_path, day2, matches=True)
    sessions = _VerifiedSessions({day1: None, day2: day1})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]

    assert row.status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert row.reason == "history_snapshot_stock_scope_changed"
    assert result.history_manifest_ids == tuple(
        sorted((current.manifest_sha256, previous.manifest_sha256))
    )


def test_visible_same_day_revisions_are_preserved_as_a_conflict(tmp_path: Path) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    _write_snapshot(
        tmp_path,
        day1,
        matches=True,
        published_at=datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI),
    )
    revision = _write_snapshot(
        tmp_path,
        day1,
        matches=False,
        published_at=datetime(2026, 10, 5, 17, 0, tzinfo=TAIPEI),
    )
    current = _write_snapshot(tmp_path, day2, matches=True)
    sessions = _VerifiedSessions({day1: None, day2: day1})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]

    assert row.status is LifecycleStatus.INCOMPARABLE
    assert row.reason == "same_session_multiple_observations_or_revisions"
    assert revision.manifest_sha256 in result.history_manifest_ids


def test_future_publication_is_excluded_from_current_as_of_history(tmp_path: Path) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    prior = _write_snapshot(tmp_path, day1, matches=True)
    future_revision = _write_snapshot(
        tmp_path,
        day1,
        matches=False,
        published_at=datetime(2026, 10, 7, 10, 0, tzinfo=TAIPEI),
    )
    current = _write_snapshot(tmp_path, day2, matches=True)
    sessions = _VerifiedSessions({day1: None, day2: day1})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]

    assert row.status is LifecycleStatus.CONTINUING
    assert prior.manifest_sha256 in result.history_manifest_ids
    assert future_revision.manifest_sha256 not in result.history_manifest_ids


def test_missing_expected_session_is_a_boundary_not_a_no_match(tmp_path: Path) -> None:
    day1, day2, day3 = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
    _write_snapshot(tmp_path, day1, matches=False)
    current = _write_snapshot(tmp_path, day3, matches=True)
    sessions = _VerifiedSessions({day1: None, day3: day2})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]

    assert row.status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert row.reason == "expected_session_gap_or_missing_observation"
    assert row.current_state.value == "match"


def test_later_day_publication_is_an_explicit_historical_boundary(
    tmp_path: Path,
) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    _write_snapshot(
        tmp_path,
        day1,
        matches=False,
        published_at=datetime(2026, 10, 6, 10, 0, tzinfo=TAIPEI),
    )
    current = _write_snapshot(tmp_path, day2, matches=True)
    sessions = _VerifiedSessions({day1: None, day2: day1})

    result = _read(tmp_path, current, sessions)
    row = result.rows_by_stock["2382"]
    replay_sources = row.to_dict()["classification"]["source_observations"]

    assert row.status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert row.reason == "history_snapshot_published_after_decision_day"
    assert "history_snapshot_published_after_decision_day" in row.warnings
    assert replay_sources[0]["source_available_at"] is None
    assert any(
        item["decision_date"] == day1.isoformat() and item["state"] == "unknown"
        for item in replay_sources
    )
    history_as_of = [as_of for target, as_of in sessions.as_of_by_date if target == day1]
    assert history_as_of == [datetime(2026, 10, 6, 10, 0, tzinfo=TAIPEI)]


def test_root_offline_factory_and_service_use_verified_annual_plan_without_network(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace
    from test_official_trading_calendar_cache import _cache
    from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
    calendar = tmp_path / "calendar" / "twse_holiday_schedule_2026_test.json"
    _cache(calendar, captured_at=datetime(2026, 10, 1, 8, tzinfo=TAIPEI))
    root = tmp_path / "snapshots"
    _write_snapshot(root, date(2026, 10, 2), matches=False)
    current = _write_snapshot(root, date(2026, 10, 5), matches=True)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("此 reader 不可連線或讀 SQLite")
    monkeypatch.setattr("data_module.official_trading_calendar.safe_request", forbidden)
    monkeypatch.setattr("sqlite3.connect", forbidden)
    service = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=tmp_path / "missing.sqlite", official_calendar_cache_path=calendar),
        snapshot_root=root,
    )
    result = service.read_membership_lifecycle(current, CONDITION_KEYS, "AND")
    row = result.rows_by_stock["2382"]
    assert row.status is LifecycleStatus.NEWLY_SELECTED
    assert row.previous_date == date(2026, 10, 2)
    assert row.first_seen == date(2026, 10, 2)
    assert result.research_only and not result.historical_pit_eligible
    assert "source_available_at_unrecorded" in row.warnings


def test_root_offline_calendar_rejects_corrupt_future_or_explicit_missing_overlay(tmp_path: Path) -> None:
    import json
    from test_official_trading_calendar_cache import _cache
    from data_module.official_trading_calendar_cache import payload_hash
    from app_module.research_membership_lifecycle_read_model import create_offline_official_calendar_session_provider
    as_of = datetime(2026, 10, 5, 16, tzinfo=TAIPEI)
    valid = tmp_path / "calendar" / "valid.json"
    _cache(valid, captured_at=datetime(2026, 10, 1, 8, tzinfo=TAIPEI))
    bad = tmp_path / "calendar" / "bad.json"
    payload = json.loads(valid.read_text(encoding="utf-8"))
    payload["source"]["response_sha256"] = "0" * 64
    payload["content_sha256"] = payload_hash({k: v for k, v in payload.items() if k != "content_sha256"})
    bad.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    future = tmp_path / "calendar" / "future.json"
    _cache(future, captured_at=datetime(2026, 10, 6, 8, tzinfo=TAIPEI))
    for path in (bad, future):
        provider = create_offline_official_calendar_session_provider(path)
        assert not provider.expected_session(date(2026, 10, 5), as_of=as_of).verified
    missing_overlay = create_offline_official_calendar_session_provider(valid, temporary_closure_path=tmp_path / "absent_closure.json")
    assert not missing_overlay.expected_session(date(2026, 10, 5), as_of=as_of).verified


def test_root_incomplete_save_does_not_turn_match_into_exit(tmp_path: Path) -> None:
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    _write_snapshot(tmp_path, day1, matches=True)
    current = _write_snapshot(tmp_path, day2, matches=False)
    sessions = _VerifiedSessions({day1: None, day2: day1})
    assert _read(tmp_path, current, sessions).rows_by_stock["2382"].status is LifecycleStatus.NO_LONGER_SELECTED
    partial = b"{"
    path = tmp_path / snapshot_manifest_relpath(hashlib.sha256(partial).hexdigest())
    path.write_bytes(partial)
    result = _read(tmp_path, current, sessions)
    assert result.history_coverage is HistoryCoverage.UNKNOWN
    assert result.rows_by_stock["2382"].status is LifecycleStatus.HISTORY_INSUFFICIENT
    assert result.reason == "history_manifest_invalid_or_unverified"


def test_root_duplicate_read_is_stable_and_budget_or_cancel_fails_closed(tmp_path: Path, monkeypatch) -> None:
    import pytest
    from app_module.daily_market_research_screener import DailyMarketResearchCancelled
    day1, day2 = date(2026, 10, 5), date(2026, 10, 6)
    _write_snapshot(tmp_path, day1, matches=True)
    current = _write_snapshot(tmp_path, day2, matches=False)
    sessions = _VerifiedSessions({day1: None, day2: day1})
    inventory = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    first = _read(tmp_path, current, sessions).to_dict()
    assert _read(tmp_path, current, sessions).to_dict() == first
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")} == inventory
    monkeypatch.setattr("app_module.research_membership_lifecycle_read_model.MAX_HISTORY_OBSERVATIONS", 1)
    result = _read(tmp_path, current, sessions)
    assert result.history_coverage is HistoryCoverage.TRUNCATED
    assert result.rows_by_stock["2382"].status is LifecycleStatus.HISTORY_INSUFFICIENT
    with pytest.raises(DailyMarketResearchCancelled):
        read_membership_lifecycle(DailyMarketSnapshotRepository(tmp_path), current, CONDITION_KEYS, "AND", cancel_callback=lambda: True, session_provider=sessions)
