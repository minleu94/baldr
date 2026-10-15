"""策略 Paper checkpoint 的版本化可得時鐘 companion。

``persisted_at`` 與 ``available_at`` 是 writer 在完整 finalized snapshot、base
receipt 與前一 companion 版本成功讀回後觀測到的 UTC 時鐘。它們不宣稱目前含
該欄位的 companion 版本已在同一時刻提交。跨資料庫仍採逐庫恢復，不代表原子提交。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from app_module.personal_data_paths import PersonalDataPathError
from app_module.personal_paper_store_paths import (
    PersonalPaperStorePaths,
    PersonalStoreCustody,
)
from app_module.personal_store_routes import (
    PersonalStoreDomain,
    PersonalStoreMode,
    PersonalStoreRouteError,
    StoreSourceKind,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
)
from app_module.paper_trade_ledger import (
    PaperTradeDailyOperationMarker,
    PaperTradeDailyOperationRead,
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.portfolio_research_valuation import PortfolioResearchValuation
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
)


AVAILABILITY_SCHEMA = "strategy-paper-account-availability.v1"
_TABLE = "strategy_paper_account_availability_v1"
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_TABLE_COLUMNS = (
    "schema_version",
    "snapshot_id",
    "operation_id",
    "portfolio_id",
    "account_namespace",
    "binding_sha256",
    "snapshot_sha256",
    "base_receipt_sha256",
    "persisted_at_utc",
    "available_at_utc",
    "receipt_json",
    "receipt_sha256",
)
_OPERATION_TABLE = "strategy_paper_account_daily_operations"
_DAILY_RECEIPT_TABLE = "strategy_paper_account_daily_receipts"
_MAX_ACCOUNT_POSITIONS = 8
_MAX_BASE_JSON_BYTES = 2 * 1024 * 1024
_MAX_DAILY_FILLS = 2000
_OPERATION_COLUMNS = (
    "operation_id",
    "portfolio_id",
    "prior_snapshot_id",
    "prior_snapshot_sha256",
    "snapshot_id",
    "snapshot_sha256",
    "binding_sha256",
    "operation_json",
    "operation_sha256",
    "expected_ledger_rowset_hash",
    "ledger_after_rowset_hash",
    "ledger_operation_sha256",
    "receipt_sha256",
    "status",
)
_DAILY_RECEIPT_COLUMNS = (
    "snapshot_id",
    "operation_id",
    "portfolio_id",
    "account_namespace",
    "binding_sha256",
    "receipt_json",
    "receipt_sha256",
)
_SNAPSHOT_COLUMNS = (
    "snapshot_id",
    "portfolio_id",
    "decision_date",
    "source_result_id",
    "cash",
    "total_value",
)
_POSITION_COLUMNS = (
    "snapshot_id",
    "stock_code",
    "quantity",
    "mark_price",
    "market_value",
    "weight_bp",
)
_OPERATION_FIELDS = frozenset(
    {
        "schema_version", "operation_id", "portfolio_id", "account_namespace",
        "binding_sha256", "strategy_id", "strategy_version_id",
        "strategy_config_sha256", "policy_sha256", "cost_model_sha256",
        "benchmark_sha256", "prior_snapshot_id", "prior_snapshot_sha256",
        "prior_receipt_sha256", "snapshot", "snapshot_sha256", "result_id",
        "expected_ledger_rowset_hash",
        "saved_execution", "decision_cutoff", "execution_date", "mark_cutoff",
        "fills", "ordered_fill_ids", "transition", "mark_prices",
        "execution_prices", "quote_event_receipts", "performance_eligible",
        "forward_qualification", "research_only", "broker_order_allowed",
        "auto_rebalance_allowed",
    }
)
_DAILY_RECEIPT_FIELDS = frozenset(
    {
        "schema_version", "operation_id", "operation_sha256", "portfolio_id",
        "account_namespace", "binding_sha256", "strategy_version_id",
        "prior_snapshot_id", "prior_snapshot_sha256", "prior_receipt_sha256",
        "snapshot_id", "snapshot_sha256", "result_id", "saved_execution",
        "decision_cutoff", "execution_date", "mark_cutoff", "ordered_fill_ids",
        "fill_batch_sha256", "transition_sha256", "mark_prices",
        "execution_prices", "quote_event_receipts", "ledger_rowset_hash_before",
        "ledger_rowset_hash_after", "ledger_operation_sha256", "zero_fill",
        "performance_eligible", "forward_qualification", "research_only",
        "broker_order_allowed", "auto_rebalance_allowed",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "snapshot_id", "portfolio_id", "decision_date", "source_result_id",
        "cash", "total_value", "positions",
    }
)
_POSITION_FIELDS = frozenset(
    {"stock_code", "quantity", "mark_price", "market_value", "weight_bp"}
)
_SAVED_EXECUTION_FIELDS = frozenset(
    {
        "result_id", "raw_artifact_sha256", "payload_hash", "artifact_location",
        "decision_at", "created_at", "available_at", "persisted_at",
        "strategy_version_id", "strategy_config_hash", "strategy_config_id",
        "strategy_config_content_sha256",
    }
)
_FILL_FIELDS = frozenset(
    {
        "schema_version", "fill_id", "order_id", "portfolio_id", "event_date",
        "stock_code", "side", "requested_quantity", "filled_quantity",
        "reference_price", "fill_price", "commission", "tax", "slippage_cost",
        "total_cost", "gross_amount", "turnover_bp", "execution_gap_bp",
        "status", "source_event_id", "override_reason", "source_type",
        "research_only", "broker_order_allowed", "auto_rebalance_allowed",
    }
)
_TRANSITION_FIELDS = frozenset(
    {
        "schema_version", "transition_id", "batch_id", "portfolio_id",
        "event_date", "fill_ids", "pre_cash", "pre_total_value", "post_cash",
        "post_total_value", "common_nav", "common_prices", "pre_positions",
        "post_positions", "source_type", "research_only", "broker_order_allowed",
        "auto_rebalance_allowed",
    }
)
_PRICE_EVIDENCE_FIELDS = frozenset(
    {
        "source_date", "stock_code", "scalar_column", "scalar_value", "source_id",
        "parser_id", "first_observed_at", "written_at", "raw_response_sha256",
        "custody_receipt_sha256", "observation_receipt_sha256", "csv_sha256",
        "projection_row_sha256", "sqlite_projection_row_sha256",
        "projection_columns",
    }
)
_QUOTE_EVENT_FIELDS = frozenset(
    {
        "schema_version", "receipt_id", "stock_code", "source_date",
        "projection_row_sha256", "event_at", "receipt_sha256",
    }
)


class StrategyPaperAccountAvailabilityError(ValueError):
    """checkpoint availability receipt 缺失或不能精確驗證。"""


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountAvailability:
    schema_version: str
    operation_id: str
    snapshot_id: str
    portfolio_id: str
    account_namespace: str
    binding_sha256: str
    snapshot_sha256: str
    base_receipt_sha256: str
    persisted_at: datetime
    available_at: datetime
    receipt_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != AVAILABILITY_SCHEMA:
            raise StrategyPaperAccountAvailabilityError(
                "availability_dto_schema_version_invalid"
            )
        for field in (
            "operation_id", "snapshot_id", "portfolio_id", "account_namespace"
        ):
            _require_text(getattr(self, field), f"availability_dto_{field}")
        for field in (
            "binding_sha256", "snapshot_sha256", "base_receipt_sha256", "receipt_sha256"
        ):
            _require_hash(getattr(self, field), f"availability_dto_{field}")
        persisted_at = _parse_aware_utc(self.persisted_at, "availability_dto_persisted_at")
        available_at = _parse_aware_utc(self.available_at, "availability_dto_available_at")
        if available_at < persisted_at:
            raise StrategyPaperAccountAvailabilityError("availability_dto_clock_order_invalid")
        object.__setattr__(self, "persisted_at", persisted_at)
        object.__setattr__(self, "available_at", available_at)


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountCheckpointRead:
    """同一 exact binding 下讀回的完整 snapshot、clock 與 ledger append。"""

    binding: StrategyPaperAccountBinding
    snapshot: PaperPortfolioSnapshot
    availability: StrategyPaperAccountAvailability
    operation_sha256: str
    ledger_operation: PaperTradeDailyOperationMarker
    ordered_fills: tuple[PaperTradeFill, ...]
    transition: PaperTradeTransition | None
    mark_price_evidence_json: tuple[str, ...] = ()
    allocation_decision_date: str | None = None
    allocation_prefix_fills: tuple[PaperTradeFill, ...] = ()
    allocation_prefix_transitions: tuple[PaperTradeTransition, ...] = ()
    allocation_prefix_rowset_hash: str | None = None

    def __post_init__(self) -> None:
        if self.snapshot.snapshot_id != self.availability.snapshot_id:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_snapshot_identity_mismatch"
            )
        if (
            self.snapshot.portfolio_id != self.binding.portfolio_id
            or self.availability.portfolio_id != self.binding.portfolio_id
            or self.availability.account_namespace != self.binding.account_namespace
            or self.availability.binding_sha256 != self.binding.binding_sha256
        ):
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_binding_identity_mismatch"
            )
        _require_hash(self.operation_sha256, "checkpoint_read_operation_sha256")
        if self.ledger_operation.ordered_fill_ids != tuple(
            item.fill_id for item in self.ordered_fills
        ):
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_ledger_fill_order_mismatch"
            )
        if self.ledger_operation.zero_fill != (not self.ordered_fills):
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_ledger_zero_fill_mismatch"
            )
        if self.ledger_operation.operation_id != self.availability.operation_id:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_ledger_operation_identity_mismatch"
            )


def _utc_now() -> datetime:
    """取得受控 writer 的時鐘；呼叫端不能指定或補填時間。"""

    return datetime.now(timezone.utc)


def _read_exact_ledger_operation(
    ledger: PaperTradeLedgerRepository,
    *,
    operation_id: str,
    portfolio_id: str,
    event_date: str,
    allocation_decision_date: str | None = None,
) -> PaperTradeDailyOperationRead:
    """透過 ledger 公開 API 讀回 route-bound exact append。"""

    try:
        if allocation_decision_date is None:
            return ledger.read_exact_daily_operation(
                operation_id, portfolio_id=portfolio_id, event_date=event_date,
            )
        return ledger.read_exact_daily_operation(
            operation_id,
            portfolio_id=portfolio_id,
            event_date=event_date,
            allocation_decision_date=allocation_decision_date,
        )
    except ValueError as exc:
        message = str(exc)
        if any(
            marker in message
            for marker in (
                "append chain mismatch",
                "historical rowset mismatch",
                "prefix is incomplete",
                "date is ambiguous",
                "fill hash mismatch",
                "transition hash mismatch",
            )
        ):
            code = "checkpoint_read_ledger_append_chain_mismatch"
        elif "daily operation is missing" in message:
            code = "checkpoint_read_ledger_operation_missing"
        elif "daily operation identity mismatch" in message:
            code = "checkpoint_read_ledger_operation_identity_mismatch"
        else:
            code = "checkpoint_read_ledger_unavailable"
        raise StrategyPaperAccountAvailabilityError(code) from exc
    except (OSError, RuntimeError, sqlite3.Error, TypeError) as exc:
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_ledger_unavailable"
        ) from exc


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return value


def _require_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return value


def _parse_aware_utc(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise StrategyPaperAccountAvailabilityError(f"{field}_invalid") from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise StrategyPaperAccountAvailabilityError(f"{field}_timezone_unknown")
    return value.astimezone(timezone.utc)


def _parse_json_object(raw: object, field: str) -> dict[str, object]:
    if not isinstance(raw, str):
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise StrategyPaperAccountAvailabilityError(f"{field}_duplicate_key")
            result[key] = item
        return result

    def reject_float(_: str) -> object:
        raise StrategyPaperAccountAvailabilityError(f"{field}_float_forbidden")

    def reject_constant(_: str) -> object:
        raise StrategyPaperAccountAvailabilityError(f"{field}_non_finite_forbidden")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, StrategyPaperAccountAvailabilityError):
            raise
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid") from exc
    if not isinstance(value, dict) or _canonical_json(value) != raw:
        raise StrategyPaperAccountAvailabilityError(f"{field}_not_canonical")
    return value


def _require_fields(
    value: object,
    expected: frozenset[str],
    field: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StrategyPaperAccountAvailabilityError(f"{field}_fields_unknown_or_incomplete")
    return value


def _require_text_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return value


def _require_hash_value(value: object, field: str) -> str:
    return _require_hash(_require_text_value(value, field), field)


def _require_money_text(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 128:
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    try:
        amount = Decimal(value)
    except Exception as exc:  # Decimal's accepted exception types vary by input.
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return amount


def _require_sql_integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return value


def _table_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    )


def _unique_indexes(connection: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    indexes = connection.execute(f'PRAGMA index_list("{table}")').fetchall()
    unique: set[tuple[str, ...]] = set()
    for index in indexes:
        if int(index[2]) != 1 or (len(index) > 4 and int(index[4]) != 0):
            continue
        index_name = str(index[1]).replace('"', '""')
        columns = tuple(
            str(row[2])
            for row in connection.execute(f'PRAGMA index_info("{index_name}")').fetchall()
        )
        unique.add(columns)
    return unique


def _require_table_contract(
    connection: sqlite3.Connection,
    table: str,
    expected_columns: tuple[str, ...],
    expected_unique_indexes: frozenset[tuple[str, ...]],
) -> None:
    if _table_columns(connection, table) != expected_columns:
        raise StrategyPaperAccountAvailabilityError(
            f"availability_schema_columns_mismatch:{table}"
        )
    if not expected_unique_indexes.issubset(_unique_indexes(connection, table)):
        raise StrategyPaperAccountAvailabilityError(
            f"availability_schema_unique_index_missing:{table}"
        )


def _require_exact_account_custody(
    custody: PersonalStoreCustody,
    state_path: Path,
    identity: dict[str, str],
) -> None:
    route = custody.route
    if (
        route is None
        or custody.paths is None
        or route.domain is not PersonalStoreDomain.PAPER
        or route.mode is not PersonalStoreMode.PERSONAL
        or route.source_kind is not StoreSourceKind.PERSONAL
        or route.identity.key != identity["portfolio_id"]
        or route.paper_account_namespace != identity["account_namespace"]
        or route.write_target != route.read_source
    ):
        raise StrategyPaperAccountAvailabilityError("availability_exact_personal_route_required")
    try:
        selected_paths = PersonalPaperStorePaths.from_route(
            route, portfolio_id=identity["portfolio_id"]
        )
        if state_path != selected_paths.state_db:
            raise StrategyPaperAccountAvailabilityError(
                "availability_state_path_route_mismatch"
            )
        custody.sqlite_guard(state_path)
    except StrategyPaperAccountAvailabilityError:
        raise
    except (PersonalDataPathError, PersonalStoreRouteError, OSError, ValueError) as exc:
        raise StrategyPaperAccountAvailabilityError(
            "availability_exact_personal_route_required"
        ) from exc


def _read_bounded_json_text(
    connection: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    key_value: str,
    text_column: str,
    field: str,
) -> str:
    size_row = connection.execute(
        f'SELECT typeof("{text_column}"), length(CAST("{text_column}" AS BLOB)) '
        f'FROM "{table}" WHERE "{key_column}" = ?',
        (key_value,),
    ).fetchone()
    if size_row is None or size_row[0] != "text" or type(size_row[1]) is not int:
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    if size_row[1] > _MAX_BASE_JSON_BYTES:
        raise StrategyPaperAccountAvailabilityError(f"{field}_exceeds_size_limit")
    row = connection.execute(
        f'SELECT "{text_column}" FROM "{table}" WHERE "{key_column}" = ?',
        (key_value,),
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise StrategyPaperAccountAvailabilityError(f"{field}_invalid")
    return row[0]


def _identity(
    *,
    operation_id: str,
    snapshot_id: str,
    portfolio_id: str,
    account_namespace: str,
    binding_sha256: str,
    snapshot_sha256: str,
    base_receipt_sha256: str,
) -> dict[str, str]:
    return {
        "operation_id": _require_text(operation_id, "operation_id"),
        "snapshot_id": _require_text(snapshot_id, "snapshot_id"),
        "portfolio_id": _require_text(portfolio_id, "portfolio_id"),
        "account_namespace": _require_text(account_namespace, "account_namespace"),
        "binding_sha256": _require_hash(binding_sha256, "binding_sha256"),
        "snapshot_sha256": _require_hash(snapshot_sha256, "snapshot_sha256"),
        "base_receipt_sha256": _require_hash(
            base_receipt_sha256, "base_receipt_sha256"
        ),
    }


def _payload(
    identity: dict[str, str],
    persisted_at: datetime | None,
    available_at: datetime | None,
) -> dict[str, object]:
    return {
        "schema_version": AVAILABILITY_SCHEMA,
        **identity,
        "persisted_at": None if persisted_at is None else persisted_at.isoformat(),
        "available_at": None if available_at is None else available_at.isoformat(),
    }


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
            schema_version TEXT NOT NULL,
            snapshot_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL UNIQUE,
            portfolio_id TEXT NOT NULL,
            account_namespace TEXT NOT NULL,
            binding_sha256 TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            base_receipt_sha256 TEXT NOT NULL,
            persisted_at_utc TEXT,
            available_at_utc TEXT,
            receipt_json TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL
        )"""
    )
    columns = tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{_TABLE}")').fetchall()
    )
    if columns != _TABLE_COLUMNS:
        raise StrategyPaperAccountAvailabilityError(
            "availability_v1_schema_columns_mismatch"
        )


