"""題材盤後觀察聚合；缺件保留，研究結果不授歷史 PIT 或交易資格。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Protocol, Sequence

from decision_module.industry_theme_map import ThemeMappingRow

_TAIPEI = timezone(timedelta(hours=8))
if TYPE_CHECKING:
    from app_module.recommendation_portfolio_calendar_evidence_v1 import PortfolioPeriodCalendarEvidenceV1


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("可得時間必須包含時區")


def _number(value: Decimal | None, *, nonnegative: bool = False) -> None:
    if value is not None and (
        not isinstance(value, Decimal) or not value.is_finite()
        or (nonnegative and value < 0)
    ):
        raise ValueError("金額與價格只接受有限 Decimal，且不得超出欄位範圍")


def _shares(value: int | None, *, nonnegative: bool = False) -> None:
    if value is not None and (
        type(value) is not int or (nonnegative and value < 0)
    ):
        raise ValueError("股數必須為整數；成交股數不得為負")


@dataclass(frozen=True)
class ThemePriceObservation:
    stock_id: str
    data_date: date
    available_at: datetime | None
    source_id: str
    close_twd: Decimal | None = None
    change_twd: Decimal | None = None
    turnover_twd: Decimal | None = None
    volume_shares: int | None = None

    def __post_init__(self) -> None:
        if self.available_at is not None:
            _aware(self.available_at)
        _number(self.close_twd, nonnegative=True)
        _number(self.change_twd)
        _number(self.turnover_twd, nonnegative=True)
        _shares(self.volume_shares, nonnegative=True)


@dataclass(frozen=True)
class ThemeFlowObservation:
    """三大法人合計；股數與TWD金額分欄，不用成交價格反推金額。"""

    stock_id: str
    data_date: date
    available_at: datetime | None
    source_id: str
    net_shares: int | None = None
    net_turnover_twd: Decimal | None = None

    def __post_init__(self) -> None:
        if self.available_at is not None:
            _aware(self.available_at)
        _shares(self.net_shares)
        _number(self.net_turnover_twd)


@dataclass(frozen=True)
class ThemeMarketInput:
    prices: tuple[ThemePriceObservation, ...] = ()
    flows: tuple[ThemeFlowObservation, ...] = ()
    # 須由讀者提供已核指定市場的前五個交易日；不能拿最近五筆代替缺日。
    previous_sessions: tuple[date, ...] = ()
    session_source_id: str = ""
    warnings: tuple[str, ...] = ()
    calendar_evidence: PortfolioPeriodCalendarEvidenceV1 | None = None


class ThemeMappingReader(Protocol):
    def load_pit_mapping(
        self, as_of_date: str,
    ) -> tuple[list[ThemeMappingRow], str, str, str, list[str]]: ...


class ThemeMarketReader(Protocol):
    def read(
        self, stock_ids: tuple[str, ...], data_date: date, known_at: datetime,
    ) -> ThemeMarketInput: ...


@dataclass(frozen=True)
class ThemeMetricCoverage:
    members: int
    returns: int
    turnover: int
    volume_history: int
    institutional_shares: int
    institutional_amount: int


@dataclass(frozen=True)
class ThemeDailyRow:
    chain_name: str
    theme_name: str
    stock_ids: tuple[str, ...]
    mean_return_pct: Decimal | None
    turnover_twd: Decimal | None
    volume_multiple_5d: Decimal | None
    institutional_net_shares: int | None
    institutional_net_turnover_twd: Decimal | None
    up_count: int
    down_count: int
    flat_count: int
    institutional_buy_count: int
    institutional_sell_count: int
    institutional_flat_count: int
    # 共振採上漲家數／漲跌幅已知家數，沒有另造綜合分數。
    advancing_ratio: Decimal | None
    institutional_buy_ratio: Decimal | None
    coverage: ThemeMetricCoverage
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ThemeDailyReport:
    data_date: date
    known_at: datetime
    mapping_snapshot_date: str
    mapping_available_date: str
    status: str
    rows: tuple[ThemeDailyRow, ...]
    warnings: tuple[str, ...]
    # 映射日期篩選不代替官方用途、版本原件及精確可得時間的接受。
    historical_pit_eligible: bool = False


def _sum_decimal(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) if values else None


def _volume_multiple(today: int, prior_five_total: int) -> Decimal | None:
    """純數值口徑；是否有權使用交易日由具名日曆證據另外裁決。"""
    return Decimal(today) * 5 / prior_five_total if prior_five_total > 0 else None


class ThemeDailyService:
    """沿既有映射讀者計算等權題材觀察；不寫資料、不建立今日分類。"""

    def __init__(
        self, mapping_reader: ThemeMappingReader, market_reader: ThemeMarketReader,
        *, mapping_available_at: datetime | None = None,
    ):
        self.mapping_reader = mapping_reader
        self.market_reader = market_reader
        if mapping_available_at is not None:
            _aware(mapping_available_at)
        self.mapping_available_at = mapping_available_at

    def build(self, data_date: date, known_at: datetime) -> ThemeDailyReport:
        _aware(known_at)
        if data_date > known_at.astimezone(_TAIPEI).date():
            raise ValueError("資料日不得晚於台北查詢時鐘")
        rows, snap, available, pit_status, warnings = self.mapping_reader.load_pit_mapping(
            data_date.isoformat(),
        )
        reasons = list(warnings)
        valid = pit_status == "pit_snapshot_aligned" and bool(rows)
        if self.mapping_available_at is None or self.mapping_available_at > known_at:
            valid = False
            reasons.append("mapping_clock_unavailable_or_future")
        try:
            valid = valid and date.fromisoformat(snap) <= data_date
            valid = valid and date.fromisoformat(available) <= data_date
            for row in rows:
                valid = valid and row.snapshot_date == snap and row.available_date == available
                valid = valid and bool(row.chain_name.strip()) and bool(row.theme_name.strip())
                valid = valid and len(row.stock_id) == 4 and row.stock_id.isascii() and row.stock_id.isdigit()
        except (ValueError, TypeError):
            valid = False
        if not valid:
            return ThemeDailyReport(data_date, known_at, snap, available, "mapping_unavailable", (),
                                    tuple(sorted(set(reasons + ["mapping_not_date_aligned"]))),)

        groups: dict[tuple[str, str], dict[str, ThemeMappingRow]] = {}
        for row in rows:
            group = groups.setdefault((row.chain_name, row.theme_name), {})
            if row.stock_id in group and group[row.stock_id] != row:
                raise ValueError("同一題材的股票映射互相衝突")
            group[row.stock_id] = row
        members = tuple(sorted({row.stock_id for row in rows}))
        member_set = set(members)
        market = self.market_reader.read(members, data_date, known_at)
        reasons.extend(market.warnings)
        sessions = market.previous_sessions
        qualified_calendar = False
        if market.calendar_evidence is not None:
            from app_module.recommendation_portfolio_calendar_evidence_v1 import PortfolioPeriodCalendarEvidenceV1
            evidence = market.calendar_evidence
            if (type(evidence) is PortfolioPeriodCalendarEvidenceV1
                    and not evidence.candidate_only and evidence.formal_clock_eligible):
                # 沿既有證據型別，不另造可由字串授予資格的日曆系統。
                markets = {row.market_type.lower() for row in rows}
                if markets and markets <= {"twse", "tpex"}:
                    selected = [evidence.expected_session_dates("twse" if name == "twse" else "tpex")
                                for name in sorted(markets)]
                    qualified_calendar = all(
                        data_date.isoformat() in days
                        and tuple(date.fromisoformat(day) for day in days if day < data_date.isoformat())[-5:] == sessions
                        for days in selected
                    )
        calendar_ok = (
            qualified_calendar and len(sessions) == 5 and len(set(sessions)) == 5
            and tuple(sorted(sessions)) == sessions
            and all(day < data_date for day in sessions) and bool(market.session_source_id)
        )
        if not calendar_ok:
            reasons.append("five_session_calendar_unavailable")
        wanted_dates = {data_date, *(sessions if calendar_ok else ())}
        prices: dict[tuple[str, date], ThemePriceObservation] = {}
        flows: dict[str, ThemeFlowObservation] = {}
        for price in market.prices:
            if price.stock_id not in member_set or price.data_date not in wanted_dates:
                continue
            if (price.available_at is None or price.available_at > known_at or not price.source_id
                    or price.available_at.astimezone(_TAIPEI).date() < price.data_date):
                reasons.append("price_clock_or_source_unavailable")
                continue
            key = (price.stock_id, price.data_date)
            if key in prices:
                raise ValueError("價格同股同日重複，須先明選原版本")
            prices[key] = price
        for flow in market.flows:
            if flow.stock_id not in member_set or flow.data_date != data_date:
                continue
            if (flow.available_at is None or flow.available_at > known_at or not flow.source_id
                    or flow.available_at.astimezone(_TAIPEI).date() < flow.data_date):
                reasons.append("flow_clock_or_source_unavailable")
                continue
            if flow.stock_id in flows:
                raise ValueError("法人同股同日重複，須先明選原版本")
            flows[flow.stock_id] = flow

        result: list[ThemeDailyRow] = []
        # 固定運算精度，不受呼叫端Decimal context左右；不回流裸float。
        with localcontext() as ctx:
            ctx.prec = 38
            for (chain, theme), group in sorted(groups.items()):
                ids = tuple(sorted(group))
                returns: list[Decimal] = []
                turnovers: list[Decimal] = []
                share_flows: list[int] = []
                amount_flows: list[Decimal] = []
                volume_count = 0
                today_volume = 0
                history_volume = 0
                sources: set[str] = set()
                for stock_id in ids:
                    current = prices.get((stock_id, data_date))
                    if current is not None:
                        sources.add(current.source_id)
                        if current.close_twd is not None and current.change_twd is not None:
                            previous = current.close_twd - current.change_twd
                            if previous > 0 and current.close_twd > 0:
                                returns.append(current.change_twd / previous * 100)
                        if current.turnover_twd is not None:
                            turnovers.append(current.turnover_twd)
                        history = [prices.get((stock_id, day)) for day in sessions] if calendar_ok else []
                        if current.volume_shares is not None and len(history) == 5 and all(
                            item is not None and item.volume_shares is not None for item in history
                        ):
                            volume_count += 1
                            today_volume += current.volume_shares
                            for item in history:
                                assert item is not None and item.volume_shares is not None
                                history_volume += item.volume_shares
                                sources.add(item.source_id)
                    member_flow = flows.get(stock_id)
                    if member_flow is not None:
                        sources.add(member_flow.source_id)
                        if member_flow.net_shares is not None:
                            share_flows.append(member_flow.net_shares)
                        if member_flow.net_turnover_twd is not None:
                            amount_flows.append(member_flow.net_turnover_twd)
                n = len(returns)
                fn = len(share_flows)
                up = sum(value > 0 for value in returns)
                down = sum(value < 0 for value in returns)
                buy = sum(value > 0 for value in share_flows)
                sell = sum(value < 0 for value in share_flows)
                result.append(ThemeDailyRow(
                    chain, theme, ids, sum(returns, Decimal(0)) / n if n else None,
                    _sum_decimal(turnovers),
                    _volume_multiple(today_volume, history_volume) if volume_count == len(ids) else None,
                    sum(share_flows) if share_flows else None, _sum_decimal(amount_flows),
                    up, down, n - up - down, buy, sell, fn - buy - sell,
                    Decimal(up) / n if n else None, Decimal(buy) / fn if fn else None,
                    ThemeMetricCoverage(len(ids), n, len(turnovers), volume_count, fn, len(amount_flows)),
                    tuple(sorted(sources)),
                ))
        reasons.append("mapping_dates_only_not_historical_pit_acceptance")
        return ThemeDailyReport(data_date, known_at, snap, available, "current_research", tuple(result),
                                tuple(sorted(set(reasons))))
