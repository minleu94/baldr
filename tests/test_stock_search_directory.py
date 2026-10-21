from pathlib import Path

import pytest

from app_module.stock_search_directory import StockSearchEntry, read_stock_search_directory


def test_name_directory_preserves_ambiguous_names_without_reading_financial_values(tmp_path: Path):
    path = tmp_path / "companies.csv"
    path.write_text("stock_id,stock_name,type,price\n2330,台積電,twse,999999\n2317,同名,twse,0\n2454,同名,tpex,0\n2330,台積電,twse,0\n", encoding="utf-8-sig")
    entries = read_stock_search_directory(path)
    assert entries == (StockSearchEntry("2317", "同名", "twse"), StockSearchEntry("2330", "台積電", "twse"), StockSearchEntry("2454", "同名", "tpex"))
    assert not hasattr(entries[0], "price")


def test_name_directory_missing_is_empty_but_bad_schema_and_cancel_are_rejected(tmp_path):
    assert read_stock_search_directory(tmp_path / "missing.csv") == ()
    path = tmp_path / "companies.csv"
    path.write_text("stock_id,stock_name\n2330,台積電\n", encoding="utf-8")
    with pytest.raises(ValueError, match="欄位"):
        read_stock_search_directory(path)
    path.write_text("stock_id,stock_name,type\n2330,台積電,twse\n", encoding="utf-8")
    with pytest.raises(ValueError, match="取消"):
        read_stock_search_directory(path, cancel_callback=lambda: True)
