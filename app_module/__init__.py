"""應用服務層的相容 public API。

舊頂層名稱維持可直接匯入；純 leaf contract 匯入不載入具體服務。
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.backtest_service import BacktestService
    from app_module.dtos import (
        BacktestReportDTO,
        RegimeResultDTO,
    )
    from app_module.journal_service import JournalService
    from app_module.portfolio_service import PortfolioService
    from app_module.recommendation.legacy_dtos import (
        RecommendationDTO,
        RecommendationResultDTO,
    )
    from app_module.recommendation_service import RecommendationService
    from app_module.regime_service import RegimeService
    from app_module.screening_service import ScreeningService
    from app_module.update_service import UpdateService

__all__ = [
    "RecommendationService",
    "ScreeningService",
    "RegimeService",
    "UpdateService",
    "BacktestService",
    "PortfolioService",
    "JournalService",
    "RecommendationDTO",
    "RecommendationResultDTO",
    "RegimeResultDTO",
    "BacktestReportDTO",
]

_EXPORTS = {
    "RecommendationService": ("app_module.recommendation_service", "RecommendationService"),
    "ScreeningService": ("app_module.screening_service", "ScreeningService"),
    "RegimeService": ("app_module.regime_service", "RegimeService"),
    "UpdateService": ("app_module.update_service", "UpdateService"),
    "BacktestService": ("app_module.backtest_service", "BacktestService"),
    "PortfolioService": ("app_module.portfolio_service", "PortfolioService"),
    "JournalService": ("app_module.journal_service", "JournalService"),
    "RecommendationDTO": ("app_module.recommendation.legacy_dtos", "RecommendationDTO"),
    "RecommendationResultDTO": ("app_module.recommendation.legacy_dtos", "RecommendationResultDTO"),
    "RegimeResultDTO": ("app_module.dtos", "RegimeResultDTO"),
    "BacktestReportDTO": ("app_module.dtos", "BacktestReportDTO"),
}


def __getattr__(name: str) -> object:
    export = _EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = export
    module = import_module(module_name)
    value: object = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

