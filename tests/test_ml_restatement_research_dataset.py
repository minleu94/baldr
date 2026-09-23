from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pyarrow as pa

from data_module.portfolio_ml_dataset_assembler import (
    _mae_loss_bp,
    _max_drawdown_bp,
    _mfe_gain_bp,
    _realized_volatility_bp,
    _tail_loss_bp,
)
from data_module.ml_restatement_research_dataset import (
    LABEL_FIELDS,
    SUPPORTED_HORIZONS,
    TARGET_FIELDS,
    arrow_schema,
    canonical_hash,
    expected_feature_contract,
    _feature_eligibility,
    _fixed_array,
    _series_metrics,
    RestatedDatasetBuilder,
    _decimal,
    _decimal_ohlc,
)


def test_interchange_schema_keeps_masks_and_each_horizon_dates_independent() -> None:
    schema = arrow_schema()
    assert schema.field("features_scaled_i64").type == pa.list_(pa.int64(), 62)
    assert schema.field("feature_missing_mask").type == pa.list_(pa.uint8(), 62)
    assert schema.field("target_values_i32").type == pa.list_(pa.int32(), 6)
    assert schema.field("target_missing_mask").type == pa.list_(pa.uint8(), 6)
    for horizon in SUPPORTED_HORIZONS:
        assert schema.field(f"labels_h{horizon}_i64").type == pa.list_(pa.int64(), 9)
        assert schema.field(f"labels_h{horizon}_missing_mask").type == pa.list_(pa.uint8(), 9)
        assert schema.field(f"label_end_date_h{horizon}").type == pa.date32()
        assert schema.field(f"maturity_at_h{horizon}").type == pa.string()
    assert LABEL_FIELDS == (
        "benchmark_excess_return_bp", "sector_excess_return_bp",
        "downside_observed", "mae_bp", "mfe_bp", "realized_volatility_bp",
        "max_drawdown_bp", "tail_loss_bp", "fill_feasible_observed",
    )
    assert len(TARGET_FIELDS) == 6


def test_canonical_identity_is_stable_and_sensitive_to_recipe() -> None:
    first = canonical_hash({"recipe": "v1", "rows": 10})
    assert first == canonical_hash({"rows": 10, "recipe": "v1"})
    assert first != canonical_hash({"recipe": "v2", "rows": 10})


def test_grouped_decimals_are_valid_observations_without_relaxing_bad_format_masks() -> None:
    assert _decimal("1,005.00") == Decimal("1005.00")
    assert _decimal("  -1,234.567890  ") == Decimal("-1234.567890")
    assert _decimal("1,00.00") is None
    assert _decimal("1,234e2") is None
    assert _decimal("--") is None and _decimal(None) is None
    _names, scales = expected_feature_contract()
    assert _feature_eligibility("1,005.00", 24, scales[24], 1) == (10_050_000, False, False)
    grouped_bar = {"開盤價": "1,000.00", "最高價": "1,010.00", "最低價": "1,000.00", "收盤價": "1,005.00"}
    parsed = _decimal_ohlc(grouped_bar)
    assert parsed is not None and parsed["close"] == Decimal("1005.00")


def test_wire_contract_and_feature_slot_eligibility_keep_macd_sign_and_zero() -> None:
    names, scales = expected_feature_contract()
    assert len(names) == len(scales) == 62
    assert names[42] == "technical_indicators.MACD"
    assert names[45] == "technical_indicators.RSI"
    # MACD may be negative and oscillators may legitimately be zero.
    assert _feature_eligibility("-1.25", 42, scales[42], 1) == (-12500, False, False)
    assert _feature_eligibility("0", 45, scales[45], 1) == (0, False, False)
    # A zero close remains blocked under the positive-price contract.
    assert _feature_eligibility("0", 47, scales[47], 1) == (None, False, True)


def test_fixed_width_codec_keeps_nulls_separate_from_zero_and_masks() -> None:
    values = np.array([[0, 123], [5, 0]], dtype=np.int64)
    masks = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    result = _fixed_array(values, masks, 2, pa.int64())
    assert result.to_pylist() == [[None, 123], [5, None]]


def test_decimal_label_path_metrics_match_existing_assembler_helpers() -> None:
    closes = (Decimal("100.00"), Decimal("101.25"), Decimal("99.50"), Decimal("102.00"))
    path = [
        {"open": close, "high": close + Decimal("1"), "low": close - Decimal("2"), "close": close}
        for close in closes
    ]

    def legacy_row(row: dict[str, Decimal]) -> dict[str, int]:
        return {
            f"{key}_int": int((value * Decimal(10_000)).quantize(Decimal("1")))
            for key, value in row.items()
        } | {f"{key}_scale": 10_000 for key in row}

    legacy_path = [legacy_row(row) for row in path]
    old = (
        _mae_loss_bp(legacy_path[0], legacy_path),
        _mfe_gain_bp(legacy_path[0], legacy_path),
        _realized_volatility_bp(legacy_path),
        _max_drawdown_bp(legacy_path),
        _tail_loss_bp(legacy_path),
    )
    assert _series_metrics(path[0]["open"], path) == old


def test_revision_split_role_is_not_overridden_by_legacy_fold_membership() -> None:
    builder = RestatedDatasetBuilder.__new__(RestatedDatasetBuilder)
    builder.contract = SimpleNamespace(folds=({
        "fold_id": "legacy-2026", "test_start": "2026-01-01", "test_end": "2026-04-30",
    },))
    assert builder._fold_metadata(date(2026, 2, 2), date(2026, 3, 1)) == (
        "walk_forward_fit_candidate", ["legacy-2026"]
    )
    assert builder._fold_metadata(date(2026, 4, 1), date(2026, 3, 1))[0] == "revision_purged"
    assert builder._fold_metadata(date(2026, 5, 20), date(2026, 3, 1))[0] == "revision_heldout"
