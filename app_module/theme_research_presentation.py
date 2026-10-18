"""題材研究首屏的純呈現排序與來源分類目錄。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app_module.theme_daily_service import ThemeDailyReport, ThemeDailyRow, ThemeMetricCoverage
from app_module.theme_research_snapshot import ThemeResearchSnapshot


@dataclass(frozen=True)
class ThemeChainDirectory:
    chain_name: str
    themes: tuple[str, ...]
    stock_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.chain_name) is not str or type(self.themes) is not tuple or type(self.stock_ids) is not tuple:
            raise TypeError("題材鏈目錄欄位須為字串與不可變tuple")
        if any(type(value) is not str for value in (*self.themes, *self.stock_ids)):
            raise TypeError("題材與成員代碼須為字串")


@dataclass(frozen=True)
class ThemeResearchPresentation:
    return_leaders: tuple[ThemeDailyRow, ...]
    turnover_leaders: tuple[ThemeDailyRow, ...]
    institutional_leaders: tuple[ThemeDailyRow, ...]
    volume_leaders: tuple[ThemeDailyRow, ...]
    chains: tuple[ThemeChainDirectory, ...]

    def __post_init__(self) -> None:
        for rows in (self.return_leaders, self.turnover_leaders, self.institutional_leaders, self.volume_leaders):
            if type(rows) is not tuple or any(type(row) is not ThemeDailyRow for row in rows):
                raise TypeError("題材排行榜須使用ThemeDailyRow不可變tuple")
        if type(self.chains) is not tuple or any(type(chain) is not ThemeChainDirectory for chain in self.chains):
            raise TypeError("題材鏈目錄須為不可變tuple")


def _leaders(
    rows: tuple[ThemeDailyRow, ...], *, metric_name: str, coverage_name: str,
    numeric_type: type[Decimal] | type[int],
) -> tuple[ThemeDailyRow, ...]:
    eligible: list[ThemeDailyRow] = []
    for row in rows:
        if type(row) is not ThemeDailyRow or type(row.coverage) is not ThemeMetricCoverage:
            raise TypeError("報表列或涵蓋率型別不符")
        coverage = row.coverage
        members = coverage.members
        metric_coverage = getattr(coverage, coverage_name)
        value = getattr(row, metric_name)
        if type(members) is not int or type(metric_coverage) is not int:
            raise TypeError("題材成員與涵蓋數必須為整數")
        if members <= 0 or metric_coverage != members or value is None:
            continue
        if type(value) is not numeric_type:
            raise TypeError(f"{metric_name}必須使用{numeric_type.__name__}")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError(f"{metric_name}必須為有限Decimal")
        if type(row.chain_name) is not str or type(row.theme_name) is not str:
            raise TypeError("排行榜排序名稱必須為字串")
        eligible.append(row)
    return tuple(sorted(
        eligible,
        key=lambda row: (-getattr(row, metric_name), row.chain_name, row.theme_name),
    )[:5])


def build_theme_research_presentation(snapshot: ThemeResearchSnapshot) -> ThemeResearchPresentation:
    """依既有完整涵蓋率排序觀察值，並從原映射建立穩定目錄；不重算或合併績效。"""
    if type(snapshot) is not ThemeResearchSnapshot:
        raise TypeError("需使用ThemeResearchSnapshot")
    if type(snapshot.report) is not ThemeDailyReport or type(snapshot.report.rows) is not tuple:
        raise TypeError("題材snapshot報表型別不符")
    if type(snapshot.mapping) is not tuple:
        raise TypeError("題材snapshot映射須為不可變tuple")

    rows = snapshot.report.rows
    groups: dict[str, tuple[set[str], set[str]]] = {}
    for mapping_row in snapshot.mapping:
        chain_name = mapping_row.chain_name
        theme_name = mapping_row.theme_name
        stock_id = mapping_row.stock_id
        if any(type(value) is not str for value in (chain_name, theme_name, stock_id)):
            raise TypeError("題材映射名稱與成員代碼必須為字串")
        themes, stock_ids = groups.setdefault(chain_name, (set(), set()))
        themes.add(theme_name)
        stock_ids.add(stock_id)
    chains = tuple(
        ThemeChainDirectory(chain, tuple(sorted(themes)), tuple(sorted(stock_ids)))
        for chain, (themes, stock_ids) in sorted(groups.items())
    )

    return ThemeResearchPresentation(
        return_leaders=_leaders(rows, metric_name="mean_return_pct", coverage_name="returns",
                                numeric_type=Decimal),
        turnover_leaders=_leaders(rows, metric_name="turnover_twd", coverage_name="turnover",
                                  numeric_type=Decimal),
        institutional_leaders=_leaders(rows, metric_name="institutional_net_shares",
                                        coverage_name="institutional_shares", numeric_type=int),
        volume_leaders=_leaders(rows, metric_name="volume_multiple_5d", coverage_name="volume_history",
                                numeric_type=Decimal),
        chains=chains,
    )