def _verify_base_checkpoint(
    connection: sqlite3.Connection,
    identity: dict[str, str],
) -> tuple[dict[str, object], datetime, datetime]:
    _require_table_contract(
        connection,
        "paper_portfolio_snapshots",
        _SNAPSHOT_COLUMNS,
        frozenset({("snapshot_id",)}),
    )
    _require_table_contract(
        connection,
        "paper_portfolio_positions",
        _POSITION_COLUMNS,
        frozenset({("snapshot_id", "stock_code")}),
    )
    _require_table_contract(
        connection,
        "paper_portfolio_snapshot_receipts",
        (
            "snapshot_id", "portfolio_id", "account_namespace", "binding_sha256",
            "receipt_json", "receipt_sha256",
        ),
        frozenset({("snapshot_id",)}),
    )
    _require_table_contract(
        connection,
        _OPERATION_TABLE,
        _OPERATION_COLUMNS,
        frozenset({("operation_id",), ("prior_snapshot_id",), ("snapshot_id",)}),
    )
    _require_table_contract(
        connection,
        _DAILY_RECEIPT_TABLE,
        _DAILY_RECEIPT_COLUMNS,
        frozenset({("snapshot_id",), ("operation_id",)}),
    )
    try:
        operation = connection.execute(
            "SELECT operation_id, portfolio_id, prior_snapshot_id, prior_snapshot_sha256, "
            "snapshot_id, snapshot_sha256, binding_sha256, operation_sha256, "
            "expected_ledger_rowset_hash, ledger_after_rowset_hash, "
            "ledger_operation_sha256, receipt_sha256, status "
            f"FROM {_OPERATION_TABLE} WHERE operation_id = ?",
            (identity["operation_id"],),
        ).fetchone()
        receipt = connection.execute(
            "SELECT operation_id, portfolio_id, account_namespace, binding_sha256, "
            "receipt_sha256 FROM "
            f"{_DAILY_RECEIPT_TABLE} "
            "WHERE snapshot_id = ?",
            (identity["snapshot_id"],),
        ).fetchone()
    except sqlite3.Error as exc:
        raise StrategyPaperAccountAvailabilityError(
            "availability_base_schema_unknown"
        ) from exc
    if operation is None or receipt is None:
        raise StrategyPaperAccountAvailabilityError("availability_base_receipt_missing")
    if (
        operation["status"] != "FINALIZED"
        or operation["operation_id"] != identity["operation_id"]
        or operation["portfolio_id"] != identity["portfolio_id"]
        or operation["prior_snapshot_id"] == identity["snapshot_id"]
        or operation["snapshot_id"] != identity["snapshot_id"]
        or operation["snapshot_sha256"] != identity["snapshot_sha256"]
        or operation["binding_sha256"] != identity["binding_sha256"]
        or operation["receipt_sha256"] != identity["base_receipt_sha256"]
        or not _HASH_PATTERN.fullmatch(str(operation["prior_snapshot_sha256"]))
        or not _HASH_PATTERN.fullmatch(str(operation["expected_ledger_rowset_hash"]))
        or not _HASH_PATTERN.fullmatch(str(operation["ledger_after_rowset_hash"]))
        or not _HASH_PATTERN.fullmatch(str(operation["ledger_operation_sha256"]))
        or receipt["operation_id"] != identity["operation_id"]
        or receipt["portfolio_id"] != identity["portfolio_id"]
        or receipt["account_namespace"] != identity["account_namespace"]
        or receipt["binding_sha256"] != identity["binding_sha256"]
        or receipt["receipt_sha256"] != identity["base_receipt_sha256"]
    ):
        raise StrategyPaperAccountAvailabilityError("availability_base_identity_mismatch")

    snapshot_row = connection.execute(
        "SELECT snapshot_id, portfolio_id, decision_date, source_result_id, cash, total_value "
        "FROM paper_portfolio_snapshots WHERE snapshot_id = ?",
        (identity["snapshot_id"],),
    ).fetchone()
    if snapshot_row is None:
        raise StrategyPaperAccountAvailabilityError("availability_snapshot_missing")
    position_rows = connection.execute(
        "SELECT stock_code, quantity, mark_price, market_value, weight_bp "
        "FROM paper_portfolio_positions WHERE snapshot_id = ? ORDER BY stock_code LIMIT ?",
        (identity["snapshot_id"], _MAX_ACCOUNT_POSITIONS + 1),
    ).fetchall()
    if len(position_rows) > _MAX_ACCOUNT_POSITIONS:
        raise StrategyPaperAccountAvailabilityError("availability_snapshot_position_limit_exceeded")

    snapshot_id = _require_text_value(snapshot_row["snapshot_id"], "availability_snapshot_id")
    portfolio_id = _require_text_value(
        snapshot_row["portfolio_id"], "availability_snapshot_portfolio_id"
    )
    decision_date = _require_text_value(
        snapshot_row["decision_date"], "availability_snapshot_decision_date"
    )
    try:
        parsed_date = date.fromisoformat(decision_date)
    except ValueError as exc:
        raise StrategyPaperAccountAvailabilityError(
            "availability_snapshot_decision_date_invalid"
        ) from exc
    if parsed_date.isoformat() != decision_date:
        raise StrategyPaperAccountAvailabilityError(
            "availability_snapshot_decision_date_invalid"
        )
    source_result_id = _require_text_value(
        snapshot_row["source_result_id"], "availability_snapshot_source_result_id"
    )
    cash = _require_money_text(snapshot_row["cash"], "availability_snapshot_cash")
    total_value = _require_money_text(
        snapshot_row["total_value"], "availability_snapshot_total_value"
    )
    positions_payload: list[dict[str, object]] = []
    snapshot_positions: list[PaperPortfolioPositionSnapshot] = []
    for position in position_rows:
        stock_code = _require_text_value(
            position["stock_code"], "availability_position_stock_code"
        )
        quantity = _require_sql_integer(
            position["quantity"], "availability_position_quantity", minimum=1
        )
        mark_price = _require_money_text(
            position["mark_price"], "availability_position_mark_price"
        )
        market_value = _require_money_text(
            position["market_value"], "availability_position_market_value"
        )
        weight_bp = _require_sql_integer(position["weight_bp"], "availability_position_weight_bp")
        if mark_price <= 0 or market_value <= 0 or weight_bp > 10_000:
            raise StrategyPaperAccountAvailabilityError("availability_position_value_invalid")
        positions_payload.append(
            {
                "stock_code": stock_code,
                "quantity": quantity,
                "mark_price": str(position["mark_price"]),
                "market_value": str(position["market_value"]),
                "weight_bp": weight_bp,
            }
        )
        snapshot_positions.append(
            PaperPortfolioPositionSnapshot(
                stock_code=stock_code,
                quantity=quantity,
                mark_price=mark_price,
                market_value=market_value,
                weight_bp=weight_bp,
            )
        )
    symbols = tuple(item.stock_code for item in snapshot_positions)
    if symbols != tuple(sorted(set(symbols))):
        raise StrategyPaperAccountAvailabilityError(
            "availability_snapshot_positions_not_unique_or_ordered"
        )
    if total_value <= 0:
        raise StrategyPaperAccountAvailabilityError("availability_snapshot_total_value_invalid")
    try:
        complete_snapshot = PaperPortfolioSnapshot(
            snapshot_id=snapshot_id,
            portfolio_id=portfolio_id,
            decision_date=decision_date,
            source_result_id=source_result_id,
            cash=cash,
            total_value=total_value,
            positions=tuple(snapshot_positions),
        )
        PortfolioResearchValuation.from_snapshot(complete_snapshot)
    except ValueError as exc:
        message = str(exc)
        if "weight differs" in message or "market_value differs" in message:
            code = "availability_snapshot_position_reconciliation_mismatch"
        elif "NAV must equal" in message:
            code = "availability_snapshot_value_reconciliation_mismatch"
        else:
            code = "availability_snapshot_value_reconciliation_invalid"
        raise StrategyPaperAccountAvailabilityError(code) from exc
    persisted_snapshot_payload = {
        "snapshot_id": snapshot_id,
        "portfolio_id": portfolio_id,
        "decision_date": decision_date,
        "source_result_id": source_result_id,
        "cash": str(snapshot_row["cash"]),
        "total_value": str(snapshot_row["total_value"]),
        "positions": positions_payload,
    }
    if (
        portfolio_id != identity["portfolio_id"]
        or snapshot_id != identity["snapshot_id"]
        or _sha256(persisted_snapshot_payload) != identity["snapshot_sha256"]
    ):
        raise StrategyPaperAccountAvailabilityError("availability_snapshot_hash_mismatch")

    raw_operation = _read_bounded_json_text(
        connection,
        table=_OPERATION_TABLE,
        key_column="operation_id",
        key_value=identity["operation_id"],
        text_column="operation_json",
        field="availability_base_operation",
    )
    operation_payload = _require_fields(
        _parse_json_object(raw_operation, "base_operation"),
        _OPERATION_FIELDS,
        "availability_base_operation",
    )
    if _sha256(operation_payload) != operation["operation_sha256"]:
        raise StrategyPaperAccountAvailabilityError("availability_base_operation_hash_mismatch")
    snapshot_payload = _require_fields(
        operation_payload.get("snapshot"), _SNAPSHOT_FIELDS, "availability_operation_snapshot"
    )
    if snapshot_payload != persisted_snapshot_payload:
        raise StrategyPaperAccountAvailabilityError("availability_base_operation_mismatch")
    saved_execution = _require_fields(
        operation_payload.get("saved_execution"),
        _SAVED_EXECUTION_FIELDS,
        "availability_saved_execution",
    )
    for field in (
        "raw_artifact_sha256", "payload_hash", "strategy_config_hash",
        "strategy_config_content_sha256",
    ):
        _require_hash_value(saved_execution.get(field), f"availability_saved_execution_{field}")
    if (
        saved_execution.get("result_id") != operation_payload.get("result_id")
        or saved_execution.get("strategy_version_id")
        != operation_payload.get("strategy_version_id")
    ):
        raise StrategyPaperAccountAvailabilityError("availability_saved_execution_identity_mismatch")

    for field in (
        "binding_sha256", "strategy_config_sha256", "policy_sha256",
        "cost_model_sha256", "benchmark_sha256", "prior_snapshot_sha256",
        "prior_receipt_sha256", "snapshot_sha256",
    ):
        _require_hash_value(operation_payload.get(field), f"availability_operation_{field}")
    for field in ("operation_id", "portfolio_id", "account_namespace", "strategy_id", "strategy_version_id", "result_id", "prior_snapshot_id", "execution_date", "forward_qualification"):
        _require_text_value(operation_payload.get(field), f"availability_operation_{field}")
    if (
        operation_payload.get("schema_version") != "strategy-paper-account-daily-operation.v1"
        or operation_payload.get("operation_id") != identity["operation_id"]
        or operation_payload.get("portfolio_id") != identity["portfolio_id"]
        or operation_payload.get("account_namespace") != identity["account_namespace"]
        or operation_payload.get("binding_sha256") != identity["binding_sha256"]
        or operation_payload.get("snapshot_sha256") != identity["snapshot_sha256"]
        or operation_payload.get("prior_snapshot_id") != operation["prior_snapshot_id"]
        or operation_payload.get("prior_snapshot_sha256")
        != operation["prior_snapshot_sha256"]
        or operation_payload.get("expected_ledger_rowset_hash")
        != operation["expected_ledger_rowset_hash"]
        or operation_payload.get("prior_snapshot_id") == identity["snapshot_id"]
        or operation_payload.get("performance_eligible") is not False
        or operation_payload.get("research_only") is not True
        or operation_payload.get("broker_order_allowed") is not False
        or operation_payload.get("auto_rebalance_allowed") is not False
    ):
        raise StrategyPaperAccountAvailabilityError("availability_base_operation_mismatch")

    fills = operation_payload.get("fills")
    ordered_fill_ids = operation_payload.get("ordered_fill_ids")
    if (
        not isinstance(fills, list)
        or len(fills) > _MAX_DAILY_FILLS
        or not isinstance(ordered_fill_ids, list)
        or len(ordered_fill_ids) != len(fills)
        or any(not isinstance(fill_id, str) or not fill_id.strip() for fill_id in ordered_fill_ids)
    ):
        raise StrategyPaperAccountAvailabilityError("availability_operation_fills_invalid")
    for index, fill in enumerate(fills):
        fill_payload = _require_fields(fill, _FILL_FIELDS, "availability_operation_fill")
        if (
            fill_payload.get("schema_version") != "paper-trade-ledger.v1"
            or fill_payload.get("fill_id") != ordered_fill_ids[index]
            or fill_payload.get("portfolio_id") != identity["portfolio_id"]
            or fill_payload.get("research_only") is not True
            or fill_payload.get("broker_order_allowed") is not False
            or fill_payload.get("auto_rebalance_allowed") is not False
        ):
            raise StrategyPaperAccountAvailabilityError("availability_operation_fill_mismatch")
    transition_payload = operation_payload.get("transition")
    if transition_payload is not None:
        transition_payload = _require_fields(
            transition_payload, _TRANSITION_FIELDS, "availability_operation_transition"
        )
        if (
            transition_payload.get("schema_version") != "paper-trade-transition.v1"
            or transition_payload.get("portfolio_id") != identity["portfolio_id"]
            or transition_payload.get("fill_ids") != ordered_fill_ids
            or transition_payload.get("research_only") is not True
            or transition_payload.get("broker_order_allowed") is not False
            or transition_payload.get("auto_rebalance_allowed") is not False
        ):
            raise StrategyPaperAccountAvailabilityError("availability_operation_transition_mismatch")
    if (len(fills) == 0) != (transition_payload is None):
        raise StrategyPaperAccountAvailabilityError("availability_operation_transition_mismatch")
    for name in ("mark_prices", "execution_prices"):
        evidence = operation_payload.get(name)
        if not isinstance(evidence, list) or len(evidence) > _MAX_DAILY_FILLS * 2:
            raise StrategyPaperAccountAvailabilityError(f"availability_operation_{name}_invalid")
        for row_payload in evidence:
            _require_fields(row_payload, _PRICE_EVIDENCE_FIELDS, f"availability_operation_{name}_row")
    quotes = operation_payload.get("quote_event_receipts")
    if not isinstance(quotes, list) or len(quotes) > _MAX_DAILY_FILLS:
        raise StrategyPaperAccountAvailabilityError("availability_operation_quote_receipts_invalid")
    for quote_payload in quotes:
        _require_fields(quote_payload, _QUOTE_EVENT_FIELDS, "availability_operation_quote_receipt")

    raw_receipt = _read_bounded_json_text(
        connection,
        table=_DAILY_RECEIPT_TABLE,
        key_column="snapshot_id",
        key_value=identity["snapshot_id"],
        text_column="receipt_json",
        field="availability_base_receipt",
    )
    receipt_payload = _require_fields(
        _parse_json_object(raw_receipt, "base_receipt"),
        _DAILY_RECEIPT_FIELDS,
        "availability_base_receipt",
    )
    if _sha256(receipt_payload) != identity["base_receipt_sha256"]:
        raise StrategyPaperAccountAvailabilityError("availability_base_receipt_hash_mismatch")
    if (
        receipt_payload.get("schema_version") != "strategy-paper-account-daily-receipt.v1"
        or receipt_payload.get("operation_id") != identity["operation_id"]
        or receipt_payload.get("operation_sha256") != operation["operation_sha256"]
        or receipt_payload.get("snapshot_id") != identity["snapshot_id"]
        or receipt_payload.get("snapshot_sha256") != identity["snapshot_sha256"]
        or receipt_payload.get("portfolio_id") != identity["portfolio_id"]
        or receipt_payload.get("account_namespace") != identity["account_namespace"]
        or receipt_payload.get("binding_sha256") != identity["binding_sha256"]
        or receipt_payload.get("prior_snapshot_id") != operation_payload.get("prior_snapshot_id")
        or receipt_payload.get("prior_snapshot_sha256") != operation_payload.get("prior_snapshot_sha256")
        or receipt_payload.get("prior_receipt_sha256") != operation_payload.get("prior_receipt_sha256")
        or receipt_payload.get("result_id") != operation_payload.get("result_id")
        or receipt_payload.get("saved_execution") != saved_execution
        or receipt_payload.get("decision_cutoff") != operation_payload.get("decision_cutoff")
        or receipt_payload.get("execution_date") != operation_payload.get("execution_date")
        or receipt_payload.get("mark_cutoff") != operation_payload.get("mark_cutoff")
        or receipt_payload.get("ordered_fill_ids") != ordered_fill_ids
        or receipt_payload.get("fill_batch_sha256") != _sha256(fills)
        or receipt_payload.get("transition_sha256")
        != (None if transition_payload is None else _sha256(transition_payload))
        or receipt_payload.get("ledger_rowset_hash_before")
        != operation["expected_ledger_rowset_hash"]
        or receipt_payload.get("ledger_rowset_hash_after")
        != operation["ledger_after_rowset_hash"]
        or receipt_payload.get("ledger_operation_sha256")
        != operation["ledger_operation_sha256"]
        or receipt_payload.get("zero_fill") is not (len(fills) == 0)
        or receipt_payload.get("performance_eligible") is not False
        or receipt_payload.get("research_only") is not True
        or receipt_payload.get("broker_order_allowed") is not False
        or receipt_payload.get("auto_rebalance_allowed") is not False
    ):
        raise StrategyPaperAccountAvailabilityError("availability_base_receipt_mismatch")
    decision_cutoff = _parse_aware_utc(
        receipt_payload.get("decision_cutoff"), "base_decision_cutoff"
    )
    mark_cutoff = _parse_aware_utc(receipt_payload.get("mark_cutoff"), "base_mark_cutoff")
    if mark_cutoff < decision_cutoff:
        raise StrategyPaperAccountAvailabilityError("availability_base_cutoff_order_invalid")
    if (
        _parse_aware_utc(operation_payload.get("decision_cutoff"), "operation_decision_cutoff")
        != decision_cutoff
        or _parse_aware_utc(operation_payload.get("mark_cutoff"), "operation_mark_cutoff")
        != mark_cutoff
    ):
        raise StrategyPaperAccountAvailabilityError("availability_base_cutoff_mismatch")
    return receipt_payload, decision_cutoff, mark_cutoff


