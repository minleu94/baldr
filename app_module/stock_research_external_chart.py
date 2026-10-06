"""TradingView 外部參考入口；僅使用已核實主站商品，無網路讀價。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class StockExternalChartLinkDTO:
    stock_code: str
    exchange: str
    symbol: str
    url: str
    identity_source: str = "docs/06_qa/UX07_CHART_FEASIBILITY_20261005.md#台股-widget-獨立-lane-補充"
    same_source: bool = False
    historical_pit_eligible: bool = False


# 既有官方主站身份收據的有限清冊，不由代碼形狀猜交易所。
_VERIFIED_WEBSITE_SYMBOLS = {
    "2382": ("TWSE", "2382"), "1477": ("TWSE", "1477"),
    "6488": ("TPEX", "6488"), "00878": ("TWSE", "00878"),
    "IX0001": ("TWSE", "IX0001"),
}


def stock_external_chart_link(stock_code: str) -> StockExternalChartLinkDTO | None:
    identity = _VERIFIED_WEBSITE_SYMBOLS.get(stock_code)
    if identity is None:
        return None
    exchange, symbol = identity
    return StockExternalChartLinkDTO(stock_code, exchange, symbol,
        f"https://tw.tradingview.com/symbols/{exchange}-{symbol}/")
