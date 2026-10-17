"""舊回測儲存庫的新結果須保留Decimal精度及原生產資料。"""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app_module.backtest_repository import BacktestRunRepository
from app_module.dtos import BacktestReportDTO


class _IsolatedConfig:
    def __init__(self, output_root):
        self.output_root = output_root

    def resolve_output_path(self, relative):
        return self.output_root / relative


def _report() -> BacktestReportDTO:
    index = pd.DatetimeIndex(["2026-01-02", "2026-01-05"], name="日期")
    equity = pd.DataFrame(
        {"equity": [Decimal("1000000000000000000.01"),
                    Decimal("1000000000000000000.03")]},
        index=index,
    )
    trades = pd.DataFrame(
        {"日期": ["2026-01-05"], "quantity": [1],
         "price": [Decimal("123.456789012345678901")]}
    )
    return BacktestReportDTO(
        total_return=0, annual_return=0, sharpe_ratio=0, max_drawdown=0,
        win_rate=0, total_trades=0, expectancy=0,
        details={"equity_curve": equity, "trade_list": trades},
    )


def _save(repository: BacktestRunRepository, report: BacktestReportDTO, run_id: str) -> str:
    return repository.save_run(
        run_name="隔離精度讀回", stock_code="2330", start_date="2026-01-02",
        end_date="2026-01-05", strategy_id="baseline", strategy_params={},
        capital=1000000, fee_bps=0, slippage_bps=0, stop_loss_pct=None,
        take_profit_pct=None, report=report, run_id=run_id,
    )


@pytest.mark.parametrize("attr_target", ["equity_curve", "trade_list"])
def test_decimal_attrs_save_as_parquet_and_fresh_repository_reads_exact_values(
    tmp_path, capsys, attr_target,
):
    config = _IsolatedConfig(tmp_path / "output")
    report = _report()
    report.details[attr_target].attrs = {
        "execution_contract": "next-session-open.v2",
        "execution_diagnostics": {
            "pending_limit": Decimal("12.3400"),
            "values": [Decimal("7E-20"), None],
        },
    }
    originals = {key: frame.copy(deep=True) for key, frame in report.details.items()}
    original_attrs = {key: deepcopy(frame.attrs) for key, frame in report.details.items()}
    repository = BacktestRunRepository(config)

    _save(repository, report, "decimal-attrs")
    saved = repository.load_run("decimal-attrs")

    assert saved is not None
    assert Path(saved.equity_curve_path).suffix == ".parquet"
    assert Path(saved.trade_list_path).suffix == ".parquet"
    assert "改用 CSV" not in capsys.readouterr().out
    fresh = BacktestRunRepository(config).load_run_data("decimal-attrs")
    assert fresh is not None
    assert fresh["equity_curve"]["equity"].tolist() == originals["equity_curve"]["equity"].tolist()
    assert all(isinstance(value, Decimal) for value in fresh["equity_curve"]["equity"])
    assert fresh["trade_list"]["price"].tolist() == originals["trade_list"]["price"].tolist()
    assert isinstance(fresh["trade_list"].loc[0, "price"], Decimal)
    assert fresh["equity_curve"].index.equals(originals["equity_curve"].index)
    assert fresh[attr_target].attrs == {
        "execution_contract": "next-session-open.v2",
        "execution_diagnostics": {"pending_limit": "12.3400", "values": ["7E-20", None]},
    }
    for key, original in originals.items():
        pd.testing.assert_frame_equal(report.details[key], original)
        assert report.details[key].attrs == original_attrs[key]


def test_original_csv_run_is_read_without_rewriting_or_inventing_metadata(tmp_path):
    config = _IsolatedConfig(tmp_path / "output")
    repository = BacktestRunRepository(config)
    equity_path = repository.runs_dir / "old_equity_curve.csv"
    trades_path = repository.runs_dir / "old_trades.csv"
    equity_path.write_text("date,equity\n2026-01-02,100.01\n", encoding="utf-8")
    trades_path.write_text("date,quantity,price\n2026-01-02,1,10.01\n", encoding="utf-8")
    import sqlite3

    with sqlite3.connect(repository.db_path) as connection:
        connection.execute(
            "INSERT INTO runs (run_id,run_name,equity_curve_path,trade_list_path) VALUES (?,?,?,?)",
            ("old", "舊CSV", str(equity_path), str(trades_path)),
        )
        before_row = connection.execute("SELECT * FROM runs WHERE run_id='old'").fetchone()
        before_schema = connection.execute("PRAGMA table_info(runs)").fetchall()
    before = (equity_path.read_bytes(), trades_path.read_bytes())

    old = repository.load_run_data("old")

    assert old is not None and len(old["equity_curve"]) == len(old["trade_list"]) == 1
    assert old["equity_curve"].attrs == {} and old["trade_list"].attrs == {}
    assert before == (equity_path.read_bytes(), trades_path.read_bytes())
    with sqlite3.connect(repository.db_path) as connection:
        assert connection.execute("SELECT * FROM runs WHERE run_id='old'").fetchone() == before_row
        assert connection.execute("PRAGMA table_info(runs)").fetchall() == before_schema
