"""BB 條件跨頁、unknown 篩選與下鑽返回均保留同一來源。"""
import os
from dataclasses import replace
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from app_module.daily_research_source_selection import DailyResearchQuery
from ui_qt.shared_market_research_consumer import SharedMarketResearchConsumer, shared_market_research_frame
from tests.test_baldr_bbands_research_view import _saved, _view, METHOD
from tests.test_shared_market_research_consumers import _wait_for


def test_saved_v3_query_and_exact_return(tmp_path):
    app = QApplication.instance() or QApplication([])
    snapshot, _ = _saved(tmp_path, variant="warmup")
    view, service = _view(snapshot, tmp_path / "snapshots")
    consumer = SharedMarketResearchConsumer()
    received, failures, contexts = [], [], []
    consumer.resultReady.connect(received.append)
    consumer.failed.connect(failures.append)
    consumer.set_source(view)
    query = DailyResearchQuery(snapshot.manifest_sha256, snapshot.manifest_identity_sha256,
        (METHOD,), "OR", "unknown", "bbands30_upper", True)
    assert view.restore_research_query(query)
    consumer.request()
    assert _wait_for(app, lambda: consumer._worker is None)
    assert not failures, failures
    read = received[-1]
    assert read.query == query
    assert len(read.projection.method_counts) == 3
    frame = shared_market_research_frame(read)
    assert frame["證券代號"].tolist() == ["2382"]
    assert frame.iloc[0]["條件結果"] == "未知"
    view.stockResearchRequested.connect(contexts.append)
    assert view.open_stock_from_shared_query("2382", query)
    assert contexts[0].daily_snapshot_condition_keys == METHOD
    assert contexts[0].source_snapshot_hash == query.manifest_sha256
    assert view.restore_research_query(replace(query, filter_state="all", descending=False))
    assert view.restore_research_snapshot_stock("2382", query.manifest_sha256)
    assert view.current_research_query() == query
    assert not view.open_stock_from_shared_query("2382", replace(query, manifest_sha256="f" * 64))
    assert service.produced == []
    assert consumer.begin_shutdown()
    assert view.begin_shutdown()
    view.close()
