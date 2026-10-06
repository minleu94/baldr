"""Frozen-constituent equal-weight benchmark and append-only ledger."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping

from app_module.paper_portfolio_daily_runner import PaperPriceObservation
from app_module.personal_data_paths import PersonalDataPaths, to_internal_sqlite_uri
from app_module.personal_paper_store_paths import (
    PersonalPaperStorePaths, PersonalStoreCustody,
)
from app_module.personal_store_routes import (
    PersonalStoreMode, PersonalStoreRoute, PersonalStoreRouteError,
)
from app_module.sqlite_read_only import configure_read_only_connection


@dataclass(frozen=True)
class EqualWeightBenchmarkEntry:
    benchmark_id: str
    decision_date: str
    constituents: tuple[str, ...]
    units: tuple[tuple[str, Decimal], ...]
    total_value: Decimal


class EqualWeightBenchmarkService:
    def create_baseline(
        self,
        *,
        benchmark_id: str,
        decision_date: str,
        capital: Decimal,
        prices: Mapping[str, Decimal],
    ) -> EqualWeightBenchmarkEntry:
        if not prices:
            raise ValueError("benchmark requires constituents")
        if not isinstance(capital, Decimal) or capital <= 0:
            raise ValueError("capital must be a positive Decimal")
        constituents = tuple(sorted(prices))
        allocation = capital / len(constituents)
        units = tuple((code, allocation / prices[code]) for code in constituents)
        return EqualWeightBenchmarkEntry(
            benchmark_id=benchmark_id,
            decision_date=decision_date,
            constituents=constituents,
            units=units,
            total_value=capital.quantize(Decimal("0.01")),
        )

    def mark(
        self,
        *,
        prior: EqualWeightBenchmarkEntry,
        decision_date: str,
        prices: Iterable[PaperPriceObservation],
    ) -> EqualWeightBenchmarkEntry:
        if _date(decision_date) <= _date(prior.decision_date):
            raise ValueError("decision_date must be after prior benchmark entry")
        observations = tuple(prices)
        value = Decimal("0")
        for code, units in prior.units:
            visible = tuple(
                row
                for row in observations
                if row.stock_code == code
                and _date(row.price_date) <= _date(decision_date)
                and _date(row.available_date) <= _date(decision_date)
            )
            if not visible:
                raise ValueError(f"missing causal benchmark price for {code}")
            selected = max(visible, key=lambda row: (row.price_date, row.available_date))
            value += units * selected.close
        return EqualWeightBenchmarkEntry(
            benchmark_id=prior.benchmark_id,
            decision_date=decision_date,
            constituents=prior.constituents,
            units=prior.units,
            total_value=value.quantize(Decimal("0.01")),
        )


class EqualWeightBenchmarkLedger:
    """原 append-only schema；routed 帳戶與 benchmark 身份由 caller 分別明示。"""
    def __init__(
        self, db_path: str | Path, *,
        route: PersonalStoreRoute | None = None,
        personal_paths: PersonalDataPaths | None = None,
        portfolio_id: str | None = None,
        benchmark_id: str | None = None,
        read_only: bool = False,
    ) -> None:
        self._path = Path(db_path)
        self._route = route
        self._portfolio_id = portfolio_id
        self._benchmark_id = benchmark_id
        self._read_only = read_only
        if route is not None:
            selected = PersonalPaperStorePaths.from_route(route, portfolio_id=portfolio_id or "")
            PersonalPaperStorePaths.require_selected(self._path, selected.benchmark_db)
            if benchmark_id is None or not benchmark_id.strip():
                raise PersonalStoreRouteError("paper_benchmark_identity_required")
            if not read_only and route.mode is PersonalStoreMode.LEGACY_READ_ONLY:
                raise PersonalStoreRouteError("legacy_read_only_writer_forbidden")
        self._custody = PersonalStoreCustody(route, personal_paths)
        self._custody.sqlite_guard(self._path)
        if read_only:
            return
        self._custody.prepare_parent(self._path)
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS paper_equal_weight_benchmark (
                        benchmark_id TEXT NOT NULL,
                        decision_date TEXT NOT NULL,
                        constituents_json TEXT NOT NULL,
                        units_json TEXT NOT NULL,
                        total_value TEXT NOT NULL,
                        PRIMARY KEY (benchmark_id, decision_date)
                    )"""
                )

    def _require_identity(self, benchmark_id: str) -> None:
        if self._route is not None and benchmark_id != self._benchmark_id:
            raise PersonalStoreRouteError("paper_benchmark_identity_mismatch")

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if not read_only and (self._read_only or (
            self._route is not None and self._route.mode is PersonalStoreMode.LEGACY_READ_ONLY
        )):
            raise PersonalStoreRouteError("paper_read_only_writer_forbidden")
        if self._route is not None:
            selected = PersonalPaperStorePaths.from_route(
                self._route, portfolio_id=self._portfolio_id or ""
            )
            PersonalPaperStorePaths.require_selected(self._path, selected.benchmark_db)
        canonical = self._custody.sqlite_guard(self._path)
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
        return sqlite3.connect(self._custody.io(self._path))

    def append(self, entry: EqualWeightBenchmarkEntry) -> None:
        self._require_identity(entry.benchmark_id)
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute(
                        "INSERT INTO paper_equal_weight_benchmark VALUES (?, ?, ?, ?, ?)",
                        (
                            entry.benchmark_id,
                            entry.decision_date,
                            json.dumps(entry.constituents),
                            json.dumps([(code, str(units)) for code, units in entry.units]),
                            str(entry.total_value),
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValueError("benchmark entry already exists") from exc

    def list(self, benchmark_id: str) -> tuple[EqualWeightBenchmarkEntry, ...]:
        self._require_identity(benchmark_id)
        with closing(self._connect(read_only=True)) as conn:
            rows = conn.execute(
                "SELECT * FROM paper_equal_weight_benchmark WHERE benchmark_id = ? ORDER BY decision_date",
                (benchmark_id,),
            ).fetchall()
        return tuple(
            EqualWeightBenchmarkEntry(
                benchmark_id=str(row[0]),
                decision_date=str(row[1]),
                constituents=tuple(json.loads(row[2])),
                units=tuple((code, Decimal(units)) for code, units in json.loads(row[3])),
                total_value=Decimal(str(row[4])),
            )
            for row in rows
        )


def _date(value: str) -> date:
    return date.fromisoformat(value[:10])
