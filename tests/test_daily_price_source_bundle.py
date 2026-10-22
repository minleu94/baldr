from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import data_module.daily_price_source_bundle as source_bundle_module
from data_module.daily_price_source_bundle import (
    BUNDLE_SCHEMA,
    LOCATOR_SCHEMA,
    _canonical,
    load_daily_price_source_bundle,
    publish_daily_price_source_bundle,
)


_FAMILIES = {
    "twse.mi_index.daily_price": (
        "twse-daily-price-sqlite-publication.v1",
        "twse_daily_price_sqlite_publication",
    ),
    "tpex.daily_close_quotes": (
        "tpex-daily-price-sqlite-publication.v1",
        "tpex_daily_price_sqlite_publication",
    ),
}


def _publish_fixture(
    tmp_path: Path,
    *,
    sources: tuple[str, ...] = ("twse.mi_index.daily_price", "tpex.daily_close_quotes"),
    quick_status: str = "passed",
) -> tuple[Path, Path, Path, dict[str, Any]]:
    output = tmp_path / "output"
    data = tmp_path / "data"
    output.mkdir()
    data.mkdir()
    database = data / "sqlite" / "twstock.db"
    database.parent.mkdir()
    database.write_bytes(b"sqlite-test-identity")
    descriptors: dict[str, dict[str, object]] = {}
    for source_id in sources:
        schema, directory = _FAMILIES[source_id]
        body: dict[str, object] = {
            "schema_version": schema,
            "source_id": source_id,
            "database_relative_path": "sqlite/twstock.db",
            "rows": [{"source_date": "20261022", "stock_code": "2330"}],
        }
        if source_id == "tpex.daily_close_quotes":
            body.update(
                {
                    "formal_source_contract_eligible": False,
                    "pit_eligible": False,
                    "training_eligible": False,
                }
            )
        raw = _canonical(
            {**body, "content_sha256": "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()}
        ) + b"\n"
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        relative = f"scheduled/{directory}/{digest[7:9]}/{digest[7:]}.json"
        path = output / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        descriptors[source_id] = {
            "status": "captured",
            "schema_version": schema,
            "relative_path": relative,
            "sha256": digest,
            "row_count": 1,
        }
    bundle = publish_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        quick_run_id="20261022-4400",
        completed_at="2026-10-22T16:02:03+08:00",
        quick_status=quick_status,
        descriptors=descriptors,
    )
    return output, data, database, bundle


def test_bundle_round_trip_uses_exact_captured_source_families_and_latest_locator(
    tmp_path: Path,
) -> None:
    output, data, database, descriptor = _publish_fixture(tmp_path)

    assert descriptor["status"] == "captured"
    assert descriptor["schema_version"] == BUNDLE_SCHEMA
    assert isinstance(descriptor["reference"], dict)
    loaded = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        descriptor=descriptor,
    )
    assert loaded["status"] == "captured"
    assert set(loaded["descriptors"]) == set(_FAMILIES)
    assert loaded["reference"] == descriptor["reference"]
    assert loaded["source_use_accepted"] is False
    assert loaded["source_published_at"] is None
    assert loaded["available_at"] is None
    assert loaded["pit_eligible"] is False
    assert loaded["training_eligible"] is False
    assert loaded["bundle"]["natural_success"] is False
    assert loaded["bundle"]["quick_execution_passed"] is True

    latest = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
    )
    assert latest["status"] == "captured"
    assert latest["reference"] == descriptor["reference"]


def test_quick_execution_status_does_not_claim_natural_success(
    tmp_path: Path,
) -> None:
    output, data, database, descriptor = _publish_fixture(
        tmp_path, quick_status="failed"
    )
    loaded = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        descriptor=descriptor,
    )
    assert loaded["status"] == "captured"
    assert loaded["bundle"]["quick_status"] == "failed"
    assert loaded["bundle"]["natural_success"] is False
    assert loaded["bundle"]["quick_execution_passed"] is False
    assert loaded["bundle"]["pit_eligible"] is False
    assert loaded["bundle"]["training_eligible"] is False


def test_bundle_requires_at_least_one_real_captured_descriptor(tmp_path: Path) -> None:
    output = tmp_path / "output"
    data = tmp_path / "data"
    output.mkdir()
    data.mkdir()
    database = data / "db.sqlite"
    database.write_bytes(b"db")
    with pytest.raises(ValueError, match="publication_descriptors_missing"):
        publish_daily_price_source_bundle(
            output_root=output,
            data_root=data,
            database_path=database,
            quick_run_id="run-1",
            completed_at=datetime.now(timezone.utc).isoformat(),
            quick_status="passed",
            descriptors={},
        )


def test_reader_rejects_wrong_database_identity_and_modified_publication(
    tmp_path: Path,
) -> None:
    output, data, database, descriptor = _publish_fixture(tmp_path)
    other_database = data / "other.sqlite"
    other_database.write_bytes(b"other-db")
    assert load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=other_database,
        descriptor=descriptor,
    )["status"] == "unknown"
    bundle_path = output / Path(*descriptor["reference"]["relative_path"].split("/"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    publication = bundle["publications"][0]
    publication_path = output / Path(*publication["relative_path"].split("/"))
    publication_path.write_bytes(publication_path.read_bytes() + b" ")
    rejected = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        descriptor=descriptor,
    )
    assert rejected["status"] == "unknown"
    assert rejected["source_use_accepted"] is False
    assert rejected["source_published_at"] is None
    assert rejected["available_at"] is None
    assert rejected["pit_eligible"] is False
    assert rejected["training_eligible"] is False


def test_reader_rejects_database_identity_change_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output, data, database, descriptor = _publish_fixture(tmp_path)
    original_identity = source_bundle_module._database_identity
    calls = 0

    def change_identity_on_final_check(
        data_root: Path, database_path: str | Path,
    ) -> tuple[str, dict[str, int]]:
        nonlocal calls
        calls += 1
        relative, identity = original_identity(data_root, database_path)
        if calls == 2:
            return relative, {**identity, "inode": identity["inode"] + 1}
        return relative, identity

    monkeypatch.setattr(
        source_bundle_module, "_database_identity", change_identity_on_final_check
    )
    rejected = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        descriptor=descriptor,
    )
    assert calls == 2
    assert rejected["status"] == "unknown"
    assert rejected["reason_code"] == "database_identity_changed_during_bundle_read"


