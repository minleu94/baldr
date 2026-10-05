from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
    DailyMarketFeatureSnapshotService,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_METHOD_VERSIONS,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_json_bytes,
    cohort_identity_sha256,
    snapshot_artifact_relpath,
    snapshot_manifest_identity_sha256,
    snapshot_manifest_relpath,
)
from app_module.stock_research_report_dtos import (
    StockMetricDTO,
    StockPricePointDTO,
    StockTechnicalSnapshotDTO,
)


DECISION_DATE = date(2026, 10, 5)
TAIPEI = timezone(timedelta(hours=8))
PUBLISHED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SCHEMA_SHA = "a" * 64
DATABASE = r"C:\research-data\current.sqlite"


def _price_points(stock_code: str, variant: str = "base") -> tuple[StockPricePointDTO, ...]:
    dates: list[date] = []
    cursor = DECISION_DATE
    while len(dates) < 60:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    rows = []
    for index, item_date in enumerate(dates):
        close = Decimal(100 + index)
        rows.append(
            StockPricePointDTO(
                data_date=item_date.isoformat(),
                open_price=close,
                high_price=close + Decimal("2"),
                low_price=close - Decimal("2"),
                close_price=close,
                volume=1000 + index,
                turnover=close * Decimal(1000 + index),
                change=Decimal("0"),
                source_id="sqlite.daily_prices",
                source_snapshot_hash=f"{stock_code}-{variant}-{index:03d}",
                quality="observed",
            )
        )
    return tuple(rows)


def _snapshot_payload(
    stock_code: str,
    *,
    variant: str = "base",
    technical: bool = True,
) -> dict[str, Any]:
    points = _price_points(stock_code, variant)
    technical_snapshot = None
    if technical:
        data_date = points[-1].data_date
        technical_snapshot = StockTechnicalSnapshotDTO(
            data_date=data_date,
            source_id="sqlite.technical_indicators",
            quality="observed",
            indicators=(
                StockMetricDTO(
                    key="MA20",
                    label="MA20",
                    value=Decimal("150"),
                    unit="TWD/share",
                    data_as_of=data_date,
                    source_id="sqlite.technical_indicators",
                    quality="observed",
                ),
                StockMetricDTO(
                    key="MA60",
                    label="MA60",
                    value=Decimal("170"),
                    unit="TWD/share",
                    data_as_of=data_date,
                    source_id="sqlite.technical_indicators",
                    quality="observed",
                ),
            ),
        )
    return DailyMarketFeatureSnapshotService().project(
        stock_code=stock_code,
        decision_date=DECISION_DATE,
        scope_identity=f"daily-market-source:{SCHEMA_SHA}:stock:{stock_code}",
        price_points=points,
        technical=technical_snapshot,
    ).to_dict()


def _source_refs() -> dict[str, str]:
    return {
        "database": DATABASE,
        "schema_identity_sha256": SCHEMA_SHA,
        "price": f"{DATABASE}#daily_prices",
        "technical": f"{DATABASE}#technical_indicators",
    }


def _publish(
    root: Path,
    payloads: Mapping[str, dict[str, Any]],
    declared_stock_codes: tuple[str, ...] | list[str],
    *,
    cohort_id: str = "ux19-test-cohort",
    manifest_updates: Mapping[str, Any] | None = None,
    artifact_updates: Mapping[str, Mapping[str, Any]] | None = None,
    record_updates: Mapping[str, Mapping[str, Any]] | None = None,
    write_pointer: bool = True,
) -> tuple[str, dict[str, dict[str, Any]]]:
    declared = sorted(set(declared_stock_codes))
    snapshots = {code: deepcopy(payload) for code, payload in payloads.items()}
    for code, updates in (artifact_updates or {}).items():
        snapshots[code].update(deepcopy(dict(updates)))

    records: list[dict[str, Any]] = []
    missing = []
    for code in declared:
        payload = snapshots.get(code)
        if payload is None:
            missing.append({"stock_code": code, "reason": "source_unavailable"})
            continue
        artifact_bytes = canonical_json_bytes(payload)
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_relpath = snapshot_artifact_relpath(artifact_sha)
        artifact_path = root / Path(artifact_relpath)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        record = {
                "stock_code": code,
                "source_identity": payload["scope_identity"],
                "input_fingerprint_sha256": payload["input_fingerprint_sha256"],
                "snapshot_identity_sha256": payload["snapshot_identity_sha256"],
                "artifact_sha256": artifact_sha,
                "artifact_relpath": artifact_relpath,
                "source_refs": _source_refs(),
            }
        record.update(deepcopy(dict((record_updates or {}).get(code, {}))))
        records.append(record)

    completeness = (
        "complete_declared_cohort" if len(records) == len(declared) else "partial_research"
    )
    manifest: dict[str, Any] = {
        "schema_version": DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
        "manifest_identity_sha256": "0" * 64,
        "cohort_id": cohort_id,
        "cohort_identity": cohort_identity_sha256(cohort_id, declared),
        "declared_stock_codes": declared,
        "decision_date": DECISION_DATE.isoformat(),
        "decision_cutoff": datetime(2026, 10, 5, 16, 0, tzinfo=TAIPEI).isoformat(),
        "decision_timezone": "Asia/Taipei",
        "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
        "method_versions": dict(DAILY_MARKET_SNAPSHOT_METHOD_VERSIONS),
        "stocks": records,
        "missing_stocks": missing,
        "counts": {
            "declared": len(declared),
            "published": len(records),
            "missing": len(missing),
        },
        "completeness": completeness,
        "published_at": PUBLISHED_AT.isoformat(),
        "policy": {"research_only": True, "historical_pit_eligible": False},
    }
    manifest.update(deepcopy(dict(manifest_updates or {})))
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = root / Path(snapshot_manifest_relpath(manifest_sha))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    if write_pointer:
        pointer = {
            "schema_version": DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
            "manifest_sha256": manifest_sha,
        }
        root.mkdir(parents=True, exist_ok=True)
        (root / "latest.json").write_bytes(canonical_json_bytes(pointer))
    return manifest_sha, snapshots


