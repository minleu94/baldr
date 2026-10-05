from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_cohort_projection import DailyMarketCohortProjectionError
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_KEYS,
    DailyMarketFeatureSnapshotService,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_research_capabilities import (
    DAILY_MARKET_RESEARCH_CAPABILITIES_SCHEMA,
    project_daily_market_research_capabilities,
)
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DailyMarketSnapshotRepository,
    VerifiedDailyMarketSnapshot,
    canonical_snapshot_json_bytes,
    canonical_snapshot_sha256,
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


_DECISION_DATE = date(2026, 10, 5)
_TAIPEI = timezone(timedelta(hours=8))
_PUBLISHED_AT = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
_SCHEMA_SHA = "a" * 64
_COHORT_ID = "capability-test-cohort"
_DECLARED = ("1001", "1002", "1003")


def _price_points(stock_code: str) -> tuple[StockPricePointDTO, ...]:
    dates: list[date] = []
    cursor = _DECISION_DATE
    while len(dates) < 60:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    return tuple(
        StockPricePointDTO(
            data_date=item_date.isoformat(),
            open_price=Decimal(100 + index),
            high_price=Decimal(102 + index),
            low_price=Decimal(98 + index),
            close_price=Decimal(100 + index),
            volume=1000 + index,
            turnover=Decimal(100 + index) * Decimal(1000 + index),
            change=Decimal("0"),
            source_id="sqlite.daily_prices",
            source_snapshot_hash=f"{stock_code}-price-{index:03d}",
            quality="observed",
        )
        for index, item_date in enumerate(dates)
    )


def _snapshot_payload(stock_code: str, *, unknown_technical: bool) -> dict[str, object]:
    points = _price_points(stock_code)
    technical = None
    if not unknown_technical:
        technical = StockTechnicalSnapshotDTO(
            data_date=_DECISION_DATE.isoformat(),
            source_id="sqlite.technical_indicators",
            quality="observed",
            indicators=(
                StockMetricDTO(
                    key="MA20",
                    label="MA20",
                    value=Decimal("155"),
                    unit="TWD/share",
                    data_as_of=_DECISION_DATE.isoformat(),
                    source_id="sqlite.technical_indicators",
                    quality="observed",
                ),
                StockMetricDTO(
                    key="MA60",
                    label="MA60",
                    value=Decimal("145"),
                    unit="TWD/share",
                    data_as_of=_DECISION_DATE.isoformat(),
                    source_id="sqlite.technical_indicators",
                    quality="observed",
                ),
            ),
        )
    return DailyMarketFeatureSnapshotService().project(
        stock_code=stock_code,
        decision_date=_DECISION_DATE,
        scope_identity=f"daily-market-source:{_SCHEMA_SHA}:stock:{stock_code}",
        price_points=points,
        technical=technical,
    ).to_dict()


def _source_refs(root: Path) -> dict[str, str]:
    database = str((root / "not-opened.sqlite").resolve())
    return {
        "database": database,
        "schema_identity_sha256": _SCHEMA_SHA,
        "price": f"{database}#daily_prices",
        "technical": f"{database}#technical_indicators",
    }


