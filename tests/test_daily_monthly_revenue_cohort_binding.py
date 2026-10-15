from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
import runpy
from typing import Any

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
    build_daily_monthly_revenue_cohort_pin,
    write_daily_monthly_revenue_cohort_pin_create_only,
)
from data_module.daily_monthly_revenue_cohort_binding import (
    DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES,
    DailyMonthlyRevenueCohortBindingError,
    read_daily_monthly_revenue_cohort_binding,
    serialize_daily_monthly_revenue_cohort_binding,
)
from data_module.daily_source_snapshot import DailySourceSnapshotFileReader


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@pytest.fixture
def saved_binding_fixture(tmp_path: Path) -> dict[str, Any]:
    """沿用既有完整合成批次，建立獨立 pin 與 binding 檔案。"""

    fixture_module = runpy.run_path(
        str(Path(__file__).with_name("test_daily_monthly_revenue_cohort.py"))
    )
    market_readers, acceptances, batch_ids = fixture_module["_pair"](tmp_path)
    pin: DailyMonthlyRevenueCohortPin = fixture_module["_build_pair"](
        market_readers, batch_ids
    )
    pin_root = tmp_path / "cohort-pins"
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    binding_bytes = serialize_daily_monthly_revenue_cohort_binding(
        cohort_pin_root=pin_root,
        pin=pin,
        market_readers=market_readers,
    )
    binding_path = tmp_path / "accepted-cohort-binding.json"
    binding_path.write_bytes(binding_bytes)
    return {
        "acceptances": acceptances,
        "binding_bytes": binding_bytes,
        "binding_path": binding_path,
        "market_readers": market_readers,
        "pin": pin,
        "pin_root": pin_root,
        "tmp_path": tmp_path,
    }


def _read_fixture(fixture: dict[str, Any]) -> DailyMonthlyRevenueCohortReader:
    payload = fixture["binding_bytes"]
    return read_daily_monthly_revenue_cohort_binding(
        fixture["binding_path"],
        expected_binding_sha256=_sha256(payload),
    )


def _write_document(fixture: dict[str, Any], value: object) -> bytes:
    payload = _canonical_json(value)
    fixture["binding_path"].write_bytes(payload)
    return payload


def test_binding_reopens_exact_two_market_reader_and_verifies_all_batches(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    pin = fixture["pin"]
    reader = _read_fixture(fixture)

    assert reader.pin == pin
    assert reader.pin.cohort_sha256 == pin.cohort_sha256
    assert reader.available_hour == pin.available_hour
    snapshots = reader.verify_cohort()
    assert tuple(item.scope.market for item in snapshots) == ("twse", "tpex")
    assert tuple(item.batch_id for item in snapshots) == tuple(
        pin.for_market(market).batch_id for market in pin.required_markets
    )
    for market in pin.required_markets:
        snapshot = reader.read_snapshot(
            pin.for_market(market).batch_id,
            expected_scope=fixture["acceptances"][market].scope,
        )
        assert snapshot.scope.market == market
        assert snapshot.records and all(record.period == pin.period for record in snapshot.records)


def test_binding_requires_the_callers_external_hash(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_external_hash_mismatch",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256="0" * 64
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("remove_market", "binding_markets_incomplete_or_extra"),
        ("unknown_market", "binding_market_unsupported"),
        ("wrong_market", "binding_scope_not_current_monthly_revenue"),
        ("wrong_dataset", "binding_scope_not_current_monthly_revenue"),
        ("wrong_source", "binding_scope_not_current_monthly_revenue"),
        ("wrong_parser", "binding_scope_not_current_monthly_revenue"),
        ("wrong_schema", "binding_scope_not_current_monthly_revenue"),
        ("wrong_unit", "binding_scope_not_current_monthly_revenue"),
        ("wrong_purpose", "binding_scope_not_current_monthly_revenue"),
        ("unknown_pin", "binding_pin_rejected"),
        ("wrong_binding_schema", "binding_schema_unsupported"),
        ("extra_market_key", "binding_market_fields_invalid"),
    ),
)
def test_binding_rejects_missing_or_mismatched_exact_selections(
    saved_binding_fixture: dict[str, Any], mutation: str, reason: str
) -> None:
    fixture = saved_binding_fixture
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    first_market = document["markets"][0]
    if mutation == "remove_market":
        document["markets"].pop()
    elif mutation == "unknown_market":
        first_market["market"] = "otc"
    elif mutation == "wrong_market":
        first_market["market"] = "tpex"
    elif mutation == "wrong_dataset":
        first_market["trusted_acceptance"]["scope"]["dataset_id"] = "other.dataset"
    elif mutation == "wrong_source":
        first_market["trusted_acceptance"]["scope"]["source_id"] = "other.source"
    elif mutation == "wrong_parser":
        first_market["trusted_acceptance"]["scope"]["parser_version"] = "parser.v1"
    elif mutation == "wrong_schema":
        first_market["trusted_acceptance"]["scope"][
            "source_schema_version"
        ] = "schema.v1"
    elif mutation == "wrong_unit":
        first_market["trusted_acceptance"]["scope"]["unit"] = "shares"
    elif mutation == "wrong_purpose":
        first_market["trusted_acceptance"]["scope"]["intended_use"] = "research_only"
    elif mutation == "unknown_pin":
        document["cohort_sha256"] = "0" * 64
    elif mutation == "wrong_binding_schema":
        document["schema_version"] = "daily-monthly-revenue-cohort-binding.v0"
    elif mutation == "extra_market_key":
        first_market["unexpected"] = "not-allowed"
    payload = _write_document(fixture, document)

    with pytest.raises(DailyMonthlyRevenueCohortBindingError, match=reason):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


