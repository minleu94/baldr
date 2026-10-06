"""來源選擇器以合成資料驗證真 service 讀回及取消舊回呼。"""
import os
from types import SimpleNamespace
from threading import Event
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui_qt.widgets.daily_research_source_selector import DailyResearchSourceSelector
from tests.test_shared_market_research_consumers import _wait_for
from tests.test_daily_market_research_screener import _seed_database, _service, _produce


def test_selector_reads_existing_snapshot_without_hash_input(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db, _, day = _seed_database(tmp_path)
    root = tmp_path / "output" / "research_snapshots" / "daily_market"
    produced = _produce(monkeypatch, _service(db, root), day)
    widget = DailyResearchSourceSelector(SimpleNamespace(db_file=db, output_root=tmp_path / "output"))
    received = []
    widget.sourceLoaded.connect(received.append)
    widget.refresh_sources()
    assert _wait_for(app, lambda: widget._worker is None)
    assert widget.sources.count() == 1, widget.status.text()
    widget.open_selected()
    assert _wait_for(app, lambda: widget._worker is None)
    assert received[0][1].manifest_sha256 == produced.manifest_sha256
    assert widget.begin_shutdown()
    widget.close()


def test_cancelled_result_does_not_replace_source_list(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = DailyResearchSourceSelector(SimpleNamespace(output_root=tmp_path))
    gate = Event()
    applied = []
    widget._start(lambda cancel_callback=None: gate.wait(2), applied.append)
    widget.cancel()
    gate.set()
    assert _wait_for(app, lambda: widget._worker is None)
    assert applied == []
    assert widget.begin_shutdown()
    widget.close()

