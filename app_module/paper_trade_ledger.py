"""Research-only paper trade fill ledger.

This module is deliberately separate from ``PortfolioService``.  The manual
Portfolio JSONL store represents user-recorded holdings, while this ledger
represents governed paper execution evidence.  A paper event is append-only
and never authorizes a broker order or mutates the formal Portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Context, Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from app_module.personal_data_paths import PersonalDataPaths, to_internal_sqlite_uri
from app_module.personal_paper_store_paths import (
    PersonalPaperStorePaths, PersonalStoreCustody,
)
from app_module.personal_store_routes import (
    PersonalStoreMode, PersonalStoreRoute, PersonalStoreRouteError,
)
from app_module.sqlite_read_only import configure_read_only_connection


PAPER_TRADE_LEDGER_SCHEMA_VERSION = "paper-trade-ledger.v1"
PAPER_TRADE_EVENT_STATUSES = frozenset(
    {"filled", "partially_filled", "rejected", "cancelled"}
)
PAPER_TRADE_SIDES = frozenset({"buy", "sell"})
# ``source_event_id`` comes from an importing source and is unique within a
# paper portfolio.  ``fill_id`` remains the ledger-wide primary key.  Keeping
# the domain in the identity check allows two portfolios to import the same
# source-system event namespace without falsely colliding, while the Formal
# single-portfolio consumer still rejects cross-portfolio input explicitly.
PAPER_TRADE_SOURCE_IDENTITY_SCOPE = "portfolio_id:source_event_id"
MONEY_QUANTUM = Decimal("0.01")
PAPER_TRADE_TRANSITION_SCHEMA_VERSION = "paper-trade-transition.v1"
PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION = "paper-trade-daily-operation.v1"
PAPER_TRADE_LEDGER_ROWSET_SCHEMA_VERSION = "paper-trade-ledger-rowset.v1"
_PAPER_TRADE_LEDGER_ROW_COLUMNS = (
    "schema_version",
    "fill_id",
    "order_id",
    "portfolio_id",
    "event_date",
    "stock_code",
    "side",
    "requested_quantity",
    "filled_quantity",
    "reference_price",
    "fill_price",
    "commission",
    "tax",
    "slippage_cost",
    "turnover_bp",
    "execution_gap_bp",
    "status",
    "source_event_id",
    "override_reason",
    "source_type",
    "research_only",
    "broker_order_allowed",
    "auto_rebalance_allowed",
)
_PAPER_TRADE_TRANSITION_ROW_COLUMNS = (
    "schema_version",
    "transition_id",
    "batch_id",
    "portfolio_id",
    "event_date",
    "fill_ids_json",
    "pre_cash",
    "pre_total_value",
    "post_cash",
    "post_total_value",
    "common_nav",
    "common_prices_json",
    "pre_positions_json",
    "post_positions_json",
    "source_type",
    "research_only",
    "broker_order_allowed",
    "auto_rebalance_allowed",
)
PAPER_TRADE_DAILY_OPERATION_COLUMNS = frozenset(
    {
        "schema_version",
        "operation_id",
        "portfolio_id",
        "event_date",
        "expected_rowset_hash",
        "rowset_hash_after",
        "ordered_fill_ids_json",
        "fill_batch_sha256",
        "transition_id",
        "transition_sha256",
        "operation_sha256",
        "marker_sha256",
        "zero_fill",
    }
)
_PAPER_TRADE_DAILY_OPERATION_ROW_COLUMNS = (
    "schema_version",
    "operation_id",
    "portfolio_id",
    "event_date",
    "expected_rowset_hash",
    "rowset_hash_after",
    "ordered_fill_ids_json",
    "fill_batch_sha256",
    "transition_id",
    "transition_sha256",
    "operation_sha256",
    "marker_sha256",
    "zero_fill",
)
_MAX_EXACT_READ_PREFIX_ROWS = 1_000_000
_MAX_EXACT_READ_PREFIX_OPERATIONS = 100_000
_MAX_EXACT_READ_DAILY_FILLS = 2_000

PAPER_TRADE_LEDGER_COLUMNS = frozenset(
    {
        "schema_version",
        "fill_id",
        "order_id",
        "portfolio_id",
        "event_date",
        "stock_code",
        "side",
        "requested_quantity",
        "filled_quantity",
        "reference_price",
        "fill_price",
        "commission",
        "tax",
        "slippage_cost",
        "turnover_bp",
        "execution_gap_bp",
        "status",
        "source_event_id",
        "override_reason",
        "source_type",
        "research_only",
        "broker_order_allowed",
        "auto_rebalance_allowed",
    }
)
PAPER_TRADE_TRANSITION_COLUMNS = frozenset(
    {
        "schema_version",
        "transition_id",
        "batch_id",
        "portfolio_id",
        "event_date",
        "fill_ids_json",
        "pre_cash",
        "pre_total_value",
        "post_cash",
        "post_total_value",
        "common_nav",
        "common_prices_json",
        "pre_positions_json",
        "post_positions_json",
        "source_type",
        "research_only",
        "broker_order_allowed",
        "auto_rebalance_allowed",
    }
)


@dataclass(frozen=True)
class PaperTradeFill:
    """One immutable paper execution event.

    ``requested_quantity`` and ``filled_quantity`` are integer shares.  All
    monetary values are Decimal so this contract cannot silently introduce a
    binary floating-point amount into the paper cost ledger.
    """

    fill_id: str
    order_id: str
    portfolio_id: str
    event_date: str
    stock_code: str
    side: str
    requested_quantity: int
    filled_quantity: int
    reference_price: Decimal
    fill_price: Decimal | None
    commission: Decimal
    tax: Decimal
    slippage_cost: Decimal
    turnover_bp: int | None
    execution_gap_bp: int | None
    status: str
    source_event_id: str
    override_reason: str | None = None
    source_type: str = "paper_simulation"
    research_only: bool = True
    broker_order_allowed: bool = False
    auto_rebalance_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "fill_id",
            "order_id",
            "portfolio_id",
            "event_date",
            "stock_code",
            "source_event_id",
            "source_type",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        try:
            date.fromisoformat(str(self.event_date)[:10])
        except ValueError as exc:
            raise ValueError("event_date must be an ISO date") from exc
        if self.side not in PAPER_TRADE_SIDES:
            raise ValueError("side must be buy or sell")
        if self.status not in PAPER_TRADE_EVENT_STATUSES:
            raise ValueError(f"unsupported paper trade status: {self.status}")
        for field_name in ("requested_quantity", "filled_quantity"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.requested_quantity <= 0:
            raise ValueError("requested_quantity must be positive")
        if self.filled_quantity > self.requested_quantity:
            raise ValueError("filled_quantity cannot exceed requested_quantity")
        for field_name in (
            "reference_price",
            "commission",
            "tax",
            "slippage_cost",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Decimal)
                or not value.is_finite()
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a finite non-negative Decimal")
        if self.reference_price <= 0:
            raise ValueError("reference_price must be positive")
        if self.fill_price is not None and (
            isinstance(self.fill_price, bool)
            or not isinstance(self.fill_price, Decimal)
            or not self.fill_price.is_finite()
            or self.fill_price <= 0
        ):
            raise ValueError("fill_price must be a positive Decimal or None")
        if self.filled_quantity > 0 and self.fill_price is None:
            raise ValueError("filled event requires fill_price")
        if self.status == "filled" and self.filled_quantity != self.requested_quantity:
            raise ValueError("filled status requires the full requested quantity")
        if self.status == "partially_filled" and not (
            0 < self.filled_quantity < self.requested_quantity
        ):
            raise ValueError("partially_filled status requires a partial quantity")
        if self.status in {"rejected", "cancelled"} and self.filled_quantity != 0:
            raise ValueError(f"{self.status} status cannot have filled quantity")
        if self.filled_quantity > 0 and self.execution_gap_bp is None:
            raise ValueError("filled event requires execution_gap_bp")
        if self.turnover_bp is not None and (
            isinstance(self.turnover_bp, bool)
            or not isinstance(self.turnover_bp, int)
            or self.turnover_bp < 0
        ):
            raise ValueError("turnover_bp must be a non-negative integer or None")
        if self.execution_gap_bp is not None and (
            isinstance(self.execution_gap_bp, bool)
            or not isinstance(self.execution_gap_bp, int)
        ):
            raise ValueError("execution_gap_bp must be an integer or None")
        if self.override_reason is not None and not str(self.override_reason).strip():
            raise ValueError("override_reason must be non-empty when supplied")
        if self.research_only is not True:
            raise ValueError("paper trade events must remain research_only")
        if self.broker_order_allowed is not False:
            raise ValueError("paper trade events cannot authorize broker orders")
        if self.auto_rebalance_allowed is not False:
            raise ValueError("paper trade events cannot authorize auto rebalance")

    @property
    def total_cost(self) -> Decimal:
        return (self.commission + self.tax + self.slippage_cost).quantize(MONEY_QUANTUM)

    @property
    def cash_settlement_cost(self) -> Decimal:
        """回傳會改變本筆成交現金結算的費用。

        ``fill_price`` 已包含模型化 tick 滑價，因此 gross 已反映該價格差異。
        ``slippage_cost`` 保留在 ``total_cost`` 作為歸因指標，投影現金時不能
        再扣一次。本 property 不輸出至 :meth:`to_dict`，讓歷史 ledger payload
        與 hash 維持位元相容。
        """

        return (self.commission + self.tax).quantize(MONEY_QUANTUM)

    @property
    def gross_amount(self) -> Decimal:
        if self.fill_price is None:
            return Decimal("0.00")
        return (self.fill_price * self.filled_quantity).quantize(MONEY_QUANTUM)

    @property
    def cost_record_ready(self) -> bool:
        return self.turnover_bp is not None and (
            self.status in {"filled", "partially_filled"}
            or self.filled_quantity == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PAPER_TRADE_LEDGER_SCHEMA_VERSION,
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "portfolio_id": self.portfolio_id,
            "event_date": self.event_date,
            "stock_code": self.stock_code,
            "side": self.side,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "reference_price": str(self.reference_price),
            "fill_price": None if self.fill_price is None else str(self.fill_price),
            "commission": str(self.commission),
            "tax": str(self.tax),
            "slippage_cost": str(self.slippage_cost),
            "total_cost": str(self.total_cost),
            "gross_amount": str(self.gross_amount),
            "turnover_bp": self.turnover_bp,
            "execution_gap_bp": self.execution_gap_bp,
            "status": self.status,
            "source_event_id": self.source_event_id,
            "override_reason": self.override_reason,
            "source_type": self.source_type,
            "research_only": self.research_only,
            "broker_order_allowed": self.broker_order_allowed,
            "auto_rebalance_allowed": self.auto_rebalance_allowed,
        }


@dataclass(frozen=True)
class PaperTradeTransition:
    """Immutable batch boundary used to rebuild canonical portfolio turnover.

    ``turnover_bp`` on :class:`PaperTradeFill` remains a gross-notional audit
    field.  The allocation policy consumes a transition reconstructed from
    pre/post quantities and a single common NAV/price basis, so a sell and a
    buy in the same batch cannot be accidentally treated as two independent
    target rebalances.
    """

    transition_id: str
    batch_id: str
    portfolio_id: str
    event_date: str
    fill_ids: tuple[str, ...]
    pre_cash: Decimal
    pre_total_value: Decimal
    post_cash: Decimal
    post_total_value: Decimal
    common_nav: Decimal
    common_prices: Mapping[str, Decimal]
    pre_positions: Mapping[str, int]
    post_positions: Mapping[str, int]
    source_type: str = "paper_daily_execution_delayed_eod_replay_v1"
    research_only: bool = True
    broker_order_allowed: bool = False
    auto_rebalance_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "transition_id",
            "batch_id",
            "portfolio_id",
            "event_date",
            "source_type",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        try:
            parsed_date = date.fromisoformat(self.event_date)
        except ValueError as exc:
            raise ValueError("transition event_date must be an ISO date") from exc
        if parsed_date.isoformat() != self.event_date:
            raise ValueError("transition event_date must use YYYY-MM-DD")
        if not self.fill_ids:
            raise ValueError("transition fill_ids are required")
        if any(not isinstance(value, str) or not value.strip() for value in self.fill_ids):
            raise ValueError("transition fill_ids must be non-empty strings")
        if len(set(self.fill_ids)) != len(self.fill_ids):
            raise ValueError("transition fill_ids must be unique")
        for field_name in (
            "pre_cash",
            "pre_total_value",
            "post_cash",
            "post_total_value",
            "common_nav",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Decimal)
                or not value.is_finite()
                or value < Decimal("0")
            ):
                raise ValueError(f"{field_name} must be a finite non-negative Decimal")
        if self.pre_total_value <= Decimal("0"):
            raise ValueError("pre_total_value must be positive")
        if self.post_total_value <= Decimal("0"):
            raise ValueError("post_total_value must be positive")
        if self.common_nav <= Decimal("0"):
            raise ValueError("common_nav must be positive")
        _validate_transition_prices(self.common_prices)
        _validate_transition_positions(self.pre_positions, "pre_positions")
        _validate_transition_positions(self.post_positions, "post_positions")
        required_symbols = set(self.pre_positions) | set(self.post_positions)
        if not required_symbols.issubset(self.common_prices):
            raise ValueError("transition common_prices do not cover positions")
        if not self.source_type.startswith("paper_"):
            raise ValueError("transition source_type must be paper_*")
        if self.research_only is not True:
            raise ValueError("paper transitions must remain research_only")
        if self.broker_order_allowed is not False:
            raise ValueError("paper transitions cannot authorize broker orders")
        if self.auto_rebalance_allowed is not False:
            raise ValueError("paper transitions cannot authorize auto rebalance")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PAPER_TRADE_TRANSITION_SCHEMA_VERSION,
            "transition_id": self.transition_id,
            "batch_id": self.batch_id,
            "portfolio_id": self.portfolio_id,
            "event_date": self.event_date,
            "fill_ids": list(self.fill_ids),
            "pre_cash": str(self.pre_cash),
            "pre_total_value": str(self.pre_total_value),
            "post_cash": str(self.post_cash),
            "post_total_value": str(self.post_total_value),
            "common_nav": str(self.common_nav),
            "common_prices": {
                symbol: str(price)
                for symbol, price in sorted(self.common_prices.items())
            },
            "pre_positions": dict(sorted(self.pre_positions.items())),
            "post_positions": dict(sorted(self.post_positions.items())),
            "source_type": self.source_type,
            "research_only": self.research_only,
            "broker_order_allowed": self.broker_order_allowed,
            "auto_rebalance_allowed": self.auto_rebalance_allowed,
        }


@dataclass(frozen=True, slots=True)
class PaperTradeDailyOperationMarker:
    """一個精確 daily append operation 的 ledger 內持久標記。"""

    operation_id: str
    portfolio_id: str
    event_date: str
    expected_rowset_hash: str
    rowset_hash_after: str
    ordered_fill_ids: tuple[str, ...]
    fill_batch_sha256: str
    transition_id: str | None
    transition_sha256: str | None
    operation_sha256: str
    marker_sha256: str
    zero_fill: bool


@dataclass(frozen=True, slots=True)
class PaperTradeDailyAppendResult:
    """CAS append 或精確冪等恢復的結果。"""

    operation_id: str
    status: str
    rowset_hash_before: str
    rowset_hash_after: str
    ordered_fill_ids: tuple[str, ...]
    operation_sha256: str


@dataclass(frozen=True, slots=True)
class PaperTradeDailyOperationRead:
    """同一唯讀 SQLite snapshot 驗證後的 daily operation。"""

    marker: PaperTradeDailyOperationMarker
    ordered_fills: tuple[PaperTradeFill, ...]
    transition: PaperTradeTransition | None
    rowset_hash_before: str
    rowset_hash_after: str


def _validate_transition_prices(value: Mapping[str, Decimal]) -> None:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("transition common_prices are required")
    for symbol, price in value.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("transition common_prices symbols are invalid")
        if (
            isinstance(price, bool)
            or not isinstance(price, Decimal)
            or not price.is_finite()
            or price <= Decimal("0")
        ):
            raise ValueError("transition common_prices must be positive Decimals")


def _validate_transition_positions(
    value: Mapping[str, int],
    field_name: str,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    for symbol, quantity in value.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"{field_name} symbols are invalid")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 0
        ):
            raise ValueError(f"{field_name} quantities must be non-negative integers")


def _canonical_transition_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_transition_json(value).encode("utf-8", errors="strict")
    ).hexdigest()


def _require_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")
    return value


def _require_table_columns(
    connection: sqlite3.Connection,
    table: str,
    required: frozenset[str],
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }
    if not columns:
        raise ValueError(f"paper ledger schema table is missing:{table}")
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            f"paper ledger schema columns are missing:{table}:" + ",".join(missing)
        )


def _ledger_rowset_hash(connection: sqlite3.Connection) -> str:
    """計算共享 fills/transitions rowset hash，不含 operation markers。

    marker table 保存交易身分，不應改變 rowset 前像或後像。既有 fills 與
    transitions 依穩定主鍵排序，並以 SQLite 實際儲存值計算。
    """

    for table, expected in (
        ("paper_trade_ledger", _PAPER_TRADE_LEDGER_ROW_COLUMNS),
        ("paper_trade_transitions", _PAPER_TRADE_TRANSITION_ROW_COLUMNS),
    ):
        actual = tuple(
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        )
        if actual != expected:
            raise ValueError(f"paper ledger rowset schema columns mismatch:{table}")
    fills = [
        list(row)
        for row in connection.execute(
            "SELECT " + ", ".join(_PAPER_TRADE_LEDGER_ROW_COLUMNS)
            + " FROM paper_trade_ledger ORDER BY fill_id"
        ).fetchall()
    ]
    transitions = [
        list(row)
        for row in connection.execute(
            "SELECT " + ", ".join(_PAPER_TRADE_TRANSITION_ROW_COLUMNS)
            + " FROM paper_trade_transitions ORDER BY transition_id"
        ).fetchall()
    ]
    return _canonical_sha256(
        {
            "schema_version": PAPER_TRADE_LEDGER_ROWSET_SCHEMA_VERSION,
            "fills": fills,
            "transitions": transitions,
        }
    )


def _require_exact_table_columns(
    connection: sqlite3.Connection,
    table: str,
    expected: tuple[str, ...],
) -> None:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    actual_columns = tuple(str(row[1]) for row in rows)
    if actual_columns != expected:
        raise ValueError(f"paper ledger exact-read schema mismatch:{table}")

    if table == "paper_trade_ledger":
        integer_columns = frozenset(
            {
                "requested_quantity",
                "filled_quantity",
                "turnover_bp",
                "execution_gap_bp",
                "research_only",
                "broker_order_allowed",
                "auto_rebalance_allowed",
            }
        )
        nullable_columns = frozenset(
            {"fill_price", "turnover_bp", "execution_gap_bp", "override_reason"}
        )
        primary_key = "fill_id"
    elif table == "paper_trade_transitions":
        integer_columns = frozenset(
            {"research_only", "broker_order_allowed", "auto_rebalance_allowed"}
        )
        nullable_columns = frozenset()
        primary_key = "transition_id"
    elif table == "paper_trade_daily_operations":
        integer_columns = frozenset({"zero_fill"})
        nullable_columns = frozenset({"transition_id", "transition_sha256"})
        primary_key = "operation_id"
    else:
        raise ValueError(f"paper ledger exact-read schema is unknown:{table}")

    expected_shape = tuple(
        (
            column,
            "INTEGER" if column in integer_columns else "TEXT",
            int(column not in nullable_columns and column != primary_key),
            int(column == primary_key),
        )
        for column in expected
    )
    actual_shape = tuple(
        (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
        for row in rows
    )
    if actual_shape != expected_shape:
        raise ValueError(f"paper ledger exact-read column definition mismatch:{table}")


def _require_canonical_event_date(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a canonical ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be a canonical ISO date")
    return value


def _require_raw_text(
    row: sqlite3.Row,
    field_name: str,
    *,
    nullable: bool = False,
) -> str | None:
    value = row[field_name]
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"paper ledger persisted text is invalid:{field_name}")
    return value


def _require_raw_integer(
    row: sqlite3.Row,
    field_name: str,
    *,
    nullable: bool = False,
    flag: bool = False,
) -> int | None:
    value = row[field_name]
    if nullable and value is None:
        return None
    if type(value) is not int:
        raise ValueError(f"paper ledger persisted integer is invalid:{field_name}")
    if flag and value not in (0, 1):
        raise ValueError(f"paper ledger persisted flag is invalid:{field_name}")
    return value


def _require_canonical_decimal_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"paper ledger persisted Decimal text is invalid:{field_name}")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"paper ledger persisted Decimal text is invalid:{field_name}"
        ) from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise ValueError(f"paper ledger persisted Decimal text is not canonical:{field_name}")
    return value


def _require_canonical_json_text(row: sqlite3.Row, field_name: str) -> object:
    raw = _require_raw_text(row, field_name)
    assert raw is not None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"paper ledger persisted JSON is invalid:{field_name}") from exc
    if _canonical_transition_json(value) != raw:
        raise ValueError(f"paper ledger persisted JSON is not canonical:{field_name}")
    return value


def _validate_raw_fill_row(row: sqlite3.Row) -> PaperTradeFill:
    if _require_raw_text(row, "schema_version") != PAPER_TRADE_LEDGER_SCHEMA_VERSION:
        raise ValueError("paper ledger persisted fill schema version is not governed")
    for field_name in (
        "fill_id",
        "order_id",
        "portfolio_id",
        "event_date",
        "stock_code",
        "side",
        "status",
        "source_event_id",
        "source_type",
    ):
        _require_raw_text(row, field_name)
    _require_canonical_event_date(row["event_date"], "paper_trade_ledger.event_date")
    for field_name in ("fill_price", "override_reason"):
        _require_raw_text(row, field_name, nullable=True)
    for field_name in (
        "requested_quantity",
        "filled_quantity",
        "turnover_bp",
        "execution_gap_bp",
    ):
        _require_raw_integer(
            row,
            field_name,
            nullable=field_name in {"turnover_bp", "execution_gap_bp"},
        )
    for field_name in (
        "research_only",
        "broker_order_allowed",
        "auto_rebalance_allowed",
    ):
        _require_raw_integer(row, field_name, flag=True)
    for field_name in ("reference_price", "commission", "tax", "slippage_cost"):
        _require_canonical_decimal_text(row[field_name], field_name)
    if row["fill_price"] is not None:
        _require_canonical_decimal_text(row["fill_price"], "fill_price")
    with localcontext(Context(prec=60)):
        return _row_to_fill(row)


def _validate_raw_transition_row(row: sqlite3.Row) -> PaperTradeTransition:
    if (
        _require_raw_text(row, "schema_version")
        != PAPER_TRADE_TRANSITION_SCHEMA_VERSION
    ):
        raise ValueError("paper ledger persisted transition schema version is not governed")
    for field_name in (
        "transition_id",
        "batch_id",
        "portfolio_id",
        "event_date",
        "source_type",
    ):
        _require_raw_text(row, field_name)
    _require_canonical_event_date(
        row["event_date"], "paper_trade_transitions.event_date"
    )
    for field_name in (
        "pre_cash",
        "pre_total_value",
        "post_cash",
        "post_total_value",
        "common_nav",
    ):
        _require_canonical_decimal_text(row[field_name], field_name)
    for field_name in (
        "research_only",
        "broker_order_allowed",
        "auto_rebalance_allowed",
    ):
        _require_raw_integer(row, field_name, flag=True)

    fill_ids = _require_canonical_json_text(row, "fill_ids_json")
    if (
        not isinstance(fill_ids, list)
        or any(not isinstance(item, str) or not item for item in fill_ids)
        or len(fill_ids) != len(set(fill_ids))
    ):
        raise ValueError("paper ledger persisted transition fill IDs are invalid")
    common_prices = _require_canonical_json_text(row, "common_prices_json")
    if not isinstance(common_prices, dict):
        raise ValueError("paper ledger persisted transition prices are invalid")
    for symbol, value in common_prices.items():
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("paper ledger persisted transition price symbol is invalid")
        _require_canonical_decimal_text(value, "common_prices_json")
    for field_name in ("pre_positions_json", "post_positions_json"):
        positions = _require_canonical_json_text(row, field_name)
        if not isinstance(positions, dict):
            raise ValueError(f"paper ledger persisted positions are invalid:{field_name}")
        for symbol, quantity in positions.items():
            if (
                not isinstance(symbol, str)
                or not symbol
                or type(quantity) is not int
                or quantity < 0
            ):
                raise ValueError(f"paper ledger persisted position is invalid:{field_name}")
    with localcontext(Context(prec=60)):
        return _row_to_transition(row)


def _validate_raw_daily_marker_row(row: sqlite3.Row) -> None:
    if (
        _require_raw_text(row, "schema_version")
        != PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION
    ):
        raise ValueError("paper daily operation schema_version is not governed")
    for field_name in (
        "operation_id",
        "portfolio_id",
        "event_date",
        "expected_rowset_hash",
        "rowset_hash_after",
        "ordered_fill_ids_json",
        "fill_batch_sha256",
        "operation_sha256",
        "marker_sha256",
    ):
        _require_raw_text(row, field_name)
    for field_name in ("transition_id", "transition_sha256"):
        _require_raw_text(row, field_name, nullable=True)
    _require_canonical_event_date(
        row["event_date"], "paper_trade_daily_operations.event_date"
    )
    _require_raw_integer(row, "zero_fill", flag=True)
    for field_name in ("operation_id", "portfolio_id"):
        value = row[field_name]
        if not value.strip():
            raise ValueError(f"paper daily operation identity is empty:{field_name}")


def _require_no_foreign_prefix_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    event_date: str,
    portfolio_id: str,
) -> None:
    row = connection.execute(
        f'SELECT portfolio_id FROM "{table}" '
        "WHERE event_date <= ? AND (portfolio_id IS NULL OR portfolio_id <> ?) "
        "LIMIT 1",
        (event_date, portfolio_id),
    ).fetchone()
    if row is not None:
        raise ValueError(f"paper exact-read foreign portfolio prefix row:{table}")


def _ledger_rowset_hash_prefix(
    connection: sqlite3.Connection,
    *,
    event_date: str,
    inclusive: bool,
) -> str:
    """串流計算既有 v1 canonical rowset 的日期 prefix，不變更 hash 格式。"""

    operator = "<=" if inclusive else "<"
    digest = hashlib.sha256()
    total_rows = 0
    for table, columns, order_column in (
        ("paper_trade_ledger", _PAPER_TRADE_LEDGER_ROW_COLUMNS, "fill_id"),
        (
            "paper_trade_transitions",
            _PAPER_TRADE_TRANSITION_ROW_COLUMNS,
            "transition_id",
        ),
    ):
        _require_exact_table_columns(connection, table, columns)

    digest.update(b'{"fills":[')
    first = True
    for table, columns, order_column in (
        ("paper_trade_ledger", _PAPER_TRADE_LEDGER_ROW_COLUMNS, "fill_id"),
        (
            "paper_trade_transitions",
            _PAPER_TRADE_TRANSITION_ROW_COLUMNS,
            "transition_id",
        ),
    ):
        if table == "paper_trade_transitions":
            digest.update(b'],"schema_version":')
            digest.update(
                _canonical_transition_json(
                    PAPER_TRADE_LEDGER_ROWSET_SCHEMA_VERSION
                ).encode("utf-8", errors="strict")
            )
            digest.update(b',"transitions":[')
            first = True
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        cursor = connection.execute(
            f'SELECT {quoted_columns} FROM "{table}" '
            f'WHERE event_date {operator} ? ORDER BY "{order_column}"',
            (event_date,),
        )
        while batch := cursor.fetchmany(256):
            for row in batch:
                total_rows += 1
                if total_rows > _MAX_EXACT_READ_PREFIX_ROWS:
                    raise ValueError("paper exact-read rowset prefix limit exceeded")
                if table == "paper_trade_ledger":
                    _validate_raw_fill_row(row)
                else:
                    _validate_raw_transition_row(row)
                _require_canonical_event_date(
                    row["event_date"], f"{table}.event_date"
                )
                if not first:
                    digest.update(b",")
                digest.update(
                    _canonical_transition_json(list(row)).encode(
                        "utf-8", errors="strict"
                    )
                )
                first = False
    digest.update(b"]}")
    return "sha256:" + digest.hexdigest()


def _daily_operation_payload(
    *,
    operation_id: str,
    portfolio_id: str,
    event_date: str,
    expected_rowset_hash: str,
    entries: tuple[PaperTradeFill, ...],
    transition: PaperTradeTransition | None,
) -> dict[str, object]:
    return {
        "schema_version": PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION,
        "operation_id": operation_id,
        "portfolio_id": portfolio_id,
        "event_date": event_date,
        "expected_rowset_hash": expected_rowset_hash,
        "ordered_fill_ids": [item.fill_id for item in entries],
        "fills": [item.to_dict() for item in entries],
        "transition": None if transition is None else transition.to_dict(),
    }


def _daily_marker_payload(marker: PaperTradeDailyOperationMarker) -> dict[str, object]:
    return {
        "schema_version": PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION,
        "operation_id": marker.operation_id,
        "portfolio_id": marker.portfolio_id,
        "event_date": marker.event_date,
        "expected_rowset_hash": marker.expected_rowset_hash,
        "rowset_hash_after": marker.rowset_hash_after,
        "ordered_fill_ids": list(marker.ordered_fill_ids),
        "fill_batch_sha256": marker.fill_batch_sha256,
        "transition_id": marker.transition_id,
        "transition_sha256": marker.transition_sha256,
        "operation_sha256": marker.operation_sha256,
        "zero_fill": marker.zero_fill,
    }


def _row_to_daily_marker(row: sqlite3.Row) -> PaperTradeDailyOperationMarker:
    _validate_raw_daily_marker_row(row)
    if row["schema_version"] != PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION:
        raise ValueError("paper daily operation schema_version is not governed")
    try:
        raw_ids = json.loads(str(row["ordered_fill_ids_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("paper daily operation fill ids are invalid JSON") from exc
    if (
        not isinstance(raw_ids, list)
        or any(not isinstance(item, str) or not item for item in raw_ids)
        or len(raw_ids) != len(set(raw_ids))
    ):
        raise ValueError("paper daily operation fill ids are invalid")
    if _canonical_transition_json(raw_ids) != str(row["ordered_fill_ids_json"]):
        raise ValueError("paper daily operation fill ids are not canonical JSON")
    if type(row["zero_fill"]) is not int or row["zero_fill"] not in (0, 1):
        raise ValueError("paper daily operation zero-fill flag is invalid")
    marker = PaperTradeDailyOperationMarker(
        operation_id=str(row["operation_id"]),
        portfolio_id=str(row["portfolio_id"]),
        event_date=str(row["event_date"]),
        expected_rowset_hash=_require_sha256(
            row["expected_rowset_hash"], "expected_rowset_hash"
        ),
        rowset_hash_after=_require_sha256(
            row["rowset_hash_after"], "rowset_hash_after"
        ),
        ordered_fill_ids=tuple(raw_ids),
        fill_batch_sha256=_require_sha256(
            row["fill_batch_sha256"], "fill_batch_sha256"
        ),
        transition_id=(None if row["transition_id"] is None else str(row["transition_id"])),
        transition_sha256=(
            None
            if row["transition_sha256"] is None
            else _require_sha256(row["transition_sha256"], "transition_sha256")
        ),
        operation_sha256=_require_sha256(row["operation_sha256"], "operation_sha256"),
        marker_sha256=_require_sha256(row["marker_sha256"], "marker_sha256"),
        zero_fill=bool(row["zero_fill"]),
    )
    if marker.zero_fill != (not marker.ordered_fill_ids):
        raise ValueError("paper daily operation zero-fill marker mismatch")
    if marker.zero_fill != (marker.transition_id is None):
        raise ValueError("paper daily operation transition identity mismatch")
    if marker.marker_sha256 != _canonical_sha256(_daily_marker_payload(marker)):
        raise ValueError("paper daily operation marker hash mismatch")
    return marker


class PaperTradeLedgerRepository:
    """Append-only SQLite writer for explicit paper fill events.

    預設 ctor 是 writer 邊界；明示 read_only 的 routed reader 不建立 schema。
    UI/readiness 仍沿既有唯讀 repository，不因查看狀態啟用 writer。
    """

    def __init__(
        self, db_path: str | Path, *,
        route: PersonalStoreRoute | None = None,
        personal_paths: PersonalDataPaths | None = None,
        portfolio_id: str | None = None,
        read_only: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self._route = route
        self._portfolio_id = portfolio_id
        self._read_only = read_only
        if route is not None:
            selected = PersonalPaperStorePaths.from_route(route, portfolio_id=portfolio_id or "")
            PersonalPaperStorePaths.require_selected(self.db_path, selected.cost_ledger_db)
            if not read_only and route.mode is PersonalStoreMode.LEGACY_READ_ONLY:
                raise PersonalStoreRouteError("legacy_read_only_writer_forbidden")
        self._custody = PersonalStoreCustody(route, personal_paths)
        self._custody.sqlite_guard(self.db_path)
        if not read_only:
            self._custody.prepare_parent(self.db_path)
            self._ensure_schema()

    def _require_identity(self, portfolio_id: str) -> None:
        if self._route is not None and portfolio_id != self._portfolio_id:
            raise PersonalStoreRouteError("paper_identity_mismatch")

    def _guard_path(self) -> Path:
        """每次 I/O 重驗精確 DB 與三個 sidecar，不以 resolve 掩蓋 alias。"""
        if self._route is not None:
            selected = PersonalPaperStorePaths.from_route(
                self._route, portfolio_id=self._portfolio_id or ""
            )
            PersonalPaperStorePaths.require_selected(self.db_path, selected.cost_ledger_db)
        return self._custody.sqlite_guard(self.db_path)

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if not read_only and (self._read_only or (
            self._route is not None and self._route.mode is PersonalStoreMode.LEGACY_READ_ONLY
        )):
            raise PersonalStoreRouteError("paper_read_only_writer_forbidden")
        canonical = self._guard_path()
        if read_only and (self._route is not None or self._read_only):
            if self._route is None:
                canonical = canonical.expanduser().absolute()
            conn = sqlite3.connect(to_internal_sqlite_uri(canonical, "ro"), uri=True)
            try:
                configure_read_only_connection(conn)
            except Exception:
                conn.close()
                raise
            return conn
        return sqlite3.connect(self._custody.io(self.db_path))

    def append(self, fill: PaperTradeFill) -> None:
        self.append_many((fill,))

    def append_many(self, fills: Iterable[PaperTradeFill]) -> None:
        entries = tuple(fills)
        if not entries:
            raise ValueError("at least one paper trade fill is required")
        self._append_entries(entries, transition=None)

    def append_batch(
        self,
        fills: Iterable[PaperTradeFill],
        transition: PaperTradeTransition,
    ) -> None:
        """Atomically append fills with their immutable batch transition."""

        entries = tuple(fills)
        if not entries:
            raise ValueError("at least one paper trade fill is required")
        if transition.portfolio_id != entries[0].portfolio_id:
            raise ValueError("paper transition portfolio does not match fills")
        if set(transition.fill_ids) != {item.fill_id for item in entries}:
            raise ValueError("paper transition fill identity does not match fills")
        if any(
            item.portfolio_id != transition.portfolio_id
            or item.event_date != transition.event_date
            for item in entries
        ):
            raise ValueError("paper transition date or portfolio does not match fills")
        self._append_entries(entries, transition=transition)

    def rowset_hash(self) -> str:
        """在固定唯讀 SQLite snapshot 中計算全部 fills 與 transitions hash。"""

        connection = self._connect(read_only=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            return _ledger_rowset_hash(connection)
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def get_daily_operation(
        self,
        operation_id: str,
        *,
        portfolio_id: str | None = None,
    ) -> PaperTradeDailyOperationMarker | None:
        """唯讀取得 operation marker；不建立 schema 或變更資料庫。"""

        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id is required")
        if portfolio_id is not None:
            self._require_identity(portfolio_id)
        connection = self._connect(read_only=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            _require_table_columns(
                connection,
                "paper_trade_daily_operations",
                PAPER_TRADE_DAILY_OPERATION_COLUMNS,
            )
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM paper_trade_daily_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                return None
            marker = _row_to_daily_marker(row)
            if portfolio_id is not None and marker.portfolio_id != portfolio_id:
                raise ValueError("paper daily operation portfolio identity mismatch")
            return marker
        finally:
            connection.close()

    def read_exact_daily_operation(
        self,
        operation_id: str,
        *,
        portfolio_id: str,
        event_date: str,
    ) -> PaperTradeDailyOperationRead:
        """在同一 route-bound BEGIN snapshot 精確讀回 daily append。"""

        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id is required")
        self._require_identity(portfolio_id)
        event_date = _require_canonical_event_date(event_date, "event_date")

        connection = self._connect(read_only=True)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            query_only = connection.execute("PRAGMA query_only").fetchone()
            if query_only is None or int(query_only[0]) != 1:
                raise ValueError("paper ledger exact read is not query-only")
            connection.execute("BEGIN")
            _require_exact_table_columns(
                connection,
                "paper_trade_daily_operations",
                _PAPER_TRADE_DAILY_OPERATION_ROW_COLUMNS,
            )
            _require_exact_table_columns(
                connection, "paper_trade_ledger", _PAPER_TRADE_LEDGER_ROW_COLUMNS
            )
            _require_exact_table_columns(
                connection,
                "paper_trade_transitions",
                _PAPER_TRADE_TRANSITION_ROW_COLUMNS,
            )

            raw_markers = connection.execute(
                "SELECT * FROM paper_trade_daily_operations "
                "WHERE operation_id = ? LIMIT 2",
                (operation_id,),
            ).fetchall()
            if not raw_markers:
                raise ValueError("paper daily operation is missing")
            if len(raw_markers) != 1:
                raise ValueError("paper daily operation identity is ambiguous")
            marker = _row_to_daily_marker(raw_markers[0])
            if (
                marker.operation_id != operation_id
                or marker.portfolio_id != portfolio_id
                or marker.event_date != event_date
            ):
                raise ValueError("paper daily operation identity mismatch")

            for table in (
                "paper_trade_daily_operations",
                "paper_trade_ledger",
                "paper_trade_transitions",
            ):
                _require_no_foreign_prefix_rows(
                    connection,
                    table=table,
                    event_date=event_date,
                    portfolio_id=portfolio_id,
                )

            marker_cursor = connection.execute(
                "SELECT * FROM paper_trade_daily_operations "
                "WHERE event_date <= ? ORDER BY event_date, operation_id",
                (event_date,),
            )
            previous: PaperTradeDailyOperationMarker | None = None
            found_target = False
            operation_count = 0
            while batch := marker_cursor.fetchmany(128):
                for raw_marker in batch:
                    operation_count += 1
                    if operation_count > _MAX_EXACT_READ_PREFIX_OPERATIONS:
                        raise ValueError(
                            "paper exact-read operation prefix limit exceeded"
                        )
                    current = _row_to_daily_marker(raw_marker)
                    _require_canonical_event_date(
                        current.event_date, "paper_trade_daily_operations.event_date"
                    )
                    if current.portfolio_id != portfolio_id:
                        raise ValueError("paper exact-read foreign portfolio prefix marker")
                    if previous is not None:
                        if current.event_date == previous.event_date:
                            raise ValueError("paper daily operation date is ambiguous")
                        if current.expected_rowset_hash != previous.rowset_hash_after:
                            raise ValueError("paper daily operation append chain mismatch")
                    if current.operation_id == operation_id:
                        found_target = True
                    previous = current
            if not found_target:
                raise ValueError("paper daily operation prefix is incomplete")

            raw_fills = connection.execute(
                "SELECT * FROM paper_trade_ledger WHERE event_date = ? "
                "ORDER BY fill_id LIMIT ?",
                (event_date, _MAX_EXACT_READ_DAILY_FILLS + 1),
            ).fetchmany(_MAX_EXACT_READ_DAILY_FILLS + 1)
            if len(raw_fills) > _MAX_EXACT_READ_DAILY_FILLS:
                raise ValueError("paper daily operation fill limit exceeded")
            parsed_fills = tuple(_validate_raw_fill_row(row) for row in raw_fills)
            if any(
                fill.portfolio_id != portfolio_id or fill.event_date != event_date
                for fill in parsed_fills
            ):
                raise ValueError("paper exact-read foreign portfolio daily fill")
            fills_by_id = {fill.fill_id: fill for fill in parsed_fills}
            if len(fills_by_id) != len(parsed_fills):
                raise ValueError("paper daily operation fill identity is ambiguous")
            ordered_fills_list: list[PaperTradeFill] = []
            for fill_id in marker.ordered_fill_ids:
                fill = fills_by_id.get(fill_id)
                if fill is None:
                    raise ValueError("paper daily operation fill set/order mismatch")
                ordered_fills_list.append(fill)
            ordered_fills = tuple(ordered_fills_list)
            if len(ordered_fills) != len(parsed_fills):
                raise ValueError("paper daily operation fill set/order mismatch")

            raw_transitions = connection.execute(
                "SELECT * FROM paper_trade_transitions WHERE event_date = ? "
                "ORDER BY transition_id LIMIT 2",
                (event_date,),
            ).fetchmany(2)
            if len(raw_transitions) > 1:
                raise ValueError("paper daily operation transition is ambiguous")
            transition = (
                None
                if not raw_transitions
                else _validate_raw_transition_row(raw_transitions[0])
            )
            if marker.zero_fill:
                if (
                    ordered_fills
                    or transition is not None
                    or marker.rowset_hash_after != marker.expected_rowset_hash
                ):
                    raise ValueError("paper zero-fill operation contains ledger rows")
                if marker.transition_sha256 is not None:
                    raise ValueError("paper zero-fill operation has a transition hash")
            else:
                if transition is None:
                    raise ValueError("paper daily operation transition is missing")
                if (
                    transition.portfolio_id != portfolio_id
                    or transition.event_date != event_date
                ):
                    raise ValueError("paper daily operation transition identity mismatch")
                if transition.transition_id != marker.transition_id:
                    raise ValueError("paper daily operation transition identity mismatch")
                if transition.fill_ids != marker.ordered_fill_ids:
                    raise ValueError("paper daily operation transition fill order mismatch")
                if marker.transition_sha256 is None:
                    raise ValueError("paper daily operation transition hash is missing")

            with localcontext(Context(prec=60)):
                fill_payload = [fill.to_dict() for fill in ordered_fills]
                if marker.fill_batch_sha256 != _canonical_sha256(fill_payload):
                    raise ValueError("paper daily operation fill hash mismatch")
                transition_payload = (
                    None if transition is None else transition.to_dict()
                )
                expected_transition_hash = (
                    None
                    if transition_payload is None
                    else _canonical_sha256(transition_payload)
                )
                if marker.transition_sha256 != expected_transition_hash:
                    raise ValueError("paper daily operation transition hash mismatch")
                operation_payload = _daily_operation_payload(
                    operation_id=marker.operation_id,
                    portfolio_id=marker.portfolio_id,
                    event_date=marker.event_date,
                    expected_rowset_hash=marker.expected_rowset_hash,
                    entries=ordered_fills,
                    transition=transition,
                )
                if marker.operation_sha256 != _canonical_sha256(operation_payload):
                    raise ValueError("paper daily operation operation hash mismatch")

            prefix_before = _ledger_rowset_hash_prefix(
                connection, event_date=event_date, inclusive=False
            )
            prefix_after = _ledger_rowset_hash_prefix(
                connection, event_date=event_date, inclusive=True
            )
            if (
                marker.expected_rowset_hash != prefix_before
                or marker.rowset_hash_after != prefix_after
            ):
                raise ValueError("paper daily operation historical rowset mismatch")

            return PaperTradeDailyOperationRead(
                marker=marker,
                ordered_fills=ordered_fills,
                transition=transition,
                rowset_hash_before=prefix_before,
                rowset_hash_after=prefix_after,
            )
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def append_daily_operation(
        self,
        *,
        operation_id: str,
        portfolio_id: str,
        event_date: str,
        expected_rowset_hash: str,
        fills: Iterable[PaperTradeFill],
        transition: PaperTradeTransition | None,
    ) -> PaperTradeDailyAppendResult:
        """在單一 SQLite 交易中 CAS 寫入有序 daily batch 與 marker。

        ``fills`` 必須已按執行順序提供。非空批次必須含 fill_ids 順序完全相同
        的 transition；空批次會保存零成交 marker，不寫 transition。只有完整
        payload、保存列與目前 ledger rowset 都相符時，重試才會視為冪等成功。
        """

        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id is required")
        if not isinstance(portfolio_id, str) or not portfolio_id.strip():
            raise ValueError("portfolio_id is required")
        try:
            parsed_date = date.fromisoformat(event_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("event_date must be an ISO date") from exc
        if parsed_date.isoformat() != event_date:
            raise ValueError("event_date must use YYYY-MM-DD")
        expected_hash = _require_sha256(expected_rowset_hash, "expected_rowset_hash")
        entries = tuple(fills)
        if any(not isinstance(item, PaperTradeFill) for item in entries):
            raise TypeError("fills must contain PaperTradeFill values")
        if transition is not None and not isinstance(transition, PaperTradeTransition):
            raise TypeError("transition must be PaperTradeTransition or None")
        fill_ids = tuple(item.fill_id for item in entries)
        if len(fill_ids) != len(set(fill_ids)):
            raise ValueError("daily fill order contains duplicate fill_id")
        source_keys = tuple((item.portfolio_id, item.source_event_id) for item in entries)
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("daily fill order contains duplicate portfolio/source_event_id")
        if not entries and transition is not None:
            raise ValueError("zero-fill daily operation cannot contain a transition")
        if entries and transition is None:
            raise ValueError("non-empty daily operation requires a transition")
        if transition is not None and transition.fill_ids != fill_ids:
            raise ValueError("daily transition fill_ids must match exact fill order")
        for fill in entries:
            self._require_identity(fill.portfolio_id)
            if fill.portfolio_id != portfolio_id or fill.event_date != event_date:
                raise ValueError("daily fill portfolio or date does not match operation")
        if transition is not None:
            self._require_identity(transition.portfolio_id)
            if (
                transition.portfolio_id != portfolio_id
                or transition.event_date != event_date
            ):
                raise ValueError("daily transition portfolio or date does not match operation")

        operation_payload = _daily_operation_payload(
            operation_id=operation_id,
            portfolio_id=portfolio_id,
            event_date=event_date,
            expected_rowset_hash=expected_hash,
            entries=entries,
            transition=transition,
        )
        operation_sha256 = _canonical_sha256(operation_payload)
        fill_batch_sha256 = _canonical_sha256(
            [item.to_dict() for item in entries]
        )
        transition_sha256 = (
            None if transition is None else _canonical_sha256(transition.to_dict())
        )
        self._require_identity(portfolio_id)

        connection = self._connect()
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            _require_table_columns(
                connection,
                "paper_trade_daily_operations",
                PAPER_TRADE_DAILY_OPERATION_COLUMNS,
            )
            current_hash = _ledger_rowset_hash(connection)
            existing_row = connection.execute(
                "SELECT * FROM paper_trade_daily_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if existing_row is not None:
                marker = _row_to_daily_marker(existing_row)
                if (
                    marker.portfolio_id != portfolio_id
                    or marker.event_date != event_date
                    or marker.expected_rowset_hash != expected_hash
                    or marker.operation_sha256 != operation_sha256
                    or marker.ordered_fill_ids != fill_ids
                    or marker.fill_batch_sha256 != fill_batch_sha256
                    or marker.transition_id != (
                        None if transition is None else transition.transition_id
                    )
                    or marker.transition_sha256 != transition_sha256
                ):
                    raise ValueError("paper daily operation identity conflicts with prior marker")
                self._verify_daily_operation_rows(
                    connection,
                    marker=marker,
                    expected_fills=entries,
                    expected_transition=transition,
                )
                if current_hash != marker.rowset_hash_after:
                    raise ValueError(
                        "paper daily operation ledger rowset changed after commit"
                    )
                connection.rollback()
                return PaperTradeDailyAppendResult(
                    operation_id=operation_id,
                    status="already_committed",
                    rowset_hash_before=marker.expected_rowset_hash,
                    rowset_hash_after=marker.rowset_hash_after,
                    ordered_fill_ids=marker.ordered_fill_ids,
                    operation_sha256=marker.operation_sha256,
                )
            if current_hash != expected_hash:
                raise ValueError("paper trade ledger rowset compare-and-swap failed")
            same_day_fills = connection.execute(
                "SELECT 1 FROM paper_trade_ledger "
                "WHERE portfolio_id = ? AND event_date = ? LIMIT 1",
                (portfolio_id, event_date),
            ).fetchone()
            same_day_transitions = connection.execute(
                "SELECT 1 FROM paper_trade_transitions "
                "WHERE portfolio_id = ? AND event_date = ? LIMIT 1",
                (portfolio_id, event_date),
            ).fetchone()
            if same_day_fills is not None or same_day_transitions is not None:
                raise ValueError("paper daily ledger window is not empty")
            existing_day = connection.execute(
                "SELECT operation_id FROM paper_trade_daily_operations "
                "WHERE portfolio_id = ? AND event_date = ? LIMIT 1",
                (portfolio_id, event_date),
            ).fetchone()
            if existing_day is not None:
                raise ValueError(
                    "paper daily operation already exists for portfolio/event_date"
                )

            if entries:
                fill_placeholders = ",".join("?" for _ in fill_ids)
                existing_fills = connection.execute(
                    "SELECT fill_id FROM paper_trade_ledger WHERE fill_id IN ("
                    + fill_placeholders
                    + ")",
                    fill_ids,
                ).fetchall()
                source_clauses = " OR ".join(
                    "(portfolio_id = ? AND source_event_id = ?)"
                    for _ in source_keys
                )
                source_params = tuple(
                    value
                    for key in source_keys
                    for value in key
                )
                existing_sources = connection.execute(
                    "SELECT fill_id FROM paper_trade_ledger WHERE " + source_clauses,
                    source_params,
                ).fetchall()
                if existing_fills or existing_sources:
                    raise ValueError(
                        "paper trade fill already exists: fill_id or "
                        "portfolio/source_event_id"
                    )
                self._insert_daily_fills(connection, entries)
                self._insert_daily_transition(connection, transition)

            after_hash = _ledger_rowset_hash(connection)
            marker_without_hash = PaperTradeDailyOperationMarker(
                operation_id=operation_id,
                portfolio_id=portfolio_id,
                event_date=event_date,
                expected_rowset_hash=expected_hash,
                rowset_hash_after=after_hash,
                ordered_fill_ids=fill_ids,
                fill_batch_sha256=fill_batch_sha256,
                transition_id=None if transition is None else transition.transition_id,
                transition_sha256=transition_sha256,
                operation_sha256=operation_sha256,
                marker_sha256="",
                zero_fill=not entries,
            )
            marker_sha256 = _canonical_sha256(_daily_marker_payload(marker_without_hash))
            marker = replace(marker_without_hash, marker_sha256=marker_sha256)
            connection.execute(
                """
                INSERT INTO paper_trade_daily_operations (
                    schema_version, operation_id, portfolio_id, event_date,
                    expected_rowset_hash, rowset_hash_after,
                    ordered_fill_ids_json, fill_batch_sha256,
                    transition_id, transition_sha256, operation_sha256,
                    marker_sha256, zero_fill
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION,
                    marker.operation_id,
                    marker.portfolio_id,
                    marker.event_date,
                    marker.expected_rowset_hash,
                    marker.rowset_hash_after,
                    _canonical_transition_json(list(marker.ordered_fill_ids)),
                    marker.fill_batch_sha256,
                    marker.transition_id,
                    marker.transition_sha256,
                    marker.operation_sha256,
                    marker.marker_sha256,
                    int(marker.zero_fill),
                ),
            )
            connection.commit()
            return PaperTradeDailyAppendResult(
                operation_id=operation_id,
                status="appended",
                rowset_hash_before=expected_hash,
                rowset_hash_after=after_hash,
                ordered_fill_ids=fill_ids,
                operation_sha256=operation_sha256,
            )
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ValueError("paper trade daily append identity already exists") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _insert_daily_fills(
        connection: sqlite3.Connection,
        entries: tuple[PaperTradeFill, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO paper_trade_ledger (
                schema_version, fill_id, order_id, portfolio_id, event_date,
                stock_code, side, requested_quantity, filled_quantity,
                reference_price, fill_price, commission, tax, slippage_cost,
                turnover_bp, execution_gap_bp, status, source_event_id,
                override_reason, source_type, research_only,
                broker_order_allowed, auto_rebalance_allowed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                (
                    PAPER_TRADE_LEDGER_SCHEMA_VERSION,
                    item.fill_id,
                    item.order_id,
                    item.portfolio_id,
                    item.event_date,
                    item.stock_code,
                    item.side,
                    item.requested_quantity,
                    item.filled_quantity,
                    str(item.reference_price),
                    None if item.fill_price is None else str(item.fill_price),
                    str(item.commission),
                    str(item.tax),
                    str(item.slippage_cost),
                    item.turnover_bp,
                    item.execution_gap_bp,
                    item.status,
                    item.source_event_id,
                    item.override_reason,
                    item.source_type,
                    int(item.research_only),
                    int(item.broker_order_allowed),
                    int(item.auto_rebalance_allowed),
                )
                for item in entries
            ),
        )

    @staticmethod
    def _insert_daily_transition(
        connection: sqlite3.Connection,
        transition: PaperTradeTransition | None,
    ) -> None:
        if transition is None:
            return
        values = transition.to_dict()
        connection.execute(
            """
            INSERT INTO paper_trade_transitions (
                schema_version, transition_id, batch_id, portfolio_id,
                event_date, fill_ids_json, pre_cash, pre_total_value,
                post_cash, post_total_value, common_nav, common_prices_json,
                pre_positions_json, post_positions_json, source_type,
                research_only, broker_order_allowed, auto_rebalance_allowed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                PAPER_TRADE_TRANSITION_SCHEMA_VERSION,
                transition.transition_id,
                transition.batch_id,
                transition.portfolio_id,
                transition.event_date,
                _canonical_transition_json(values["fill_ids"]),
                str(transition.pre_cash),
                str(transition.pre_total_value),
                str(transition.post_cash),
                str(transition.post_total_value),
                str(transition.common_nav),
                _canonical_transition_json(values["common_prices"]),
                _canonical_transition_json(values["pre_positions"]),
                _canonical_transition_json(values["post_positions"]),
                transition.source_type,
                int(transition.research_only),
                int(transition.broker_order_allowed),
                int(transition.auto_rebalance_allowed),
            ),
        )

    @staticmethod
    def _verify_daily_operation_rows(
        connection: sqlite3.Connection,
        *,
        marker: PaperTradeDailyOperationMarker,
        expected_fills: tuple[PaperTradeFill, ...],
        expected_transition: PaperTradeTransition | None,
    ) -> None:
        fill_ids = marker.ordered_fill_ids
        if fill_ids:
            placeholders = ",".join("?" for _ in fill_ids)
            rows = connection.execute(
                "SELECT * FROM paper_trade_ledger WHERE fill_id IN ("
                + placeholders
                + ")",
                fill_ids,
            ).fetchall()
            by_id = {str(row["fill_id"]): _row_to_fill(row) for row in rows}
            loaded = tuple(by_id.get(fill_id) for fill_id in fill_ids)
            if len(rows) != len(fill_ids) or loaded != expected_fills:
                raise ValueError("paper daily operation fill readback mismatch")
            if marker.fill_batch_sha256 != _canonical_sha256(
                [item.to_dict() for item in expected_fills]
            ):
                raise ValueError("paper daily operation fill batch hash mismatch")
        elif expected_fills:
            raise ValueError("paper daily operation zero-fill readback mismatch")
        if expected_transition is None:
            if marker.transition_id is not None or marker.transition_sha256 is not None:
                raise ValueError("paper daily operation unexpected transition marker")
        else:
            if marker.transition_id != expected_transition.transition_id:
                raise ValueError("paper daily operation transition identity mismatch")
            row = connection.execute(
                "SELECT * FROM paper_trade_transitions WHERE transition_id = ?",
                (expected_transition.transition_id,),
            ).fetchone()
            if row is None or _row_to_transition(row) != expected_transition:
                raise ValueError("paper daily operation transition readback mismatch")

    def _append_entries(
        self,
        entries: tuple[PaperTradeFill, ...],
        *,
        transition: PaperTradeTransition | None,
    ) -> None:
        for item in entries:
            self._require_identity(item.portfolio_id)
        if transition is not None:
            self._require_identity(transition.portfolio_id)
        fill_ids = tuple(item.fill_id for item in entries)
        source_event_keys = tuple(
            (item.portfolio_id, item.source_event_id) for item in entries
        )
        if len(set(fill_ids)) != len(fill_ids):
            raise ValueError("paper trade fill already exists: duplicate fill_id in batch")
        if len(set(source_event_keys)) != len(source_event_keys):
            raise ValueError(
                "paper trade fill already exists: duplicate portfolio/source_event_id in batch"
            )
        connection = self._connect()
        try:
            # Serialize the identity check with the insert.  A retry after a
            # process crash can then either observe the complete batch
            # (handled by the producer's exact readback) or fail closed.
            connection.execute("BEGIN IMMEDIATE")
            fill_placeholders = ",".join("?" for _ in fill_ids)
            existing = connection.execute(
                "SELECT fill_id FROM paper_trade_ledger "
                f"WHERE fill_id IN ({fill_placeholders})",
                fill_ids,
            ).fetchall()
            if not existing:
                source_clauses = " OR ".join(
                    "(portfolio_id = ? AND source_event_id = ?)"
                    for _ in source_event_keys
                )
                source_params = tuple(
                    value
                    for portfolio_id, source_event_id in source_event_keys
                    for value in (portfolio_id, source_event_id)
                )
                existing = connection.execute(
                    "SELECT fill_id FROM paper_trade_ledger WHERE "
                    + source_clauses,
                    source_params,
                ).fetchall()
            if existing:
                raise ValueError(
                    "paper trade fill already exists: fill_id or "
                    "portfolio/source_event_id"
                )
            self._insert_daily_fills(connection, entries)
            self._insert_daily_transition(connection, transition)
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ValueError("paper trade fill already exists") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_transitions(
        self,
        *,
        portfolio_id: str = "paper-main",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[PaperTradeTransition, ...]:
        self._require_identity(portfolio_id)
        clauses = ["portfolio_id = ?"]
        params: list[Any] = [portfolio_id]
        if start_date is not None:
            clauses.append("event_date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("event_date <= ?")
            params.append(end_date)
        query = (
            "SELECT * FROM paper_trade_transitions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY event_date, transition_id"
        )
        connection = self._connect(read_only=True)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, tuple(params)).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_transition(row) for row in rows)

    def list(
        self,
        *,
        portfolio_id: str = "paper-main",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[PaperTradeFill, ...]:
        self._require_identity(portfolio_id)
        clauses = ["portfolio_id = ?"]
        params: list[Any] = [portfolio_id]
        if start_date is not None:
            clauses.append("event_date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("event_date <= ?")
            params.append(end_date)
        query = (
            "SELECT * FROM paper_trade_ledger WHERE "
            + " AND ".join(clauses)
            + " ORDER BY event_date, fill_id"
        )
        connection = self._connect(read_only=True)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, tuple(params)).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_fill(row) for row in rows)

    def schema_readback(self) -> dict[str, object]:
        """以唯讀連線確認 writer 建立的兩張 ledger 表仍可讀。"""

        resolved = (self._guard_path() if self._route is not None
                    else self.db_path.expanduser().resolve())
        if not self._custody.exists(resolved):
            raise ValueError("paper ledger schema readback path is not a file")
        uri = resolved.as_uri() + "?mode=ro"
        connection: sqlite3.Connection | None = None
        required_tables = ("paper_trade_ledger", "paper_trade_transitions")
        required_columns = {
            "paper_trade_ledger": PAPER_TRADE_LEDGER_COLUMNS,
            "paper_trade_transitions": PAPER_TRADE_TRANSITION_COLUMNS,
        }
        try:
            connection = (self._connect(read_only=True) if self._route is not None
                          else sqlite3.connect(uri, uri=True))
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA query_only").fetchone() != (1,):
                raise ValueError("paper ledger schema readback is not query-only")
            table_columns: dict[str, list[str]] = {}
            row_counts: dict[str, int] = {}
            for table in required_tables:
                columns = [
                    str(row[1])
                    for row in connection.execute(
                        f'PRAGMA table_info("{table}")'
                    ).fetchall()
                ]
                if not columns:
                    raise ValueError(f"paper ledger schema table is missing:{table}")
                missing = sorted(required_columns[table] - set(columns))
                if missing:
                    raise ValueError(
                        f"paper ledger schema columns are missing:{table}:"
                        + ",".join(missing)
                    )
                table_columns[table] = sorted(columns)
                row_counts[table] = int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
        except sqlite3.Error as exc:
            raise ValueError("paper ledger schema readback failed") from exc
        finally:
            if connection is not None:
                connection.close()
        return {
            "path": str(resolved),
            "mode": "ro/query_only",
            "required_tables": list(required_tables),
            "table_columns": table_columns,
            "row_counts": row_counts,
            "ledger_schema_version": PAPER_TRADE_LEDGER_SCHEMA_VERSION,
            "transition_schema_version": PAPER_TRADE_TRANSITION_SCHEMA_VERSION,
            "readback_verified": True,
            # 表存在只證明 schema readiness；不把既有 fill rows 推成歷史
            # transition evidence。consumer 仍須依 transition rows 驗證窗口。
            "historical_transition_evidence_inferred": False,
        }

    def daily_operation_schema_readback(self) -> dict[str, object]:
        """唯讀確認 CAS operation marker schema，不變更資料庫。"""

        resolved = (
            self._guard_path()
            if self._route is not None
            else self.db_path.expanduser().resolve()
        )
        if not self._custody.exists(resolved):
            raise ValueError("paper ledger schema readback path is not a file")
        connection = self._connect(read_only=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA query_only").fetchone() != (1,):
                raise ValueError("paper ledger schema readback is not query-only")
            for table, columns in (
                ("paper_trade_ledger", PAPER_TRADE_LEDGER_COLUMNS),
                ("paper_trade_transitions", PAPER_TRADE_TRANSITION_COLUMNS),
                ("paper_trade_daily_operations", PAPER_TRADE_DAILY_OPERATION_COLUMNS),
            ):
                _require_table_columns(connection, table, columns)
            return {
                "path": str(resolved),
                "mode": "ro/query_only",
                "daily_operation_schema_version": PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION,
                "readback_verified": True,
            }
        except sqlite3.Error as exc:
            raise ValueError("paper ledger daily operation schema readback failed") from exc
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_trade_ledger (
                    schema_version TEXT NOT NULL,
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    portfolio_id TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    requested_quantity INTEGER NOT NULL,
                    filled_quantity INTEGER NOT NULL,
                    reference_price TEXT NOT NULL,
                    fill_price TEXT,
                    commission TEXT NOT NULL,
                    tax TEXT NOT NULL,
                    slippage_cost TEXT NOT NULL,
                    turnover_bp INTEGER,
                    execution_gap_bp INTEGER,
                    status TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    override_reason TEXT,
                    source_type TEXT NOT NULL,
                    research_only INTEGER NOT NULL,
                    broker_order_allowed INTEGER NOT NULL,
                    auto_rebalance_allowed INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_paper_trade_ledger_portfolio_date
                    ON paper_trade_ledger (portfolio_id, event_date, fill_id);
                CREATE INDEX IF NOT EXISTS idx_paper_trade_ledger_source_event
                    ON paper_trade_ledger (source_event_id);
                CREATE TABLE IF NOT EXISTS paper_trade_transitions (
                    schema_version TEXT NOT NULL,
                    transition_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    portfolio_id TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    fill_ids_json TEXT NOT NULL,
                    pre_cash TEXT NOT NULL,
                    pre_total_value TEXT NOT NULL,
                    post_cash TEXT NOT NULL,
                    post_total_value TEXT NOT NULL,
                    common_nav TEXT NOT NULL,
                    common_prices_json TEXT NOT NULL,
                    pre_positions_json TEXT NOT NULL,
                    post_positions_json TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    research_only INTEGER NOT NULL,
                    broker_order_allowed INTEGER NOT NULL,
                    auto_rebalance_allowed INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_paper_trade_transitions_portfolio_date
                    ON paper_trade_transitions (portfolio_id, event_date, transition_id);
                CREATE TABLE IF NOT EXISTS paper_trade_daily_operations (
                    schema_version TEXT NOT NULL,
                    operation_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    expected_rowset_hash TEXT NOT NULL,
                    rowset_hash_after TEXT NOT NULL,
                    ordered_fill_ids_json TEXT NOT NULL,
                    fill_batch_sha256 TEXT NOT NULL,
                    transition_id TEXT,
                    transition_sha256 TEXT,
                    operation_sha256 TEXT NOT NULL,
                    marker_sha256 TEXT NOT NULL,
                    zero_fill INTEGER NOT NULL CHECK (zero_fill IN (0, 1))
                );
                CREATE INDEX IF NOT EXISTS idx_paper_trade_daily_operations_portfolio_date
                    ON paper_trade_daily_operations (portfolio_id, event_date, operation_id);
                """
            )
        finally:
            connection.close()


def _row_to_fill(row: sqlite3.Row) -> PaperTradeFill:
    return PaperTradeFill(
        fill_id=str(row["fill_id"]),
        order_id=str(row["order_id"]),
        portfolio_id=str(row["portfolio_id"]),
        event_date=str(row["event_date"]),
        stock_code=str(row["stock_code"]),
        side=str(row["side"]),
        requested_quantity=int(row["requested_quantity"]),
        filled_quantity=int(row["filled_quantity"]),
        reference_price=Decimal(str(row["reference_price"])),
        fill_price=(None if row["fill_price"] is None else Decimal(str(row["fill_price"]))),
        commission=Decimal(str(row["commission"])),
        tax=Decimal(str(row["tax"])),
        slippage_cost=Decimal(str(row["slippage_cost"])),
        turnover_bp=(None if row["turnover_bp"] is None else int(row["turnover_bp"])),
        execution_gap_bp=(
            None if row["execution_gap_bp"] is None else int(row["execution_gap_bp"])
        ),
        status=str(row["status"]),
        source_event_id=str(row["source_event_id"]),
        override_reason=(None if row["override_reason"] is None else str(row["override_reason"])),
        source_type=str(row["source_type"]),
        research_only=bool(row["research_only"]),
        broker_order_allowed=bool(row["broker_order_allowed"]),
        auto_rebalance_allowed=bool(row["auto_rebalance_allowed"]),
    )


def _row_to_transition(row: sqlite3.Row) -> PaperTradeTransition:
    if row["schema_version"] != PAPER_TRADE_TRANSITION_SCHEMA_VERSION:
        raise ValueError("transition schema_version is not governed")

    def decode_json(field_name: str) -> object:
        try:
            return json.loads(str(row[field_name]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"transition {field_name} is invalid JSON") from exc

    fill_ids_value = decode_json("fill_ids_json")
    common_prices_value = decode_json("common_prices_json")
    pre_positions_value = decode_json("pre_positions_json")
    post_positions_value = decode_json("post_positions_json")
    if (
        not isinstance(fill_ids_value, list)
        or not isinstance(common_prices_value, dict)
        or not isinstance(pre_positions_value, dict)
        or not isinstance(post_positions_value, dict)
    ):
        raise ValueError("transition JSON fields have invalid shapes")
    return PaperTradeTransition(
        transition_id=str(row["transition_id"]),
        batch_id=str(row["batch_id"]),
        portfolio_id=str(row["portfolio_id"]),
        event_date=str(row["event_date"]),
        fill_ids=tuple(str(item) for item in fill_ids_value),
        pre_cash=Decimal(str(row["pre_cash"])),
        pre_total_value=Decimal(str(row["pre_total_value"])),
        post_cash=Decimal(str(row["post_cash"])),
        post_total_value=Decimal(str(row["post_total_value"])),
        common_nav=Decimal(str(row["common_nav"])),
        common_prices={
            str(symbol): Decimal(str(price))
            for symbol, price in common_prices_value.items()
        },
        pre_positions={
            str(symbol): int(quantity)
            for symbol, quantity in pre_positions_value.items()
        },
        post_positions={
            str(symbol): int(quantity)
            for symbol, quantity in post_positions_value.items()
        },
        source_type=str(row["source_type"]),
        research_only=bool(row["research_only"]),
        broker_order_allowed=bool(row["broker_order_allowed"]),
        auto_rebalance_allowed=bool(row["auto_rebalance_allowed"]),
    )


__all__ = [
    "PAPER_TRADE_DAILY_OPERATION_COLUMNS",
    "PAPER_TRADE_DAILY_OPERATION_SCHEMA_VERSION",
    "PAPER_TRADE_EVENT_STATUSES",
    "PAPER_TRADE_LEDGER_SCHEMA_VERSION",
    "PAPER_TRADE_LEDGER_ROWSET_SCHEMA_VERSION",
    "PAPER_TRADE_SOURCE_IDENTITY_SCOPE",
    "PAPER_TRADE_TRANSITION_SCHEMA_VERSION",
    "PaperTradeDailyAppendResult",
    "PaperTradeDailyOperationRead",
    "PaperTradeDailyOperationMarker",
    "PaperTradeFill",
    "PaperTradeLedgerRepository",
    "PaperTradeTransition",
]
