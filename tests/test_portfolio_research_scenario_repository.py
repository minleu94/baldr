from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Context, Decimal, Inexact, localcontext
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import (
    PersonalStoreDomain, PersonalStoreMode, PersonalStoreRouteError, StoreIdentity,
    select_personal_store_route,
)
from app_module.portfolio_allocation_dtos import AllocationWeightContract, PortfolioAllocationContextRow
from app_module.portfolio_research_valuation import PortfolioResearchValuation, PortfolioResearchValuedPosition
from app_module.portfolio_research_scenario_artifact import (
    MAX_SCENARIO_BYTES, decode_scenario_artifact, encode_scenario_artifact, scenario_artifact_id,
)
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.portfolio_research_scenario_service import (
    PortfolioResearchAccountState, PortfolioResearchContextEvidence, PortfolioResearchPosition,
    PortfolioResearchScenarioRequest, PortfolioResearchScenarioService,
)


HASH = "sha256:" + "a" * 64
DECISION = datetime(2026, 10, 9, 1, tzinfo=timezone.utc)
SAVED = DECISION + timedelta(minutes=1)


def _comparison(kind="paper", account_id="account-a", *, explicit=True):
    state = PortfolioResearchAccountState(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a", as_of_date="2026-10-08",
        available_at=DECISION - timedelta(days=1), source_hash=HASH, capital_amount=Decimal("1000000.00"),
        current_weights=AllocationWeightContract({"2330": 1000}, 9000),
        positions=(PortfolioResearchPosition("2330", 1000),),
        valuation=PortfolioResearchValuation(Decimal("900000.00"), Decimal("1000000.00"), (
            PortfolioResearchValuedPosition("2330", 1000, Decimal("100.00"), Decimal("100000.00")),
        )),
    )

    class Reader:
        def read_exact(self, **kwargs):
            assert kwargs == {"account_kind": kind, "portfolio_id": account_id, "snapshot_id": "snapshot-a"}
            return state

    contexts = tuple(PortfolioResearchContextEvidence(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a", available_at=DECISION - timedelta(hours=2),
        source_hash=HASH, health_known=True,
        context=PortfolioAllocationContextRow(
            stock_code=code, stock_name="測試" + code, current_weight_bp=1000 if code == "2330" else 0,
            current_shares=1000 if code == "2330" else 0, sector_id="sector-" + code,
            reference_price=Decimal("100.00"), median_volume_20d_shares=200000,
            market_data_as_of_date="2026-10-08", trading_days_since_last_trade=5,
        ),
    ) for code in ("2330", "2382"))
    request = PortfolioResearchScenarioRequest(
        account_kind=kind, portfolio_id=account_id, snapshot_id="snapshot-a", decision_at=DECISION,
        candidate_symbols=("2382", "2330"), contexts=contexts, research_source_hash=HASH,
        explicit_weights=AllocationWeightContract({"2330": 1500}, 8500) if explicit else None,
    )
    return PortfolioResearchScenarioService(Reader()).compare(request)


def _route(paths, mode=PersonalStoreMode.PERSONAL):
    return select_personal_store_route(domain=PersonalStoreDomain.PORTFOLIO_RESEARCH, mode=mode,
        identity=StoreIdentity("portfolio-research"), personal_paths=paths)


@pytest.fixture
def paths(tmp_path):
    return PersonalDataPaths(market_root=tmp_path / "market", legacy_output_root=tmp_path / "legacy",
                             personal_root=tmp_path / "market" / "personal")


@pytest.fixture
def repo(paths):
    return PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)