def _stage_clocks(
    row: sqlite3.Row,
    *,
    identity: dict[str, str],
) -> tuple[datetime | None, datetime | None]:
    raw_persisted = row["persisted_at_utc"]
    raw_available = row["available_at_utc"]
    persisted_at = (
        None
        if raw_persisted is None
        else _parse_aware_utc(raw_persisted, "availability_persisted_clock")
    )
    available_at = (
        None
        if raw_available is None
        else _parse_aware_utc(raw_available, "availability_available_clock")
    )
    if available_at is not None and persisted_at is None:
        raise StrategyPaperAccountAvailabilityError("availability_clock_order_invalid")
    if persisted_at is not None and available_at is not None and available_at < persisted_at:
        raise StrategyPaperAccountAvailabilityError("availability_clock_order_invalid")
    payload = _payload(identity, persisted_at, available_at)
    raw_payload = _parse_json_object(row["receipt_json"], "availability_receipt")
    if (
        row["schema_version"] != AVAILABILITY_SCHEMA
        or raw_payload != payload
        or _sha256(raw_payload) != row["receipt_sha256"]
        or row["snapshot_id"] != identity["snapshot_id"]
        or row["operation_id"] != identity["operation_id"]
        or row["portfolio_id"] != identity["portfolio_id"]
        or row["account_namespace"] != identity["account_namespace"]
        or row["binding_sha256"] != identity["binding_sha256"]
        or row["snapshot_sha256"] != identity["snapshot_sha256"]
        or row["base_receipt_sha256"] != identity["base_receipt_sha256"]
    ):
        raise StrategyPaperAccountAvailabilityError("availability_receipt_mismatch")
    return persisted_at, available_at


