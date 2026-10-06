"""完整原保存母體、公用 reader、原 pins 與時序；全部為合成 QA。"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module.recommendation.personal_current_observed_h20_capture import (
    digest, encoded, read_personal_current_observed_h20_capture,
)
from app_module.recommendation.personal_h20_product_evidence import save_personal_h20_daily_manifest
from app_module.recommendation.personal_h20_research_cohort import (
    read_personal_h20_research_cohort, sort_personal_h20_research_rows,
)
from tests.test_personal_current_observed_h20_capture import make_bundle, save


def public_reader(path, *, root, expected_sha256):
    # 合成 verifier 不授予正式來源資格；讀回仍經原完整 capture validator。
    return read_personal_current_observed_h20_capture(path, root=root, expected_sha256=expected_sha256,
        source_verifier=lambda v: deepcopy(v), contract_verifier=lambda v: deepcopy(v))


def saved_cohort(tmp_path, symbols=("1101", "2330", "2454"), values=(120, 120, -50)):
    root, source, contract, prediction = make_bundle(tmp_path)
    source["pins"]["cycle_source_date"] = source["feature_rows_by_symbol"]["2330"]["feature_as_of_date"]
    captures = []
    for symbol, bp in zip(symbols, values, strict=True):
        current_source, current_prediction = deepcopy(source), deepcopy(prediction)
        current_source["feature_rows_by_symbol"] = {symbol: deepcopy(source["feature_rows_by_symbol"]["2330"])}
        current_prediction["request"]["symbol"] = symbol
        current_prediction["predicted_gross_return_bp"] = bp
        current_prediction["prediction_id"] = "personal-h20:" + digest(json.dumps(
            current_prediction["request"], sort_keys=True, separators=(",", ":")).encode())[7:]
        captures.append(save((root, current_source, contract, current_prediction), symbol=symbol))
    activation = SimpleNamespace(personal_root=str(root), market_root=source["data_root"],
        candidate_id=contract["candidate_id"], model_contract_hash=contract["contract_hash"])
    result = dict(status="completed", candidate_id=contract["candidate_id"],
        contract_hash=contract["contract_hash"], cycle_id=source["cycle_id"], captures=captures)
    path, pin, body = save_personal_h20_daily_manifest(activation, result,
        expected_symbols=list(symbols), prediction_reader=public_reader)
    return root, path, pin, body


def read_saved(saved, reader=public_reader):
    root, path, pin, _body = saved
    return read_personal_h20_research_cohort(path, root=root, expected_sha256=pin, prediction_reader=reader)


def repin(saved, body):
    root, _old, _pin, _body = saved
    raw = encoded(body)
    pin = digest(raw)
    path = root / "h20_daily_receipts" / (pin[7:] + ".json")
    path.write_bytes(raw)
    return root, path, pin, body


def test_full_saved_original_public_read_pins_sort_no_recompute_or_source_changes(tmp_path):
    saved = saved_cohort(tmp_path)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    calls = []
    def reader(path, **kwargs):
        calls.append((path, kwargs["expected_sha256"]))
        return public_reader(path, **kwargs)
    cohort = read_saved(saved, reader)
    assert cohort.symbols == ("1101", "2330", "2454")
    assert len(calls) == 3 and len(set(calls)) == 3
    assert [r.symbol for r in sort_personal_h20_research_rows(cohort)] == ["1101", "2330", "2454"]
    assert [r.symbol for r in sort_personal_h20_research_rows(cohort, descending=False)] == ["2454", "1101", "2330"]
    assert all(r.status == "available" for r in cohort.rows)
    assert read_saved(saved) == cohort
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()} == before
    with pytest.raises(FrozenInstanceError):
        cohort.cycle_id = "other"


@pytest.mark.parametrize("count", [1, 50])
def test_saved_denominator_bounds(tmp_path, count):
    cohort = read_saved(saved_cohort(tmp_path, tuple(f"{i:04d}" for i in range(count)), (1,) * count))
    assert len(cohort.rows) == count


@pytest.mark.parametrize("failure", ["missing", "tampered", "source_unavailable"])
def test_unavailable_member_keeps_exact_unknown_row_and_denominator(tmp_path, failure):
    saved = saved_cohort(tmp_path)
    pin = saved[3]["captures"][0]
    path = Path(pin["path"])
    if failure == "missing":
        path.unlink()
    elif failure == "tampered":
        path.write_bytes(path.read_bytes() + b" ")
    def reader(path, **kwargs):
        if failure == "source_unavailable" and path == pin["path"]:
            raise ValueError("original_source_unavailable")
        return public_reader(path, **kwargs)
    cohort = read_saved(saved, reader)
    row = next(r for r in cohort.rows if r.symbol == pin["symbol"])
    assert row.status == "unknown" and row.gross_return_bp is None
    assert row.sample_id == pin["sample_id"] and row.prediction_id == pin["prediction_id"]
    assert row.capture_path == pin["path"] and row.capture_sha256 == pin["raw_sha256"]
    assert row.source_date is None and row.feature_as_of_date is None
    assert len(cohort.rows) == 3
    for direction in (True, False):
        assert sort_personal_h20_research_rows(cohort, descending=direction)[-1] == row


@pytest.mark.parametrize("mutation", ["empty", "over50", "missing_member", "duplicate_symbol", "duplicate_sample",
    "outside", "wrong_schema", "qualification", "contract", "cycle", "date", "candidate", "sample", "prediction"])
def test_manifest_scope_or_identity_fail_closed(tmp_path, mutation):
    saved = saved_cohort(tmp_path)
    body = deepcopy(saved[3])
    if mutation == "empty": body["symbols"] = []
    elif mutation == "over50": body["symbols"] = [str(i) for i in range(51)]
    elif mutation == "missing_member": body["captures"].pop()
    elif mutation == "duplicate_symbol": body["symbols"][1] = body["symbols"][0]
    elif mutation == "duplicate_sample": body["captures"][1]["sample_id"] = body["captures"][0]["sample_id"]
    elif mutation == "outside": body["captures"][0]["path"] = str(tmp_path / "other.json")
    elif mutation == "wrong_schema": body["schema_version"] = "other"
    elif mutation == "qualification": body["production_action_allowed"] = True
    elif mutation == "contract": body["contract_hash"] = "sha256:" + "b" * 64
    elif mutation == "cycle": body["cycle_id"] = "other"
    elif mutation == "date": body["decision_date"] = "2026-01-01"
    elif mutation == "candidate": body["candidate_id"] = "other"
    elif mutation == "sample": body["captures"][0]["sample_id"] = "other"
    elif mutation == "prediction": body["captures"][0]["prediction_id"] = "other"
    with pytest.raises(ValueError):
        read_saved(repin(saved, body))


def test_manifest_raw_filename_pin_budget_and_duplicate_keys(tmp_path):
    saved = saved_cohort(tmp_path)
    root, path, pin, body = saved
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="raw_pin"):
        read_saved(saved)
    for raw in (b'{"symbols":[],"symbols":[]}', b" " * (64 * 1024 + 1)):
        newpin = digest(raw)
        newpath = path.with_name(newpin[7:] + ".json")
        newpath.write_bytes(raw)
        with pytest.raises(Exception):
            read_saved((root, newpath, newpin, body))
    with pytest.raises(ValueError, match="exact_store"):
        read_personal_h20_research_cohort(path, root=root, expected_sha256="sha256:" + "b" * 64,
            prediction_reader=public_reader)


def test_manifest_mutation_during_reader_rejected(tmp_path):
    saved = saved_cohort(tmp_path)
    def reader(path, **kwargs):
        capture = public_reader(path, **kwargs)
        saved[1].write_bytes(saved[1].read_bytes() + b" ")
        return capture
    with pytest.raises(ValueError, match="raw_pin"):
        read_saved(saved, reader)


@pytest.mark.parametrize("field", ["observed_at", "feature_as_of_date", "source_date", "symbol"])
def test_returned_wrong_clock_future_features_or_symbol_rejected(tmp_path, field):
    saved = saved_cohort(tmp_path)
    def reader(path, **kwargs):
        payload = public_reader(path, **kwargs)
        if field == "observed_at": payload[field] = "2026-01-01T10:00:00"
        elif field == "feature_as_of_date": payload["prediction"]["request"][field] = payload["source_binding"]["decision_date"]
        elif field == "source_date": payload["source_binding"]["pins"]["cycle_source_date"] = "2099-01-01"
        else: payload["identity"]["symbol"] = "other"
        return payload
    with pytest.raises(ValueError):
        read_saved(saved, reader)


def test_hardlinked_manifest_rejected(tmp_path):
    saved = saved_cohort(tmp_path)
    os.link(saved[1], tmp_path / "alias.json")
    with pytest.raises(ValueError, match="single_link"):
        read_saved(saved)


def test_cancelled_reader_does_not_return_partial_cohort(tmp_path):
    saved = saved_cohort(tmp_path)
    def cancelled(*a, **k):
        raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        read_saved(saved, cancelled)


def test_manifest_same_bytes_new_stat_during_read_rejected(tmp_path):
    saved = saved_cohort(tmp_path)
    def reader(path, **kwargs):
        payload = public_reader(path, **kwargs)
        stat = saved[1].stat()
        os.utime(saved[1], ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return payload
    with pytest.raises(ValueError, match="changed_during_read"):
        read_saved(saved, reader)


def test_sort_rejects_noninteger_not_probability(tmp_path):
    cohort = read_saved(saved_cohort(tmp_path))
    with pytest.raises(ValueError, match="integer_gross"):
        sort_personal_h20_research_rows(replace(cohort, rows=(replace(cohort.rows[0], gross_return_bp=True),)))


def test_original_manifest_and_public_reader_fresh_process(tmp_path):
    root, path, pin, _body = saved_cohort(tmp_path)
    code = """
import json,sys
from tests.test_personal_h20_research_cohort import public_reader
from app_module.recommendation.personal_h20_research_cohort import read_personal_h20_research_cohort,sort_personal_h20_research_rows
c=read_personal_h20_research_cohort(sys.argv[1],root=sys.argv[2],expected_sha256=sys.argv[3],prediction_reader=public_reader)
print(json.dumps([r.symbol for r in sort_personal_h20_research_rows(c)]))
"""
    result = subprocess.run([sys.executable, "-c", code, str(path), str(root), pin],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["1101", "2330", "2454"]
