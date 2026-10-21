"""MainWindow 的非 Qt 導覽協調規則。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceDefinition:
    key: str
    label: str
    icon: str


WORKSPACE_DEFINITIONS = (
    WorkspaceDefinition("workbench", "決策工作台", "command"),
    WorkspaceDefinition("market_explore", "市場探索", "radar"),
    WorkspaceDefinition("recommendation", "推薦分析", "spark-list"),
    WorkspaceDefinition("backtest", "策略回測", "replay"),
    WorkspaceDefinition("watchlist", "觀察清單", "bookmark"),
    WorkspaceDefinition("stock_research", "個股研究", "spark-list"),
    WorkspaceDefinition("portfolio", "持倉管理", "briefcase"),
    WorkspaceDefinition("update", "數據更新", "database-sync"),
    WorkspaceDefinition("runtime", "系統狀態", "pulse"),
)


WORKSPACE_ALIASES = {
    "決策工作台": "workbench",
    "每日決策": "workbench",
    "市場探索": "market_explore",
    "市場觀察": "market_explore",
    "推薦分析": "recommendation",
    "策略回測": "backtest",
    "觀察清單": "watchlist",
    "個股研究": "stock_research",
    "個股研究報告": "stock_research",
    "持倉管理": "portfolio",
    "數據更新": "update",
    "Runtime": "runtime",
    "Runtime Observatory": "runtime",
    "系統狀態": "runtime",
}


def resolve_workspace_key(key_or_label: str) -> str:
    return WORKSPACE_ALIASES.get(key_or_label, key_or_label)


# 舊工作區識別保留給既有 callback；V2 僅統一使用者可見的導覽。
PRIMARY_NAVIGATION = (
    WorkspaceDefinition("workbench", "今日總覽", "command"),
    WorkspaceDefinition("explore", "探索與研究", "radar"),
    WorkspaceDefinition("investment", "我的投資", "briefcase"),
    WorkspaceDefinition("laboratory", "策略實驗室", "replay"),
    WorkspaceDefinition("systems", "⚙ 系統管理", "database-sync"),
)


@dataclass(frozen=True)
class ProductRoute:
    route_id: str
    group: str
    label: str
    workspace: str


PRODUCT_ROUTES = (
    ProductRoute("overview", "workbench", "今日總覽", "workbench"),
    ProductRoute("market", "explore", "市場分析", "market_explore"),
    ProductRoute("themes", "explore", "產業與題材", "market_explore"),
    ProductRoute("screener", "explore", "綜合選股", "recommendation"),
    ProductRoute("lookup", "explore", "個股查詢", "stock_lookup"),
    ProductRoute("lists", "investment", "自選與名單", "watchlist"),
    ProductRoute("positions", "investment", "持倉管理", "portfolio"),
    ProductRoute("paper", "investment", "模擬帳與配置", "portfolio"),
    ProductRoute("journal", "investment", "研究紀錄與覆盤", "research_timeline"),
    ProductRoute("strategies", "laboratory", "策略庫", "strategy_library"),
    ProductRoute("backtests", "laboratory", "回測分析", "backtest"),
    ProductRoute("performance", "laboratory", "績效比較", "backtest"),
    ProductRoute("ml", "laboratory", "ML 研究", "recommendation"),
    ProductRoute("data", "systems", "資料與更新", "update"),
    ProductRoute("operations", "systems", "排程與營運", "runtime"),
    ProductRoute("diagnostics", "systems", "環境與來源診斷", "runtime"),
    ProductRoute("storage", "systems", "儲存維護", "storage"),
)

ROUTE_BY_ID = {route.route_id: route for route in PRODUCT_ROUTES}
LEGACY_DEFAULT_ROUTES = {
    "workbench": "overview", "market_explore": "market",
    "recommendation": "screener", "backtest": "backtests",
    "watchlist": "lists", "portfolio": "positions",
    "update": "data", "runtime": "diagnostics", "stock_research": "lookup",
    "stock_lookup": "lookup",
    "strategy_library": "strategies", "research_timeline": "journal", "storage": "storage",
}


def routes_for_group(group: str) -> tuple[ProductRoute, ...]:
    return tuple(route for route in PRODUCT_ROUTES if route.group == group)
