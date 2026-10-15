from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from app_module.research_run_dated_equity import (
    ResearchRunDatedEquityError,
    research_run_dated_equity_copy,
)
from app_module.research_run_dtos import ResearchRunMetadataDTO
from app_module.research_run_service import ResearchRunService
from data_module.config import TWStockConfig


def _config(tmp_path):
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
    )


def _metadata(run_id: str = "dated-equity-run") -> ResearchRunMetadataDTO:
    return ResearchRunMetadataDTO(
        run_id=run_id,
        run_name="Dated equity fixture",
        run_type="single_backtest",
        strategy_id="fixture_strategy",
        payload_hash="sha256:dated-equity-fixture",
        created_at="2026-10-14T12:00:00",
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-06-02"],
            "stock_code": ["2330"],
            "quantity": [1],
        }
    )


def test_datetime_index_becomes_saved_date_column_without_mutating_source():
    index = pd.DatetimeIndex(
        [datetime(2026, 6, 1), datetime(2026, 6, 2)], name="date"
    )
    source = pd.DataFrame(
        {
            "equity": [Decimal("1000000.00"), Decimal("1000123.45")],
            "cash": [Decimal("1000000.00"), Decimal("1000123.45")],
        },
        index=index,
    )
    source.attrs = {"producer": "fixture", "unit": "unchanged"}
    before = source.copy(deep=True)
    before_attrs = dict(source.attrs)

    dated = research_run_dated_equity_copy(source)

    assert dated.columns.tolist() == ["date", "equity", "cash"]
    assert dated["date"].tolist() == index.tolist()
    assert dated["equity"].tolist() == source["equity"].tolist()
    assert dated["cash"].tolist() == source["cash"].tolist()
    assert dated.index.equals(index)
    assert dated.attrs == before_attrs
    pd.testing.assert_frame_equal(source, before)
    assert source.attrs == before_attrs


def test_existing_date_column_is_validated_and_preserved():
    source = pd.DataFrame(
        {
            "日期": ["2026-06-01", "2026-06-02"],
            "equity": [100, 101],
        }
    )

    dated = research_run_dated_equity_copy(source)

    assert dated.columns.tolist() == ["日期", "equity"]
    assert dated["日期"].tolist() == source["日期"].tolist()
    assert dated is not source
    pd.testing.assert_frame_equal(
        source,
        pd.DataFrame(
            {"日期": ["2026-06-01", "2026-06-02"], "equity": [100, 101]}
        ),
    )


def test_real_registry_save_and_fresh_service_read_back_full_date_and_amounts(
    tmp_path,
):
    config = _config(tmp_path)
    index = pd.DatetimeIndex(
        [datetime(2026, 6, 1), datetime(2026, 6, 2), datetime(2026, 6, 3)]
    )
    source = pd.DataFrame(
        {
            "equity": [
                Decimal("1000000.00"),
                Decimal("1000123.45"),
                Decimal("999876.54"),
            ],
            "cash": [
                Decimal("1000000.00"),
                Decimal("1000123.45"),
                Decimal("999876.54"),
            ],
            "position_value": [Decimal("0.00"), Decimal("0.00"), Decimal("0.00")],
        },
        index=index,
    )
    source.attrs = {"producer": "isolated-test"}
    original = source.copy(deep=True)
    original_attrs = dict(source.attrs)
    dated = research_run_dated_equity_copy(source)

    saved = ResearchRunService(config).save_run(_metadata(), dated, _trades())
    loaded = ResearchRunService(config).load_run_data(saved.run_id)

    assert loaded.equity["date"].tolist() == index.tolist()
    assert loaded.equity["equity"].tolist() == source["equity"].tolist()
    assert loaded.equity["cash"].tolist() == source["cash"].tolist()
    assert loaded.equity["position_value"].tolist() == source["position_value"].tolist()
    assert len(loaded.equity) == len(source)
    pd.testing.assert_frame_equal(source, original)
    assert source.attrs == original_attrs


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            pd.DataFrame({"equity": [1, 2]}),
            "date/日期 欄或 DatetimeIndex",
        ),
        (
            pd.DataFrame(
                {"equity": [1, 2]},
                index=pd.DatetimeIndex(["2026-06-01", "2026-06-01"]),
            ),
            "重複日期",
        ),
        (
            pd.DataFrame(
                {"equity": [1, 2]},
                index=pd.DatetimeIndex(["2026-06-02", "2026-06-01"]),
            ),
            "嚴格遞增",
        ),
        (
            pd.DataFrame({"date": ["2026-06-01", "2026-06-01"], "equity": [1, 2]}),
            "重複日期",
        ),
        (
            pd.DataFrame({"date": ["01/02/2026", "01/03/2026"], "equity": [1, 2]}),
            "非明確日期字串",
        ),
        (
            pd.DataFrame({"date": ["2026-02-30", "2026-03-01"], "equity": [1, 2]}),
            "無效日曆日期",
        ),
        (
            pd.DataFrame({"date": [46000, 46001], "equity": [1, 2]}),
            "epoch 誤判",
        ),
        (
            pd.DataFrame({"equity": [1, 2]}, index=pd.Index([46000, 46001])),
            "epoch 誤判",
        ),
    ],
)
def test_rejects_missing_duplicate_unordered_or_ambiguous_dates(source, message):
    with pytest.raises(ResearchRunDatedEquityError, match=message):
        research_run_dated_equity_copy(source)


def test_rejects_mismatched_existing_date_column_and_datetime_index():
    source = pd.DataFrame(
        {"date": ["2026-06-01", "2026-06-03"], "equity": [1, 2]},
        index=pd.DatetimeIndex(["2026-06-01", "2026-06-02"]),
    )

    with pytest.raises(ResearchRunDatedEquityError, match="不一致"):
        research_run_dated_equity_copy(source)
