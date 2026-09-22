import importlib.util
from pathlib import Path

import pytest


def _load_audit_module():
    path = Path("scripts/audit_historical_price_spike_20260921.py")
    spec = importlib.util.spec_from_file_location("historical_price_spike_audit", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(*, symbol: str = "1256", close: str = "100", sign: str = "+") -> dict[str, object]:
    return {
        "date": "20260520",
        "symbol": symbol,
        "name": "sample",
        "source": "fixture",
        "market": "TWSE",
        "sign": sign,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume_shares": "1000",
        "turnover": "100000",
        "change_value": "0",
    }


def test_twse_filename_fallback_and_date_normalization(tmp_path: Path) -> None:
    module = _load_audit_module()
    path = tmp_path / "20260520.csv"
    path.write_text(
        "證券代號,證券名稱,開盤價,最高價,最低價,收盤價,成交股數,成交金額,漲跌價差,漲跌(+/-)\n"
        "1256,測試,100,101,99,100,1000,100000,0,+\n",
        encoding="utf-8",
    )

    rows = module._load_csv_file(
        path,
        source="twse_raw",
        market="TWSE",
        fallback_date=module._filename_date(path),
    )

    assert rows[0]["date"] == "20260520"
    assert rows[0]["symbol"] == "1256"
    assert module._date_key("2026-05-20") == "20260520"
    assert module._date_key("2026/05/20") == "20260520"


def test_dual_sign_columns_use_nonempty_direction() -> None:
    module = _load_audit_module()
    row = module._row_from_mapping(
        {
            "證券代號": "1256",
            "證券名稱": "測試",
            "開盤價": "100",
            "最高價": "101",
            "最低價": "99",
            "收盤價": "100",
            "成交股數": "1000",
            "成交金額": "100000",
            "漲跌價差": "0",
            "漲跌(+/-)": "",
            "漲跌": "-",
        },
        date_value="20260520",
        source="sqlite",
        market="TWSE",
    )

    assert row["sign"] == "-"
    assert row["sign_candidates"] == {"漲跌(+/-)": "", "漲跌": "-"}


def test_compare_sources_separates_numeric_and_sign_differences() -> None:
    module = _load_audit_module()
    left = [_row(symbol="1256", close="100", sign="+"), _row(symbol="1477", close="100", sign="+")]
    right = [_row(symbol="1256", close="100", sign="-"), _row(symbol="1477", close="101", sign="-")]

    result = module._compare_sources(
        left,
        right,
        left_name="sqlite",
        right_name="canonical",
        include_market=True,
    )

    assert result["mismatch_count"] == 2
    assert result["numeric_value_mismatch_count"] == 1
    assert result["sign_only_mismatch_count"] == 1
    assert result["numeric_and_sign_mismatch_count"] == 1
    assert result["difference_field_counts"]["close"] == 1
    assert result["difference_field_counts"]["sign"] == 2


def test_empty_merged_source_is_completed_and_not_not_run(tmp_path: Path) -> None:
    module = _load_audit_module()
    path = tmp_path / "stock_data_whole.csv"
    path.write_text("日期,證券代號,收盤價\n", encoding="utf-8")

    rows, metadata = module._load_merged_rows(
        path,
        start_date="20260501",
        end_date="20260630",
    )

    assert rows == []
    assert metadata["status"] == "completed"
    assert metadata["row_count"] == 0


def test_output_guard_rejects_source_subtree_and_symlink(tmp_path: Path) -> None:
    module = _load_audit_module()
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="inside a source root"):
        module._validate_output_dir(source / "qa", [source])

    class SymlinkCandidate:
        def expanduser(self):
            return self

        def is_symlink(self):
            return True

    with pytest.raises(ValueError, match="symlink"):
        module._validate_output_dir(SymlinkCandidate(), [source])
