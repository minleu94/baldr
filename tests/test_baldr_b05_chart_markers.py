"""B05 身份與時點正負例；資料全部合成，不讀實際帳本。"""
from dataclasses import replace
from decimal import Decimal

import pytest

from app_module.stock_research_chart_markers import (
    StockChartMarkerDTO, StockChartMarkerIdentityDTO, StockChartMarkerKind,
    stock_chart_marker_fingerprint, verified_stock_chart_markers,
)
from app_module.stock_research_external_chart import stock_external_chart_link
from tests.test_stock_research_chart_payload import _point, _report, _CONTEXT
from app_module.stock_research_chart_payload import project_stock_chart_payload


def evidence(kind=StockChartMarkerKind.RECOMMENDATION_CONFIRMED):
    marker = StockChartMarkerDTO("record-1", kind, "2330", "2026-10-08", "synthetic.record", "b" * 64,
        "account-1", "research" if kind == StockChartMarkerKind.RECOMMENDATION_CONFIRMED else "actual",
        "2026-10-08T15:00:00+08:00", tuple(sorted(_CONTEXT.items())))
    marker = replace(marker, content_sha256=stock_chart_marker_fingerprint(marker))
    pin = StockChartMarkerIdentityDTO(marker.record_id, marker.kind, marker.stock_code,
        marker.event_date, marker.source_id, marker.source_row_hash, marker.account_id,
        marker.account_kind, marker.source_context, marker.available_at)
    return marker, pin


def project(marker, pin):
    return verified_stock_chart_markers((marker,), (pin,), stock_code="2330", cutoff_date="2026-10-08",
        source_context=tuple(sorted(_CONTEXT.items())), price_points=(_point("2026-10-08"),))


@pytest.mark.parametrize("kind", list(StockChartMarkerKind))
def test_marker_positive_identity_and_same_exact_payload(kind):
    marker, pin = evidence(kind)
    assert project(marker, pin) == (marker,)
    report = _report(_point("2026-10-08"))
    result = project_stock_chart_payload(report, marker_candidates=(marker,), marker_identities=(pin,))
    assert result.payload.verified_markers == (marker,)
    assert result.payload.table_rows == report.price_points
    assert result.payload.historical_pit_eligible is False
    assert "研究" in marker.label if kind == StockChartMarkerKind.RECOMMENDATION_CONFIRMED else "實際記錄" in marker.label


@pytest.mark.parametrize("field,value", [
    ("stock_code", "2317"), ("event_date", "2026-10-07"), ("source_id", "other"),
    ("source_row_hash", "a" * 64), ("record_id", "other"), ("account_id", "other"),
    ("account_kind", "paper"), ("kind", StockChartMarkerKind.RECORDED_BUY),
    ("source_context", (("source_kind", "other"),)),
])
def test_each_independent_pin_mismatch_rejected(field, value):
    marker, pin = evidence()
    assert project(marker, replace(pin, **{field: value})) == ()


@pytest.mark.parametrize("field,value", [
    ("account_id", ""), ("source_id", ""), ("record_id", ""),
    ("available_at", ""), ("available_at", "2026-10-08T15:00:00"),
    ("available_at", "2026-10-09T00:00:00+08:00"),
    ("available_at", "2026-10-07T15:00:00+08:00"),
    ("event_date", "2026-10-09"), ("account_kind", "paper"),
    ("source_row_hash", ""), ("content_sha256", ""),
])
def test_missing_and_late_identity_never_drawn(field, value):
    marker, pin = evidence(StockChartMarkerKind.RECORDED_BUY)
    changed = replace(marker, **{field: value})
    assert project(changed, pin) == ()


def test_tampered_record_even_with_matching_pin_hash_rejected():
    marker, pin = evidence()
    changed = replace(marker, available_at="2026-10-08T16:00:00+08:00")
    assert project(changed, pin) == ()


def test_missing_scope_pin_and_duplicate_identity_rejected():
    marker, pin = evidence()
    kwargs = dict(stock_code="2330", cutoff_date="2026-10-08", source_context=marker.source_context,
                  price_points=(_point("2026-10-08"),))
    assert verified_stock_chart_markers((marker,), (), **kwargs) == ()
    assert verified_stock_chart_markers((marker,), (pin,pin), **kwargs) == ()
    assert verified_stock_chart_markers((marker,marker), (pin,), **kwargs) == ()
    assert verified_stock_chart_markers((marker,), (pin,), **{**kwargs,"source_context":()}) == ()
    assert verified_stock_chart_markers((marker,), (pin,), **{**kwargs,"price_points":(replace(_point("2026-10-08"),close_price=None),)}) == ()


@pytest.mark.parametrize("code,exchange", [("2382","TWSE"),("1477","TWSE"),("6488","TPEX"),("00878","TWSE"),("IX0001","TWSE")])
def test_external_only_verified_website_identity(code, exchange):
    link=stock_external_chart_link(code)
    assert link.exchange==exchange and link.symbol==code
    assert link.url==f"https://tw.tradingview.com/symbols/{exchange}-{code}/"
    assert link.same_source is False and link.historical_pit_eligible is False
    assert "UX07" in link.identity_source


@pytest.mark.parametrize("code",["2330","UNKNOWN","TWSE:2382","2382?account=private","../2382",""])
def test_external_unknown_or_injected_symbol_disabled(code):
    assert stock_external_chart_link(code) is None


@pytest.mark.parametrize("field,value", [
    ("available_at", "2026-10-08T16:00:01+00:00"),
    ("available_at", "2026-10-08T15:00:00"),
    ("available_at", "2026-10-07T15:00:00+08:00"),
    ("account_kind", "paper"), ("account_id", ""), ("source_id", ""),
])
def test_matching_pins_and_rehashed_record_still_cannot_bypass_guards(field,value):
    marker,pin=evidence(StockChartMarkerKind.RECORDED_BUY)
    marker=replace(marker,**{field:value})
    marker=replace(marker,content_sha256=stock_chart_marker_fingerprint(marker))
    pin=replace(pin,source_row_hash=marker.source_row_hash,**({field:value} if hasattr(pin,field) else {}))
    assert project(marker,pin)==()


def test_marker_has_bounded_input_and_rejects_unknown_kind():
    marker,pin=evidence()
    kwargs=dict(stock_code="2330",cutoff_date="2026-10-08",source_context=marker.source_context,
                price_points=(_point("2026-10-08"),))
    assert verified_stock_chart_markers((marker,)*129,(pin,),**kwargs)==()
    assert project(replace(marker,kind="unknown"),pin)==()