def _select_stage_row(
    connection: sqlite3.Connection,
    identity: dict[str, str],
) -> sqlite3.Row | None:
    return connection.execute(
        f"SELECT * FROM {_TABLE} WHERE snapshot_id = ?",
        (identity["snapshot_id"],),
    ).fetchone()


def _ensure_readable_table(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (_TABLE,),
    ).fetchone()
    if table_exists is None:
        raise StrategyPaperAccountAvailabilityError("availability_clock_unknown")
    _require_table_contract(
        connection,
        _TABLE,
        _TABLE_COLUMNS,
        frozenset({("snapshot_id",), ("operation_id",)}),
    )


def _read_stage(
    custody: PersonalStoreCustody,
    state_path: Path,
    identity: dict[str, str],
) -> tuple[datetime | None, datetime | None, datetime, datetime]:
    _require_exact_account_custody(custody, state_path, identity)
    try:
        with custody.read_sqlite(state_path) as connection:
            try:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or int(query_only[0]) != 1:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_reader_not_read_only"
                    )
                connection.execute("BEGIN")
                _ensure_readable_table(connection)
                _, decision_cutoff, mark_cutoff = _verify_base_checkpoint(
                    connection, identity
                )
                row = _select_stage_row(connection, identity)
                if row is None:
                    raise StrategyPaperAccountAvailabilityError("availability_clock_unknown")
                persisted_at, available_at = _stage_clocks(row, identity=identity)
                return persisted_at, available_at, decision_cutoff, mark_cutoff
            finally:
                if connection.in_transaction:
                    connection.rollback()
    except sqlite3.Error as exc:
        raise StrategyPaperAccountAvailabilityError(
            "availability_reader_failed"
        ) from exc


