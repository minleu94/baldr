from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortProjectionError,
    project_daily_market_cohort,
    sort_daily_market_cohort_members,
)
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
from app_module.daily_market_research_screener import DailyMarketResearchScreenerService
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    canonical_snapshot_json_bytes,
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
_COHORT_ID = "cohort-projection-test"
_SOURCE_DB = r"C:\research-data\daily-market.sqlite"
_CONDITION_KEYS = tuple(DAILY_MARKET_CONDITION_KEYS)


def _price_points(stock_code: str, close: Decimal) -> tuple[StockPricePointDTO, ...]:
    dates: list[date] = []
    cursor = _DECISION_DATE
    while len(dates) < 60:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    rows = []
    for index, data_date in enumerate(dates):
        value = close - Decimal(59 - index)
        rows.append(
            StockPricePointDTO(
                data_date=data_date.isoformat(),
                open_price=value,
                high_price=value + Decimal("2"),
                low_price=value - Decimal("2"),
                close_price=value,
                volume=1000 + index,
                turnover=value * Decimal(1000 + index),
                change=Decimal("0"),
                source_id="sqlite.daily_prices",
                source_snapshot_hash=f"{stock_code}-price-{index:03d}",
                quality="observed",
            )
        )
    return tuple(rows)


def _snapshot_payload(
    stock_code: str,
    close: Decimal,
    ma20: Decimal | None,
    ma60: Decimal | None,
) -> dict[str, object]:
    points = _price_points(stock_code, close)
    metrics = tuple(
        StockMetricDTO(
            key=key,
            label=key,
            value=value,
            unit="TWD/share",
            data_as_of=_DECISION_DATE.isoformat(),
            source_id="sqlite.technical_indicators",
            quality="observed",
        )
        for key, value in (("MA20", ma20), ("MA60", ma60))
        if value is not None
    )
    technical = (
        StockTechnicalSnapshotDTO(
            data_date=_DECISION_DATE.isoformat(),
            source_id="sqlite.technical_indicators",
            quality="observed",
            indicators=metrics,
        )
        if metrics
        else None
    )
    return DailyMarketFeatureSnapshotService().project(
        stock_code=stock_code,
        decision_date=_DECISION_DATE,
        scope_identity=f"daily-market-source:{_SCHEMA_SHA}:stock:{stock_code}",
        price_points=points,
        technical=technical,
    ).to_dict()


def _source_refs() -> dict[str, str]:
    return {
        "database": _SOURCE_DB,
        "schema_identity_sha256": _SCHEMA_SHA,
        "price": f"{_SOURCE_DB}#daily_prices",
        "technical": f"{_SOURCE_DB}#technical_indicators",
    }


