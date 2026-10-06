"""隔離唯讀 SQLite→既有 MA producer→完整樣本／receipt→readiness。"""
from datetime import datetime, time, timedelta
import hashlib
import json
import os
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app_module.daily_market_snapshot_repository import DailyMarketSnapshotRepository
from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter, SAFETY_RESERVE_BYTES
from app_module.rule_research_sample_readiness import project_rule_sample_readiness, read_saved_rule_sample_readiness
from tests.test_daily_market_snapshot_consumer import _seed
from tests.test_rule_research_sample_capture import _fixture


def test_actual_readonly_sqlite_cli_capture_repeat_and_source_revision(tmp_path, monkeypatch, capsys):
    import scripts.produce_daily_market_research_snapshot as cli
    from app_module.daily_market_snapshot_producer import DailyMarketSnapshotProducer
    db, day = _seed(tmp_path)
    root, store = tmp_path / "snapshot", tmp_path / "capture"
    cutoff = datetime.combine(day, time(16), tzinfo=ZoneInfo("Asia/Taipei"))
    as_of = cutoff + timedelta(days=1)
    class ControlledProducer(DailyMarketSnapshotProducer):
        def __init__(self, root):
            super().__init__(root,
                capacity_probe=lambda p: {"probe_path": str(p), "total_bytes": SAFETY_RESERVE_BYTES * 4,
                    "used_bytes": 0, "free_bytes": SAFETY_RESERVE_BYTES * 4})
    monkeypatch.setattr(cli, "DailyMarketSnapshotProducer", ControlledProducer)
    monkeypatch.setattr(cli, "_isolated_output", lambda _p: root)
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda _s: SAFETY_RESERVE_BYTES * 4)
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    args = ["--db-path", str(db), "--output-root", str(root), "--cohort-id", "controlled",
        "--decision-cutoff", cutoff.isoformat(), "--symbols", "2382", "1477",
        "--capture-root", str(store), "--capture-as-of", "observed-now"]
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["sample_capture"]["status"] == "published"
    ready = first["sample_readiness"]
    assert ready["status"] == "saved_verified" and ready["represented_denominator"] == 2
    assert all(c["matched"] + c["notmatched"] + c["unknown"] + c["excluded"] == 2 for c in ready["method_counts"])
    assert ready["source_availability"] == ready["market_calendar"] == ready["outcome_maturity"] == "unknown"
    assert ready["mature_outcomes"] is None and not ready["training_eligible"]
    args[-1] = ready["as_of"]
    assert cli.main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["sample_capture"]["status"] == "duplicate"
    assert second["sample_readiness"]["receipt"] == ready["receipt"]
    assert before == (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    # 只修改本測試擁有的合成來源；同日修訂保留兩包，不覆寫首次樣本。
    import sqlite3
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE daily_prices SET 收盤價='103' WHERE 日期=?", (day.isoformat(),))
    args[-1] = "observed-now"
    assert cli.main(args) == 0
    revised = json.loads(capsys.readouterr().out)
    assert revised["sample_readiness"]["capture_identity_sha256"] != ready["capture_identity_sha256"]
    assert len(list(store.glob("*/receipt.json"))) == 2
    monkeypatch.setattr(BoundedRuleResearchCaptureWriter, "_free_bytes", lambda _s: 0)
    assert cli.main(args) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["sample_capture_status"] == "rejected"
    assert rejected["sample_capture_error"]["code"] == "capacity_reserve"
    assert rejected["manifest_sha256"] == revised["manifest_sha256"]
    assert "sample_readiness" not in rejected
    assert len(list(store.glob("*/receipt.json"))) == 2


def test_cli_large_population_rejected_before_source_read(tmp_path, capsys):
    from scripts.produce_daily_market_research_snapshot import main
    assert main(["--db-path", str(tmp_path / "absent.db"), "--output-root",
        "output/qa/ux20_rejected_large", "--cohort-id", "large", "--decision-cutoff",
        "2026-09-01T16:00:00+08:00", "--symbols", *[str(1000+i) for i in range(17)]]) == 2
    assert "parent manifest" in capsys.readouterr().out


def test_projection_and_saved_consumer_reject_wrong_asof(tmp_path, monkeypatch):
    repo, _, capture = _fixture(tmp_path)
    writer = BoundedRuleResearchCaptureWriter(tmp_path / "store")
    monkeypatch.setattr(writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES * 4)
    body = capture.to_dict()
    writer.write(capture, revalidate=lambda: capture)
    assert project_rule_sample_readiness(capture)["status"] == "projection_only"
    with pytest.raises(ValueError):
        read_saved_rule_sample_readiness(writer, repo, identity_sha256=capture.identity_sha256,
            manifest_sha256=body["snapshot_sha256"], cohort_id=repo.load_manifest(body["snapshot_sha256"],
                body["cohort_id"], datetime.fromisoformat(body["decision_date"]).date()).cohort_id,
            decision_date=datetime.fromisoformat(body["decision_date"]).date(),
            as_of=datetime.fromisoformat(body["as_of"]) + timedelta(seconds=1))


def test_existing_ma_page_readiness_is_pure_and_clears(tmp_path):
    from PySide6.QtWidgets import QApplication
    from ui_qt.views.daily_market_research_view import DailyMarketResearchView
    app = QApplication.instance() or QApplication([])
    _, snapshot, _ = _fixture(tmp_path)
    view = DailyMarketResearchView()
    view._accept_snapshot(snapshot, sync_cutoff=False)
    text = view.sample_readiness_label.text()
    assert "完整聲明單批 3 檔" in text and "排除 1" in text and "尚未保存" in text
    assert json.loads(view.sample_readiness_label.toolTip())["selection_status"] == "unknown"
    view._clear_current_snapshot()
    assert "來源已清除" in view.sample_readiness_label.text()
    assert not list(tmp_path.glob("**/receipt.json"))
    view.close()
    app.processEvents()