def read_exact_strategy_paper_account_availability(
    custody: PersonalStoreCustody,
    state_path: Path,
    *,
    operation_id: str,
    snapshot_id: str,
    portfolio_id: str,
    account_namespace: str,
    binding_sha256: str,
    snapshot_sha256: str,
    base_receipt_sha256: str,
    decision_cutoff: datetime,
) -> StrategyPaperAccountAvailability:
    """驗證完整 snapshot、base receipt 與 intent cutoff 的 clock。"""

    identity = _identity(
        operation_id=operation_id,
        snapshot_id=snapshot_id,
        portfolio_id=portfolio_id,
        account_namespace=account_namespace,
        binding_sha256=binding_sha256,
        snapshot_sha256=snapshot_sha256,
        base_receipt_sha256=base_receipt_sha256,
    )
    _require_exact_account_custody(custody, state_path, identity)
    cutoff = _parse_aware_utc(decision_cutoff, "availability_decision_cutoff")
    try:
        with custody.read_sqlite(state_path) as connection:
            try:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or int(query_only[0]) != 1:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_reader_not_read_only"
                    )
                connection.execute("BEGIN")
                _ensure_readable_table(connection)
                receipt_payload, base_decision_cutoff, mark_cutoff = _verify_base_checkpoint(
                    connection, identity
                )
                if cutoff < base_decision_cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_decision_before_checkpoint_cutoff"
                    )
                if cutoff > _parse_aware_utc(
                    _utc_now(), "availability_reader_observation_clock"
                ):
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_decision_cutoff_in_future"
                    )
                row = _select_stage_row(connection, identity)
                if row is None:
                    raise StrategyPaperAccountAvailabilityError("availability_clock_unknown")
                persisted_at, available_at = _stage_clocks(row, identity=identity)
                if persisted_at is None or available_at is None:
                    raise StrategyPaperAccountAvailabilityError("availability_clock_unknown")
                if persisted_at < base_decision_cutoff or persisted_at < mark_cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_persisted_clock_before_base_cutoff"
                    )
                if available_at < persisted_at:
                    raise StrategyPaperAccountAvailabilityError("availability_clock_order_invalid")
                if available_at > cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_after_decision_cutoff"
                    )
                if receipt_payload.get("snapshot_sha256") != identity["snapshot_sha256"]:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_base_snapshot_mismatch"
                    )
                return StrategyPaperAccountAvailability(
                    schema_version=AVAILABILITY_SCHEMA,
                    operation_id=identity["operation_id"],
                    snapshot_id=identity["snapshot_id"],
                    portfolio_id=identity["portfolio_id"],
                    account_namespace=identity["account_namespace"],
                    binding_sha256=identity["binding_sha256"],
                    snapshot_sha256=identity["snapshot_sha256"],
                    base_receipt_sha256=identity["base_receipt_sha256"],
                    persisted_at=persisted_at,
                    available_at=available_at,
                    receipt_sha256=str(row["receipt_sha256"]),
                )
            finally:
                if connection.in_transaction:
                    connection.rollback()
    except sqlite3.Error as exc:
        raise StrategyPaperAccountAvailabilityError(
            "availability_reader_failed"
        ) from exc


