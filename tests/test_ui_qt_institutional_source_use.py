"""法人唯讀 UI 明選來源用途接受 pin 與限縮顯示契約。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app_module.institutional_source_use as source_use_module
from app_module.institutional_daily_snapshot import (
    InstitutionalDailyRow,
    InstitutionalDailySnapshotPin,
    InstitutionalDailySnapshotRead,
)
from app_module.institutional_source_use import (
    InstitutionalSourceUsePin,
    InstitutionalSourceUseRead,
    TPEX_INSTITUTIONAL_USE_SCOPE,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from test_ui_qt_update_view_workbench import FakeUpdateService, _TestableUpdateView
from ui_qt.widgets.institutional_daily_snapshot_widget import (
    InstitutionalDailySnapshotWidget,
)


_TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")


def _batch_result(*, market: str = "TPEx") -> InstitutionalDailySnapshotRead:
    pin = InstitutionalDailySnapshotPin(
        directory=Path("C:/fixed/tpex-batch"),
        manifest_sha256="a" * 64,
        receipt_sha256="b" * 64,
    )
    row = InstitutionalDailyRow(
        stock_code="2330",
        decision_date="2026-10-15",
        foreign_investor_buy=110,
        foreign_investor_sell=55,
        foreign_investor_net=55,
        investment_trust_buy=30,
        investment_trust_sell=20,
        investment_trust_net=10,
        dealer_buy=10,
        dealer_sell=5,
        dealer_net=5,
        raw_sha256="c" * 64,
        source_version="fixture-source-v1",
        official_timestamp_original_text="2026-10-15T15:00:00+08:00",
        official_timestamp="2026-10-15T15:00:00+08:00",
    )
    return InstitutionalDailySnapshotRead(
        pin=pin,
        stock_code="2330",
        rows=(row,),
        total_records=898,
        first_persisted_at=datetime(2026, 10, 15, 16, 5, tzinfo=_TAIPEI),
        successful_batch_completed_at=datetime(2026, 10, 15, 16, 6, tzinfo=_TAIPEI),
        available_hour=datetime(2026, 10, 15, 17, 0, tzinfo=_TAIPEI),
        availability_basis="synthetic UI fixture clock",
        market=market,
    )


def _qualified_source_use() -> InstitutionalSourceUseRead:
    evidence_identity = source_use_module._evidence_identity()
    pin = InstitutionalSourceUsePin(
        path=Path("C:/fixed/source-use/source_use.json"),
        sha256="d" * 64,
    )
    acceptance = DailySourceUseAcceptance(
        scope=TPEX_INSTITUTIONAL_USE_SCOPE,
        acceptance_id="machine:tpex-institutional:" + evidence_identity,
        accepted_at=datetime(2026, 10, 16, 8, 0, tzinfo=_TAIPEI),
        official_source_endpoint=source_use_module.TPEX_OPENAPI_URL,
        document_chain=tuple(item["url"] for item in source_use_module._DOCUMENT_POLICY),
        acceptance_evidence_ref="sha256:" + evidence_identity,
        authorization_scope="diagnostics",
    )
    return InstitutionalSourceUseRead(
        pin=pin,
        acceptance=acceptance,
        attribution=source_use_module._ATTRIBUTION,
    )


def _select_primary_pin(widget: InstitutionalDailySnapshotWidget) -> None:
    widget.directory_edit.setText("C:/fixed/tpex-batch")
    widget.manifest_sha_edit.setText("a" * 64)
    widget.receipt_sha_edit.setText("b" * 64)
    widget.stock_code_edit.setText("2330")


def _wait(app: QApplication, condition) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.005)
    assert condition(), "原8秒內法人唯讀worker未收尾"


def _close_view(app: QApplication, view) -> None:
    view.begin_shutdown()
    _wait(app, lambda: view._institutional_daily_worker is None)
    view.close()
    app.processEvents()


def test_widget_emits_original_three_signal_arguments_and_freezes_optional_pin():
    app = QApplication.instance() or QApplication([])
    widget = InstitutionalDailySnapshotWidget()
    requests: list[tuple[object, str, int]] = []
    widget.readRequested.connect(
        lambda pin, stock_code, generation: requests.append(
            (pin, stock_code, generation)
        )
    )
    try:
        _select_primary_pin(widget)
        widget.source_use_path_edit.setText("C:/fixed/source-use/source_use.json")
        widget.source_use_sha_edit.setText("e" * 64)
        widget.open_button.click()

        assert len(requests) == 1
        assert len(requests[0]) == 3
        assert requests[0][1] == "2330"
        assert isinstance(widget.requested_source_use_pin, InstitutionalSourceUsePin)
        assert widget.requested_source_use_pin.path == Path(
            "C:/fixed/source-use/source_use.json"
        )
        assert widget.requested_source_use_pin.sha256 == "e" * 64

        generation = widget.generation
        widget.source_use_sha_edit.setText("f" * 64)
        assert widget.generation == generation + 1
        assert widget.requested_source_use_pin is None
        assert len(requests) == 1

        widget.source_use_path_edit.setText("C:/fixed/source-use/source_use.json")
        widget.source_use_sha_edit.setText("e" * 64)
        widget.open_button.click()
        assert widget.requested_source_use_pin is not None
        widget.cancel_button.click()
        assert widget.requested_source_use_pin is None
    finally:
        widget.close()
        app.processEvents()


def test_partial_or_invalid_optional_pin_never_emits_read_request():
    app = QApplication.instance() or QApplication([])
    widget = InstitutionalDailySnapshotWidget()
    requests: list[tuple[object, str, int]] = []
    widget.readRequested.connect(
        lambda pin, stock_code, generation: requests.append(
            (pin, stock_code, generation)
        )
    )
    try:
        _select_primary_pin(widget)
        widget.source_use_path_edit.setText("C:/fixed/source-use/source_use.json")
        widget.open_button.click()
        assert requests == []
        assert widget.requested_source_use_pin is None
        assert "一併提供" in widget.status_label.text()

        widget.source_use_sha_edit.setText("UPPERCASE")
        widget.open_button.click()
        assert requests == []
        assert widget.requested_source_use_pin is None
        assert "無效" in widget.status_label.text()
    finally:
        widget.close()
        app.processEvents()


def test_qualified_typed_tp_ex_diagnostics_source_is_visible_but_stays_candidate():
    app = QApplication.instance() or QApplication([])
    widget = InstitutionalDailySnapshotWidget()
    source_use = _qualified_source_use()
    result = replace(
        _batch_result(), source_use=source_use, source_use_accepted=True
    )
    try:
        widget.show_result(result)

        identity = widget.identity_label.text()
        assert widget.rows_table.rowCount() == 1
        assert "TPEx diagnostics 用途接受 ID：" + source_use.acceptance.acceptance_id in identity
        assert source_use.pin.sha256 in identity
        assert source_use.acceptance.accepted_at.astimezone(_TAIPEI).isoformat() in identity
        assert source_use.attribution in identity
        assert "候選資料" in identity
        assert "不具歷史 PIT 資格" in identity
        assert "不代表正式來源接受或 P0 整桶接受" in identity
        assert "不得用於連買判斷、評分或交易" in identity
    finally:
        widget.close()
        app.processEvents()


@pytest.mark.parametrize(
    "result",
    [
        replace(_batch_result(), source_use_accepted=True),
        replace(
            _batch_result(market="TWSE"),
            source_use=_qualified_source_use(),
            source_use_accepted=True,
        ),
        replace(
            _batch_result(), source_use=_qualified_source_use(), source_use_accepted=False
        ),
        replace(
            _batch_result(),
            source_use=object(),
            source_use_accepted=True,
        ),
    ],
)
def test_untyped_bare_true_or_crossmarket_acceptance_is_fail_closed(result):
    app = QApplication.instance() or QApplication([])
    widget = InstitutionalDailySnapshotWidget()
    try:
        widget.show_result(result)

        assert widget.rows_table.rowCount() == 0
        assert widget.identity_label.text() == ""
        assert "不符合唯讀顯示契約" in widget.status_label.text()
    finally:
        widget.close()
        app.processEvents()


class _OldSignatureService(FakeUpdateService):
    def __init__(self):
        super().__init__()
        self.read_calls = 0

    def read_saved_institutional_daily_batch(
        self, pin, *, stock_code, decision_cutoff, cancel_callback=None
    ):
        self.read_calls += 1
        return _batch_result()


class _SourceUseAwareService(FakeUpdateService):
    def __init__(self):
        super().__init__()
        self.received_source_use_pin = None

    def read_saved_institutional_daily_batch(
        self,
        pin,
        *,
        stock_code,
        decision_cutoff,
        cancel_callback=None,
        source_use_pin=None,
    ):
        self.received_source_use_pin = source_use_pin
        return _batch_result()


def test_update_view_omits_optional_keyword_for_old_stub_and_passes_only_selected_pin():
    app = QApplication.instance() or QApplication([])
    old_service = _OldSignatureService()
    old_view = _TestableUpdateView(old_service)
    try:
        widget = old_view.institutional_daily_widget
        _select_primary_pin(widget)
        widget.open_button.click()
        _wait(app, lambda: old_view._institutional_daily_worker is None)
        assert old_service.read_calls == 1
        assert widget.rows_table.rowCount() == 1
    finally:
        _close_view(app, old_view)

    source_service = _SourceUseAwareService()
    source_view = _TestableUpdateView(source_service)
    try:
        widget = source_view.institutional_daily_widget
        _select_primary_pin(widget)
        widget.source_use_path_edit.setText("C:/fixed/source-use/source_use.json")
        widget.source_use_sha_edit.setText("e" * 64)
        widget.open_button.click()
        _wait(app, lambda: source_view._institutional_daily_worker is None)
        assert isinstance(source_service.received_source_use_pin, InstitutionalSourceUsePin)
        assert source_service.received_source_use_pin.sha256 == "e" * 64
    finally:
        _close_view(app, source_view)
