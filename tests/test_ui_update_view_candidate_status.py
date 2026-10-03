import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_module.update_service import UpdateService
from ui_qt.views.update_view import UpdateView


class FakeConfig:
    def __init__(self, tmp_path: Path):
        self.use_sqlite = False
        self.data_root = tmp_path
        self.output_root = tmp_path / "output"
        self.profile = "test"
        self.log_dir = tmp_path / "logs"
        self.db_file = tmp_path / "test.db"
        self.meta_data_dir = tmp_path / "metadata"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.meta_data_dir.mkdir(parents=True, exist_ok=True)


def test_update_view_candidate_status_rendering(tmp_path):
    _app = QApplication.instance() or QApplication(sys.argv)
    mock_service = MagicMock()
    mock_service.config = FakeConfig(tmp_path)
    mock_service.scripts_dir = tmp_path / "scripts"

    view = UpdateView(update_service=mock_service)

    fake_status = {
        "institutional_flow": {
            "total_records": 1200,
            "earliest_date": "2024-07-22",
            "latest_date": "2026-07-22",
            "coverage_pct": "98.5%",
            "status": "CANDIDATE_AVAILABLE",
            "disclaimer": "候選研究資料，不參與評分",
        },
        "credit_transaction": {
            "total_records": 0,
            "earliest_date": "無",
            "latest_date": "無",
            "coverage_pct": "0.0%",
            "status": "MISSING",
            "disclaimer": "候選研究資料，不參與評分",
        },
        "tdcc_shareholding": {
            "total_records": 0,
            "earliest_date": "無",
            "latest_date": "無",
            "coverage_pct": "0.0%",
            "status": "MISSING",
            "disclaimer": "候選研究資料，不參與評分",
        },
    }

    view._on_status_checked(fake_status)

    inst_text = view.institutional_status_text.toPlainText()
    assert "候選可用" in inst_text
    assert "2024-07-22" in inst_text
    assert "候選研究資料，不參與評分" in inst_text
    # Candidate cards use the same canonical fields as the regular data cards;
    # the visible labels must not remain ``--`` when the candidate DB has rows.
    assert "2026-07-22" in view.institutional_status_text.date_label.text()
    assert "1,200" in view.institutional_status_text.records_label.text()
    assert "98.5%" in view.institutional_status_text.extra_label.text()

    credit_text = view.credit_status_text.toPlainText()
    assert "缺漏" in credit_text
    assert "候選研究資料，不參與評分" in credit_text


def test_candidate_card_displays_formal_and_candidate_lanes_separately():
    text = UpdateView._format_candidate_status_card({
        "status": "FORMAL_AVAILABLE",
        "candidate_status": "CANDIDATE_AVAILABLE",
        "formal_records": 50,
        "formal_latest_date": "2026-10-02",
        "candidate_records": 12,
        "candidate_earliest_date": "2026-09-01",
        "candidate_latest_date": "2026-09-30",
        "coverage_pct": "90.0%",
        "disclaimer": "候選資料不得升格",
    })

    assert "正式資料：50 筆，最新 2026-10-02" in text
    assert "候選資料：12 筆，最新 2026-09-30" in text
    assert "區間：2026-09-01 ~ 2026-09-30" in text


def test_candidate_increment_uses_candidate_latest_not_formal_latest(tmp_path, monkeypatch):
    _app = QApplication.instance() or QApplication(sys.argv)
    mock_service = MagicMock()
    mock_service.config = FakeConfig(tmp_path)
    mock_service.scripts_dir = tmp_path / "scripts"
    mock_service.check_decision_data_status.return_value = {
        "institutional_flow": {
            "latest_date": "2026-10-01",
            "candidate_latest_date": "2026-09-26",
        }
    }
    view = UpdateView(update_service=mock_service)
    monkeypatch.setattr(
        UpdateView, "_safe_update_end_date", staticmethod(lambda: date(2026, 10, 2))
    )

    start, end = view._candidate_update_window("institutional_flow")

    assert (start, end) == ("2026-09-27", "2026-10-02")


def test_update_service_reads_only_explicit_candidate_db(monkeypatch, tmp_path):
    config = FakeConfig(tmp_path)
    candidate_db = tmp_path / "isolated_candidate.db"
    import sqlite3

    with sqlite3.connect(candidate_db) as conn:
        conn.execute("CREATE TABLE institutional_flows (decision_date TEXT)")
        conn.execute("INSERT INTO institutional_flows VALUES ('2024-07-22')")
        conn.execute(
            """
            CREATE TABLE phase3c_backfill_checkpoints (
                decision_date TEXT, source TEXT, status TEXT
            )
            """
        )
        conn.execute("INSERT INTO phase3c_backfill_checkpoints VALUES ('2024-07-22', 'institutional', 'SUCCESS')")

    monkeypatch.setenv("PHASE3C_CANDIDATE_DB_PATH", str(candidate_db))
    original_connect = sqlite3.connect
    connect_calls = []

    def spy_connect(database, *args, **kwargs):
        connect_calls.append((database, kwargs))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    status = UpdateService(config).check_decision_data_status()

    assert status["institutional_flow"]["status"] == "CANDIDATE_AVAILABLE"
    assert status["institutional_flow"]["coverage_pct"] == "100.0%"
    assert status["credit_transaction"]["status"] == "MISSING"
    assert len(connect_calls) == 3
    assert all(
        kwargs.get("uri") is True and "mode=ro" in str(database)
        for database, kwargs in connect_calls
    )
