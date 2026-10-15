"""唯讀法人批次 widget 顯示 TWSE／TPEx 市場與原始列值。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app_module.institutional_daily_snapshot import (
    InstitutionalDailyRow,
    InstitutionalDailySnapshotPin,
    InstitutionalDailySnapshotRead,
)
from ui_qt.widgets.institutional_daily_snapshot_widget import (
    InstitutionalDailySnapshotWidget,
)


_TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")


def _read_result(*, market: str = "TPEx") -> InstitutionalDailySnapshotRead:
    pin = InstitutionalDailySnapshotPin(
        directory=Path("C:/fixed/tpex-batch"),
        manifest_sha256="a" * 64,
        receipt_sha256="b" * 64,
    )
    row = InstitutionalDailyRow(
        stock_code="2330",
        decision_date="2026-10-15",
        foreign_investor_buy=9007199254740993,
        foreign_investor_sell=202,
        foreign_investor_net=9007199254740791,
        investment_trust_buy=303,
        investment_trust_sell=404,
        investment_trust_net=-101,
        dealer_buy=505,
        dealer_sell=606,
        dealer_net=-101,
        raw_sha256="c" * 64,
        source_version="tpex-openapi-v1",
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
        availability_basis="fixture successful-batch clock",
        market=market,
    )


def _widget() -> tuple[QApplication, InstitutionalDailySnapshotWidget]:
    app = QApplication.instance() or QApplication([])
    return app, InstitutionalDailySnapshotWidget()


def test_tpex_result_shows_market_and_all_nine_original_integer_values():
    app, widget = _widget()
    result = _read_result()
    try:
        widget.show_result(result)

        assert widget.rows_table.rowCount() == 1
        assert "市場：TPEx" in widget.identity_label.text()
        assert "候選資料" in widget.identity_label.text()
        assert "不具歷史 PIT 資格" in widget.identity_label.text()
        assert [widget.rows_table.item(0, column).text() for column in range(2, 11)] == [
            str(getattr(result.rows[0], field))
            for field in (
                "foreign_investor_buy",
                "foreign_investor_sell",
                "foreign_investor_net",
                "investment_trust_buy",
                "investment_trust_sell",
                "investment_trust_net",
                "dealer_buy",
                "dealer_sell",
                "dealer_net",
            )
        ]
        assert widget.rows_table.item(0, 2).text() == "9007199254740993"
    finally:
        widget.close()
        app.processEvents()


@pytest.mark.parametrize(
    "changes",
    [
        {"market": "tpex"},
        {"market": "NASDAQ"},
        {"market": None},
        {"candidate_only": False},
        {"source_use_accepted": True},
        {"historical_pit_eligible": True},
    ],
)
def test_unrecognized_market_or_qualification_is_fail_closed(changes):
    app, widget = _widget()
    try:
        widget.show_result(replace(_read_result(), **changes))

        assert widget.rows_table.rowCount() == 0
        assert widget.identity_label.text() == ""
        assert "不符合唯讀顯示契約" in widget.status_label.text()
    finally:
        widget.close()
        app.processEvents()


def test_wrong_result_type_is_fail_closed():
    app, widget = _widget()
    try:
        widget.show_result(object())  # type: ignore[arg-type]

        assert widget.rows_table.rowCount() == 0
        assert widget.identity_label.text() == ""
        assert "結果型別" in widget.status_label.text()
    finally:
        widget.close()
        app.processEvents()