def test_binding_reader_rejects_a_pin_whose_period_disagrees_with_saved_batches(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    pin = fixture["pin"]
    changed_market_pins = tuple(
        replace(market_pin, period="2026-05") for market_pin in pin.market_pins
    )
    wrong_period_pin = DailyMonthlyRevenueCohortPin(
        period="2026-05",
        required_markets=pin.required_markets,
        market_pins=changed_market_pins,
        available_hour=pin.available_hour,
    )
    write_daily_monthly_revenue_cohort_pin_create_only(
        fixture["pin_root"], wrong_period_pin
    )
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["cohort_sha256"] = wrong_period_pin.cohort_sha256
    payload = _write_document(fixture, document)

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_cohort_verification_failed:.*record_identity_mismatch",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


def test_binding_rejects_changed_acceptance_even_with_recomputed_artifact_hash(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["markets"][0]["trusted_acceptance"][
        "acceptance_evidence_ref"
    ] = "different-evidence-reference"
    payload = _write_document(fixture, document)

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_cohort_verification_failed:cohort_trusted_acceptance_hash_mismatch:twse",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


def test_binding_reader_rejects_a_missing_required_market_batch(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["markets"][1]["snapshot_root"] = str(
        fixture["tmp_path"] / "missing-tpex-snapshot-root"
    )
    payload = _write_document(fixture, document)

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_cohort_verification_failed:每日快照 manifest 或成功收據不存在",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


def test_binding_rejects_duplicate_and_extra_top_level_json_keys(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    duplicate = (
        b'{"schema_version":"daily-monthly-revenue-cohort-binding.v1",'
        b'"schema_version":"daily-monthly-revenue-cohort-binding.v1"}'
    )
    fixture["binding_path"].write_bytes(duplicate)
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_duplicate_json_key:schema_version",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(duplicate)
        )

    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["extra"] = "not-allowed"
    payload = _write_document(fixture, document)
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError, match="binding_fields_invalid"
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


@pytest.mark.parametrize("payload", (b"\xef\xbb\xbf{}", b"\xff{}"))
def test_binding_rejects_non_plain_utf8_json(
    saved_binding_fixture: dict[str, Any], payload: bytes
) -> None:
    fixture = saved_binding_fixture
    fixture["binding_path"].write_bytes(payload)

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError, match="binding_json_invalid"
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


def test_binding_rejects_json_nesting_past_parser_limit(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    payload = (b"[" * 20_000) + (b"]" * 20_000)
    fixture["binding_path"].write_bytes(payload)

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_json_nesting_exceeds_parser_limit",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )


@pytest.mark.parametrize("target", ("binding", "pin", "snapshot"))
def test_binding_loader_rejects_paths_inside_forbidden_bundle_roots(
    saved_binding_fixture: dict[str, Any], target: str
) -> None:
    fixture = saved_binding_fixture
    if target == "binding":
        forbidden_root = fixture["binding_path"].parent
        reason = "binding_binding_path_inside_forbidden_root"
    elif target == "pin":
        forbidden_root = fixture["pin_root"]
        reason = "binding_cohort_pin_root_inside_forbidden_root"
    else:
        forbidden_root = fixture["market_readers"]["twse"].root
        reason = "binding_snapshot_root:twse_inside_forbidden_root"

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match=reason,
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"],
            expected_binding_sha256=_sha256(fixture["binding_bytes"]),
            forbidden_roots=(forbidden_root,),
        )


def test_binding_rejects_relative_roots_and_oversized_files(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["markets"][0]["snapshot_root"] = "relative/snapshot-root"
    payload = _write_document(fixture, document)
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_snapshot_root:twse_must_be_absolute",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(payload)
        )

    oversized = b" " * (DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES + 1)
    fixture["binding_path"].write_bytes(oversized)
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_exceeds_size_limit",
    ):
        read_daily_monthly_revenue_cohort_binding(
            fixture["binding_path"], expected_binding_sha256=_sha256(oversized)
        )


def test_binding_reader_rejects_a_symlinked_artifact_path(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    link_path = fixture["tmp_path"] / "binding-link.json"
    try:
        link_path.symlink_to(fixture["binding_path"])
    except OSError as exc:
        pytest.skip(f"此環境不允許建立測試符號連結：{exc}")

    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_binding_path_is_symlink",
    ):
        read_daily_monthly_revenue_cohort_binding(
            link_path,
            expected_binding_sha256=_sha256(fixture["binding_bytes"]),
        )


def test_binding_growth_after_stat_is_bounded_and_rejected(saved_binding_fixture, monkeypatch):
    fixture = saved_binding_fixture
    original_open = Path.open
    requested_sizes = []

    class GrowingSource(io.BytesIO):
        def read(self, size=-1):
            requested_sizes.append(size)
            assert 0 < size <= DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES + 1
            return super().read(size)

    def open_path(path, *args, **kwargs):
        if path == fixture['binding_path']:
            return GrowingSource(b'x' * (DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES + 2))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_path)
    with pytest.raises(DailyMonthlyRevenueCohortBindingError, match='binding_exceeds_size_limit'):
        _read_fixture(fixture)
    assert requested_sizes == [DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES + 1]


def test_binding_serialization_requires_all_typed_market_readers(
    saved_binding_fixture: dict[str, Any],
) -> None:
    fixture = saved_binding_fixture
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_market_readers_incomplete_or_extra",
    ):
        serialize_daily_monthly_revenue_cohort_binding(
            cohort_pin_root=fixture["pin_root"],
            pin=fixture["pin"],
            market_readers={"twse": fixture["market_readers"]["twse"]},
        )

    invalid_reader = DailySourceSnapshotFileReader(
        fixture["market_readers"]["twse"].root
    )
    readers = {
        "twse": invalid_reader,
        "tpex": fixture["market_readers"]["tpex"],
    }
    with pytest.raises(
        DailyMonthlyRevenueCohortBindingError,
        match="binding_trusted_acceptance_missing:twse",
    ):
        serialize_daily_monthly_revenue_cohort_binding(
            cohort_pin_root=fixture["pin_root"],
            pin=fixture["pin"],
            market_readers=readers,
        )


