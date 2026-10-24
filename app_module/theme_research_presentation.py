"""題材研究首屏的純呈現排序與來源分類目錄。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

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
class ThemeReturnTile:
    """完整漲跌覆蓋題材的唯讀格子，保留原始觀察值與版本脈絡。"""

    chain_name: str
    theme_name: str
    mean_return_pct: Decimal
    returns_coverage: int
    members: int
    data_date: str
    mapping_snapshot_date: str
    mapping_available_date: str
    known_at: str
    snapshot_identity: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(type(value) is not str for value in (
            self.chain_name, self.theme_name, self.data_date,
            self.mapping_snapshot_date, self.mapping_available_date,
            self.known_at, self.snapshot_identity,
        )):
            raise TypeError("題材格子來源脈絡須為字串")
        if type(self.mean_return_pct) is not Decimal or not self.mean_return_pct.is_finite():
            raise TypeError("題材格子漲跌幅須為有限Decimal")
        if (type(self.returns_coverage) is not int or type(self.members) is not int
                or self.members <= 0 or self.returns_coverage != self.members):
            raise ValueError("題材格子只接受成員漲跌覆蓋完整的列")
        if type(self.source_ids) is not tuple or any(type(value) is not str for value in self.source_ids):
            raise TypeError("題材格子來源識別須為字串tuple")


@dataclass(frozen=True)
class ThemeTurnoverTile:
    """完整成交金額覆蓋題材的原值，保留快照與來源脈絡。"""

    chain_name: str
    theme_name: str
    turnover_twd: Decimal
    turnover_coverage: int
    members: int
    data_date: str
    mapping_snapshot_date: str
    mapping_available_date: str
    known_at: str
    snapshot_identity: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(type(value) is not str for value in (
            self.chain_name, self.theme_name, self.data_date,
            self.mapping_snapshot_date, self.mapping_available_date,
            self.known_at, self.snapshot_identity,
        )):
            raise TypeError("成交金額題材格來源脈絡須為字串")
        if (type(self.turnover_twd) is not Decimal or not self.turnover_twd.is_finite()
                or self.turnover_twd < 0):
            raise ValueError("成交金額題材格須為有限非負Decimal")
        if (type(self.turnover_coverage) is not int or type(self.members) is not int
                or self.members <= 0 or self.turnover_coverage != self.members):
            raise ValueError("成交金額題材格只接受成員覆蓋完整的列")
        if type(self.source_ids) is not tuple or any(type(value) is not str for value in self.source_ids):
            raise TypeError("成交金額題材格來源識別須為字串tuple")


@dataclass(frozen=True)
class ThemeReturnVersionObservation:
    """單一明選版本的題材原值；缺值與部分覆蓋一律以None呈現。"""

    chain_name: str
    theme_name: str
    stock_ids: tuple[str, ...]
    member_count: int
    mean_return_pct: Decimal | None
    returns_coverage: int | None
    row_present: bool
    data_date: str
    mapping_snapshot_date: str
    mapping_available_date: str
    known_at: str
    snapshot_identity: str
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(type(value) is not str for value in (
            self.chain_name, self.theme_name, self.data_date,
            self.mapping_snapshot_date, self.mapping_available_date,
            self.known_at, self.snapshot_identity,
        )):
            raise TypeError("版本觀察來源脈絡須為字串")
        if (type(self.stock_ids) is not tuple
                or any(type(value) is not str for value in self.stock_ids)):
            raise TypeError("版本觀察成員須為字串tuple")
        if type(self.member_count) is not int or self.member_count < 0:
            raise ValueError("版本觀察成員數須為非負整數")
        if type(self.row_present) is not bool:
            raise TypeError("版本觀察列存在狀態須為布林值")
        if self.row_present:
            if (type(self.returns_coverage) is not int
                    or not 0 <= self.returns_coverage <= self.member_count):
                raise ValueError("報酬覆蓋數超出成員分母")
        elif self.returns_coverage is not None or self.mean_return_pct is not None:
            raise ValueError("缺少報表列時不得推定覆蓋數或漲跌幅")
        if self.mean_return_pct is not None and (
            type(self.mean_return_pct) is not Decimal or not self.mean_return_pct.is_finite()
        ):
            raise TypeError("版本觀察報酬須為有限Decimal或None")
        if self.mean_return_pct is not None and (
            not self.row_present or self.member_count == 0
            or self.returns_coverage != self.member_count
        ):
            raise ValueError("版本觀察原值須有完整非空成員覆蓋")
        if type(self.source_ids) is not tuple or any(type(value) is not str for value in self.source_ids):
            raise TypeError("版本觀察來源識別須為字串tuple")


@dataclass(frozen=True)
class ThemeReturnTwoVersionPresentation:
    """兩個明選版本的獨立原值列，順序與呼叫端選取順序相同。"""

    observations: tuple[ThemeReturnVersionObservation, ThemeReturnVersionObservation]

    def __post_init__(self) -> None:
        if (type(self.observations) is not tuple or len(self.observations) != 2
                or any(type(item) is not ThemeReturnVersionObservation for item in self.observations)):
            raise TypeError("雙版本呈現須恰有兩筆版本觀察")
        if self.observations[0].snapshot_identity == self.observations[1].snapshot_identity:
            raise ValueError("雙版本呈現不可重複使用同一快照身份")


def build_theme_return_two_version_presentation(
    first: ThemeResearchSnapshot,
    second: ThemeResearchSnapshot,
    *,
    chain_name: str,
    theme_name: str,
) -> ThemeReturnTwoVersionPresentation:
    """投影兩個呼叫端已明選版本的同標籤題材原值，不讀檔、不計算差值。"""
    if type(chain_name) is not str or not chain_name.strip() or type(theme_name) is not str or not theme_name.strip():
        raise ValueError("須明選非空題材鏈與題材名稱")
    if type(first) is not ThemeResearchSnapshot or type(second) is not ThemeResearchSnapshot:
        raise TypeError("雙版本投影須使用兩個已讀取的ThemeResearchSnapshot")
    if first.identity_sha256 == second.identity_sha256:
        raise ValueError("雙版本投影不可重複使用同一快照身份")

    def observe(snapshot: ThemeResearchSnapshot) -> ThemeReturnVersionObservation:
        if re.fullmatch(r"[0-9a-f]{64}", snapshot.identity_sha256, re.ASCII) is None:
            raise ValueError("題材快照身份須為SHA256")
        report = snapshot.report
        if type(report) is not ThemeDailyReport or type(report.rows) is not tuple or type(snapshot.mapping) is not tuple:
            raise TypeError("題材快照報表或映射型別不符")
        if report.status != "current_research":
            raise ValueError("雙版本呈現只接受已驗證的current_research快照")
        if any(type(item) is not ThemeDailyRow for item in report.rows):
            raise TypeError("題材快照含非ThemeDailyRow列")
        matching_rows = tuple(
            row for row in report.rows if row.chain_name == chain_name and row.theme_name == theme_name
        )
        if len(matching_rows) > 1:
            raise ValueError("同一版本含重複題材觀察列")
        row = matching_rows[0] if matching_rows else None
        if row is not None and type(row.coverage) is not ThemeMetricCoverage:
            raise TypeError("題材觀察列涵蓋率型別不符")
        mapped_ids: list[str] = []
        for item in snapshot.mapping:
            if type(item.chain_name) is not str or type(item.theme_name) is not str or type(item.stock_id) is not str:
                raise TypeError("題材映射的鏈、題材與成員欄位須為字串")
            if item.chain_name == chain_name and item.theme_name == theme_name and item.stock_id not in mapped_ids:
                mapped_ids.append(item.stock_id)
        stock_ids = row.stock_ids if row is not None else tuple(mapped_ids)
        if type(stock_ids) is not tuple or any(type(value) is not str for value in stock_ids):
            raise TypeError("題材觀察成員須為字串tuple")
        source_ids: tuple[str, ...]
        if row is None:
            members, coverage, value, source_ids = len(stock_ids), None, None, ()
        else:
            members = row.coverage.members
            coverage = row.coverage.returns
            if type(members) is not int or members < 0 or type(coverage) is not int or not 0 <= coverage <= members:
                raise ValueError("題材報酬覆蓋數或分母不合法")
            candidate = row.mean_return_pct
            value = candidate if coverage == members and members > 0 and type(candidate) is Decimal and candidate.is_finite() else None
            source_ids = row.source_ids
        return ThemeReturnVersionObservation(
            chain_name, theme_name, stock_ids, members, value, coverage, row is not None,
            report.data_date.isoformat(), report.mapping_snapshot_date,
            report.mapping_available_date, report.known_at.isoformat(),
            snapshot.identity_sha256, source_ids,
        )

    return ThemeReturnTwoVersionPresentation((observe(first), observe(second)))


@dataclass(frozen=True)
class ThemeResearchPresentation:
    return_leaders: tuple[ThemeDailyRow, ...]
    turnover_leaders: tuple[ThemeDailyRow, ...]
    institutional_leaders: tuple[ThemeDailyRow, ...]
    volume_leaders: tuple[ThemeDailyRow, ...]
    chains: tuple[ThemeChainDirectory, ...]
    return_tiles: tuple[ThemeReturnTile, ...] = ()
    return_tile_total: int = 0
    turnover_tiles: tuple[ThemeTurnoverTile, ...] = ()
    turnover_tile_total: int = 0

    def __post_init__(self) -> None:
        for rows in (self.return_leaders, self.turnover_leaders, self.institutional_leaders, self.volume_leaders):
            if type(rows) is not tuple or any(type(row) is not ThemeDailyRow for row in rows):
                raise TypeError("題材排行榜須使用ThemeDailyRow不可變tuple")
        if type(self.chains) is not tuple or any(type(chain) is not ThemeChainDirectory for chain in self.chains):
            raise TypeError("題材鏈目錄須為不可變tuple")
        if type(self.return_tiles) is not tuple or any(type(tile) is not ThemeReturnTile for tile in self.return_tiles):
            raise TypeError("漲跌題材格子須為不可變tuple")
        if type(self.return_tile_total) is not int or self.return_tile_total < len(self.return_tiles):
            raise ValueError("漲跌題材格子總數不可小於合格數")
        if type(self.turnover_tiles) is not tuple or any(type(tile) is not ThemeTurnoverTile for tile in self.turnover_tiles):
            raise TypeError("成交金額題材格須為不可變tuple")
        if type(self.turnover_tile_total) is not int or self.turnover_tile_total < len(self.turnover_tiles):
            raise ValueError("成交金額題材格總數不可小於合格數")


def _leaders(
    rows: tuple[ThemeDailyRow, ...], *, metric_name: str, coverage_name: str,
    numeric_type: type[Decimal] | type[int], ascending: bool = False,
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
    # 先排同值名稱，再穩定排序原值；不以負號觸發呼叫端Decimal精度捨入。
    by_name = sorted(eligible, key=lambda row: (row.chain_name, row.theme_name))
    return tuple(sorted(
        by_name, key=lambda row: getattr(row, metric_name), reverse=not ascending,
    )[:5])


def build_theme_research_presentation(
    snapshot: ThemeResearchSnapshot, *, ascending: bool = False,
) -> ThemeResearchPresentation:
    """依完整涵蓋率列出高端或低端觀察，保留原精度與映射；不重算或合併績效。"""
    if type(ascending) is not bool:
        raise TypeError("題材排序方向須為bool")
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
    return_tiles = tuple(
        ThemeReturnTile(
            chain_name=row.chain_name,
            theme_name=row.theme_name,
            mean_return_pct=row.mean_return_pct,
            returns_coverage=row.coverage.returns,
            members=row.coverage.members,
            data_date=snapshot.report.data_date.isoformat(),
            mapping_snapshot_date=snapshot.report.mapping_snapshot_date,
            mapping_available_date=snapshot.report.mapping_available_date,
            known_at=snapshot.report.known_at.isoformat(),
            snapshot_identity=snapshot.identity_sha256,
            source_ids=row.source_ids,
        )
        for row in rows
        if (type(row) is ThemeDailyRow
            and type(row.coverage) is ThemeMetricCoverage
            and type(row.coverage.members) is int and row.coverage.members > 0
            and row.coverage.returns == row.coverage.members
            and type(row.mean_return_pct) is Decimal
            and row.mean_return_pct.is_finite())
    )
    turnover_tiles = tuple(
        ThemeTurnoverTile(
            chain_name=row.chain_name,
            theme_name=row.theme_name,
            turnover_twd=row.turnover_twd,
            turnover_coverage=row.coverage.turnover,
            members=row.coverage.members,
            data_date=snapshot.report.data_date.isoformat(),
            mapping_snapshot_date=snapshot.report.mapping_snapshot_date,
            mapping_available_date=snapshot.report.mapping_available_date,
            known_at=snapshot.report.known_at.isoformat(),
            snapshot_identity=snapshot.identity_sha256,
            source_ids=row.source_ids,
        )
        for row in rows
        if (type(row) is ThemeDailyRow
            and type(row.coverage) is ThemeMetricCoverage
            and type(row.coverage.members) is int and row.coverage.members > 0
            and row.coverage.turnover == row.coverage.members
            and type(row.turnover_twd) is Decimal
            and row.turnover_twd.is_finite() and row.turnover_twd >= 0)
    )

    return ThemeResearchPresentation(
        return_leaders=_leaders(rows, metric_name="mean_return_pct", coverage_name="returns",
                                numeric_type=Decimal, ascending=ascending),
        turnover_leaders=_leaders(rows, metric_name="turnover_twd", coverage_name="turnover",
                                  numeric_type=Decimal, ascending=ascending),
        institutional_leaders=_leaders(rows, metric_name="institutional_net_shares",
                                        coverage_name="institutional_shares", numeric_type=int,
                                        ascending=ascending),
        volume_leaders=_leaders(rows, metric_name="volume_multiple_5d", coverage_name="volume_history",
                                numeric_type=Decimal, ascending=ascending),
        chains=chains,
        return_tiles=return_tiles,
        return_tile_total=len(rows),
        turnover_tiles=turnover_tiles,
        turnover_tile_total=len(rows),
    )
