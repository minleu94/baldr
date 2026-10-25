from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pytest

from app_module.paper_equal_weight_benchmark_ledger import (
    EqualWeightBenchmarkEntry,
    EqualWeightBenchmarkLedger,
    EqualWeightBenchmarkService,
)
from app_module.paper_portfolio_daily_runner import PaperPriceObservation
from app_module.paper_equal_weight_benchmark_builder import PaperEqualWeightBenchmarkBuilder
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)


def _update_fixture(tmp_path: Path):
    paper_root = tmp_path / "paper_portfolio"
    paper_root.mkdir()
    baseline_path = paper_root / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "decision_date": "2026-08-20",
                "residual_cash": "900.00",
                "research_only": True,
                "writes_positions_db": False,
                "broker_order_allowed": False,
                "auto_rebalance_allowed": False,
                "allocations": [
                    {
                        "stock_code": "2330",
                        "reference_price": "100.00",
                        "executable_shares": 1,
                        "executable_amount": "100.00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_db = paper_root / "paper_portfolio.sqlite"
    repository = PaperPortfolioSnapshotRepository(state_db)
    for day, price, total in (
        ("2026-08-20", "100.00", "1000.00"),
        ("2026-08-21", "101.00", "1001.00"),
    ):
        repository.append(
            PaperPortfolioSnapshot(
                snapshot_id=f"paper-main-{day.replace('-', '')}",
                portfolio_id="paper-main",
                decision_date=day,
                source_result_id="frozen-research-source",
                cash=Decimal("900.00"),
                total_value=Decimal(total),
                positions=(
                    PaperPortfolioPositionSnapshot(
                        stock_code="2330",
                        quantity=1,
                        mark_price=Decimal(price),
                        market_value=Decimal(price),
                        weight_bp=1000,
                    ),
                ),
            )
        )
    market_db = tmp_path / "sqlite" / "twstock.db"
    market_db.parent.mkdir()
    with sqlite3.connect(market_db) as connection:
        connection.execute(
            'CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT, "收盤價" TEXT)'
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?)",
            (("2330", "20260820", "100.00"), ("2330", "20260821", "101.00")),
        )
    output = paper_root / "paper_equal_weight_benchmark.sqlite"
    builder = PaperEqualWeightBenchmarkBuilder(
        today_provider=lambda: date(2026, 8, 21)
    )
    inputs = {
        "baseline_path": baseline_path,
        "state_db_path": state_db,
        "market_db_path": market_db,
        "output_ledger_path": output,
    }
    return builder, inputs, output


def test_benchmark_freezes_initial_constituents_and_marks_equally(tmp_path: Path) -> None:
    ledger = EqualWeightBenchmarkLedger(tmp_path / "benchmark.sqlite")
    service = EqualWeightBenchmarkService()
    baseline = service.create_baseline(
        benchmark_id="paper-main-equal",
        decision_date="2026-07-10",
        capital=Decimal("100000"),
        prices={"2330": Decimal("1000"), "2317": Decimal("100")},
    )
    ledger.append(baseline)

    marked = service.mark(
        prior=baseline,
        decision_date="2026-07-11",
        prices=(
            PaperPriceObservation("2330", "2026-07-11", "2026-07-11", Decimal("1010")),
            PaperPriceObservation("2317", "2026-07-11", "2026-07-11", Decimal("90")),
            PaperPriceObservation("2454", "2026-07-11", "2026-07-11", Decimal("999")),
        ),
    )
    ledger.append(marked)

    assert marked.constituents == baseline.constituents
    assert marked.total_value == Decimal("95500.00")
    assert ledger.list("paper-main-equal") == (baseline, marked)


def test_missing_constituent_price_fails_closed() -> None:
    baseline = EqualWeightBenchmarkService().create_baseline(
        benchmark_id="b",
        decision_date="2026-07-10",
        capital=Decimal("100000"),
        prices={"2330": Decimal("1000"), "2317": Decimal("100")},
    )

    with pytest.raises(ValueError, match="missing causal benchmark price"):
        EqualWeightBenchmarkService().mark(
            prior=baseline,
            decision_date="2026-07-11",
            prices=(PaperPriceObservation("2330", "2026-07-11", "2026-07-11", Decimal("1010")),),
        )


def test_duplicate_benchmark_date_cannot_overwrite(tmp_path: Path) -> None:
    ledger = EqualWeightBenchmarkLedger(tmp_path / "benchmark.sqlite")
    entry = EqualWeightBenchmarkService().create_baseline(
        benchmark_id="b",
        decision_date="2026-07-10",
        capital=Decimal("100000"),
        prices={"2330": Decimal("1000")},
    )
    ledger.append(entry)
    with pytest.raises(ValueError, match="already exists"):
        ledger.append(entry)


def test_benchmark_update_appends_only_verified_missing_suffix(tmp_path: Path) -> None:
    builder, inputs, output = _update_fixture(tmp_path)
    first_preview = builder.preview(**inputs)
    EqualWeightBenchmarkLedger(output).append(first_preview.entries[0])

    preview = builder.preview_update(**inputs)
    assert preview.existing_count == 1
    assert preview.append_count == 1
    assert preview.append_first_date == "2026-08-21"
    assert preview.append_latest_date == "2026-08-21"
    with pytest.raises(ValueError, match="confirm"):
        builder.commit_update(preview)
    assert len(EqualWeightBenchmarkLedger(output, read_only=True).list("paper-main-equal")) == 1

    assert builder.commit_update(preview, confirm=True) == output
    saved = EqualWeightBenchmarkLedger(output, read_only=True).list("paper-main-equal")
    assert saved == first_preview.entries


def test_benchmark_update_refuses_existing_non_prefix(tmp_path: Path) -> None:
    builder, inputs, output = _update_fixture(tmp_path)
    expected = builder.preview(**inputs).entries[0]
    wrong = EqualWeightBenchmarkEntry(
        benchmark_id=expected.benchmark_id,
        decision_date=expected.decision_date,
        constituents=expected.constituents,
        units=expected.units,
        total_value=expected.total_value + Decimal("1.00"),
    )
    EqualWeightBenchmarkLedger(output).append(wrong)

    with pytest.raises(ValueError, match="not an exact prefix"):
        builder.preview_update(**inputs)
    assert EqualWeightBenchmarkLedger(output, read_only=True).list("paper-main-equal") == (wrong,)
