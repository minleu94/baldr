"""明示保存 bundle 四群組正式入口的單次來源讀取與取消回歸。"""
from pathlib import Path
import sys
import pytest
import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader
import app_module.daily_market_technical_official_disposition_composite_query_v1 as composite
from app_module.daily_market_technical_official_disposition_bundle_v1 import DailyMarketTechnicalOfficialDispositionBundleReaderV1
_REPO = next(p for p in Path(__file__).resolve().parents if (p / "tests").is_dir() and (p / "app_module").is_dir())
if str(_REPO / "tests") not in sys.path:
    sys.path.insert(0, str(_REPO / "tests"))
pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)

def test_bundle_entry_issues_full_group_with_one_exact_read(monkeypatch, bundle_fixture, exact_query):
    calls = []
    original = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact
    def observed(instance, *args, **kwargs):
        calls.append((args, kwargs.get("technical_read_session_builder")))
        return original(instance, *args, **kwargs)
    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_exact", observed)
    def forbidden(*args, **kwargs):
        raise AssertionError("不可先走 legacy opener 或 query opener 再重開來源")
    monkeypatch.setattr(reader, "open_daily_market_technical_official_disposition_bundle_session_v1", forbidden)
    monkeypatch.setattr(reader, "open_daily_market_technical_official_disposition_projection_group_session_v2", forbidden)
    session = reader.open_daily_market_technical_official_disposition_bundle_projection_group_session_v2(
        bundle_output_root=exact_query.bundle_output_root,
        bundle_identity_sha256=exact_query.bundle_identity_sha256,
        expected_manifest_sha256=exact_query.expected_manifest_sha256,
        row_scope_filter=exact_query.row_scope_filter,
    )
    assert len(calls) == 1 and calls[0][1] is not None
    assert session.query.to_json() == exact_query.to_json()
    group = session.projection_group_session
    assert group is not None
    assert len(group.ma_index.entries) == len(group.kdj_entries) == len(group.volatility_entries) == 257
    query = composite.DailyMarketTechnicalOfficialDispositionCompositeQueryV1.create(
        session.query, projection_group_session_identity_sha256=group.identity_sha256,
        condition_combine_mode="AND", unknown_policy="include",
    )
    result = session.execute_composite_query_v1(query)
    population = result.counts.base_f17_counts.population
    assert (population.declared_count, population.included_count, population.processed_count, population.excluded_count) == (258,257,257,1)
    assert result.visible_count == 258
    pages = (result.read_page(0,256), result.read_page(1,256))
    codes = tuple(row.fact_row.stock_code for page in pages for row in page.rows)
    assert codes == (*bundle_fixture.included_codes, bundle_fixture.excluded_code)
    assert len(calls) == 1

def test_cancel_before_bundle_entry_does_not_read_metadata(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("取消後不得讀來源")
    monkeypatch.setattr(DailyMarketTechnicalOfficialDispositionBundleReaderV1, "read_manifest_metadata", forbidden)
    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
        reader.open_daily_market_technical_official_disposition_bundle_projection_group_session_v2(
            bundle_output_root="unused", bundle_identity_sha256="1"*64,
            expected_manifest_sha256="2"*64, row_scope_filter=("included_processed",),
            cancel_callback=lambda: True,
        )