def read_exact_strategy_paper_account_checkpoint(
    account_service: StrategyPaperAccountService,
    *,
    strategy_id: str,
    strategy_version_id: str,
    account_namespace: str,
    operation_id: str,
    snapshot_id: str,
    decision_cutoff: datetime,
    allocation_decision_date: str | None = None,
) -> StrategyPaperAccountCheckpointRead:
    """從 exact account 讀回同份 snapshot/clock，並核對實際 ledger append。"""

    selected = account_service.select_exact_version(
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
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_read_exact_binding_unavailable:{reason}"
        )
    binding = selected.binding
    route = selected.route
    if (
        binding.strategy_id != strategy_id
        or binding.strategy_version_id != strategy_version_id
        or binding.account_namespace != account_namespace
        or route.identity.key != binding.portfolio_id
        or route.paper_account_namespace != binding.account_namespace
    ):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_exact_binding_mismatch"
        )
    store_paths = PersonalPaperStorePaths.from_route(
        route, portfolio_id=binding.portfolio_id
    )
    custody = PersonalStoreCustody(route, account_service.personal_paths)
    identity: dict[str, str]
    operation_record: sqlite3.Row
    snapshot: PaperPortfolioSnapshot
    availability: StrategyPaperAccountAvailability
    operation_payload: dict[str, object]
    cutoff = _parse_aware_utc(decision_cutoff, "checkpoint_read_decision_cutoff")

    try:
        with custody.read_sqlite(store_paths.state_db) as connection:
            try:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or int(query_only[0]) != 1:
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_state_not_read_only"
                    )
                connection.execute("BEGIN")
                _ensure_readable_table(connection)
                row = connection.execute(
                    "SELECT operation_id, portfolio_id, snapshot_id, snapshot_sha256, "
                    "binding_sha256, operation_sha256, expected_ledger_rowset_hash, "
                    "ledger_after_rowset_hash, ledger_operation_sha256, receipt_sha256 "
                    f"FROM {_OPERATION_TABLE} WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
                if row is None:
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_operation_missing"
                    )
                operation_record = row
                receipt_sha256 = _require_hash_value(
                    row["receipt_sha256"], "checkpoint_read_base_receipt_sha256"
                )
                identity = _identity(
                    operation_id=operation_id,
                    snapshot_id=snapshot_id,
                    portfolio_id=binding.portfolio_id,
                    account_namespace=binding.account_namespace,
                    binding_sha256=binding.binding_sha256,
                    snapshot_sha256=_require_hash_value(
                        row["snapshot_sha256"], "checkpoint_read_snapshot_sha256"
                    ),
                    base_receipt_sha256=receipt_sha256,
                )
                receipt_payload, base_decision_cutoff, mark_cutoff = (
                    _verify_base_checkpoint(connection, identity)
                )
                if cutoff < base_decision_cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_decision_before_base_cutoff"
                    )
                if cutoff > _parse_aware_utc(
                    _utc_now(), "checkpoint_read_observation_clock"
                ):
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_decision_cutoff_in_future"
                    )
                stage_row = _select_stage_row(connection, identity)
                if stage_row is None:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_clock_unknown"
                    )
                persisted_at, available_at = _stage_clocks(
                    stage_row, identity=identity
                )
                if persisted_at is None or available_at is None:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_clock_unknown"
                    )
                if persisted_at < base_decision_cutoff or persisted_at < mark_cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_persisted_clock_before_base_cutoff"
                    )
                if available_at > cutoff:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_after_decision_cutoff"
                    )
                availability = StrategyPaperAccountAvailability(
                    schema_version=AVAILABILITY_SCHEMA,
                    operation_id=identity["operation_id"],
                    snapshot_id=identity["snapshot_id"],
                    portfolio_id=identity["portfolio_id"],
                    account_namespace=identity["account_namespace"],
                    binding_sha256=identity["binding_sha256"],
                    snapshot_sha256=identity["snapshot_sha256"],
                    base_receipt_sha256=identity["base_receipt_sha256"],
                    persisted_at=persisted_at,
                    available_at=available_at,
                    receipt_sha256=_require_hash_value(
                        stage_row["receipt_sha256"],
                        "checkpoint_read_availability_receipt_sha256",
                    ),
                )
                snapshot_row = connection.execute(
                    "SELECT snapshot_id, portfolio_id, decision_date, source_result_id, "
                    "cash, total_value FROM paper_portfolio_snapshots "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if snapshot_row is None:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_snapshot_missing"
                    )
                position_rows = connection.execute(
                    "SELECT stock_code, quantity, mark_price, market_value, weight_bp "
                    "FROM paper_portfolio_positions WHERE snapshot_id = ? "
                    "ORDER BY stock_code",
                    (snapshot_id,),
                ).fetchall()
                snapshot = PaperPortfolioSnapshot(
                    snapshot_id=_require_text_value(
                        snapshot_row["snapshot_id"], "checkpoint_read_snapshot_id"
                    ),
                    portfolio_id=_require_text_value(
                        snapshot_row["portfolio_id"], "checkpoint_read_portfolio_id"
                    ),
                    decision_date=_require_text_value(
                        snapshot_row["decision_date"], "checkpoint_read_decision_date"
                    ),
                    source_result_id=_require_text_value(
                        snapshot_row["source_result_id"],
                        "checkpoint_read_source_result_id",
                    ),
                    cash=_require_money_text(
                        snapshot_row["cash"], "checkpoint_read_cash"
                    ),
                    total_value=_require_money_text(
                        snapshot_row["total_value"], "checkpoint_read_total_value"
                    ),
                    positions=tuple(
                        PaperPortfolioPositionSnapshot(
                            stock_code=_require_text_value(
                                item["stock_code"], "checkpoint_read_stock_code"
                            ),
                            quantity=_require_sql_integer(
                                item["quantity"],
                                "checkpoint_read_quantity",
                                minimum=1,
                            ),
                            mark_price=_require_money_text(
                                item["mark_price"], "checkpoint_read_mark_price"
                            ),
                            market_value=_require_money_text(
                                item["market_value"],
                                "checkpoint_read_market_value",
                            ),
                            weight_bp=_require_sql_integer(
                                item["weight_bp"], "checkpoint_read_weight_bp"
                            ),
                        )
                        for item in position_rows
                    ),
                )
                try:
                    PortfolioResearchValuation.from_snapshot(snapshot)
                except ValueError as exc:
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_snapshot_valuation_invalid"
                    ) from exc
                raw_operation = _read_bounded_json_text(
                    connection,
                    table=_OPERATION_TABLE,
                    key_column="operation_id",
                    key_value=operation_id,
                    text_column="operation_json",
                    field="checkpoint_read_operation",
                )
                operation_payload = _require_fields(
                    _parse_json_object(raw_operation, "checkpoint_read_operation"),
                    _OPERATION_FIELDS,
                    "checkpoint_read_operation",
                )
                if _sha256(operation_payload) != operation_record["operation_sha256"]:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_base_operation_hash_mismatch"
                    )
                if (
                    operation_payload.get("strategy_id") != binding.strategy_id
                    or operation_payload.get("strategy_version_id")
                    != binding.strategy_version_id
                    or operation_payload.get("strategy_config_sha256")
                    != binding.config_sha256
                    or operation_payload.get("policy_sha256") != binding.policy_sha256
                    or operation_payload.get("cost_model_sha256")
                    != binding.cost_model_sha256
                    or operation_payload.get("benchmark_sha256")
                    != binding.benchmark_sha256
                    or receipt_payload.get("snapshot_sha256")
                    != identity["snapshot_sha256"]
                    or row["operation_id"] != identity["operation_id"]
                    or row["snapshot_id"] != identity["snapshot_id"]
                ):
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_read_operation_binding_mismatch"
                    )
            finally:
                if connection.in_transaction:
                    connection.rollback()
    except sqlite3.Error as exc:
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_state_failed"
        ) from exc

    operation_fills = operation_payload.get("fills")
    ordered_ids = operation_payload.get("ordered_fill_ids")
    if not isinstance(operation_fills, list) or not isinstance(ordered_ids, list):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_operation_fills_invalid"
        )
    execution_date = _require_text_value(
        operation_payload.get("execution_date"), "checkpoint_read_execution_date"
    )
    try:
        ledger = PaperTradeLedgerRepository(
            store_paths.cost_ledger_db,
            route=route,
            personal_paths=account_service.personal_paths,
            portfolio_id=binding.portfolio_id,
            read_only=True,
        )
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as exc:
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_ledger_unavailable"
        ) from exc
    ledger_read = _read_exact_ledger_operation(
        ledger,
        operation_id=operation_id,
        portfolio_id=binding.portfolio_id,
        event_date=execution_date,
        allocation_decision_date=allocation_decision_date,
    )
    marker = ledger_read.marker
    day_fills = ledger_read.ordered_fills
    transition = ledger_read.transition

    ordered_fill_ids = tuple(
        _require_text_value(item, "checkpoint_read_ordered_fill_id")
        for item in ordered_ids
    )
    fills_by_id = {item.fill_id: item for item in day_fills}
    if (
        len(fills_by_id) != len(day_fills)
        or set(fills_by_id) != set(ordered_fill_ids)
        or marker.ordered_fill_ids != ordered_fill_ids
        or marker.expected_rowset_hash != operation_record["expected_ledger_rowset_hash"]
        or marker.rowset_hash_after != operation_record["ledger_after_rowset_hash"]
        or ledger_read.rowset_hash_before
        != operation_record["expected_ledger_rowset_hash"]
        or ledger_read.rowset_hash_after != operation_record["ledger_after_rowset_hash"]
        or marker.operation_sha256 != operation_record["ledger_operation_sha256"]
        or marker.zero_fill is not (len(ordered_fill_ids) == 0)
    ):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_ledger_operation_mismatch"
        )
    ordered_fills = tuple(fills_by_id[fill_id] for fill_id in ordered_fill_ids)
    with localcontext(Context(prec=60)):
        actual_fill_payloads = [fill.to_dict() for fill in ordered_fills]
    if (
        actual_fill_payloads != operation_fills
        or marker.fill_batch_sha256 != _sha256(operation_fills)
    ):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_ledger_fills_mismatch"
        )
    raw_transition = operation_payload.get("transition")
    if raw_transition is None:
        if transition is not None or marker.transition_id is not None:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_ledger_transition_mismatch"
            )
    else:
        if transition is None or transition.to_dict() != raw_transition:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_read_ledger_transition_mismatch"
            )
    if (
        marker.transition_id != (None if transition is None else transition.transition_id)
        or marker.transition_sha256
        != (None if raw_transition is None else _sha256(raw_transition))
    ):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_read_ledger_transition_mismatch"
        )
    mark_prices = operation_payload.get("mark_prices")
    if not isinstance(mark_prices, list):
        raise StrategyPaperAccountAvailabilityError("checkpoint_read_mark_evidence_invalid")
    return StrategyPaperAccountCheckpointRead(
        binding=binding,
        snapshot=snapshot,
        availability=availability,
        operation_sha256=_require_hash_value(
            operation_record["operation_sha256"], "checkpoint_read_operation_sha256"
        ),
        ledger_operation=marker,
        ordered_fills=ordered_fills,
        transition=transition,
        mark_price_evidence_json=tuple(_canonical_json(row) for row in mark_prices),
        allocation_decision_date=ledger_read.allocation_decision_date,
        allocation_prefix_fills=ledger_read.allocation_prefix_fills,
        allocation_prefix_transitions=ledger_read.allocation_prefix_transitions,
        allocation_prefix_rowset_hash=ledger_read.allocation_prefix_rowset_hash,
    )