def _json(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.mark.parametrize("precision", [1, 3, 28])
def test_complete_frozen_scenario_codec_is_independent_of_caller_decimal_context(precision):
    comparison = _comparison()
    expected_payload = encode_scenario_artifact(comparison)
    expected_restored = decode_scenario_artifact(expected_payload)
    caller_context = Context(prec=precision, Emax=1, Emin=-1)
    caller_context.traps[Inexact] = True
    with localcontext(caller_context):
        restored = decode_scenario_artifact(expected_payload)
        roundtrip_payload = encode_scenario_artifact(restored)
    assert restored == expected_restored
    assert roundtrip_payload == expected_payload


@pytest.mark.parametrize("kind", ["manual", "user_declared", "paper"])
@pytest.mark.parametrize("explicit", [False, True])
def test_codec_restores_complete_original_inputs_and_results(kind, explicit):
    comparison = _comparison(kind, explicit=explicit)
    payload = encode_scenario_artifact(comparison)
    restored = decode_scenario_artifact(payload)
    assert restored.to_dict() == comparison.to_dict()
    assert encode_scenario_artifact(restored) == payload
    assert restored.request.candidate_symbols == ("2330", "2382")
    assert isinstance(restored.account.capital_amount, Decimal)
    assert len(restored.scenarios) == (3 if explicit else 2)
    assert all(item.snapshot_id == restored.account.snapshot_id for item in restored.request.contexts)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema="portfolio-research-scenarios.v1"),
    lambda p: p["request"]["contexts"][0].pop("snapshot_id"),
    lambda p: p["request"]["contexts"][0].update(snapshot_id="snapshot-b"),
])
def test_decoder_refuses_legacy_missing_or_mismatched_context_snapshot(mutation):
    payload = _comparison().to_dict()
    mutation(payload)
    with pytest.raises(ValueError):
        decode_scenario_artifact(_json(payload))


def test_legacy_payload_public_reader_refuses_without_rewriting_database(repo):
    saved = repo.append(_comparison(), saved_at=SAVED)
    payload = saved.comparison.to_dict()
    payload["schema"] = "portfolio-research-scenarios.v1"
    for evidence in payload["request"]["contexts"]:
        evidence.pop("snapshot_id")
    legacy_bytes = _json(payload)
    legacy_id = "sha256:" + hashlib.sha256(legacy_bytes).hexdigest()
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("UPDATE scenario_archives SET artifact_id=?, payload_json=?",
                     (legacy_id, legacy_bytes))
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match="unsupported scenario artifact schema"):
        repo.get_exact(legacy_id, account_kind="paper", portfolio_id="account-a")
    assert repo.db_path.read_bytes() == before


def test_empty_reader_does_not_create_or_fallback(paths, repo):
    legacy = _route(paths, PersonalStoreMode.LEGACY_COMPAT).read_source
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"not a scenario database")
    assert repo.get_exact(HASH, account_kind="paper", portfolio_id="account-a") is None
    assert repo.list_artifact_ids(account_kind="paper", portfolio_id="account-a") == ()
    assert not paths.personal_root.exists()
    assert legacy.read_bytes() == b"not a scenario database"


def test_writer_close_public_read_idempotent_and_database_bytes_unchanged(paths, repo):
    comparison = _comparison()
    saved = repo.append(comparison, saved_at=SAVED)
    before = repo.db_path.read_bytes()
    reader = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    assert reader.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a") == saved
    assert reader.list_artifact_ids(account_kind="paper", portfolio_id="account-a") == (saved.artifact_id,)
    assert repo.append(comparison, saved_at=SAVED + timedelta(days=1)) == saved
    assert repo.db_path.read_bytes() == before
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM scenario_archives").fetchone()[0] == 1


def test_fresh_process_public_reader_uses_saved_artifact(paths, repo):
    saved = repo.append(_comparison(), saved_at=SAVED)
    before = hashlib.sha256(repo.db_path.read_bytes()).hexdigest()
    script = '''import json, os, sys
from pathlib import Path
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, StoreIdentity, select_personal_store_route
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact, scenario_artifact_id
p = PersonalDataPaths(market_root=Path(sys.argv[1]), legacy_output_root=Path(sys.argv[2]), personal_root=Path(sys.argv[3]))
r = select_personal_store_route(domain=PersonalStoreDomain.PORTFOLIO_RESEARCH, mode=PersonalStoreMode.PERSONAL, identity=StoreIdentity("portfolio-research"), personal_paths=p)
s = PortfolioResearchScenarioRepository(route=r, personal_paths=p).get_exact(sys.argv[4], account_kind="paper", portfolio_id="account-a")
assert s is not None
print(json.dumps({"pid":os.getpid(), "id":scenario_artifact_id(encode_scenario_artifact(s.comparison)), "input_hash":s.comparison.input_hash, "saved_at":s.saved_at.isoformat()}))
'''
    result = subprocess.run([sys.executable, "-c", script, str(paths.market_root), str(paths.legacy_output_root),
        str(paths.personal_root), saved.artifact_id], capture_output=True, text=True, timeout=30, check=True)
    evidence = json.loads(result.stdout)
    assert evidence["pid"] != os.getpid()
    assert evidence["id"] == saved.artifact_id
    assert evidence["input_hash"] == saved.comparison.input_hash
    assert evidence["saved_at"] == SAVED.isoformat()
    assert hashlib.sha256(repo.db_path.read_bytes()).hexdigest() == before
    evidence["database_sha256_before"] = before
    evidence["database_sha256_after"] = hashlib.sha256(repo.db_path.read_bytes()).hexdigest()
    (paths.market_root.parent / "fresh_reader_receipt.json").write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")


