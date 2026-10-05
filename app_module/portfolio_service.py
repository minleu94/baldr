"""Thin orchestration service for the Phase 4.1 Portfolio MVP."""

import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation
from hashlib import sha256
import io
import json
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
import pandas as pd

from app_module.market_session_cadence import MarketSessionCadence, TAIPEI

from app_module.dtos.portfolio_dtos import (
    LedgerEventDTO,
    LedgerPositionDTO,
    LedgerProjectionDTO,
    PortfolioDTO,
    PortfolioLedgerReadModelDTO,
    PositionDTO,
    RecordedTradeCostSummaryDTO,
    TradeDTO,
)
from app_module.portfolio_store import PortfolioJsonlStore
from app_module.sqlite_read_only import ReadOnlySQLiteManager
from data_module.config import TWStockConfig
from data_module.portfolio_ledger_repository import (
    PortfolioLedgerEvent,
    PortfolioLedgerRepository,
)
from financial_module.units import quantize_money, to_decimal
from portfolio_module import PortfolioValidationError, Trade, rebuild_positions, validate_trade
from portfolio_module.core import (
    LedgerProjection,
    ledger_unrealized_pnl,
    rebuild_ledger_projection,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortfolioQuoteObservation:
    """唯讀行情列及其資料日、來源指紋和官方市場節奏評估。"""

    stock_code: str
    price: Decimal | None
    data_date: date | None
    source_id: str
    source_snapshot_hash: str
    freshness_status: str
    expected_date: date | None
    freshness_reason: str = ""


class PortfolioService:
    """Coordinates trade storage and derived position views.

    Trades are append-only source records. Positions are rebuilt from trades.
    """

    def __init__(
        self,
        config: TWStockConfig,
        position_service: object = None,
        ledger_repository: Optional[PortfolioLedgerRepository] = None,
        *,
        market_session_cadence: MarketSessionCadence | None = None,
        now_provider: Any | None = None,
    ):
        self.config = config
        self.position_service = position_service
        self.store = PortfolioJsonlStore(config.output_root)
        # 只有呼叫者明確注入隔離 repository 才會啟用精確帳本；既有 JSONL
        # 相容路徑仍由既有測試與 UI 使用，避免偷偷切換正式 writer。
        self.ledger_repository = ledger_repository
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.market_session_cadence = market_session_cadence or MarketSessionCadence.for_config(
            config, clock=self._now_provider
        )

    def record_trade(
        self,
        stock_code: str,
        stock_name: str,
        side: str,
        quantity: float,
        price: float,
        trade_date: str,
        portfolio_id: str = "default",
        fees: float = 0.0,
        taxes: float = 0.0,
        currency: str = "TWD",
        notes: str = "",
        source_type: str = "",
        source_id: str = "",
        source_snapshot_hash: str = "",
        source_summary: Optional[Dict[str, Any]] = None,
        trade_id: Optional[str] = None,
    ) -> TradeDTO:
        """Append a manual trade record after domain validation."""
        created_at = datetime.now().isoformat()
        dto = TradeDTO(
            trade_id=trade_id or f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}",
            portfolio_id=portfolio_id,
            stock_code=stock_code,
            stock_name=stock_name,
            side=side.lower(),
            quantity=float(quantity),  # numeric-boundary: dto
            price=float(price),  # numeric-boundary: dto
            trade_date=trade_date,
            fees=float(fees),  # numeric-boundary: dto
            taxes=float(taxes),  # numeric-boundary: dto
            currency=currency,
            notes=notes,
            source_type=source_type,
            source_id=source_id,
            source_snapshot_hash=source_snapshot_hash,
            source_summary=dict(source_summary or {}),
            created_at=created_at,
        )

        existing_ids = {trade.trade_id for trade in self._load_domain_trades()}
        if dto.trade_id in existing_ids:
            raise PortfolioValidationError(f"trade_id already exists: {dto.trade_id}")

        trade = Trade.from_mapping(dto.to_dict())
        validate_trade(trade)

        # Validate the full rebuilt portfolio before appending the trade.
        rebuild_positions([*self._load_domain_trades(), trade])
        self.store.append_trade(dto.to_dict())
        logger.info("[PortfolioService] recorded trade %s", dto.trade_id)
        return dto

    def record_trades(self, trades: List[TradeDTO]) -> List[TradeDTO]:
        """Validate a batch before appending it to the append-only trade store.

        This is the write boundary used by Trade Import.  Every row is validated
        and the complete rebuilt portfolio is checked before the first append;
        callers still need an explicit confirmation before invoking this method.
        """
        if not trades:
            raise PortfolioValidationError("at least one trade is required")

        existing_domain_trades = self._load_domain_trades()
        existing_ids = {trade.trade_id for trade in self._load_trade_dtos()}
        batch_ids: set[str] = set()
        domain_trades: list[Trade] = []
        normalized: list[TradeDTO] = []
        for incoming in trades:
            dto = TradeDTO.from_dict(incoming.to_dict())
            if not dto.created_at:
                dto.created_at = datetime.now().isoformat()
            if not dto.trade_id:
                raise PortfolioValidationError("trade_id is required")
            if dto.trade_id in existing_ids or dto.trade_id in batch_ids:
                raise PortfolioValidationError(f"trade_id already exists: {dto.trade_id}")
            batch_ids.add(dto.trade_id)
            domain_trade = Trade.from_mapping(dto.to_dict())
            validate_trade(domain_trade)
            domain_trades.append(domain_trade)
            normalized.append(dto)

        # Validate the final state before writing any row.
        rebuild_positions([*existing_domain_trades, *domain_trades])
        for dto in normalized:
            self.store.append_trade(dto.to_dict())
        logger.info("[PortfolioService] recorded %s imported trades", len(normalized))
        return normalized

    def list_trades(self, portfolio_id: str = "default") -> List[TradeDTO]:
        trades = [TradeDTO.from_dict(item) for item in self.store.load_trades()]
        return [trade for trade in trades if trade.portfolio_id == portfolio_id]

    def list_positions(self, portfolio_id: str = "default") -> List[PositionDTO]:
        positions = rebuild_positions(self._load_domain_trades(portfolio_id=portfolio_id))
        return [self._position_to_dto(position) for position in positions]

    def get_position_detail(
        self,
        stock_code: str,
        portfolio_id: str = "default",
    ) -> Optional[PositionDTO]:
        for position in self.list_positions(portfolio_id=portfolio_id):
            if position.stock_code == stock_code:
                return position
        return None

    def get_portfolio(self, portfolio_id: str = "default") -> PortfolioDTO:
        # 由同一次 JSONL 讀取建立持倉與已記錄費稅摘要，避免兩個投影讀到
        # 不同版本；此路徑只讀取，沒有改寫或補算交易成本。
        raw_trades = self.store.load_trades()
        selected_trades = [
            item
            for item in raw_trades
            if str(item.get("portfolio_id", "default")) == portfolio_id
        ]
        positions = [
            self._position_to_dto(position)
            for position in rebuild_positions(
                [Trade.from_mapping(item) for item in selected_trades]
            )
        ]
        return PortfolioDTO(
            portfolio_id=portfolio_id,
            portfolio_name="Default Portfolio",
            total_positions=len(positions),
            active_positions=sum(1 for position in positions if position.is_holding),
            positions=positions,
            total_invested_amount=self._sum_money(position.invested_amount for position in positions),
            total_realized_pnl=self._sum_money(position.realized_pnl for position in positions),
            updated_at=datetime.now().isoformat(),
            recorded_trade_costs=self._summarize_recorded_trade_costs(
                selected_trades
            ),
        )

    @staticmethod
    def _summarize_recorded_trade_costs(
        trades: List[Dict[str, Any]],
    ) -> RecordedTradeCostSummaryDTO:
        fees_by_currency: Dict[str, Decimal] = {}
        taxes_by_currency: Dict[str, Decimal] = {}
        fees_recorded_count = 0
        taxes_recorded_count = 0
        fees_missing_count = 0
        taxes_missing_count = 0

        for trade in trades:
            currency = str(trade.get("currency", "TWD") or "").strip().upper()
            currency = currency or "未知幣別"
            for key, totals in (
                ("fees", fees_by_currency),
                ("taxes", taxes_by_currency),
            ):
                raw_value = trade.get(key)
                if isinstance(raw_value, bool) or raw_value is None:
                    if key == "fees":
                        fees_missing_count += 1
                    else:
                        taxes_missing_count += 1
                    continue
                try:
                    amount = Decimal(str(raw_value))
                    if not amount.is_finite():
                        raise ValueError("non-finite recorded trade cost")
                    totals[currency] = totals.get(currency, Decimal("0")) + amount
                except (DecimalException, TypeError, ValueError):
                    if key == "fees":
                        fees_missing_count += 1
                    else:
                        taxes_missing_count += 1
                    continue
                if key == "fees":
                    fees_recorded_count += 1
                else:
                    taxes_recorded_count += 1

        return RecordedTradeCostSummaryDTO(
            trade_count=len(trades),
            fees_recorded_count=fees_recorded_count,
            fees_missing_count=fees_missing_count,
            taxes_recorded_count=taxes_recorded_count,
            taxes_missing_count=taxes_missing_count,
            fees_by_currency=fees_by_currency,
            taxes_by_currency=taxes_by_currency,
        )

    def update_portfolio(self) -> PortfolioDTO:
        """Compatibility wrapper for the previous skeleton API."""
        return self.get_portfolio()

    def get_benchmark_comparison(self, benchmark_type: str = "buy_hold") -> Dict[str, Any]:
        """Return an explicit not-computable result until a period is supplied.

        The Phase 4.1 manual-trade portfolio has no canonical benchmark period,
        cash ledger, or frozen constituent set. Returning numeric zeroes here
        would look like a measured result and could be mistaken for a valid
        excess-return comparison, so the compatibility API remains
        fail-closed until the paper-portfolio benchmark path is connected.
        """
        return {
            "benchmark_type": benchmark_type,
            "status": "not_computable",
            "portfolio_return": None,
            "benchmark_return": None,
            "excess_return": None,
            "missing_inputs": (
                "comparison_period",
                "cash_and_flow_ledger",
                "frozen_benchmark_constituents",
            ),
            "note": "Phase 4.1 manual portfolio has no canonical benchmark observation yet",
            "research_only": True,
            "investment_effectiveness_claim": False,
        }

    def delete_trade(self, trade_id: str) -> bool:
        """刪除單筆交易紀錄，並重新驗證與重寫儲存"""
        trades = self.store.load_trades()
        new_trades = [t for t in trades if t.get('trade_id') != trade_id]
        if len(new_trades) == len(trades):
            return False
            
        # 領域安全性校驗：重新計算持倉，防止出現超賣或非法狀態
        try:
            domain_trades = [Trade.from_mapping(item) for item in new_trades]
            rebuild_positions(domain_trades)
        except Exception as e:
            raise PortfolioValidationError(f"刪除此交易將導致持倉數據不合法: {str(e)}")
            
        self.store.overwrite_trades(new_trades)
        logger.info("[PortfolioService] deleted trade %s and successfully rebuilt positions", trade_id)
        return True

    def clear_all_data(self) -> None:
        """重設/清空所有交易紀錄"""
        self.store.overwrite_trades([])
        logger.info("[PortfolioService] cleared all trades data")

    def _load_domain_trades(self, portfolio_id: Optional[str] = None) -> List[Trade]:
        trades = [Trade.from_mapping(item) for item in self.store.load_trades()]
        if portfolio_id is not None:
            trades = [trade for trade in trades if trade.portfolio_id == portfolio_id]
        return trades

    def _load_trade_dtos(self) -> List[TradeDTO]:
        return [TradeDTO.from_dict(item) for item in self.store.load_trades()]

    def _sum_money(self, values) -> float:
        total = sum((to_decimal(value) for value in values), to_decimal("0"))
        return float(quantize_money(total))  # numeric-boundary: dto

    def get_current_price(self, stock_code: str) -> Optional[float]:
        """獲取指定個股的最新收盤價。"""
        if getattr(self.config, 'use_sqlite', False):
            try:
                # Portfolio 的價格投影是唯讀查詢；不可因為打開持倉頁或
                # 查詢單一價格而初始化 schema、切換 WAL 或建立空 DB。
                db = ReadOnlySQLiteManager(self.config.db_file)
                df = db.execute_query(
                    "SELECT 收盤價 FROM daily_prices WHERE 證券代號 = ? ORDER BY 日期 DESC LIMIT 1;",
                    (stock_code,)
                )
                if not df.empty:
                    return float(df.iloc[0]['收盤價'])  # numeric-boundary: dto
            except FileNotFoundError:
                logger.debug("SQLite price database is unavailable: %s", self.config.db_file)
            except Exception as e:
                logger.warning("從 SQLite 獲取 %s 最新收盤價失敗: %s", stock_code, e)
        
        # 降級讀取 CSV
        try:
            daily_price_dir = self.config.daily_price_dir
            if daily_price_dir.exists():
                csv_files = sorted(list(daily_price_dir.glob("*.csv")), reverse=True)
                for file in csv_files[:3]:  # 檢查最近3天以防假日無交易
                    df = pd.read_csv(file)
                    if '證券代號' in df.columns:
                        df['證券代號'] = df['證券代號'].astype(str).str.zfill(4)
                        stock_row = df[df['證券代號'] == stock_code.zfill(4)]
                        if not stock_row.empty and '收盤價' in stock_row.columns:
                            return float(stock_row.iloc[0]['收盤價'])  # numeric-boundary: dto
        except Exception as e:
            logger.warning("從 CSV 獲取 %s 最新收盤價失敗: %s", stock_code, e)
        return None

    def get_current_price_observation(self, stock_code: str) -> PortfolioQuoteObservation:
        """讀取目前價格與精確資料日；只有官方日曆確認的最新已完成交易日才標 current。

        ``source_snapshot_hash`` 是所選正規化 SQLite 行的值指紋，或 CSV 原始位元組
        的 SHA-256。此觀測不宣稱原始公告可用時間，也不提供歷史 PIT 資格。
        """
        raw_code = str(stock_code or "").strip()
        if not raw_code:
            return self._unverified_quote("", reason="stock_code_missing")
        if re.fullmatch(r"[0-9]{1,6}", raw_code) is None:
            return self._unverified_quote(raw_code, reason="stock_code_invalid")
        code = raw_code.zfill(4)

        if getattr(self.config, "use_sqlite", False):
            try:
                db = ReadOnlySQLiteManager(self.config.db_file)
                frame = db.execute_query(
                    "SELECT 日期, 證券代號, 開盤價, 最高價, 最低價, 收盤價, 成交股數, 成交金額 "
                    "FROM daily_prices WHERE 證券代號 = ? ORDER BY 日期 DESC LIMIT 1;",
                    (code,),
                )
                if not frame.empty:
                    row = frame.iloc[0]
                    row_code = str(row.get("證券代號") or code).strip().zfill(4)
                    if row_code == code:
                        return self._make_quote_observation(
                            stock_code=code,
                            price=row.get("收盤價"),
                            data_date=self._parse_quote_date(row.get("日期")),
                            source_id="sqlite.daily_prices",
                            source_snapshot_hash=self._sqlite_quote_row_hash(code, row),
                        )
            except FileNotFoundError:
                logger.debug("SQLite price database is unavailable: %s", self.config.db_file)
            except Exception as exc:  # noqa: BLE001
                logger.warning("從 SQLite 取得 %s 行情觀測失敗: %s", code, exc)

        try:
            daily_price_dir = self.config.daily_price_dir
            if daily_price_dir.exists():
                files = sorted(daily_price_dir.glob("*.csv"), reverse=True)
                for path in files[:3]:
                    raw = path.read_bytes()
                    try:
                        frame = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
                    except UnicodeDecodeError:
                        frame = pd.read_csv(io.BytesIO(raw), encoding="cp950")
                    if "證券代號" not in frame.columns or "收盤價" not in frame.columns:
                        continue
                    frame["證券代號"] = frame["證券代號"].astype(str).str.replace(
                        r"\.0$", "", regex=True
                    ).str.zfill(4)
                    matches = frame[frame["證券代號"] == code]
                    if len(matches.index) != 1:
                        continue
                    return self._make_quote_observation(
                        stock_code=code,
                        price=matches.iloc[0]["收盤價"],
                        data_date=self._parse_quote_date(path.stem),
                        source_id="csv.daily_prices",
                        source_snapshot_hash=sha256(raw).hexdigest(),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("從 CSV 取得 %s 行情觀測失敗: %s", code, exc)
        return self._unverified_quote(code, reason="quote_row_unavailable")

    def _make_quote_observation(
        self,
        *,
        stock_code: str,
        price: Any,
        data_date: date | None,
        source_id: str,
        source_snapshot_hash: str,
    ) -> PortfolioQuoteObservation:
        parsed_price = self._quote_decimal(price)
        digest = str(source_snapshot_hash or "").strip().lower()
        if digest.startswith("sha256:"):
            digest = digest[7:]
        if parsed_price is None or data_date is None or len(digest) != 64:
            return PortfolioQuoteObservation(
                stock_code=stock_code,
                price=parsed_price,
                data_date=data_date,
                source_id=source_id,
                source_snapshot_hash=digest,
                freshness_status="unverified",
                expected_date=None,
                freshness_reason="quote_date_or_fingerprint_missing",
            )
        try:
            now = self._now_provider()
            if now.tzinfo is None or now.utcoffset() is None:
                return PortfolioQuoteObservation(
                    stock_code, parsed_price, data_date, source_id, digest,
                    "unverified", None, "portfolio_clock_timezone_missing",
                )
            assessment = self.market_session_cadence.assess(
                now.astimezone(TAIPEI).date(), data_date
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("評估 %s 行情日期 freshness 失敗: %s", stock_code, exc)
            return PortfolioQuoteObservation(
                stock_code, parsed_price, data_date, source_id, digest,
                "unverified", None, "market_session_assessment_failed",
            )
        blockers = assessment.metadata.get("blockers", ())
        return PortfolioQuoteObservation(
            stock_code=stock_code,
            price=parsed_price,
            data_date=data_date,
            source_id=source_id,
            source_snapshot_hash=digest,
            freshness_status=assessment.status,
            expected_date=assessment.expected_date,
            freshness_reason=";".join(str(item) for item in blockers),
        )

    @staticmethod
    def _parse_quote_date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return None
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _quote_decimal(value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None
        if not parsed.is_finite() or parsed <= 0:
            return None
        return parsed

    @classmethod
    def _sqlite_quote_row_hash(cls, stock_code: str, row: Any) -> str:
        def decimal_text(key: str) -> str | None:
            raw = row.get(key)
            if raw is None or str(raw).strip() == "":
                return None
            try:
                parsed = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                return None
            return format(parsed.normalize(), "f") if parsed.is_finite() else None

        data_date = cls._parse_quote_date(row.get("日期"))
        payload = {
            "schema_version": "portfolio-sqlite-daily-price-row.v1",
            "stock_code": stock_code,
            "data_date": data_date.isoformat() if data_date else str(row.get("日期") or ""),
            "open_price": decimal_text("開盤價"),
            "high_price": decimal_text("最高價"),
            "low_price": decimal_text("最低價"),
            "close_price": decimal_text("收盤價"),
            "volume": str(row.get("成交股數")) if row.get("成交股數") is not None else None,
            "turnover": decimal_text("成交金額"),
        }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return sha256(canonical).hexdigest()

    @staticmethod
    def _unverified_quote(stock_code: str, *, reason: str) -> PortfolioQuoteObservation:
        return PortfolioQuoteObservation(
            stock_code=stock_code,
            price=None,
            data_date=None,
            source_id="",
            source_snapshot_hash="",
            freshness_status="unverified",
            expected_date=None,
            freshness_reason=reason,
        )

    def _position_to_dto(self, position) -> PositionDTO:
        data = position.to_dict()
        current_price = self.get_current_price(position.stock_code)
        unrealized_pnl = None
        unrealized_pnl_pct = None
        
        if current_price is not None:
            qty_dec = to_decimal(position.quantity)
            cost_dec = to_decimal(position.average_cost)
            price_dec = to_decimal(current_price)
            
            pnl_dec = quantize_money((price_dec - cost_dec) * qty_dec)
            unrealized_pnl = float(pnl_dec)  # numeric-boundary: dto
            
            invested_dec = cost_dec * qty_dec
            if invested_dec > 0:
                pct_dec = (pnl_dec / invested_dec).quantize(Decimal("0.0001"))
                unrealized_pnl_pct = float(pct_dec)  # numeric-boundary: dto
            else:
                unrealized_pnl_pct = 0.0  # numeric-boundary: dto
                
        return PositionDTO.from_dict({
            **data,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "schema_version": "4.1"
        })

    def record_precise_trade(
        self,
        *,
        event_id: str,
        portfolio_id: str,
        stock_code: str,
        stock_name: str,
        side: str,
        quantity: int,
        price: Decimal,
        occurred_at: str,
        source_namespace: str = "manual",
        fees: Decimal = Decimal("0.00"),
        taxes: Decimal = Decimal("0.00"),
        currency: str = "TWD",
        source_id: str = "",
        source_snapshot_hash: str = "",
        thesis_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LedgerEventDTO:
        """將精確人工／隔離 paper event 寫入注入的單一 writer。"""

        if source_namespace == "backtest":
            raise PortfolioValidationError(
                "backtest results cannot be recorded as portfolio fills"
            )
        repository = self._require_ledger_repository()
        event = PortfolioLedgerEvent(
            event_id=event_id,
            portfolio_id=portfolio_id,
            source_namespace=source_namespace,
            occurred_at=occurred_at,
            stock_code=stock_code,
            stock_name=stock_name,
            side=side.lower(),
            quantity=quantity,
            price=price,
            fees=fees,
            taxes=taxes,
            currency=currency,
            source_id=source_id,
            source_snapshot_hash=source_snapshot_hash,
            thesis_id=thesis_id,
            metadata=dict(metadata or {}),
        )
        existing = repository.get(event.event_id)
        if existing is not None:
            raise PortfolioValidationError(f"ledger event already exists: {event.event_id}")
        repository.append(event)
        return _ledger_event_to_dto(event)

    def list_ledger_events(
        self,
        *,
        portfolio_id: str,
        source_namespace: str = "manual",
        as_of_date: Optional[str] = None,
    ) -> tuple[LedgerEventDTO, ...]:
        repository = self._require_ledger_repository()
        return tuple(
            _ledger_event_to_dto(event)
            for event in repository.list_events(
                portfolio_id=portfolio_id,
                source_namespace=source_namespace,
                as_of_date=as_of_date,
            )
        )

    def rebuild_from_ledger(
        self,
        *,
        portfolio_id: str,
        source_namespace: str = "manual",
        as_of_date: Optional[str] = None,
        initial_cash: Decimal = Decimal("0.00"),
        reject_negative_cash: bool = False,
    ) -> LedgerProjectionDTO:
        repository = self._require_ledger_repository()
        events = repository.list_events(
            portfolio_id=portfolio_id,
            source_namespace=source_namespace,
            as_of_date=as_of_date,
        )
        projection = rebuild_ledger_projection(
            events,
            initial_cash=initial_cash,
            reject_negative_cash=reject_negative_cash,
        )
        return _ledger_projection_to_dto(projection)

    def compensate_ledger_event(
        self,
        *,
        event_id: str,
        reverses_event_id: str,
        occurred_at: str,
        reason: str,
        source_id: str = "",
    ) -> LedgerEventDTO:
        repository = self._require_ledger_repository()
        event = repository.append_compensation(
            reverses_event_id,
            event_id=event_id,
            occurred_at=occurred_at,
            reason=reason,
            source_id=source_id,
        )
        return _ledger_event_to_dto(event)

    def build_ledger_read_model(
        self,
        *,
        portfolio_id: str,
        source_namespace: str = "manual",
        as_of_date: str,
        market_prices: Optional[Dict[str, Decimal]] = None,
        source_ledger_id: Optional[str] = None,
        initial_cash: Decimal = Decimal("0.00"),
        reject_negative_cash: bool = False,
    ) -> PortfolioLedgerReadModelDTO:
        """建立日期／品質／來源 hash read-model，供決策台只讀消費。"""

        repository = self._require_ledger_repository()
        events = repository.list_events(
            portfolio_id=portfolio_id,
            source_namespace=source_namespace,
            as_of_date=as_of_date,
        )
        missing: list[str] = []
        warnings: list[str] = []
        projection_dto: Optional[LedgerProjectionDTO] = None
        if any(not event.source_id for event in events):
            warnings.append("source_id_missing")
        if any(event.event_type == "trade" and not event.thesis_id for event in events):
            warnings.append("thesis_missing")
        if events:
            try:
                projection = rebuild_ledger_projection(
                    events,
                    initial_cash=initial_cash,
                    reject_negative_cash=reject_negative_cash,
                )
                projection_dto = _ledger_projection_to_dto(projection)
            except PortfolioValidationError as exc:
                missing.append("ledger_replay")
                warnings.append(f"ledger_replay_rejected:{type(exc).__name__}")
                projection = None
            if projection is not None and projection.positions:
                if market_prices is None:
                    missing.append("market_prices")
                else:
                    missing.extend(
                        f"market_price:{position.stock_code}"
                        for position in projection.positions
                        if position.stock_code not in market_prices
                    )
                    if projection_dto is not None:
                        projection_dto = LedgerProjectionDTO(
                            portfolio_id=projection_dto.portfolio_id,
                            source_namespace=projection_dto.source_namespace,
                            positions=tuple(
                                replace(
                                    item,
                                    current_price=market_prices.get(item.stock_code),
                                    unrealized_pnl=(
                                        ledger_unrealized_pnl(core_position, market_prices[item.stock_code])
                                        if item.stock_code in market_prices
                                        else None
                                    ),
                                )
                                for item, core_position in zip(
                                    projection_dto.positions, projection.positions
                                )
                            ),
                            cash=projection_dto.cash,
                            realized_pnl=projection_dto.realized_pnl,
                            event_ids=projection_dto.event_ids,
                            compensated_event_ids=projection_dto.compensated_event_ids,
                        )
        model = repository.read_model(
            portfolio_id=portfolio_id,
            source_namespace=source_namespace,
            as_of_date=as_of_date,
            source_ledger_id=source_ledger_id,
            missing_inputs=tuple(dict.fromkeys(missing)),
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return PortfolioLedgerReadModelDTO(
            portfolio_id=model.portfolio_id,
            source_namespace=model.source_namespace,
            as_of_date=model.as_of_date,
            quality=model.quality,
            source_ledger_id=model.source_ledger_id,
            source_ledger_hash=model.source_ledger_hash,
            event_count=model.event_count,
            missing_inputs=model.missing_inputs,
            warnings=model.warnings,
            candidate_only=model.candidate_only,
            positions=() if projection_dto is None else projection_dto.positions,
            cash=None if projection_dto is None else projection_dto.cash,
            realized_pnl=None if projection_dto is None else projection_dto.realized_pnl,
        )

    def _require_ledger_repository(self) -> PortfolioLedgerRepository:
        if self.ledger_repository is None:
            raise PortfolioValidationError(
                "precise ledger requires an explicitly injected isolated repository"
            )
        return self.ledger_repository


def _ledger_event_to_dto(event: PortfolioLedgerEvent) -> LedgerEventDTO:
    return LedgerEventDTO(
        event_id=event.event_id,
        portfolio_id=event.portfolio_id,
        source_namespace=event.source_namespace,
        occurred_at=event.occurred_at,
        stock_code=event.stock_code,
        stock_name=event.stock_name,
        side=event.side,
        quantity=event.quantity,
        price=event.price,
        fees=event.fees,
        taxes=event.taxes,
        currency=event.currency,
        source_id=event.source_id,
        source_snapshot_hash=event.source_snapshot_hash,
        thesis_id=event.thesis_id,
        event_type=event.event_type,
        reverses_event_id=event.reverses_event_id,
        reason=event.reason,
        metadata=dict(event.metadata),
        created_at=event.created_at,
    )


def _ledger_projection_to_dto(projection: LedgerProjection) -> LedgerProjectionDTO:
    return LedgerProjectionDTO(
        portfolio_id=projection.portfolio_id,
        source_namespace=projection.source_namespace,
        positions=tuple(
            LedgerPositionDTO(
                position_id=position.position_id,
                portfolio_id=position.portfolio_id,
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                quantity=position.quantity,
                average_cost=position.average_cost,
                invested_amount=position.invested_amount,
                realized_pnl=position.realized_pnl,
                opened_at=position.opened_at,
                last_trade_date=position.last_trade_date,
                source_type=position.source_type,
                source_id=position.source_id,
                source_snapshot_hash=position.source_snapshot_hash,
                thesis_id=position.thesis_id,
                trade_ids=position.trade_ids,
            )
            for position in projection.positions
        ),
        cash=projection.cash,
        realized_pnl=projection.realized_pnl,
        event_ids=projection.event_ids,
        compensated_event_ids=projection.compensated_event_ids,
    )
