from __future__ import annotations

from datetime import date
import json

import pytest

import ml_module.recommendation_calibration_evidence as evidence


def _binding_fixture(tmp_path, rows):
    feature_body = {
        "component": "prospective_recommendation_features",
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "rows": rows,
    }
    feature_snapshot = {
        **feature_body,
        "row_count": len(rows),
        "status": "captured",
        "verified": True,
    }
    feature_snapshot["content_sha256"] = evidence._hash_payload(feature_snapshot)
    body = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "lanes": {
            "price_up_calibration": {
                "prospective_status": "ready",
                "prospective_blockers": [],
            }
        },
        "technical": {"prospective_feature_snapshot": feature_snapshot},
    }
    payload = {**body, "contract_sha256": evidence._hash_payload(body)}
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    contract_file_hash = evidence._sha256_file(contract_path)
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path),
        "contract_content_sha256": payload["contract_sha256"],
        "contract_file_sha256": contract_file_hash,
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "price_up_prospective_status": "ready",
        "historical_pit_eligible": False,
        "capture_decision_date": "2026-09-14",
        "capture_symbols": ["1101"],
        "feature_row_count": len(rows),
        "feature_snapshot_fingerprint": evidence._feature_snapshot_fingerprint(
            date(2026, 9, 14), rows
        ),
        "feature_snapshot_content_sha256": feature_snapshot["content_sha256"],
    }
    return binding


def test_source_binding_rejects_wrong_symbol_date_and_feature_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_verify_source_contract_dependencies", lambda *_: None)
    rows = [
        {
            "row_id": "row-1101",
            "symbol": "1101",
            "decision_date": "2026-09-14",
            "feature_as_of_date": "2026-09-11",
            "feature_available_date": "2026-09-11",
            "feature_values": [1, 2, 3],
        }
    ]
    binding = _binding_fixture(tmp_path, rows)
    evidence._verify_source_contract_binding(
        binding,
        require_ready=True,
        capture_day=date(2026, 9, 14),
        capture_rows=rows,
    )

    wrong_symbol = [dict(rows[0], symbol="2330")]
    with pytest.raises(ValueError, match="symbols|symbol"):
        evidence._verify_source_contract_binding(
            binding,
            require_ready=True,
            capture_day=date(2026, 9, 14),
            capture_rows=wrong_symbol,
        )

    with pytest.raises(ValueError, match="cutoff|date"):
        evidence._verify_source_contract_binding(
            binding,
            require_ready=True,
            capture_day=date(2026, 9, 15),
            capture_rows=rows,
        )

    changed_features = [dict(rows[0], feature_values=[99, 2, 3])]
    with pytest.raises(ValueError, match="fingerprint"):
        evidence._verify_source_contract_binding(
            binding,
            require_ready=True,
            capture_day=date(2026, 9, 14),
            capture_rows=changed_features,
        )


def test_source_binding_rejects_same_day_technical_value_substitution(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_verify_source_contract_dependencies", lambda *_: None)
    rows = [
        {
            "row_id": "row-1101",
            "symbol": "1101",
            "decision_date": "2026-09-14",
            "feature_as_of_date": "2026-09-11",
            "feature_available_date": "2026-09-11",
            # These values stand for the canonical derived vector whose RSI,
            # MACD and ADX components must remain bound to the source audit.
            "feature_values": [55, 15, 20],
        }
    ]
    feature_rows = [
        {
            "symbol": "1101",
            "decision_date": "2026-09-14",
            "feature_as_of_date": "2026-09-11",
            "feature_available_date": "2026-09-11",
            "feature_ids": ["rsi", "macd", "adx"],
            "feature_values": [55, 15, 20],
            "snapshot_hash": "sha256:" + ("1" * 64),
        }
    ]
    feature_body = {
        "component": "prospective_recommendation_features",
        "source_db": str(tmp_path / "source.db"),
        "decision_date": "2026-09-14",
        "history_start_date": "2026-01-01",
        "feature_registry_hash": "sha256:" + ("2" * 64),
        "feature_schema_hash": "sha256:" + ("3" * 64),
        "symbols": ["1101"],
        "rows": feature_rows,
    }
    feature_snapshot = {
        "status": "captured",
        "verified": True,
        **feature_body,
        "row_count": 1,
        "rows_sha256": evidence._hash_payload(feature_body),
        "reason": None,
    }
    feature_snapshot["content_sha256"] = evidence._hash_payload(
        {key: value for key, value in feature_snapshot.items() if key != "content_sha256"}
    )
    contract_body = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "lanes": {
            "price_up_calibration": {
                "prospective_status": "ready",
                "prospective_blockers": [],
            }
        },
        "technical": {"prospective_feature_snapshot": feature_snapshot},
    }
    contract_payload = {
        **contract_body,
        "contract_sha256": evidence._hash_payload(contract_body),
    }
    contract_path = tmp_path / "contract-with-feature-snapshot.json"
    contract_path.write_text(json.dumps(contract_payload, sort_keys=True) + "\n", encoding="utf-8")
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": str(contract_path),
        "contract_content_sha256": contract_payload["contract_sha256"],
        "contract_file_sha256": evidence._sha256_file(contract_path),
        "decision_date": "2026-09-14",
        "symbols": ["1101"],
        "price_up_prospective_status": "ready",
        "historical_pit_eligible": False,
        "capture_decision_date": "2026-09-14",
        "capture_symbols": ["1101"],
        "feature_row_count": 1,
        "feature_snapshot_fingerprint": evidence._feature_snapshot_fingerprint(
            date(2026, 9, 14), rows
        ),
        "feature_snapshot_content_sha256": feature_snapshot["content_sha256"],
        "feature_snapshot_rows_sha256": feature_snapshot["rows_sha256"],
    }
    evidence._verify_source_contract_binding(
        binding,
        require_ready=True,
        capture_day=date(2026, 9, 14),
        capture_rows=rows,
    )

    substituted_rows = [dict(rows[0], feature_values=[99, 15, 20])]
    substituted_binding = dict(binding)
    substituted_binding["feature_snapshot_fingerprint"] = evidence._feature_snapshot_fingerprint(
        date(2026, 9, 14), substituted_rows
    )
    with pytest.raises(ValueError, match="feature values"):
        evidence._verify_source_contract_binding(
            substituted_binding,
            require_ready=True,
            capture_day=date(2026, 9, 14),
            capture_rows=substituted_rows,
        )
