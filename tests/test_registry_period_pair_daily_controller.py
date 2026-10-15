from __future__ import annotations

from dataclasses import replace
from datetime import timezone

import pytest

pytest_plugins = ("test_registry_period_pair_controller",)

from app_module.recommendation_portfolio_period_calendar_read_pin_v1 import (
    PortfolioPeriodCalendarDailyReadPinV1,
    PortfolioPeriodDailyCalendarIdentityV1,
)
from app_module.saved_strategy_rule_card import metadata_sha256
from ui_qt.workers.task_worker import TaskWorker
import test_official_calendar_daily_snapshot_v1 as daily_fixture
from test_registry_period_pair_controller import _wait_until


_MANIFEST_SHA = "a" * 64
_RECEIPT_SHA = "b" * 64
_CAPTURE_SHA = "c" * 64


def _acceptance_tuple(*, suffix: str = ""):
    anchors = daily_fixture._acceptances(suffix=suffix)
    return anchors["twse"], anchors["tpex"]


def _configure_daily(case, *, inject_anchors: bool = True) -> PortfolioPeriodCalendarDailyReadPinV1 | None:
    controller = case.controller
    controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
    batch_directory = case.calendar_path.parent / "exact-daily-batch-20261014"
    controller.artifact_path.setText(str(batch_directory))
    controller.external_sha.setText(_MANIFEST_SHA)
    controller.receipt_sha.setText(_RECEIPT_SHA)
    controller.market.setCurrentIndex(controller.market.findData("twse"))
    if inject_anchors:
        controller.set_daily_acceptances(_acceptance_tuple())
    controller.apply_button.click()
    pin = controller._pin
    return pin if type(pin) is PortfolioPeriodCalendarDailyReadPinV1 else None


def _daily_identity(pin: PortfolioPeriodCalendarDailyReadPinV1) -> PortfolioPeriodDailyCalendarIdentityV1:
    return PortfolioPeriodDailyCalendarIdentityV1(
        batch_id=pin.batch_directory.name,
        manifest_sha256=pin.expected_manifest_sha256,
        receipt_sha256=pin.expected_receipt_sha256,
        capture_sha256=_CAPTURE_SHA,
        first_persisted_at="2026-01-02T14:45:00+08:00",
        successful_batch_completed_at="2026-01-02T14:48:00+08:00",
        available_hour="2026-01-02T15:00:00+08:00",
        availability_basis="synthetic_test_fixture",
        decision_cutoff=pin.decision_cutoff.isoformat(),
        acceptance_ids=tuple(item.acceptance_id for item in pin.trusted_acceptances),
    )


def _install_daily_reader(case, result) -> None:
    reader = case.reader
    reader.calls.clear()
    reader.result = result

    def read_daily(left_id: str, right_id: str, **kwargs):
        reader.calls.append((left_id, right_id, kwargs))
        reader.entered.set()
        if not reader.release.wait(timeout=4.0):
            raise TimeoutError("測試 daily pair reader 未在期限內釋放")
        if reader.error is not None:
            raise reader.error
        return reader.result

    setattr(reader, "read_daily", read_daily)


def _start_daily_read(case, pin: PortfolioPeriodCalendarDailyReadPinV1, result) -> TaskWorker:
    assert case.controller._pin is pin
    _install_daily_reader(case, result)
    case.widget.compare_period_pair_button.click()
    worker = case.controller.worker
    assert isinstance(worker, TaskWorker)
    assert case.reader.entered.wait(timeout=2.0)
    return worker


def test_daily_controller_fails_closed_without_independent_acceptance_anchors(pair_controller):
    case = pair_controller
    pin = _configure_daily(case, inject_anchors=False)

    assert pin is None
    assert case.controller._pin is None
    assert case.controller.acceptance_status.isHidden() is False
    assert "缺少" in case.controller.status.text()
    assert case.widget.compare_period_pair_button.isEnabled() is False
    assert case.reader.calls == []
    assert case.service.load_calls == []


def test_daily_controller_dispatches_exact_batch_and_both_external_shas(pair_controller):
    case = pair_controller
    pin = _configure_daily(case)
    assert pin is not None
    assert pin.expected_manifest_sha256 == _MANIFEST_SHA
    assert pin.expected_receipt_sha256 == _RECEIPT_SHA
    assert pin.trusted_acceptances == _acceptance_tuple()
    assert pin.decision_cutoff.tzinfo is timezone.utc

    result = replace(
        case.result,
        market=pin.market,
        calendar_external_sha256=pin.expected_manifest_sha256,
        daily_calendar_source=_daily_identity(pin),
    )
    worker = _start_daily_read(case, pin, result)
    assert len(case.reader.calls) == 1
    left_id, right_id, kwargs = case.reader.calls[0]
    assert (left_id, right_id) == ("left", "right")
    assert kwargs["calendar_pin"] is pin
    assert kwargs["calendar_pin"].expected_manifest_sha256 == _MANIFEST_SHA
    assert kwargs["calendar_pin"].expected_receipt_sha256 == _RECEIPT_SHA
    assert kwargs["expected_left_metadata_sha256"] == metadata_sha256(case.service.runs[0])
    assert kwargs["expected_right_metadata_sha256"] == metadata_sha256(case.service.runs[1])
    assert callable(kwargs["check_cancel"])
    assert "calendar_path" not in kwargs
    assert case.service.load_calls == []

    case.reader.release.set()
    assert worker.wait(5000)
    assert _wait_until(case.app, lambda: case.controller.worker is None)
    assert case.widget._period_pair_result is result
    assert case.controller.status.text().startswith("已讀回指定兩筆 run")


