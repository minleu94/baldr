"""刷新終態不能借刷新前 cache；日期／hash／時間 guard 保留。"""
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.scheduled import run_scheduled_recommendation_snapshot as snapshot


@pytest.mark.parametrize("tamper,missing", [(False, False), (True, False), (False, True)])
def test_refreshed_terminal_selected_instead_of_expired_preinspection(tmp_path, monkeypatch, tamper, missing):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    digest = lambda path: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    node = {"path": str(new), "calendar_year": 2026, "cache_file_sha256": digest(new)}
    body = {"schema_version": "official-calendar-refresh-status.v1", "status": "refreshed",
            "candidate_only": True, "read_only": True, "forward_child_started": False,
            "forward_credit_granted": False, "production_action_allowed": False,
            "broker_order_allowed": False, "cache_root": str(tmp_path), "calendar_year": 2026,
            "observed_at": "2026-10-13T00:25:03+00:00",
            "inspection": {"selected": {"path": str(old), "file_sha256": digest(old), "calendar_year": 2026}},
            "refreshes": {} if missing else {
                "2027": {"verified": {**node, "calendar_year": 2027, "path": str(old)}},
                "2026": {"verified": node}}}
    status = tmp_path / "status.json"
    status.write_text(json.dumps(body), encoding="utf-8")
    if tamper:
        new.write_bytes(b"tampered")
    seen = []
    def verify(path, *, calendar_year, observed_at):
        seen.append(path)
        assert path == new.resolve()
        return SimpleNamespace(evidence={"path": str(new.resolve()), "calendar_year": calendar_year,
            "cache_file_sha256": digest(new), "captured_at": "2026-10-13T00:25:03+00:00"})
    monkeypatch.setattr(snapshot, "load_verified_twse_calendar_cache", verify)
    path, evidence = snapshot._resolve_forward_calendar_cache(explicit_path=None,
        refresh_status_path=status, observed_at=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
    if tamper or missing:
        assert path is None and evidence["status"] == "blocked"
        assert seen == []
    else:
        assert path == new.resolve()
        assert evidence["status"] == "verified_refresh_receipt"
        assert seen == [new.resolve()]
