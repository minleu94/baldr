from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module import forward_source_observation as observation
from app_module.forward_source_observation import (
    ForwardSourceObservationError,
    ForwardSourceObservationRecorder,
)
from app_module.forward_performance_service import ForwardPerformanceService


RUN_ID = "20261022T120000123456Z"


def _create_only(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def test_recorder_publishes_actual_rows_and_explicit_unknown_qualifications(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=tmp_path / "market.sqlite3",
        writer=_create_only,
    )
    recorder.begin_outcome(event_id="event-1", window_days=5)
    query_id = recorder.observe_query(
        table="daily_prices",
        query='SELECT "日期", "收盤價" FROM daily_prices WHERE "證券代號" = ?',
        parameters=("2330",),
        rows=(("20261020", 101.25), ("20261021", 102.5)),
        symbol="2330",
        purpose="daily_price_series",
    )
    recorder.record_use(query_id, purpose="daily_price_series_cache_reuse")
    recorder.observe_query(
        table="market_indices",
        query='SELECT "日期", "收盤指數" FROM market_indices WHERE "指數名稱" = ?',
        parameters=("TAIEX",),
        rows=(),
        symbol="TAIEX",
        purpose="benchmark_value",
    )
    query_ids = recorder.end_outcome()
    recorder.record_outcome(
        event_id="event-1",
        window_days=5,
        return_basis="close_to_close",
        outcome_status="insufficient_future_data",
        outcome_payload={"forward_return_bp": None},
        query_ids=query_ids,
    )

    reference = recorder.persist()
    manifest_path = output_root / reference["manifest_path"]
    manifest_bytes = manifest_path.read_bytes()
    assert len(manifest_bytes) <= 512 * 1024
    manifest = json.loads(manifest_bytes)
    assert manifest["semantics"] == {
        "source_availability": "unknown",
        "pit_qualified": False,
        "training_eligible": False,
        "cross_read_snapshot_consistency": "not_guaranteed",
        "rows_are_actual_fetch_results": True,
    }
    assert manifest["outcomes"][0]["query_ids"] == list(query_ids)
    assert manifest["queries"][0]["parameters"] == ["2330"]
    assert manifest["queries"][0]["uses"] == [
        {"event_id": "event-1", "window_days": 5, "purpose": "daily_price_series"},
        {
            "event_id": "event-1",
            "window_days": 5,
            "purpose": "daily_price_series_cache_reuse",
        },
    ]
    rows = []
    for query in manifest["queries"]:
        for chunk in query["chunks"]:
            raw = (output_root / chunk["path"]).read_bytes()
            assert len(raw) <= 512 * 1024
            rows.extend(json.loads(raw)["rows"])
    assert rows == [
        ["20261020", {"type": "sqlite_float", "value": "101.25"}],
        ["20261021", {"type": "sqlite_float", "value": "102.5"}],
    ]
    assert reference["training_eligible"] is False
    assert reference["source_availability"] == "unknown"


def test_recorder_chunks_without_truncation_and_respects_per_file_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    monkeypatch.setattr(observation, "MAX_CHUNK_BYTES", 500)
    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=tmp_path / "market.sqlite3",
        writer=_create_only,
    )
    recorder.begin_outcome(event_id="event-2", window_days=10)
    rows = tuple((f"2026{index:04d}", f"value-{index}-" + "x" * 80) for index in range(12))
    query_id = recorder.observe_query(
        table="daily_prices",
        query="SELECT date, close FROM daily_prices WHERE symbol = ?",
        parameters=("2330",),
        rows=rows,
        symbol="2330",
        purpose="daily_price_series",
    )
    query_ids = recorder.end_outcome()
    recorder.record_outcome(
        event_id="event-2",
        window_days=10,
        return_basis="close_to_close",
        outcome_status="ready",
        outcome_payload={"value": 1},
        query_ids=query_ids,
    )

    reference = recorder.persist()
    assert reference["chunk_count"] > 1
    manifest = json.loads((output_root / reference["manifest_path"]).read_bytes())
    actual_rows = []
    for chunk in manifest["queries"][0]["chunks"]:
        raw = (output_root / chunk["path"]).read_bytes()
        assert len(raw) <= 500
        actual_rows.extend(json.loads(raw)["rows"])
    assert len(actual_rows) == len(rows)
    assert [row[0] for row in actual_rows] == [row[0] for row in rows]


