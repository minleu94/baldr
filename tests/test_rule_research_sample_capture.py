"""UX20 完整分母、時鐘、修訂與隔離原子收據驗證。"""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app_module.daily_market_research_universe import load_research_universe_spec
from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository, DailyMarketSnapshotVerificationError,
    canonical_snapshot_sha256, snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath, snapshot_artifact_relpath,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter, RuleResearchCapture, RuleSampleCaptureError,
    SAFETY_RESERVE_BYTES, build_rule_research_capture, read_rule_research_capture,
)
import app_module.rule_research_sample_capture as capture_module
from tests.test_daily_market_snapshot_repository import (
    DECISION_DATE, PUBLISHED_AT, _publish, _snapshot_payload,
)


def _fixture(tmp_path, *, missing=False, variant="base", universe=True):
    source = tmp_path / ("source-" + variant)
    source.mkdir(exist_ok=True)
    updates = {}
    if universe:
        path = source / "universe.json"
        path.write_text(json.dumps({
            "schema_version": "daily-market-research-universe.v1",
            "universe_id": "ux19-test-cohort", "version": "1.0",
            "as_of_date": DECISION_DATE.isoformat(), "method": "daily-market-close-ma.v1",
            "included_stock_codes": ["2382", "3034"],
            "excluded_stock_codes": [{"stock_code": "1477", "reason": "明示排除對照。"}],
            "population_count": 3, "scope": "bounded_research_cohort",
            "research_only": True, "complete_fixed_cohort": True,
        }, ensure_ascii=False), encoding="utf-8")
        updates["research_universe"] = load_research_universe_spec(path).to_manifest_binding()
    payloads = {"2382": _snapshot_payload("2382", variant=variant)}
    if not missing:
        payloads["3034"] = _snapshot_payload("3034", technical=False)
    pin, _ = _publish(source, payloads, ("2382", "3034"), manifest_updates=updates)
    repo = DailyMarketSnapshotRepository(source)
    snapshot = repo.load_manifest(pin, "ux19-test-cohort", DECISION_DATE)
    capture = build_rule_research_capture(snapshot, as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT)
    return repo, snapshot, capture


def _writer(tmp_path, monkeypatch):
    writer = BoundedRuleResearchCaptureWriter(tmp_path / "capture-store")
    monkeypatch.setattr(writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES + 1024 ** 3)
    return writer


def _expect(code, operation):
    with pytest.raises(RuleSampleCaptureError) as error:
        operation()
    assert error.value.code == code


def test_complete_control_groups_and_method_denominators(tmp_path):
    _, _, capture = _fixture(tmp_path)
    body = capture.to_dict()
    assert body["included_denominator"] == 2
    assert body["represented_denominator"] == body["population_count"] == 3
    assert body["population_status"] == "declared_fixed_cohort"
    assert len(body["rows"]) == 6
    counts = {item["method_id"]: item for item in body["method_counts"]}
    assert counts["daily_market.close_above_ma20"]["matched"] == 1
    assert counts["daily_market.close_above_ma60"]["notmatched"] == 1
    for item in counts.values():
        assert item["unknown"] == item["excluded"] == 1
        assert sum(item[state] for state in ("matched", "notmatched", "unknown", "excluded")) == 3
    assert all(row["reason"] and not row["selected"] for row in body["rows"])
    assert body["policy"]["selected_count"] == 0
    assert body["policy"]["selection_predicate"] is None


def test_unknown_source_clocks_are_never_backfilled(tmp_path):
    _, _, capture = _fixture(tmp_path)
    body = capture.to_dict()
    assert body["artifact_published_at"] and body["observed_at"] and body["as_of"]
    assert body["source_observed_at"] is body["source_available_at"] is None
    assert all(row["source_observed_at"] is row["source_available_at"] is None for row in body["rows"])
    assert all(body["policy"][flag] is False for flag in
               ("historical_pit_eligible", "natural_authority", "formal_eligible", "training_eligible"))
    unknown = [row for row in body["rows"] if row["state"] == "unknown"]
    assert all(row["unknown_reason"] for row in unknown)