def _fixture(
    tmp_path: Path,
    *,
    missing_stock: str | None = None,
    unknown_technical_stock: str | None = None,
) -> tuple[Path, VerifiedDailyMarketSnapshot, tuple]:
    root = tmp_path / "snapshots"
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        code: _snapshot_payload(
            code,
            unknown_technical=(code == unknown_technical_stock),
        )
        for code in _DECLARED
        if code != missing_stock
    }
    records = []
    for code, payload in sorted(payloads.items()):
        artifact_bytes = canonical_snapshot_json_bytes(payload)
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_relpath = snapshot_artifact_relpath(artifact_sha)
        artifact_path = root / artifact_relpath
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        records.append(
            {
                "stock_code": code,
                "source_identity": payload["scope_identity"],
                "input_fingerprint_sha256": payload["input_fingerprint_sha256"],
                "snapshot_identity_sha256": payload["snapshot_identity_sha256"],
                "artifact_sha256": artifact_sha,
                "artifact_relpath": artifact_relpath,
                "source_refs": _source_refs(root),
            }
        )
    missing_codes = [code for code in _DECLARED if code not in payloads]
    contracts = method_contracts_payload()
    manifest: dict[str, object] = {
        "schema_version": DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
        "manifest_identity_sha256": "0" * 64,
        "cohort_id": _COHORT_ID,
        "cohort_identity": cohort_identity_sha256(_COHORT_ID, _DECLARED),
        "declared_stock_codes": list(_DECLARED),
        "decision_date": _DECISION_DATE.isoformat(),
        "decision_cutoff": datetime(2026, 10, 5, 16, 0, tzinfo=_TAIPEI).isoformat(),
        "decision_timezone": "Asia/Taipei",
        "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
        "method_contracts": contracts,
        "method_contracts_sha256": method_contracts_sha256(contracts),
        "stocks": records,
        "missing_stocks": [
            {"stock_code": code, "reason": "source_unavailable"}
            for code in missing_codes
        ],
        "counts": {
            "declared": len(_DECLARED),
            "published": len(payloads),
            "missing": len(missing_codes),
        },
        "completeness": "partial_research" if missing_codes else "complete_declared_cohort",
        "published_at": _PUBLISHED_AT.isoformat(),
        "policy": {"research_only": True, "historical_pit_eligible": False},
    }
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    manifest_bytes = canonical_snapshot_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = root / snapshot_manifest_relpath(manifest_sha)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    pointer = {
        "schema_version": DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
        "manifest_sha256": manifest_sha,
    }
    (root / "latest.json").write_bytes(canonical_snapshot_json_bytes(pointer))

    snapshot = DailyMarketSnapshotRepository(root).load_latest(_COHORT_ID, _DECISION_DATE)
    screener = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=root / "not-opened.sqlite"),
        snapshot_root=root,
    )
    rows = screener.filter_rows(snapshot, DAILY_MARKET_CONDITION_KEYS, "AND")
    return root, snapshot, rows


def _rehash_manifest(snapshot: VerifiedDailyMarketSnapshot, manifest: dict) -> VerifiedDailyMarketSnapshot:
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    return replace(
        snapshot,
        manifest=manifest,
        manifest_sha256=canonical_snapshot_sha256(manifest),
        manifest_identity_sha256=manifest["manifest_identity_sha256"],
    )


def test_complete_snapshot_exposes_five_detached_versioned_capabilities(tmp_path):
    _root, snapshot, _rows = _fixture(tmp_path)

    report = project_daily_market_research_capabilities(snapshot)
    value = report.to_dict()

    assert report.schema_version == DAILY_MARKET_RESEARCH_CAPABILITIES_SCHEMA
    assert tuple(item["key"] for item in value["catalog"]["features"]) == DAILY_MARKET_FEATURE_KEYS
    assert tuple(item["key"] for item in value["catalog"]["methods"]) == DAILY_MARKET_CONDITION_KEYS
    required_metadata = {
        "field",
        "unit",
        "warmup",
        "missing",
        "availability",
        "version",
        "cost",
        "source",
    }
    for item in (*value["catalog"]["features"], *value["catalog"]["methods"]):
        assert required_metadata.issubset(item)
        assert item["availability"]["official_availability_state"] == "unknown"
        assert item["cost"]["measured_runtime_memory_or_bytes"] == "unknown"
    assert value["catalog"]["features"][1]["warmup"]["required_observation_count"] == 20
    assert value["catalog"]["features"][2]["warmup"]["required_observation_count"] == 60
    assert value["catalog"]["methods"][0]["version"] == "1.0.0"
    assert value["catalog"]["methods"][0]["method_contracts_sha256"] == snapshot.manifest["method_contracts_sha256"]
    assert value["snapshot"]["method_contracts_sha256"] == method_contracts_sha256()
    assert value["declared_cohort"]["completeness_basis"] == "declared_stock_codes"
    assert value["declared_cohort"]["complete_declared_cohort"] is True
    assert value["declared_cohort"]["full_market_coverage"] is False
    assert value["declared_cohort"]["historical_pit_eligible"] is False
    assert len(value["stocks"]) == len(_DECLARED)
    assert len(value["stocks"][0]["features"]) == 3
    assert len(value["stocks"][0]["methods"]) == 2
    assert value["stocks"][0]["features"][0]["source_ref"].endswith("#daily_prices")

    value["catalog"]["features"][0]["source"]["source_table"] = "mutated"
    value["stocks"][0]["features"][0]["value"] = "0"
    fresh = report.to_dict()
    assert fresh["catalog"]["features"][0]["source"]["source_table"] == "daily_prices"
    assert fresh["stocks"][0]["features"][0]["value"] != "0"


