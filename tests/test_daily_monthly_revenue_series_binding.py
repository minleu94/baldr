from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from data_module.daily_monthly_revenue_series_binding import (
    DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1,
    DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1,
    DailyMonthlyRevenueSeriesBindingError,
    read_daily_monthly_revenue_series_binding_v1,
    serialize_daily_monthly_revenue_series_binding_v1,
    serialize_daily_monthly_revenue_series_catalog_pointer_v1,
    write_daily_monthly_revenue_series_catalog_create_only,
    write_daily_monthly_revenue_series_pointer_create_only,
)
from tests.test_daily_monthly_revenue_series import (
    REPORT_PERIOD,
    _trust,
    _write_cohort,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture(tmp_path: Path, *, second_pin: bool = False) -> dict[str, Any]:
    first = _write_cohort(tmp_path, version="series-binding-first")
    pins = [first]
    if second_pin:
        pins.append(
            _write_cohort(
                tmp_path,
                version="series-binding-second",
                twse_hour=12,
                tpex_hour=13,
            )
        )
    trust = _trust(tmp_path)
    catalog_root = tmp_path / "series-catalog"
    catalog_root.mkdir()
    catalog_path, catalog_sha = write_daily_monthly_revenue_series_catalog_create_only(
        catalog_root,
        report_period=REPORT_PERIOD,
        cohort_sha256s=tuple(pin.cohort_sha256 for pin in pins),
    )
    pointer_path = write_daily_monthly_revenue_series_pointer_create_only(
        catalog_root / "current.json", catalog_sha256=catalog_sha
    )
    binding_bytes = serialize_daily_monthly_revenue_series_binding_v1(
        trust=trust,
        catalog_root=catalog_root,
        pointer_path=pointer_path,
    )
    binding_path = tmp_path / "series-binding.json"
    binding_path.write_bytes(binding_bytes)
    return {
        "tmp_path": tmp_path,
        "pins": tuple(pins),
        "trust": trust,
        "catalog_root": catalog_root,
        "catalog_path": catalog_path,
        "catalog_sha": catalog_sha,
        "pointer_path": pointer_path,
        "binding_path": binding_path,
        "binding_bytes": binding_bytes,
        "binding_sha": _sha256(binding_bytes),
    }


def _read(
    fixture: dict[str, Any],
    cutoff_at: datetime,
    *,
    report_period: str | None = None,
    forbidden_roots: tuple[Path, ...] = (),
):
    return read_daily_monthly_revenue_series_binding_v1(
        fixture["binding_path"],
        expected_binding_sha256=fixture["binding_sha"],
        cutoff_at=cutoff_at,
        report_period=report_period,
        forbidden_roots=forbidden_roots,
    )


def _replace_pointer(fixture: dict[str, object], catalog_sha: str) -> None:
    pointer_path = fixture["pointer_path"]
    assert isinstance(pointer_path, Path)
    pointer_path.write_bytes(
        serialize_daily_monthly_revenue_series_catalog_pointer_v1(
            catalog_sha256=catalog_sha
        )
    )


def test_binding_reopens_exact_catalog_and_returns_fixed_reader(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]

    selected = _read(fixture, pin.available_hour)

    assert selected.pin == pin
    assert selected.reader.pin is selected.pin
    assert selected.report_period == REPORT_PERIOD
    assert selected.source_qualification == "not_granted"
    assert selected.historical_pit_eligible is False
    assert selected.formal_pit_eligible is False
    assert selected.verify_integrity() is selected.pin
    with pytest.raises((TypeError, ValueError)):
        replace(selected, cutoff_at=pin.available_hour + timedelta(days=1))


def test_new_invocation_reads_pointer_update_without_refreshing_old_selection(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, second_pin=True)
    first, second = fixture["pins"]
    old = _read(fixture, first.available_hour)
    _, second_catalog_sha = write_daily_monthly_revenue_series_catalog_create_only(
        fixture["catalog_root"],
        report_period=REPORT_PERIOD,
        cohort_sha256s=(second.cohort_sha256,),
    )

    _replace_pointer(fixture, second_catalog_sha)
    new = _read(fixture, second.available_hour)

    assert old.pin == first
    assert old.verify_integrity() is old.pin
    assert new.pin == second
    assert new.catalog_sha256 == second_catalog_sha


def test_cutoff_is_not_ceiled_and_future_catalog_candidate_is_diagnostic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, second_pin=True)
    first, second = fixture["pins"]
    cutoff = first.available_hour + timedelta(minutes=37)

    selected = _read(fixture, cutoff)

    assert selected.pin == first
    assert selected.cutoff_at == cutoff
    assert any(
        second.cohort_sha256 in item and "candidate_after_invocation_cutoff" in item
        for item in selected.candidate_diagnostics
    )
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="cutoff_at_must_be_aware"):
        _read(fixture, cutoff.replace(tzinfo=None))
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="report_period_mismatch"):
        _read(fixture, cutoff, report_period="2026-05")