def test_binding_allows_only_the_explicit_single_required_market(
    tmp_path: Path,
) -> None:
    fixture_module = runpy.run_path(
        str(Path(__file__).with_name("test_daily_monthly_revenue_cohort.py"))
    )
    reader, acceptance = fixture_module["_write_market_batch"](
        tmp_path / "twse-only-snapshot",
        "twse",
        batch_id="binding-twse-only",
    )
    pin = build_daily_monthly_revenue_cohort_pin(
        period="2026-04",
        required_markets=("twse",),
        batch_ids={"twse": "binding-twse-only"},
        readers={"twse": reader},
    )
    pin_root = tmp_path / "twse-only-pin"
    write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    payload = serialize_daily_monthly_revenue_cohort_binding(
        cohort_pin_root=pin_root,
        pin=pin,
        market_readers={"twse": reader},
    )
    binding_path = tmp_path / "twse-only-binding.json"
    binding_path.write_bytes(payload)

    reopened = read_daily_monthly_revenue_cohort_binding(
        binding_path, expected_binding_sha256=_sha256(payload)
    )
    assert reopened.pin.required_markets == ("twse",)
    assert reopened.verify_cohort()[0].scope.market == "twse"
    assert reopened.read_snapshot(
        pin.for_market("twse").batch_id,
        expected_scope=acceptance.scope,
    ).batch_id == "binding-twse-only"
