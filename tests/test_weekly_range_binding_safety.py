"""查詢區間身份與執行時鐘分開驗證的負向回歸。"""

from copy import deepcopy

import pytest

from data_module.scheduled_research_acquisition_binding import (
    ResearchBindingError, _query_period,
    _verify_core_query_period, _verify_monthly_query_period,
)


def _objects():
    period = {"period_start": "2026-10-12", "period_end": "2026-10-18"}
    record = {**period, "payload_json": dict(period)}
    receipt = {"core": {"collection_record": record}}
    status = {"selected_start_date": "2026-10-12", "selected_end_date": "2026-10-18"}
    query = {"query_start_date": "2026-10-12", "query_end_date": "2026-10-18"}
    artifact = {**query, "query_manifest": [dict(query) for _ in range(6)]}
    return dict(period), record, receipt, status, artifact


def test_matching_period_across_core_and_every_child_query():
    stdout, record, receipt, status, artifact = _objects()
    assert _verify_core_query_period(stdout, record) == ("2026-10-12", "2026-10-18")
    _verify_monthly_query_period(receipt, status, artifact)


@pytest.mark.parametrize("start,end", [
    (None, "2026-10-18"), ("20261012", "2026-10-18"),
    ("2026-02-30", "2026-10-18"), ("2026-10-19", "2026-10-18"),
    ("2026-10-12T00:00:00", "2026-10-18"),
])
def test_period_rejects_missing_noncanonical_invalid_or_reversed_dates(start, end):
    with pytest.raises(ResearchBindingError, match="query_period"):
        _query_period({"start": start, "end": end}, "start", "end")


@pytest.mark.parametrize("location", ["stdout", "payload", "record"])
def test_core_same_run_and_status_cannot_hide_different_period(location):
    stdout, record, _, _, _ = _objects()
    target = stdout if location == "stdout" else record["payload_json"] if location == "payload" else record
    target["period_start"] = "2026-10-09"
    target["period_end"] = "2026-10-15"
    with pytest.raises(ResearchBindingError, match="period_mismatch"):
        _verify_core_query_period(stdout, record)


@pytest.mark.parametrize("location", ["status", "artifact", "query"])
def test_child_clock_and_pins_cannot_replace_exact_query_period(location):
    _, _, receipt, status, artifact = _objects()
    if location == "status":
        status["selected_start_date"] = "2026-10-09"
    elif location == "artifact":
        artifact["query_start_date"] = "2026-10-09"
    else:
        artifact["query_manifest"][4]["query_start_date"] = "2026-10-09"
    with pytest.raises(ResearchBindingError, match="period_mismatch"):
        _verify_monthly_query_period(receipt, status, artifact)


@pytest.mark.parametrize("manifest", [None, [], [{"query_end_date": "2026-10-18"}]])
def test_missing_query_manifest_or_date_fails_closed(manifest):
    _, _, receipt, status, artifact = _objects()
    artifact["query_manifest"] = deepcopy(manifest)
    with pytest.raises(ResearchBindingError):
        _verify_monthly_query_period(receipt, status, artifact)
