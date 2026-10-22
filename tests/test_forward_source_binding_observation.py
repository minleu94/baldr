from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app_module import forward_source_observation as observation
from app_module.forward_daily_price_source_binding import unknown_price_source_binding


def _recorder(tmp_path: Path):
    root = tmp_path.resolve()

    def write(path, text):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    recorder = observation.ForwardSourceObservationRecorder(
        run_id="20261022T120000123456Z", output_root=root,
        db_path=root / "market.sqlite3", writer=write,
    )
    recorder.begin_outcome(event_id="event-1", window_days=5)
    return recorder


def test_binding_chunks_align_with_actual_rows_and_have_separate_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(observation, "MAX_CHUNK_BYTES", 650)
    recorder = _recorder(tmp_path)
    rows = [(str(index), index) for index in range(15)]
    bindings = [unknown_price_source_binding(f"missing-{index}") for index in range(15)]
    recorder.observe_query(
        table="daily_prices", query="SELECT date, close FROM daily_prices",
        parameters=(), rows=rows, symbol="2330", purpose="daily_price_series",
        columns=("date", "close"), source_bindings=bindings,
    )
    ids = recorder.end_outcome()
    recorder.record_outcome(event_id="event-1", window_days=5, return_basis="close_to_close",
                            outcome_status="ready", outcome_payload={}, query_ids=ids)
    ref = recorder.persist()
    assert ref["schema_version"] == observation.BOUND_SCHEMA_VERSION
    manifest = json.loads((tmp_path / ref["manifest_path"]).read_bytes())
    query = manifest["queries"][0]
    assert "source_bindings" not in query
    fetched, captured = [], []
    for chunk in query["chunks"]:
        raw = (tmp_path / chunk["path"]).read_bytes()
        assert len(raw) <= 650
        assert chunk["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
        value = json.loads(raw)
        assert value["schema_version"] == observation.BOUND_CHUNK_SCHEMA_VERSION
        assert len(value["rows"]) == len(value["source_bindings"])
        fetched.extend(value["rows"])
        captured.extend(value["source_bindings"])
    assert fetched == [list(row) for row in rows]
    assert captured == bindings
    assert query["rows_sha256"] == observation._sha256(observation._canonical_bytes(fetched))
    assert query["source_bindings_sha256"] == observation._sha256(observation._canonical_bytes(bindings))
    assert manifest["outcomes"][0]["query_ids"] == list(ids)


@pytest.mark.parametrize("field,value", [
    ("source_use_accepted", True), ("pit_eligible", True), ("training_eligible", True),
    ("available_at", "2026-10-21T00:00:00+08:00"),
    ("source_published_at", "2026-10-21T00:00:00+08:00"),
])
def test_observation_refuses_qualification_escalation(tmp_path, field, value):
    recorder = _recorder(tmp_path)
    binding = unknown_price_source_binding("unknown")
    binding[field] = value
    with pytest.raises(observation.ForwardSourceObservationError, match="qualification_invalid"):
        recorder.observe_query(table="daily_prices", query="SELECT date", parameters=(),
                               rows=[("20261021",)], symbol="2330", purpose="test",
                               columns=("date",), source_bindings=[binding])


def test_binding_count_and_duplicate_columns_refused(tmp_path):
    recorder = _recorder(tmp_path)
    with pytest.raises(observation.ForwardSourceObservationError, match="binding_count_invalid"):
        recorder.observe_query(table="daily_prices", query="SELECT date", parameters=(),
                               rows=[("20261021",)], symbol=None, purpose="test",
                               columns=("date",), source_bindings=[])
    with pytest.raises(observation.ForwardSourceObservationError, match="columns_invalid"):
        recorder.observe_query(table="daily_prices", query="SELECT date, date", parameters=(),
                               rows=[("20261021", "20261021")], symbol=None, purpose="test",
                               columns=("date", "date"))


def test_binding_bytes_count_toward_run_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(observation, "MAX_RUN_BYTES", 180)
    recorder = _recorder(tmp_path)
    binding = unknown_price_source_binding("x" * 200)
    with pytest.raises(observation.ForwardSourceObservationError, match="row_budget_exceeded"):
        recorder.observe_query(table="daily_prices", query="SELECT date", parameters=(),
                               rows=[("20261021",)], symbol=None, purpose="test",
                               columns=("date",), source_bindings=[binding])
