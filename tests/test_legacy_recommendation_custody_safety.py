from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import data_module.legacy_recommendation_run_locator as locator


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.fixture
def sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    origin = tmp_path / "missing_original" / "rec_test.json"
    raw = b'{"result_id":"rec_test","stocks":[]}'
    target = runs / "rec_test.json"
    target.write_bytes(raw)
    entry = {
        "result_id": "rec_test", "origin_path": str(origin),
        "current_path": str(target), "relocated_file_sha256": _sha(raw),
        "relocated_size_bytes": len(raw), "db_row_sha256": "sha256:" + "a" * 64,
        "custody_verification_tier": "tier1_independent_pre_migration_file_sha256",
        "independent_pre_migration_file_sha256": _sha(raw),
        "independent_pre_migration_evidence_ref": "not-an-authority",
    }
    monkeypatch.setattr(locator, "_read_verified_locator_profile", lambda: [entry])
    evidence = tmp_path / "independent.json"
    record = {
        "result_id": entry["result_id"], "origin_path": entry["origin_path"],
        "original_sha256": _sha(raw),
    }
    evidence_raw = json.dumps({"source": record}).encode()
    evidence.write_bytes(evidence_raw)
    pin = locator.LegacyRecommendationCustodyEvidencePin(
        evidence, _sha(evidence_raw), len(evidence_raw), ("source",),
        "result_id", "origin_path", "original_sha256",
    )
    options = {"runs_root": runs, "db_row_sha256": entry["db_row_sha256"]}
    return entry, options, pin, target


def test_independent_full_identity_required_and_read_back(sample):
    entry, options, pin, _ = sample
    assert locator.locate_legacy_recommendation_run("rec_test", entry["origin_path"], **options) is None
    bound = locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options, custody_evidence={"rec_test": pin},
    )
    assert bound is not None and bound.custody_verified and not bound.research_only
    pin.evidence_path.write_bytes(b"{}")
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options, custody_evidence={"rec_test": pin},
    ) is None


@pytest.mark.parametrize("tier", locator.ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS[1:])
def test_weak_tier_only_explicit_audit_envelope(sample, tier):
    entry, options, pin, _ = sample
    entry["custody_verification_tier"] = tier
    entry["independent_pre_migration_file_sha256"] = None
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options,
        allowed_tiers=locator.ALL_LEGACY_RECOMMENDATION_CUSTODY_TIERS,
        custody_evidence={"rec_test": pin},
    ) is None
    audited = locator.audit_legacy_recommendation_run("rec_test", entry["origin_path"], **options)
    assert audited is not None and audited.research_only and not audited.custody_verified
    assert audited.custody_verification_tier == tier


@pytest.mark.parametrize("field", ["result_id", "origin_path", "original_sha256"])
def test_independent_record_field_mismatch_rejected(sample, field):
    entry, options, pin, _ = sample
    document = json.loads(pin.evidence_path.read_bytes())
    document["source"][field] = "unrelated"
    raw = json.dumps(document).encode()
    pin.evidence_path.write_bytes(raw)
    pin = replace(pin, evidence_sha256=_sha(raw), evidence_size_bytes=len(raw))
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options, custody_evidence={"rec_test": pin},
    ) is None


def test_missing_evidence_or_db_pin_and_changed_current_bytes_rejected(sample):
    entry, options, pin, target = sample
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], runs_root=options["runs_root"],
        custody_evidence={"rec_test": pin},
    ) is None
    missing = replace(pin, evidence_path=pin.evidence_path.with_name("missing.json"))
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options, custody_evidence={"rec_test": missing},
    ) is None
    target.write_bytes(b"tampered")
    assert locator.audit_legacy_recommendation_run("rec_test", entry["origin_path"], **options) is None


def test_hash_substring_in_unrelated_field_does_not_prove_custody(sample):
    entry, options, pin, _ = sample
    raw = json.dumps({"note": entry["relocated_file_sha256"]}).encode()
    pin.evidence_path.write_bytes(raw)
    pin = replace(pin, evidence_sha256=_sha(raw), evidence_size_bytes=len(raw))
    assert locator.locate_legacy_recommendation_run(
        "rec_test", entry["origin_path"], **options, custody_evidence={"rec_test": pin},
    ) is None


def test_mixed_query_does_not_return_partial_when_one_legacy_is_rejected(monkeypatch):
    from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
    from app_module.recommendation.queries import RecommendationExecutionQueries

    class Persistence:
        def list_verified_envelopes(self):
            return ()

    class Reader:
        def list_result_ids(self):
            return ("first", "missing_custody")

        def get(self, result_id):
            return object() if result_id == "first" else None

    query = RecommendationExecutionQueries(Persistence(), legacy_reader=Reader())
    monkeypatch.setattr(query, "_assert_no_unindexed_canonical_artifact", lambda _: None)
    monkeypatch.setattr(query, "_legacy_read_model", lambda *_: object())
    with pytest.raises(ExecutionArtifactIntegrityError, match="list"):
        query.list()


