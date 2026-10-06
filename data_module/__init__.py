"""Data module public API.

Keep the legacy top-level names available without importing concrete providers
when a pure leaf contract is imported from ``data_module.contracts``.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import TWStockConfig
    from .data_loader import DataLoader, MarketDateRange
    from .data_processor import TWMarketDataProcessor

__all__ = ["TWStockConfig", "MarketDateRange", "TWMarketDataProcessor", "DataLoader"]


def __getattr__(name: str) -> object:
    value: object
    if name == "TWStockConfig":
        from .config import TWStockConfig

        value = TWStockConfig
    elif name in ("MarketDateRange", "DataLoader"):
        from .data_loader import DataLoader, MarketDateRange

        value = {"MarketDateRange": MarketDateRange, "DataLoader": DataLoader}[name]
    elif name == "TWMarketDataProcessor":
        from .data_processor import TWMarketDataProcessor

        value = TWMarketDataProcessor
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
