from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.forward_outcome_context import (
    DEFAULT_OFFICIAL_CALENDAR_CACHE_PATH,
    build_official_maturity_calendar,
    resolve_canonical_evidence_release_root,
)
from data_module.config import TWStockConfig
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)


def _write_cache(root: Path, *, captured_at: datetime) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "test closed day",
                "Date": "1150101",
                "Weekday": "Thursday",
                "Description": "test closed day",
            }
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    path = root / "twse_holiday_schedule_2026_test.json"
    cache = build_twse_calendar_cache(
        calendar_year=2026,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": '"forward-context-test"'},
    )
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path


def test_factory_prefers_explicit_cache_and_keeps_read_only_calendar(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    explicit_root = tmp_path / "explicit"
    path = _write_cache(explicit_root, captured_at=now)
    config = SimpleNamespace(
        output_root=tmp_path / "other-output",
        official_calendar_cache_path=tmp_path / "configured-cache",
        temporary_closure_path=None,
    )

    calendar = build_official_maturity_calendar(
        config=config,
        observed_at=now,
        calendar_cache_path=explicit_root,
    )
    diagnostic = calendar.evaluate(
        event_date="2026-09-07",
        window_days=5,
        as_of_date="2026-09-10",
    )

    assert calendar.cache_path == explicit_root.resolve()
    assert calendar.describe()["read_only"] is True
    assert diagnostic.planned_date == "2026-09-14"
    assert diagnostic.calendar["sources"][0]["source_path"] == str(path.resolve())
    assert not (tmp_path / "other-output" / "paper_execution_eod_replay").exists()


def test_factory_uses_configured_cache_before_repository_default(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    configured_root = tmp_path / "configured"
    _write_cache(configured_root, captured_at=now)
    config = SimpleNamespace(
        output_root=tmp_path / "redirected-output",
        official_calendar_cache_path=configured_root,
        temporary_closure_path=None,
    )

    calendar = build_official_maturity_calendar(config=config, observed_at=now)

    assert calendar.cache_path == configured_root.resolve()
    assert calendar.cache_path != DEFAULT_OFFICIAL_CALENDAR_CACHE_PATH.resolve()


def test_factory_default_calendar_is_repository_cache_not_output_root(tmp_path: Path) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "redirected-output",
    )
    now = datetime.now(timezone.utc)

    calendar = build_official_maturity_calendar(config=config, observed_at=now)

    assert calendar.cache_path == DEFAULT_OFFICIAL_CALENDAR_CACHE_PATH.resolve()
    assert calendar.cache_path != config.output_root.resolve()
    assert calendar.temporary_closure_path is None


def test_factory_normalizes_aware_clock_and_rejects_naive_clock(tmp_path: Path) -> None:
    config = SimpleNamespace()
    now = datetime(2026, 10, 4, 20, 0, tzinfo=timezone(timedelta(hours=8)))

    calendar = build_official_maturity_calendar(config=config, observed_at=now)

    assert calendar.observed_at == datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="aware datetime"):
        build_official_maturity_calendar(
            config=config,
            observed_at=datetime(2026, 10, 4, 12, 0),
        )


def test_canonical_writer_root_uses_base_config_and_database_identity(
    tmp_path: Path,
) -> None:
    canonical = TWStockConfig(
        data_root=tmp_path / "canonical-data",
        output_root=tmp_path / "canonical-output",
    )
    artifact = TWStockConfig(
        data_root=tmp_path / "canonical-data",
        output_root=tmp_path / "artifact-output",
    )

    release_root = resolve_canonical_evidence_release_root(
        canonical_config=canonical,
        db_path=canonical.db_file,
    )
    isolated_root = resolve_canonical_evidence_release_root(
        canonical_config=canonical,
        db_path=tmp_path / "working-copy.sqlite",
    )

    assert release_root == (tmp_path / "canonical-output" / "release_v4").resolve()
    assert release_root != artifact.output_root.resolve() / "release_v4"
    assert isolated_root is None
