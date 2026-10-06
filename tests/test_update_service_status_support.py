from datetime import datetime, timezone

import pytest

from app_module.update_service_status_support import (
    FreshnessReceiptBinding,
    compose_sqlite_status_read_model,
)


def _statuses():
    return {
        "daily_data": {"latest_date": "2026-07-10", "total_records": 10, "status": "ok"},
        "market_index": {"latest_date": "2026-07-10", "total_records": 2, "status": "ok"},
        "industry_index": {"latest_date": "2026-07-10", "total_records": 3, "status": "ok"},
        "broker_branch": {"latest_date": "2026-07-10", "broker_count": 1, "status": "summary"},
        "technical_indicators": {"latest_date": "2026-07-10", "file_count": 4, "status": "summary"},
        "monthly_revenue": {"latest_date": "2026-06", "total_records": 5, "status": "ok"},
    }


def test_compose_sqlite_status_read_model_preserves_detail_payloads():
    statuses = _statuses()

    result = compose_sqlite_status_read_model(statuses)

    assert list(result) == list(statuses)
    assert result == statuses
    assert all("is_overview" not in payload for payload in result.values())


def test_compose_sqlite_status_read_model_marks_copied_overview_payloads():
    statuses = _statuses()

    result = compose_sqlite_status_read_model(statuses, is_overview=True)

    assert list(result) == list(statuses)
    assert all(payload["is_overview"] is True for payload in result.values())
    assert all("is_overview" not in payload for payload in statuses.values())


def test_compose_sqlite_status_read_model_marks_date_lag_only_when_requested():
    statuses = _statuses()
    statuses["market_index"]["latest_date"] = "2026-07-09"

    unchanged = compose_sqlite_status_read_model(statuses)
    assert unchanged["market_index"]["status"] == "ok"

    result = compose_sqlite_status_read_model(statuses, is_overview=True, apply_freshness=True)
    assert result["daily_data"]["freshness_status"] == "reference"
    assert result["market_index"]["freshness_status"] == "lagging"
    assert result["market_index"]["freshness_reference_date"] == "2026-07-10"
    assert result["market_index"]["status"] == "lagging"
    # input mapping 必須維持唯讀／不被副作用修改。
    assert statuses["market_index"]["status"] == "ok"


def test_compose_sqlite_status_read_model_projects_explicit_freshness_receipt():
    statuses = _statuses()
    receipt = {
        "status": "degraded",
        "checked_at": "2026-07-10T05:00:00-07:00",
        "source_statuses": [
            {
                "source_id": "sqlite.market_indices",
                "freshness_status": "partial",
                "reason": "missing official session",
                "expected_period": "20260710",
                "actual_period": "20260709",
                "available_at": "2026-07-10T05:00:00-07:00",
                "coverage": {"observed_official_sessions": 9},
                "missing_periods": ["20260708"],
            },
        ],
    }

    result = compose_sqlite_status_read_model(
        statuses,
        apply_freshness=True,
        freshness_receipt=receipt,
    )

    assert result["market_index"]["freshness_status"] == "partial"
    assert result["market_index"]["freshness_reason"] == "missing official session"
    assert result["market_index"]["freshness_expected_period"] == "20260710"
    assert result["market_index"]["freshness_missing_periods"] == ["20260708"]
    assert result["market_index"]["status"] == "lagging"
    assert result["market_index"]["freshness_probe_checked_at"] == receipt["checked_at"]
    assert statuses["market_index"]["status"] == "ok"


def _bound_receipt(tmp_path):
    data_root = tmp_path / "FA_Data"
    output_root = data_root / "output"
    db_path = data_root / "sqlite" / "twstock.db"
    candidate_path = data_root / "output" / "candidate.db"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.touch()
    return {
        "task": "baldr-data-freshness-check-daily",
        "status": "passed",
        "checked_at": "2026-10-02T05:00:00+08:00",
        "data_root": str(data_root),
        "output_root": str(output_root),
        "checks": {
            "db_path": str(db_path),
            "calendar_cutoff_local": "04:30",
            "calendar_cutoff_timezone": "America/Los_Angeles",
            "daily_prices_latest_date": "20261002",
            "technical_indicators_latest_date": "20261002",
            "phase3c_candidate_db": {"path": str(candidate_path), "status": "available"},
        },
        "source_statuses": [
            {
                "source_id": "sqlite.daily_prices",
                "freshness_status": "current",
                "actual_period": "20261002",
                "expected_period": "20261002",
            },
            {
                "source_id": "sqlite.market_indices",
                "freshness_status": "stale",
                "actual_period": "20261001",
                "expected_period": "20261002",
                "reason": "missing expected market session",
            },
        ],
    }


