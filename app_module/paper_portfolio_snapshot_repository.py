"""Append-only SQLite repository for research paper-portfolio snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Literal
from app_module.personal_store_routes import PersonalStoreRoute
from app_module.personal_paper_store_paths import PersonalPaperStorePaths, PersonalStoreCustody
from app_module.personal_data_paths import PersonalDataPaths, to_internal_io_path, to_internal_sqlite_uri


PAPER_SNAPSHOT_RECEIPT_SCHEMA_VERSION = "paper-portfolio-snapshot-receipt.v1"
PAPER_SNAPSHOT_RECEIPT_MAX_BYTES = 16 * 1024
_PAPER_ACCOUNT_NAMESPACE = re.compile(r"^acct-[0-9a-f]{64}$")
_SHA256_TEXT = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_PAYLOAD_FIELDS = (
    "schema_version",
    "receipt_kind",
    "snapshot_id",
    "portfolio_id",
    "decision_date",
    "source_result_id",
    "account_namespace",
    "binding_sha256",
    "unknown_reason",
    "seed_source_id",
    "seed_source_sha256",
    "initial_capital",
    "max_positions",
    "positions_sha256",
)


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_sha256(payload: object) -> str:
    return "sha256:" + sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _receipt_text(name: str, value: object, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"paper snapshot receipt {name} is invalid")
    if len(value) > limit:
        raise ValueError(f"paper snapshot receipt {name} is too long")
    return value


def _receipt_hash(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256_TEXT.fullmatch(value):
        raise ValueError(f"paper snapshot receipt {name} is invalid")
    return value


def _positions_sha256(snapshot: "PaperPortfolioSnapshot") -> str:
    payload = [
        {
            "stock_code": row.stock_code,
            "quantity": row.quantity,
            "mark_price": str(row.mark_price),
            "market_value": str(row.market_value),
            "weight_bp": row.weight_bp,
        }
        for row in sorted(snapshot.positions, key=lambda item: item.stock_code)
    ]
    return _canonical_sha256(payload)


@dataclass(frozen=True, slots=True)
class PaperPortfolioSnapshotReceipt:
    """有界的來源憑證；僅支援 unknown 與 synthetic seed reference，沒有 net 資格。"""

    schema_version: str
    receipt_kind: Literal["unknown", "seed_reference"]
    snapshot_id: str
    portfolio_id: str
    decision_date: str
    source_result_id: str
    account_namespace: str | None
    binding_sha256: str | None
    unknown_reason: str | None
    seed_source_id: str | None
    seed_source_sha256: str | None
    initial_capital: str | None
    max_positions: int | None
    positions_sha256: str | None
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.schema_version != PAPER_SNAPSHOT_RECEIPT_SCHEMA_VERSION
            or self.receipt_kind not in ("unknown", "seed_reference")
        ):
            raise ValueError("paper snapshot receipt contract is unsupported")
        for name in ("snapshot_id", "portfolio_id", "decision_date", "source_result_id"):
            _receipt_text(name, getattr(self, name))
        try:
            parsed_date = date.fromisoformat(self.decision_date)
        except ValueError as exc:
            raise ValueError("paper snapshot receipt decision_date is invalid") from exc
        if parsed_date.isoformat() != self.decision_date:
            raise ValueError("paper snapshot receipt decision_date is not canonical")
        if self.account_namespace is None:
            if self.binding_sha256 is not None:
                raise ValueError("paper snapshot receipt binding hash requires a namespace")
            if _PAPER_ACCOUNT_NAMESPACE.fullmatch(self.portfolio_id):
                raise ValueError("paper snapshot receipt namespace binding is missing")
        else:
            if not isinstance(self.account_namespace, str):
                raise ValueError("paper snapshot receipt account namespace is invalid")
            binding_hash = _receipt_hash("binding_sha256", self.binding_sha256)
            expected = "acct-" + binding_hash.removeprefix("sha256:")
            if not _PAPER_ACCOUNT_NAMESPACE.fullmatch(self.account_namespace) or (
                self.account_namespace != expected or self.portfolio_id != expected
            ):
                raise ValueError("paper snapshot receipt account binding mismatch")
        self._validate_kind_fields()
        _receipt_hash("receipt_sha256", self.receipt_sha256)
        if self.receipt_sha256 != _canonical_sha256(self._payload()):
            raise ValueError("paper snapshot receipt hash mismatch")
        self.to_json()

    def _payload(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in _RECEIPT_PAYLOAD_FIELDS}

    def _validate_kind_fields(self) -> None:
        seed_fields = (
            self.seed_source_id,
            self.seed_source_sha256,
            self.initial_capital,
            self.max_positions,
            self.positions_sha256,
        )
        if self.receipt_kind == "unknown":
            _receipt_text("unknown_reason", self.unknown_reason, 512)
            if any(value is not None for value in seed_fields):
                raise ValueError("unknown receipt cannot contain seed claims")
            return
        if self.unknown_reason is not None:
            raise ValueError("seed reference cannot contain an unknown reason")
        seed_source_id = _receipt_text("seed_source_id", self.seed_source_id)
        if not seed_source_id.startswith("synthetic:"):
            raise ValueError("seed reference is limited to synthetic source IDs")
        _receipt_hash("seed_source_sha256", self.seed_source_sha256)
        if self.initial_capital != "500000":
            raise ValueError("seed reference initial capital must remain 500000")
        if type(self.max_positions) is not int or self.max_positions != 8:
            raise ValueError("seed reference max positions must remain 8")
        _receipt_hash("positions_sha256", self.positions_sha256)
        if self.account_namespace is None or self.binding_sha256 is None:
            raise ValueError("seed reference requires an explicit bound account")

    @classmethod
    def unknown_for(
        cls,
        snapshot: "PaperPortfolioSnapshot",
        *,
        reason: str,
        account_namespace: str | None = None,
        binding_sha256: str | None = None,
    ) -> "PaperPortfolioSnapshotReceipt":
        payload: dict[str, object] = {
            "schema_version": PAPER_SNAPSHOT_RECEIPT_SCHEMA_VERSION,
            "receipt_kind": "unknown",
            "snapshot_id": snapshot.snapshot_id,
            "portfolio_id": snapshot.portfolio_id,
            "decision_date": snapshot.decision_date,
            "source_result_id": snapshot.source_result_id,
            "account_namespace": account_namespace,
            "binding_sha256": binding_sha256,
            "unknown_reason": reason,
            "seed_source_id": None,
            "seed_source_sha256": None,
            "initial_capital": None,
            "max_positions": None,
            "positions_sha256": None,
        }
        receipt = cls(**payload, receipt_sha256=_canonical_sha256(payload))  # type: ignore[arg-type]
        receipt.validate_for_snapshot(snapshot)
        return receipt

    @classmethod
    def seed_reference_for(
        cls,
        snapshot: "PaperPortfolioSnapshot",
        *,
        account_namespace: str,
        binding_sha256: str,
        seed_source_id: str,
        seed_source_sha256: str,
    ) -> "PaperPortfolioSnapshotReceipt":
        payload: dict[str, object] = {
            "schema_version": PAPER_SNAPSHOT_RECEIPT_SCHEMA_VERSION,
            "receipt_kind": "seed_reference",
            "snapshot_id": snapshot.snapshot_id,
            "portfolio_id": snapshot.portfolio_id,
            "decision_date": snapshot.decision_date,
            "source_result_id": snapshot.source_result_id,
            "account_namespace": account_namespace,
            "binding_sha256": binding_sha256,
            "unknown_reason": None,
            "seed_source_id": seed_source_id,
            "seed_source_sha256": seed_source_sha256,
            "initial_capital": "500000",
            "max_positions": 8,
            "positions_sha256": _positions_sha256(snapshot),
        }
        receipt = cls(**payload, receipt_sha256=_canonical_sha256(payload))  # type: ignore[arg-type]
        receipt.validate_for_snapshot(snapshot)
        return receipt

    def validate_for_snapshot(
        self,
        snapshot: "PaperPortfolioSnapshot",
        *,
        expected_account_namespace: str | None = None,
    ) -> None:
        if (
            self.snapshot_id != snapshot.snapshot_id
            or self.portfolio_id != snapshot.portfolio_id
            or self.decision_date != snapshot.decision_date
            or self.source_result_id != snapshot.source_result_id
        ):
            raise ValueError("paper snapshot receipt does not match snapshot identity")
        if expected_account_namespace is not None:
            if self.account_namespace != expected_account_namespace:
                raise ValueError("paper snapshot receipt route namespace mismatch")
        if self.receipt_kind == "seed_reference":
            if len(snapshot.positions) > 8:
                raise ValueError("seed reference exceeds the 8-position limit")
            symbols = tuple(row.stock_code for row in snapshot.positions)
            if len(set(symbols)) != len(symbols):
                raise ValueError("seed reference contains duplicate positions")
            if snapshot.total_value != Decimal("500000"):
                raise ValueError("seed reference total value must remain 500000")
            reconciled = snapshot.cash + sum(
                (row.market_value for row in snapshot.positions), Decimal("0")
            )
            if reconciled != snapshot.total_value:
                raise ValueError("seed reference snapshot value does not reconcile")
            for row in snapshot.positions:
                try:
                    # 與既有 PaperPortfolioDailyRunner 相同，以分為量化後核對市值。
                    expected_market_value = (
                        Decimal(row.quantity) * row.mark_price
                    ).quantize(Decimal("0.01"))
                    # 沿用既有 int(...) 截斷語義，不引入新的權重捨入規則。
                    expected_weight_bp = int(
                        row.market_value * Decimal("10000") / snapshot.total_value
                    )
                except (InvalidOperation, OverflowError, ValueError) as exc:
                    raise ValueError(
                        "seed reference position consistency cannot be verified"
                    ) from exc
                if row.market_value != expected_market_value:
                    raise ValueError(
                        "seed reference market value does not match quantity and mark price"
                    )
                if row.weight_bp != expected_weight_bp:
                    raise ValueError(
                        "seed reference weight_bp does not match market value"
                    )
            if self.positions_sha256 != _positions_sha256(snapshot):
                raise ValueError("seed reference positions hash mismatch")

    def to_json(self) -> str:
        serialized = _canonical_json({**self._payload(), "receipt_sha256": self.receipt_sha256})
        if len(serialized.encode("utf-8")) > PAPER_SNAPSHOT_RECEIPT_MAX_BYTES:
            raise ValueError("paper snapshot receipt exceeds the size limit")
        return serialized

    @classmethod
    def from_json(cls, value: str) -> "PaperPortfolioSnapshotReceipt":
        if not isinstance(value, str):
            raise ValueError("paper snapshot receipt JSON must be text")
        raw = value.encode("utf-8")
        if len(raw) > PAPER_SNAPSHOT_RECEIPT_MAX_BYTES:
            raise ValueError("paper snapshot receipt exceeds the size limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("paper snapshot receipt JSON has duplicate keys")
                result[key] = item
            return result

        try:
            payload = json.loads(value, object_pairs_hook=unique_object)
        except json.JSONDecodeError as exc:
            raise ValueError("paper snapshot receipt JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("paper snapshot receipt JSON must be an object")
        expected = set(_RECEIPT_PAYLOAD_FIELDS) | {"receipt_sha256"}
        if set(payload) != expected:
            raise ValueError("paper snapshot receipt fields are incomplete or unknown")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True)
class PaperPortfolioPositionSnapshot:
    stock_code: str
    quantity: int
    mark_price: Decimal
    market_value: Decimal
    weight_bp: int

    def __post_init__(self) -> None:
        if not self.stock_code:
            raise ValueError("stock_code is required")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 0:
            raise ValueError("quantity must be a non-negative integer")
        for field_name in ("mark_price", "market_value"):
            _require_finite_nonnegative_decimal(field_name, getattr(self, field_name))
        if isinstance(self.weight_bp, bool) or not isinstance(self.weight_bp, int) or not 0 <= self.weight_bp <= 10000:
            raise ValueError("weight_bp must be an integer within 0..10000")


@dataclass(frozen=True)
class PaperPortfolioSnapshot:
    snapshot_id: str
    portfolio_id: str
    decision_date: str
    source_result_id: str
    cash: Decimal
    total_value: Decimal
    positions: tuple[PaperPortfolioPositionSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.portfolio_id or not self.decision_date:
            raise ValueError("snapshot_id, portfolio_id and decision_date are required")
        for field_name in ("cash", "total_value"):
            _require_finite_nonnegative_decimal(field_name, getattr(self, field_name))


def _require_finite_nonnegative_decimal(name: str, value: object) -> None:
    """拒絕非 Decimal、非有限或負數的金額欄位。"""

    if (
        isinstance(value, bool)
        or not isinstance(value, Decimal)
        or not value.is_finite()
        or value < Decimal("0")
    ):
        raise ValueError(f"{name} must be a finite non-negative Decimal")


class PaperPortfolioSnapshotRepository:
    def __init__(self, db_path: str | Path, *, route: PersonalStoreRoute | None = None,
                 portfolio_id: str | None = None, personal_paths: PersonalDataPaths | None = None) -> None:
        self.custody = PersonalStoreCustody(route, personal_paths)
        self._path = Path(db_path)
        self.route = route
        self.portfolio_id = portfolio_id
        self.read_only = route is not None and route.write_target is None
        if route is not None:
            paths = PersonalPaperStorePaths.from_route(route, portfolio_id=portfolio_id or "")
            paths.require_selected(db_path, paths.state_db)
        if self.read_only:
            return
        self.custody.sqlite_guard(self._path)
        self.custody.prepare_parent(self._path)
        self._ensure_schema()

    def _require_identity(self, portfolio_id: str) -> None:
        if self.route is not None and portfolio_id != self.route.identity.key:
            raise ValueError("paper identity mismatch")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.custody.sqlite_guard(self._path)
        if self.read_only:
            conn = sqlite3.connect(to_internal_sqlite_uri(self._path, "ro"), uri=True)
            conn.execute("PRAGMA query_only=ON")
        else:
            conn = sqlite3.connect(self.custody.io(self._path) if self.route is not None else to_internal_io_path(self._path.resolve()))
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def append(
        self,
        snapshot: PaperPortfolioSnapshot,
        receipt: PaperPortfolioSnapshotReceipt | None = None,
    ) -> None:
        if self.read_only:
            raise PermissionError("paper snapshot route is read-only")
        self._require_identity(snapshot.portfolio_id)
        if receipt is not None:
            receipt.validate_for_snapshot(
                snapshot,
                expected_account_namespace=(
                    None if self.route is None else self.route.paper_account_namespace
                ),
            )
        try:
            with self._connect() as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute(
                    "INSERT INTO paper_portfolio_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        snapshot.snapshot_id,
                        snapshot.portfolio_id,
                        snapshot.decision_date,
                        snapshot.source_result_id,
                        str(snapshot.cash),
                        str(snapshot.total_value),
                    ),
                )
                conn.executemany(
                    "INSERT INTO paper_portfolio_positions VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        (
                            snapshot.snapshot_id,
                            item.stock_code,
                            item.quantity,
                            str(item.mark_price),
                            str(item.market_value),
                            item.weight_bp,
                        )
                        for item in snapshot.positions
                    ),
                )
                if receipt is not None:
                    conn.execute(
                        """
                        INSERT INTO paper_portfolio_snapshot_receipts (
                            snapshot_id, portfolio_id, account_namespace,
                            binding_sha256, receipt_json, receipt_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            receipt.snapshot_id,
                            receipt.portfolio_id,
                            receipt.account_namespace,
                            receipt.binding_sha256,
                            receipt.to_json(),
                            receipt.receipt_sha256,
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            if "paper_portfolio_snapshots.snapshot_id" in str(exc):
                raise ValueError(f"snapshot already exists: {snapshot.snapshot_id}") from exc
            raise ValueError("snapshot append failed") from exc

    def get(self, snapshot_id: str) -> PaperPortfolioSnapshot | None:
        if self.read_only and not self.custody.exists(self._path):
            return None
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM paper_portfolio_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            if row is None:
                return None
            return self._hydrate(conn, row)

    def list_for_portfolio(self, portfolio_id: str) -> tuple[PaperPortfolioSnapshot, ...]:
        self._require_identity(portfolio_id)
        if self.read_only and not self.custody.exists(self._path):
            return ()
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM paper_portfolio_snapshots WHERE portfolio_id = ? ORDER BY decision_date, snapshot_id",
                (portfolio_id,),
            ).fetchall()
            return tuple(self._hydrate(conn, row) for row in rows)

    def get_receipt(self, snapshot_id: str) -> PaperPortfolioSnapshotReceipt | None:
        """讀取已保存憑證；舊 snapshot 或缺列回傳 None，呼叫端必須視為 unknown。"""

        if self.read_only and not self.custody.exists(self._path):
            return None
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            snapshot_row = conn.execute(
                "SELECT * FROM paper_portfolio_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            if snapshot_row is None:
                return None
            snapshot = self._hydrate(conn, snapshot_row)
            table = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'paper_portfolio_snapshot_receipts'
                """
            ).fetchone()
            if table is None:
                return None
            row = conn.execute(
                """
                SELECT portfolio_id, account_namespace, binding_sha256,
                       receipt_json, receipt_sha256
                FROM paper_portfolio_snapshot_receipts
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if row is None:
                return None
            receipt = PaperPortfolioSnapshotReceipt.from_json(str(row["receipt_json"]))
            receipt.validate_for_snapshot(
                snapshot,
                expected_account_namespace=(
                    None if self.route is None else self.route.paper_account_namespace
                ),
            )
            if (
                str(row["portfolio_id"]) != receipt.portfolio_id
                or row["account_namespace"] != receipt.account_namespace
                or row["binding_sha256"] != receipt.binding_sha256
                or str(row["receipt_sha256"]) != receipt.receipt_sha256
            ):
                raise ValueError("paper snapshot receipt row metadata mismatch")
            return receipt

    def _hydrate(self, conn: sqlite3.Connection, row: sqlite3.Row) -> PaperPortfolioSnapshot:
        self._require_identity(str(row["portfolio_id"]))
        position_rows = conn.execute(
            "SELECT * FROM paper_portfolio_positions WHERE snapshot_id = ? ORDER BY stock_code",
            (row["snapshot_id"],),
        ).fetchall()
        positions = tuple(
            PaperPortfolioPositionSnapshot(
                stock_code=str(item["stock_code"]),
                quantity=int(item["quantity"]),
                mark_price=Decimal(str(item["mark_price"])),
                market_value=Decimal(str(item["market_value"])),
                weight_bp=int(item["weight_bp"]),
            )
            for item in position_rows
        )
        return PaperPortfolioSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            portfolio_id=str(row["portfolio_id"]),
            decision_date=str(row["decision_date"]),
            source_result_id=str(row["source_result_id"]),
            cash=Decimal(str(row["cash"])),
            total_value=Decimal(str(row["total_value"])),
            positions=positions,
        )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_portfolio_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    decision_date TEXT NOT NULL,
                    source_result_id TEXT NOT NULL,
                    cash TEXT NOT NULL,
                    total_value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_portfolio_positions (
                    snapshot_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    mark_price TEXT NOT NULL,
                    market_value TEXT NOT NULL,
                    weight_bp INTEGER NOT NULL,
                    PRIMARY KEY (snapshot_id, stock_code),
                    FOREIGN KEY (snapshot_id) REFERENCES paper_portfolio_snapshots(snapshot_id)
                );
                CREATE TABLE IF NOT EXISTS paper_portfolio_snapshot_receipts (
                    snapshot_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    account_namespace TEXT,
                    binding_sha256 TEXT,
                    receipt_json TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL,
                    FOREIGN KEY (snapshot_id) REFERENCES paper_portfolio_snapshots(snapshot_id)
                );
                """
            )