def test_external_binding_digest_schema_and_exact_fields_are_required(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    path = fixture["binding_path"]

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="external_hash_mismatch"):
        read_daily_monthly_revenue_series_binding_v1(
            path,
            expected_binding_sha256="0" * 64,
            cutoff_at=pin.available_hour,
        )
    binding_path = fixture["binding_path"]
    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["unexpected"] = True
    payload = _canonical(document)
    binding_path.write_bytes(payload)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="fields_invalid"):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(payload),
            cutoff_at=pin.available_hour,
        )

    duplicate = (
        '{"schema_version":"'
        + DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1
        + '","schema_version":"x"}'
    ).encode("utf-8")
    binding_path.write_bytes(duplicate)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="duplicate_key"):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(duplicate),
            cutoff_at=pin.available_hour,
        )

    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    document["schema_version"] = "daily-monthly-revenue-series-binding.v9"
    payload = _canonical(document)
    binding_path.write_bytes(payload)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="schema_unsupported"):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(payload),
            cutoff_at=pin.available_hour,
        )

    document = json.loads(fixture["binding_bytes"].decode("utf-8"))
    trust = document["trust"]
    trust["market_sources"][0]["trusted_acceptance"]["scope"]["unit"] = "thousand_TWD"
    trust_core = {
        key: value for key, value in trust.items() if key != "configuration_sha256"
    }
    trust["configuration_sha256"] = _sha256(_canonical(trust_core))
    payload = _canonical(document)
    binding_path.write_bytes(payload)
    with pytest.raises(
        DailyMonthlyRevenueSeriesBindingError,
        match="not_current_monthly_revenue",
    ):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(payload),
            cutoff_at=pin.available_hour,
        )
    oversized_binding = b" " * (64 * 1024 + 1)
    binding_path.write_bytes(oversized_binding)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="exceeds_size_limit"):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(oversized_binding),
            cutoff_at=pin.available_hour,
        )


def test_pointer_digest_must_resolve_to_exact_immutable_catalog(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    pointer_path = fixture["pointer_path"]
    assert isinstance(pointer_path, Path)
    pointer_path.write_bytes(
        serialize_daily_monthly_revenue_series_catalog_pointer_v1(
            catalog_sha256="f" * 64
        )
    )

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="catalog_not_found"):
        _read(fixture, pin.available_hour)
    catalog = {
        "schema_version": DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1,
        "report_period": REPORT_PERIOD,
        "cohort_sha256s": [pin.cohort_sha256, pin.cohort_sha256],
    }
    raw = _canonical(catalog)
    digest = _sha256(raw)
    catalog_root = fixture["catalog_root"]
    assert isinstance(catalog_root, Path)
    (catalog_root / f"{digest}.json").write_bytes(raw)
    _replace_pointer(fixture, digest)

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="duplicate_hash"):
        _read(fixture, pin.available_hour)
    pointer_path.write_bytes(b" " * 4097)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="exceeds_size_limit"):
        _read(fixture, pin.available_hour)
    oversized_catalog = b" " * (64 * 1024 + 1)
    digest = _sha256(oversized_catalog)
    catalog_root = fixture["catalog_root"]
    (catalog_root / f"{digest}.json").write_bytes(oversized_catalog)
    _replace_pointer(fixture, digest)
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="exceeds_size_limit"):
        _read(fixture, pin.available_hour)


@pytest.mark.parametrize("bad_payload", (b"\xff", b'{"schema_version":"wrong"}'))
def test_bad_catalog_pin_is_named_and_excluded_while_valid_pin_remains_usable(
    tmp_path: Path, bad_payload: bytes
) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    bad_hash = "f" * 64
    pin_root = fixture["trust"].cohort_pin_root
    (pin_root / f"{bad_hash}.json").write_bytes(bad_payload)
    _, catalog_sha = write_daily_monthly_revenue_series_catalog_create_only(
        fixture["catalog_root"],
        report_period=REPORT_PERIOD,
        cohort_sha256s=tuple(sorted((pin.cohort_sha256, bad_hash))),
    )
    _replace_pointer(fixture, catalog_sha)

    selected = _read(fixture, pin.available_hour)

    assert selected.pin == pin
    assert any(bad_hash in item for item in selected.candidate_diagnostics)


