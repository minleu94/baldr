"""Quick 只轉交本次 TPEx 來源描述，不從舊檔補發列證據。"""

from __future__ import annotations

import json
from decimal import localcontext
from pathlib import Path
from typing import Any

import pytest

from scripts.scheduled.run_daily_data_update_quick import (
    _sync_daily_price_files_with_twse_evidence,
)


class _CaptureService:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def sync_source_to_sqlite(self, *_args: object, **kwargs: Any) -> dict[str, Any]:
        self.kwargs = kwargs
        return {"success": True}


def test_same_run_tpex_projection_is_handed_to_sqlite_without_twse_relabel() -> None:
    service = _CaptureService()
    twse = {"source_date": "20261022", "row_projection_manifest": {"sha256": "twse"}}
    tpex = {"source_date": "20261022", "row_projection_manifest": {"sha256": "tpex"}}
    _sync_daily_price_files_with_twse_evidence(
        service,
        steps=[
            {"name": "update_twse_daily_prices", "result": {"source_diagnostics": [twse]}},
            {"name": "update_tpex_daily_prices", "result": {"source_custody": [tpex]}},
        ],
        start_date="2026-10-22",
        end_date="2026-10-22",
    )
    assert service.kwargs["row_evidence_source_diagnostics"] == [twse]
    assert service.kwargs["row_evidence_tpex_source_diagnostics"] == [tpex]


@pytest.mark.parametrize("custody", [None, {}, [], [{"source_date": "20261022"}], [None]])
def test_cached_or_missing_tpex_projection_does_not_invent_evidence(custody: object) -> None:
    service = _CaptureService()
    _sync_daily_price_files_with_twse_evidence(
        service,
        steps=[{"name": "update_tpex_daily_prices", "result": {"source_custody": custody}}],
        start_date="2026-10-22",
        end_date="2026-10-22",
    )
    assert "row_evidence_tpex_source_diagnostics" not in service.kwargs


def test_actual_tpex_source_quick_and_update_service_publish_same_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.update_service import UpdateService
    from data_module.config import TWStockConfig
    from data_module.tpex_daily_price_source import TpexDailyPriceSource
    import requests

    for name in ("DATA_ROOT", "OUTPUT_ROOT", "CURRENT_OBSERVED_SOURCE_OUTPUT_ROOT"):
        monkeypatch.delenv(name, raising=False)
    config = TWStockConfig(
        data_root=tmp_path / "data", output_root=tmp_path / "output",
        profile="test", use_sqlite=True,
    )
    body = {"tables": [{"date": "1150616", "fields": ["代號", "名稱", "收盤"],
                         "data": [["3207", "耀勝", "42.50"]]}]}

    class Response:
        status_code = 200
        url = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/06/16&type=EW&response=json"
        headers = {"content-type": "application/json"}
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")

        def raise_for_status(self) -> None:
            pass

        def json(self) -> object:
            return body

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())
    source = TpexDailyPriceSource(
        output_dir=config.tpex_daily_price_dir,
        source_custody_root=config.output_root,
    )
    captured = source.update_for_date("2026-06-16")
    assert captured.success and captured.source_custody is not None
    receipt = json.loads(Path(captured.source_custody["receipt_path"]).read_bytes())
    assert receipt["requested_url"] == "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
    assert receipt["final_url"] == Response.url
    synced = _sync_daily_price_files_with_twse_evidence(
        UpdateService(config),
        steps=[{"name": "update_tpex_daily_prices",
                "result": {"source_custody": [dict(captured.source_custody)]}}],
        start_date="2026-06-16", end_date="2026-06-16",
    )
    assert synced["success"] is True
    evidence = synced["tpex_row_evidence"]
    assert evidence["status"] == "captured"
    artifact = json.loads((config.output_root / evidence["relative_path"]).read_bytes())
    assert [row["stock_code"] for row in artifact["rows"]] == ["3207"]
    assert artifact["formal_source_contract_eligible"] is False
    assert artifact["pit_eligible"] is False
    assert artifact["training_eligible"] is False


@pytest.mark.parametrize("final_url", [
    "https://example.invalid/www/zh-tw/afterTrading/otc",
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/06/15&type=EW&response=json",
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/06/16&date=2026/06/16&type=EW&response=json",
])
def test_redirect_or_changed_request_never_writes_official_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, final_url: str,
) -> None:
    from data_module.tpex_daily_price_source import TpexDailyPriceSource
    import requests

    body = {"tables": [{"date": "1150616", "fields": ["代號", "名稱", "收盤"],
                         "data": [["3207", "耀勝", "42.50"]]}]}

    class Response:
        status_code = 200
        url = final_url
        headers = {"content-type": "application/json"}
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")

        def raise_for_status(self) -> None:
            pass

        def json(self) -> object:
            return body

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())
    directory = tmp_path / "data" / "daily_price_tpex"
    result = TpexDailyPriceSource(
        output_dir=directory, source_custody_root=tmp_path / "output",
    ).update_for_date("2026-06-16")
    assert result.success is False
    assert result.source_custody is None
    assert not (directory / "20260616.csv").exists()


def test_row_fingerprint_retains_digits_under_low_decimal_context() -> None:
    from data_module.tpex_daily_price_publication import _row_hash

    left = {"收盤價": "42.500001"}
    right = {"收盤價": "42.500002"}
    baseline = _row_hash(left, ("收盤價",))
    with localcontext() as context:
        context.prec = 3
        assert _row_hash(left, ("收盤價",)) == baseline
        assert _row_hash(left, ("收盤價",)) != _row_hash(right, ("收盤價",))
        assert _row_hash({"收盤價": "42.5000"}, ("收盤價",)) == _row_hash(
            {"收盤價": "42.5"}, ("收盤價",),
        )


def test_unbounded_numeric_exponent_is_rejected_before_fingerprint_allocation() -> None:
    from data_module.tpex_daily_price_publication import _row_hash, TpexDailyPriceEvidenceError

    with pytest.raises(TpexDailyPriceEvidenceError, match="編碼上限"):
        _row_hash({"收盤價": "1e100000000"}, ("收盤價",))
