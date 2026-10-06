from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from typing import Any

import pytest

from ml_module.current_restated_research_bridge import (
    CurrentRestatedResearchError,
    _bind_verified_current_restated_fold_qualification,
    _canonical_json_bytes,
    _validate_verified_current_restated_fold_qualification,
)
from ml_module.purged_walk_forward import MLTimeWindowRow, PurgedWalkForwardFold


_DIRECT_MANIFEST_SHA256 = "a" * 64


def _session_calendar(calendar_count: int) -> tuple[str, ...]:
    result: list[str] = []
    current = date(2014, 1, 1)
    while len(result) < calendar_count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(result)


def _build_qualified_audit(calendar_count: int, *, fold_count: int = 40) -> dict[str, Any]:
    calendar = _session_calendar(calendar_count)
    folds: list[PurgedWalkForwardFold] = []
    raw_fold_audits: list[dict[str, Any]] = []
    test_start_indices = tuple(185 + 68 * index for index in range(fold_count))
    if any(index + 63 > calendar_count for index in test_start_indices):
        raise ValueError("test fold fixture exceeds its event calendar")
    for fold_index, test_start_index in enumerate(test_start_indices, start=1):
        train = tuple(
            MLTimeWindowRow(
                row_id=f"train-{fold_index}-{index}",
                decision_date=calendar[index],
                label_end_date=(date.fromisoformat(calendar[index]) + timedelta(days=5)).isoformat(),
            )
            for index in range(test_start_index - 60)
        )
        test = tuple(
            MLTimeWindowRow(
                row_id=f"test-{fold_index}-{index}",
                decision_date=calendar[index],
                label_end_date=(date.fromisoformat(calendar[index]) + timedelta(days=5)).isoformat(),
            )
            for index in range(test_start_index, test_start_index + 63)
        )
        fold_id = f"fold-{fold_index:02d}"
        folds.append(
            PurgedWalkForwardFold(
                fold_id=fold_id,
                train_rows=train,
                test_rows=test,
                test_start=test[0].decision_date,
                test_end=test[-1].decision_date,
                purge_days=60,
                embargo_days=5,
            )
        )
        raw_fold_audits.append(
            {
                "fold_id": fold_id,
                "label_head": "benchmark_excess_return_bp",
                "purge_trading_days": 60,
                "embargo_trading_days": 5,
                "preprocessing_fit_scope": "fold-local-training-rows-only",
                "training_mature_date_count": len(train),
                "test_date_count": len(test),
            }
        )

    calendar_sha256 = sha256(_canonical_json_bytes(list(calendar))).hexdigest()
    raw_audit = {
        "event_date_calendar": list(calendar),
        "event_date_calendar_sha256": calendar_sha256,
        "folds": raw_fold_audits,
    }
    return _bind_verified_current_restated_fold_qualification(
        raw_audit,
        folds=folds,
        event_date_calendar=calendar,
        direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
        direct_event_date_calendar_sha256=calendar_sha256,
    )


def _verify(audit: dict[str, Any]) -> None:
    qualification = audit["current_restated_verified_fold_qualification"]
    _validate_verified_current_restated_fold_qualification(
        audit,
        expected_direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
        expected_direct_event_date_calendar_sha256=(
            qualification.get("direct_event_date_calendar_sha256")
        ),
    )


def test_v2_accepts_complete_3111_session_calendar_with_40_fold_scale_profile() -> None:
    audit = _build_qualified_audit(3111, fold_count=40)
    qualification = audit["current_restated_verified_fold_qualification"]

    _verify(audit)

    assert qualification["schema_version"] == "current-restated-verified-fold-qualification.v2"
    assert qualification["minimum_event_date_calendar_count"] == 905
    assert qualification["event_date_calendar_count"] == 3111
    assert qualification["event_date_calendar_sha256"] == audit["event_date_calendar_sha256"]
    assert qualification["direct_event_date_calendar_sha256"] == audit["event_date_calendar_sha256"]
    assert len(qualification["folds"]) == 40
    assert all(len(item["train_date_indices"]) >= 125 for item in qualification["folds"])
    assert all(len(item["test_date_indices"]) >= 63 for item in qualification["folds"])
    assert all(item["actual_purge_trading_days"] >= 60 for item in qualification["folds"])
    assert all(item["actual_embargo_trading_days"] >= 5 for item in qualification["folds"])