def test_partial_preserves_complete_membership_as_unknown(tmp_path):
    _, _, capture = _fixture(tmp_path, missing=True)
    body = capture.to_dict()
    assert body["completeness"] == "partial_research"
    assert body["missing_count"] == 1 and body["published_count"] == 1
    assert body["missing_stocks"] == [{"stock_code": "3034", "reason": "source_unavailable"}]
    assert all(c["unknown"] == 2 and c["matched"] == c["notmatched"] == 0 for c in body["method_counts"])


def test_legacy_cohort_does_not_invent_market_population(tmp_path):
    _, _, capture = _fixture(tmp_path, universe=False)
    body = capture.to_dict()
    assert body["population_count"] is None
    assert body["population_status"] == "unknown_full_market_population"
    assert body["universe"]["scope"] == "legacy_declared_research_only"
    assert len(body["rows"]) == 4


def test_pure_projection_has_no_io_and_freezes_mutable_dto(tmp_path, monkeypatch):
    _, snapshot, capture = _fixture(tmp_path)
    before = capture.body_json
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "open", lambda *a, **k: pytest.fail("純投影不得讀檔"))
        other = build_rule_research_capture(snapshot, as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT)
    assert other == capture
    snapshot.manifest["cohort_id"] = "mutated"
    assert capture.body_json == before
    _expect("capture_identity_mismatch", lambda: RuleResearchCapture(before.replace("明示排除對照", "竄改排除對照")).to_dict())


def test_pinned_reader_never_reads_latest_and_preserves_source_bytes(tmp_path):
    repo, snapshot, capture = _fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in repo.output_root.rglob("*.json")}
    (repo.output_root / "latest.json").write_text("{}", encoding="utf-8")
    result = read_rule_research_capture(repo, manifest_sha256=snapshot.manifest_sha256,
        cohort_id=snapshot.cohort_id, decision_date=DECISION_DATE,
        as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT)
    assert result == capture
    after = {p.name: p.read_bytes() for p in repo.output_root.rglob("*.json") if p.name != "latest.json"}
    assert after == {k: v for k, v in before.items() if k != "latest.json"}


@pytest.mark.parametrize("kind", ["naive", "future_as_of", "before_as_of"])
def test_invalid_clock_rejected(tmp_path, kind):
    _, snapshot, _ = _fixture(tmp_path)
    as_of = PUBLISHED_AT.replace(tzinfo=None) if kind == "naive" else PUBLISHED_AT
    if kind == "future_as_of":
        as_of -= timedelta(seconds=1)
    observed = PUBLISHED_AT - timedelta(seconds=1) if kind == "before_as_of" else PUBLISHED_AT
    with pytest.raises(ValueError):
        build_rule_research_capture(snapshot, as_of=as_of, observed_at=observed)


def test_source_revision_new_identity_preserves_old_evidence(tmp_path, monkeypatch):
    _, snapshot, first = _fixture(tmp_path)
    _, _, revised = _fixture(tmp_path, variant="revision")
    writer = _writer(tmp_path, monkeypatch)
    old = writer.write(first, revalidate=lambda: first)
    old_bytes = (Path(old["directory"]) / "capture.json").read_bytes()
    new = writer.write(revised, revalidate=lambda: revised)
    assert first.identity_sha256 != revised.identity_sha256
    assert new["status"] == "published"
    assert (Path(old["directory"]) / "capture.json").read_bytes() == old_bytes
    retry = build_rule_research_capture(snapshot, as_of=PUBLISHED_AT,
                                       observed_at=PUBLISHED_AT + timedelta(hours=1))
    assert retry.identity_sha256 == first.identity_sha256
    duplicate = writer.write(retry, revalidate=lambda: retry)
    assert duplicate["status"] == "duplicate"
    assert duplicate["receipt"] == old["receipt"]


