from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from decision_module.industry_mapper import IndustryMapper
from data_module.industry_mapper_data_provider import IndustryMapperDataProvider


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


def _mapper(config, *, index_provider=None, companies_provider=None):
    reader = IndustryMapperDataProvider(config)
    return IndustryMapper(
        config,
        index_provider if index_provider is not None else reader.load_legacy_industry_index,
        companies_provider=(
            companies_provider
            if companies_provider is not None
            else reader.load_companies
        ),
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
    mapper = _mapper(_config(tmp_path), index_provider=provider)

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
    mapper = _mapper(
        _config(tmp_path), index_provider=provider, companies_provider=lambda: None
    )

    assert mapper.industry_index_df is not None
    assert mapper.industry_index_df["日期"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-07-10"
    ]


def test_industry_mapper_missing_index_file_keeps_company_categories(tmp_path) -> None:
    _write_companies(tmp_path)

    mapper = _mapper(_config(tmp_path, use_sqlite=False))

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

    mapper = _mapper(_config(tmp_path, use_sqlite=False))

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

    mapper = _mapper(_config(tmp_path), index_provider=provider)

    assert mapper.get_stock_industries("2330") == ["半導體業"]
    assert mapper.industry_normalization == {}
    assert mapper.get_industry_index_name("半導體業") is None
    assert mapper.get_industry_performance("半導體業") is None


def test_industry_mapper_keeps_positional_index_provider_and_requires_company_provider(
    tmp_path,
) -> None:
    index_provider = MagicMock(return_value=pd.DataFrame())
    company_provider = MagicMock(return_value=None)
    mapper = IndustryMapper(
        _config(tmp_path), index_provider, companies_provider=company_provider
    )

    index_provider.assert_called_once_with()
    company_provider.assert_called_once_with()
    assert mapper.industry_index_df is not None
    assert mapper.industry_index_df.empty

    untouched_provider = MagicMock(return_value=pd.DataFrame())
    with pytest.raises(ValueError, match="companies_provider"):
        IndustryMapper(_config(tmp_path), untouched_provider)
    untouched_provider.assert_not_called()


def test_industry_mapper_validates_both_callables_before_reading_either(tmp_path) -> None:
    company_provider = MagicMock(return_value=None)
    with pytest.raises(TypeError, match="must be callable"):
        IndustryMapper(
            _config(tmp_path),
            industry_index_provider=object(),
            companies_provider=company_provider,
        )
    company_provider.assert_not_called()


def test_industry_mapper_source_has_no_csv_or_database_io() -> None:
    from pathlib import Path

    source_path = Path(__file__).resolve().parents[1] / "decision_module" / "industry_mapper.py"
    source = source_path.read_text(encoding="utf-8")

    assert "pd.read_csv" not in source
    assert "DBManager" not in source
    assert "execute_query" not in source


def test_company_reader_preserves_missing_and_read_error_as_none(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    reader = IndustryMapperDataProvider(config, db_factory=lambda _: None)
    assert reader.load_companies() is None

    _write_companies(tmp_path)
    monkeypatch.setattr(pd, "read_csv", MagicMock(side_effect=OSError("bad csv")))
    assert reader.load_companies() is None


def test_main_index_reader_prefers_nonempty_sqlite_and_falls_back_to_primary_csv(
    tmp_path,
) -> None:
    config = _config(tmp_path)
    config.industry_index_file.write_text(
        "日期,指數名稱,收盤指數\n2026-07-10,CSV指數,100\n", encoding="utf-8-sig"
    )

    class Database:
        def __init__(self, frame):
            self.frame = frame

        def execute_query(self, query):
            assert query == "SELECT * FROM industry_indices ORDER BY 日期 ASC;"
            return self.frame

    sqlite_frame = pd.DataFrame([{"日期": "20260710", "指數名稱": "SQLite指數"}])
    sqlite_reader = IndustryMapperDataProvider(
        config, db_factory=lambda _: Database(sqlite_frame)
    )
    assert sqlite_reader.load_industry_index_frame()["指數名稱"].tolist() == [
        "SQLite指數"
    ]

    empty_reader = IndustryMapperDataProvider(
        config, db_factory=lambda _: Database(pd.DataFrame())
    )
    assert empty_reader.load_industry_index_frame()["指數名稱"].tolist() == [
        "CSV指數"
    ]


def test_main_and_legacy_index_reader_keep_distinct_empty_and_error_semantics(
    tmp_path, monkeypatch
) -> None:
    config = _config(tmp_path, use_sqlite=False)
    missing_reader = IndustryMapperDataProvider(config, db_factory=lambda _: None)
    assert missing_reader.load_industry_index_frame().empty
    assert missing_reader.load_legacy_industry_index() is None

    config.industry_index_file.write_text(
        "日期,指數名稱,收盤指數\n", encoding="utf-8-sig"
    )
    empty_reader = IndustryMapperDataProvider(config, db_factory=lambda _: None)
    assert empty_reader.load_industry_index_frame().empty
    legacy_empty = empty_reader.load_legacy_industry_index()
    assert legacy_empty is not None and legacy_empty.empty

    monkeypatch.setattr(pd, "read_csv", MagicMock(side_effect=OSError("bad csv")))
    with pytest.raises(OSError, match="bad csv"):
        empty_reader.load_industry_index_frame()
    assert empty_reader.load_legacy_industry_index() is None