def _load(root: Path, **kwargs: Any):
    return DailyMarketSnapshotRepository(root).load_latest(
        "ux19-test-cohort", DECISION_DATE, **kwargs
    )


def test_reader_verifies_complete_cohort_hashes_and_existing_unknown_features(tmp_path: Path):
    payloads = {
        "2382": _snapshot_payload("2382"),
        "3034": _snapshot_payload("3034", technical=False),
    }
    _manifest_sha, _ = _publish(tmp_path, payloads, ("2382", "3034"))

    result = _load(
        tmp_path,
        expected_stock_codes=("2382", "3034"),
        expected_input_hashes={
            "2382": payloads["2382"]["input_fingerprint_sha256"]
        },
    )

    assert result.completeness == "complete_declared_cohort"
    assert set(result.stock_snapshots) == {"2382", "3034"}
    assert result.stock_snapshots["2382"] == payloads["2382"]
    assert result.stock_snapshots["3034"]["features"]["MA20"]["state"] == "unknown"
    assert result.stock_snapshots["3034"]["conditions"]["close_above_ma20"]["state"] == "unknown"
    assert result.manifest["counts"] == {"declared": 2, "published": 2, "missing": 0}


def test_partial_research_retains_declared_denominator_and_missing_diagnostic(tmp_path: Path):
    payload = _snapshot_payload("2382")
    _publish(tmp_path, {"2382": payload}, ("1477", "2382"))

    result = _load(tmp_path)

    assert result.completeness == "partial_research"
    assert set(result.stock_snapshots) == {"2382"}
    assert result.manifest["declared_stock_codes"] == ["1477", "2382"]
    assert result.manifest["missing_stocks"] == [
        {"stock_code": "1477", "reason": "source_unavailable"}
    ]
    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        _load(tmp_path, expected_stock_codes=("2382",))
    assert error.value.code == "snapshot_stock_scope_mismatch"


@pytest.mark.parametrize(
    ("cohort_id", "decision_date", "input_hash", "error_code"),
    [
        ("other-cohort", DECISION_DATE, None, "snapshot_cohort_mismatch"),
        ("ux19-test-cohort", date(2026, 10, 6), None, "snapshot_decision_date_mismatch"),
        ("ux19-test-cohort", DECISION_DATE, "b" * 64, "snapshot_input_hash_mismatch"),
    ],
)
def test_reader_fails_closed_on_cohort_date_or_input_revision(
    tmp_path: Path,
    cohort_id: str,
    decision_date: date,
    input_hash: str | None,
    error_code: str,
):
    payload = _snapshot_payload("2382")
    _publish(tmp_path, {"2382": payload}, ("2382",))
    expected_hashes = {"2382": input_hash} if input_hash is not None else None

    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        DailyMarketSnapshotRepository(tmp_path).load_latest(
            cohort_id,
            decision_date,
            expected_input_hashes=expected_hashes,
        )
    assert error.value.code == error_code


@pytest.mark.parametrize(
    ("artifact_updates", "manifest_updates", "record_updates", "error_code"),
    [
        (None, None, {"2382": {"source_identity": "wrong-scope"}}, "snapshot_scope_identity_mismatch"),
        ({"policy": {"usage": "formal", "historical_pit_eligible": True}}, None, None, "snapshot_policy_invalid"),
        ({"market_date": "2026-10-06"}, None, None, "snapshot_future_market_date"),
        ({"stock_code": "9999"}, None, None, "snapshot_stock_mismatch"),
        ({"snapshot_identity_sha256": "b" * 64}, None, None, "snapshot_identity_mismatch"),
        (None, {"feature_contract_version": "daily-market-feature-snapshot.v2"}, None, "snapshot_contract_version_mismatch"),
        (None, {"method_versions": {"close": "new-method"}}, None, "snapshot_method_version_mismatch"),
        (None, {"counts": {"declared": True, "published": 1, "missing": 0}}, None, "snapshot_counts_mismatch"),
        (None, {"missing_stocks": [{"stock_code": "9999", "reason": "bad"}]}, None, "snapshot_missing_diagnostics_invalid"),
    ],
)
def test_reader_rejects_semantic_tampering_even_when_bytes_are_repinned(
    tmp_path: Path,
    artifact_updates: Mapping[str, Any] | None,
    manifest_updates: Mapping[str, Any] | None,
    record_updates: Mapping[str, Mapping[str, Any]] | None,
    error_code: str,
):
    payload = _snapshot_payload("2382")
    _publish(
        tmp_path,
        {"2382": payload},
        ("2382",),
        artifact_updates={"2382": artifact_updates} if artifact_updates else None,
        record_updates=record_updates,
        manifest_updates=manifest_updates,
    )

    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        _load(tmp_path)
    assert error.value.code == error_code