def test_partial_and_unknown_values_stay_unknown_with_declared_denominator(tmp_path):
    root, snapshot, rows = _fixture(
        tmp_path,
        missing_stock="1003",
        unknown_technical_stock="1002",
    )

    value = project_daily_market_research_capabilities(
        snapshot,
        rows,
        expected_snapshot_root=root,
    ).to_dict()

    cohort = value["declared_cohort"]
    assert cohort["declared_count"] == 3
    assert cohort["published_count"] == 2
    assert cohort["missing_stock_codes"] == ["1003"]
    assert cohort["complete_declared_cohort"] is False
    by_code = {item["stock_code"]: item for item in value["stocks"]}
    unknown_stock = by_code["1002"]
    assert unknown_stock["features"][1]["state"] == "unknown"
    assert unknown_stock["features"][1]["warmup_required_count"] == 20
    assert unknown_stock["methods"][0]["state"] == "unknown"
    assert unknown_stock["methods"][0]["unknown_reason"]
    missing_stock = by_code["1003"]
    assert missing_stock["snapshot_state"] == "missing"
    assert all(feature["state"] == "unknown" for feature in missing_stock["features"])
    assert all(method["state"] == "unknown" for method in missing_stock["methods"])
    assert all(method["unknown_reason"] == "snapshot_missing" for method in missing_stock["methods"])


def test_strict_projection_rejects_schema_identity_method_hash_and_source_changes(tmp_path):
    root, snapshot, rows = _fixture(tmp_path)

    wrong_schema = replace(
        snapshot,
        manifest={**snapshot.manifest, "schema_version": "daily-market-snapshot-manifest.v999"},
    )
    with pytest.raises(DailyMarketCohortProjectionError) as schema_error:
        project_daily_market_research_capabilities(wrong_schema, rows)
    assert schema_error.value.code == "cohort_manifest_schema_invalid"

    wrong_identity = replace(snapshot, manifest_identity_sha256="0" * 64)
    with pytest.raises(DailyMarketCohortProjectionError) as identity_error:
        project_daily_market_research_capabilities(wrong_identity, rows)
    assert identity_error.value.code == "cohort_manifest_identity_mismatch"

    bad_method_hash_manifest = deepcopy(dict(snapshot.manifest))
    bad_method_hash_manifest["method_contracts_sha256"] = "0" * 64
    bad_method_hash = _rehash_manifest(snapshot, bad_method_hash_manifest)
    with pytest.raises(DailyMarketCohortProjectionError) as method_hash_error:
        project_daily_market_research_capabilities(bad_method_hash, rows)
    assert method_hash_error.value.code == "cohort_method_contract_hash_mismatch"

    bad_feature_version_manifest = deepcopy(dict(snapshot.manifest))
    bad_feature_version_manifest["feature_contract_version"] = "daily-market-feature-snapshot.v999"
    bad_feature_version = _rehash_manifest(snapshot, bad_feature_version_manifest)
    with pytest.raises(DailyMarketCohortProjectionError) as version_error:
        project_daily_market_research_capabilities(bad_feature_version, rows)
    assert version_error.value.code == "snapshot_contract_version_mismatch"

    changed_row = replace(rows[0], source_snapshot_hash="f" * 64)
    with pytest.raises(DailyMarketCohortProjectionError) as source_error:
        project_daily_market_research_capabilities(
            snapshot,
            (changed_row, *rows[1:]),
            expected_snapshot_root=root,
        )
    assert source_error.value.code == "cohort_row_source_mismatch"