def test_as_of_is_semantic_identity(tmp_path):
    _, snapshot, first = _fixture(tmp_path)
    later = PUBLISHED_AT + timedelta(hours=1)
    revised = build_rule_research_capture(snapshot, as_of=later, observed_at=later)
    assert revised.identity_sha256 != first.identity_sha256


def test_real_pinned_writer_uses_actual_observed_time(tmp_path, monkeypatch):
    repo, snapshot, _ = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    result = writer.capture_pinned(repo, manifest_sha256=snapshot.manifest_sha256,
        cohort_id=snapshot.cohort_id, decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert result["status"] == "published"
    body = json.loads((Path(result["directory"]) / "capture.json").read_text(encoding="utf-8"))
    assert body["observed_at"] != body["as_of"]
    assert body["source_available_at"] is None


@pytest.mark.parametrize("phase", ["capture", "receipt", "rename"])
def test_partial_failure_never_publishes_new_receipt(tmp_path, monkeypatch, phase):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    original = capture_module._write_file
    def failing(path, raw):
        if (phase == "capture" and path.name == "capture.json") or (phase == "receipt" and path.name == "receipt.json"):
            raise OSError("合成寫入故障")
        original(path, raw)
    with monkeypatch.context() as scoped:
        scoped.setattr(capture_module, "_write_file", failing)
        if phase == "rename":
            scoped.setattr(Path, "rename", lambda *a, **k: (_ for _ in ()).throw(OSError("合成rename故障")))
        with pytest.raises(OSError):
            writer.write(capture, revalidate=lambda: capture)
    assert not (writer.output_root / capture.identity_sha256).exists()
    assert not (writer.output_root / ".writer.lock").exists()
    assert len(list(writer.output_root.glob(".partial-*"))) == 1
    _expect("store_unknown_or_partial_entry", lambda: writer.write(capture, revalidate=lambda: capture))


def test_source_revision_during_commit_is_rejected_and_old_receipt_unchanged(tmp_path, monkeypatch):
    _, _, first = _fixture(tmp_path)
    _, _, revised = _fixture(tmp_path, variant="revision")
    writer = _writer(tmp_path, monkeypatch)
    prior = writer.write(first, revalidate=lambda: first)
    old = (Path(prior["directory"]) / "receipt.json").read_bytes()
    reads = iter([revised, first])
    _expect("source_revision_during_capture", lambda: writer.write(revised, revalidate=lambda: next(reads)))
    assert not (writer.output_root / revised.identity_sha256).exists()
    assert (Path(prior["directory"]) / "receipt.json").read_bytes() == old


@pytest.mark.parametrize("bound", ["reserve", "bytes", "entries"])
def test_capacity_refusal_before_any_partial(tmp_path, monkeypatch, bound):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    if bound == "reserve":
        monkeypatch.setattr(writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES)
        code = "capacity_reserve"
    elif bound == "bytes":
        monkeypatch.setattr(capture_module, "MAX_RETAINED_BYTES", 1)
        code = "retention_byte_limit"
    else:
        monkeypatch.setattr(capture_module, "MAX_CAPTURES", 0)
        code = "retention_entry_limit"
    _expect(code, lambda: writer.write(capture, revalidate=lambda: capture))
    assert list(writer.output_root.iterdir()) == []


def test_duplicate_corrupt_receipt_is_rejected(tmp_path, monkeypatch):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    result = writer.write(capture, revalidate=lambda: capture)
    receipt = Path(result["directory"]) / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    _expect("receipt_binding_mismatch", lambda: writer.write(capture, revalidate=lambda: capture))


def test_lock_and_unknown_files_rejected_without_cleanup(tmp_path, monkeypatch):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    writer.output_root.mkdir()
    lock = writer.output_root / ".writer.lock"
    lock.write_bytes(b"other-owner")
    _expect("writer_busy", lambda: writer.write(capture, revalidate=lambda: capture))
    assert lock.read_bytes() == b"other-owner"
    lock.unlink()
    other = writer.output_root / "unknown.txt"
    other.write_bytes(b"retain")
    _expect("store_unknown_or_partial_entry", lambda: writer.write(capture, revalidate=lambda: capture))
    assert other.read_bytes() == b"retain"


def test_source_output_overlap_refused(tmp_path, monkeypatch):
    repo, snapshot, _ = _fixture(tmp_path)
    writer = BoundedRuleResearchCaptureWriter(repo.output_root / "capture")
    with pytest.raises(RuleSampleCaptureError, match="source_output_overlap"):
        writer.capture_pinned(repo, manifest_sha256=snapshot.manifest_sha256,
            cohort_id=snapshot.cohort_id, decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert not writer.output_root.exists()


def test_repository_and_formal_output_path_rejected():
    _expect("isolated_output_required", lambda: BoundedRuleResearchCaptureWriter(Path(__file__).parents[1] / "app_module" / "bad"))
    _expect("isolated_output_required", lambda: BoundedRuleResearchCaptureWriter("D:/Min/Python/Project/FA_Data/capture"))


def test_hardlinked_capture_rejected(tmp_path, monkeypatch):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    result = writer.write(capture, revalidate=lambda: capture)
    file = Path(result["directory"]) / "capture.json"
    os.link(file, tmp_path / "linked.json")
    _expect("path_hardlink_rejected", lambda: writer.write(capture, revalidate=lambda: capture))


@pytest.mark.parametrize("change", ["method", "snapshot", "capture", "universe", "artifact", "condition"])
def test_version_source_revision_and_payload_mismatch_refused(tmp_path, change):
    repo, snapshot, capture = _fixture(tmp_path)
    if change == "capture":
        _expect("capture_version_mismatch", lambda: RuleResearchCapture(capture.body_json.replace(capture_module.CAPTURE_SCHEMA, "bad.v2")).to_dict())
        return
    if change == "universe":
        (repo.output_root / "universe.json").write_text("{}", encoding="utf-8")
    elif change == "artifact":
        record = snapshot.manifest["stocks"][0]
        (repo.output_root / snapshot_artifact_relpath(record["artifact_sha256"])).write_text("{}", encoding="utf-8")
    elif change == "condition":
        payload = snapshot.stock_snapshots["2382"]
        payload["conditions"]["close_above_ma20"]["state"] = "no_match"
        with pytest.raises(DailyMarketSnapshotVerificationError):
            build_rule_research_capture(snapshot, as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT)
        return
    else:
        manifest = deepcopy(snapshot.manifest)
        if change == "snapshot":
            manifest["schema_version"] = "bad.v3"
        else:
            manifest["method_contracts"]["close_above_ma20"]["version"] = "9.0.0"
            manifest["method_contracts_sha256"] = canonical_snapshot_sha256(manifest["method_contracts"])
        manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
        pin = canonical_snapshot_sha256(manifest)
        (repo.output_root / snapshot_manifest_relpath(pin)).write_text(capture_module._json(manifest), encoding="utf-8")
        snapshot = replace(snapshot, manifest_sha256=pin)
    with pytest.raises(DailyMarketSnapshotVerificationError):
        read_rule_research_capture(repo, manifest_sha256=snapshot.manifest_sha256,
            cohort_id=snapshot.cohort_id, decision_date=DECISION_DATE,
            as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT)


def test_cross_process_pinned_readback_is_read_only(tmp_path, monkeypatch):
    _, _, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    writer.write(capture, revalidate=lambda: capture)
    before = {p.name: p.read_bytes() for p in writer.output_root.rglob("*.json")}
    code = "from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter; import json,sys; print(json.dumps(BoundedRuleResearchCaptureWriter(sys.argv[1]).read(sys.argv[2]),sort_keys=True))"
    result = subprocess.run([sys.executable, "-c", code, str(writer.output_root), capture.identity_sha256],
        capture_output=True, text=True, check=True, timeout=20)
    body = json.loads(result.stdout)
    assert body["capture"] == capture.to_dict()
    assert body["receipt"]["status"] == "complete"
    assert before == {p.name: p.read_bytes() for p in writer.output_root.rglob("*.json")}
    assert not (writer.output_root / ".writer.lock").exists()


@pytest.mark.parametrize("failure", ["reserve", "universe"])
def test_failure_after_staging_retains_partial_and_never_commits(tmp_path, monkeypatch, failure):
    repo, snapshot, capture = _fixture(tmp_path)
    writer = _writer(tmp_path, monkeypatch)
    if failure == "reserve":
        free = iter([SAFETY_RESERVE_BYTES + 1024 ** 3, SAFETY_RESERVE_BYTES])
        monkeypatch.setattr(writer, "_free_bytes", lambda: next(free))
        _expect("capacity_reserve", lambda: writer.write(capture, revalidate=lambda: capture))
    else:
        original = capture_module._write_file
        def revise(path, raw):
            original(path, raw)
            if path.name == "receipt.json":
                (repo.output_root / "universe.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(capture_module, "_write_file", revise)
        with pytest.raises(DailyMarketSnapshotVerificationError):
            writer.capture_pinned(repo, manifest_sha256=snapshot.manifest_sha256,
                cohort_id=snapshot.cohort_id, decision_date=DECISION_DATE, as_of=PUBLISHED_AT)
    assert not (writer.output_root / capture.identity_sha256).exists()
    assert len(list(writer.output_root.glob(".partial-*"))) == 1
    assert not (writer.output_root / ".writer.lock").exists()


@pytest.mark.parametrize("mutation", ["counts", "policy", "duplicate", "availability"])
def test_rehashed_capture_semantic_damage_rejected(tmp_path, mutation):
    _, _, capture = _fixture(tmp_path)
    body = capture.to_dict()
    if mutation == "counts":
        body["method_counts"][0]["matched"] += 1
    elif mutation == "policy":
        body["policy"]["selected_count"] = 1
    elif mutation == "duplicate":
        body["rows"].append(body["rows"][0])
    else:
        body["source_available_at"] = body["observed_at"]
    body["capture_identity_sha256"] = capture_module._identity(body)
    with pytest.raises(RuleSampleCaptureError):
        RuleResearchCapture(capture_module._json(body)).to_dict()


def test_linked_output_is_rejected_when_symlink_supported(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "alias"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("本機不提供一般 symlink 建立權限；hardlink 拒絕另有實測。")
    _expect("path_link_rejected", lambda: BoundedRuleResearchCaptureWriter(link / "capture"))


def test_reader_rejects_bad_pin_without_creating_root(tmp_path):
    writer = BoundedRuleResearchCaptureWriter(tmp_path / "not-created")
    _expect("capture_pin_invalid", lambda: writer.read("../invalid"))
    assert not writer.output_root.exists()


def test_full_bounded_16_stock_cohort_is_never_truncated(tmp_path):
    codes = tuple(str(1000 + n) for n in range(16))
    pin, _ = _publish(tmp_path, {code: _snapshot_payload(code) for code in codes}, codes)
    result = read_rule_research_capture(DailyMarketSnapshotRepository(tmp_path), manifest_sha256=pin,
        cohort_id="ux19-test-cohort", decision_date=DECISION_DATE,
        as_of=PUBLISHED_AT, observed_at=PUBLISHED_AT).to_dict()
    assert result["included_denominator"] == result["published_count"] == 16
    assert len(result["rows"]) == 32
    assert all(c["represented_denominator"] == 16 for c in result["method_counts"])
    assert {row["stock_code"] for row in result["rows"]} == set(codes)


def test_capture_byte_bound_before_json_parse_and_source_hash_tamper(tmp_path):
    _expect("capture_byte_limit", lambda: RuleResearchCapture(" " * (capture_module.MAX_CAPTURE_BYTES + 1)).to_dict())
    _, _, capture = _fixture(tmp_path)
    body = capture.to_dict()
    body["source_sha256"] = "0" * 64
    body["capture_identity_sha256"] = capture_module._identity(body)
    _expect("capture_source_hash_mismatch", lambda: RuleResearchCapture(capture_module._json(body)).to_dict())
