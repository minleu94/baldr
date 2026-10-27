"""可攜與原碼共用外部日曆來源，不從 bundle 猜本機 output。"""
from pathlib import Path
from types import SimpleNamespace
from datetime import date, datetime, timedelta, timezone
import json
import pytest

from app_module.application_bootstrap import resolve_application_settings
from app_module.market_session_cadence import MarketSessionCadence
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    build_twse_temporary_closure_cache,
    write_twse_calendar_cache,
    write_twse_temporary_closure_cache,
)


def test_shared_config_accepts_explicit_calendar_and_environment_precedence(tmp_path):
    import json
    config = tmp_path / "config.json"
    configured = tmp_path / "configured-calendar"
    override = tmp_path / "override-calendar"
    config.write_text(json.dumps({"OFFICIAL_CALENDAR_CACHE_PATH": str(configured)}), encoding="utf-8")
    settings = resolve_application_settings(environ={"BALDR_CONFIG": str(config),
        "LOCALAPPDATA": str(tmp_path / "local"), "OFFICIAL_CALENDAR_CACHE_PATH": str(override)},
        resource_root=tmp_path / "bundle", frozen=False)
    assert settings.environment["OFFICIAL_CALENDAR_CACHE_PATH"] == str(override.resolve())
    assert not override.exists()


def test_explicit_source_and_external_research_root_do_not_depend_on_bundle(monkeypatch, tmp_path):
    repository = tmp_path / "external-research"
    explicit = tmp_path / "official-calendar"
    monkeypatch.setenv("RESEARCH_STATE_ROOT", str(repository))
    monkeypatch.delenv("OFFICIAL_CALENDAR_CACHE_PATH", raising=False)
    cadence = MarketSessionCadence.for_config(SimpleNamespace())
    assert cadence.calendar.calendar_cache_path == repository / "output/paper_execution_eod_replay/calendar_cache"
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(explicit))
    cadence = MarketSessionCadence.for_config(SimpleNamespace())
    assert cadence.calendar.calendar_cache_path == explicit
    chosen = tmp_path / "chosen-by-caller"
    cadence = MarketSessionCadence.for_config(SimpleNamespace(official_calendar_cache_path=chosen))
    assert cadence.calendar.calendar_cache_path == chosen
    assert cadence.calendar.temporary_closure_path == chosen
    assert not repository.exists() and not explicit.exists()


def test_market_session_cadence_uses_hash_bound_temporary_closure_sidecars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "official-calendar"
    cache_root.mkdir()
    captured = datetime(2026, 10, 22, 13, 0, tzinfo=timezone.utc)
    schedule = [
        {"Name": "中華民國開國紀念日", "Date": "1150101", "Weekday": "四", "Description": "放假1日。"},
        {"Name": "國曆新年開始交易日", "Date": "1150102", "Weekday": "五", "Description": "開始交易。"},
        {"Name": "補假", "Date": "1151026", "Weekday": "一", "Description": "補假1日。"},
    ]
    annual_cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=json.dumps(schedule, ensure_ascii=False).encode("utf-8"),
        requested_at=captured - timedelta(minutes=2),
        captured_at=captured - timedelta(minutes=1),
        response_status=200,
        response_headers={"Content-Type": "application/json"},
    )
    write_twse_calendar_cache(
        cache_root / "twse_holiday_schedule_2026.json",
        annual_cache,
        allowed_root=tmp_path,
    )
    source_url = "https://www.twse.com.tw/zh/announcement/announcement/detail.html?id=8a8216d6a0fa351b01a1638507a10203"
    closure_cache = build_twse_temporary_closure_cache(
        closure_date=date(2026, 10, 23),
        raw_response="<html>臺灣證券交易所集中交易市場115年10月23日全日休市一天。</html>".encode("utf-8"),
        source_url=source_url,
        requested_at=captured - timedelta(minutes=2),
        captured_at=captured,
        response_status=200,
        response_headers={"Content-Type": "text/html"},
        response_url=source_url,
    )
    write_twse_temporary_closure_cache(
        cache_root / "twse_temporary_closure_20261023_test.json",
        closure_cache,
        allowed_root=tmp_path,
    )
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(cache_root))
    observed_at = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)
    cadence = MarketSessionCadence.for_config(
        SimpleNamespace(),
        clock=lambda: observed_at,
    )

    assessment = cadence.assess(date(2026, 10, 26), date(2026, 10, 22))

    assert cadence.calendar.temporary_closure_path == cache_root
    assert assessment.status == "current", assessment.metadata
    assert assessment.expected_date == date(2026, 10, 22)
    assert assessment.metadata["calendar"]["status"] == "verified"


