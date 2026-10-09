"""新程序由隔離 COW 觀察清單嚴格重開官方研究收藏。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from app_module.watchlist_service import WatchlistService
from app_module.daily_market_technical_official_disposition_bookmark_v1 import DailyMarketTechnicalOfficialDispositionBookmarkV1
from ui_qt.views.daily_market_technical_official_disposition_view import DailyMarketTechnicalOfficialDispositionView


def main() -> None:
    output = Path(sys.argv[1])
    config = SimpleNamespace(output_root=output, resolve_output_path=lambda relative: output / relative)
    service = WatchlistService(config)
    assert service.get_storage_status().is_repository
    bookmark = service.get_research_bookmark(sys.argv[2])
    assert type(bookmark) is DailyMarketTechnicalOfficialDispositionBookmarkV1
    assert bookmark.bundle_identity_sha256 == sys.argv[3]
    assert bookmark.manifest_sha256 == sys.argv[4]
    assert bookmark.selected_stock_code == "1101"
    app = QApplication([])
    view = DailyMarketTechnicalOfficialDispositionView(None)
    try:
        view.restore_bookmark(bookmark)
        deadline = time.monotonic() + 60
        while view.active_worker is not None:
            app.processEvents()
            if time.monotonic() >= deadline:
                raise AssertionError("合成收藏重開逾時")
            time.sleep(0.01)
        app.processEvents()
        assert view.current_page is not None and view.current_request is not None
        assert view._selected_row is not None and view._selected_row.stock_code == "1101"
        assert view.current_request.to_json() == bookmark.origin_page_request_json
        assert view.current_page.historical_pit_eligible is False
        assert view.current_page.full_market_claim is False
        print(json.dumps({"status": "passed_new_process_cow_exact_ui_reopen", "pid": os.getpid(),
                          "parent_pid": os.getppid(), "stock_code": "1101", "bookmark_id": bookmark.bookmark_id,
                          "bundle_identity": bookmark.bundle_identity_sha256,
                          "query_identity": bookmark.query_identity_sha256}, sort_keys=True))
    finally:
        view.begin_shutdown()
        view.close()


if __name__ == "__main__":
    main()
