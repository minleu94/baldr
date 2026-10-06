"""BBUI01 version-aware 原收藏 codec 的保存、相容與拒收證據。"""
from copy import deepcopy
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from app_module.daily_market_research_bookmark import (
    DailyMarketResearchBookmarkError, create_daily_market_research_bookmark,
    decode_daily_market_research_bookmark,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.daily_market_snapshot_repository import canonical_snapshot_sha256, snapshot_manifest_identity_sha256
from app_module.daily_market_method_contract import method_contracts_sha256
from app_module.watchlist_service import WatchlistService
from tests.test_baldr_bbands_research_view import _saved, METHOD, V2, V3

BASE = "d222ba0dbd3e87991ba5404fec29470646af2c68"


def _row(snapshot, root, keys):
    return DailyMarketResearchScreenerService(SimpleNamespace(db_file="unused"), root).filter_rows(snapshot, keys, "AND")[0]


def _config(tmp_path):
    return SimpleNamespace(output_root=tmp_path / "personal", resolve_output_path=lambda name: tmp_path / "personal" / name)


def _repin(payload):
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    payload["payload_sha256"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return payload



def _rebind_query(payload):
    def sha(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    query = {key: payload[key] for key in ("source_snapshot_id", "source_snapshot_hash", "snapshot_root",
        "cohort_id", "decision_date", "declared_stock_codes", "condition_keys", "combine_mode",
        "filter_state", "sort_key", "descending")}
    payload["query_sha256"] = sha(query)
    identity = {key: payload[key] for key in ("schema_version", "stock_code", "source_snapshot_id",
        "source_snapshot_hash", "decision_date", "cohort_id", "filter_state", "query_sha256")}
    payload["bookmark_id"] = "dmarket-" + sha(identity)
    payload["source_id"] = payload["bookmark_id"]
    payload["context"].update(source_id=payload["bookmark_id"], source_snapshot_hash=payload["source_snapshot_hash"],
        daily_snapshot_root=payload["snapshot_root"])
    return payload

def test_v2_body_context_and_all_hashes_equal_immutable_base_codec(tmp_path):
    snapshot, _ = _saved(tmp_path, V2)
    row = _row(snapshot, tmp_path / "snapshots", ("close_above_ma20", "close_above_ma60"))
    # 以固定 commit 原碼為 oracle，不以 mutable HEAD 或新 codec 複製算法。
    original = subprocess.run(["git", "show", f"{BASE}:app_module/daily_market_research_bookmark.py"],
        capture_output=True, check=True).stdout.decode("utf-8")
    legacy = ModuleType("_bbui01_frozen_bookmark_oracle")
    sys.modules[legacy.__name__] = legacy
    try:
        exec(compile(original, f"{BASE}:daily_market_research_bookmark.py", "exec"), legacy.__dict__)
        before = legacy.create_daily_market_research_bookmark(snapshot, row, sort_key="ma60", descending=True)
        after = create_daily_market_research_bookmark(snapshot, row, sort_key="ma60", descending=True)
        assert after.to_dict() == before.to_dict()
        assert after.payload_sha256 == before.payload_sha256
        assert after.query_sha256 == before.query_sha256
        assert after.bookmark_id == before.bookmark_id
        assert decode_daily_market_research_bookmark(before.to_dict()).to_dict() == before.to_dict()
    finally:
        sys.modules.pop(legacy.__name__, None)


@pytest.mark.parametrize("variant", ["match", "no_match", "warmup", "missing", "source"])
def test_v3_json_store_readback_fresh_process_and_exact_identity(tmp_path, variant):
    snapshot, source = _saved(tmp_path, V3, variant)
    root = tmp_path / "snapshots"
    source_before = source.read_bytes(), source.stat().st_mtime_ns
    pins = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*.json")}
    row = _row(snapshot, root, (METHOD,))
    bookmark = create_daily_market_research_bookmark(snapshot, row, sort_key="bbands30_upper")
    payload = bookmark.to_dict()
    assert payload["schema_version"] == "daily-market-research-bookmark.v1"
    assert payload["result_id"] == ""
    assert payload["method_contracts"] == snapshot.manifest["method_contracts"]
    config = _config(tmp_path)
    service = WatchlistService(config)
    assert service.add_research_bookmark(bookmark).status == "added"
    saved_bytes = service.default_watchlist_file.read_bytes()
    assert service.add_research_bookmark(bookmark).status == "already_present"
    assert service.default_watchlist_file.read_bytes() == saved_bytes
    reopened = WatchlistService(config).get_research_bookmark(bookmark.bookmark_id)
    assert reopened.to_dict() == payload
    context = reopened.context
    assert context.source_snapshot_hash == snapshot.manifest_sha256
    assert context.source_snapshot_id == snapshot.manifest_identity_sha256
    assert context.daily_snapshot_condition_keys == METHOD
    assert context.daily_snapshot_combine_mode == "AND"
    payload_path = tmp_path / "bookmark.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    code = '''import json,sys
from pathlib import Path
from app_module.daily_market_research_bookmark import decode_daily_market_research_bookmark
b=decode_daily_market_research_bookmark(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
print(json.dumps(b.to_dict(),ensure_ascii=False,sort_keys=True))'''
    child = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(payload_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=Path(__file__).resolve().parents[1])
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == payload
    assert source_before == (source.read_bytes(), source.stat().st_mtime_ns)
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == pin for p, pin in pins.items())


@pytest.mark.parametrize("sort_key,keys", [("bbands30_upper", ("close_above_ma20",)), ("stock_code", (METHOD,))])
def test_v2_cannot_claim_bb_sort_or_condition(tmp_path, sort_key, keys):
    snapshot, _ = _saved(tmp_path, V2)
    row = _row(snapshot, tmp_path / "snapshots", keys)
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        create_daily_market_research_bookmark(snapshot, row, sort_key=sort_key)
    assert error.value.code in {"query_sort_invalid", "query_filter_invalid"}


def test_unknown_feature_version_rejected_before_save(tmp_path):
    snapshot, _ = _saved(tmp_path)
    manifest = deepcopy(snapshot.manifest)
    manifest["feature_contract_version"] = "daily-market-feature-snapshot.v999"
    changed = replace(snapshot, manifest=manifest, manifest_sha256=canonical_snapshot_sha256(manifest),
        manifest_identity_sha256=snapshot_manifest_identity_sha256(manifest))
    row = _row(snapshot, tmp_path / "snapshots", (METHOD,))
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        create_daily_market_research_bookmark(changed, row)
    assert error.value.code == "snapshot_feature_version_invalid"


@pytest.mark.parametrize("mutation", ["parameters", "version", "missing_method", "v2_source", "state", "root", "source_hash"])
def test_v3_rehashed_forgery_and_wrong_saved_identity_fail_closed(tmp_path, mutation):
    snapshot, _ = _saved(tmp_path)
    bookmark = create_daily_market_research_bookmark(snapshot, _row(snapshot, tmp_path / "snapshots", (METHOD,)))
    payload = deepcopy(bookmark.to_dict())
    if mutation == "parameters":
        payload["method_contracts"][METHOD]["parameters"]["timeperiod"] = 20
        payload["method_contracts_sha256"] = method_contracts_sha256(payload["method_contracts"])
    elif mutation == "version":
        payload["method_contracts"][METHOD]["version"] = "999"
        payload["method_contracts_sha256"] = method_contracts_sha256(payload["method_contracts"])
    elif mutation == "missing_method":
        payload["method_contracts"].pop(METHOD)
        payload["method_contracts_sha256"] = method_contracts_sha256(payload["method_contracts"])
    elif mutation == "v2_source":
        other = tmp_path / "v2"
        other.mkdir()
        old, _ = _saved(other, V2)
        payload["source_snapshot_hash"] = old.manifest_sha256
        payload["snapshot_root"] = str((other / "snapshots").resolve())
    elif mutation == "state":
        payload["conditions"][0]["state"] = "no_match"
    elif mutation == "root":
        payload["snapshot_root"] = str((tmp_path / "other").resolve())
    else:
        payload["source_snapshot_hash"] = "f" * 64
    if mutation in {"v2_source", "root", "source_hash"}:
        payload = _rebind_query(payload)
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        decode_daily_market_research_bookmark(_repin(payload))
    if mutation == "v2_source":
        assert error.value.code == "bookmark_feature_version_mismatch"


def test_v3_missing_saved_artifact_does_not_fallback_to_latest(tmp_path):
    snapshot, _ = _saved(tmp_path)
    bookmark = create_daily_market_research_bookmark(snapshot, _row(snapshot, tmp_path / "snapshots", (METHOD,)))
    record = snapshot.manifest["stocks"][0]
    path = tmp_path / "snapshots" / record["artifact_relpath"]
    # 合成 artifact 用移名模擬缺件；原件保留。
    path.rename(path.with_suffix(".saved"))
    with pytest.raises(DailyMarketResearchBookmarkError) as error:
        decode_daily_market_research_bookmark(bookmark.to_dict())
    assert error.value.code == "bookmark_snapshot_root_mismatch"
