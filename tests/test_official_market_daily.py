import hashlib
import json
from decimal import Decimal

import pandas as pd
import pytest

from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader, MarketDateRange
from data_module.data_processor import TWMarketDataProcessor
from data_module.official_market_daily import (
    OfficialMarketDailyError,
    fetch_official_market_daily,
    update_market_index_csv,
)


_FMTQIK = "FMTQIK"
_MI_5MINS_HIST = "MI_5MINS_HIST"


def _payload(report, month, rows):
    fields = (
        ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"]
        if report == _FMTQIK
        else ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"]
    )
    return {"stat": "OK", "date": month + "01", "fields": fields, "data": rows}


def _may_payloads(*, fmt_close="20,000.50", include_29=True):
    fmt_rows = [["115/05/28", "1,234", "5,000", "6", fmt_close, "-10.25"]]
    mi_rows = [["115/05/28", "19,990.00", "20,010.00", "19,900.00", "20,000.50"]]
    if include_29:
        fmt_rows.append(["115/05/29", "2,000", "6,000", "7", "20,050.00", "49.50"])
        mi_rows.append(["115/05/29", "20,010.00", "20,070.00", "20,000.00", "20,050.00"])
    return {
        _FMTQIK: _payload(_FMTQIK, "202605", fmt_rows),
        _MI_5MINS_HIST: _payload(_MI_5MINS_HIST, "202605", mi_rows),
    }


class _Response:
    def __init__(self, payload):
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._payload = payload

    def json(self):
        return self._payload


def _requester(payloads, calls=None):
    calls = calls if calls is not None else []

    def request(url, params):
        report = _FMTQIK if url.endswith("/FMTQIK") else _MI_5MINS_HIST
        calls.append((report, params["date"]))
        payload = payloads.get(report)
        return None if payload is None else _Response(payload)

    return request, calls


def _config(tmp_path):
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="unit",
    )
    config.use_sqlite = False
    return config