def test_same_symbol_and_same_id_different_account_kind_are_isolated(repo):
    saved = [repo.append(_comparison(kind), saved_at=SAVED) for kind in ("manual", "user_declared", "paper")]
    assert len({item.artifact_id for item in saved}) == 3
    for kind, item in zip(("manual", "user_declared", "paper"), saved):
        assert repo.list_artifact_ids(account_kind=kind, portfolio_id="account-a") == (item.artifact_id,)
        with pytest.raises(ValueError, match="another selected account"):
            repo.get_exact(item.artifact_id, account_kind=kind, portfolio_id="other")
    with pytest.raises(ValueError, match="another selected account"):
        repo.get_exact(saved[0].artifact_id, account_kind="paper", portfolio_id="account-a")


@pytest.mark.parametrize("mode", [PersonalStoreMode.LEGACY_READ_ONLY, PersonalStoreMode.LEGACY_COMPAT])
def test_legacy_routes_cannot_append(paths, mode):
    route = _route(paths, mode)
    reader = PortfolioResearchScenarioRepository(route=route, personal_paths=paths)
    with pytest.raises(PersonalStoreRouteError, match="read_only"):
        reader.append(_comparison(), saved_at=SAVED)
    assert not route.read_source.exists()


def test_invalid_save_clock_rejected_before_database_creation(repo):
    for clock in (datetime(2026, 10, 9), DECISION - timedelta(seconds=1)):
        with pytest.raises(ValueError):
            repo.append(_comparison(), saved_at=clock)
    assert not repo.db_path.exists()


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema="portfolio-research-scenarios.v999"),
    lambda p: p.update(broker_order_allowed=True),
    lambda p: p["scenarios"][0]["result"].update(apply_rebalance=True),
    lambda p: p["account"].update(capital_amount=1000000),
    lambda p: p["account"]["positions"][0].update(quantity=True),
    lambda p: p["request"]["contexts"][0].update(health_known=False),
    lambda p: p["request"]["contexts"][0].update(available_at="2026-10-10T01:00:00+00:00"),
    lambda p: p["account"].update(portfolio_id="other"),
    lambda p: p["scenarios"].reverse(),
    lambda p: p["scenarios"][0]["result"]["projection"]["rows"][0].update(gap_weight_bp=999),
    lambda p: p["scenarios"][0]["result"]["projection"].update(total_estimated_cost="100.00"),
    lambda p: p["scenarios"][0]["result"].update(allocation_policy_hash="sha256:" + "b" * 64),
    lambda p: p["account"].update(extra="unexpected"),
])
def test_codec_refuses_bad_contract_or_incoherent_frozen_facts(mutation):
    payload = _comparison().to_dict()
    mutation(payload)
    with pytest.raises(ValueError):
        decode_scenario_artifact(_json(payload))


@pytest.mark.parametrize("payload", [
    b'{"schema":"one","schema":"two"}', b'{"amount":NaN}', b'{"amount":1.1}',
    b'{"amount":1234567890123456789}', b'\xff', b'[]', b'null',
])
def test_codec_refuses_ambiguous_or_unbounded_json(payload):
    with pytest.raises(ValueError):
        decode_scenario_artifact(payload)


def test_codec_resource_limit_and_noncanonical_payload():
    with pytest.raises(ValueError, match="size"):
        decode_scenario_artifact(b" " * (MAX_SCENARIO_BYTES + 1))
    with pytest.raises(ValueError, match="not canonical"):
        decode_scenario_artifact(json.dumps(_comparison().to_dict()).encode("utf-8"))


