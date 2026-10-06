"""保存來源沿原 repository/service 讀回，拒絕混入其他來源。"""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from app_module.daily_research_source_selection import (
    list_daily_research_sources, resolve_daily_research_source_selection,
    read_selected_daily_research_source, DailyResearchQuery,
)
from tests.test_daily_market_research_screener import _seed_database, _service, _produce


def test_original_root_discovery_strict_read_and_query_pin(tmp_path, monkeypatch):
    db, _, day = _seed_database(tmp_path)
    root = tmp_path / "output" / "research_snapshots" / "daily_market"
    service = _service(db, root)
    produced = _produce(monkeypatch, service, day)
    config = SimpleNamespace(db_file=db, output_root=tmp_path / "output")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*.json")}
    sources = list_daily_research_sources(config, snapshot_root=root)
    assert len(sources) == 1  # 重複的同根不重列。
    selected = sources[0]
    assert selected.manifest_sha256 == produced.manifest_sha256
    reader, snapshot = read_selected_daily_research_source(selected, config)
    assert reader.snapshot_root == root
    query = DailyResearchQuery(snapshot.manifest_sha256, snapshot.manifest_identity_sha256,
        ("close_above_ma20",), "OR", "unknown", "close", True, "2317")
    query.assert_snapshot(snapshot)
    with pytest.raises(ValueError, match="query_snapshot_changed"):
        replace(query, manifest_sha256="f" * 64).assert_snapshot(snapshot)
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == saved for p, saved in before.items())
    assert list_daily_research_sources(config, cancel_callback=lambda: True) == ()


def test_wrong_schema_and_changed_source_fail_explicitly(tmp_path, monkeypatch):
    db, _, day = _seed_database(tmp_path)
    root = tmp_path / "snapshots"
    produced = _produce(monkeypatch, _service(db, root), day)
    path = root / "manifests" / f"{produced.manifest_sha256}.json"
    selected = resolve_daily_research_source_selection(path)
    path.write_text('{"schema_version":"recommendation_snapshot.v1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="source_schema_is_not_daily_market"):
        resolve_daily_research_source_selection(path)
    with pytest.raises(Exception):
        read_selected_daily_research_source(selected, SimpleNamespace(db_file=db))

