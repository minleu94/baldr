"""受控研究保存根的實際產製、唯讀重開與拒絕寫入邊界。"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from app_module.daily_market_universe_producer import (
    DailyMarketUniverseProductionError,
    preflight_daily_market_universe_run,
    produce_daily_market_universe_run,
)
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from tests.test_daily_market_universe_producer import (
    _enable_real_parent_writers, _request, _seed_source,
)


def _managed_request(tmp_path, monkeypatch):
    db = tmp_path / "market.sqlite"
    codes = _seed_source(db, 17)
    failures = _enable_real_parent_writers(monkeypatch)
    output = Path(__file__).resolve().parents[1] / "output" / ("ms" + uuid4().hex[:8])
    scope = ResearchCaptureWriteScope(output, db)
    request = replace(_request(db, scope.root / "daily_universe", codes), research_scope=scope)
    return request, failures


def test_managed_parent_capture_production_and_fresh_process_readonly(tmp_path, monkeypatch):
    request, failures = _managed_request(tmp_path, monkeypatch)
    db = Path(request.db_path)
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    result = produce_daily_market_universe_run(request)
    assert result.status == "complete", (result.error_code, result.cause_code)
    assert not failures
    assert result.counts["processed_count"] == 17
    assert before == (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    ref = result.parent_references[0]
    script = (
        "import json,sys; from pathlib import Path; "
        "from app_module.daily_market_universe_run import DailyMarketUniverseRunReader; "
        "from app_module.rule_research_parent_capture import read_parent_rule_sample_readiness; "
        "r=DailyMarketUniverseRunReader.open(Path(sys.argv[1]),sys.argv[2]); "
        "p=read_parent_rule_sample_readiness(sys.argv[3],sys.argv[4],"
        "universe_path=sys.argv[5],identity_sha256=sys.argv[6]); "
        "print(json.dumps({'count':r.query(page_size=25).total_count,'parent':p['status']})); r.close()"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(request.output_root), result.generation_identity_sha256,
         str(ref.snapshot_root), str(ref.capture_root), str(ref.universe_path), ref.capture_identity_sha256],
        capture_output=True, text=True, encoding="utf-8", timeout=40,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"count": 17, "parent": "saved_verified_complete"}


@pytest.mark.parametrize("invalid", ["missing_scope", "outside_scope", "wrong_source"])
def test_managed_preflight_rejects_without_creating_output(tmp_path, monkeypatch, invalid):
    request, _ = _managed_request(tmp_path, monkeypatch)
    assert request.research_scope is not None
    configured_root = Path(request.research_scope.configured_output_root)
    if invalid == "missing_scope":
        request = replace(request, research_scope=None)
    elif invalid == "outside_scope":
        request = replace(request, output_root=configured_root / "outside")
    else:
        other = tmp_path / "other.sqlite"
        _seed_source(other, 1)
        request = replace(request, db_path=other)
    with pytest.raises(DailyMarketUniverseProductionError, match="root_preflight_failed"):
        preflight_daily_market_universe_run(request)
    assert not configured_root.exists()
