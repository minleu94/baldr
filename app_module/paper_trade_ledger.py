"""Research-only paper trade fill ledger.

This module is deliberately separate from ``PortfolioService``.  The manual
Portfolio JSONL store represents user-recorded holdings, while this ledger
represents governed paper execution evidence.  A paper event is append-only
and never authorizes a broker order or mutates the formal Portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


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


class PaperTradeLedgerRepository:
    """Append-only SQLite writer for explicit paper fill events.

    The constructor is intentionally a writer boundary.  UI/readiness code
    must use ``ReadOnlySQLiteManager`` instead and therefore cannot create the
    schema merely by inspecting status.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

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

    def _append_entries(
        self,
        entries: tuple[PaperTradeFill, ...],
        *,
        transition: PaperTradeTransition | None,
    ) -> None:
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
        connection = sqlite3.connect(self.db_path)
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
                    (
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
            if transition is not None:
                transition_values = transition.to_dict()
                connection.execute(
                    """
                    INSERT INTO paper_trade_transitions (
                        schema_version, transition_id, batch_id, portfolio_id,
                        event_date, fill_ids_json, pre_cash, pre_total_value,
                        post_cash, post_total_value, common_nav,
                        common_prices_json, pre_positions_json,
                        post_positions_json, source_type, research_only,
                        broker_order_allowed, auto_rebalance_allowed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        PAPER_TRADE_TRANSITION_SCHEMA_VERSION,
                        transition.transition_id,
                        transition.batch_id,
                        transition.portfolio_id,
                        transition.event_date,
                        _canonical_transition_json(transition_values["fill_ids"]),
                        str(transition.pre_cash),
                        str(transition.pre_total_value),
                        str(transition.post_cash),
                        str(transition.post_total_value),
                        str(transition.common_nav),
                        _canonical_transition_json(
                            transition_values["common_prices"]
                        ),
                        _canonical_transition_json(
                            transition_values["pre_positions"]
                        ),
                        _canonical_transition_json(
                            transition_values["post_positions"]
                        ),
                        transition.source_type,
                        int(transition.research_only),
                        int(transition.broker_order_allowed),
                        int(transition.auto_rebalance_allowed),
                    ),
                )
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
        connection = sqlite3.connect(self.db_path)
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
        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, tuple(params)).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_fill(row) for row in rows)

    def schema_readback(self) -> dict[str, object]:
        """以唯讀連線確認 writer 建立的兩張 ledger 表仍可讀。"""

        resolved = self.db_path.expanduser().resolve()
        if not resolved.is_file():
            raise ValueError("paper ledger schema readback path is not a file")
        uri = resolved.as_uri() + "?mode=ro"
        connection: sqlite3.Connection | None = None
        required_tables = ("paper_trade_ledger", "paper_trade_transitions")
        required_columns = {
            "paper_trade_ledger": PAPER_TRADE_LEDGER_COLUMNS,
            "paper_trade_transitions": PAPER_TRADE_TRANSITION_COLUMNS,
        }
        try:
            connection = sqlite3.connect(uri, uri=True)
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

    def _ensure_schema(self) -> None:
        connection = sqlite3.connect(self.db_path)
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
    "PAPER_TRADE_EVENT_STATUSES",
    "PAPER_TRADE_LEDGER_SCHEMA_VERSION",
    "PAPER_TRADE_SOURCE_IDENTITY_SCOPE",
    "PAPER_TRADE_TRANSITION_SCHEMA_VERSION",
    "PaperTradeFill",
    "PaperTradeLedgerRepository",
    "PaperTradeTransition",
]