def _bound_statuses():
    return {
        "daily_data": {"latest_date": "2026-10-02", "status": "ok"},
        "market_index": {"latest_date": "2026-10-01", "status": "ok"},
        "technical_indicators": {"latest_date": "2026-10-02", "status": "ok"},
    }


def _binding(receipt, now=None, cutoff=None):
    return FreshnessReceiptBinding(
        data_root=receipt["data_root"],
        db_path=receipt["checks"]["db_path"],
        output_root=receipt["output_root"],
        candidate_db_path=receipt["checks"]["phase3c_candidate_db"]["path"],
        evaluated_at=now or datetime(2026, 10, 2, 0, 30, tzinfo=timezone.utc),
        calendar_cutoff_local=cutoff or receipt["checks"]["calendar_cutoff_local"],
    )


def test_bound_freshness_receipt_projects_only_same_paths_periods_and_market_day(tmp_path):
    receipt = _bound_receipt(tmp_path)
    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["daily_data"]["freshness_status"] == "current"
    assert result["daily_data"]["freshness_probe_status"] == "passed"
    assert result["market_index"]["freshness_status"] == "stale"
    assert result["market_index"]["status"] == "lagging"


def _expected_wait_receipt(tmp_path, checked_at="2026-10-01T04:00:00-07:00"):
    receipt = _bound_receipt(tmp_path)
    receipt["status"] = "degraded"
    receipt["checked_at"] = checked_at
    receipt["source_statuses"][0]["freshness_status"] = "expected_wait"
    receipt["source_statuses"][0]["reason"] = "target period may publish after cutoff"
    return receipt


def test_expected_wait_receipt_remains_valid_on_same_pre_cutoff_side(tmp_path):
    receipt = _expected_wait_receipt(tmp_path)
    before_cutoff = datetime.fromisoformat("2026-10-01T04:29:00-07:00")

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, before_cutoff),
    )

    assert result["daily_data"]["freshness_status"] == "expected_wait"
    assert result["daily_data"]["freshness_probe_status"] == "degraded"


@pytest.mark.parametrize("evaluated_at", ["2026-10-01T04:30:00-07:00", "2026-10-01T05:00:00-07:00"])
def test_expected_wait_receipt_crossing_cutoff_requires_revalidation(tmp_path, evaluated_at):
    receipt = _expected_wait_receipt(tmp_path)
    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, datetime.fromisoformat(evaluated_at)),
    )

    assert result["daily_data"]["freshness_status"] == "unknown"
    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"
    assert result["daily_data"]["status"] == "lagging"
    assert "Pacific 04:30" in result["daily_data"]["freshness_reason"]


def test_post_cutoff_receipt_is_valid_on_same_post_cutoff_side(tmp_path):
    receipt = _bound_receipt(tmp_path)
    receipt["checked_at"] = "2026-10-01T04:30:00-07:00"
    receipt["source_statuses"][0]["freshness_status"] = "stale"
    receipt["source_statuses"][0]["reason"] = "expected period not yet observed"
    after_cutoff = datetime.fromisoformat("2026-10-01T05:00:00-07:00")

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, after_cutoff),
    )

    assert result["daily_data"]["freshness_status"] == "stale"
    assert result["daily_data"]["freshness_probe_status"] == "passed"


@pytest.mark.parametrize(
    ("checked_at", "evaluated_at"),
    [
        ("2026-10-05T23:00:00+08:00", "2026-10-06T00:30:00+08:00"),
        ("2026-10-05T06:59:00+00:00", "2026-10-05T07:01:00+00:00"),
        ("2026-10-05T12:00:00+00:00", "2026-10-05T13:00:00+00:00"),
    ],
)
def test_receipt_remains_valid_within_pacific_publication_bucket(
    tmp_path, checked_at, evaluated_at
):
    receipt = _bound_receipt(tmp_path)
    receipt["checked_at"] = checked_at
    receipt["source_statuses"][0]["freshness_status"] = "expected_wait"

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, datetime.fromisoformat(evaluated_at)),
    )

    assert result["daily_data"]["freshness_probe_status"] == "passed"