def test_historical_replay_uses_calendar_evidence_as_of_decision_date(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_root = tmp_path / "official-calendar"
    cache_root.mkdir()
    schedule = [
        {"Name": "中華民國開國紀念日", "Date": "1150101", "Weekday": "四", "Description": "放假1日。"},
        {"Name": "國曆新年開始交易日", "Date": "1150102", "Weekday": "五", "Description": "開始交易。"},
        {"Name": "補假", "Date": "1151026", "Weekday": "一", "Description": "補假1日。"},
    ]
    old_capture = datetime(2026, 10, 20, 0, 25, tzinfo=timezone.utc)
    old_cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=json.dumps(schedule, ensure_ascii=False).encode("utf-8"),
        requested_at=old_capture - timedelta(minutes=1),
        captured_at=old_capture,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        max_age=timedelta(days=7),
    )
    old_path = cache_root / "twse_holiday_schedule_2026_20261020.json"
    write_twse_calendar_cache(old_path, old_cache, allowed_root=tmp_path)

    new_capture = datetime(2026, 10, 27, 0, 25, tzinfo=timezone.utc)
    new_cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=json.dumps(schedule, ensure_ascii=False).encode("utf-8"),
        requested_at=new_capture - timedelta(minutes=1),
        captured_at=new_capture,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        max_age=timedelta(days=7),
    )
    write_twse_calendar_cache(
        cache_root / "twse_holiday_schedule_2026_20261027.json",
        new_cache,
        allowed_root=tmp_path,
    )

    closure_capture = datetime(2026, 10, 24, 7, 5, tzinfo=timezone.utc)
    source_url = "https://www.twse.com.tw/zh/announcement/announcement/detail.html?id=8a8216d6a0fa351b01a1638507a10203"
    closure_cache = build_twse_temporary_closure_cache(
        closure_date=date(2026, 10, 23),
        raw_response="<html>臺灣證券交易所集中交易市場115年10月23日全日休市一天。</html>".encode("utf-8"),
        source_url=source_url,
        requested_at=closure_capture - timedelta(minutes=1),
        captured_at=closure_capture,
        response_status=200,
        response_headers={"Content-Type": "text/html"},
        response_url=source_url,
    )
    write_twse_temporary_closure_cache(
        cache_root / "twse_temporary_closure_20261023_test.json",
        closure_cache,
        allowed_root=tmp_path,
    )
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(cache_root))
    runtime_observed_at = datetime(2026, 10, 27, 2, 22, tzinfo=timezone.utc)
    cadence = MarketSessionCadence.for_config(
        SimpleNamespace(),
        clock=lambda: runtime_observed_at,
    )

    assessment = cadence.assess(date(2026, 10, 26), date(2026, 10, 22))

    assert assessment.status == "current", assessment.metadata
    assert assessment.expected_date == date(2026, 10, 22)
    assert assessment.metadata["observed_at"] == runtime_observed_at.isoformat()
    assert assessment.metadata["calendar_observed_at"] == "2026-10-26T15:59:59.999999+00:00"
    assert assessment.metadata["calendar"]["status"] == "verified"
    selected_cache = assessment.metadata["calendar"]["years"][2026]
    assert selected_cache["path"] == str(old_path.resolve())
    assert selected_cache["available_at"] <= assessment.metadata["decision_at"]
    assert assessment.metadata["calendar"]["temporary_closure_path"] == str(cache_root.resolve())


def test_frozen_calendar_refuses_bundle_and_direct_entry_uses_external_default(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    with pytest.raises(ValueError, match="OFFICIAL_CALENDAR_CACHE_PATH"):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"),
            "OFFICIAL_CALENDAR_CACHE_PATH": str(bundle / "calendar")},
            resource_root=bundle, frozen=True)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.delenv("RESEARCH_STATE_ROOT", raising=False)
    monkeypatch.delenv("OFFICIAL_CALENDAR_CACHE_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    cadence = MarketSessionCadence.for_config(SimpleNamespace())
    assert cadence.calendar.calendar_cache_path == (
        tmp_path / "local/baldr/research_state/output/paper_execution_eod_replay/calendar_cache")


@pytest.mark.parametrize("cache_state", ["verified", "missing", "expired", "tampered", "future"])
def test_external_calendar_is_actually_verified_and_invalid_evidence_stays_blocked(
    monkeypatch, tmp_path, cache_state,
):
    """經正式 cache reader 驗證外部接線，不能用路徑存在代替日曆有效。"""
    from datetime import date, datetime, timedelta, timezone
    import hashlib
    import json
    from tests.test_official_trading_calendar_cache import _cache

    now = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    cache_root = tmp_path / "external/calendar"
    cache_file = cache_root / "twse_holiday_schedule_2026_test.json"
    if cache_state != "missing":
        captured = now - timedelta(days=1)
        if cache_state == "expired":
            captured = now - timedelta(days=8)
        elif cache_state == "future":
            captured = now + timedelta(hours=1)
        _cache(cache_file, captured_at=captured)
        if cache_state == "tampered":
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            payload["content_sha256"] = "sha256:" + "0" * 64
            cache_file.write_text(json.dumps(payload), encoding="utf-8")
    before = hashlib.sha256(cache_file.read_bytes()).hexdigest() if cache_file.exists() else None
    monkeypatch.setenv("OFFICIAL_CALENDAR_CACHE_PATH", str(cache_root))
    monkeypatch.setattr("data_module.official_trading_calendar.safe_request",
        lambda *args, **kwargs: pytest.fail("研究讀取不可隱性下載日曆"))
    cadence = MarketSessionCadence.for_config(SimpleNamespace(), clock=lambda: now)
    assessment = cadence.assess(date(2026, 10, 7), date(2026, 10, 7))
    assert assessment.metadata["calendar"]["calendar_cache_path"] == str(cache_root.resolve())
    if cache_state == "verified":
        assert assessment.current
        assert assessment.expected_date == date(2026, 10, 7)
        assert assessment.metadata["calendar"]["status"] == "verified"
    else:
        assert assessment.status == "unverified"
        assert assessment.expected_date is None
        assert assessment.metadata["blockers"]
    after = hashlib.sha256(cache_file.read_bytes()).hexdigest() if cache_file.exists() else None
    assert after == before
    assert not (cache_root / "market.sqlite").exists()