def test_reader_rejects_duplicate_source_families_even_with_recomputed_bundle_pin(
    tmp_path: Path,
) -> None:
    output, data, database, descriptor = _publish_fixture(tmp_path)
    reference = descriptor["reference"]
    path = output / Path(*reference["relative_path"].split("/"))
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["publications"].append(bundle["publications"][0])
    raw = _canonical(bundle) + b"\n"
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    relative = (
        "scheduled/daily_price_source_bundles/runs/20261022-4400/"
        f"{digest[7:]}.json"
    )
    tampered_path = output / Path(*relative.split("/"))
    tampered_path.write_bytes(raw)
    forged_reference = {
        **descriptor,
        "reference": {"relative_path": relative, "sha256": digest},
    }
    loaded = load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
        descriptor=forged_reference,
    )
    assert loaded == {
        "status": "unknown",
        "reason_code": "bundle_source_family_duplicate",
        "source_use_accepted": False,
        "source_published_at": None,
        "available_at": None,
        "pit_eligible": False,
        "training_eligible": False,
    }


@pytest.mark.parametrize("run_id", ["..", "../escape", "run/name", "C:temp"])
def test_publisher_rejects_unsafe_quick_run_id(tmp_path: Path, run_id: str) -> None:
    output, data, database, descriptor = _publish_fixture(tmp_path)
    bundle = json.loads(
        (
            output
            / Path(*descriptor["reference"]["relative_path"].split("/"))
        ).read_text(encoding="utf-8")
    )
    publication_inputs = {
        item["source_id"]: {
            "status": "captured",
            "schema_version": item["schema_version"],
            "relative_path": item["relative_path"],
            "sha256": item["sha256"],
            "row_count": item["row_count"],
        }
        for item in bundle["publications"]
    }
    with pytest.raises(ValueError, match="quick_run_id_invalid"):
        publish_daily_price_source_bundle(
            output_root=output,
            data_root=data,
            database_path=database,
            quick_run_id=run_id,
            completed_at="2026-10-22T16:02:03+00:00",
            quick_status="passed",
            descriptors=publication_inputs,
        )


def test_latest_locator_cannot_select_a_traversal_or_unpinned_path(
    tmp_path: Path,
) -> None:
    output, data, database, _descriptor = _publish_fixture(tmp_path)
    locator_path = output / "scheduled" / "daily_price_source_bundles" / "latest.json"
    locator_body = {
        "schema_version": LOCATOR_SCHEMA,
        "quick_run_id": "20261022-4400",
        "relative_path": "scheduled/daily_price_source_bundles/runs/20261022-4400/../../foreign.json",
        "sha256": "sha256:" + "0" * 64,
    }
    forged = {
        **locator_body,
        "content_sha256": "sha256:" + hashlib.sha256(_canonical(locator_body)).hexdigest(),
    }
    locator_path.write_bytes(_canonical(forged) + b"\n")
    assert load_daily_price_source_bundle(
        output_root=output,
        data_root=data,
        database_path=database,
    )["status"] == "unknown"


def test_quick_helper_bundles_only_captured_sync_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_data_update_quick as quick

    captured = {
        "status": "captured",
        "schema_version": _FAMILIES["tpex.daily_close_quotes"][0],
        "relative_path": "scheduled/tpex_daily_price_sqlite_publication/aa/" + "a" * 64 + ".json",
        "sha256": "sha256:" + "a" * 64,
        "row_count": 1,
    }
    observed: dict[str, object] = {}

    def fake_publish(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"status": "captured", "schema_version": BUNDLE_SCHEMA}

    monkeypatch.setattr(
        "data_module.daily_price_source_bundle.publish_daily_price_source_bundle",
        fake_publish,
        raising=False,
    )
    result = quick._publish_quick_daily_price_source_bundle(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "db.sqlite",
        run_id="20261022-4400",
        completed_at=datetime.now(timezone.utc),
        quick_status="failed",
        steps=[
            {
                "name": "sync_daily_prices_to_sqlite",
                "result": {
                    "row_evidence": {"status": "unknown"},
                    "tpex_row_evidence": captured,
                },
            }
        ],
    )
    assert result["status"] == "captured"
    assert set(observed["descriptors"]) == {"tpex.daily_close_quotes"}
    assert observed["quick_status"] == "failed"


def test_quick_helper_rejects_duplicate_sync_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.run_daily_data_update_quick as quick

    def unexpected_publish(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("ambiguous sync steps must not publish a bundle")

    monkeypatch.setattr(
        "data_module.daily_price_source_bundle.publish_daily_price_source_bundle",
        unexpected_publish,
        raising=False,
    )
    step = {
        "name": "sync_daily_prices_to_sqlite",
        "result": {"row_evidence": {"status": "captured"}},
    }
    result = quick._publish_quick_daily_price_source_bundle(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "db.sqlite",
        run_id="20261022-4400",
        completed_at=datetime.now(timezone.utc),
        quick_status="passed",
        steps=[step, dict(step)],
    )
    assert result == {
        "status": "unknown",
        "reason_code": "quick_sync_result_ambiguous",
    }