@pytest.mark.parametrize("mutation", [
    lambda p: p["scenarios"][0]["result"]["projection"].update(post_cost_cash_amount="900000.01"),
    lambda p: p["scenarios"][0]["result"]["projection"]["rows"][0].update(executable_shares=999),
    lambda p: p["scenarios"][0]["result"]["projection"]["rows"][0].update(executable_amount="99999.99"),
    lambda p: p["account"]["valuation"].update(cash_amount="900000.01"),
    lambda p: p["account"].pop("valuation"),
    lambda p: p.update(schema="portfolio-research-scenarios.v2"),
    lambda p: p["account"]["valuation"]["display_weights"].update(cash_weight_bp=8999),
])
def test_codec_refuses_reencoded_inconsistent_exact_money(mutation):
    payload = _comparison().to_dict()
    mutation(payload)
    with pytest.raises(ValueError):
        decode_scenario_artifact(_json(payload))


def test_codec_refuses_consistently_reencoded_display_weights_without_real_amounts():
    payload = _comparison().to_dict()
    projection = payload["scenarios"][0]["result"]["projection"]
    projection["executable_weights"]["symbol_weights_bp"]["2330"] = 1001
    projection["executable_weights"]["cash_weight_bp"] = 8999
    projection["rows"][0]["executable_weight_bp"] = 1001
    with pytest.raises(ValueError, match="final valuation"):
        decode_scenario_artifact(_json(payload))


def test_codec_refuses_wrong_trade_cost_even_when_sum_and_cash_are_adjusted():
    payload = _comparison().to_dict()
    projection = payload["scenarios"][1]["result"]["projection"]
    traded = next(row for row in projection["rows"] if Decimal(row["estimated_cost"]) > 0)
    original_cost = Decimal(traded["estimated_cost"])
    traded["estimated_cost"] = "0.00"
    projection["total_estimated_cost"] = str(Decimal(projection["total_estimated_cost"]) - original_cost)
    projection["post_cost_cash_amount"] = str(Decimal(projection["post_cost_cash_amount"]) + original_cost)
    with pytest.raises(ValueError, match="trade cost mismatch"):
        decode_scenario_artifact(_json(payload))


def test_valuation_list_bound_is_checked_before_constructing_positions(monkeypatch):
    import app_module.portfolio_research_scenario_artifact as codec
    value = _comparison().account.valuation.to_dict()
    value["positions"] *= 10001
    def forbidden(*args, **kwargs):
        pytest.fail("oversized positions must not be constructed")
    monkeypatch.setattr(codec, "PortfolioResearchValuedPosition", forbidden)
    with pytest.raises(ValueError, match="positions exceed limit"):
        codec._valuation(value)


@pytest.mark.parametrize("column, value, message", [
    ("payload_json", b"{}", "hash mismatch"),
    ("snapshot_id", "wrong-snapshot", "index differs"),
    ("input_hash", "sha256:" + "b" * 64, "index differs"),
    ("saved_at", "2026-10-08T00:00:00+00:00", "precedes decision"),
    ("payload_json", "text-not-blob", "type or size"),
])
def test_reader_rejects_tampered_database_without_repair(repo, column, value, message):
    saved = repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(f"UPDATE scenario_archives SET {column}=? WHERE artifact_id=?", (value, saved.artifact_id))
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match=message):
        repo.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    assert repo.db_path.read_bytes() == before


def test_unknown_schema_and_existing_empty_db_are_not_migrated(repo):
    repo.db_path.parent.mkdir(parents=True)
    with sqlite3.connect(repo.db_path):
        pass
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match="schema"):
        repo.append(_comparison(), saved_at=SAVED)
    assert repo.db_path.read_bytes() == before


def test_public_reader_uses_query_only_and_one_transaction(repo, monkeypatch):
    saved = repo.append(_comparison(), saved_at=SAVED)
    original_load = repo._load
    observed = []

    def observe(conn, artifact_id, **kwargs):
        observed.append((conn.in_transaction, conn.execute("PRAGMA query_only").fetchone()[0]))
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE scenario_archives SET snapshot_id='forbidden'")
        return original_load(conn, artifact_id, **kwargs)

    monkeypatch.setattr(repo, "_load", observe)
    before = repo.db_path.read_bytes()
    assert repo.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a") == saved
    assert observed == [(True, 1)]
    assert repo.db_path.read_bytes() == before


def test_reader_rejects_oversized_blob_before_decoder(repo, monkeypatch):
    saved = repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("UPDATE scenario_archives SET payload_json=zeroblob(?)", (MAX_SCENARIO_BYTES + 1,))

    def must_not_decode(payload):
        raise AssertionError("oversized blob reached decoder")

    monkeypatch.setattr("app_module.portfolio_research_scenario_repository.decode_scenario_artifact", must_not_decode)
    with pytest.raises(ValueError, match="size rejected"):
        repo.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a")


