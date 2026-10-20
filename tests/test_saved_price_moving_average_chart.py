"""同版價量顯示均線的前綴、精度與缺值邊界。"""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, localcontext

import pytest

from app_module.saved_price_moving_average_chart import project_saved_price_moving_average_lines
from app_module.stock_research_report_dtos import StockPricePointDTO


def _points(count=120):
    return tuple(StockPricePointDTO(
        data_date=(date(2026, 1, 1) + timedelta(days=index)).isoformat(),
        close_price=Decimal(index + 1), source_id="same_saved_source",
        source_snapshot_hash=f"{index:064x}",
    ) for index in range(count))


def test_exact_windows_warmup_and_future_suffix_never_changes_prefix():
    points = _points()
    ma20, ma60 = project_saved_price_moving_average_lines(points)
    assert all(row.value is None for row in ma20.points[:19])
    assert ma20.points[19].value == Decimal("10.5")
    assert all(row.value is None for row in ma60.points[:59])
    assert ma60.points[59].value == Decimal("30.5")
    assert ma60.points[-1].value == Decimal("90.5")
    changed = points[:80] + tuple(replace(row, close_price=Decimal("999")) for row in points[80:])
    other = project_saved_price_moving_average_lines(changed)
    assert ma20.points[:80] == other[0].points[:80]
    assert ma60.points[:80] == other[1].points[:80]
    assert all(row.available_at == "" for line in other for row in line.points)


def test_missing_close_restarts_both_windows_and_does_not_fill_zero():
    points = list(_points())
    points[30] = replace(points[30], close_price=None)
    ma20, ma60 = project_saved_price_moving_average_lines(tuple(points))
    assert all(row.value is None for row in ma20.points[30:50])
    assert ma20.points[50].value == Decimal("41.5")
    assert all(row.value is None for row in ma60.points[30:90])
    assert ma60.points[90].value == Decimal("61.5")


def test_decimal_result_independent_of_caller_context():
    points = tuple(replace(row, close_price=Decimal("12345678901234567890.0123456789") + Decimal(index % 3))
                   for index, row in enumerate(_points()))
    original = project_saved_price_moving_average_lines(points)
    with localcontext() as ctx:
        ctx.prec = 6
        ctx.rounding = ROUND_DOWN
        assert project_saved_price_moving_average_lines(points) == original


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-1"), Decimal(0)])
def test_nonfinite_or_nonpositive_prices_rejected(value):
    points = _points(1)
    with pytest.raises(ValueError, match="invalid_close"):
        project_saved_price_moving_average_lines((replace(points[0], close_price=value),))


def test_changed_source_duplicate_date_and_capacity_rejected():
    points = _points(2)
    with pytest.raises(ValueError, match="source_mismatch"):
        project_saved_price_moving_average_lines((points[0], replace(points[1], source_id="another")))
    with pytest.raises(ValueError, match="date_order"):
        project_saved_price_moving_average_lines((points[0], points[0]))
    with pytest.raises(ValueError, match="row_limit"):
        project_saved_price_moving_average_lines(_points(121))