@pytest.mark.parametrize(
    ("checked_at", "evaluated_at"),
    [
        ("2026-03-08T04:29:00-07:00", "2026-03-08T04:30:00-07:00"),
        ("2026-11-01T04:29:00-08:00", "2026-11-01T04:30:00-08:00"),
    ],
)
def test_receipt_rejects_pacific_cutoff_transition_across_dst(
    tmp_path, checked_at, evaluated_at
):
    receipt = _bound_receipt(tmp_path)
    receipt["checked_at"] = checked_at

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, datetime.fromisoformat(evaluated_at)),
    )

    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"


def test_legacy_receipt_uses_known_producer_timezone_only(tmp_path):
    receipt = _bound_receipt(tmp_path)
    receipt["checks"].pop("calendar_cutoff_timezone")

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["daily_data"]["freshness_probe_status"] == "passed"


@pytest.mark.parametrize("timezone_value", ["Asia/Taipei", "Mars/Nowhere"])
def test_receipt_rejects_incompatible_or_unknown_cutoff_timezone(tmp_path, timezone_value):
    receipt = _bound_receipt(tmp_path)
    receipt["checks"]["calendar_cutoff_timezone"] = timezone_value

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"


def test_receipt_rejects_unknown_legacy_producer(tmp_path):
    receipt = _bound_receipt(tmp_path)
    receipt.pop("task")
    receipt["checks"].pop("calendar_cutoff_timezone")

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"


def test_malformed_matching_cutoff_fails_closed(tmp_path):
    receipt = _expected_wait_receipt(tmp_path)
    receipt["checks"]["calendar_cutoff_local"] = "25:00"

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt, cutoff="25:00"),
    )

    assert result["daily_data"]["freshness_status"] == "unknown"
    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"
    assert "cutoff 格式無效" in result["daily_data"]["freshness_reason"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt, _tmp: receipt.update(data_root="X:/foreign/root"),
        lambda receipt, _tmp: receipt.update(output_root="X:/foreign/output"),
        lambda receipt, _tmp: receipt["checks"].update(db_path="X:/foreign/db.sqlite"),
        lambda receipt, _tmp: receipt["checks"].update(calendar_cutoff_local="05:00"),
        lambda receipt, _tmp: receipt["checks"]["phase3c_candidate_db"].update(path="X:/foreign/candidate.db"),
        lambda receipt, _tmp: receipt.update(checked_at="2026-10-01T05:00:00+08:00"),
        lambda receipt, _tmp: receipt.update(checked_at="2026-10-02T10:00:00+08:00"),
        lambda receipt, _tmp: receipt.update(checked_at="2026-10-02T05:00:00"),
    ],
)
def test_bound_freshness_receipt_mismatch_requires_revalidation(tmp_path, mutate):
    receipt = _bound_receipt(tmp_path)
    binding = _binding(receipt)
    mutate(receipt, tmp_path)
    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=binding,
    )

    assert result["daily_data"]["freshness_status"] == "unknown"
    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"
    assert result["daily_data"]["status"] == "lagging"


def test_bound_freshness_receipt_rejects_prior_period_after_database_advances(tmp_path):
    receipt = _bound_receipt(tmp_path)
    receipt["checks"]["daily_prices_latest_date"] = "20261001"
    receipt["source_statuses"][0]["actual_period"] = "20261001"
    receipt["source_statuses"][1]["actual_period"] = "20261001"

    result = compose_sqlite_status_read_model(
        _bound_statuses(),
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["daily_data"]["freshness_status"] == "unknown"
    assert result["daily_data"]["freshness_probe_status"] == "needs_revalidation"


def test_bound_freshness_receipt_rejects_source_period_after_that_table_advances(tmp_path):
    receipt = _bound_receipt(tmp_path)
    receipt["source_statuses"][1]["actual_period"] = "20260930"
    current = _bound_statuses()
    current["market_index"]["latest_date"] = "2026-10-01"

    result = compose_sqlite_status_read_model(
        current,
        freshness_receipt=receipt,
        freshness_binding=_binding(receipt),
    )

    assert result["market_index"]["freshness_status"] == "unknown"
    assert result["market_index"]["freshness_probe_status"] == "needs_revalidation"