def test_unknown_version_reader_and_writer_do_not_repair(repo):
    saved = repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("UPDATE scenario_store_meta SET schema_version='portfolio-research-store.v999'")
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match="unsupported"):
        repo.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    with pytest.raises(ValueError, match="unsupported"):
        repo.append(_comparison(), saved_at=SAVED)
    assert repo.db_path.read_bytes() == before


@pytest.mark.parametrize("contract", ["target_weights", "executable_weights"])
@pytest.mark.parametrize("hidden_weight", [0, 1])
def test_hidden_projection_weights_are_rejected(contract, hidden_weight):
    payload = _comparison().to_dict()
    weights = payload["scenarios"][0]["result"]["projection"][contract]
    assert weights is not None
    weights["symbol_weights_bp"]["HIDDEN"] = hidden_weight
    weights["cash_weight_bp"] -= hidden_weight
    with pytest.raises(ValueError, match="hidden symbols"):
        decode_scenario_artifact(_json(payload))


@pytest.mark.parametrize("replacement", [None, "CREATE INDEX scenario_account_time ON scenario_archives(account_kind, portfolio_id, saved_at ASC, artifact_id ASC)"])
def test_missing_or_wrong_index_is_rejected_without_rebuilding(repo, replacement):
    saved = repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("DROP INDEX scenario_account_time")
        if replacement is not None:
            conn.execute(replacement)
    before = repo.db_path.read_bytes()
    with pytest.raises(ValueError, match="index"):
        repo.get_exact(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    with pytest.raises(ValueError, match="index"):
        repo.list_artifact_ids(account_kind="paper", portfolio_id="account-a")
    with pytest.raises(ValueError, match="index"):
        repo.append(_comparison(), saved_at=SAVED)
    assert repo.db_path.read_bytes() == before


def test_account_list_uses_covering_ordered_index(repo):
    repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        plan = conn.execute("EXPLAIN QUERY PLAN SELECT artifact_id FROM scenario_archives WHERE account_kind=? AND portfolio_id=? ORDER BY saved_at DESC,artifact_id ASC LIMIT ?", ("paper", "account-a", 25)).fetchall()
    text = " ".join(str(row[3]) for row in plan)
    assert "scenario_account_time" in text
    assert "TEMP B-TREE" not in text


def test_concurrent_first_append_is_atomic_and_idempotent(repo):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)
    comparison = _comparison()

    def append(offset):
        barrier.wait(timeout=10)
        return repo.append(comparison, saved_at=SAVED + timedelta(seconds=offset))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append, offset) for offset in (0, 1)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0] == results[1]
    assert repo.get_exact(results[0].artifact_id, account_kind="paper", portfolio_id="account-a") == results[0]
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM scenario_archives").fetchone()[0] == 1


def test_failed_insert_rolls_back_without_half_artifact(repo):
    original = repo.append(_comparison(), saved_at=SAVED)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_new BEFORE INSERT ON scenario_archives BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    before = repo.db_path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        repo.append(_comparison(account_id="account-b"), saved_at=SAVED)
    assert repo.db_path.read_bytes() == before
    assert repo.get_exact(original.artifact_id, account_kind="paper", portfolio_id="account-a") == original


def test_list_uses_utc_clock_and_bound_and_missing_id_never_guesses_latest(repo):
    first = repo.append(_comparison(account_id="account-a"), saved_at=SAVED)
    second_comparison = _comparison(account_id="account-a", explicit=False)
    second = repo.append(second_comparison, saved_at=(SAVED + timedelta(minutes=1)).astimezone(timezone(timedelta(hours=-7))))
    assert repo.list_artifact_ids(account_kind="paper", portfolio_id="account-a", limit=1) == (second.artifact_id,)
    assert repo.get_exact("sha256:" + "f" * 64, account_kind="paper", portfolio_id="account-a") is None
    for invalid in (0, 201, True):
        with pytest.raises(ValueError):
            repo.list_artifact_ids(account_kind="paper", portfolio_id="account-a", limit=invalid)
    assert repo.get_exact(first.artifact_id, account_kind="paper", portfolio_id="account-a") == first
