from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader


class _FakeResponse:
    def __init__(self, payload: dict, *, final_url: str = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX") -> None:
        self.payload = payload
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status_code = 200
        self.url = final_url
        self.headers = {"content-type": "application/json"}

    def json(self) -> dict:
        return self.payload


def _industry_response(names: list[str]) -> dict:
    return {
        "stat": "OK",
        "date": "115年09月03日",
        "tables": [
            {
                "title": "115年09月03日 類股指數",
                "rows": [[name, "100.25", "<p style='color:red'>+</p>", "1.00", "0.50"] for name in names],
            }
        ],
    }


def _make_loader(tmp_path: Path, names: list[str]) -> DataLoader:
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
    )
    existing = pd.DataFrame(
        [
            {
                "指數名稱": "電子類指數",
                "收盤指數": 90,
                "漲跌": "+",
                "漲跌點數": 1,
                "漲跌百分比": 1,
                "日期": "2026-05-11",
            },
            {
                "指數名稱": "觀光類指數",
                "收盤指數": 90,
                "漲跌": "+",
                "漲跌點數": 1,
                "漲跌百分比": 1,
                "日期": "2026-05-11",
            },
            {
                "指數名稱": "電子工業類指數",
                "收盤指數": 99,
                "漲跌": "+",
                "漲跌點數": 1,
                "漲跌百分比": 1,
                "日期": "2026-09-02",
            },
            {
                "指數名稱": "觀光餐旅類指數",
                "收盤指數": 99,
                "漲跌": "+",
                "漲跌點數": 1,
                "漲跌百分比": 1,
                "日期": "2026-09-02",
            },
        ]
    )
    existing.to_csv(config.industry_index_file, index=False, encoding="utf-8-sig")
    loader = DataLoader(config)
    loader._make_request = lambda *_args, **_kwargs: _FakeResponse(  # type: ignore[method-assign]
        _industry_response(names)
    )
    return loader


def test_historical_retired_industry_names_do_not_trigger_warning(tmp_path, caplog):
    loader = _make_loader(
        tmp_path,
        ["電子工業類指數", "觀光餐旅類指數"],
    )

    with caplog.at_level("WARNING"):
        assert loader.update_industry_index("2026-09-03", skip_backup=True)

    assert not any("degraded" in record.message for record in caplog.records)
    updated = pd.read_csv(loader.config.industry_index_file, encoding="utf-8-sig", dtype=str)
    current = updated[updated["日期"] == "2026-09-03"]
    assert set(current["指數名稱"]) == {"電子工業類指數", "觀光餐旅類指數"}
    assert set(current["收盤指數"]) == {"100.25"}


def test_same_date_rows_are_replaced_exactly_and_capture_is_bound_to_raw_response(tmp_path):
    loader = _make_loader(
        tmp_path,
        ["電子工業類指數", "觀光餐旅類指數"],
    )
    existing = pd.read_csv(loader.config.industry_index_file, encoding="utf-8-sig")
    same_date = pd.DataFrame([
        {
            "指數名稱": "電子工業類指數",
            "收盤指數": 1,
            "漲跌": "-",
            "漲跌點數": 99,
            "漲跌百分比": 99,
            "日期": "2026-09-03",
        },
        {
            "指數名稱": "觀光餐旅類指數",
            "收盤指數": 2,
            "漲跌": "-",
            "漲跌點數": 98,
            "漲跌百分比": 98,
            "日期": "2026-09-03",
        },
    ])
    pd.concat([existing, same_date], ignore_index=True).to_csv(
        loader.config.industry_index_file,
        index=False,
        encoding="utf-8-sig",
    )
    captures: list[Path] = []

    assert loader.update_industry_index("2026-09-03", skip_backup=True, capture_manifests=captures)

    updated = pd.read_csv(loader.config.industry_index_file, encoding="utf-8-sig", dtype=str)
    current = updated[updated["日期"] == "2026-09-03"]
    assert len(current) == 2
    assert set(current["收盤指數"]) == {"100.25"}
    assert set(current["漲跌點數"]) == {"1"}
    assert len(captures) == 1
    receipt = json.loads(captures[0].read_text(encoding="utf-8"))
    raw_path = captures[0].parent.parent / receipt["raw_response_file"]
    assert receipt["raw_response_sha256"] == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert receipt["captured_at"].endswith("+00:00")
    assert receipt["available_at"] is None
    assert receipt["published_at"] is None
    assert receipt["historical_pit_eligible"] is False
    assert receipt["source_authority"] == "TWSE"
    assert "TPEx" in receipt["coverage_limit"]
    assert receipt["selected_table_titles"] == ["115年09月03日 類股指數"]


def test_missing_industry_name_is_degraded_and_same_date_csv_is_unchanged(tmp_path, caplog):
    loader = _make_loader(tmp_path, ["電子工業類指數"])

    existing_current = pd.read_csv(loader.config.industry_index_file, encoding="utf-8-sig")
    existing_current = pd.concat(
        [
            existing_current,
            pd.DataFrame(
                [
                    {
                        "指數名稱": "觀光餐旅類指數",
                        "收盤指數": 101,
                        "漲跌": "+",
                        "漲跌點數": 1,
                        "漲跌百分比": 1,
                        "日期": "2026-09-03",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    existing_current.to_csv(loader.config.industry_index_file, index=False, encoding="utf-8-sig")

    before = loader.config.industry_index_file.read_bytes()
    with caplog.at_level("WARNING"):
        assert not loader.update_industry_index("2026-09-03", skip_backup=True)

    assert any("degraded" in record.message for record in caplog.records)
    assert loader.config.industry_index_file.read_bytes() == before
    updated = pd.read_csv(loader.config.industry_index_file, encoding="utf-8-sig")
    preserved = updated[
        (updated["日期"] == "2026-09-03")
        & (updated["指數名稱"] == "觀光餐旅類指數")
    ]
    assert len(preserved) == 1


def test_response_date_mismatch_is_captured_but_never_projected(tmp_path):
    loader = _make_loader(
        tmp_path,
        ["電子工業類指數", "觀光餐旅類指數"],
    )
    before = loader.config.industry_index_file.read_bytes()
    payload = _industry_response(["電子工業類指數", "觀光餐旅類指數"])
    payload["date"] = "115年09月02日"
    loader._make_request = lambda *_args, **_kwargs: _FakeResponse(payload)  # type: ignore[method-assign]

    assert not loader.update_industry_index("2026-09-03", skip_backup=True)

    assert loader.config.industry_index_file.read_bytes() == before
    captures = list((loader.config.output_root / "industry_capture" / "twse").rglob("*.json"))
    receipt = json.loads(captures[0].read_text(encoding="utf-8"))
    assert receipt["response_date_status"] == "mismatch"
    assert receipt["parse_status"] == "rejected"
