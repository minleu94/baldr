"""受控建立 Paper Portfolio 的 frozen-constituent Equal Weight benchmark。

這個 service 將 benchmark 建置的讀取／驗證／append 邊界放在應用層，讓
CLI 與 Qt 走同一套契約。預覽永遠 query-only；只有明確 ``confirm=True``
才會建立新的 append-only ledger，且既有 output 絕不覆寫。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from app_module.paper_equal_weight_benchmark_ledger import (
    EqualWeightBenchmarkEntry,
    EqualWeightBenchmarkLedger,
    EqualWeightBenchmarkService,
)
from app_module.paper_portfolio_daily_runner import PaperPriceObservation
from app_module.paper_portfolio_time import paper_portfolio_today
from app_module.personal_data_paths import PersonalDataPaths, PersonalDataPathError, _absolute, to_internal_io_path
from app_module.personal_paper_store_paths import PersonalPaperStorePaths, PersonalStoreCustody
from app_module.personal_store_selection import assert_personal_store_path
from app_module.personal_store_routes import PersonalStoreRoute, PersonalStoreMode, PersonalStoreRouteError


PAPER_EQUAL_WEIGHT_BENCHMARK_BUILD_SCHEMA_VERSION = "paper-equal-weight-benchmark-build.v1"
DEFAULT_PORTFOLIO_ID = "paper-main"
DEFAULT_BENCHMARK_ID = "paper-main-equal"
TodayProvider = Callable[[], date]


@dataclass(frozen=True)
class PaperEqualWeightBenchmarkPreview:
    """不可變的 benchmark 建置預覽；不持有任何 writer connection。"""

    baseline_path: Path
    state_db_path: Path
    market_db_path: Path
    output_ledger_path: Path
    portfolio_id: str
    benchmark_id: str
    entries: tuple[EqualWeightBenchmarkEntry, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("benchmark preview requires at least one entry")
        if not self.portfolio_id.strip() or not self.benchmark_id.strip():
            raise ValueError("portfolio_id and benchmark_id are required")
        if self.entries[0].benchmark_id != self.benchmark_id:
            raise ValueError("preview benchmark_id does not match entries")

    @property
    def constituent_count(self) -> int:
        return len(self.entries[0].constituents)

    @property
    def constituents(self) -> tuple[str, ...]:
        return self.entries[0].constituents

    @property
    def observation_count(self) -> int:
        return len(self.entries)

    @property
    def first_date(self) -> str:
        return self.entries[0].decision_date

    @property
    def latest_date(self) -> str:
        return self.entries[-1].decision_date

    @property
    def initial_value(self) -> Decimal:
        return self.entries[0].total_value

    @property
    def latest_value(self) -> Decimal:
        return self.entries[-1].total_value

    def to_dict(self, *, status: str = "preview", write_performed: bool = False) -> dict[str, Any]:
        if status not in {"preview", "built"}:
            raise ValueError(f"unsupported benchmark build status: {status}")
        return {
            "schema_version": PAPER_EQUAL_WEIGHT_BENCHMARK_BUILD_SCHEMA_VERSION,
            "status": status,
            "baseline_path": str(self.baseline_path),
            "state_db": str(self.state_db_path),
            "market_db": str(self.market_db_path),
            "output_ledger": str(self.output_ledger_path),
            "portfolio_id": self.portfolio_id,
            "benchmark_id": self.benchmark_id,
            "constituent_count": self.constituent_count,
            "constituents": list(self.constituents),
            "observation_count": self.observation_count,
            "first_date": self.first_date,
            "latest_date": self.latest_date,
            "initial_value": str(self.initial_value),
            "latest_value": str(self.latest_value),
            "research_only": True,
            "writes_market_db": False,
            "broker_order_allowed": False,
            "auto_rebalance_allowed": False,
            "write_performed": write_performed,
        }


class PaperEqualWeightBenchmarkBuilder:
    """建立並在確認後保存 Equal Weight benchmark。"""

    def __init__(
        self,
        *,
        portfolio_id: str = DEFAULT_PORTFOLIO_ID,
        benchmark_id: str | None = None,
        today_provider: TodayProvider = paper_portfolio_today,
        route: PersonalStoreRoute | None = None,
        personal_paths: PersonalDataPaths | None = None,
    ) -> None:
        self.portfolio_id = str(portfolio_id)
        self.benchmark_id = (DEFAULT_BENCHMARK_ID if benchmark_id is None and route is None else str(benchmark_id or ""))
        self._today_provider = today_provider
        self.route = route
        self.personal_paths = personal_paths
        self.selected = (None if route is None else
                         PersonalPaperStorePaths.from_route(route, portfolio_id=self.portfolio_id))
        if route is not None and not self.benchmark_id.strip():
            raise PersonalStoreRouteError("paper_benchmark_identity_required")
        self.custody = PersonalStoreCustody(route, personal_paths)

    def _input(self, value: str | Path, selected: Path | None, *, sqlite: bool = False) -> Path:
        if selected is None:
            return _resolve_path(value)
        path = PersonalPaperStorePaths.require_selected(value, selected)
        return self.custody.sqlite_guard(path) if sqlite else self.custody.guard(path)

    def preview(
        self,
        *,
        baseline_path: str | Path,
        state_db_path: str | Path,
        market_db_path: str | Path,
        output_ledger_path: str | Path,
    ) -> PaperEqualWeightBenchmarkPreview:
        baseline = self._input(baseline_path, self.selected.baseline if self.selected else None)
        state_db = self._input(state_db_path, self.selected.state_db if self.selected else None, sqlite=True)
        market_db = _absolute(market_db_path) if self.route is not None else _resolve_path(market_db_path)
        output = self._input(output_ledger_path, self.selected.benchmark_db if self.selected else None, sqlite=True)
        require_market_separation(market_db, self.personal_paths)
        if output in {baseline, state_db, market_db}:
            raise ValueError("benchmark output must be different from every input path")
        entries = self.build_entries(
            baseline_path=baseline,
            state_db_path=state_db,
            market_db_path=market_db,
        )
        return PaperEqualWeightBenchmarkPreview(
            baseline_path=baseline,
            state_db_path=state_db,
            market_db_path=market_db,
            output_ledger_path=output,
            portfolio_id=self.portfolio_id,
            benchmark_id=self.benchmark_id,
            entries=entries,
        )

    def commit(
        self,
        preview: PaperEqualWeightBenchmarkPreview,
        *,
        confirm: bool = False,
    ) -> Path:
        """重新驗證預覽輸入後建立新的 ledger；不接受隱含寫入。"""
        if not confirm:
            raise ValueError("paper benchmark build requires explicit confirm=True")
        if preview.portfolio_id != self.portfolio_id or preview.benchmark_id != self.benchmark_id:
            raise ValueError("benchmark preview belongs to a different builder identity")
        output = preview.output_ledger_path
        if os.path.exists(self.custody.io(output)):
            raise ValueError(f"output ledger already exists: {output}")

        current = self.preview(
            baseline_path=preview.baseline_path,
            state_db_path=preview.state_db_path,
            market_db_path=preview.market_db_path,
            output_ledger_path=output,
        )
        if current.entries != preview.entries:
            raise ValueError("benchmark inputs changed after preview")
        self.write_new_ledger(output, current.entries, route=self.route,
                              personal_paths=self.personal_paths, portfolio_id=self.portfolio_id,
                              benchmark_id=self.benchmark_id)
        return output

    def build_entries(
        self,
        *,
        baseline_path: str | Path,
        state_db_path: str | Path,
        market_db_path: str | Path,
    ) -> tuple[EqualWeightBenchmarkEntry, ...]:
        baseline = self._input(baseline_path, self.selected.baseline if self.selected else None)
        state = self._input(state_db_path, self.selected.state_db if self.selected else None, sqlite=True)
        market = _absolute(market_db_path) if self.route is not None else _resolve_path(market_db_path)
        require_market_separation(market, self.personal_paths)
        baseline_payload = _read_object(Path(self.custody.io(baseline)))
        if self.route is not None and "portfolio_id" in baseline_payload and str(baseline_payload["portfolio_id"]) != self.portfolio_id:
            raise PersonalStoreRouteError("paper_baseline_identity_mismatch")
        baseline_date, capital, prices = _baseline_inputs(baseline_payload)
        snapshot_dates = self._snapshot_dates(state)
        if snapshot_dates[0] != baseline_date:
            raise ValueError(
                "paper snapshot and benchmark baseline require aligned first date: "
                f"{snapshot_dates[0]} != {baseline_date}"
            )
        service = EqualWeightBenchmarkService()
        entries: list[EqualWeightBenchmarkEntry] = [
            service.create_baseline(
                benchmark_id=self.benchmark_id,
                decision_date=baseline_date,
                capital=capital,
                prices=prices,
            )
        ]
        for decision_date in snapshot_dates[1:]:
            observations = self._latest_price_observations(
                market,
                symbols=tuple(prices),
                decision_date=decision_date,
            )
            entries.append(
                service.mark(
                    prior=entries[-1],
                    decision_date=decision_date,
                    prices=observations,
                )
            )
        return tuple(entries)

    @staticmethod
    def write_new_ledger(
        path: str | Path,
        entries: tuple[EqualWeightBenchmarkEntry, ...],
        *, route: PersonalStoreRoute | None = None,
        personal_paths: PersonalDataPaths | None = None,
        portfolio_id: str | None = None,
        benchmark_id: str | None = None,
    ) -> None:
        custody = PersonalStoreCustody(route, personal_paths)
        output = Path(path) if route is not None else _resolve_path(path)
        if route is not None:
            selected = PersonalPaperStorePaths.from_route(route, portfolio_id=portfolio_id or "")
            selected.require_selected(output, selected.benchmark_db)
            require_paper_writer(route)
            if not benchmark_id or any(row.benchmark_id != benchmark_id for row in entries):
                raise PersonalStoreRouteError("paper_benchmark_identity_mismatch")
        custody.sqlite_guard(output)
        if os.path.exists(custody.io(output)):
            raise ValueError(f"output ledger already exists: {output}")
        custody.prepare_parent(output)
        custody.sqlite_guard(output)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{output.stem}.",
            suffix=".tmp.sqlite",
            dir=str(Path(custody.io(output)).parent),
        )
        creation_identity = GeneratedPaperStaging._inode(os.fstat(fd))
        os.close(fd)
        temporary = output.parent / Path(temporary_name).name
        staging = GeneratedPaperStaging(custody, output, temporary, creation_identity=creation_identity)
        try:
            ledger = _GeneratedBenchmarkLedger(staging, benchmark_id)
            for entry in entries:
                ledger.append(entry)
            staging.guard_sqlite()
            if os.path.exists(custody.io(output)):
                raise ValueError(f"output ledger already exists: {output}")
            custody.sqlite_guard(output)
            # Windows rename 為 create-only；其他平台以 hardlink 原子建立目標。
            if os.name == "nt":
                os.rename(staging.io(), custody.io(output))
            else:
                os.link(staging.io(), custody.io(output), follow_symlinks=False)
                os.unlink(to_internal_io_path(temporary))
        finally:
            staging.cleanup()

    def _snapshot_dates(self, state_db: Path) -> tuple[str, ...]:
        if not self.custody.exists(state_db):
            raise FileNotFoundError(state_db)
        with self.custody.read_sqlite(state_db) as conn:
            if not _table_exists(conn, "paper_portfolio_snapshots"):
                raise ValueError("paper snapshot DB is missing paper_portfolio_snapshots")
            rows = conn.execute(
                """
                SELECT decision_date
                FROM paper_portfolio_snapshots
                WHERE portfolio_id = ?
                ORDER BY decision_date, snapshot_id
                """,
                (self.portfolio_id,),
            ).fetchall()
        dates = tuple(_iso_date(row["decision_date"], "snapshot decision_date") for row in rows)
        if len(dates) < 2:
            raise ValueError("paper snapshots require at least two observations")
        if len(set(dates)) != len(dates):
            raise ValueError("paper snapshots require one observation per decision date")
        today = self._today_provider()
        future_dates = sorted({item for item in dates if date.fromisoformat(item) > today})
        if future_dates:
            raise ValueError(
                "paper snapshots contain future-dated observations: "
                + ", ".join(future_dates)
                + f" (today={today.isoformat()})"
            )
        return dates

    def _latest_price_observations(
        self,
        market_db: Path,
        *,
        symbols: Sequence[str],
        decision_date: str,
    ) -> tuple[PaperPriceObservation, ...]:
        if not Path(to_internal_io_path(market_db)).is_file():
            raise FileNotFoundError(market_db)
        require_market_separation(market_db, self.personal_paths)
        selected: dict[str, tuple[str, Decimal]] = {}
        with PersonalStoreCustody(None, None).read_sqlite(market_db) as conn:
            if not _table_exists(conn, "daily_prices"):
                raise ValueError("market DB is missing daily_prices")
            columns = {
                str(row[1])
                for row in conn.execute('PRAGMA table_info("daily_prices")').fetchall()
            }
            required = {"證券代號", "日期", "收盤價"}
            if not required.issubset(columns):
                missing = ",".join(sorted(required - columns))
                raise ValueError(f"market DB daily_prices schema mismatch: {missing}")
            for symbol in sorted(set(symbols)):
                rows = conn.execute(
                    """
                    SELECT 日期 AS price_date, 收盤價 AS close
                    FROM daily_prices
                    WHERE 證券代號 = ? AND 收盤價 IS NOT NULL
                    """,
                    (symbol,),
                ).fetchall()
                for row in rows:
                    try:
                        price_date = _iso_date(row["price_date"], "market price date")
                        close = _positive_decimal(row["close"], f"market close {symbol}")
                    except ValueError:
                        continue
                    if price_date >= decision_date:
                        continue
                    prior = selected.get(symbol)
                    if prior is None or price_date > prior[0]:
                        selected[symbol] = (price_date, close)
        missing_symbols = sorted(set(symbols) - set(selected))
        if missing_symbols:
            raise ValueError(
                "missing causal T-1 benchmark prices: " + ",".join(missing_symbols)
            )
        return tuple(
            PaperPriceObservation(symbol, selected[symbol][0], selected[symbol][0], selected[symbol][1])
            for symbol in sorted(set(symbols))
        )


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _read_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("baseline JSON must contain an object")
    return payload


def _iso_date(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be Decimal text") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return parsed


def _positive_decimal(value: object, field_name: str) -> Decimal:
    parsed = _decimal(value, field_name)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


def _baseline_inputs(payload: Mapping[str, Any]) -> tuple[str, Decimal, dict[str, Decimal]]:
    if payload.get("research_only") is not True:
        raise ValueError("baseline must remain research_only")
    for key in ("writes_positions_db", "broker_order_allowed", "auto_rebalance_allowed"):
        if payload.get(key) is not False:
            raise ValueError(f"baseline safety boundary violated: {key}")
    decision_date = _iso_date(payload.get("decision_date"), "baseline decision_date")
    residual_cash = _decimal(payload.get("residual_cash"), "baseline residual_cash")
    raw_allocations = payload.get("allocations")
    if not isinstance(raw_allocations, list) or not raw_allocations:
        raise ValueError("baseline allocations are required")

    prices: dict[str, Decimal] = {}
    invested_amount = Decimal("0")
    for index, raw in enumerate(raw_allocations, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError(f"allocation {index} must be an object")
        stock_code = str(raw.get("stock_code") or "").strip()
        if not stock_code:
            raise ValueError(f"allocation {index} stock_code is required")
        shares = _integer(raw.get("executable_shares"), f"allocation {index} executable_shares")
        if shares == 0:
            continue
        if stock_code in prices:
            raise ValueError(f"duplicate benchmark constituent: {stock_code}")
        price = _positive_decimal(raw.get("reference_price"), f"allocation {index} reference_price")
        amount = _decimal(
            raw.get("executable_amount", price * shares),
            f"allocation {index} executable_amount",
        )
        if amount <= 0:
            raise ValueError(f"allocation {index} executable_amount must be positive")
        prices[stock_code] = price
        invested_amount += amount

    if not prices:
        raise ValueError("baseline has no executable benchmark constituents")
    capital = (residual_cash + invested_amount).quantize(Decimal("0.01"))
    if capital <= 0:
        raise ValueError("benchmark capital must be positive")
    return decision_date, capital, prices


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


__all__ = [
    "DEFAULT_BENCHMARK_ID",
    "DEFAULT_PORTFOLIO_ID",
    "PAPER_EQUAL_WEIGHT_BENCHMARK_BUILD_SCHEMA_VERSION",
    "PaperEqualWeightBenchmarkBuilder",
    "PaperEqualWeightBenchmarkPreview",
]


def require_paper_writer(route: PersonalStoreRoute | None) -> None:
    if route is not None and (route.write_target is None or route.mode is PersonalStoreMode.LEGACY_READ_ONLY):
        raise PersonalStoreRouteError("legacy_read_only_writer_forbidden")


def require_market_separation(market: Path, paths: PersonalDataPaths | None) -> None:
    if paths is not None:
        canonical = _absolute(market)
        if canonical.is_relative_to(paths.personal_root) or canonical.is_relative_to(paths.legacy_output_root):
            raise PersonalStoreRouteError("paper_market_must_be_independent")


class GeneratedPaperStaging:
    """只綁本次已建立 temporary；target／parent 與 inode 每次重新核驗。"""

    def __init__(self, custody: PersonalStoreCustody, target: Path, generated: Path, *, creation_identity: tuple[int, int]) -> None:
        self.custody, self.target, self.path = custody, target, generated
        custody.guard(target)
        if generated.parent != target.parent or not generated.name.startswith(f".{target.stem}."):
            raise PersonalStoreRouteError("paper_generated_staging_mismatch")
        self._identity = creation_identity
        self._parent_identity = self._inode(os.stat(to_internal_io_path(target.parent), follow_symlinks=False))
        self.guard_sqlite()

    @staticmethod
    def _inode(info: os.stat_result) -> tuple[int, int]:
        return info.st_dev, info.st_ino

    def guard(self, path: Path) -> Path:
        self.custody.guard(self.target)
        if path not in {self.path, *(self.path.with_name(self.path.name + suffix)
                                    for suffix in ("-journal", "-wal", "-shm"))}:
            raise PersonalStoreRouteError("paper_generated_staging_mismatch")
        if self.custody.route is not None and self.custody.route.mode is PersonalStoreMode.PERSONAL:
            if self.custody.paths is None:
                raise PersonalStoreRouteError("personal_paths_required")
            assert_personal_store_path(self.custody.paths, path)
        elif _absolute(path) != path:
            raise PersonalDataPathError("personal_store_path_alias", path)
        parent = os.stat(to_internal_io_path(self.path.parent), follow_symlinks=False)
        if self._inode(parent) != self._parent_identity:
            raise PersonalStoreRouteError("paper_staging_parent_changed")
        try:
            info = os.stat(to_internal_io_path(path), follow_symlinks=False)
        except FileNotFoundError:
            if path == self.path:
                raise PersonalStoreRouteError("paper_generated_staging_missing")
            return path
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PersonalDataPathError("personal_store_alias_or_type", path)
        if path == self.path and self._inode(info) != self._identity:
            raise PersonalStoreRouteError("paper_generated_staging_changed")
        return path

    def guard_sqlite(self) -> None:
        self.custody.sqlite_guard(self.target)
        for path in (self.path, *(self.path.with_name(self.path.name + suffix)
                                 for suffix in ("-journal", "-wal", "-shm"))):
            self.guard(path)

    def io(self) -> str:
        self.guard_sqlite()
        return to_internal_io_path(self.path)

    def cleanup(self) -> None:
        # 已出版 main 不存在；仍核 sidecars，拒絕清理遭替換或別名的檔案。
        for suffix in ("-journal", "-wal", "-shm", ""):
            path = self.path.with_name(self.path.name + suffix)
            if os.path.lexists(to_internal_io_path(path)):
                self.guard(path)
                os.unlink(to_internal_io_path(path))


class _GeneratedBenchmarkLedger(EqualWeightBenchmarkLedger):
    """只替換 connect custody，金融 schema／append 全沿 P1 writer。"""

    def __init__(self, staging: GeneratedPaperStaging, benchmark_id: str | None):
        self.staging = staging
        self.expected_benchmark_id = benchmark_id
        super().__init__(staging.io())

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            raise PersonalStoreRouteError("paper_staging_reader_forbidden")
        return sqlite3.connect(self.staging.io())

    def _require_identity(self, benchmark_id: str) -> None:
        if self.expected_benchmark_id is not None and benchmark_id != self.expected_benchmark_id:
            raise PersonalStoreRouteError("paper_benchmark_identity_mismatch")
