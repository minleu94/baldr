"""H20 讀取驗證分組的合成測試。"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

import app_module.recommendation.personal_current_observed_h20_capture as capture_module
from app_module.recommendation.personal_h20_read_session import (
    PersonalH20ReadProgress,
    PersonalH20ReadSession,
    PersonalH20ReadSessionError,
)


def _binding(observed_at: str = "2026-10-07T10:00:00+00:00") -> dict[str, object]:
    return {
        "cycle_id": "cycle-1",
        "pins": {
            "snapshot_database_sha256": "sha256:" + "a" * 64,
            "observed_at": observed_at,
        },
        "feature_rows_by_symbol": {"2330": {"values": [["ma20", 42]]}},
    }


def test_exact_canonical_groups_cache_only_inside_session_and_return_independent_values():
    calls = {"source": 0, "contract": 0}
    source = _binding()
    contract = {"contract_hash": "sha256:" + "b" * 64, "feature_schema": [["x", "integer"]]}
    progress: list[PersonalH20ReadProgress] = []

    def verify_source(value):
        calls["source"] += 1
        return deepcopy(value)

    def verify_contract(value):
        calls["contract"] += 1
        return deepcopy(value)

    session = PersonalH20ReadSession(
        source_verifier=verify_source,
        contract_verifier=verify_contract,
        progress_callback=progress.append,
    )
    first_source = session.verify_source(source)
    first_source["feature_rows_by_symbol"]["2330"]["values"][0][1] = 999
    reordered_source = {
        "feature_rows_by_symbol": {"2330": {"values": [["ma20", 42]]}},
        "pins": deepcopy(source["pins"]),
        "cycle_id": "cycle-1",
    }
    assert session.verify_source(reordered_source)["feature_rows_by_symbol"]["2330"]["values"] == [["ma20", 42]]
    assert session.verify_contract(contract) == contract
    assert session.verify_contract(deepcopy(contract)) == contract
    assert calls == {"source": 1, "contract": 1}

    session.finish()

    assert calls == {"source": 2, "contract": 2}
    assert any(event.stage == "source_group_reused" for event in progress)
    assert any(event.stage == "source_group_rechecked" and event.group_total == 1 for event in progress)
    with pytest.raises(PersonalH20ReadSessionError, match="session_closed"):
        session.verify_source(source)

    second_operation = PersonalH20ReadSession(source_verifier=verify_source, contract_verifier=verify_contract)
    second_operation.verify_source(source)
    second_operation.finish()
    assert calls == {"source": 4, "contract": 2}


def test_observed_at_is_part_of_exact_source_group_identity():
    calls = 0

    def verify(value):
        nonlocal calls
        calls += 1
        return deepcopy(value)

    session = PersonalH20ReadSession(source_verifier=verify, contract_verifier=verify)
    session.verify_source(_binding("2026-10-07T10:00:00+00:00"))
    session.verify_source(_binding("2026-10-07T10:00:01+00:00"))
    assert session.source_group_count == 2
    assert calls == 2
    session.finish()
    assert calls == 4


@pytest.mark.parametrize("kind", ["source", "contract"])
def test_finish_rejects_verifier_binding_change(kind):
    calls = 0

    def verify(value):
        nonlocal calls
        calls += 1
        return {**value, "verified_revision": 1 if calls == 1 else 2}

    source_verifier = verify if kind == "source" else deepcopy
    contract_verifier = verify if kind == "contract" else deepcopy
    session = PersonalH20ReadSession(source_verifier=source_verifier, contract_verifier=contract_verifier)
    if kind == "source":
        session.verify_source(_binding())
    else:
        session.verify_contract({"contract_hash": "sha256:" + "b" * 64})

    with pytest.raises(PersonalH20ReadSessionError, match=f"{kind}_changed_during_read"):
        session.finish()


def test_cancel_is_strict_bool_and_interrupts_between_verifier_steps():
    cancel_results = iter((False, False, False, True))
    calls = 0

    def cancel():
        return next(cancel_results)

    def verify(value):
        nonlocal calls
        calls += 1
        return deepcopy(value)

    session = PersonalH20ReadSession(
        source_verifier=verify,
        contract_verifier=verify,
        cancel_callback=cancel,
    )
    with pytest.raises(InterruptedError, match="personal_h20_read_cancelled"):
        session.verify_source(_binding())
    assert calls == 1
    assert session.source_group_count == 0

    invalid = PersonalH20ReadSession(
        source_verifier=verify,
        contract_verifier=verify,
        cancel_callback=lambda: 1,
    )
    with pytest.raises(PersonalH20ReadSessionError, match="cancel_callback_must_return_bool"):
        invalid.verify_source(_binding())


def test_progress_callback_errors_propagate_without_skipping_verification():
    calls = 0

    def verify(value):
        nonlocal calls
        calls += 1
        return deepcopy(value)

    def broken_progress(_event):
        raise RuntimeError("progress channel failed")

    session = PersonalH20ReadSession(
        source_verifier=verify,
        contract_verifier=verify,
        progress_callback=broken_progress,
    )
    with pytest.raises(RuntimeError, match="progress channel failed"):
        session.verify_source(_binding())
    assert calls == 0


def test_verifier_return_mutation_is_detected_at_finish():
    returned = {"values": [1]}

    def verify(_value):
        return returned

    session = PersonalH20ReadSession(source_verifier=verify, contract_verifier=verify)
    first = session.verify_source(_binding())
    first["values"].append(2)
    assert session.verify_source(_binding()) == {"values": [1]}
    returned["values"].append(3)
    with pytest.raises(PersonalH20ReadSessionError, match="source_changed_during_read"):
        session.finish()


def _saved_h20_product(tmp_path: Path, *, missing_stock: str | None = None):
    from app_module.recommendation.personal_h20_activation import (
        publish_personal_h20_activation,
    )
    from app_module.recommendation.personal_h20_product_evidence import (
        read_personal_h20_product_reference,
    )
    from tests.test_personal_current_observed_h20_capture import make_bundle
    from tests.test_personal_h20_activation import _activation

    root, source, contract, prediction = make_bundle(tmp_path)
    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    source = deepcopy(source)
    source["data_root"] = activation.market_root
    source["symbols"] = ["1101", "2330"]
    source["pins"]["cycle_source_date"] = source["decision_date"]
    source["feature_rows_by_symbol"]["1101"] = deepcopy(source["feature_rows_by_symbol"]["2330"])
    contract = deepcopy(contract)
    contract.update(
        candidate_id=activation.candidate_id,
        contract_hash=activation.model_contract_hash,
        model_id=activation.model_id,
        fit_receipt_path=activation.fit_receipt,
        fit_receipt_sha256=activation.fit_receipt_sha256,
    )
    root = Path(activation.personal_root)
    predictions_dir = root / "h20_predictions"
    receipts_dir = root / "h20_daily_receipts"
    predictions_dir.mkdir(exist_ok=True)
    receipts_dir.mkdir(exist_ok=True)
    pins = []
    for symbol in ("1101", "2330"):
        row = source["feature_rows_by_symbol"][symbol]
        original = deepcopy(prediction)
        request = original["request"]
        request.update(
            symbol=symbol,
            feature_snapshot_hash=row["row_sha256"],
            feature_source_hash=source["source_fingerprint"],
            model_contract_hash=contract["contract_hash"],
        )
        original.update(
            model_id=contract["model_id"],
            model_contract_hash=contract["contract_hash"],
            artifact_hash=contract["artifact_hash"],
            lineage_hash=contract["lineage_hash"],
            prediction_id="personal-h20:" + capture_module.digest(json.dumps(
                request, sort_keys=True, separators=(",", ":")).encode("utf-8"))[7:],
        )
        identity = capture_module._binding(source, contract, symbol)
        sample_id = "h20-observed:" + capture_module.digest(capture_module.encoded(identity))[7:]
        body = {
            "schema_version": capture_module.SCHEMA,
            "sample_id": sample_id,
            "identity": identity,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_binding": source,
            "contract_binding": contract,
            "prediction": original,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "production_action_allowed": False,
            "promotion_credit_created": False,
            "research_only": True,
            "natural_outcome_status": "pending_exact_entry_capture_and_twenty_sessions",
        }
        body["payload_sha256"] = capture_module.digest(capture_module.encoded(body))
        capture_module._validate(body, deepcopy, deepcopy)
        raw = capture_module.encoded(body)
        raw_pin = capture_module.digest(raw)
        capture_path = predictions_dir / (capture_module._retry_key(identity) + ".json")
        if symbol != missing_stock:
            capture_path.write_bytes(raw)
        pins.append({
            "symbol": symbol,
            "path": str(capture_path),
            "raw_sha256": raw_pin,
            "sample_id": sample_id,
            "prediction_id": original["prediction_id"],
        })

    manifest_body = {
        "schema_version": "personal-h20-daily-manifest.v1",
        "status": "completed",
        "candidate_id": activation.candidate_id,
        "contract_hash": activation.model_contract_hash,
        "cycle_id": source["cycle_id"],
        "decision_date": source["decision_date"],
        "symbols": ["1101", "2330"],
        "captures": pins,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "production_action_allowed": False,
    }
    manifest_raw = json.dumps(
        manifest_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    manifest_path = receipts_dir / f"{manifest_sha}.json"
    manifest_path.write_bytes(manifest_raw)
    reference_body = {
        "schema_version": "personal-h20-product-reference.v1",
        "activation_revision": activation.revision,
        "scope_id": activation.scope_id,
        "candidate_id": activation.candidate_id,
        "contract_hash": activation.model_contract_hash,
        "receipt_path": str(manifest_path),
        "receipt_sha256": "sha256:" + manifest_sha,
        "cycle_id": source["cycle_id"],
        "decision_date": source["decision_date"],
    }
    pointer = root / "h20_product_reference.json"
    pointer.write_bytes(json.dumps(
        reference_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))
    reference = read_personal_h20_product_reference(
        activation.config_path, market_root=Path(activation.market_root)
    )
    return activation, root, manifest_path, reference


def test_hook_cohort_groups_source_and_contract_but_rechecks_every_capture(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, _root, _manifest, _reference = _saved_h20_product(tmp_path)
    calls = {"source": 0, "contract": 0}

    def source_verifier(binding):
        calls["source"] += 1
        return deepcopy(binding)

    def contract_verifier(binding):
        calls["contract"] += 1
        return deepcopy(binding)

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": source_verifier,
        "contract_verifier": contract_verifier,
    })
    progress: list[str] = []
    reference, cohort = hook.read_personal_h20_product_cohort(
        activation.config_path,
        market_root=Path(activation.market_root),
        progress_callback=progress.append,
    )

    assert reference == _reference
    assert cohort.symbols == ("1101", "2330")
    assert [row.status for row in cohort.rows] == ["available", "available"]
    # Initial exact read verifies one canonical source and contract group.
    # Terminal pass re-reads both captures through the same operation cache;
    # finish then fresh-verifies the two groups once.
    assert calls == {"source": 2, "contract": 2}
    assert any("第 1 列" in message for message in progress)
    assert "H20 終態重讀完成，共驗證 2 列 pin" in progress
    assert any("終態重讀原 manifest 與全部 capture pins" in message for message in progress)
    assert any("終態重驗來源第 1 組／共 1 組" in message for message in progress)


def test_hook_stock_read_reuses_session_for_daily_and_prediction_reader(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, _root, _manifest, reference = _saved_h20_product(tmp_path)
    calls = {"source": 0, "contract": 0}

    def source_verifier(binding):
        calls["source"] += 1
        return deepcopy(binding)

    def contract_verifier(binding):
        calls["contract"] += 1
        return deepcopy(binding)

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": source_verifier,
        "contract_verifier": contract_verifier,
    })
    evidence = hook.read_personal_h20_product_for_stock_with_session(
        activation.config_path,
        stock_code="2330",
        market_root=Path(activation.market_root),
        expected_reference=reference,
    )

    assert evidence.status == "available"
    # The first manifest-selected read and the product's explicit prediction
    # read share a canonical group; the final exact manifest read also uses it.
    assert calls == {"source": 2, "contract": 2}


def test_hook_keeps_missing_capture_as_unknown_and_propagates_cancel(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, _root, _manifest, _reference = _saved_h20_product(tmp_path, missing_stock="1101")
    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": deepcopy,
        "contract_verifier": deepcopy,
    })
    reference, cohort = hook.read_personal_h20_product_cohort(
        activation.config_path, market_root=Path(activation.market_root)
    )
    assert reference.manifest_path == _manifest
    assert [(row.symbol, row.status) for row in cohort.rows] == [
        ("1101", "unknown"), ("2330", "available")
    ]

    with pytest.raises(InterruptedError, match="personal_h20_read_cancelled"):
        hook.read_personal_h20_product_cohort(
            activation.config_path,
            market_root=Path(activation.market_root),
            cancel_callback=lambda: True,
        )


@pytest.mark.parametrize("changed_pin", ["capture", "reference"])
def test_hook_rejects_source_or_manifest_dependencies_changed_during_finish(
    tmp_path, monkeypatch, changed_pin
):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, root, manifest_path, _reference = _saved_h20_product(tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    selected_capture = Path(next(pin["path"] for pin in manifest["captures"] if pin["symbol"] == "2330"))
    calls = 0

    def source_verifier(binding):
        nonlocal calls
        calls += 1
        if calls == 2:
            if changed_pin == "capture":
                selected_capture.write_bytes(selected_capture.read_bytes() + b" ")
            else:
                pointer = root / "h20_product_reference.json"
                body = json.loads(pointer.read_bytes())
                body["cycle_id"] = "changed-cycle"
                pointer.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return deepcopy(binding)

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": source_verifier,
        "contract_verifier": deepcopy,
    })
    expected_reason = (
        "personal_h20_cohort_changed_during_terminal_read"
        if changed_pin == "capture"
        else "personal_h20_cohort_reference_changed"
    )
    with pytest.raises(ValueError, match=expected_reason):
        hook.read_personal_h20_product_cohort(
            activation.config_path, market_root=Path(activation.market_root)
        )


def test_hook_cancel_during_terminal_capture_read_is_not_returned_as_unknown(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, _root, _manifest, _reference = _saved_h20_product(tmp_path)
    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": deepcopy,
        "contract_verifier": deepcopy,
    })
    cancelled = False

    def progress(message):
        nonlocal cancelled
        if "終態重讀已保存第 1 列：完成" in message:
            cancelled = True

    with pytest.raises(InterruptedError, match="personal_h20_read_cancelled"):
        hook.read_personal_h20_product_cohort(
            activation.config_path,
            market_root=Path(activation.market_root),
            cancel_callback=lambda: cancelled,
            progress_callback=progress,
        )


def test_hook_progress_callback_failure_cannot_turn_valid_capture_into_unknown(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    activation, _root, _manifest, _reference = _saved_h20_product(tmp_path)
    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", lambda: {
        "source_verifier": deepcopy,
        "contract_verifier": deepcopy,
    })

    def broken_progress(message):
        if "讀取已保存第 1 列" in message:
            raise RuntimeError("progress channel failed")

    with pytest.raises(PersonalH20ReadSessionError, match="progress_callback_failed"):
        hook.read_personal_h20_product_cohort(
            activation.config_path,
            market_root=Path(activation.market_root),
            progress_callback=broken_progress,
        )
