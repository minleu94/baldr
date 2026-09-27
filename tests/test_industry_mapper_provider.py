from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from decision_module.industry_mapper import IndustryMapper


def _write_companies(tmp_path) -> None:
    companies_file = tmp_path / "companies.csv"
    companies_file.write_text(
        "stock_id,stock_name,industry_category\n2330,合成公司,半導體業\n",
        encoding="utf-8-sig",
    )


def _config(tmp_path, *, use_sqlite: bool = True):
    return SimpleNamespace(
        meta_data_dir=tmp_path,
        industry_index_file=tmp_path / "industry_index.csv",
        use_sqlite=use_sqlite,
    )


def test_industry_mapper_uses_injected_industry_index_provider(tmp_path) -> None:
    _write_companies(tmp_path)
    provider = MagicMock(
        return_value=pd.DataFrame(
            {
                "日期": ["20260710"],
                "指數名稱": ["半導體類指數"],
                "收盤指數": [100],
            }
        )
    )
    mapper = IndustryMapper(_config(tmp_path), industry_index_provider=provider)

    provider.assert_called_once_with()
    assert mapper.industry_index_df is not None
    assert str(mapper.industry_index_df["日期"].dtype).startswith("datetime64")
    assert mapper.get_stock_industries("2330") == ["半導體業"]
    assert mapper.industry_normalization == {"半導體": "半導體類指數"}
    assert mapper.get_industry_index_name("半導體業") == "半導體類指數"


def test_industry_mapper_preserves_iso_dates_from_provider_csv_fallback(tmp_path) -> None:
    provider = MagicMock(
        return_value=pd.DataFrame(
            {
                "日期": ["2026-07-10"],
                "指數名稱": ["半導體類指數"],
                "收盤指數": [100],
            }
        )
    )
    mapper = IndustryMapper(_config(tmp_path), industry_index_provider=provider)

    assert mapper.industry_index_df is not None
    assert mapper.industry_index_df["日期"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-07-10"
    ]


def test_industry_mapper_missing_index_file_keeps_company_categories(tmp_path) -> None:
    _write_companies(tmp_path)

    mapper = IndustryMapper(_config(tmp_path, use_sqlite=False))

    assert mapper.industry_index_df is None
    assert mapper.get_stock_industries("2330") == ["半導體業"]
    assert mapper.industry_normalization == {}
    assert mapper.get_industry_index_name("半導體業") is None
    assert mapper.get_industry_performance("半導體業") is None


def test_industry_mapper_empty_index_file_keeps_company_categories(tmp_path) -> None:
    _write_companies(tmp_path)
    (tmp_path / "industry_index.csv").write_text(
        "日期,指數名稱,收盤指數\n",
        encoding="utf-8-sig",
    )

    mapper = IndustryMapper(_config(tmp_path, use_sqlite=False))

    assert mapper.industry_index_df is not None
    assert mapper.industry_index_df.empty
    assert mapper.get_stock_industries("2330") == ["半導體業"]
    assert mapper.industry_normalization == {}
    assert mapper.get_industry_index_name("半導體業") is None
    assert mapper.get_industry_performance("半導體業") is None


@pytest.mark.parametrize("index_shape", ["empty", "missing_index_name"])
def test_industry_mapper_incomplete_index_omits_index_mapping_without_losing_companies(
    tmp_path,
    index_shape: str,
) -> None:
    _write_companies(tmp_path)
    if index_shape == "empty":
        index_frame = pd.DataFrame()
    else:
        index_frame = pd.DataFrame(
            {
                "日期": ["20260710"],
                "收盤指數": [100],
            }
        )
    provider = MagicMock(return_value=index_frame)

    mapper = IndustryMapper(_config(tmp_path), industry_index_provider=provider)

    assert mapper.get_stock_industries("2330") == ["半導體業"]
    assert mapper.industry_normalization == {}
    assert mapper.get_industry_index_name("半導體業") is None
    assert mapper.get_industry_performance("半導體業") is None