def test_recorder_accepts_more_than_128_small_queries_within_existing_bounds(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=tmp_path / "market.sqlite3",
        writer=_create_only,
    )
    recorder.begin_outcome(event_id="event-many-small-queries", window_days=5)
    expected_rows = []
    for index in range(129):
        row = (f"202610{index % 28 + 1:02d}", index)
        expected_rows.append(row)
        recorder.observe_query(
            table="daily_prices",
            query="SELECT date, close FROM daily_prices WHERE symbol = ?",
            parameters=(f"symbol-{index:03d}",),
            rows=(row,),
            symbol=f"symbol-{index:03d}",
            purpose="daily_price_series",
        )
    query_ids = recorder.end_outcome()
    recorder.record_outcome(
        event_id="event-many-small-queries",
        window_days=5,
        return_basis="close_to_close",
        outcome_status="ready",
        outcome_payload={"value": 1},
        query_ids=query_ids,
    )

    reference = recorder.persist()
    manifest = json.loads((output_root / reference["manifest_path"]).read_bytes())

    assert manifest["query_count"] == 129
    assert reference["chunk_count"] == 129
    actual_rows = []
    for query in manifest["queries"]:
        assert len(query["chunks"]) == 1
        chunk = query["chunks"][0]
        raw = (output_root / chunk["path"]).read_bytes()
        assert len(raw) <= observation.MAX_CHUNK_BYTES
        actual_rows.extend(json.loads(raw)["rows"])
    assert actual_rows == [list(row) for row in expected_rows]


def test_recorder_write_failure_does_not_publish_a_reference(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()

    def reject_write(_path: Path, _text: str) -> None:
        raise OSError("test writer failure")

    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=tmp_path / "market.sqlite3",
        writer=reject_write,
    )
    recorder.begin_outcome(event_id="event-3", window_days=1)
    query_id = recorder.observe_query(
        table="daily_prices",
        query="SELECT date, close FROM daily_prices WHERE symbol = ?",
        parameters=("2330",),
        rows=(("20261021", 100),),
        symbol="2330",
        purpose="daily_price_series",
    )
    query_ids = recorder.end_outcome()
    recorder.record_outcome(
        event_id="event-3",
        window_days=1,
        return_basis="close_to_close",
        outcome_status="ready",
        outcome_payload={"value": 1},
        query_ids=query_ids,
    )

    with pytest.raises(ForwardSourceObservationError, match="write_failed"):
        recorder.persist()
    assert recorder.reference is None


def test_calculate_rejects_reused_recorder_before_second_repository_read(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()

    class EmptyRepository:
        def __init__(self) -> None:
            self.list_calls = 0
            self.upsert_calls = 0

        def list_events(self, **_kwargs):
            self.list_calls += 1
            return []

        def upsert_outcomes(self, _outcomes) -> None:
            self.upsert_calls += 1

    repository = EmptyRepository()
    db_path = tmp_path / "market.sqlite3"
    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=db_path,
        writer=_create_only,
    )
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    service = ForwardPerformanceService(
        SimpleNamespace(db_file=db_path),
        repository,
        db_path=db_path,
        clock=lambda: now,
        source_observer=recorder,
    )

    service.calculate(
        windows=(1,),
        dry_run=True,
        data_as_of_date="2026-10-21",
        invocation_at=now,
    )
    assert repository.list_calls == 1
    assert recorder.reference is not None

    with pytest.raises(ForwardSourceObservationError, match="recorder_already_used"):
        service.calculate(
            windows=(1,),
            dry_run=False,
            data_as_of_date="2026-10-21",
            invocation_at=now,
        )
    assert repository.list_calls == 1
    assert repository.upsert_calls == 0


def test_failed_calculation_also_consumes_source_recorder(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()

    class EmptyRepository:
        def __init__(self) -> None:
            self.list_calls = 0

        def list_events(self, **_kwargs):
            self.list_calls += 1
            return []

    repository = EmptyRepository()
    db_path = tmp_path / "market.sqlite3"
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    recorder = ForwardSourceObservationRecorder(
        run_id=RUN_ID,
        output_root=output_root,
        db_path=db_path,
        writer=_create_only,
    )
    service = ForwardPerformanceService(
        SimpleNamespace(db_file=db_path),
        repository,
        db_path=db_path,
        clock=lambda: now,
        source_observer=recorder,
    )

    with pytest.raises(ValueError, match="cannot be in the future"):
        service.calculate(
            windows=(1,),
            dry_run=True,
            data_as_of_date="2026-10-21",
            invocation_at=now.replace(year=2027),
        )
    with pytest.raises(ForwardSourceObservationError, match="recorder_already_used"):
        service.calculate(
            windows=(1,),
            dry_run=True,
            data_as_of_date="2026-10-21",
            invocation_at=now,
        )
    assert repository.list_calls == 0
