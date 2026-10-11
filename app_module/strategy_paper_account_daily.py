"""策略 Paper account 的隔離 daily checkpoint writer。

此 writer 只保存 research-only 帳戶快照與 ledger lineage，不啟動排程、正式
Paper producer 或 broker。它重用既有 account binding、推薦查詢、snapshot DTO
與 PaperTradeLedgerRepository；跨資料庫狀態以 state DB pending row 和 ledger
operation marker 逐步恢復。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Callable, Iterable, Mapping, ParamSpec, TypeVar

from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_trade_ledger import (
    PaperTradeDailyAppendResult,
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import (
    PersonalPaperStorePaths,
    PersonalStoreCustody,
)
from app_module.paper_portfolio_time import TAIWAN_MARKET_TIMEZONE
from app_module.portfolio_research_valuation import PortfolioResearchValuation
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailabilityError,
    _record_newly_finalized_strategy_paper_account_availability,
    read_exact_strategy_paper_account_availability,
)
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
    canonical_sha256,
)
from data_module.twse_daily_price_publication import (
    DailyPriceScalarEvidenceReadResult,
)


DAILY_ACCOUNT_OPERATION_SCHEMA = "strategy-paper-account-daily-operation.v1"
DAILY_ACCOUNT_RECEIPT_SCHEMA = "strategy-paper-account-daily-receipt.v1"
_MAX_MONEY_CENTS = 10**17 - 1
_MAX_QUANTITY = 10**12
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PRICE_COLUMNS = frozenset({"開盤價", "收盤價"})
_VOLUME_COLUMNS = frozenset({"成交股數"})
_STATE_TABLE_COLUMNS = {
    "paper_portfolio_snapshots": (
        "snapshot_id", "portfolio_id", "decision_date", "source_result_id", "cash", "total_value"
    ),
    "paper_portfolio_positions": (
        "snapshot_id", "stock_code", "quantity", "mark_price", "market_value", "weight_bp"
    ),
    "paper_portfolio_snapshot_receipts": (
        "snapshot_id", "portfolio_id", "account_namespace", "binding_sha256", "receipt_json", "receipt_sha256"
    ),
}
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _with_fixed_decimal_context(
    function: Callable[_P, _R],
) -> Callable[_P, _R]:
    """讓完整 writer 與既有 ledger DTO 序列化使用固定 Decimal precision。"""

    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with localcontext(Context(prec=60)):
            return function(*args, **kwargs)

    return wrapped


class StrategyPaperAccountDailyError(ValueError):
    """策略帳戶 daily operation 缺少可驗證前置條件時拒絕寫入。"""


def _exact_money_cents(value: object, field: str) -> int:
    """以有界整數分核實精確分；不讀取 caller Decimal context。"""

    if (
        isinstance(value, bool)
        or not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
    ):
        raise StrategyPaperAccountDailyError(f"{field}_invalid")
    parts = value.as_tuple()
    if (
        value.adjusted() > 15
        or len(parts.digits) > 32
        or not isinstance(parts.exponent, int)
        or not -32 <= parts.exponent <= 15
    ):
        raise StrategyPaperAccountDailyError(f"{field}_exceeds_exact_money_bound")
    numerator, denominator = value.as_integer_ratio()
    cents, remainder = divmod(numerator * 100, denominator)
    if remainder or cents > _MAX_MONEY_CENTS:
        raise StrategyPaperAccountDailyError(f"{field}_must_be_exact_cents")
    return cents


def _rounded_product_cents(price: Decimal, quantity: int, field: str) -> int:
    """以整數比率對正價格乘股數做 ROUND_HALF_UP 分量化。"""

    if (
        isinstance(price, bool)
        or not isinstance(price, Decimal)
        or not price.is_finite()
        or price <= 0
        or isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or not 0 < quantity <= _MAX_QUANTITY
    ):
        raise StrategyPaperAccountDailyError(f"{field}_invalid")
    parts = price.as_tuple()
    if (
        len(parts.digits) > 32
        or not isinstance(parts.exponent, int)
        or not -18 <= parts.exponent <= 15
    ):
        raise StrategyPaperAccountDailyError(f"{field}_exceeds_exact_price_bound")
    numerator, denominator = price.as_integer_ratio()
    cents, remainder = divmod(numerator * quantity * 100, denominator)
    if remainder * 2 >= denominator:
        cents += 1
    if cents > _MAX_MONEY_CENTS:
        raise StrategyPaperAccountDailyError(f"{field}_exceeds_exact_money_bound")
    return cents


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_hash(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise StrategyPaperAccountDailyError(f"{name}_invalid")
    return value


def _aware_datetime(value: object, name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise StrategyPaperAccountDailyError(f"{name}_invalid") from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise StrategyPaperAccountDailyError(f"{name}_timezone_unknown")
    return value.astimezone(timezone.utc)


def _iso_date(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise StrategyPaperAccountDailyError(f"{name}_invalid")
    canonical = value
    if re.fullmatch(r"\d{8}", value):
        canonical = f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    try:
        parsed = date.fromisoformat(canonical)
    except ValueError as exc:
        raise StrategyPaperAccountDailyError(f"{name}_invalid") from exc
    if parsed.isoformat() != canonical:
        raise StrategyPaperAccountDailyError(f"{name}_not_canonical")
    return canonical


def _snapshot_payload(snapshot: PaperPortfolioSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "portfolio_id": snapshot.portfolio_id,
        "decision_date": snapshot.decision_date,
        "source_result_id": snapshot.source_result_id,
        "cash": str(snapshot.cash),
        "total_value": str(snapshot.total_value),
        "positions": [
            {
                "stock_code": item.stock_code,
                "quantity": item.quantity,
                "mark_price": str(item.mark_price),
                "market_value": str(item.market_value),
                "weight_bp": item.weight_bp,
            }
            for item in snapshot.positions
        ],
    }


def _validate_snapshot_exact_valuation(
    snapshot: PaperPortfolioSnapshot,
    *,
    prefix: str,
) -> None:
    """以共用估值 DTO 核實完整金額、數量、市值與向下取整 bp。"""

    try:
        PortfolioResearchValuation.from_snapshot(snapshot)
    except ValueError as exc:
        message = str(exc)
        if "cash_amount" in message:
            code = f"{prefix}_cash_precision_invalid"
        elif "total_value" in message and "positive" in message:
            code = f"{prefix}_value_not_positive"
        elif "total_value" in message:
            code = f"{prefix}_value_precision_invalid"
        elif "weight differs" in message:
            code = f"{prefix}_position_weight_mismatch"
        elif "market_value" in message:
            code = f"{prefix}_market_value_mismatch"
        elif "NAV must equal" in message:
            code = f"{prefix}_total_mismatch"
        else:
            code = f"{prefix}_valuation_invalid"
        raise StrategyPaperAccountDailyError(code) from exc


def _snapshot_sha256(snapshot: PaperPortfolioSnapshot) -> str:
    return _sha256(_snapshot_payload(snapshot))


def _snapshot_from_row(
    connection: sqlite3.Connection,
    snapshot_id: str,
) -> PaperPortfolioSnapshot | None:
    row = connection.execute(
        "SELECT snapshot_id, portfolio_id, decision_date, source_result_id, cash, total_value "
        "FROM paper_portfolio_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()
    if row is None:
        return None
    positions = connection.execute(
        "SELECT stock_code, quantity, mark_price, market_value, weight_bp "
        "FROM paper_portfolio_positions WHERE snapshot_id = ? ORDER BY stock_code",
        (snapshot_id,),
    ).fetchall()
    return PaperPortfolioSnapshot(
        snapshot_id=str(row[0]),
        portfolio_id=str(row[1]),
        decision_date=str(row[2]),
        source_result_id=str(row[3]),
        cash=Decimal(str(row[4])),
        total_value=Decimal(str(row[5])),
        positions=tuple(
            PaperPortfolioPositionSnapshot(
                stock_code=str(item[0]),
                quantity=int(item[1]),
                mark_price=Decimal(str(item[2])),
                market_value=Decimal(str(item[3])),
                weight_bp=int(item[4]),
            )
            for item in positions
        ),
    )


def _table_columns(connection: sqlite3.Connection, table: str) -> frozenset[str]:
    return frozenset(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    )


@dataclass(frozen=True, slots=True)
class DailyPriceScalarEvidence:
    """由既有 publication scalar reader 回傳的同列行情欄位與 row receipt。"""

    source_date: str
    stock_code: str
    scalar_column: str
    scalar_value: Decimal | int
    source_id: str
    parser_id: str
    first_observed_at: datetime
    written_at: datetime
    raw_response_sha256: str
    custody_receipt_sha256: str
    observation_receipt_sha256: str
    csv_sha256: str
    projection_row_sha256: str
    sqlite_projection_row_sha256: str
    projection_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        _iso_date(self.source_date, "daily_price_source_date")
        if not isinstance(self.stock_code, str) or not self.stock_code.strip():
            raise StrategyPaperAccountDailyError("daily_price_stock_code_invalid")
        if not isinstance(self.scalar_column, str):
            raise StrategyPaperAccountDailyError("daily_price_scalar_column_unsupported")
        if self.scalar_column in _PRICE_COLUMNS:
            if (
                isinstance(self.scalar_value, bool)
                or isinstance(self.scalar_value, float)
                or not isinstance(self.scalar_value, Decimal)
                or not self.scalar_value.is_finite()
                or self.scalar_value <= 0
            ):
                raise StrategyPaperAccountDailyError("daily_price_decimal_invalid")
        elif self.scalar_column in _VOLUME_COLUMNS:
            if (
                isinstance(self.scalar_value, bool)
                or isinstance(self.scalar_value, float)
                or not isinstance(self.scalar_value, int)
                or self.scalar_value <= 0
            ):
                raise StrategyPaperAccountDailyError("daily_volume_integer_invalid")
        else:
            raise StrategyPaperAccountDailyError("daily_price_scalar_column_unsupported")
        for name in ("source_id", "parser_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise StrategyPaperAccountDailyError(f"daily_price_{name}_invalid")
        for name in (
            "raw_response_sha256",
            "custody_receipt_sha256",
            "observation_receipt_sha256",
            "csv_sha256",
            "projection_row_sha256",
            "sqlite_projection_row_sha256",
        ):
            _require_hash(getattr(self, name), name)
        if self.projection_row_sha256 != self.sqlite_projection_row_sha256:
            raise StrategyPaperAccountDailyError("daily_price_row_hash_mismatch")
        if (
            not isinstance(self.projection_columns, tuple)
            or any(not isinstance(item, str) or not item for item in self.projection_columns)
            or len(set(self.projection_columns)) != len(self.projection_columns)
            or self.scalar_column not in self.projection_columns
        ):
            raise StrategyPaperAccountDailyError("daily_price_scalar_not_attested")
        observed = _aware_datetime(self.first_observed_at, "first_observed_at")
        written = _aware_datetime(self.written_at, "written_at")
        if written < observed:
            raise StrategyPaperAccountDailyError("daily_price_written_before_observed")
        object.__setattr__(self, "source_date", _iso_date(self.source_date, "daily_price_source_date"))
        object.__setattr__(self, "first_observed_at", observed)
        object.__setattr__(self, "written_at", written)

    @classmethod
    def from_reader_result(
        cls,
        result: DailyPriceScalarEvidenceReadResult,
    ) -> "DailyPriceScalarEvidence":
        if result.status != "ready" or result.row is None:
            raise StrategyPaperAccountDailyError(
                f"daily_price_evidence_{result.status}:{result.reason_code}"
            )
        row = result.row
        column = result.scalar_column
        if not isinstance(column, str) or column not in row.projection_columns:
            raise StrategyPaperAccountDailyError("daily_price_scalar_not_attested")
        value = result.scalar_value
        if column in _PRICE_COLUMNS:
            if isinstance(value, bool) or isinstance(value, float) or value is None:
                raise StrategyPaperAccountDailyError("daily_price_decimal_invalid")
            try:
                decimal_value = Decimal(str(value))
            except Exception as exc:
                raise StrategyPaperAccountDailyError("daily_price_decimal_invalid") from exc
            if not decimal_value.is_finite() or decimal_value <= 0:
                raise StrategyPaperAccountDailyError("daily_price_decimal_invalid")
            scalar_value: Decimal | int = decimal_value
        elif column in _VOLUME_COLUMNS:
            if isinstance(value, bool) or isinstance(value, float) or value is None:
                raise StrategyPaperAccountDailyError("daily_volume_integer_invalid")
            try:
                text = str(value).strip()
                if not re.fullmatch(r"\d+", text):
                    raise ValueError("volume is not an integer string")
                scalar_value = int(text)
            except (TypeError, ValueError) as exc:
                raise StrategyPaperAccountDailyError("daily_volume_integer_invalid") from exc
            if scalar_value <= 0:
                raise StrategyPaperAccountDailyError("daily_volume_integer_invalid")
        else:
            raise StrategyPaperAccountDailyError("daily_price_scalar_column_unsupported")
        if row.source_published_at is not None:
            raise StrategyPaperAccountDailyError("daily_price_publication_clock_contract_changed")
        projection_hash = _require_hash(row.projection_row_sha256, "projection_row_sha256")
        sqlite_hash = _require_hash(
            row.sqlite_projection_row_sha256, "sqlite_projection_row_sha256"
        )
        if projection_hash != sqlite_hash:
            raise StrategyPaperAccountDailyError("daily_price_row_hash_mismatch")
        for name, value_hash in (
            ("raw_response_sha256", row.raw_response_sha256),
            ("custody_receipt_sha256", row.custody_receipt_sha256),
            ("observation_receipt_sha256", row.observation_receipt_sha256),
            ("csv_sha256", row.csv_sha256),
        ):
            _require_hash(value_hash, name)
        return cls(
            source_date=_iso_date(row.source_date, "daily_price_source_date"),
            stock_code=row.stock_code,
            scalar_column=column,
            scalar_value=scalar_value,
            source_id=row.source_id,
            parser_id=row.parser_id,
            first_observed_at=_aware_datetime(row.first_observed_at, "first_observed_at"),
            written_at=_aware_datetime(row.written_at, "written_at"),
            raw_response_sha256=row.raw_response_sha256,
            custody_receipt_sha256=row.custody_receipt_sha256,
            observation_receipt_sha256=row.observation_receipt_sha256,
            csv_sha256=row.csv_sha256,
            projection_row_sha256=projection_hash,
            sqlite_projection_row_sha256=sqlite_hash,
            projection_columns=tuple(row.projection_columns),
        )

    @property
    def row_identity(self) -> tuple[object, ...]:
        return (
            self.source_date,
            self.stock_code,
            self.source_id,
            self.parser_id,
            self.first_observed_at,
            self.written_at,
            self.raw_response_sha256,
            self.custody_receipt_sha256,
            self.observation_receipt_sha256,
            self.csv_sha256,
            self.projection_row_sha256,
            self.sqlite_projection_row_sha256,
            self.projection_columns,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_date": self.source_date,
            "stock_code": self.stock_code,
            "scalar_column": self.scalar_column,
            "scalar_value": str(self.scalar_value),
            "source_id": self.source_id,
            "parser_id": self.parser_id,
            "first_observed_at": self.first_observed_at.isoformat(),
            "written_at": self.written_at.isoformat(),
            "raw_response_sha256": self.raw_response_sha256,
            "custody_receipt_sha256": self.custody_receipt_sha256,
            "observation_receipt_sha256": self.observation_receipt_sha256,
            "csv_sha256": self.csv_sha256,
            "projection_row_sha256": self.projection_row_sha256,
            "sqlite_projection_row_sha256": self.sqlite_projection_row_sha256,
            "projection_columns": list(self.projection_columns),
        }


@dataclass(frozen=True, slots=True)
class DailyQuoteEventReceipt:
    """連結行情 row hash 與來源 quote event clock 的明示 sidecar。"""

    receipt_id: str
    stock_code: str
    source_date: str
    projection_row_sha256: str
    event_at: datetime
    receipt_sha256: str

    @classmethod
    def create(
        cls,
        *,
        receipt_id: str,
        stock_code: str,
        source_date: str,
        projection_row_sha256: str,
        event_at: datetime,
    ) -> "DailyQuoteEventReceipt":
        payload = {
            "schema_version": "strategy-paper-quote-event-sidecar.v1",
            "receipt_id": receipt_id,
            "stock_code": stock_code,
            "source_date": _iso_date(source_date, "quote_source_date"),
            "projection_row_sha256": _require_hash(
                projection_row_sha256, "projection_row_sha256"
            ),
            "event_at": _aware_datetime(event_at, "quote_event_at").isoformat(),
        }
        return cls(
            receipt_id=receipt_id,
            stock_code=stock_code,
            source_date=str(payload["source_date"]),
            projection_row_sha256=str(payload["projection_row_sha256"]),
            event_at=_aware_datetime(event_at, "quote_event_at"),
            receipt_sha256=_sha256(payload),
        )

    def validate(self) -> None:
        if (
            not isinstance(self.receipt_id, str)
            or not self.receipt_id.strip()
            or not isinstance(self.stock_code, str)
            or not self.stock_code.strip()
        ):
            raise StrategyPaperAccountDailyError("quote_event_identity_invalid")
        payload = {
            "schema_version": "strategy-paper-quote-event-sidecar.v1",
            "receipt_id": self.receipt_id,
            "stock_code": self.stock_code,
            "source_date": _iso_date(self.source_date, "quote_source_date"),
            "projection_row_sha256": _require_hash(
                self.projection_row_sha256, "projection_row_sha256"
            ),
            "event_at": _aware_datetime(self.event_at, "quote_event_at").isoformat(),
        }
        if _require_hash(self.receipt_sha256, "quote_event_receipt_sha256") != _sha256(payload):
            raise StrategyPaperAccountDailyError("quote_event_receipt_hash_mismatch")

    def to_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": "strategy-paper-quote-event-sidecar.v1",
            "receipt_id": self.receipt_id,
            "stock_code": self.stock_code,
            "source_date": self.source_date,
            "projection_row_sha256": self.projection_row_sha256,
            "event_at": self.event_at.isoformat(),
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountDailyWriteResult:
    operation_id: str
    snapshot_id: str
    status: str
    receipt_sha256: str
    ledger: PaperTradeDailyAppendResult
    availability_sha256: str | None = None
    persisted_at: datetime | None = None
    available_at: datetime | None = None
    performance_eligible: bool = False
    blockers: tuple[str, ...] = (
        "governed_quote_event_clock_not_available_for_performance_qualification",
        "official_trading_calendar_and_session_gate_unverified",
        "bound_cost_policy_not_recomputed_by_shared_fill_engine",
    )


class StrategyPaperAccountDailyWriter:
    """以 exact binding 與 immutable receipts 追加策略帳戶 daily checkpoint。"""

    def __init__(
        self,
        *,
        account_service: StrategyPaperAccountService,
        recommendation_queries: object,
        personal_paths: PersonalDataPaths,
    ) -> None:
        self.account_service = account_service
        self.recommendation_queries = recommendation_queries
        self.personal_paths = personal_paths

    @_with_fixed_decimal_context
    def write_checkpoint(
        self,
        *,
        strategy_id: str,
        strategy_version_id: str,
        account_namespace: str,
        result_id: str,
        decision_cutoff: datetime,
        execution_date: str,
        mark_cutoff: datetime,
        prior_snapshot_id: str,
        snapshot: PaperPortfolioSnapshot,
        fills: Iterable[PaperTradeFill],
        transition: PaperTradeTransition | None,
        mark_prices: Iterable[DailyPriceScalarEvidence],
        execution_prices: Iterable[DailyPriceScalarEvidence],
        quote_event_receipts: Iterable[DailyQuoteEventReceipt],
    ) -> StrategyPaperAccountDailyWriteResult:
        execution_day = _iso_date(execution_date, "execution_date")
        decision_at_cutoff = _aware_datetime(decision_cutoff, "decision_cutoff")
        mark_at_cutoff = _aware_datetime(mark_cutoff, "mark_cutoff")
        selected = self.account_service.select_exact_version(
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            account_namespace=account_namespace,
        )
        if (
            selected.status is not AccountBindingStatus.READY
            or selected.binding is None
            or selected.route is None
        ):
            reason = ",".join(selected.blockers) or "strategy_account_binding_unavailable"
            raise StrategyPaperAccountDailyError(reason)
        binding = selected.binding
        route = selected.route
        if (
            binding.strategy_id != strategy_id
            or binding.strategy_version_id != strategy_version_id
            or binding.account_namespace != account_namespace
            or route.paper_account_namespace != account_namespace
            or route.identity.key != binding.portfolio_id
        ):
            raise StrategyPaperAccountDailyError("strategy_account_exact_binding_mismatch")
        policy_initial = Decimal(binding.initial_capital)
        if policy_initial != Decimal("500000") or binding.max_positions != 8:
            raise StrategyPaperAccountDailyError("strategy_account_policy_identity_mismatch")
        if execution_day < binding.start_date:
            raise StrategyPaperAccountDailyError("strategy_account_execution_before_start_date")

        read_model = self.recommendation_queries.get(result_id)  # type: ignore[attr-defined]
        source = self._validate_saved_execution(
            read_model,
            result_id=result_id,
            binding=binding,
            decision_cutoff=decision_at_cutoff,
        )
        fills_tuple = tuple(fills)
        mark_tuple = tuple(mark_prices)
        execution_tuple = tuple(execution_prices)
        quote_tuple = tuple(quote_event_receipts)
        store_paths = PersonalPaperStorePaths.from_route(
            route, portfolio_id=binding.portfolio_id
        )
        custody = PersonalStoreCustody(route, self.personal_paths)
        self._require_existing_stores(custody, store_paths)
        self._verify_state_schema(custody, store_paths.state_db)

        state_repository = PaperPortfolioSnapshotRepository(
            store_paths.state_db,
            route=route,
            portfolio_id=binding.portfolio_id,
            personal_paths=self.personal_paths,
        )
        prior = state_repository.get(prior_snapshot_id)
        if prior is None or prior.portfolio_id != binding.portfolio_id:
            raise StrategyPaperAccountDailyError("strategy_account_prior_snapshot_unknown")
        prior_receipt_sha256 = self._validate_prior_receipt(
            custody=custody,
            state_path=store_paths.state_db,
            repository=state_repository,
            prior=prior,
            binding=binding,
            decision_cutoff=decision_at_cutoff,
        )
        if snapshot.decision_date <= prior.decision_date:
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_date_not_after_prior")
        if execution_day <= prior.decision_date:
            raise StrategyPaperAccountDailyError("strategy_account_execution_not_after_prior")
        self._validate_checkpoint_values(
            binding=binding,
            execution_date=execution_day,
            result_id=result_id,
            prior_snapshot_id=prior_snapshot_id,
            prior=prior,
            snapshot=snapshot,
            fills=fills_tuple,
            transition=transition,
            mark_cutoff=mark_at_cutoff,
            mark_prices=mark_tuple,
            execution_prices=execution_tuple,
            quote_event_receipts=quote_tuple,
            decision_cutoff=decision_at_cutoff,
        )
        self._ensure_daily_state_schema(custody, store_paths.state_db)
        prior_sha256 = _snapshot_sha256(prior)
        operation_id = self._operation_id(
            binding=binding,
            prior_snapshot_id=prior_snapshot_id,
            prior_sha256=prior_sha256,
            result_id=result_id,
            execution_date=execution_day,
            snapshot_date=snapshot.decision_date,
        )

        ledger_reader = PaperTradeLedgerRepository(
            store_paths.cost_ledger_db,
            route=route,
            personal_paths=self.personal_paths,
            portfolio_id=binding.portfolio_id,
            read_only=True,
        )
        try:
            ledger_reader.schema_readback()
            current_ledger_hash = ledger_reader.rowset_hash()
        except (ValueError, sqlite3.Error) as exc:
            raise StrategyPaperAccountDailyError(
                f"strategy_account_ledger_schema_unknown:{type(exc).__name__}"
            ) from exc
        ledger_writer = PaperTradeLedgerRepository(
            store_paths.cost_ledger_db,
            route=route,
            personal_paths=self.personal_paths,
            portfolio_id=binding.portfolio_id,
        )
        ledger_writer.daily_operation_schema_readback()

        payload_without_ledger = self._operation_payload(
            operation_id=operation_id,
            binding=binding,
            prior=prior,
            prior_sha256=prior_sha256,
            prior_receipt_sha256=prior_receipt_sha256,
            snapshot=snapshot,
            result_id=result_id,
            source=source,
            decision_cutoff=decision_at_cutoff,
            execution_date=execution_day,
            mark_cutoff=mark_at_cutoff,
            fills=fills_tuple,
            transition=transition,
            mark_prices=mark_tuple,
            execution_prices=execution_tuple,
            quote_event_receipts=quote_tuple,
        )
        existing = self._read_operation(custody, store_paths.state_db, operation_id)
        expected_ledger_hash = (
            current_ledger_hash
            if existing is None
            else str(existing["expected_ledger_rowset_hash"])
        )
        operation_payload = {
            **payload_without_ledger,
            "expected_ledger_rowset_hash": expected_ledger_hash,
        }
        operation_sha256 = _sha256(operation_payload)
        self._prepare_operation(
            custody=custody,
            state_path=store_paths.state_db,
            operation_id=operation_id,
            operation_payload=operation_payload,
            operation_sha256=operation_sha256,
            binding=binding,
            prior=prior,
            prior_sha256=prior_sha256,
            snapshot=snapshot,
            expected_ledger_hash=expected_ledger_hash,
            existing=existing,
        )

        try:
            ledger_result = ledger_writer.append_daily_operation(
                operation_id=operation_id,
                portfolio_id=binding.portfolio_id,
                event_date=execution_day,
                expected_rowset_hash=expected_ledger_hash,
                fills=fills_tuple,
                transition=transition,
            )
        except ValueError as exc:
            raise StrategyPaperAccountDailyError(
                f"strategy_account_daily_ledger_blocked:{exc}"
            ) from exc
        self._record_ledger_commit(
            custody=custody,
            state_path=store_paths.state_db,
            operation_id=operation_id,
            operation_sha256=operation_sha256,
            ledger_result=ledger_result,
        )

        saved_snapshot = state_repository.get(snapshot.snapshot_id)
        if saved_snapshot is None:
            try:
                state_repository.append(snapshot)
            except ValueError:
                saved_snapshot = state_repository.get(snapshot.snapshot_id)
                if saved_snapshot != snapshot:
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_snapshot_append_conflict"
                    )
        else:
            if saved_snapshot != snapshot:
                raise StrategyPaperAccountDailyError(
                    "strategy_account_snapshot_readback_mismatch"
                )

        verified_ledger_result = ledger_writer.append_daily_operation(
            operation_id=operation_id,
            portfolio_id=binding.portfolio_id,
            event_date=execution_day,
            expected_rowset_hash=expected_ledger_hash,
            fills=fills_tuple,
            transition=transition,
        )
        if (
            verified_ledger_result.rowset_hash_after != ledger_result.rowset_hash_after
            or verified_ledger_result.operation_sha256 != ledger_result.operation_sha256
            or verified_ledger_result.ordered_fill_ids != ledger_result.ordered_fill_ids
        ):
            raise StrategyPaperAccountDailyError("strategy_account_daily_ledger_readback_mismatch")

        receipt_payload = self._daily_receipt_payload(
            operation_payload=operation_payload,
            operation_sha256=operation_sha256,
            ledger_result=ledger_result,
            prior_receipt_sha256=prior_receipt_sha256,
        )
        receipt_sha256 = _sha256(receipt_payload)
        self._finalize_operation(
            custody=custody,
            state_path=store_paths.state_db,
            operation_id=operation_id,
            operation_sha256=operation_sha256,
            prior=prior,
            prior_sha256=prior_sha256,
            snapshot=snapshot,
            receipt_payload=receipt_payload,
            receipt_sha256=receipt_sha256,
            ledger_result=ledger_result,
            binding=binding,
        )
        try:
            availability, _ = _record_newly_finalized_strategy_paper_account_availability(
                custody,
                store_paths.state_db,
                operation_id=operation_id,
                snapshot_id=snapshot.snapshot_id,
                portfolio_id=binding.portfolio_id,
                account_namespace=binding.account_namespace,
                binding_sha256=binding.binding_sha256,
                snapshot_sha256=_snapshot_sha256(snapshot),
                base_receipt_sha256=receipt_sha256,
            )
        except StrategyPaperAccountAvailabilityError as exc:
            raise StrategyPaperAccountDailyError(
                f"strategy_account_daily_availability_blocked:{exc}"
            ) from exc
        return StrategyPaperAccountDailyWriteResult(
            operation_id=operation_id,
            snapshot_id=snapshot.snapshot_id,
            status=ledger_result.status,
            receipt_sha256=receipt_sha256,
            ledger=ledger_result,
            availability_sha256=availability.receipt_sha256,
            persisted_at=availability.persisted_at,
            available_at=availability.available_at,
        )

    @staticmethod
    def _validate_saved_execution(
        read_model: object,
        *,
        result_id: str,
        binding: StrategyPaperAccountBinding,
        decision_cutoff: datetime,
    ) -> dict[str, object]:
        if read_model is None:
            raise StrategyPaperAccountDailyError("strategy_account_saved_execution_missing")
        if getattr(read_model, "integrity_basis", None) != "canonical_payload_and_index_verified":
            raise StrategyPaperAccountDailyError("strategy_account_execution_not_canonical")
        execution = getattr(read_model, "execution", None)
        if execution is None or getattr(execution, "result_id", None) != result_id:
            raise StrategyPaperAccountDailyError("strategy_account_execution_identity_mismatch")
        if getattr(read_model, "result_id", None) != result_id:
            raise StrategyPaperAccountDailyError("strategy_account_execution_identity_mismatch")
        if getattr(getattr(execution, "status", None), "value", None) != "completed":
            raise StrategyPaperAccountDailyError("strategy_account_execution_not_completed")
        context = getattr(execution, "context", None)
        strategy_identity = getattr(context, "strategy_identity", None)
        if (
            strategy_identity is None
            or getattr(strategy_identity, "strategy_version_id", None)
            != binding.strategy_version_id
        ):
            raise StrategyPaperAccountDailyError("strategy_account_execution_version_mismatch")
        config_spec_text = getattr(strategy_identity, "strategy_config_spec_json", None)
        if not isinstance(config_spec_text, str) or not config_spec_text.strip():
            raise StrategyPaperAccountDailyError(
                "strategy_account_execution_config_spec_missing"
            )
        try:
            config_spec = json.loads(config_spec_text)
        except json.JSONDecodeError as exc:
            raise StrategyPaperAccountDailyError(
                "strategy_account_execution_config_spec_missing"
            ) from exc
        if (
            not isinstance(config_spec, dict)
            or not isinstance(config_spec.get("config"), dict)
            or canonical_sha256(config_spec["config"]) != binding.config_sha256
        ):
            raise StrategyPaperAccountDailyError(
                "strategy_account_execution_config_binding_mismatch"
            )
        config_spec_hash = canonical_sha256(config_spec)
        config_hash = _require_hash(
            getattr(strategy_identity, "strategy_config_hash", None),
            "strategy_config_hash",
        )
        config_id = getattr(strategy_identity, "strategy_config_id", None)
        if (
            config_hash != config_spec_hash
            or config_id != "recommendation-strategy-config-v1:" + config_spec_hash.removeprefix("sha256:")
        ):
            raise StrategyPaperAccountDailyError(
                "strategy_account_execution_config_identity_mismatch"
            )
        decision_times = {
            "decision_at": getattr(context, "decision_at", None),
            "created_at": getattr(context, "created_at", None),
            "available_at": getattr(context, "available_at", None),
            "persisted_at": getattr(read_model, "persisted_at", None),
        }
        for name, value in decision_times.items():
            timestamp = _aware_datetime(value, f"execution_{name}")
            if timestamp > decision_cutoff:
                raise StrategyPaperAccountDailyError(
                    f"strategy_account_execution_after_decision_cutoff:{name}"
                )
        raw_hash = _require_hash(
            getattr(read_model, "raw_artifact_sha256", None), "raw_artifact_sha256"
        )
        payload_hash = _require_hash(
            getattr(read_model, "payload_hash", None), "payload_hash"
        )
        return {
            "result_id": result_id,
            "raw_artifact_sha256": raw_hash,
            "payload_hash": payload_hash,
            "artifact_location": str(getattr(read_model, "artifact_location", "")),
            "decision_at": _aware_datetime(decision_times["decision_at"], "decision_at").isoformat(),
            "created_at": _aware_datetime(decision_times["created_at"], "created_at").isoformat(),
            "available_at": _aware_datetime(decision_times["available_at"], "available_at").isoformat(),
            "persisted_at": _aware_datetime(decision_times["persisted_at"], "persisted_at").isoformat(),
            "strategy_version_id": binding.strategy_version_id,
            "strategy_config_hash": config_hash,
            "strategy_config_id": config_id,
            "strategy_config_content_sha256": canonical_sha256(config_spec["config"]),
        }

    @staticmethod
    def _validate_checkpoint_values(
        *,
        binding: StrategyPaperAccountBinding,
        execution_date: str,
        result_id: str,
        prior_snapshot_id: str,
        prior: PaperPortfolioSnapshot,
        snapshot: PaperPortfolioSnapshot,
        fills: tuple[PaperTradeFill, ...],
        transition: PaperTradeTransition | None,
        mark_cutoff: datetime,
        mark_prices: tuple[DailyPriceScalarEvidence, ...],
        execution_prices: tuple[DailyPriceScalarEvidence, ...],
        quote_event_receipts: tuple[DailyQuoteEventReceipt, ...],
        decision_cutoff: datetime,
    ) -> None:
        if any(not isinstance(item, PaperTradeFill) for item in fills):
            raise StrategyPaperAccountDailyError("strategy_account_fill_type_invalid")
        if transition is not None and not isinstance(transition, PaperTradeTransition):
            raise StrategyPaperAccountDailyError("strategy_account_transition_type_invalid")
        if any(not isinstance(item, DailyPriceScalarEvidence) for item in (*mark_prices, *execution_prices)):
            raise StrategyPaperAccountDailyError("strategy_account_price_evidence_type_invalid")
        if any(not isinstance(item, DailyQuoteEventReceipt) for item in quote_event_receipts):
            raise StrategyPaperAccountDailyError("strategy_account_quote_receipt_type_invalid")
        if mark_cutoff < decision_cutoff:
            raise StrategyPaperAccountDailyError("strategy_account_mark_cutoff_before_decision")
        _validate_snapshot_exact_valuation(prior, prefix="strategy_account_prior_snapshot")
        _validate_snapshot_exact_valuation(snapshot, prefix="strategy_account_snapshot")
        if snapshot.portfolio_id != binding.portfolio_id:
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_portfolio_mismatch")
        if snapshot.source_result_id != result_id:
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_result_mismatch")
        if snapshot.snapshot_id != (
            f"{binding.portfolio_id}-{snapshot.decision_date.replace('-', '')}"
        ):
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_id_not_deterministic")
        if _iso_date(snapshot.decision_date, "snapshot_decision_date") <= execution_date:
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_not_after_execution")
        if not prior_snapshot_id.strip():
            raise StrategyPaperAccountDailyError("strategy_account_prior_snapshot_unknown")
        if any(item.quantity <= 0 for item in snapshot.positions):
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_zero_position")
        if len({item.stock_code for item in snapshot.positions}) != len(snapshot.positions):
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_positions_duplicate")
        if tuple(item.stock_code for item in snapshot.positions) != tuple(
            sorted(item.stock_code for item in snapshot.positions)
        ):
            raise StrategyPaperAccountDailyError("strategy_account_snapshot_positions_not_ordered")
        if len(snapshot.positions) > binding.max_positions:
            raise StrategyPaperAccountDailyError("strategy_account_max_positions_exceeded")
        if any(item.event_date != execution_date for item in fills):
            raise StrategyPaperAccountDailyError("strategy_account_fill_event_date_mismatch")
        if any(item.portfolio_id != binding.portfolio_id for item in fills):
            raise StrategyPaperAccountDailyError("strategy_account_fill_portfolio_mismatch")
        if len({item.fill_id for item in fills}) != len(fills):
            raise StrategyPaperAccountDailyError("strategy_account_fill_identity_duplicate")
        if len({item.source_event_id for item in fills}) != len(fills):
            raise StrategyPaperAccountDailyError("strategy_account_fill_source_event_duplicate")
        if transition is None and fills:
            raise StrategyPaperAccountDailyError("strategy_account_transition_missing")
        if transition is not None:
            if transition.portfolio_id != binding.portfolio_id:
                raise StrategyPaperAccountDailyError("strategy_account_transition_portfolio_mismatch")
            if transition.event_date != execution_date:
                raise StrategyPaperAccountDailyError("strategy_account_transition_date_mismatch")
            if transition.fill_ids != tuple(item.fill_id for item in fills):
                raise StrategyPaperAccountDailyError("strategy_account_transition_order_mismatch")
        if not fills and transition is not None:
            raise StrategyPaperAccountDailyError("strategy_account_zero_fill_transition_invalid")

        marks = StrategyPaperAccountDailyWriter._index_price_scalars(
            mark_prices, required_column="收盤價"
        )
        expected_symbols = {item.stock_code for item in snapshot.positions}
        if set(marks) != expected_symbols:
            raise StrategyPaperAccountDailyError("strategy_account_mark_evidence_set_mismatch")
        for position in snapshot.positions:
            evidence = marks[position.stock_code]
            if evidence.source_date != execution_date:
                raise StrategyPaperAccountDailyError(
                    "strategy_account_mark_price_not_execution_day_close"
                )
            if evidence.first_observed_at > mark_cutoff or evidence.written_at > mark_cutoff:
                raise StrategyPaperAccountDailyError("strategy_account_mark_after_cutoff")
            if evidence.scalar_value != position.mark_price:
                raise StrategyPaperAccountDailyError("strategy_account_mark_value_mismatch")

        if fills:
            if not quote_event_receipts:
                raise StrategyPaperAccountDailyError("strategy_account_quote_receipt_missing")
            execution_map = StrategyPaperAccountDailyWriter._index_price_scalars(
                execution_prices, required_column="開盤價"
            )
            volume_map = StrategyPaperAccountDailyWriter._index_price_scalars(
                execution_prices, required_column="成交股數"
            )
            quote_map: dict[str, DailyQuoteEventReceipt] = {}
            for receipt in quote_event_receipts:
                receipt.validate()
                if receipt.stock_code in quote_map:
                    raise StrategyPaperAccountDailyError("strategy_account_duplicate_quote_receipt")
                quote_map[receipt.stock_code] = receipt
            if transition is None:
                raise StrategyPaperAccountDailyError("strategy_account_transition_missing")
            common_symbols = set(transition.common_prices)
            if set(execution_map) != common_symbols or set(volume_map) != common_symbols:
                raise StrategyPaperAccountDailyError("strategy_account_execution_evidence_set_mismatch")
            if set(quote_map) != common_symbols:
                raise StrategyPaperAccountDailyError("strategy_account_quote_receipt_set_mismatch")
            for symbol, price in transition.common_prices.items():
                price_evidence = execution_map[symbol]
                volume_evidence = volume_map[symbol]
                receipt = quote_map[symbol]
                if price_evidence.row_identity != volume_evidence.row_identity:
                    raise StrategyPaperAccountDailyError("strategy_account_execution_scalars_not_same_row")
                if price_evidence.source_date != execution_date:
                    raise StrategyPaperAccountDailyError("strategy_account_execution_price_date_mismatch")
                if price_evidence.scalar_value != price:
                    raise StrategyPaperAccountDailyError("strategy_account_execution_price_mismatch")
                if (
                    receipt.stock_code != symbol
                    or receipt.source_date != execution_date
                    or receipt.projection_row_sha256 != price_evidence.sqlite_projection_row_sha256
                ):
                    raise StrategyPaperAccountDailyError("strategy_account_quote_receipt_row_mismatch")
                if (
                    receipt.event_at.astimezone(TAIWAN_MARKET_TIMEZONE).date().isoformat()
                    != execution_date
                ):
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_quote_event_taipei_date_mismatch"
                    )
                if receipt.event_at <= decision_cutoff:
                    raise StrategyPaperAccountDailyError("strategy_account_quote_event_before_intent")
                if not (
                    receipt.event_at
                    <= price_evidence.first_observed_at
                    <= price_evidence.written_at
                    <= mark_cutoff
                ):
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_execution_price_clock_invalid"
                    )
                if not (
                    receipt.event_at
                    <= volume_evidence.first_observed_at
                    <= volume_evidence.written_at
                    <= mark_cutoff
                ):
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_execution_volume_clock_invalid"
                    )
                if volume_evidence.scalar_value <= 0:
                    raise StrategyPaperAccountDailyError("strategy_account_quote_volume_invalid")
            for fill in fills:
                if fill.stock_code not in execution_map:
                    raise StrategyPaperAccountDailyError("strategy_account_fill_quote_missing")
                if fill.reference_price != execution_map[fill.stock_code].scalar_value:
                    raise StrategyPaperAccountDailyError("strategy_account_fill_reference_price_mismatch")
            StrategyPaperAccountDailyWriter._validate_fill_projection(
                prior_snapshot=prior,
                snapshot=snapshot,
                fills=fills,
                transition=transition,
            )
        else:
            if execution_prices or quote_event_receipts:
                raise StrategyPaperAccountDailyError("strategy_account_zero_fill_has_execution_quote")
            if snapshot.cash != prior.cash:
                raise StrategyPaperAccountDailyError("strategy_account_zero_fill_cash_changed")
            if {
                item.stock_code: item.quantity for item in snapshot.positions
            } != {
                item.stock_code: item.quantity for item in prior.positions
            }:
                raise StrategyPaperAccountDailyError(
                    "strategy_account_zero_fill_positions_changed"
                )

    @staticmethod
    def _index_price_scalars(
        values: tuple[DailyPriceScalarEvidence, ...],
        *,
        required_column: str,
    ) -> dict[str, DailyPriceScalarEvidence]:
        selected: dict[str, DailyPriceScalarEvidence] = {}
        for item in values:
            if item.scalar_column != required_column:
                continue
            if item.stock_code in selected:
                raise StrategyPaperAccountDailyError("strategy_account_duplicate_price_scalar")
            if item.scalar_column not in item.projection_columns:
                raise StrategyPaperAccountDailyError("strategy_account_price_scalar_unattested")
            selected[item.stock_code] = item
        return selected

    @staticmethod
    def _validate_fill_projection(
        *,
        prior_snapshot: PaperPortfolioSnapshot,
        snapshot: PaperPortfolioSnapshot,
        fills: tuple[PaperTradeFill, ...],
        transition: PaperTradeTransition,
    ) -> None:
        prior_cash_cents = _exact_money_cents(
            prior_snapshot.cash, "strategy_account_prior_snapshot_cash"
        )
        if _exact_money_cents(
            transition.pre_cash, "strategy_account_transition_pre_cash"
        ) != prior_cash_cents:
            raise StrategyPaperAccountDailyError("strategy_account_transition_pre_cash_mismatch")
        prior_positions = {
            item.stock_code: item.quantity for item in prior_snapshot.positions
        }
        if dict(transition.pre_positions) != prior_positions:
            raise StrategyPaperAccountDailyError("strategy_account_transition_pre_positions_mismatch")
        if transition.fill_ids != tuple(item.fill_id for item in fills):
            raise StrategyPaperAccountDailyError("strategy_account_transition_order_mismatch")
        common_symbols = set(transition.pre_positions) | set(transition.post_positions)
        fill_symbols = {item.stock_code for item in fills}
        if set(transition.common_prices) != common_symbols or not fill_symbols.issubset(
            transition.common_prices
        ):
            raise StrategyPaperAccountDailyError("strategy_account_transition_price_set_mismatch")
        cash_cents = prior_cash_cents
        positions = dict(transition.pre_positions)
        for fill in fills:
            quantity = fill.filled_quantity
            if quantity == 0:
                continue
            if fill.fill_price is None:
                raise StrategyPaperAccountDailyError("strategy_account_filled_price_missing")
            gross_cents = _rounded_product_cents(
                fill.fill_price,
                quantity,
                "strategy_account_fill_gross",
            )
            commission_cents = _exact_money_cents(
                fill.commission, "strategy_account_fill_commission"
            )
            tax_cents = _exact_money_cents(fill.tax, "strategy_account_fill_tax")
            settlement_cents = commission_cents + tax_cents
            if fill.side == "buy":
                cash_cents -= gross_cents + settlement_cents
                positions[fill.stock_code] = positions.get(fill.stock_code, 0) + quantity
            else:
                if quantity > positions.get(fill.stock_code, 0):
                    raise StrategyPaperAccountDailyError("strategy_account_sell_exceeds_position")
                cash_cents += gross_cents - settlement_cents
                positions[fill.stock_code] -= quantity
        positions = {symbol: qty for symbol, qty in positions.items() if qty > 0}
        projected_positions = {
            item.stock_code: item.quantity
            for item in snapshot.positions
        }
        if (
            cash_cents
            != _exact_money_cents(
                transition.post_cash, "strategy_account_transition_post_cash"
            )
            or cash_cents
            != _exact_money_cents(snapshot.cash, "strategy_account_snapshot_cash")
        ):
            raise StrategyPaperAccountDailyError("strategy_account_fill_cash_projection_mismatch")
        if positions != dict(transition.post_positions) or positions != projected_positions:
            raise StrategyPaperAccountDailyError("strategy_account_fill_position_projection_mismatch")
        pre_value_cents = prior_cash_cents + sum(
            _rounded_product_cents(
                transition.common_prices[symbol],
                quantity,
                "strategy_account_transition_pre_position_value",
            )
            for symbol, quantity in transition.pre_positions.items()
        )
        post_value_cents = cash_cents + sum(
            _rounded_product_cents(
                transition.common_prices[symbol],
                quantity,
                "strategy_account_transition_post_position_value",
            )
            for symbol, quantity in transition.post_positions.items()
        )
        if pre_value_cents != _exact_money_cents(
            transition.pre_total_value, "strategy_account_transition_pre_value"
        ):
            raise StrategyPaperAccountDailyError("strategy_account_transition_pre_value_mismatch")
        if post_value_cents != _exact_money_cents(
            transition.post_total_value, "strategy_account_transition_post_value"
        ):
            raise StrategyPaperAccountDailyError("strategy_account_transition_post_value_mismatch")
        if _exact_money_cents(
            transition.common_nav, "strategy_account_transition_common_nav"
        ) != _exact_money_cents(
            transition.pre_total_value, "strategy_account_transition_pre_value"
        ):
            raise StrategyPaperAccountDailyError("strategy_account_transition_common_nav_mismatch")

    @staticmethod
    def _operation_id(
        *,
        binding: StrategyPaperAccountBinding,
        prior_snapshot_id: str,
        prior_sha256: str,
        result_id: str,
        execution_date: str,
        snapshot_date: str,
    ) -> str:
        return "strategy-paper-daily:" + _sha256(
            {
                "binding_sha256": binding.binding_sha256,
                "prior_snapshot_id": prior_snapshot_id,
                "prior_snapshot_sha256": prior_sha256,
                "result_id": result_id,
                "execution_date": execution_date,
                "snapshot_date": snapshot_date,
            }
        ).removeprefix("sha256:")

    @staticmethod
    def _operation_payload(
        *,
        operation_id: str,
        binding: StrategyPaperAccountBinding,
        prior: PaperPortfolioSnapshot,
        prior_sha256: str,
        prior_receipt_sha256: str,
        snapshot: PaperPortfolioSnapshot,
        result_id: str,
        source: Mapping[str, object],
        decision_cutoff: datetime,
        execution_date: str,
        mark_cutoff: datetime,
        fills: tuple[PaperTradeFill, ...],
        transition: PaperTradeTransition | None,
        mark_prices: tuple[DailyPriceScalarEvidence, ...],
        execution_prices: tuple[DailyPriceScalarEvidence, ...],
        quote_event_receipts: tuple[DailyQuoteEventReceipt, ...],
    ) -> dict[str, object]:
        return {
            "schema_version": DAILY_ACCOUNT_OPERATION_SCHEMA,
            "operation_id": operation_id,
            "portfolio_id": binding.portfolio_id,
            "account_namespace": binding.account_namespace,
            "binding_sha256": binding.binding_sha256,
            "strategy_id": binding.strategy_id,
            "strategy_version_id": binding.strategy_version_id,
            "strategy_config_sha256": binding.config_sha256,
            "policy_sha256": binding.policy_sha256,
            "cost_model_sha256": binding.cost_model_sha256,
            "benchmark_sha256": binding.benchmark_sha256,
            "prior_snapshot_id": prior.snapshot_id,
            "prior_snapshot_sha256": prior_sha256,
            "prior_receipt_sha256": prior_receipt_sha256,
            "snapshot": _snapshot_payload(snapshot),
            "snapshot_sha256": _snapshot_sha256(snapshot),
            "result_id": result_id,
            "saved_execution": dict(source),
            "decision_cutoff": decision_cutoff.isoformat(),
            "execution_date": execution_date,
            "mark_cutoff": mark_cutoff.isoformat(),
            "fills": [item.to_dict() for item in fills],
            "ordered_fill_ids": [item.fill_id for item in fills],
            "transition": None if transition is None else transition.to_dict(),
            "mark_prices": [item.to_payload() for item in mark_prices],
            "execution_prices": [item.to_payload() for item in execution_prices],
            "quote_event_receipts": [item.to_payload() for item in quote_event_receipts],
            "performance_eligible": False,
            "forward_qualification": "not_established",
            "research_only": True,
            "broker_order_allowed": False,
            "auto_rebalance_allowed": False,
        }

    @staticmethod
    def _daily_receipt_payload(
        *,
        operation_payload: Mapping[str, object],
        operation_sha256: str,
        ledger_result: PaperTradeDailyAppendResult,
        prior_receipt_sha256: str,
    ) -> dict[str, object]:
        return {
            "schema_version": DAILY_ACCOUNT_RECEIPT_SCHEMA,
            "operation_id": ledger_result.operation_id,
            "operation_sha256": operation_sha256,
            "portfolio_id": operation_payload["portfolio_id"],
            "account_namespace": operation_payload["account_namespace"],
            "binding_sha256": operation_payload["binding_sha256"],
            "strategy_version_id": operation_payload["strategy_version_id"],
            "prior_snapshot_id": operation_payload["prior_snapshot_id"],
            "prior_snapshot_sha256": operation_payload["prior_snapshot_sha256"],
            "prior_receipt_sha256": prior_receipt_sha256,
            "snapshot_id": operation_payload["snapshot"]["snapshot_id"],  # type: ignore[index]
            "snapshot_sha256": operation_payload["snapshot_sha256"],
            "result_id": operation_payload["result_id"],
            "saved_execution": operation_payload["saved_execution"],
            "decision_cutoff": operation_payload["decision_cutoff"],
            "execution_date": operation_payload["execution_date"],
            "mark_cutoff": operation_payload["mark_cutoff"],
            "ordered_fill_ids": list(ledger_result.ordered_fill_ids),
            "fill_batch_sha256": _sha256(operation_payload["fills"]),
            "transition_sha256": (
                None
                if operation_payload["transition"] is None
                else _sha256(operation_payload["transition"])
            ),
            "mark_prices": operation_payload["mark_prices"],
            "execution_prices": operation_payload["execution_prices"],
            "quote_event_receipts": operation_payload["quote_event_receipts"],
            "ledger_rowset_hash_before": ledger_result.rowset_hash_before,
            "ledger_rowset_hash_after": ledger_result.rowset_hash_after,
            "ledger_operation_sha256": ledger_result.operation_sha256,
            "zero_fill": not ledger_result.ordered_fill_ids,
            "performance_eligible": False,
            "forward_qualification": "not_established",
            "research_only": True,
            "broker_order_allowed": False,
            "auto_rebalance_allowed": False,
        }

    @staticmethod
    def _require_existing_stores(
        custody: PersonalStoreCustody,
        paths: PersonalPaperStorePaths,
    ) -> None:
        for label, path in (("state", paths.state_db), ("ledger", paths.cost_ledger_db)):
            custody.sqlite_guard(path)
            if not custody.exists(path):
                raise StrategyPaperAccountDailyError(
                    f"strategy_account_{label}_database_missing"
                )

    @staticmethod
    def _verify_state_schema(custody: PersonalStoreCustody, path: Path) -> None:
        try:
            with custody.read_sqlite(path) as connection:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or int(query_only[0]) != 1:
                    raise StrategyPaperAccountDailyError("strategy_account_state_reader_not_read_only")
                for table, required in _STATE_TABLE_COLUMNS.items():
                    columns = tuple(
                        str(row[1])
                        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                    )
                    if not columns:
                        raise StrategyPaperAccountDailyError(
                            f"strategy_account_state_table_missing:{table}"
                        )
                    if columns != required:
                        raise StrategyPaperAccountDailyError(
                            f"strategy_account_state_columns_mismatch:{table}"
                        )
        except sqlite3.Error as exc:
            raise StrategyPaperAccountDailyError("strategy_account_state_schema_unknown") from exc

    @staticmethod
    def _ensure_daily_state_schema(custody: PersonalStoreCustody, path: Path) -> None:
        connection = sqlite3.connect(custody.io(path), timeout=5)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS strategy_paper_account_daily_operations (
                    operation_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    prior_snapshot_id TEXT NOT NULL UNIQUE,
                    prior_snapshot_sha256 TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL UNIQUE,
                    snapshot_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    operation_json TEXT NOT NULL,
                    operation_sha256 TEXT NOT NULL,
                    expected_ledger_rowset_hash TEXT NOT NULL,
                    ledger_after_rowset_hash TEXT,
                    ledger_operation_sha256 TEXT,
                    receipt_sha256 TEXT,
                    status TEXT NOT NULL CHECK (status IN ('PENDING', 'LEDGER_COMMITTED', 'FINALIZED'))
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS strategy_paper_account_daily_receipts (
                    snapshot_id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL UNIQUE,
                    portfolio_id TEXT NOT NULL,
                    account_namespace TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL
                )"""
            )
            expected = {
                "strategy_paper_account_daily_operations": {
                    "operation_id", "portfolio_id", "prior_snapshot_id",
                    "prior_snapshot_sha256", "snapshot_id", "snapshot_sha256",
                    "binding_sha256", "operation_json", "operation_sha256",
                    "expected_ledger_rowset_hash", "ledger_after_rowset_hash",
                    "ledger_operation_sha256", "receipt_sha256", "status",
                },
                "strategy_paper_account_daily_receipts": {
                    "snapshot_id", "operation_id", "portfolio_id", "account_namespace",
                    "binding_sha256", "receipt_json", "receipt_sha256",
                },
            }
            for table, required in expected.items():
                missing = required - set(_table_columns(connection, table))
                if missing:
                    raise StrategyPaperAccountDailyError(
                        f"strategy_account_daily_schema_columns_missing:{table}"
                    )
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StrategyPaperAccountDailyError("strategy_account_daily_schema_write_failed") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _state_connection(custody: PersonalStoreCustody, path: Path) -> sqlite3.Connection:
        custody.sqlite_guard(path)
        connection = sqlite3.connect(custody.io(path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _read_operation(
        custody: PersonalStoreCustody,
        path: Path,
        operation_id: str,
    ) -> sqlite3.Row | None:
        try:
            with custody.read_sqlite(path) as connection:
                return connection.execute(
                    "SELECT * FROM strategy_paper_account_daily_operations WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StrategyPaperAccountDailyError("strategy_account_daily_operation_read_failed") from exc

    def _prepare_operation(
        self,
        *,
        custody: PersonalStoreCustody,
        state_path: Path,
        operation_id: str,
        operation_payload: Mapping[str, object],
        operation_sha256: str,
        binding: StrategyPaperAccountBinding,
        prior: PaperPortfolioSnapshot,
        prior_sha256: str,
        snapshot: PaperPortfolioSnapshot,
        expected_ledger_hash: str,
        existing: sqlite3.Row | None,
    ) -> None:
        connection = self._state_connection(custody, state_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            persisted = connection.execute(
                "SELECT * FROM strategy_paper_account_daily_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if existing is None and persisted is not None:
                raise StrategyPaperAccountDailyError("strategy_account_daily_operation_race")
            if existing is not None and persisted is None:
                raise StrategyPaperAccountDailyError("strategy_account_daily_operation_disappeared")
            if persisted is not None:
                if (
                    persisted["operation_sha256"] != operation_sha256
                    or persisted["operation_json"] != _canonical_json(operation_payload)
                    or persisted["binding_sha256"] != binding.binding_sha256
                    or persisted["expected_ledger_rowset_hash"] != expected_ledger_hash
                ):
                    raise StrategyPaperAccountDailyError("strategy_account_daily_retry_payload_mismatch")
                status = str(persisted["status"])
                if status not in {"PENDING", "LEDGER_COMMITTED", "FINALIZED"}:
                    raise StrategyPaperAccountDailyError("strategy_account_daily_operation_status_invalid")
                if (
                    persisted["portfolio_id"] != binding.portfolio_id
                    or persisted["prior_snapshot_id"] != prior.snapshot_id
                    or persisted["prior_snapshot_sha256"] != prior_sha256
                    or persisted["snapshot_id"] != snapshot.snapshot_id
                    or persisted["snapshot_sha256"] != _snapshot_sha256(snapshot)
                ):
                    raise StrategyPaperAccountDailyError("strategy_account_daily_state_identity_mismatch")
                persisted_prior = _snapshot_from_row(connection, prior.snapshot_id)
                if (
                    persisted_prior is None
                    or _snapshot_sha256(persisted_prior) != prior_sha256
                ):
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_prior_snapshot_changed"
                    )
                latest = connection.execute(
                    "SELECT snapshot_id FROM paper_portfolio_snapshots "
                    "WHERE portfolio_id = ? ORDER BY decision_date DESC, snapshot_id DESC LIMIT 1",
                    (binding.portfolio_id,),
                ).fetchone()
                latest_id = None if latest is None else str(latest[0])
                saved_snapshot = _snapshot_from_row(connection, snapshot.snapshot_id)
                if latest_id == prior.snapshot_id:
                    if saved_snapshot is not None or status == "FINALIZED":
                        raise StrategyPaperAccountDailyError(
                            "strategy_account_daily_recovery_state_mismatch"
                        )
                elif latest_id == snapshot.snapshot_id:
                    if saved_snapshot != snapshot or status == "PENDING":
                        raise StrategyPaperAccountDailyError(
                            "strategy_account_daily_recovery_state_mismatch"
                        )
                else:
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_daily_recovery_latest_snapshot_changed"
                    )
            else:
                latest = connection.execute(
                    "SELECT snapshot_id FROM paper_portfolio_snapshots "
                    "WHERE portfolio_id = ? ORDER BY decision_date DESC, snapshot_id DESC LIMIT 1",
                    (binding.portfolio_id,),
                ).fetchone()
                if latest is None or str(latest[0]) != prior.snapshot_id:
                    raise StrategyPaperAccountDailyError("strategy_account_prior_snapshot_not_latest")
                persisted_prior = _snapshot_from_row(connection, prior.snapshot_id)
                if persisted_prior is None or _snapshot_sha256(persisted_prior) != prior_sha256:
                    raise StrategyPaperAccountDailyError("strategy_account_prior_snapshot_changed")
                connection.execute(
                    """
                    INSERT INTO strategy_paper_account_daily_operations (
                        operation_id, portfolio_id, prior_snapshot_id,
                        prior_snapshot_sha256, snapshot_id, snapshot_sha256,
                        binding_sha256, operation_json, operation_sha256,
                        expected_ledger_rowset_hash, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        operation_id,
                        binding.portfolio_id,
                        prior.snapshot_id,
                        prior_sha256,
                        snapshot.snapshot_id,
                        _snapshot_sha256(snapshot),
                        binding.binding_sha256,
                        _canonical_json(operation_payload),
                        operation_sha256,
                        expected_ledger_hash,
                    ),
                )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise StrategyPaperAccountDailyError("strategy_account_daily_prior_already_pending") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _record_ledger_commit(
        self,
        *,
        custody: PersonalStoreCustody,
        state_path: Path,
        operation_id: str,
        operation_sha256: str,
        ledger_result: PaperTradeDailyAppendResult,
    ) -> None:
        connection = self._state_connection(custody, state_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT operation_sha256, status, expected_ledger_rowset_hash, "
                "ledger_after_rowset_hash, ledger_operation_sha256 "
                "FROM strategy_paper_account_daily_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None or row["operation_sha256"] != operation_sha256:
                raise StrategyPaperAccountDailyError("strategy_account_daily_pending_operation_missing")
            if row["expected_ledger_rowset_hash"] != ledger_result.rowset_hash_before:
                raise StrategyPaperAccountDailyError("strategy_account_daily_ledger_before_hash_mismatch")
            if row["status"] == "FINALIZED":
                if (
                    row["ledger_after_rowset_hash"] != ledger_result.rowset_hash_after
                    or row["ledger_operation_sha256"] != ledger_result.operation_sha256
                ):
                    raise StrategyPaperAccountDailyError("strategy_account_daily_final_ledger_mismatch")
            elif row["status"] == "PENDING":
                connection.execute(
                    "UPDATE strategy_paper_account_daily_operations "
                    "SET status='LEDGER_COMMITTED', ledger_after_rowset_hash=?, "
                    "ledger_operation_sha256=? WHERE operation_id=? AND status='PENDING'",
                    (ledger_result.rowset_hash_after, ledger_result.operation_sha256, operation_id),
                )
            elif (
                row["status"] != "LEDGER_COMMITTED"
                or row["ledger_after_rowset_hash"] != ledger_result.rowset_hash_after
                or row["ledger_operation_sha256"] != ledger_result.operation_sha256
            ):
                raise StrategyPaperAccountDailyError("strategy_account_daily_ledger_recovery_mismatch")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _finalize_operation(
        self,
        *,
        custody: PersonalStoreCustody,
        state_path: Path,
        operation_id: str,
        operation_sha256: str,
        prior: PaperPortfolioSnapshot,
        prior_sha256: str,
        snapshot: PaperPortfolioSnapshot,
        receipt_payload: Mapping[str, object],
        receipt_sha256: str,
        ledger_result: PaperTradeDailyAppendResult,
        binding: StrategyPaperAccountBinding,
    ) -> None:
        connection = self._state_connection(custody, state_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            operation = connection.execute(
                "SELECT * FROM strategy_paper_account_daily_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if operation is None or operation["operation_sha256"] != operation_sha256:
                raise StrategyPaperAccountDailyError("strategy_account_daily_pending_operation_missing")
            if operation["status"] not in {"LEDGER_COMMITTED", "FINALIZED"}:
                raise StrategyPaperAccountDailyError("strategy_account_daily_ledger_not_committed")
            if (
                operation["expected_ledger_rowset_hash"] != ledger_result.rowset_hash_before
                or operation["ledger_after_rowset_hash"] != ledger_result.rowset_hash_after
                or operation["ledger_operation_sha256"] != ledger_result.operation_sha256
            ):
                raise StrategyPaperAccountDailyError("strategy_account_daily_ledger_marker_mismatch")
            saved_prior = _snapshot_from_row(connection, prior.snapshot_id)
            if saved_prior is None or _snapshot_sha256(saved_prior) != prior_sha256:
                raise StrategyPaperAccountDailyError("strategy_account_prior_snapshot_changed")
            saved_snapshot = _snapshot_from_row(connection, snapshot.snapshot_id)
            if saved_snapshot != snapshot:
                raise StrategyPaperAccountDailyError("strategy_account_snapshot_readback_mismatch")
            latest = connection.execute(
                "SELECT snapshot_id FROM paper_portfolio_snapshots "
                "WHERE portfolio_id = ? ORDER BY decision_date DESC, snapshot_id DESC LIMIT 1",
                (binding.portfolio_id,),
            ).fetchone()
            if latest is None or str(latest[0]) != snapshot.snapshot_id:
                raise StrategyPaperAccountDailyError("strategy_account_daily_output_not_latest")
            existing_receipt = connection.execute(
                "SELECT operation_id, portfolio_id, account_namespace, binding_sha256, "
                "receipt_json, receipt_sha256 FROM strategy_paper_account_daily_receipts "
                "WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            receipt_text = _canonical_json(receipt_payload)
            if existing_receipt is None:
                if operation["status"] == "FINALIZED":
                    raise StrategyPaperAccountDailyError(
                        "strategy_account_daily_final_receipt_missing"
                    )
                connection.execute(
                    """
                    INSERT INTO strategy_paper_account_daily_receipts (
                        snapshot_id, operation_id, portfolio_id, account_namespace,
                        binding_sha256, receipt_json, receipt_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        operation_id,
                        binding.portfolio_id,
                        binding.account_namespace,
                        binding.binding_sha256,
                        receipt_text,
                        receipt_sha256,
                    ),
                )
            elif (
                existing_receipt["operation_id"] != operation_id
                or existing_receipt["portfolio_id"] != binding.portfolio_id
                or existing_receipt["account_namespace"] != binding.account_namespace
                or existing_receipt["binding_sha256"] != binding.binding_sha256
                or existing_receipt["receipt_json"] != receipt_text
                or existing_receipt["receipt_sha256"] != receipt_sha256
            ):
                raise StrategyPaperAccountDailyError("strategy_account_daily_receipt_conflict")
            if operation["status"] != "FINALIZED":
                connection.execute(
                    "UPDATE strategy_paper_account_daily_operations SET status='FINALIZED', "
                    "receipt_sha256=? WHERE operation_id=? AND status='LEDGER_COMMITTED'",
                    (receipt_sha256, operation_id),
                )
            elif operation["receipt_sha256"] != receipt_sha256:
                raise StrategyPaperAccountDailyError("strategy_account_daily_final_receipt_mismatch")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _validate_prior_receipt(
        self,
        *,
        custody: PersonalStoreCustody,
        state_path: Path,
        repository: PaperPortfolioSnapshotRepository,
        prior: PaperPortfolioSnapshot,
        binding: StrategyPaperAccountBinding,
        decision_cutoff: datetime,
    ) -> str:
        receipt = repository.get_receipt(prior.snapshot_id)
        if receipt is not None:
            if (
                receipt.receipt_kind != "account_cash_seed"
                or receipt.account_namespace != binding.account_namespace
                or receipt.binding_sha256 != binding.binding_sha256
            ):
                raise StrategyPaperAccountDailyError("strategy_account_prior_seed_binding_mismatch")
            try:
                seed_created_at = _aware_datetime(
                    receipt.seed_created_at,
                    "strategy_account_prior_seed_created_at",
                )
            except StrategyPaperAccountDailyError as exc:
                raise StrategyPaperAccountDailyError(
                    "strategy_account_prior_seed_clock_unknown"
                ) from exc
            if seed_created_at > decision_cutoff:
                raise StrategyPaperAccountDailyError(
                    "strategy_account_prior_seed_after_decision_cutoff"
                )
            return receipt.receipt_sha256
        try:
            with custody.read_sqlite(state_path) as connection:
                row = connection.execute(
                    "SELECT receipt_json, receipt_sha256, portfolio_id, account_namespace, binding_sha256 "
                    "FROM strategy_paper_account_daily_receipts WHERE snapshot_id = ?",
                    (prior.snapshot_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StrategyPaperAccountDailyError("strategy_account_prior_daily_receipt_unknown") from exc
        if row is None:
            raise StrategyPaperAccountDailyError("strategy_account_prior_receipt_unknown")
        raw = str(row["receipt_json"])
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StrategyPaperAccountDailyError("strategy_account_prior_daily_receipt_invalid") from exc
        if (
            not isinstance(payload, dict)
            or _canonical_json(payload) != raw
            or _sha256(payload) != row["receipt_sha256"]
            or row["portfolio_id"] != binding.portfolio_id
            or row["account_namespace"] != binding.account_namespace
            or row["binding_sha256"] != binding.binding_sha256
            or payload.get("schema_version") != DAILY_ACCOUNT_RECEIPT_SCHEMA
            or payload.get("portfolio_id") != binding.portfolio_id
            or payload.get("account_namespace") != binding.account_namespace
            or payload.get("strategy_version_id") != binding.strategy_version_id
            or payload.get("snapshot_id") != prior.snapshot_id
            or payload.get("snapshot_sha256") != _snapshot_sha256(prior)
            or payload.get("binding_sha256") != binding.binding_sha256
            or payload.get("performance_eligible") is not False
            or payload.get("research_only") is not True
            or payload.get("broker_order_allowed") is not False
            or payload.get("auto_rebalance_allowed") is not False
        ):
            raise StrategyPaperAccountDailyError("strategy_account_prior_daily_receipt_mismatch")
        try:
            availability = read_exact_strategy_paper_account_availability(
                custody,
                state_path,
                operation_id=str(payload["operation_id"]),
                snapshot_id=prior.snapshot_id,
                portfolio_id=binding.portfolio_id,
                account_namespace=binding.account_namespace,
                binding_sha256=binding.binding_sha256,
                snapshot_sha256=_snapshot_sha256(prior),
                base_receipt_sha256=str(row["receipt_sha256"]),
                decision_cutoff=decision_cutoff,
            )
        except StrategyPaperAccountAvailabilityError as exc:
            raise StrategyPaperAccountDailyError(
                f"strategy_account_prior_daily_availability_unknown:{exc}"
            ) from exc
        return str(row["receipt_sha256"])


__all__ = [
    "DAILY_ACCOUNT_OPERATION_SCHEMA",
    "DAILY_ACCOUNT_RECEIPT_SCHEMA",
    "DailyPriceScalarEvidence",
    "DailyQuoteEventReceipt",
    "StrategyPaperAccountDailyError",
    "StrategyPaperAccountDailyWriteResult",
    "StrategyPaperAccountDailyWriter",
]