def test_fetch_uses_aligned_official_ohlc_and_integer_fmtqik_volume(tmp_path):
    request, calls = _requester(_may_payloads())

    rows = fetch_official_market_daily(
        "2026-05-28", "2026-05-28", requester=request, source_dir=tmp_path,
    )

    assert calls == [("FMTQIK", "20260501"), ("MI_5MINS_HIST", "20260501")]
    assert rows == [{
        "日期": "2026-05-28",
        "收盤價": Decimal("20000.50"),
        "開盤價": Decimal("19990.00"),
        "最高價": Decimal("20010.00"),
        "最低價": Decimal("19900.00"),
        "成交量": 1234,
    }]
    assert type(rows[0]["成交量"]) is int

    manifest_path = next((tmp_path / "official_market_daily_sources").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["historical_pit"] is False
    assert len(manifest["reports"]) == 2
    for report in manifest["reports"]:
        raw = (manifest_path.parent / report["file"]).read_bytes()
        assert report["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()


def test_fetch_excludes_rows_after_requested_cutoff(tmp_path):
    request, _ = _requester(_may_payloads())

    rows = fetch_official_market_daily(
        "2026-05-28", "2026-05-28", requester=request, source_dir=tmp_path,
    )

    assert [row["日期"] for row in rows] == ["2026-05-28"]


def test_fetch_rejects_cross_report_close_mismatch_without_capture(tmp_path):
    request, _ = _requester(_may_payloads(fmt_close="20,000.51"))

    with pytest.raises(OfficialMarketDailyError, match="close 不一致"):
        fetch_official_market_daily(
            "2026-05-28", "2026-05-28", requester=request, source_dir=tmp_path,
        )

    assert not (tmp_path / "official_market_daily_sources").exists()


def test_fetch_rejects_missing_report_without_publishing_csv(tmp_path):
    payloads = _may_payloads()
    payloads[_MI_5MINS_HIST] = None
    request, _ = _requester(payloads)

    with pytest.raises(OfficialMarketDailyError, match="無回應"):
        fetch_official_market_daily(
            "2026-05-28", "2026-05-28", requester=request, source_dir=tmp_path,
        )

    assert not (tmp_path / "official_market_daily_sources").exists()
    assert not (tmp_path / "market_index.csv").exists()


def test_fetch_deduplicates_each_report_per_month_and_filters_range(tmp_path):
    may = _may_payloads()
    june = {
        _FMTQIK: _payload(_FMTQIK, "202606", [[
            "115/06/01", "3,000", "7,000", "8", "20,100.00", "50.00",
        ]]),
        _MI_5MINS_HIST: _payload(_MI_5MINS_HIST, "202606", [[
            "115/06/01", "20,050.00", "20,150.00", "20,040.00", "20,100.00",
        ]]),
    }
    calls = []

    def request(url, params):
        report = _FMTQIK if url.endswith("/FMTQIK") else _MI_5MINS_HIST
        month = params["date"][:6]
        calls.append((report, month))
        return _Response((may if month == "202605" else june)[report])

    rows = fetch_official_market_daily(
        "2026-05-28", "2026-06-01", requester=request, source_dir=tmp_path,
    )

    assert calls == [
        ("FMTQIK", "202605"), ("MI_5MINS_HIST", "202605"),
        ("FMTQIK", "202606"), ("MI_5MINS_HIST", "202606"),
    ]
    assert [row["日期"] for row in rows] == ["2026-05-28", "2026-05-29", "2026-06-01"]


def test_loader_updates_historical_gap_even_when_csv_has_later_date(tmp_path, monkeypatch):
    config = _config(tmp_path)
    pd.DataFrame([{
        "日期": "2026-05-29", "收盤價": 20050, "開盤價": 20010,
        "最高價": 20070, "最低價": 20000, "成交量": 2000,
    }]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")
    loader = DataLoader(config)
    request, calls = _requester(_may_payloads())
    monkeypatch.setattr(loader, "_make_request", request)

    assert loader.update_market_index("2026-05-28") is True

    saved = pd.read_csv(config.market_index_file, encoding="utf-8-sig")
    row = saved.loc[saved["日期"] == "2026-05-28"].iloc[0]
    assert row["開盤價"] == 19990
    assert row["最高價"] == 20010
    assert row["最低價"] == 19900
    assert row["收盤價"] == 20000.5
    assert int(row["成交量"]) == 1234
    assert calls == [("FMTQIK", "20260501"), ("MI_5MINS_HIST", "20260501")]


def test_loader_does_not_substitute_nearest_earlier_date_for_requested_future_date(
    tmp_path, monkeypatch,
):
    config = _config(tmp_path)
    loader = DataLoader(config)
    request, _ = _requester(_may_payloads())
    monkeypatch.setattr(loader, "_make_request", request)

    assert loader.update_market_index("2026-05-30") is False
    assert not config.market_index_file.exists()


def test_processor_uses_the_same_official_collector(tmp_path, monkeypatch):
    config = _config(tmp_path)
    processor = TWMarketDataProcessor(
        config, MarketDateRange("2026-05-28", "2026-05-28"),
    )
    request, _ = _requester(_may_payloads())
    monkeypatch.setattr(processor, "_make_request", request)

    assert processor.update_market_index() is True

    saved = pd.read_csv(config.market_index_file, encoding="utf-8-sig")
    assert list(saved.columns) == ["日期", "收盤價", "開盤價", "最高價", "最低價", "成交量"]
    assert saved.loc[0, "開盤價"] == 19990
    assert saved.loc[0, "最高價"] == 20010
    assert saved.loc[0, "最低價"] == 19900
    assert int(saved.loc[0, "成交量"]) == 1234


def test_csv_writer_refuses_write_when_market_index_lock_is_busy(tmp_path, monkeypatch):
    import data_module.official_market_daily as official_market_daily

    config = _config(tmp_path)
    row = {
        "日期": "2026-05-28", "收盤價": Decimal("20000.50"),
        "開盤價": Decimal("19990.00"), "最高價": Decimal("20010.00"),
        "最低價": Decimal("19900.00"), "成交量": 1234,
    }
    monkeypatch.setattr(official_market_daily, "acquire_heavy_chain_reservation", lambda _: None)

    assert update_market_index_csv(config, [row]) is False
    assert not config.market_index_file.exists()