@pytest.mark.parametrize(
    "change",
    [
        pytest.param("anchors", id="acceptance-anchors-changed"),
        pytest.param("batch_directory", id="batch-directory-changed"),
        pytest.param("manifest_sha", id="manifest-sha-changed"),
        pytest.param("receipt_sha", id="receipt-sha-changed"),
        pytest.param("market", id="market-changed"),
        pytest.param("source_mode", id="source-mode-changed"),
    ],
)
def test_daily_controller_discards_queued_result_after_pin_identity_changes(pair_controller, change: str):
    case = pair_controller
    pin = _configure_daily(case)
    assert pin is not None
    result = replace(
        case.result,
        market=pin.market,
        calendar_external_sha256=pin.expected_manifest_sha256,
        daily_calendar_source=_daily_identity(pin),
    )
    worker = _start_daily_read(case, pin, result)
    case.reader.release.set()
    assert worker.wait(5000)
    assert case.controller.worker is worker

    if change == "anchors":
        case.controller.set_daily_acceptances(_acceptance_tuple(suffix="-changed"))
    elif change == "batch_directory":
        case.controller.artifact_path.setText(str(pin.batch_directory.parent / "different-batch"))
    elif change == "manifest_sha":
        case.controller.external_sha.setText("d" * 64)
    elif change == "receipt_sha":
        case.controller.receipt_sha.setText("e" * 64)
    elif change == "market":
        case.controller.market.setCurrentIndex(case.controller.market.findData("tpex"))
    else:
        case.controller.source_mode.setCurrentIndex(case.controller.source_mode.findData("artifact"))

    assert case.controller._pin is None
    assert _wait_until(case.app, lambda: case.controller.worker is None)
    assert case.widget._period_pair_result is None
    assert case.widget._period_pair_busy is False


@pytest.mark.parametrize(
    "identity_change",
    [
        pytest.param(("batch_id", "other-batch"), id="wrong-batch-id"),
        pytest.param(("manifest_sha256", "d" * 64), id="wrong-identity-manifest-sha"),
        pytest.param(("receipt_sha256", "e" * 64), id="wrong-identity-receipt-sha"),
        pytest.param(("acceptance_ids", ("wrong-twse", "wrong-tpex")), id="wrong-acceptance-ids"),
        pytest.param(("decision_cutoff", "2026-01-02T00:00:00+00:00"), id="wrong-decision-cutoff"),
        pytest.param(("daily_calendar_source", None), id="missing-daily-identity"),
        pytest.param(("outer_manifest", "f" * 64), id="wrong-outer-manifest-sha"),
        pytest.param(("market", "tpex"), id="wrong-result-market"),
    ],
)
def test_daily_controller_rejects_result_with_mismatched_source_identity(pair_controller, identity_change):
    case = pair_controller
    pin = _configure_daily(case)
    assert pin is not None
    identity = _daily_identity(pin)
    field, value = identity_change
    if field == "daily_calendar_source":
        result = replace(
            case.result,
            market=pin.market,
            calendar_external_sha256=pin.expected_manifest_sha256,
            daily_calendar_source=None,
        )
    elif field == "outer_manifest":
        result = replace(
            case.result,
            market=pin.market,
            calendar_external_sha256=value,
            daily_calendar_source=identity,
        )
    elif field == "market":
        result = replace(
            case.result,
            market=value,
            calendar_external_sha256=pin.expected_manifest_sha256,
            daily_calendar_source=identity,
        )
    else:
        wrong_identity = replace(identity, **{field: value})
        result = replace(
            case.result,
            market=pin.market,
            calendar_external_sha256=pin.expected_manifest_sha256,
            daily_calendar_source=wrong_identity,
        )
    worker = _start_daily_read(case, pin, result)
    case.reader.release.set()
    assert worker.wait(5000)
    assert _wait_until(case.app, lambda: case.controller.worker is None)

    assert case.widget._period_pair_result is None
    assert "完整期間結果未套用" in case.controller.status.text()
    assert "每日批次" in case.controller.status.text() or "來源身份" in case.controller.status.text()
