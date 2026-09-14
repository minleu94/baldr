from __future__ import annotations

import hashlib
import json

import pytest

from data_module.corporate_action_adjustment_custody import (
    publish_corporate_action_adjustment_custody,
)


def _hash_json(value):
    return "sha256:" + hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _hash_file(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _publication_fixture(root, *, prospective=False):
    publication_root = root / "release_v4" / "official_market_events"
    run_root = publication_root / "runs" / "publication-1"
    raw_root = run_root / "raw"
    canonical_root = run_root / "canonical"
    raw_root.mkdir(parents=True)
    canonical_root.mkdir(parents=True)

    raw_path = raw_root / "response.json"
    raw_path.write_bytes(b'{"official":true}\n')
    raw_hash = _hash_file(raw_path)
    raw_index_path = run_root / "raw_index.jsonl"
    raw_index_path.write_text(
        json.dumps(
            {"response_path": "raw/response.json", "response_sha256": raw_hash},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    events = [
        {
            "event_id": "event-good",
            "source_id": "twse.TWT49U.ex_right_dividend_result",
            "source_version": "test-v1",
            "event_type": "ex_right_dividend_result",
            "result_only": True,
            "symbol": "1101",
            "effective_at": "2026-09-14T00:00:00+08:00",
            "available_at": "2026-09-14T00:00:00+08:00",
            "raw_response_sha256": raw_hash,
            "source_record_hash": "sha256:record-good",
            "source_record": {"除權息前收盤價": "100", "除權息參考價": "95"},
        },
        {
            "event_id": "event-missing-factor",
            "source_id": "twse.TWT49U.ex_right_dividend_result",
            "source_version": "test-v1",
            "event_type": "ex_right_dividend_result",
            "result_only": True,
            "symbol": "2330",
            "effective_at": "2026-09-14T00:00:00+08:00",
            "available_at": "2026-09-14T00:00:00+08:00",
            "raw_response_sha256": raw_hash,
            "source_record_hash": "sha256:record-missing",
            "source_record": {"除權息前收盤價": "100", "除權息參考價": "--"},
        },
    ]
    canonical_path = canonical_root / "events.jsonl"
    canonical_path.write_bytes(
        b"".join((json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for event in events)
    )
    canonical_hash = _hash_file(canonical_path)
    raw_index_hash = _hash_file(raw_index_path)
    manifest_body = {
        "schema_version": "official-market-event-publication.v1",
        "publication_id": "publication-1",
        "status": (
            "prospective_source_publication"
            if prospective
            else "formal_source_publication"
        ),
        "publication_scope": (
            "prospective_bounded" if prospective else "formal_historical"
        ),
        "generated_at": "2026-09-14T01:00:00+08:00",
        "request": {"start_year": 2026, "end_year": 2026},
        "raw_index": {"path": "raw_index.jsonl", "file_hash": raw_index_hash},
        "canonical_events": {
            "path": "canonical/events.jsonl",
            "file_hash": canonical_hash,
            "event_count": len(events),
        },
    }
    manifest = {**manifest_body, "manifest_hash": _hash_json(manifest_body)}
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    pointer_name = (
        "prospective_latest_manifest.json"
        if prospective
        else "latest_manifest.json"
    )
    publication_root.joinpath(pointer_name).write_text(
        json.dumps(
            {
                "schema_version": "official-market-event-latest.v1",
                "publication_id": "publication-1",
                "manifest_path": "runs/publication-1/manifest.json",
                "manifest_hash": manifest["manifest_hash"],
                "manifest_file_hash": _hash_file(manifest_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return publication_root


def test_corporate_action_custody_derives_factor_and_preserves_missing_factor(tmp_path):
    publication_root = _publication_fixture(tmp_path)
    result = publish_corporate_action_adjustment_custody(
        publication_root=publication_root,
        output_root=tmp_path / "output",
    )
    assert result["status"] == "published"
    assert result["factor_available_count"] == 1
    assert result["factor_missing_count"] == 1

    rows = [
        json.loads(line)
        for line in (
            tmp_path / "output" / "release_v4" / "corporate_action_adjustments"
            / "runs" / result["custody_id"] / "adjustments.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["1101"]["adjustment_factor"] == "0.95"
    assert by_symbol["2330"]["adjustment_factor"] is None
    assert by_symbol["2330"]["quality_status"] == "official_result_factor_missing"
    assert by_symbol["2330"]["historical_pit_eligible"] is False


def test_corporate_action_custody_rejects_tampered_official_raw_response(tmp_path):
    publication_root = _publication_fixture(tmp_path)
    raw_path = publication_root / "runs" / "publication-1" / "raw" / "response.json"
    raw_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="raw_response_hash_mismatch"):
        publish_corporate_action_adjustment_custody(
            publication_root=publication_root,
            output_root=tmp_path / "output",
        )


def test_corporate_action_custody_accepts_bounded_prospective_pointer(tmp_path):
    publication_root = _publication_fixture(tmp_path, prospective=True)
    result = publish_corporate_action_adjustment_custody(
        publication_root=publication_root,
        output_root=tmp_path / "output",
        manifest_pointer_path=publication_root / "prospective_latest_manifest.json",
        prospective=True,
    )
    assert result["status"] == "published"
    assert result["source_publication_scope"] == "prospective_bounded"