def _write_v2_snapshot(
    root: Path,
    *,
    wrong_schema: bool = False,
) -> None:
    payloads = {
        "1001": _snapshot_payload("1001", Decimal("101"), Decimal("99"), Decimal("102")),
        "1002": _snapshot_payload("1002", Decimal("95"), Decimal("96"), Decimal("90")),
        "1003": _snapshot_payload("1003", Decimal("100"), None, None),
    }
    declared = ("1001", "1002", "1003", "1004")
    records = []
    for stock_code, payload in payloads.items():
        artifact_bytes = canonical_snapshot_json_bytes(payload)
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_path = root / snapshot_artifact_relpath(artifact_hash)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        records.append(
            {
                "stock_code": stock_code,
                "source_identity": payload["scope_identity"],
                "input_fingerprint_sha256": payload["input_fingerprint_sha256"],
                "snapshot_identity_sha256": payload["snapshot_identity_sha256"],
                "artifact_sha256": artifact_hash,
                "artifact_relpath": snapshot_artifact_relpath(artifact_hash),
                "source_refs": _source_refs(),
            }
        )
    records.sort(key=lambda item: item["stock_code"])
    contracts = method_contracts_payload()
    manifest: dict[str, object] = {
        "schema_version": DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
        "manifest_identity_sha256": "0" * 64,
        "cohort_id": _COHORT_ID,
        "cohort_identity": cohort_identity_sha256(_COHORT_ID, declared),
        "declared_stock_codes": list(declared),
        "decision_date": _DECISION_DATE.isoformat(),
        "decision_cutoff": datetime(2026, 10, 5, 16, 0, tzinfo=_TAIPEI).isoformat(),
        "decision_timezone": "Asia/Taipei",
        "feature_contract_version": DAILY_MARKET_FEATURE_CONTRACT_VERSION,
        "feature_keys": list(DAILY_MARKET_FEATURE_KEYS),
        "method_contracts": contracts,
        "method_contracts_sha256": method_contracts_sha256(contracts),
        "stocks": records,
        "missing_stocks": [{"stock_code": "1004", "reason": "source_unavailable"}],
        "counts": {"declared": 4, "published": 3, "missing": 1},
        "completeness": "partial_research",
        "published_at": _PUBLISHED_AT.isoformat(),
        "policy": {"research_only": True, "historical_pit_eligible": False},
    }
    if wrong_schema:
        manifest["schema_version"] = "daily-market-snapshot-manifest.v999"
    manifest["manifest_identity_sha256"] = snapshot_manifest_identity_sha256(manifest)
    manifest_bytes = canonical_snapshot_json_bytes(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = root / snapshot_manifest_relpath(manifest_hash)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_bytes)
    pointer = {
        "schema_version": DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
        "manifest_sha256": manifest_hash,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_bytes(canonical_snapshot_json_bytes(pointer))


def _fixture(tmp_path: Path):
    root = tmp_path / "snapshots"
    _write_v2_snapshot(root)
    snapshot = DailyMarketSnapshotRepository(root).load_latest(_COHORT_ID, _DECISION_DATE)
    screener = DailyMarketResearchScreenerService(
        SimpleNamespace(db_file=tmp_path / "unused.sqlite"),
        snapshot_root=root,
    )
    rows = screener.filter_rows(snapshot, _CONDITION_KEYS, "AND")
    return root, snapshot, rows, screener


def test_projection_preserves_verified_v2_scope_source_hash_date_and_method_counts(tmp_path):
    root, snapshot, rows, _screener = _fixture(tmp_path)

    projection = project_daily_market_cohort(
        snapshot,
        rows,
        expected_snapshot_root=root,
    )

    assert projection.cohort_id == _COHORT_ID
    assert projection.decision_date == _DECISION_DATE.isoformat()
    assert projection.manifest_schema_version == DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA
    assert projection.source_snapshot_id == snapshot.manifest_identity_sha256
    assert projection.source_snapshot_hash == snapshot.manifest_sha256
    assert projection.method_contracts_sha256 == snapshot.manifest["method_contracts_sha256"]
    assert projection.completeness == "partial_research"
    assert projection.declared_stock_codes == ("1001", "1002", "1003", "1004")
    assert projection.published_stock_codes == ("1001", "1002", "1003")
    assert projection.missing_stock_codes == ("1004",)
    assert projection.published_count == 3
    assert projection.original_rank_state == "unknown"

    ma20, ma60 = projection.method_counts
    assert ma20.key == "close_above_ma20"
    assert ma20.method_id == "daily_market.close_above_ma20"
    assert ma20.parameters == (("direction", "above"), ("window", 20))
    assert (ma20.match_count, ma20.no_match_count, ma20.unknown_count, ma20.denominator) == (
        1,
        1,
        2,
        4,
    )
    assert ma60.key == "close_above_ma60"
    assert ma60.method_id == "daily_market.close_above_ma60"
    assert (ma60.match_count, ma60.no_match_count, ma60.unknown_count, ma60.denominator) == (
        1,
        1,
        2,
        4,
    )

    first = projection.members[0]
    assert first.stock_code == "1001"
    assert first.data_date == _DECISION_DATE.isoformat()
    assert first.close == Decimal("101")
    assert first.ma20 == Decimal("99")
    assert first.ma60 == Decimal("102")
    assert first.snapshot_missing is False
    assert dict(first.source_refs)["price"] == f"{_SOURCE_DB}#daily_prices"
    assert first.condition("close_above_ma20").state == "match"
    assert first.condition("close_above_ma60").state == "no_match"

    missing = projection.members[-1]
    assert missing.stock_code == "1004"
    assert missing.data_date is None
    assert missing.close is None and missing.ma20 is None and missing.ma60 is None
    assert missing.snapshot_missing is True
    assert all(item.state == "unknown" for item in missing.conditions)
    assert all(item.reason == "snapshot_missing" for item in missing.conditions)


@pytest.mark.parametrize(
    ("key", "descending", "expected_codes"),
    [
        ("stock_code", False, ("1001", "1002", "1003", "1004")),
        ("stock_code", True, ("1004", "1003", "1002", "1001")),
        ("data_date", False, ("1001", "1002", "1003", "1004")),
        ("data_date", True, ("1001", "1002", "1003", "1004")),
        ("close", False, ("1002", "1003", "1001", "1004")),
        ("close", True, ("1001", "1003", "1002", "1004")),
        ("ma20", False, ("1002", "1001", "1003", "1004")),
        ("ma20", True, ("1001", "1002", "1003", "1004")),
        ("ma60", False, ("1002", "1001", "1003", "1004")),
        ("ma60", True, ("1001", "1002", "1003", "1004")),
    ],
)
def test_sort_helper_orders_all_supported_keys_without_mutating_snapshot(
    tmp_path,
    key,
    descending,
    expected_codes,
):
    _root, snapshot, rows, _screener = _fixture(tmp_path)
    original_payloads = deepcopy(snapshot.stock_snapshots)
    projection = project_daily_market_cohort(snapshot, rows)

    sorted_members = sort_daily_market_cohort_members(
        projection.members,
        key,
        descending=descending,
    )

    assert tuple(item.stock_code for item in sorted_members) == expected_codes
    assert snapshot.stock_snapshots == original_payloads
    assert tuple(item.stock_code for item in projection.members) == projection.declared_stock_codes


def test_projection_rejects_rows_from_wrong_root_subset_duplicates_and_filtered_methods(tmp_path):
    root, snapshot, rows, screener = _fixture(tmp_path)
    expected_root = tmp_path / "another-root"
    forged_condition = replace(rows[1].conditions[0], state="match", relation="above")
    forged_row = replace(
        rows[1],
        conditions=(forged_condition, *rows[1].conditions[1:]),
    )

    cases = [
        (rows[:-1], root, "cohort_rows_scope_mismatch"),
        (rows + rows[:1], root, "cohort_rows_duplicate"),
        (rows, expected_root, "cohort_row_root_mismatch"),
        (
            screener.filter_rows(snapshot, ("close_above_ma20",), "AND"),
            root,
            "cohort_row_conditions_incomplete",
        ),
        ((replace(rows[0], decision_date="2026-10-04"), *rows[1:]), root, "cohort_row_scope_mismatch"),
        ((replace(rows[0], source_snapshot_hash="0" * 64), *rows[1:]), root, "cohort_row_source_mismatch"),
        ((rows[0], forged_row, *rows[2:]), root, "cohort_row_evaluation_mismatch"),
    ]
    for candidate_rows, candidate_root, expected_code in cases:
        with pytest.raises(DailyMarketCohortProjectionError) as error:
            project_daily_market_cohort(
                snapshot,
                candidate_rows,
                expected_snapshot_root=candidate_root,
            )
        assert error.value.code == expected_code


def test_snapshot_reader_rejects_wrong_manifest_schema_before_projection(tmp_path):
    root = tmp_path / "wrong-schema"
    _write_v2_snapshot(root, wrong_schema=True)

    with pytest.raises(DailyMarketSnapshotVerificationError) as error:
        DailyMarketSnapshotRepository(root).load_latest(_COHORT_ID, _DECISION_DATE)

    assert error.value.code == "snapshot_manifest_schema_mismatch"