def test_v1_exact_905_calendar_remains_readable() -> None:
    audit = _build_qualified_audit(905, fold_count=4)
    qualification = audit["current_restated_verified_fold_qualification"]
    qualification["schema_version"] = "current-restated-verified-fold-qualification.v1"
    qualification.pop("minimum_event_date_calendar_count")
    qualification.pop("calendar_scope")
    qualification.pop("direct_event_date_calendar_sha256")

    _validate_verified_current_restated_fold_qualification(
        audit,
        expected_direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
    )


@pytest.mark.parametrize("calendar_count", [100, 904])
def test_calendar_shorter_than_905_is_rejected(calendar_count: int) -> None:
    calendar = tuple(
        (date(2000, 1, 1) + timedelta(days=index)).isoformat()
        for index in range(calendar_count)
    )
    calendar_sha256 = sha256(_canonical_json_bytes(list(calendar))).hexdigest()

    with pytest.raises(CurrentRestatedResearchError, match="at least 905"):
        _bind_verified_current_restated_fold_qualification(
            {},
            folds=(),
            event_date_calendar=calendar,
            direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
            direct_event_date_calendar_sha256=calendar_sha256,
        )


def test_v2_rejects_missing_date_and_mismatched_direct_calendar_pin() -> None:
    audit = _build_qualified_audit(3111)
    audit["event_date_calendar"].pop(2000)
    audit["event_date_calendar_sha256"] = sha256(
        _canonical_json_bytes(audit["event_date_calendar"])
    ).hexdigest()

    with pytest.raises(CurrentRestatedResearchError, match="calendar"):
        _verify(audit)

    audit = _build_qualified_audit(3111)
    with pytest.raises(CurrentRestatedResearchError, match="complete event-date calendar differs"):
        _bind_verified_current_restated_fold_qualification(
            {"folds": audit["folds"]},
            folds=(),
            event_date_calendar=audit["event_date_calendar"],
            direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
            direct_event_date_calendar_sha256="b" * 64,
        )


def test_v2_rejects_fewer_than_four_qualified_folds() -> None:
    with pytest.raises(CurrentRestatedResearchError, match="at least four unique"):
        _build_qualified_audit(3111, fold_count=3)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda item: item.__setitem__("event_date_calendar_count", 3112), "calendar"),
        (lambda item: item.__setitem__("event_date_calendar_sha256", "0" * 64), "calendar"),
        (lambda item: item.__setitem__("direct_event_date_calendar_sha256", "0" * 64), "calendar"),
    ],
)
def test_v2_rejects_forged_calendar_counts_and_hashes(mutator: Any, message: str) -> None:
    audit = _build_qualified_audit(3111)
    qualification = audit["current_restated_verified_fold_qualification"]
    mutator(qualification)

    with pytest.raises(CurrentRestatedResearchError, match=message):
        _verify(audit)


def test_v2_rejects_fold_with_weakened_purge() -> None:
    audit = _build_qualified_audit(3111)
    qualification = audit["current_restated_verified_fold_qualification"]
    qualification["folds"][0]["actual_purge_trading_days"] = 59

    with pytest.raises(CurrentRestatedResearchError, match="60 actual purge"):
        _verify(audit)


@pytest.mark.parametrize(
    ("index_field", "message"),
    [("train_date_indices", "125/63"), ("test_date_indices", "125/63")],
)
def test_v2_rejects_fold_below_minimum_train_or_test_dates(index_field: str, message: str) -> None:
    audit = _build_qualified_audit(3111)
    qualification = audit["current_restated_verified_fold_qualification"]
    qualification["folds"][0][index_field].pop()

    with pytest.raises(CurrentRestatedResearchError, match=message):
        _verify(audit)


def test_v2_rejects_calendar_sha_that_differs_from_direct_manifest_pin() -> None:
    audit = _build_qualified_audit(3111)

    with pytest.raises(CurrentRestatedResearchError, match="complete verified calendar"):
        _validate_verified_current_restated_fold_qualification(
            audit,
            expected_direct_manifest_sha256=_DIRECT_MANIFEST_SHA256,
            expected_direct_event_date_calendar_sha256="0" * 64,
        )