def test_missing_all_candidate_pins_fails_without_directory_scan_or_fallback(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    missing_hash = "e" * 64
    _, catalog_sha = write_daily_monthly_revenue_series_catalog_create_only(
        fixture["catalog_root"],
        report_period=REPORT_PERIOD,
        cohort_sha256s=(missing_hash,),
    )
    _replace_pointer(fixture, catalog_sha)

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError) as error:
        _read(fixture, datetime(2026, 10, 15, 0, tzinfo=timezone.utc))

    assert error.value.code == "series_catalog_has_no_readable_exact_pin"
    assert any(missing_hash in item and "not_found" in item for item in error.value.diagnostics)


@pytest.mark.parametrize("root_name", ("catalog_root", "snapshot_root"))
def test_forbidden_roots_reject_configured_or_data_roots(
    tmp_path: Path, root_name: str
) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    if root_name == "catalog_root":
        forbidden = fixture["catalog_root"]
    else:
        forbidden = fixture["trust"].market_sources[0].snapshot_root

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="overlaps_forbidden_root"):
        _read(fixture, pin.available_hour, forbidden_roots=(forbidden,))


def test_catalog_root_may_not_overlap_a_market_snapshot_root(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="overlap")
    trust = _trust(tmp_path)
    catalog_root = trust.market_sources[0].snapshot_root / "catalog"
    pointer_path = catalog_root / "current.json"
    catalog_root.mkdir()

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="data_roots_overlap"):
        serialize_daily_monthly_revenue_series_binding_v1(
            trust=trust,
            catalog_root=catalog_root,
            pointer_path=pointer_path,
        )


def test_hardlinked_pointer_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    pointer_path = fixture["pointer_path"]
    binding_path = fixture["binding_path"]
    assert isinstance(pointer_path, Path) and isinstance(binding_path, Path)
    hardlink_path = pointer_path.with_name("hardlinked-current.json")
    try:
        os.link(pointer_path, hardlink_path)
    except OSError as exc:
        pytest.skip(f"此平台或測試環境不允許建立 hard link：{exc}")
    binding_bytes = serialize_daily_monthly_revenue_series_binding_v1(
        trust=fixture["trust"],
        catalog_root=fixture["catalog_root"],
        pointer_path=hardlink_path,
    )
    binding_path.write_bytes(binding_bytes)

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="has_hardlinks"):
        read_daily_monthly_revenue_series_binding_v1(
            binding_path,
            expected_binding_sha256=_sha256(binding_bytes),
            cutoff_at=pin.available_hour,
        )


def test_symlinked_binding_artifact_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    pin = fixture["pins"][0]
    binding_path = fixture["binding_path"]
    assert isinstance(binding_path, Path)
    link_path = tmp_path / "binding-link.json"
    try:
        link_path.symlink_to(binding_path)
    except OSError as exc:
        pytest.skip(f"此平台或測試環境不允許建立 symlink：{exc}")

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="symlink|reparse_point"):
        read_daily_monthly_revenue_series_binding_v1(
            link_path,
            expected_binding_sha256=fixture["binding_sha"],
            cutoff_at=pin.available_hour,
        )


def test_create_only_catalog_and_pointer_helpers_never_overwrite(tmp_path: Path) -> None:
    pin = _write_cohort(tmp_path, version="create-only")
    catalog_root = tmp_path / "series-catalog"
    catalog_root.mkdir()
    catalog_path, catalog_sha = write_daily_monthly_revenue_series_catalog_create_only(
        catalog_root,
        report_period=REPORT_PERIOD,
        cohort_sha256s=(pin.cohort_sha256,),
    )
    pointer_path = write_daily_monthly_revenue_series_pointer_create_only(
        catalog_root / "current.json", catalog_sha256=catalog_sha
    )

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="target_exists"):
        write_daily_monthly_revenue_series_catalog_create_only(
            catalog_root,
            report_period=REPORT_PERIOD,
            cohort_sha256s=(pin.cohort_sha256,),
        )
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="target_exists"):
        write_daily_monthly_revenue_series_pointer_create_only(
            pointer_path, catalog_sha256=catalog_sha
        )
    from data_module.daily_monthly_revenue_series_binding import (
        serialize_daily_monthly_revenue_series_catalog_v1,
    )

    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="duplicate_hash"):
        serialize_daily_monthly_revenue_series_catalog_v1(
            report_period=REPORT_PERIOD,
            cohort_sha256s=("1" * 64, "1" * 64),
        )
    with pytest.raises(DailyMonthlyRevenueSeriesBindingError, match="count_out_of_bounds"):
        serialize_daily_monthly_revenue_series_catalog_v1(
            report_period=REPORT_PERIOD,
            cohort_sha256s=tuple(f"{value:064x}" for value in range(65)),
        )
    assert catalog_path.read_bytes()

