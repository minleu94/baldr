"""同版保存價量的顯示用SMA；不讀外部行情、不回流選股或授予PIT。"""
from __future__ import annotations

from collections import deque
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256

from app_module.stock_research_chart_payload import StockChartTechnicalLineDTO, StockChartTechnicalPointDTO
from app_module.stock_research_report_dtos import StockPricePointDTO


def project_saved_price_moving_average_lines(
    points: tuple[StockPricePointDTO, ...],
) -> tuple[StockChartTechnicalLineDTO, ...]:
    """僅用截至各觀測日的20/60筆原收盤價；缺列值重置暖機。"""
    if len(points) > 120:
        raise ValueError("saved_price_sma_row_limit")
    previous = ""
    source_id = points[0].source_id if points else ""
    for point in points:
        if date.fromisoformat(point.data_date).isoformat() != point.data_date or point.data_date <= previous:
            raise ValueError("saved_price_sma_date_order")
        if point.source_id != source_id:
            raise ValueError("saved_price_sma_source_mismatch")
        if point.close_price is not None and (
            not isinstance(point.close_price, Decimal)
            or not point.close_price.is_finite() or point.close_price <= 0
        ):
            raise ValueError("saved_price_sma_invalid_close")
        previous = point.data_date
    lines = []
    for period in (20, 60):
        window: deque[StockPricePointDTO] = deque(maxlen=period)
        projected = []
        for point in points:
            if point.close_price is None:
                window.clear()
            else:
                window.append(point)
            value = None
            if len(window) == period:
                values = [row.close_price for row in window]
                assert all(isinstance(item, Decimal) for item in values)
                exact_values = [item for item in values if isinstance(item, Decimal)]
                # 保留輸入精度並為加總與除法增加餘裕，不依賴呼叫端的Decimal context。
                precision = max(28, max(item.adjusted() for item in exact_values)
                    - min(int(item.as_tuple().exponent) for item in exact_values) + 32)
                with localcontext(Context(prec=precision, rounding=ROUND_HALF_EVEN)):
                    value = sum(exact_values, Decimal(0)) / Decimal(period)
            lineage = "|".join((str(period), *(row.source_snapshot_hash for row in window)))
            projected.append(StockChartTechnicalPointDTO(
                data_date=point.data_date, value=value,
                source_id=f"{source_id}:saved_price_sma_display.v1",
                source_row_hash=sha256(lineage.encode("utf-8")).hexdigest(),
            ))
        lines.append(StockChartTechnicalLineDTO(
            key=f"MA{period}", label=f"顯示用SMA{period}（同版收盤價）", points=tuple(projected),
        ))
    return tuple(lines)
