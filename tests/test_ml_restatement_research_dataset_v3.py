"""官方來源 v3 必須同時綁定價格、交易日、來源與真實取得時鐘。"""
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from data_module.ml_restatement_official_market import file_sha256
from data_module.ml_restatement_research_dataset import RestatedDatasetBuilder
from data_module.ml_restatement_research_dataset_v3 import (
    MARKET_SOURCE_CONTRACT, SOURCE_FILES, V3_IDENTITY_FIELDS, V3_SCHEMA_VERSION,
    compute_v3_identity_hash, expected_v3_source_pairs, validate_v3_manifest_sources,
)
from tests.test_ml_restatement_official_market import _capture


def _rehash(manifest):
    value = compute_v3_identity_hash(manifest)
    manifest.update({
        "manifest_hash": value, "dataset_identity_hash": value,
        "dataset_id": "ml-restated-research-v3-" + value[7:31],
    })
    return manifest


def _source_manifest(tmp_path):
    path, _raw = _capture(tmp_path)
    sha = "sha256:" + "1" * 64
    # 此 fixture 只驗來源子契約；62 欄與完整分片由 training loader 另驗。
    manifest = dict.fromkeys(V3_IDENTITY_FIELDS)
    manifest.update({
        "dataset_identity_fields": list(V3_IDENTITY_FIELDS), "schema_version": V3_SCHEMA_VERSION,
        "source_hashes": {
            "snapshot_db": {"sha256": sha}, "direct_manifest": {"file_sha256": sha},
            "discovery_cache": {"sha256": sha}, "transfer_receipt": {"sha256": sha},
            "corporate_action_manifest": {"sha256": sha},
            "official_market_capture": {"path": str(path), "file_sha256": file_sha256(path)},
        },
        "computation_source_hashes": {key: sha for key in SOURCE_FILES},
        "builder_code_sha256": sha, "kernel": {"sha256": sha}, "revision": sha,
        "status": "complete_research_build", "restated_research": True, "research_only": True,
        "formal_historical_PIT": False, "formal_oos": False, "promotion_eligible": False,
        "revision_observed_at": "2024-02-01T02:01:00+08:00", "training_as_of": "2024-02-01T02:01:00+08:00",
        "dataset_created_at": "2024-02-01T03:00:00+08:00", "observed_session_dates": ["2024-01-02"],
        "market_source": {
            "contract": MARKET_SOURCE_CONTRACT, "manifest_path": str(path),
            "manifest_file_sha256": file_sha256(path), "available_at": "2024-02-01T02:00:00+08:00",
            "cutoff_date": "2024-01-31",
            "calendar_policy": "official_report_dates; baseline rows preserved; non-session labels missing",
            "source_revision_id_semantics": "stock SQLite revision; official market is bound separately",
        },
    })
    manifest["source_manifest_hashes"] = expected_v3_source_pairs(manifest)
    return _rehash(manifest)


def test_valid_market_binding_uses_original_sources(tmp_path):
    manifest = _source_manifest(tmp_path)
    result = validate_v3_manifest_sources(manifest)
    assert result.rows[date(2024, 1, 2)]["成交量"] == Decimal("8299689369")


@pytest.mark.parametrize("field", ["calendar", "market_clock", "training_clock", "future_source", "alias", "source_contract", "code_missing", "builder", "stock_revision", "formal"])
def test_rehashed_manifest_still_enforces_source_contract(tmp_path, field):
    manifest = _source_manifest(tmp_path)
    if field == "calendar":
        manifest["observed_session_dates"] = ["2024-01-01"]
    elif field == "market_clock":
        manifest["market_source"]["available_at"] = "2024-01-01T00:00:00+08:00"
    elif field == "training_clock":
        manifest["training_as_of"] = "2024-01-31T00:00:00+08:00"
    elif field == "future_source":
        manifest["revision_observed_at"] = manifest["training_as_of"] = "2024-01-31T00:00:00+08:00"
    elif field == "alias":
        manifest["source_manifest_hashes"][-1][1] = "sha256:" + "2" * 64
    elif field == "source_contract":
        manifest["market_source"]["contract"] = "yahoo-volume-times-1000"
    elif field == "code_missing":
        del manifest["computation_source_hashes"]["official_market_reader"]
    elif field == "builder":
        manifest["builder_code_sha256"] = "sha256:" + "2" * 64
    elif field == "stock_revision":
        manifest["revision"] = "sha256:" + "2" * 64
    else:
        manifest["formal_historical_PIT"] = True
    _rehash(manifest)
    with pytest.raises(ValueError):
        validate_v3_manifest_sources(manifest)


def test_market_calendar_identity_fields_cannot_be_dropped(tmp_path):
    manifest = _source_manifest(tmp_path)
    manifest["dataset_identity_fields"].remove("observed_session_dates")
    with pytest.raises(ValueError, match="identity 欄位"):
        compute_v3_identity_hash(manifest)


def test_corrected_calendar_recomputes_horizon_and_downside():
    # 官方 Saturday session 必須算入 horizon；entry 用真正 open，不能用 close。
    days = [date(2014, 12, number) for number in (26, 27, 29, 30, 31)]
    context = SimpleNamespace(
        calendar=days, calendar_index={day: index for index, day in enumerate(days)},
        market_ohlc={day: {"open": Decimal("100"), "high": Decimal("112"), "low": Decimal("99"), "close": Decimal("110")} for day in days},
        corporate_actions={}, observed_clock=datetime.fromisoformat("2024-02-01T00:00:00+08:00"),
    )
    stock = {day: {"open": Decimal("100"), "high": Decimal("107"), "low": Decimal("99"), "close": Decimal("105")} for day in days}
    labels, masks, end, _maturity, _basis = RestatedDatasetBuilder._label_horizon(
        context, {"_decision": days[0], "symbol": "2330"}, days, stock, 5,
    )
    assert end == date(2014, 12, 31)
    assert labels[0] == -580  # 股票 500 bp，市場 1000 bp，原成本 80 bp。
    assert labels[2] == 1 and masks[2] == 0


def test_old_non_session_row_stays_missing():
    context = SimpleNamespace(calendar_index={})
    result = RestatedDatasetBuilder._label_horizon(
        context, {"_decision": date(2014, 7, 23), "symbol": "2330"}, [], {}, 5,
    )
    assert result[0] == {} and result[1] == {} and result[2] is None
    assert "decision_not_in_observed_TAIEX_calendar" in result[4]