def test_reader_checks_identity_cutoff_and_candidate_without_latest_pointer(tmp_path: Path):
    payload = _snapshot_payload("2382")
    manifest_sha, _ = _publish(tmp_path, {"2382": payload}, ("2382",), write_pointer=False)
    repository = DailyMarketSnapshotRepository(tmp_path)

    candidate = repository.load_manifest(manifest_sha, "ux19-test-cohort", DECISION_DATE)
    assert candidate.stock_snapshots["2382"] == payload
    with pytest.raises(DailyMarketSnapshotVerificationError) as missing_pointer:
        repository.load_latest("ux19-test-cohort", DECISION_DATE)
    assert missing_pointer.value.code == "snapshot_pointer_missing"

    _publish(
        tmp_path,
        {"2382": payload},
        ("2382",),
        manifest_updates={
            "decision_cutoff": datetime(2026, 10, 5, 21, 0, tzinfo=TAIPEI).isoformat()
        },
    )
    with pytest.raises(DailyMarketSnapshotVerificationError) as future_cutoff:
        repository.load_latest("ux19-test-cohort", DECISION_DATE)
    assert future_cutoff.value.code == "snapshot_cutoff_invalid"


def test_latest_pointer_is_read_again_and_repository_does_not_cache(tmp_path: Path):
    first_payload = _snapshot_payload("2382", variant="first")
    first_sha, _ = _publish(tmp_path, {"2382": first_payload}, ("2382",))
    repository = DailyMarketSnapshotRepository(tmp_path)
    first = repository.load_latest("ux19-test-cohort", DECISION_DATE)

    second_payload = _snapshot_payload("2382", variant="second")
    second_sha, _ = _publish(tmp_path, {"2382": second_payload}, ("2382",))
    second = repository.load_latest("ux19-test-cohort", DECISION_DATE)

    assert first.manifest_sha256 == first_sha
    assert second.manifest_sha256 == second_sha
    assert first.manifest_sha256 != second.manifest_sha256
    assert second.stock_snapshots["2382"]["input_fingerprint_sha256"] == second_payload[
        "input_fingerprint_sha256"
    ]


def test_reader_rejects_manifest_byte_changes_and_false_warmup_qualification(tmp_path: Path):
    payload = _snapshot_payload("2382")
    manifest_root = tmp_path / "manifest-integrity"
    manifest_sha, _ = _publish(manifest_root, {"2382": payload}, ("2382",))
    manifest_path = manifest_root / snapshot_manifest_relpath(manifest_sha)
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(DailyMarketSnapshotVerificationError) as manifest_error:
        DailyMarketSnapshotRepository(manifest_root).load_latest(
            "ux19-test-cohort", DECISION_DATE
        )
    assert manifest_error.value.code == "snapshot_manifest_hash_mismatch"

    invalid_warmup = deepcopy(payload)
    invalid_warmup["features"]["MA20"]["warmup_observed_count"] = 4
    warmup_root = tmp_path / "warmup-integrity"
    _publish(warmup_root, {"2382": invalid_warmup}, ("2382",))
    with pytest.raises(DailyMarketSnapshotVerificationError) as warmup_error:
        DailyMarketSnapshotRepository(warmup_root).load_latest(
            "ux19-test-cohort", DECISION_DATE
        )
    assert warmup_error.value.code == "snapshot_warmup_invalid"


def test_manifest_and_artifact_byte_hashes_are_required_and_cohort_is_bounded(tmp_path: Path):
    payload = _snapshot_payload("2382")
    _publish(tmp_path, {"2382": payload}, ("2382",))
    artifact_path = tmp_path / snapshot_artifact_relpath(
        next(iter(DailyMarketSnapshotRepository(tmp_path).load_latest("ux19-test-cohort", DECISION_DATE).manifest["stocks"]))["artifact_sha256"]
    )
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    with pytest.raises(DailyMarketSnapshotVerificationError) as artifact_error:
        _load(tmp_path)
    assert artifact_error.value.code == "snapshot_artifact_hash_mismatch"

    too_many_codes = tuple(f"{index:04d}" for index in range(17))
    _publish(tmp_path, {too_many_codes[0]: _snapshot_payload(too_many_codes[0])}, too_many_codes)
    with pytest.raises(DailyMarketSnapshotVerificationError) as count_error:
        _load(tmp_path)
    assert count_error.value.code == "snapshot_stock_scope_too_large"