def _commit_clock(
    custody: PersonalStoreCustody,
    state_path: Path,
    identity: dict[str, str],
    *,
    field: str,
) -> None:
    if field not in {"persisted_at", "available_at"}:
        raise StrategyPaperAccountAvailabilityError("availability_clock_field_invalid")
    _require_exact_account_custody(custody, state_path, identity)
    # 時鐘只由 writer 在前一筆已提交狀態讀回後取得，呼叫端不能指定時間。
    selected_clock = _parse_aware_utc(_utc_now(), f"availability_{field}")
    custody.sqlite_guard(state_path)
    connection = sqlite3.connect(custody.io(state_path), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_table(connection)
        _, decision_cutoff, mark_cutoff = _verify_base_checkpoint(connection, identity)
        row = _select_stage_row(connection, identity)
        if row is None:
            raise StrategyPaperAccountAvailabilityError("availability_clock_unknown")
        persisted_at, available_at = _stage_clocks(row, identity=identity)
        if field == "persisted_at":
            if persisted_at is None:
                if available_at is not None:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_clock_order_invalid"
                    )
                next_persisted = selected_clock
                next_available = None
            else:
                next_persisted = persisted_at
                next_available = available_at
        else:
            if persisted_at is None:
                raise StrategyPaperAccountAvailabilityError(
                    "availability_persisted_clock_unknown"
                )
            if available_at is None:
                if selected_clock < persisted_at:
                    raise StrategyPaperAccountAvailabilityError(
                        "availability_clock_order_invalid"
                    )
                next_persisted = persisted_at
                next_available = selected_clock
            else:
                next_persisted = persisted_at
                next_available = available_at
        if next_persisted < decision_cutoff or next_persisted < mark_cutoff:
            raise StrategyPaperAccountAvailabilityError(
                "availability_persisted_clock_before_base_cutoff"
            )
        if next_available is not None and next_available < next_persisted:
            raise StrategyPaperAccountAvailabilityError("availability_clock_order_invalid")
        payload = _payload(identity, next_persisted, next_available)
        digest = _sha256(payload)
        connection.execute(
            f"UPDATE {_TABLE} SET persisted_at_utc=?, available_at_utc=?, "
            "receipt_json=?, receipt_sha256=? WHERE snapshot_id=?",
            (
                None if next_persisted is None else next_persisted.isoformat(),
                None if next_available is None else next_available.isoformat(),
                _canonical_json(payload),
                digest,
                identity["snapshot_id"],
            ),
        )
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StrategyPaperAccountAvailabilityError(
            "availability_writer_failed"
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _record_newly_finalized_strategy_paper_account_availability(
    custody: PersonalStoreCustody,
    state_path: Path,
    *,
    operation_id: str,
    snapshot_id: str,
    portfolio_id: str,
    account_namespace: str,
    binding_sha256: str,
    snapshot_sha256: str,
    base_receipt_sha256: str,
) -> tuple[StrategyPaperAccountAvailability, datetime]:
    """只供 daily writer 在本次 finalize/讀回後追加；不提供舊資料補鐘 API。"""

    identity = _identity(
        operation_id=operation_id,
        snapshot_id=snapshot_id,
        portfolio_id=portfolio_id,
        account_namespace=account_namespace,
        binding_sha256=binding_sha256,
        snapshot_sha256=snapshot_sha256,
        base_receipt_sha256=base_receipt_sha256,
    )
    _require_exact_account_custody(custody, state_path, identity)
    custody.sqlite_guard(state_path)
    connection = sqlite3.connect(custody.io(state_path), timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_table(connection)
        _verify_base_checkpoint(connection, identity)
        row = _select_stage_row(connection, identity)
        if row is None:
            payload = _payload(identity, None, None)
            connection.execute(
                f"""INSERT INTO {_TABLE} (
                    schema_version, snapshot_id, operation_id, portfolio_id,
                    account_namespace, binding_sha256, snapshot_sha256,
                    base_receipt_sha256, persisted_at_utc, available_at_utc,
                    receipt_json, receipt_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                (
                    AVAILABILITY_SCHEMA,
                    identity["snapshot_id"],
                    identity["operation_id"],
                    identity["portfolio_id"],
                    identity["account_namespace"],
                    identity["binding_sha256"],
                    identity["snapshot_sha256"],
                    identity["base_receipt_sha256"],
                    _canonical_json(payload),
                    _sha256(payload),
                ),
            )
        else:
            _stage_clocks(row, identity=identity)
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise StrategyPaperAccountAvailabilityError(
            "availability_writer_failed"
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    persisted_at, _, _, _ = _read_stage(custody, state_path, identity)
    if persisted_at is None:
        _commit_clock(
            custody,
            state_path,
            identity,
            field="persisted_at",
        )

    persisted_at, available_at, _, _ = _read_stage(custody, state_path, identity)
    if persisted_at is None:
        raise StrategyPaperAccountAvailabilityError("availability_persisted_clock_unknown")
    if available_at is None:
        _commit_clock(
            custody,
            state_path,
            identity,
            field="available_at",
        )

    # final reader closure uses a fresh writer clock; exact prior readers pass their own intent cutoff.
    closure_cutoff = _parse_aware_utc(_utc_now(), "availability_closure_clock")
    receipt = read_exact_strategy_paper_account_availability(
        custody,
        state_path,
        operation_id=identity["operation_id"],
        snapshot_id=identity["snapshot_id"],
        portfolio_id=identity["portfolio_id"],
        account_namespace=identity["account_namespace"],
        binding_sha256=identity["binding_sha256"],
        snapshot_sha256=identity["snapshot_sha256"],
        base_receipt_sha256=identity["base_receipt_sha256"],
        decision_cutoff=closure_cutoff,
    )
    return receipt, closure_cutoff


__all__ = [
    "AVAILABILITY_SCHEMA",
    "StrategyPaperAccountAvailability",
    "StrategyPaperAccountAvailabilityError",
    "StrategyPaperAccountCheckpointRead",
    "read_exact_strategy_paper_account_availability",
    "read_exact_strategy_paper_account_checkpoint",
]

# P08a 候選清單只支援尋找 exact reader 的輸入，不是 checkpoint 驗證結果。
CHECKPOINT_CATALOGUE_SCHEMA = "strategy-paper-account-checkpoint-catalogue.v1"
_MAX_CHECKPOINT_CATALOGUE_ROWS = 200
_CHECKPOINT_CATALOGUE_LOOKAHEAD = _MAX_CHECKPOINT_CATALOGUE_ROWS + 1
_MAX_CHECKPOINT_CATALOGUE_TEXT_BYTES = 512
_CATALOGUE_TEXT_FIELDS = (
    "schema_version",
    "snapshot_id",
    "operation_id",
    "portfolio_id",
    "account_namespace",
    "binding_sha256",
    "snapshot_sha256",
    "base_receipt_sha256",
    "persisted_at_utc",
    "available_at_utc",
    "receipt_sha256",
)
_CATALOGUE_NULLABLE_TEXT_FIELDS = frozenset({"persisted_at_utc", "available_at_utc"})


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountCheckpointCandidate:
    """供呼叫端送入既有 exact reader 的未驗證 identity 與 clock 摘要。"""

    operation_id: str
    snapshot_id: str
    observed_schema_version: str
    observed_portfolio_id: str
    observed_account_namespace: str
    observed_binding_sha256: str
    observed_snapshot_sha256: str
    observed_base_receipt_sha256: str
    observed_availability_receipt_sha256: str
    persisted_at_text: str | None
    available_at_text: str | None
    persisted_at: datetime | None
    available_at: datetime | None
    row_state: str
    blockers: tuple[str, ...]
    exact_reader_required: bool = True
    checkpoint_verified: bool = False
    performance_eligible: bool = False

    def __post_init__(self) -> None:
        _require_text(self.operation_id, "checkpoint_catalogue_operation_id")
        _require_text(self.snapshot_id, "checkpoint_catalogue_snapshot_id")
        if self.row_state not in {
            "candidate_pending_exact_reader",
            "blocked",
        }:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_row_state_invalid"
            )
        for field_name in (
            "observed_schema_version", "observed_portfolio_id",
            "observed_account_namespace", "observed_binding_sha256",
            "observed_snapshot_sha256", "observed_base_receipt_sha256",
            "observed_availability_receipt_sha256",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise StrategyPaperAccountAvailabilityError(
                    f"checkpoint_catalogue_{field_name}_invalid"
                )
            if self.row_state == "candidate_pending_exact_reader":
                _require_text(value, f"checkpoint_catalogue_{field_name}")
        for field_name in ("persisted_at_text", "available_at_text"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise StrategyPaperAccountAvailabilityError(
                    f"checkpoint_catalogue_{field_name}_invalid"
                )
            if value is not None and self.row_state == "candidate_pending_exact_reader":
                _require_text(value, f"checkpoint_catalogue_{field_name}")
        if self.row_state == "candidate_pending_exact_reader" and self.blockers:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_candidate_has_blockers"
            )
        if self.row_state == "candidate_pending_exact_reader":
            if self.observed_schema_version != AVAILABILITY_SCHEMA:
                raise StrategyPaperAccountAvailabilityError(
                    "checkpoint_catalogue_candidate_schema_invalid"
                )
            for field_name in (
                "observed_binding_sha256", "observed_snapshot_sha256",
                "observed_base_receipt_sha256", "observed_availability_receipt_sha256",
            ):
                _require_hash(
                    getattr(self, field_name), f"checkpoint_catalogue_{field_name}"
                )
        if self.row_state == "blocked" and not self.blockers:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_blocked_reason_missing"
            )
        if (
            self.exact_reader_required is not True
            or self.checkpoint_verified is not False
            or self.performance_eligible is not False
        ):
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_qualification_forbidden"
            )
        for field_name in ("persisted_at", "available_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _parse_aware_utc(value, f"checkpoint_catalogue_{field_name}"),
                )
        if self.row_state == "candidate_pending_exact_reader":
            if self.persisted_at is None or self.available_at is None:
                raise StrategyPaperAccountAvailabilityError(
                    "checkpoint_catalogue_candidate_clock_missing"
                )
            if self.available_at < self.persisted_at:
                raise StrategyPaperAccountAvailabilityError(
                    "checkpoint_catalogue_candidate_clock_order_invalid"
                )


@dataclass(frozen=True, slots=True)
class StrategyPaperAccountCheckpointCatalogue:
    """固定 exact query 的有限候選列；不代表 complete history 或績效資格。"""

    schema_version: str
    strategy_id: str
    strategy_version_id: str
    account_namespace: str
    portfolio_id: str
    binding_sha256: str
    decision_cutoff: datetime
    rows: tuple[StrategyPaperAccountCheckpointCandidate, ...]
    truncated: bool
    complete: bool
    checkpoint_verified: bool = False
    performance_eligible: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CHECKPOINT_CATALOGUE_SCHEMA:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_schema_invalid"
            )
        for field_name in (
            "strategy_id", "strategy_version_id", "account_namespace", "portfolio_id"
        ):
            _require_text(getattr(self, field_name), f"checkpoint_catalogue_{field_name}")
        _require_hash(self.binding_sha256, "checkpoint_catalogue_binding_sha256")
        object.__setattr__(
            self,
            "decision_cutoff",
            _parse_aware_utc(self.decision_cutoff, "checkpoint_catalogue_decision_cutoff"),
        )
        if len(self.rows) > _MAX_CHECKPOINT_CATALOGUE_ROWS:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_row_limit_exceeded"
            )
        if self.complete is not (not self.truncated):
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_completeness_mismatch"
            )
        if self.checkpoint_verified is not False or self.performance_eligible is not False:
            raise StrategyPaperAccountAvailabilityError(
                "checkpoint_catalogue_qualification_forbidden"
            )


def _checkpoint_catalogue_read_text(
    row: sqlite3.Row,
    field_name: str,
    *,
    nullable: bool,
) -> str | None:
    storage_type = row[f"_type_{field_name}"]
    byte_length = row[f"_length_{field_name}"]
    raw = row[f"_raw_{field_name}"]
    if nullable and storage_type == "null" and byte_length is None and raw is None:
        return None
    if storage_type != "text" or type(byte_length) is not int:
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_sql_type_invalid:{field_name}"
        )
    if byte_length > _MAX_CHECKPOINT_CATALOGUE_TEXT_BYTES:
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_text_size_invalid:{field_name}"
        )
    if not isinstance(raw, bytes):
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_sql_type_invalid:{field_name}"
        )
    if len(raw) != byte_length:
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_text_size_invalid:{field_name}"
        )
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_text_utf8_invalid:{field_name}"
        ) from exc


def _checkpoint_catalogue_row(
    row: sqlite3.Row,
    *,
    binding: StrategyPaperAccountBinding,
    cutoff: datetime,
    observed_at: datetime,
) -> StrategyPaperAccountCheckpointCandidate:
    values = {
        name: _checkpoint_catalogue_read_text(
            row,
            name,
            nullable=name in _CATALOGUE_NULLABLE_TEXT_FIELDS,
        )
        for name in _CATALOGUE_TEXT_FIELDS
    }

    def required_text(field_name: str) -> str:
        value = values[field_name]
        if value is None:
            raise StrategyPaperAccountAvailabilityError(
                f"checkpoint_catalogue_sql_type_invalid:{field_name}"
            )
        return value

    operation_id = _require_text(
        values["operation_id"], "checkpoint_catalogue_operation_id"
    )
    snapshot_id = _require_text(
        values["snapshot_id"], "checkpoint_catalogue_snapshot_id"
    )
    blockers: list[str] = []
    if values["schema_version"] != AVAILABILITY_SCHEMA:
        blockers.append("availability_schema_version_mismatch")
    for field_name, expected in (
        ("portfolio_id", binding.portfolio_id),
        ("account_namespace", binding.account_namespace),
        ("binding_sha256", binding.binding_sha256),
    ):
        if values[field_name] != expected:
            blockers.append(f"{field_name}_binding_mismatch")
    for field_name in (
        "binding_sha256", "snapshot_sha256", "base_receipt_sha256", "receipt_sha256"
    ):
        try:
            _require_hash(values[field_name], f"checkpoint_catalogue_{field_name}")
        except StrategyPaperAccountAvailabilityError:
            blockers.append(f"{field_name}_invalid")

    persisted_raw = values["persisted_at_utc"]
    available_raw = values["available_at_utc"]
    persisted_at: datetime | None = None
    available_at: datetime | None = None
    if persisted_raw is None or available_raw is None:
        blockers.append("availability_clock_unknown")
    else:
        try:
            persisted_at = _parse_aware_utc(
                persisted_raw, "checkpoint_catalogue_persisted_clock"
            )
            available_at = _parse_aware_utc(
                available_raw, "checkpoint_catalogue_available_clock"
            )
        except StrategyPaperAccountAvailabilityError:
            blockers.append("availability_clock_invalid_or_timezone_unknown")
        if persisted_at is not None and available_at is not None:
            if available_at < persisted_at:
                blockers.append("availability_clock_order_invalid")
            if persisted_at > observed_at or available_at > observed_at:
                blockers.append("availability_clock_in_future")
            if available_at > cutoff:
                blockers.append("availability_after_decision_cutoff")

    unique_blockers = tuple(dict.fromkeys(blockers))
    return StrategyPaperAccountCheckpointCandidate(
        operation_id=operation_id,
        snapshot_id=snapshot_id,
        observed_schema_version=required_text("schema_version"),
        observed_portfolio_id=required_text("portfolio_id"),
        observed_account_namespace=required_text("account_namespace"),
        observed_binding_sha256=required_text("binding_sha256"),
        observed_snapshot_sha256=required_text("snapshot_sha256"),
        observed_base_receipt_sha256=required_text("base_receipt_sha256"),
        observed_availability_receipt_sha256=required_text("receipt_sha256"),
        persisted_at_text=persisted_raw,
        available_at_text=available_raw,
        persisted_at=persisted_at,
        available_at=available_at,
        row_state=("blocked" if unique_blockers else "candidate_pending_exact_reader"),
        blockers=unique_blockers,
    )


def list_strategy_paper_account_checkpoint_candidates(
    account_service: StrategyPaperAccountService,
    *,
    strategy_id: str,
    strategy_version_id: str,
    account_namespace: str,
    decision_cutoff: datetime,
) -> StrategyPaperAccountCheckpointCatalogue:
    """列出 exact account 的至多 200 個未驗證 checkpoint 候選與截斷標記。"""

    query_strategy_id = _require_text(strategy_id, "checkpoint_catalogue_strategy_id")
    query_version_id = _require_text(
        strategy_version_id, "checkpoint_catalogue_strategy_version_id"
    )
    query_namespace = _require_text(
        account_namespace, "checkpoint_catalogue_account_namespace"
    )
    cutoff = _parse_aware_utc(decision_cutoff, "checkpoint_catalogue_decision_cutoff")
    observed_at = _parse_aware_utc(
        _utc_now(), "checkpoint_catalogue_observation_clock"
    )
    if cutoff > observed_at:
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_catalogue_decision_cutoff_in_future"
        )

    selected = account_service.select_exact_version(
        strategy_id=query_strategy_id,
        strategy_version_id=query_version_id,
        account_namespace=query_namespace,
    )
    if (
        selected.status is not AccountBindingStatus.READY
        or selected.binding is None
        or selected.route is None
    ):
        reason = ",".join(selected.blockers) or "strategy_account_exact_binding_unavailable"
        raise StrategyPaperAccountAvailabilityError(
            f"checkpoint_catalogue_exact_binding_unavailable:{reason}"
        )
    binding = selected.binding
    route = selected.route
    if (
        binding.strategy_id != query_strategy_id
        or binding.strategy_version_id != query_version_id
        or binding.account_namespace != query_namespace
        or route.identity.key != binding.portfolio_id
        or route.paper_account_namespace != binding.account_namespace
    ):
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_catalogue_exact_binding_mismatch"
        )
    state_paths = PersonalPaperStorePaths.from_route(
        route, portfolio_id=binding.portfolio_id
    )
    identity = {
        "portfolio_id": binding.portfolio_id,
        "account_namespace": binding.account_namespace,
    }
    custody = PersonalStoreCustody(route, account_service.personal_paths)
    _require_exact_account_custody(custody, state_paths.state_db, identity)

    projection: list[str] = []
    for field_name in _CATALOGUE_TEXT_FIELDS:
        escaped = field_name.replace('"', '""')
        projection.extend(
            (
                f'typeof("{escaped}") AS "_type_{field_name}"',
                f'length(CAST("{escaped}" AS BLOB)) AS "_length_{field_name}"',
                f'''CASE WHEN typeof("{escaped}") = 'text' AND length(CAST("{escaped}" AS BLOB)) <= {_MAX_CHECKPOINT_CATALOGUE_TEXT_BYTES} THEN CAST("{escaped}" AS BLOB) ELSE NULL END AS "_raw_{field_name}"''',
            )
        )
    query = (
        "SELECT " + ", ".join(projection)
        + f' FROM "{_TABLE}" WHERE "portfolio_id" = ? '
        + 'AND "account_namespace" = ? ORDER BY "snapshot_id" COLLATE BINARY, '
        + '"operation_id" COLLATE BINARY LIMIT '
        + str(_CHECKPOINT_CATALOGUE_LOOKAHEAD)
    )
    try:
        with custody.read_sqlite(state_paths.state_db) as connection:
            try:
                query_only = connection.execute("PRAGMA query_only").fetchone()
                if query_only is None or int(query_only[0]) != 1:
                    raise StrategyPaperAccountAvailabilityError(
                        "checkpoint_catalogue_reader_not_read_only"
                    )
                connection.execute("BEGIN")
                _ensure_readable_table(connection)
                raw_rows = connection.execute(
                    query,
                    (binding.portfolio_id, binding.account_namespace),
                ).fetchmany(_CHECKPOINT_CATALOGUE_LOOKAHEAD)
                truncated = len(raw_rows) > _MAX_CHECKPOINT_CATALOGUE_ROWS
                rows = tuple(
                    _checkpoint_catalogue_row(
                        row,
                        binding=binding,
                        cutoff=cutoff,
                        observed_at=observed_at,
                    )
                    for row in raw_rows[:_MAX_CHECKPOINT_CATALOGUE_ROWS]
                )
            finally:
                if connection.in_transaction:
                    connection.rollback()
    except sqlite3.Error as exc:
        raise StrategyPaperAccountAvailabilityError(
            "checkpoint_catalogue_reader_failed"
        ) from exc

    return StrategyPaperAccountCheckpointCatalogue(
        schema_version=CHECKPOINT_CATALOGUE_SCHEMA,
        strategy_id=query_strategy_id,
        strategy_version_id=query_version_id,
        account_namespace=query_namespace,
        portfolio_id=binding.portfolio_id,
        binding_sha256=binding.binding_sha256,
        decision_cutoff=cutoff,
        rows=rows,
        truncated=truncated,
        complete=not truncated,
    )


__all__ += [
    "CHECKPOINT_CATALOGUE_SCHEMA",
    "StrategyPaperAccountCheckpointCandidate",
    "StrategyPaperAccountCheckpointCatalogue",
    "list_strategy_paper_account_checkpoint_candidates",
]