@pytest.mark.parametrize("result_id", [
    "scheduled_rec_20260907_051003", "scheduled_rec_20260910_051003",
])
def test_original_git_statement_binds_full_identity_not_substrings(monkeypatch, result_id):
    origin = rf"D:\Min\Python\Project\FA_Data\output\recommendation\runs\{result_id}.json"
    original_sha = "sha256:" + "b" * 64
    entry = {
        "result_id": result_id, "origin_path": origin,
        "independent_pre_migration_file_sha256": original_sha,
        "relocated_file_sha256": original_sha,
    }
    if result_id == "scheduled_rec_20260907_051003":
        line = (
            f"- Recommendation：`{origin}`，file hash `{original_sha}`，5 rows，"
            "decision date `2026-09-07`。"
        )
    else:
        line = (
            f"| recommendation source snapshot | `{origin}`；"
            "`created_at=2026-09-10T05:10:03-07:00`；"
            f"bytes SHA-256 `{original_sha}`。 |"
        )
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: line.encode())
    assert locator._verify_original_git_custody(entry)
    entry["origin_path"] = origin.replace("D:\\", "F:\\", 1)
    assert not locator._verify_original_git_custody(entry)
    entry["origin_path"] = origin
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: ("note: " + line).encode())
    assert not locator._verify_original_git_custody(entry)
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: (line + "\n" + line).encode())
    assert not locator._verify_original_git_custody(entry)


def test_git_document_reader_checks_original_blob_sha_size_and_fixed_commit(monkeypatch):
    original = locator._GIT_ORIGINAL_PINS["scheduled_rec_20260910_051003"]
    raw = b"independent original document\n"
    object_raw = b"blob " + str(len(raw)).encode() + b"\0" + raw
    pin = replace(original, raw_sha256=_sha(raw), size_bytes=len(raw),
                  blob_id=hashlib.sha1(object_raw).hexdigest())
    captured = []

    def run(arguments, **options):
        captured.append((arguments, options))
        return SimpleNamespace(
            returncode=0,
            stdout=str(len(raw)).encode() if arguments[-2] == "-s" else raw,
        )

    monkeypatch.setattr(locator.subprocess, "run", run)
    monkeypatch.setattr(locator.Path, "is_file", lambda _: True)
    assert locator._read_original_git_document(pin) == raw
    assert captured[0][0][-1] == f"{original.commit}:{original.document_path}"
    assert captured[0][1]["timeout"] == 5
    assert not any(key.upper().startswith("GIT_") for key in captured[0][1]["env"])
    assert locator._read_original_git_document(replace(pin, blob_id="0" * 40)) is None
    assert locator._read_original_git_document(replace(pin, raw_sha256="sha256:" + "0" * 64)) is None
    assert locator._read_original_git_document(replace(pin, size_bytes=len(raw) + 1)) is None


def test_git_missing_original_or_timeout_does_not_accept_worktree_copy(monkeypatch):
    pin = locator._GIT_ORIGINAL_PINS["scheduled_rec_20260910_051003"]
    monkeypatch.setattr(locator.Path, "is_file", lambda _: True)
    monkeypatch.setattr(locator.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=128, stdout=b""))
    assert locator._read_original_git_document(pin) is None

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(locator.subprocess, "run", timeout)
    assert locator._read_original_git_document(pin) is None


@pytest.mark.parametrize("result_id", [
    "scheduled_rec_20260914_051003", "scheduled_rec_20260917_051002",
    "scheduled_rec_20260921_051002",
])
def test_additional_git_records_require_adjacent_exact_source_identity(monkeypatch, result_id):
    origin = rf"D:\Min\Python\Project\FA_Data\output\recommendation\runs\{result_id}.json"
    source_sha = "sha256:" + "c" * 64
    entry = {
        "result_id": result_id, "origin_path": origin,
        "independent_pre_migration_file_sha256": source_sha,
        "relocated_file_sha256": source_sha,
    }
    if result_id == "scheduled_rec_20260914_051003":
        statement = f"- path：`{origin}`\n- file hash：`{source_sha}`"
    elif result_id == "scheduled_rec_20260917_051002":
        statement = (
            f"| recommendation source | `{origin}`；file hash `{source_sha}`；"
            "`available_at=created_at=2026-09-17T05:10:02-07:00` | "
            "source bytes 在 candidate decision 前已可用。 |"
        )
    else:
        statement = (
            f"`{origin}`\n\n其 `result_id={result_id}`、"
            "`created_at=2026-09-21T05:10:02-07:00`、`decision_date=2026-09-21`、"
            "`decision_at=2026-09-21T12:10:22.626235+00:00`；"
            f"檔案 SHA256 為 `{source_sha}`。snapshot cohort 共 200 rows，原有研究資料。"
        )
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: statement.encode())
    assert locator._verify_original_git_custody(entry)
    bad_statement = statement.replace(origin, origin.replace(result_id, "unrelated_source"))
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: bad_statement.encode())
    assert not locator._verify_original_git_custody(entry)
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: (statement + "\n" + statement).encode())
    assert not locator._verify_original_git_custody(entry)


