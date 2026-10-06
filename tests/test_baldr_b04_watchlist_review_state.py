"""私人 Watchlist 原庫的理由／狀態 CAS 與跨程序閉環。"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from tests.test_personal_watchlist_service import _config, _payload
from app_module.personal_watchlist_service import build_watchlist_service
from app_module.watchlist_service import WatchlistService
from app_module.watchlist_review_state import (
    REVIEW_EXTENSION, REVIEW_SCHEMA, WatchlistReviewStateError,
    review_source_identity, compare_saved_items, with_review_state,
)
from ui_qt.views.watchlist_view import WatchlistView


def _active(tmp_path):
    config = _config(tmp_path)
    payload = _payload()
    payload["items"][0].update(source="recommendation", source_id="synthetic-source",
                               account_id="synthetic-account", source_snapshot_hash="a" * 64,
                               decision_identity={"stock_code": "2330", "result_id": "synthetic-r1",
                                                  "decision_date": "2026-10-05", "future_identity_extension": {"keep": True}})
    other = deepcopy(payload["items"][0])
    other.update(stock_code="2317", stock_name="其他合成股", source_id="other-source",
                 decision_identity={"stock_code": "2317", "result_id": "synthetic-r2"},
                 notes="其他理由", unknown_future_field={"keep": [1, "two"]})
    payload["items"].append(other)
    source = Path(config.personal_watchlist_source)
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    service = build_watchlist_service(config)
    service.upgrade_to_repository()
    return config, service, payload


def _review(service, code="2330"):
    row = next(row for row in service.get_stocks() if row["stock_code"] == code)
    return service.get_review_state(code, row["review_source_identity"])


def _pins(service):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in service.personal_paths.personal_root.rglob("*") if path.is_file()}


def test_cas_reason_state_preserves_other_items_unknown_fields_source_and_new_process(tmp_path):
    config, service, original = _active(tmp_path)
    source_bytes = Path(config.personal_watchlist_source).read_bytes()
    prior = _review(service)
    repository = service.repository
    before = repository.get_current("default")
    saved = service.save_review_state("2330", reason="新的私人理由", state="confirmed",
                                     expected_revision=prior.revision, sourcepins=prior.source_identity)
    after = repository.get_current("default")
    assert saved.revision == prior.revision + 1
    assert after["source_hash"] == before["source_hash"]
    assert after["payload"]["items"][1] == before["payload"]["items"][1]
    expected = deepcopy(before["payload"])
    expected["items"][0]["notes"] = "新的私人理由"
    expected["items"][0][REVIEW_EXTENSION] = {
        "schema_version": REVIEW_SCHEMA, "state": "confirmed",
        "source_identity_sha256": prior.source_identity.item_sha256,
    }
    assert after["payload"] == expected
    assert Path(config.personal_watchlist_source).read_bytes() == source_bytes
    assert _review(service) == saved
    change = service.get_same_source_change("2330", prior.source_identity,
                                           before_revision=prior.revision, after_revision=saved.revision)
    assert change.status == "changed"
    assert change.fields == ("收藏理由", "查看狀態")
    assert "非今日行情" in change.message
    child = r'''
import json, sys
from pathlib import Path
from types import SimpleNamespace
from app_module.personal_watchlist_service import build_watchlist_service
market, output, personal, source = map(Path, sys.argv[1:])
config = SimpleNamespace(data_root=market, output_root=output, personal_data_root=personal,
 personal_watchlist_source=source, resolve_data_path=lambda value: market/value)
s = build_watchlist_service(config)
row = s.get_stocks()[0]
r = s.get_review_state(row['stock_code'], row['review_source_identity'])
assert r.reason == '新的私人理由' and r.state == 'confirmed' and r.writable
print(json.dumps({'identity': r.source_identity.item_sha256, 'revision': r.revision}))
'''
    process = subprocess.run([sys.executable, "-c", child, *map(str, (
        config.data_root, config.output_root, config.personal_data_root, config.personal_watchlist_source))],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result == {"identity": saved.source_identity.item_sha256, "revision": saved.revision}
    assert repository.get_current("default")["payload"] == expected
    assert Path(config.personal_watchlist_source).read_bytes() == source_bytes


def test_stale_revision_and_sourcepins_refuse_without_overwriting_saved_state(tmp_path):
    config, service, _ = _active(tmp_path)
    other = build_watchlist_service(config)
    prior = _review(service)
    service.save_review_state("2330", reason="第一個保存", state="deferred",
                              expected_revision=prior.revision, sourcepins=prior.source_identity)
    before = _pins(service)
    with pytest.raises(WatchlistReviewStateError, match="revision_conflict"):
        other.save_review_state("2330", reason="過期不可覆寫", state="confirmed",
                                expected_revision=prior.revision, sourcepins=prior.source_identity)
    current = _review(service)
    with pytest.raises(WatchlistReviewStateError, match="identity_mismatch"):
        service.save_review_state("2317", reason="跨股不可覆寫", state="confirmed",
                                  expected_revision=current.revision, sourcepins=current.source_identity)
    assert _pins(service) == before
    assert _review(service).reason == "第一個保存"


def test_repository_cas_closes_race_after_service_read_and_changed_same_stock_pins(tmp_path, monkeypatch):
    config, service, _ = _active(tmp_path)
    concurrent = build_watchlist_service(config)
    prior = _review(service)
    original_save = service.repository.save

    def race(*args, **kwargs):
        # Synthetic repository fixture bypasses the marker lock to exercise CAS itself.
        current = concurrent.repository.get_current("default")
        payload = deepcopy(current["payload"])
        payload["items"][0] = with_review_state(
            payload["items"][0], reason="競爭程序已保存", state="deferred")
        concurrent.repository.save("default", payload, expected_revision=current["revision"],
                                   source_hash=current["source_hash"])
        return original_save(*args, **kwargs)

    monkeypatch.setattr(service.repository, "save", race)
    with pytest.raises(RuntimeError, match="revision_conflict"):
        service.save_review_state("2330", reason="晚到不可覆寫", state="confirmed",
                                  expected_revision=prior.revision, sourcepins=prior.source_identity)
    assert _review(concurrent).reason == "競爭程序已保存"
    monkeypatch.setattr(service.repository, "save", original_save)
    current = service.repository.get_current("default")
    current["payload"]["items"][0]["source_snapshot_hash"] = "b" * 64
    # 這是明示 synthetic source revision；舊 review extension 不得替新來源背書。
    service.repository.save("default", current["payload"], expected_revision=current["revision"])
    revision = current["revision"] + 1
    before = _pins(service)
    with pytest.raises(WatchlistReviewStateError, match="changed"):
        service.save_review_state("2330", reason="錯源不保存", state="confirmed",
                                  expected_revision=revision, sourcepins=prior.source_identity)
    assert _pins(service) == before


@pytest.mark.parametrize("cancel_at", [1, 2])
def test_cancel_before_cas_does_not_save(tmp_path, cancel_at):
    _, service, _ = _active(tmp_path)
    prior = _review(service)
    before = _pins(service)
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) == cancel_at

    with pytest.raises(WatchlistReviewStateError, match="cancelled"):
        service.save_review_state("2330", reason="取消", state="confirmed",
                                  expected_revision=prior.revision, sourcepins=prior.source_identity,
                                  cancel_callback=cancelled)
    assert _pins(service) == before
    assert _review(service) == prior


def test_legacy_and_unactivated_personal_readonly_refuse_review_writer(tmp_path):
    config = _config(tmp_path)
    payload = _payload()
    Path(config.personal_watchlist_source).write_text(json.dumps(payload), encoding="utf-8")
    service = build_watchlist_service(config)
    prior = _review(service)
    assert not prior.writable and prior.revision is None
    source = Path(config.personal_watchlist_source).read_bytes()
    with pytest.raises(RuntimeError, match="personal_watchlist_readonly"):
        service.save_review_state("2330", reason="不寫", state="confirmed", expected_revision=1,
                                  sourcepins=prior.source_identity)
    assert Path(config.personal_watchlist_source).read_bytes() == source
    assert not service.personal_paths.personal_root.exists()
    legacy_config = _config(tmp_path / "legacy", personal=False)
    legacy = WatchlistService(legacy_config)
    with pytest.raises(WatchlistReviewStateError, match="personal_writer_not_active"):
        legacy.save_review_state("2330", reason="不寫", state="confirmed", expected_revision=1,
                                 sourcepins=prior.source_identity)


def test_unknown_extension_is_preserved_and_unknown_review_schema_is_refused(tmp_path):
    _, service, _ = _active(tmp_path)
    current = service.repository.get_current("default")
    payload = deepcopy(current["payload"])
    pins = review_source_identity(payload["items"][0])
    payload["items"][0][REVIEW_EXTENSION] = {"schema_version": REVIEW_SCHEMA, "state": "pending",
        "source_identity_sha256": pins.item_sha256, "unknown_extension": {"keep": [1, 2]}}
    service.repository.save("default", payload, expected_revision=current["revision"])
    review = _review(service)
    service.save_review_state("2330", reason="新理由", state="confirmed",
                              expected_revision=review.revision, sourcepins=review.source_identity)
    current = service.repository.get_current("default")
    assert current["payload"]["items"][0][REVIEW_EXTENSION]["unknown_extension"] == {"keep": [1, 2]}
    current["payload"]["items"][0][REVIEW_EXTENSION]["schema_version"] = "future-unknown"
    service.repository.save("default", current["payload"], expected_revision=current["revision"])
    before = _pins(service)
    with pytest.raises(WatchlistReviewStateError, match="schema_mismatch"):
        service.get_review_state("2330", pins)
    assert _pins(service) == before


def test_saved_comparison_refuses_cross_source_account_unknown_and_never_fetches_today(tmp_path):
    _, service, _ = _active(tmp_path)
    first = service.repository.get_current("default")
    item = first["payload"]["items"][0]
    changed = deepcopy(item)
    changed["notes"] = "新理由"
    for key, value in (("stock_code", "other"), ("source_id", "other"), ("account_id", "other"), ("account_id", "")):
        wrong = deepcopy(changed)
        wrong[key] = value
        assert compare_saved_items(item, wrong, before_revision=1, after_revision=2).status == "unknown"
    prior = _review(service)
    unknown = service.get_same_source_change("2330", prior.source_identity, before_revision=100, after_revision=101)
    assert unknown.status == "unknown"


def test_offscreen_reason_confirm_defer_reopen_and_cancel_stale_dialog(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    config, service, _ = _active(tmp_path)
    view = WatchlistView(service)
    try:
        view.stocks_table.selectRow(0)
        assert view.confirm_observation_button.isEnabled()
        view.confirm_observation_button.click()
        assert _review(service).state == "confirmed"
        assert "已確認查看" in view.observation_state_label.text()
        monkeypatch.setattr("ui_qt.views.watchlist_view.QInputDialog.getText", lambda *_args, **_kw: ("私人原因", True))
        view.edit_observation_reason_button.click()
        assert _review(service).reason == "私人原因"
        view.later_observation_button.click()
        assert _review(service).state == "deferred"
        before = _pins(service)
        monkeypatch.setattr("ui_qt.views.watchlist_view.QInputDialog.getText", lambda *_args, **_kw: ("不保存", False))
        view.edit_observation_reason_button.click()
        assert _pins(service) == before

        def changed_selection(*_args, **_kwargs):
            view.stocks_table.clearSelection()
            view.stocks_table.selectRow(1)
            return "過期不保存", True

        monkeypatch.setattr("ui_qt.views.watchlist_view.QInputDialog.getText", changed_selection)
        view.edit_observation_reason_button.click()
        assert _pins(service) == before
        assert "未保存" in view.status_label.text()
        reopened = WatchlistView(build_watchlist_service(config))
        try:
            reopened.stocks_table.selectRow(0)
            assert "私人原因" in reopened.observation_reason_label.text()
            assert "稍後查看" in reopened.observation_state_label.text()
        finally:
            reopened.close()
    finally:
        view.close()
        app.processEvents()
