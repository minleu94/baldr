from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta
import hashlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_research_screener import (
    DAILY_MARKET_RESEARCH_SOURCE_KIND,
    DailyMarketResearchCancelled,
    DailyMarketResearchScreenerService,
    evaluate_daily_market_conditions,
)
from app_module.daily_market_snapshot_repository import DailyMarketSnapshotVerificationError
from app_module.daily_market_snapshot_repository import (
    canonical_snapshot_json_bytes,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.research_session.session_store import ResearchSessionStore
from app_module.stock_research_report_service import StockResearchReportReadService


_TAIPEI = ZoneInfo("Asia/Taipei")
_CONDITIONS = ("close_above_ma20", "close_above_ma60")


def _seed_database(tmp_path: Path) -> tuple[Path, date, date]:
    database = tmp_path / "daily_market_source.db"
    first_price_date = date(2026, 7, 1)
    price_dates = tuple(
        first_price_date + timedelta(days=offset) for offset in range(65)
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                "日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT,
                "開盤價" TEXT, "最高價" TEXT, "最低價" TEXT, "收盤價" TEXT,
                "成交股數" INTEGER, "成交金額" TEXT, "漲跌價差" TEXT
            );
            CREATE TABLE technical_indicators (
                "日期" TEXT, "證券代號" TEXT, "MA20" TEXT, "MA60" TEXT
            );
            """
        )
        for code, name, close in (
            ("2330", "台積電", "101"),
            ("2317", "鴻海", "95"),
        ):
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        data_date.isoformat(),
                        code,
                        name,
                        str(int(close) - 1),
                        str(int(close) + 1),
                        str(int(close) - 2),
                        close,
                        1000,
                        "100000",
                        "0",
                    )
                    for data_date in price_dates
                ],
            )
            connection.execute(
                "INSERT INTO technical_indicators VALUES (?, ?, ?, ?)",
                (
                    price_dates[-1].isoformat(),
                    code,
                    "99" if code == "2330" else "96",
                    "102" if code == "2330" else "",
                ),
            )
    # 行情日與研究決策日分開，並不把決策日補成新的市場資料日。
    return database, price_dates[-1], price_dates[-1] + timedelta(days=1)


def _service(database: Path, snapshot_root: Path) -> DailyMarketResearchScreenerService:
    return DailyMarketResearchScreenerService(
        SimpleNamespace(
            db_file=database,
            output_root=database.parent / "formal-output-must-not-be-used",
        ),
        snapshot_root=snapshot_root,
    )


def _produce(
    monkeypatch: pytest.MonkeyPatch,
    service: DailyMarketResearchScreenerService,
    decision_date: date,
):
    # 測試只驗證小型隔離寫入，不重測磁碟 reserve gate。
    monkeypatch.setattr(
        "app_module.daily_market_snapshot_producer.resolve_heavy_chain_safety_reserve",
        lambda _reserve=None: 1,
    )
    return service.produce_snapshot(
        ("2330", "2317"),
        datetime.combine(decision_date, time(16), tzinfo=_TAIPEI),
        "controlled-daily-market",
    )


def test_produce_read_filter_and_session_context_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, price_date, decision_date = _seed_database(tmp_path)
    snapshot_root = tmp_path / "research_snapshots" / "daily_market"
    service = _service(database, snapshot_root)
    result = _produce(monkeypatch, service, decision_date)

    assert result.status in {"published_complete", "unchanged"}
    assert result.published or result.status == "unchanged"
    verified = service.read_latest("controlled-daily-market")
    assert verified.completeness == "complete_declared_cohort"
    assert set(verified.stock_snapshots) == {"2317", "2330"}

    and_rows = service.filter_rows(verified, _CONDITIONS, "and")
    or_rows = service.filter_rows(verified, _CONDITIONS, "OR")
    first, second = and_rows
    assert first.stock_code == "2317"
    assert first.data_date == price_date.isoformat()
    assert first.decision_date == decision_date.isoformat()
    assert first.completeness == "complete_declared_cohort"
    assert first.research_scope_label == "明示研究 cohort；非全市場／非正式推薦"
    assert first.research_only is True
    assert first.historical_pit_eligible is False
    assert first.conditions[0].state == "no_match"
    assert first.conditions[1].state == "unknown"
    assert first.combined_state == "no_match"
    assert len(first.why_not) == 2
    assert second.stock_code == "2330"
    assert second.combined_state == "no_match"
    assert or_rows[0].combined_state == "unknown"
    assert or_rows[1].combined_state == "match"
    assert or_rows[1].source_snapshot_hash == verified.manifest_sha256

    context = service.context_for_stock(or_rows[1], stock_name="台積電")
    assert context.source_kind == DAILY_MARKET_RESEARCH_SOURCE_KIND
    assert context.source_workspace == "recommendation"
    assert context.source_label == "每日市場研究快照（研究 cohort）"
    assert context.result_id == ""
    assert context.source_snapshot_id == verified.manifest_identity_sha256
    assert context.source_snapshot_hash == verified.manifest_sha256
    assert context.decision_date == decision_date.isoformat()
    assert context.data_date == price_date.isoformat()
    assert context.daily_snapshot_condition_keys == ",".join(_CONDITIONS)
    assert context.daily_snapshot_combine_mode == "OR"
    assert context.daily_snapshot_root == str(snapshot_root.resolve())

    session = ResearchSessionStore()
    roundtrip = session.set_stock_context(context)
    assert roundtrip.stock_context == context
    assert roundtrip.source_snapshot_hash == context.source_snapshot_hash
    assert roundtrip.daily_snapshot_root == context.daily_snapshot_root
    assert roundtrip.daily_snapshot_cohort_id == context.daily_snapshot_cohort_id
    assert roundtrip.daily_snapshot_condition_keys == context.daily_snapshot_condition_keys
    assert roundtrip.daily_snapshot_combine_mode == context.daily_snapshot_combine_mode


@pytest.mark.parametrize(
    ("mode", "left", "right", "expected"),
    [
        ("AND", "match", "unknown", "unknown"),
        ("AND", "no_match", "unknown", "no_match"),
        ("OR", "match", "unknown", "match"),
        ("OR", "no_match", "unknown", "unknown"),
    ],
)
def test_filter_uses_kleene_logic_and_keeps_each_condition(
    mode: str, left: str, right: str, expected: str
) -> None:
    evaluation = evaluate_daily_market_conditions(
        {
            "close_above_ma20": {
                "state": left,
                "relation": {
                    "match": "above",
                    "no_match": "below",
                    "unknown": "unknown",
                }[left],
                "reason": "",
            },
            "close_above_ma60": {
                "state": right,
                "relation": "unknown",
                "reason": "technical_date_mismatch",
            },
        },
        _CONDITIONS,
        mode,
    )
    assert evaluation.combined_state == expected
    assert tuple(item.state for item in evaluation.conditions) == (left, right)
    assert any("technical_date_mismatch" in reason for reason in evaluation.why_not)
    assert any("最新技術指標資料日與行情日不一致" in reason for reason in evaluation.why_not)


def test_stock_report_loads_the_exact_pinned_manifest_and_fails_closed_on_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, price_date, decision_date = _seed_database(tmp_path)
    snapshot_root = tmp_path / "research_snapshots"
    screener = _service(database, snapshot_root)
    result = _produce(monkeypatch, screener, decision_date)
    verified = screener.read_snapshot(
        "controlled-daily-market",
        decision_date,
        manifest_sha256=result.manifest_sha256,
    )
    row = screener.filter_rows(verified, _CONDITIONS, "OR")[1]
    context = screener.context_for_stock(row, stock_name="台積電")

    report_service = StockResearchReportReadService(
        SimpleNamespace(db_file=database, output_root=None),
        clock=lambda: datetime.combine(
            decision_date + timedelta(days=2), time(12), tzinfo=_TAIPEI
        ),
    )
    report = report_service.read_report("2330", context=context)
    readback = report.shared_daily_features["readback"]
    assert report.as_of == decision_date.isoformat()
    assert report.shared_daily_features["market_date"] == price_date.isoformat()
    assert readback["manifest_sha256"] == row.source_snapshot_hash
    assert readback["source_snapshot_hash"] == row.source_snapshot_hash
    assert readback["stock_code"] == row.stock_code
    assert readback["data_date"] == row.data_date
    assert readback["input_fingerprint_sha256"] == row.input_fingerprint_sha256
    assert readback["filter_evaluation"]["condition_keys"] == list(_CONDITIONS)
    assert readback["filter_evaluation"]["combine_mode"] == "OR"
    assert readback["filter_evaluation"]["combined_state"] == row.combined_state
    assert readback["filter_evaluation"]["why"] == list(row.why)
    assert readback["filter_evaluation"]["why_not"] == list(row.why_not)
    # 實際列表與個股 pinned consumer 必須保留同一方法契約及判讀資格。
    assert readback["filter_evaluation"]["conditions"] == [
        condition.to_dict() for condition in row.conditions
    ]
    assert report.shared_daily_features["method_contracts"] == verified.manifest["method_contracts"]
    assert report.shared_daily_features["method_contracts_sha256"] == verified.manifest["method_contracts_sha256"]
    for condition in row.conditions:
        binding = condition.to_dict()
        assert binding["method_id"] == f"daily_market.{condition.key}"
        assert binding["family"] == "close_vs_moving_average"
        assert binding["version"] == "1.0.0"
        assert binding["parameters"]["direction"] == "above"
        assert binding["parameters"]["window"] in (20, 60)
        assert binding["decision_date"] == decision_date.isoformat()
        assert binding["eligibility"] != "unknown"
        assert binding["unknown_reason"] == ""
    assert readback["historical_pit_eligible"] is False
    assert report.advice.saved_analysis is None
    assert report.advice.recommendation is None

    with sqlite3.connect(database) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = "103" '
            'WHERE "日期" = ? AND "證券代號" = "2330"',
            (price_date.isoformat(),),
        )
    with pytest.raises(DailyMarketSnapshotVerificationError) as stale_read:
        screener.read_snapshot(
            "controlled-daily-market",
            decision_date,
            manifest_sha256=result.manifest_sha256,
        )
    assert stale_read.value.code == "snapshot_input_hash_mismatch"
    revised = report_service.read_report("2330", context=context)
    assert revised.shared_daily_features["projection_status"] == "failed"
    assert revised.shared_daily_features["conditions"]["close_above_ma20"]["state"] == "unknown"
    assert "readback" not in revised.shared_daily_features
    assert any("重新載入" in text or "fingerprint" in text for text in revised.limitations)


def test_context_normalization_and_default_root_are_research_scoped(tmp_path: Path) -> None:
    database, _price_date, _decision_date = _seed_database(tmp_path)
    config = SimpleNamespace(
        db_file=database,
        output_root=tmp_path / "formal-output-must-not-be-used",
    )
    service = DailyMarketResearchScreenerService(config)
    assert service.snapshot_root.name == "daily_market"
    assert "research_snapshots" in service.snapshot_root.parts
    assert service.snapshot_root != config.output_root.resolve()
    context = ResearchStockContextDTO(
        stock_code="2330",
        daily_snapshot_root="  /research/root  ",
        daily_snapshot_cohort_id="  small-cohort ",
        daily_snapshot_condition_keys=" close_above_ma20, close_above_ma60,close_above_ma20 ",
        daily_snapshot_combine_mode=" or ",
    )
    assert context.daily_snapshot_root == "/research/root"
    assert context.daily_snapshot_cohort_id == "small-cohort"
    assert context.daily_snapshot_condition_keys == "close_above_ma20,close_above_ma60"
    assert context.daily_snapshot_combine_mode == "OR"


@pytest.mark.parametrize("corruption", ("method_id", "version", "parameters", "decision_date", "method_hash", "legacy_schema"))
def test_pinned_report_rejects_method_contract_corruption_without_live_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    database, _price_date, decision_date = _seed_database(tmp_path)
    snapshot_root = tmp_path / "research_snapshots"
    screener = _service(database, snapshot_root)
    _produce(monkeypatch, screener, decision_date)
    verified = screener.read_latest("controlled-daily-market")
    row = screener.filter_rows(verified, _CONDITIONS, "OR")[1]
    context = screener.context_for_stock(row)
    forged = deepcopy(dict(verified.manifest))
    method = forged["method_contracts"]["close_above_ma20"]
    if corruption == "method_id":
        method["method_id"] = "daily_market.unprovided_method"
    elif corruption == "version":
        method["version"] = "9.0.0"
    elif corruption == "parameters":
        method["parameters"]["window"] = 21
    elif corruption == "decision_date":
        forged["decision_date"] = (decision_date - timedelta(days=1)).isoformat()
    elif corruption == "method_hash":
        forged["method_contracts_sha256"] = "f" * 64
    else:
        forged["schema_version"] = "daily-market-snapshot-manifest.v1"
        del forged["method_contracts"]
        del forged["method_contracts_sha256"]
    # 重算外層 pin 也不能將錯方法契約變成合法快照。
    forged["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(forged)
    forged_bytes = canonical_snapshot_json_bytes(forged)
    forged_hash = hashlib.sha256(forged_bytes).hexdigest()
    forged_path = snapshot_root / snapshot_manifest_relpath(forged_hash)
    forged_path.write_bytes(forged_bytes)
    context = replace(context, source_snapshot_hash=forged_hash, source_snapshot_id=forged["manifest_identity_sha256"])
    inventory_before = {path.relative_to(snapshot_root): path.read_bytes() for path in snapshot_root.rglob("*.json")}
    report_service = StockResearchReportReadService(
        SimpleNamespace(db_file=database, output_root=None),
        clock=lambda: datetime.combine(decision_date + timedelta(days=2), time(12), tzinfo=_TAIPEI),
    )

    def forbidden_live_projection(**_kwargs):
        raise AssertionError("拒絕 pinned 方法契約後不得以 live 投影替代")

    monkeypatch.setattr(report_service.daily_market_feature_snapshot_service, "project", forbidden_live_projection)
    rejected = report_service.read_report("2330", context=context)
    assert rejected.shared_daily_features["projection_status"] == "failed"
    assert "readback" not in rejected.shared_daily_features
    assert rejected.shared_daily_features["conditions"]["close_above_ma20"]["state"] == "unknown"
    assert rejected.advice.saved_analysis is None
    assert rejected.advice.recommendation is None
    assert {path.relative_to(snapshot_root): path.read_bytes() for path in snapshot_root.rglob("*.json")} == inventory_before


def test_partial_method_binding_cannot_preserve_a_match() -> None:
    evaluation = evaluate_daily_market_conditions(
        {"close_above_ma20": {
            "state": "match", "relation": "above", "reason": "",
            "version": "1.0.0", "decision_date": "2026-10-02",
            "eligibility": "eligible", "unknown_reason": "",
        }},
        ("close_above_ma20",), "AND", expected_decision_date=date(2026, 10, 2),
    )
    assert evaluation.combined_state == "unknown"
    assert evaluation.conditions[0].eligibility == "unknown"
    assert evaluation.conditions[0].unknown_reason == "method_contract_invalid"


def test_cancelled_explicit_production_does_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, _price_date, decision_date = _seed_database(tmp_path)
    snapshot_root = tmp_path / "research_snapshots"
    service = _service(database, snapshot_root)
    monkeypatch.setattr(
        "app_module.daily_market_snapshot_producer.resolve_heavy_chain_safety_reserve",
        lambda _reserve=None: 1,
    )

    with pytest.raises(DailyMarketResearchCancelled):
        service.produce_snapshot(
            ("2330", "2317"),
            datetime.combine(decision_date, time(16), tzinfo=_TAIPEI),
            "cancelled-cohort",
            cancel_callback=lambda: True,
        )
    assert not (snapshot_root / "latest.json").exists()