def test_banktaiwan_git_document_requires_fixed_receipt_and_source_snapshot_proof(monkeypatch):
    result_id = "scheduled_rec_20260915_051003"
    origin = rf"D:\Min\Python\Project\FA_Data\output\recommendation\runs\{result_id}.json"
    source_sha = "sha256:" + "d" * 64
    entry = {
        "result_id": result_id, "origin_path": origin,
        "independent_pre_migration_file_sha256": source_sha,
        "relocated_file_sha256": source_sha,
    }
    snapshot_statement = (
        "前置 dry-run 結果為 exit `0`：官方交易日判定 `true`、snapshot `verified`，"
        f"snapshot hash 仍為 `{source_sha}`，成本情境為 `banktaiwan-electronic-estimate`／"
        "`sha256:73ad38fa8a5cd983535f50fcaf99e168aea44400ac2e7428d58400a21f55e450`，"
        "且 `shadow_only=true`、`formal_order_allowed=false`。"
    )
    receipt_statement = (
        "| operational receipt | `D:\\Min\\Python\\Project\\FA_Data_Shadow_BankTaiwan\\scheduled\\"
        "recommendation_learning_banktaiwan\\runs\\2026-09-15-attempt-002-848408b70b64.json`；"
        f"SHA-256 `{locator._BANKTAIWAN_0915_RECEIPT_SHA256}` |"
    )
    statement = snapshot_statement + "\n\n" + receipt_statement
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: statement.encode())
    monkeypatch.setattr(locator, "_verify_banktaiwan_0915_original_receipt", lambda *_: False)
    assert not locator._verify_original_git_custody(entry)
    monkeypatch.setattr(locator, "_verify_banktaiwan_0915_original_receipt", lambda *_: True)
    assert locator._verify_original_git_custody(entry)
    monkeypatch.setattr(locator, "_read_original_git_document", lambda _: snapshot_statement.encode())
    assert not locator._verify_original_git_custody(entry)


@pytest.mark.parametrize("bad_field", [None, "path", "file_sha256", "status"])
def test_original_banktaiwan_receipt_reads_fixed_bytes_and_exact_snapshot(monkeypatch, bad_field):
    origin = r"D:\Min\Python\Project\FA_Data\output\recommendation\runs\scheduled_rec_20260915_051003.json"
    source_sha = "sha256:" + "d" * 64
    snapshot = {"path": origin, "file_sha256": source_sha, "status": "verified"}
    if bad_field is not None:
        snapshot[bad_field] = "unrelated"
    calls = []

    def read(path, **options):
        calls.append((path, options))
        return json.dumps({"snapshot": snapshot}).encode()

    monkeypatch.setattr(locator, "_read_pinned_profile_target_bytes", read)
    assert locator._verify_banktaiwan_0915_original_receipt(origin, source_sha) == (bad_field is None)
    assert calls[0][0] == locator._BANKTAIWAN_0915_RECEIPT_PATH
    assert calls[0][1]["expected_sha256"] == locator._BANKTAIWAN_0915_RECEIPT_SHA256
    assert calls[0][1]["expected_size"] == locator._BANKTAIWAN_0915_RECEIPT_BYTES


def test_original_banktaiwan_receipt_missing_or_duplicate_identity_rejected(monkeypatch):
    monkeypatch.setattr(locator, "_read_pinned_profile_target_bytes", lambda *_a, **_k: None)
    assert not locator._verify_banktaiwan_0915_original_receipt("origin", "sha")
    duplicate = b'{"snapshot":{"path":"origin","path":"origin","file_sha256":"sha","status":"verified"}}'
    monkeypatch.setattr(locator, "_read_pinned_profile_target_bytes", lambda *_a, **_k: duplicate)
    assert not locator._verify_banktaiwan_0915_original_receipt("origin", "sha")
