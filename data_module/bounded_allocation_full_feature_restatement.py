"""以完整價格前綴產生 bounded allocation 研究重述特徵。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd
import talib

from analysis_module.technical_analysis.technical_indicators import (
    CAUSAL_INDICATOR_COLUMNS,
    calculate_causal_indicators,
)
from data_module.bounded_allocation_label_restatement import (
    BoundedRestatementError,
    JSONL_SCHEMA,
    OUTCOME_FIELDS,
    _canonical_json,
    _date_key,
    _file_sha256,
    _mapping,
    _normalize_symbol,
    _read_header,
    _read_json,
    _sha256_json,
    _source_shards,
    _timestamp,
    _verify_publication_manifest,
    _write_json,
)
from utils.numeric_text import normalize_grouped_numeric_text


FULL_RESTATEMENT_SCHEMA = "bounded-allocation-full-feature-restatement.v1"
RESEARCH_PUBLICATION_SCHEMA = "bounded-allocation-restated-research-publication.v1"
RESEARCH_JSONL_SCHEMA = "bounded-allocation-restated-research-jsonl.v1"
TECHNICAL_SOURCE_ID = "derived:causal_technical_indicators"
QUALITY_SOURCE_ID = "derived:restated_price_feature_quality"
PRICE_FAMILY = "price_liquidity_technical"
QUALITY_FEATURE_IDS = tuple(
    f"data_quality.{PRICE_FAMILY}.{name}"
    for name in (
        "coverage_bp",
        "missing_count",
        "stale_count",
        "quality_blocked_count",
        "max_available_lag_days",
    )
)
TECHNICAL_FEATURE_IDS = tuple(
    f"technical_indicators.{column}" for column in CAUSAL_INDICATOR_COLUMNS
)
RESTATED_FEATURE_IDS = frozenset(TECHNICAL_FEATURE_IDS + QUALITY_FEATURE_IDS)
_OHLC_FIELDS = ("開盤價", "最高價", "最低價", "收盤價")
_MISSING_TEXT = frozenset({"", "--", "nan", "none"})
_TARGET_OUTCOME_FIELDS = frozenset(OUTCOME_FIELDS)
_EXPECTED_SYMBOLS = frozenset(
    {"1101", "1216", "1301", "2002", "2303", "2317", "2330", "2412", "2454", "2881", "6505"}
)


class BoundedFeatureRestatementError(ValueError):
    """封存資料集、來源價格或特徵 lineage 不符合契約。"""


def restate_bounded_full_features(
    *,
    original_publication_dir: Path,
    label_restatement_dir: Path,
    source_snapshot_path: Path,
    output_directory: Path,
    expected_snapshot_sha256: str,
    revision_observed_at: str | None = None,
) -> dict[str, Any]:
    """只重算凍結 schema 中的 20 個技術欄與 5 個相依品質指標。

    計算使用 run02 snapshot 中每檔股票的完整 OHLC 前綴。輸出特徵的
    available_at 記錄本次研究重算的實際時間，event_at 保留歷史 T-1
    OHLC 觀測時間。
    """

    original_dir = Path(original_publication_dir).resolve()
    label_dir = Path(label_restatement_dir).resolve()
    snapshot_path = Path(source_snapshot_path).resolve()
    output_dir = Path(output_directory).resolve()
    if output_dir.exists():
        raise BoundedFeatureRestatementError(
            f"output directory already exists: {output_dir}"
        )
    if output_dir == original_dir or output_dir.is_relative_to(original_dir):
        raise BoundedFeatureRestatementError(
            "output must be outside the frozen publication"
        )
    if output_dir == label_dir or output_dir.is_relative_to(label_dir):
        raise BoundedFeatureRestatementError(
            "full-feature output must not replace or nest in label-only evidence"
        )

    observed_at = _timestamp(
        revision_observed_at or datetime.now(timezone.utc).isoformat()
    )
    expected_sha = _require_sha256(
        expected_snapshot_sha256, "expected_snapshot_sha256"
    )
    if _file_sha256(snapshot_path) != expected_sha:
        raise BoundedFeatureRestatementError("run02 snapshot hash mismatch")

    original_manifest = _read_json(original_dir / "manifest.json", "frozen manifest")
    _verify_publication_manifest(original_manifest)
    label_manifest = _read_json(label_dir / "manifest.json", "label restatement manifest")
    _verify_manifest_hash(label_manifest, "label restatement")
    _verify_parent_lineage(original_manifest, label_manifest)
    repair_record = _mapping(
        label_manifest.get("restatement"), "label restatement metadata"
    )
    if repair_record.get("historical_pit") is not False:
        raise BoundedFeatureRestatementError(
            "label-only parent must declare historical_pit=false"
        )
    if repair_record.get("source_snapshot_sha256") != expected_sha:
        raise BoundedFeatureRestatementError(
            "label-only parent used a different source snapshot"
        )
    receipt_path = Path(str(repair_record.get("source_repair_receipt_path", "")))
    receipt_hash = _require_sha256(
        str(repair_record.get("source_repair_receipt_sha256", "")),
        "repair receipt hash",
    )
    if not receipt_path.is_file() or _file_sha256(receipt_path) != repair_record.get(
        "source_repair_receipt_file_sha256"
    ):
        raise BoundedFeatureRestatementError(
            "label-only parent repair receipt file hash mismatch"
        )

    original_shards = _source_shards(original_dir, original_manifest)
    label_shards = _source_shards(label_dir, label_manifest)
    if len(original_shards) != len(label_shards):
        raise BoundedFeatureRestatementError("label-only shard count changed")
    original_headers = tuple(
        _read_header(path, entry, original_manifest)
        for path, entry in original_shards
    )
    label_headers = tuple(
        _read_header(path, entry, label_manifest)
        for path, entry in label_shards
    )
    if original_headers[0].get("horizons") != [5, 10, 20, 60]:
        raise BoundedFeatureRestatementError("bounded horizons changed")
    if any(
        _canonical_json(a.get("feature_packs"))
        != _canonical_json(b.get("feature_packs"))
        for a, b in zip(original_headers, label_headers, strict=True)
    ):
        raise BoundedFeatureRestatementError("label-only feature-pack ABI changed")

    source_registry = _mapping(
        label_manifest.get("feature_registry"), "feature registry"
    )
    price_definitions = _price_feature_definitions(source_registry)
    expected_raw_price_ids = tuple(sorted(price_definitions))
    if len(expected_raw_price_ids) != 41:
        raise BoundedFeatureRestatementError(
            f"expected 41 raw price-family slots; found {len(expected_raw_price_ids)}"
        )
    if not set(TECHNICAL_FEATURE_IDS).issubset(expected_raw_price_ids):
        raise BoundedFeatureRestatementError(
            "source feature registry does not contain all causal indicators"
        )
    feature_ids = _first_row_feature_ids(label_shards[0][0])
    pack_feature_ids = _validate_header_feature_abi(label_headers[0])
    if len(feature_ids) != 62 or len(set(feature_ids)) != 62:
        raise BoundedFeatureRestatementError("bounded feature ABI is not 62 unique slots")
    if set(pack_feature_ids) != set(feature_ids) or len(pack_feature_ids) != 62:
        raise BoundedFeatureRestatementError(
            "feature pack membership differs from the frozen row ABI"
        )
    if not set(QUALITY_FEATURE_IDS).issubset(feature_ids):
        raise BoundedFeatureRestatementError("price quality slots are incomplete")

    changed_labels = _changed_label_rows(
        original_shards=original_shards,
        label_shards=label_shards,
    )
    if len(changed_labels) != 210 or any(
        horizons != {60} for horizons in changed_labels.values()
    ):
        raise BoundedFeatureRestatementError(
            "expected 210 restated H60 labels from the label-only parent"
        )

    source_prices, input_stats = _load_ohlc_prefixes(snapshot_path)
    feature_by_symbol_date, indicator_stats = _calculate_full_prefix_features(
        source_prices
    )
    kernel_hashes = _kernel_source_hashes()
    helper_hash = _file_sha256(Path(__file__).resolve().parents[1] / "utils" / "numeric_text.py")
    producer_code_hash = _file_sha256(Path(__file__).resolve())
    serializer_path = Path(__file__).resolve().with_name(
        "bounded_allocation_label_restatement.py"
    )
    driver_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "restate_bounded_allocation_full_features.py"
    )
    producer_execution = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "working_directory": str(Path.cwd()),
        "actual_invocation": list(sys.argv),
        "sys_path": list(sys.path),
        "producer_module_path": str(Path(__file__).resolve()),
        "serializer_module_path": str(serializer_path),
        "driver_module_path": str(driver_path),
        "serializer_module_sha256": _file_sha256(serializer_path),
        "driver_module_sha256": _file_sha256(driver_path),
    }
    identity_payload = {
        "schema_version": FULL_RESTATEMENT_SCHEMA,
        "parent_label_publication_id": label_manifest["publication_id"],
        "parent_label_manifest_hash": label_manifest["manifest_hash"],
        "parent_dataset_identity_hash": label_manifest["dataset_identity_hash"],
        "source_snapshot_sha256": expected_sha,
        "source_repair_receipt_sha256": receipt_hash,
        "revision_observed_at": observed_at,
        "training_as_of": observed_at,
        "kernel_source_hashes": kernel_hashes,
        "grouped_numeric_helper_sha256": helper_hash,
        "producer_code_sha256": producer_code_hash,
        "producer_execution": producer_execution,
        "technical_recipe": "calculate_causal_indicators_full_prefix_gap_rewarm_v1",
        "quality_recipe": "price_liquidity_technical_event_clock_quality_v1",
        "scope": "bounded_full_feature_restated_research",
        "feature_restatement_reason_zh": (
            "無可核驗暖機／晚期有數值差異；120 尾窗並未重現本樣本差異"
        ),
    }
    identity_hash = _sha256_json(identity_payload)
    dataset_id = (
        f"{label_manifest['dataset_id']}-fullfeat-{identity_hash[7:19]}"
    )
    new_registry = _restated_feature_registry(
        source_registry,
        kernel_hash=identity_payload["kernel_source_hashes"],
    )
    feature_registry_hash = _sha256_json(new_registry)
    original_registry = _mapping(
        original_manifest.get("feature_registry"), "original feature registry"
    )
    original_registry_hash = _sha256_json(original_registry)
    declared_original_registry_hash = original_manifest.get("feature_registry_hash")
    if declared_original_registry_hash != original_registry_hash:
        raise BoundedFeatureRestatementError(
            "original feature registry hash does not match its manifest"
        )
    registry_transition = {
        "schema_version": "bounded-feature-registry-transition.v1",
        "original_registry": original_registry,
        "original_registry_hash": original_registry_hash,
        "restated_registry_hash": feature_registry_hash,
        "allowed_changed_feature_ids": sorted(TECHNICAL_FEATURE_IDS),
        "allowed_definition_fields": ["source_id", "table_name", "record_hash"],
    }
    source_hashes = _new_source_manifest_hashes(
        label_manifest.get("source_manifest_hashes"),
        expected_sha=expected_sha,
        receipt_hash=receipt_hash,
        kernel_hashes=kernel_hashes,
        helper_hash=helper_hash,
        identity_hash=identity_hash,
    )

    parent_by_year = {
        int(entry["year"]): (path, entry)
        for path, entry in label_shards
    }
    original_by_year = {
        int(entry["year"]): (path, entry)
        for path, entry in original_shards
    }
    staging_parent = output_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.staging-", dir=staging_parent
        )
    )
    stats = _RestatementStats(feature_ids)
    new_shards: list[dict[str, Any]] = []
    try:
        for year in sorted(parent_by_year):
            source_path, source_entry = parent_by_year[year]
            source_original_path, original_entry = original_by_year[year]
            if source_entry.get("sample_count") != original_entry.get("sample_count"):
                raise BoundedFeatureRestatementError(
                    f"original/label-only row count differs in {year}"
                )
            output_path = staging / str(source_entry["path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            header = _read_header(source_path, source_entry, label_manifest)
            header.update(
                {
                    "schema_version": RESEARCH_JSONL_SCHEMA,
                    "dataset_id": dataset_id,
                    "publication_id": _research_publication_id(identity_hash),
                    "dataset_identity_hash": identity_hash,
                    "feature_registry_hash": feature_registry_hash,
                    "feature_registry": new_registry,
                    "row_feature_ids": list(feature_ids),
                    "source_manifest_hashes": [list(pair) for pair in source_hashes],
                    "training_as_of": observed_at,
                    "revision_observed_at": observed_at,
                    "research_only": True,
                    "dataset_temporality": "restated_research",
                    "historical_pit": False,
                    "formal_consumer_compatible": False,
                    "direct_training_input": False,
                    "restated_research_training_input": True,
                    "formal_oos_allowed": False,
                    "production_action_allowed": False,
                    "promotion_eligible": False,
                    "release_eligible": False,
                }
            )
            shard_stats = _write_feature_shard(
                source_path=source_path,
                expected_parent_sha256=str(source_entry["compressed_sha256"]),
                original_path=source_original_path,
                expected_original_sha256=str(original_entry["compressed_sha256"]),
                output_path=output_path,
                header=header,
                feature_ids=feature_ids,
                price_definitions=price_definitions,
                calculated=feature_by_symbol_date,
                changed_labels=changed_labels,
                dataset_identity_hash=identity_hash,
                feature_registry_hash=feature_registry_hash,
                source_manifest_hashes=source_hashes,
                revision_observed_at=observed_at,
                stats=stats,
            )
            new_shards.append(
                {
                    "year": year,
                    "path": output_path.relative_to(staging).as_posix(),
                    "format": "gzip_jsonl",
                    "schema_version": RESEARCH_JSONL_SCHEMA,
                    "compressed_sha256": _file_sha256(output_path),
                    "content_sha256": shard_stats["content_sha256"],
                    "compressed_bytes": output_path.stat().st_size,
                    "sample_count": shard_stats["sample_count"],
                    "min_decision_date": source_entry["min_decision_date"],
                    "max_decision_date": source_entry["max_decision_date"],
                    "direct_training_input": False,
                    "restated_research_training_input": True,
                }
            )
        if stats.sample_count != int(label_manifest["sample_count"]):
            raise BoundedFeatureRestatementError("full-feature row count changed")
        if stats.replaced_technical_slots != stats.sample_count * 20:
            raise BoundedFeatureRestatementError(
                "not every sample received all 20 causal technical slots"
            )
        if stats.replaced_quality_slots != stats.sample_count * 5:
            raise BoundedFeatureRestatementError(
                "not every sample received all 5 price quality slots"
            )
        if stats.revised_labels != 210:
            raise BoundedFeatureRestatementError(
                "label revision-clock count differs from 210"
            )
        stats.assert_preserved()

        manifest = dict(label_manifest)
        manifest.pop("manifest_hash", None)
        manifest.update(
            {
                "schema_version": RESEARCH_PUBLICATION_SCHEMA,
                "publication_id": _research_publication_id(
                    identity_hash, new_shards
                ),
                "stage": "portfolio_ml_bounded_full_feature_restatement",
                "dataset_temporality": "restated_research",
                "dataset_id": dataset_id,
                "dataset_identity_hash": identity_hash,
                "feature_registry": new_registry,
                "feature_registry_hash": feature_registry_hash,
                "feature_registry_transition": registry_transition,
                "row_feature_ids": list(feature_ids),
                "source_manifest_hashes": [list(pair) for pair in source_hashes],
                "training_as_of": observed_at,
                "revision_observed_at": observed_at,
                "sample_count": stats.sample_count,
                "shards": new_shards,
                "research_only": True,
                "historical_pit": False,
                "direct_training_input": False,
                "restated_research_training_input": True,
                "formal_consumer_compatible": False,
                "formal_oos_allowed": False,
                "production_alpha_bp": 0,
                "production_action_allowed": False,
                "promotion_eligible": False,
                "release_eligible": False,
                "research_shadow_included": True,
                "formal_source_only": False,
                "safety": {
                    **dict(label_manifest.get("safety", {})),
                    "historical_pit": False,
                    "source_revision_observed_at": observed_at,
                    "source_revision_availability_backfilled": False,
                    "source_revision_event_dates_preserved": True,
                    "sqlite_source_write": False,
                    "formal_oos_allowed": False,
                    "production_action_allowed": False,
                    "promotion_eligible": False,
                },
                "restatement": {
                    "schema_version": FULL_RESTATEMENT_SCHEMA,
                    "status": "completed_research_only",
                    "dataset_temporality": "restated_research",
                    "historical_pit": False,
                    "formal_training_allowed": False,
                    "formal_oos_allowed": False,
                    "production_action_allowed": False,
                    "promotion_eligible": False,
                    "source_correction_recorded_at": repair_record.get(
                        "source_correction_recorded_at"
                    ),
                    "revision_observed_at": observed_at,
                    "training_as_of": observed_at,
                    "source_snapshot_path": str(snapshot_path),
                    "source_snapshot_sha256": expected_sha,
                    "source_repair_receipt_path": str(receipt_path),
                    "source_repair_receipt_sha256": receipt_hash,
                    "parent_label_publication_id": label_manifest["publication_id"],
                    "parent_label_manifest_hash": label_manifest["manifest_hash"],
                    "parent_dataset_identity_hash": label_manifest[
                        "dataset_identity_hash"
                    ],
                    "original_publication_id": original_manifest["publication_id"],
                    "original_publication_manifest_hash": original_manifest[
                        "manifest_hash"
                    ],
                    "identity_payload": identity_payload,
                    "producer_execution": producer_execution,
                    "feature_registry_hash": feature_registry_hash,
                    "kernel_source_hashes": kernel_hashes,
                    "grouped_numeric_helper_sha256": helper_hash,
                    "feature_restate_counts": stats.payload(),
                    "source_ohlc_audit": input_stats,
                    "full_prefix_kernel_audit": indicator_stats,
                    "label_revision_clock_policy": (
                        "unchanged labels retain original maturity as revision availability; "
                        "210 corrected H60 outcomes carry this rebuild's actual revision time"
                    ),
                    "quality_metric_clock_policy": (
                        "新鮮度與延遲值使用歷史來源／事件時鐘；五個重算品質欄位記錄本次重建的實際可用時間"
                    ),
                    "feature_restatement_reason_zh": identity_payload[
                        "feature_restatement_reason_zh"
                    ],
                    "preservation": stats.preservation_payload(),
                },
            }
        )
        manifest["manifest_hash"] = _sha256_json(manifest)
        _write_json(staging / "manifest.json", manifest)
        os.replace(staging, output_dir)
    except Exception as exc:
        raise BoundedFeatureRestatementError(
            f"full-feature restatement failed; staging retained at {staging}: {exc}"
        ) from exc

    return {
        "status": "completed_research_only",
        "output_directory": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "manifest_hash": manifest["manifest_hash"],
        "publication_id": manifest["publication_id"],
        "dataset_id": dataset_id,
        "dataset_identity_hash": identity_hash,
        "sample_count": stats.sample_count,
        "technical_slots_recomputed": stats.replaced_technical_slots,
        "quality_slots_recomputed": stats.replaced_quality_slots,
        "changed_label_revision_rows": stats.revised_labels,
        "revision_observed_at": observed_at,
        "historical_pit": False,
        "formal_oos_allowed": False,
        "production_action_allowed": False,
    }


def _load_ohlc_prefixes(
    snapshot_path: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    connection = sqlite3.connect(
        snapshot_path.resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        symbols = tuple(sorted(_EXPECTED_SYMBOLS))
        result: dict[str, pd.DataFrame] = {}
        total_rows = 0
        missing_cells: Counter[str] = Counter()
        grouped_cells: Counter[str] = Counter()
        symbol_rows: dict[str, int] = {}
        for symbol in symbols:
            rows = connection.execute(
                "SELECT 日期, 開盤價, 最高價, 最低價, 收盤價 "
                "FROM daily_prices WHERE 證券代號=? ORDER BY 日期",
                (symbol,),
            ).fetchall()
            if not rows:
                raise BoundedFeatureRestatementError(
                    f"run02 has no OHLC history for bounded symbol {symbol}"
                )
            parsed_rows: list[dict[str, Any]] = []
            previous_date = ""
            for row in rows:
                date_key = _date_key(str(row["日期"]))
                if date_key <= previous_date:
                    raise BoundedFeatureRestatementError(
                        f"run02 OHLC history is not unique/ordered for {symbol}"
                    )
                previous_date = date_key
                parsed: dict[str, Any] = {
                    "日期": f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                }
                for field in _OHLC_FIELDS:
                    decimal_value, grouped = _source_decimal(
                        row[field], symbol=symbol, date=date_key, field=field
                    )
                    if decimal_value is None:
                        parsed[field] = np.nan
                        missing_cells[field] += 1
                    else:
                        parsed[field] = float(decimal_value)
                    grouped_cells[field] += int(grouped)
                parsed_rows.append(parsed)
            frame = pd.DataFrame.from_records(parsed_rows)
            result[symbol] = frame
            total_rows += len(frame)
            symbol_rows[symbol] = len(frame)
        stats = {
            "snapshot_sha256": _file_sha256(snapshot_path),
            "symbols": list(symbols),
            "rows_by_symbol": dict(sorted(symbol_rows.items())),
            "ohlc_rows": total_rows,
            "missing_cells_by_field": dict(sorted(missing_cells.items())),
            "valid_grouped_decimal_cells_by_field": dict(
                sorted(grouped_cells.items())
            ),
            "sqlite_mode": "mode=ro",
            "sqlite_query_only": True,
            "runtime_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "talib": talib.__version__,
            },
        }
        return result, stats
    finally:
        connection.close()


def _source_decimal(
    value: Any, *, symbol: str, date: str, field: str
) -> tuple[Decimal | None, bool]:
    if value is None:
        return None, False
    raw = str(value).strip()
    if raw.casefold() in _MISSING_TEXT:
        return None, False
    normalized = normalize_grouped_numeric_text(raw)
    grouped = "," in raw and normalized != raw
    try:
        number = Decimal(str(normalized).strip())
    except (InvalidOperation, ValueError) as exc:
        raise BoundedFeatureRestatementError(
            f"invalid OHLC source text {symbol}/{date}/{field}: {value!r}"
        ) from exc
    if not number.is_finite():
        raise BoundedFeatureRestatementError(
            f"non-finite OHLC source {symbol}/{date}/{field}"
        )
    return number, grouped


def _calculate_full_prefix_features(
    frames: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, dict[str, dict[str, int | None]]], dict[str, Any]]:
    calculated: dict[str, dict[str, dict[str, int | None]]] = {}
    missing: Counter[str] = Counter()
    finite: Counter[str] = Counter()
    row_count_by_symbol: dict[str, int] = {}
    gaps_by_symbol: dict[str, int] = {}
    for symbol, source_frame in sorted(frames.items()):
        # 輸入副本已嚴格解析；純 kernel 收到完整排序前綴，缺價維持 NaN。
        output = calculate_causal_indicators(source_frame)
        symbol_values: dict[str, dict[str, int | None]] = {}
        for source_row, (_, indicator_row) in zip(
            source_frame.itertuples(index=False, name=None),
            output.iterrows(),
            strict=True,
        ):
            event_date = str(source_row[0])
            values: dict[str, int | None] = {}
            for column in CAUSAL_INDICATOR_COLUMNS:
                raw_value = float(indicator_row[column])
                if not math.isfinite(raw_value):
                    values[column] = None
                    missing[column] += 1
                else:
                    values[column] = _indicator_value_int(raw_value)
                    finite[column] += 1
            symbol_values[event_date] = values
        if len(symbol_values) != len(source_frame):
            raise BoundedFeatureRestatementError(
                f"causal kernel changed row cardinality for {symbol}"
            )
        calculated[symbol] = symbol_values
        row_count_by_symbol[symbol] = len(source_frame)
        missing_ohlc = source_frame.loc[:, list(_OHLC_FIELDS)].isna().any(axis=1)
        gaps_by_symbol[symbol] = int(missing_ohlc.sum())
    return calculated, {
        "kernel": "calculate_causal_indicators",
        "calculation_prefix": "各股票完整的來源 OHLC 歷史前綴",
        "missing_ohlc_rows_by_symbol": dict(sorted(gaps_by_symbol.items())),
        "source_rows_by_symbol": dict(sorted(row_count_by_symbol.items())),
        "finite_values_by_indicator": dict(sorted(finite.items())),
        "missing_values_by_indicator": dict(sorted(missing.items())),
        "暖機與缺價後重算期間維持缺值": True,
    }


def _indicator_value_int(value: float) -> int:
    # TA-Lib 僅在分析計算邊界使用浮點數，輸出以 Decimal 半偶捨入到凍結尺度。
    scaled = Decimal(str(value)) * Decimal(10_000)
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _changed_label_rows(
    *,
    original_shards: tuple[tuple[Path, Mapping[str, Any]], ...],
    label_shards: tuple[tuple[Path, Mapping[str, Any]], ...],
) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    for (original_path, original_entry), (label_path, label_entry) in zip(
        original_shards, label_shards, strict=True
    ):
        if int(original_entry["year"]) != int(label_entry["year"]):
            raise BoundedFeatureRestatementError("source and label shard years differ")
        with gzip.open(original_path, "rt", encoding="utf-8") as original_stream, gzip.open(
            label_path, "rt", encoding="utf-8"
        ) as label_stream:
            original_header = json.loads(next(original_stream))
            label_header = json.loads(next(label_stream))
            if (
                original_header.get("record_type") != "header"
                or label_header.get("record_type") != "header"
            ):
                raise BoundedFeatureRestatementError("invalid paired JSONL headers")
            row_count = 0
            for original_line, label_line in zip(
                original_stream, label_stream, strict=True
            ):
                original_record = json.loads(original_line)
                label_record = json.loads(label_line)
                original_sample = _sample_record(original_record)
                label_sample = _sample_record(label_record)
                original_row = _mapping(original_sample.get("row"), "original row")
                label_row = _mapping(label_sample.get("row"), "label row")
                row_id = str(original_row.get("row_id", ""))
                if row_id != label_row.get("row_id"):
                    raise BoundedFeatureRestatementError(
                        "row order/identity changed in label-only publication"
                    )
                original_labels = _labels_by_horizon(original_sample)
                label_labels = _labels_by_horizon(label_sample)
                if set(original_labels) != set(label_labels):
                    raise BoundedFeatureRestatementError(
                        f"label horizons changed for {row_id}"
                    )
                changed: set[int] = set()
                for horizon, prior in original_labels.items():
                    current = label_labels[horizon]
                    if prior["horizon_end_date"] != current["horizon_end_date"]:
                        raise BoundedFeatureRestatementError(
                            f"label maturity changed for {row_id}/H{horizon}"
                        )
                    if prior["available_at"] != current["available_at"]:
                        raise BoundedFeatureRestatementError(
                            f"label maturity clock changed for {row_id}/H{horizon}"
                        )
                    if any(
                        prior.get(field) != current.get(field)
                        for field in _TARGET_OUTCOME_FIELDS
                    ):
                        changed.add(horizon)
                if changed:
                    result[row_id] = changed
                row_count += 1
            if row_count != int(original_entry["sample_count"]):
                raise BoundedFeatureRestatementError(
                    f"paired row count mismatch for {original_path.name}"
                )
    return result


def _write_feature_shard(
    *,
    source_path: Path,
    expected_parent_sha256: str,
    original_path: Path,
    expected_original_sha256: str,
    output_path: Path,
    header: Mapping[str, Any],
    feature_ids: tuple[str, ...],
    price_definitions: Mapping[str, Mapping[str, Any]],
    calculated: Mapping[str, Mapping[str, Mapping[str, int | None]]],
    changed_labels: Mapping[str, set[int]],
    dataset_identity_hash: str,
    feature_registry_hash: str,
    source_manifest_hashes: tuple[tuple[str, str], ...],
    revision_observed_at: str,
    stats: "_RestatementStats",
) -> dict[str, Any]:
    if _file_sha256(source_path) != expected_parent_sha256:
        raise BoundedFeatureRestatementError("label-only shard changed before read")
    if _file_sha256(original_path) != expected_original_sha256:
        raise BoundedFeatureRestatementError("original shard changed before read")
    output_digest = hashlib.sha256()
    sample_count = 0
    with gzip.open(source_path, "rt", encoding="utf-8") as parent_stream, gzip.open(
        original_path, "rt", encoding="utf-8"
    ) as original_stream, output_path.open("wb") as file_stream:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=file_stream, compresslevel=6, mtime=0
        ) as output_stream:
            parent_header = json.loads(next(parent_stream))
            original_header = json.loads(next(original_stream))
            if (
                parent_header.get("record_type") != "header"
                or original_header.get("record_type") != "header"
            ):
                raise BoundedFeatureRestatementError("source header is not first")
            encoded_header = (_canonical_json(dict(header)) + "\n").encode("utf-8")
            output_stream.write(encoded_header)
            output_digest.update(encoded_header)
            for parent_line, original_line in zip(
                parent_stream, original_stream, strict=True
            ):
                parent_record = json.loads(parent_line)
                original_record = json.loads(original_line)
                sample = dict(_sample_record(parent_record))
                original_sample = _sample_record(original_record)
                row = dict(_mapping(sample.get("row"), "sample.row"))
                row_id = str(row.get("row_id", ""))
                original_row = _mapping(original_sample.get("row"), "original row")
                if row_id != original_row.get("row_id"):
                    raise BoundedFeatureRestatementError(
                        "paired rows changed order during write"
                    )
                symbol = _normalize_symbol(row.get("symbol"))
                decision_at = _require_text(
                    row.get("decision_at"), "row.decision_at"
                )
                decision_date = decision_at[:10]
                features_raw = row.get("features")
                if not isinstance(features_raw, list) or len(features_raw) != 62:
                    raise BoundedFeatureRestatementError(
                        f"row {row_id} does not carry 62 features"
                    )
                if tuple(str(item.get("feature_id", "")) for item in features_raw) != feature_ids:
                    raise BoundedFeatureRestatementError(
                        f"feature order changed in row {row_id}"
                    )
                close_feature = next(
                    item
                    for item in features_raw
                    if item["feature_id"] == "daily_prices.收盤價"
                )
                event_at = _require_text(
                    close_feature.get("event_at"),
                    f"{row_id}.daily_prices.收盤價.event_at",
                )
                event_date = _event_date(event_at)
                indicator_values = calculated.get(symbol, {}).get(event_date)
                replaced_features: list[dict[str, Any]] = []
                for raw_feature in features_raw:
                    feature = dict(raw_feature)
                    feature_id = str(feature["feature_id"])
                    if feature_id in TECHNICAL_FEATURE_IDS:
                        if int(feature.get("scale", 0)) != 10000:
                            raise BoundedFeatureRestatementError(
                                f"frozen technical scale changed: {feature_id}"
                            )
                        column = feature_id.removeprefix("technical_indicators.")
                        value_int = (
                            None
                            if indicator_values is None
                            else indicator_values[column]
                        )
                        feature.update(
                            _restated_feature_payload(
                                feature_id=feature_id,
                                family_id=PRICE_FAMILY,
                                source_id=TECHNICAL_SOURCE_ID,
                                value_int=value_int,
                                scale=10000,
                                event_at=event_at,
                                available_at=revision_observed_at,
                                quality="estimated" if value_int is not None else "missing",
                                row_id=row_id,
                                snapshot_event_date=event_date,
                                identity_hash=dataset_identity_hash,
                            )
                        )
                        stats.observe_indicator(column, value_int)
                    replaced_features.append(feature)
                price_stats = _price_quality_stats(
                    features=replaced_features,
                    definitions=price_definitions,
                    decision_date=decision_date,
                )
                old_quality_blocked = next(
                    feature
                    for feature in replaced_features
                    if feature["feature_id"]
                    == f"data_quality.{PRICE_FAMILY}.quality_blocked_count"
                )
                if old_quality_blocked["value_int"] != 0:
                    raise BoundedFeatureRestatementError(
                        "price-family quality-blocked source values are unsupported"
                    )
                for feature in replaced_features:
                    if feature["feature_id"] in QUALITY_FEATURE_IDS:
                        if int(feature.get("scale", 0)) != 1:
                            raise BoundedFeatureRestatementError(
                                f"frozen quality scale changed: {feature['feature_id']}"
                            )
                        metric = feature["feature_id"].rsplit(".", 1)[-1]
                        value_int = price_stats[metric]
                        feature.update(
                            _restated_feature_payload(
                                feature_id=feature["feature_id"],
                                family_id="data_quality",
                                source_id=QUALITY_SOURCE_ID,
                                value_int=value_int,
                                scale=1,
                                event_at=decision_at,
                                available_at=revision_observed_at,
                                quality="estimated",
                                row_id=row_id,
                                snapshot_event_date=event_date,
                                identity_hash=dataset_identity_hash,
                            )
                        )
                        stats.observe_quality(metric, value_int)
                # 保留原 ID 順序、尺度與型別；只更新白名單中的 25 欄及 lineage。
                if tuple(f["feature_id"] for f in replaced_features) != feature_ids:
                    raise BoundedFeatureRestatementError(
                        f"feature id order changed for {row_id}"
                    )
                row["features"] = replaced_features
                row["missing_family_ids"] = sorted(
                    {
                        str(feature["family_id"])
                        for feature in replaced_features
                        if feature["family_id"] != "data_quality"
                        and not bool(feature["observed"])
                    }
                )
                row["dataset_identity_hash"] = dataset_identity_hash
                row["feature_registry_hash"] = feature_registry_hash
                row["source_manifest_hashes"] = [
                    list(pair) for pair in source_manifest_hashes
                ]
                sample["row"] = row

                labels = sample.get("horizon_labels")
                if not isinstance(labels, list):
                    raise BoundedFeatureRestatementError(
                        f"horizon_labels missing for {row_id}"
                    )
                revision_rows: list[dict[str, Any]] = []
                changed_horizons = changed_labels.get(row_id, set())
                for label in labels:
                    horizon = int(label["horizon_trading_days"])
                    maturity = str(label["available_at"])
                    restated = horizon in changed_horizons
                    revision_rows.append(
                        {
                            "horizon_trading_days": horizon,
                            "event_maturity_available_at": maturity,
                            "revision_available_at": (
                                revision_observed_at if restated else maturity
                            ),
                            "restated": restated,
                        }
                    )
                    if restated:
                        stats.revised_labels += 1
                sample["restated_research_provenance"] = {
                    "dataset_temporality": "restated_research",
                    "historical_pit": False,
                    "feature_revision_observed_at": revision_observed_at,
                    "label_revision_clocks": revision_rows,
                }
                stats.observe_sample_before(parent_record, original_sample)
                stats.observe_sample_after(sample)
                record = {"record_type": "sample", "sample": sample}
                encoded = (_canonical_json(record) + "\n").encode("utf-8")
                output_stream.write(encoded)
                output_digest.update(encoded)
                sample_count += 1
            output_stream.close()
            file_stream.flush()
            os.fsync(file_stream.fileno())
    if _file_sha256(source_path) != expected_parent_sha256:
        raise BoundedFeatureRestatementError("label-only shard changed during read")
    if _file_sha256(original_path) != expected_original_sha256:
        raise BoundedFeatureRestatementError("original shard changed during read")
    return {
        "sample_count": sample_count,
        "content_sha256": "sha256:" + output_digest.hexdigest(),
    }


def _restated_feature_payload(
    *,
    feature_id: str,
    family_id: str,
    source_id: str,
    value_int: int | None,
    scale: int,
    event_at: str,
    available_at: str,
    quality: str,
    row_id: str,
    snapshot_event_date: str,
    identity_hash: str,
) -> dict[str, Any]:
    revision = _sha256_json(
        {
            "schema_version": FULL_RESTATEMENT_SCHEMA,
            "dataset_identity_hash": identity_hash,
            "row_id": row_id,
            "feature_id": feature_id,
            "snapshot_event_date": snapshot_event_date,
            "value_int": value_int,
            "scale": scale,
        }
    )
    content = _sha256_json(
        {
            "source_id": source_id,
            "row_id": row_id,
            "feature_id": feature_id,
            "event_at": event_at,
            "value_int": value_int,
            "scale": scale,
            "dataset_identity_hash": identity_hash,
        }
    )
    observed = value_int is not None
    return {
        "feature_id": feature_id,
        "family_id": family_id,
        "source_id": source_id,
        "value_int": value_int,
        "scale": scale,
        "event_at": event_at,
        "available_at": available_at,
        "revision_id": revision,
        "quality": quality if observed else "missing",
        "content_hash": content,
        "observed": observed,
        "event_time_semantics": "realized_observation",
    }


def _price_quality_stats(
    *,
    features: list[dict[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
    decision_date: str,
) -> dict[str, int]:
    by_id = {str(feature["feature_id"]): feature for feature in features}
    total = len(definitions)
    observed = 0
    missing = 0
    stale_count = 0
    max_lag = 0
    quality_blocked_count = 0
    for feature_id, definition in definitions.items():
        feature = by_id.get(feature_id)
        if feature is None:
            raise BoundedFeatureRestatementError(
                f"price family feature absent from row: {feature_id}"
            )
        # 新技術欄的修訂是在本次觀測到；新鮮度仍以歷史來源事件評估，
        # 兩種時鐘會分別序列化。
        age_clock = (
            feature["event_at"]
            if feature_id in TECHNICAL_FEATURE_IDS
            else feature["available_at"]
        )
        lag = max(
            0,
            (
                datetime.fromisoformat(decision_date).date()
                - datetime.fromisoformat(str(age_clock).replace("Z", "+00:00")).date()
            ).days,
        )
        max_lag = max(max_lag, lag)
        stale = lag > int(definition["stale_after_days"])
        stale_count += int(stale)
        quality_blocked_count += int(
            bool(feature.get("quality_blocked_mask", False))
        )
        is_observed = (
            bool(feature["observed"])
            and feature["value_int"] is not None
            and not stale
        )
        observed += int(is_observed)
        missing += int(not is_observed)
    if quality_blocked_count != 0:
        raise BoundedFeatureRestatementError(
            "source row carries unsupported quality-blocked price masks"
        )
    return {
        "coverage_bp": observed * 10_000 // total if total else 0,
        "missing_count": missing,
        "stale_count": stale_count,
        "quality_blocked_count": quality_blocked_count,
        "max_available_lag_days": max_lag,
    }


def _price_feature_definitions(
    registry: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    features = registry.get("features")
    if not isinstance(features, list):
        raise BoundedFeatureRestatementError(
            "feature registry definitions are missing"
        )
    result = {
        str(item["feature_id"]): _mapping(item, "feature definition")
        for item in features
        if isinstance(item, dict)
        and item.get("family_id") == PRICE_FAMILY
    }
    if len(result) != sum(
        1
        for item in features
        if isinstance(item, dict) and item.get("family_id") == PRICE_FAMILY
    ):
        raise BoundedFeatureRestatementError(
            "price feature registry ids are duplicated"
        )
    return result


def _validate_header_feature_abi(header: Mapping[str, Any]) -> tuple[str, ...]:
    packs = header.get("feature_packs")
    if not isinstance(packs, list):
        raise BoundedFeatureRestatementError("feature packs are missing")
    ids: list[str] = []
    for pack in packs:
        payload = _mapping(pack, "feature pack")
        feature_ids = payload.get("feature_ids")
        if not isinstance(feature_ids, list):
            raise BoundedFeatureRestatementError("feature pack ids are missing")
        ids.extend(str(feature_id) for feature_id in feature_ids)
    return tuple(ids)


def _first_row_feature_ids(path: Path) -> tuple[str, ...]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if not isinstance(header, dict) or header.get("record_type") != "header":
            raise BoundedFeatureRestatementError("invalid first-shard header")
        sample_record = json.loads(next(stream))
    sample = _sample_record(sample_record)
    row = _mapping(sample.get("row"), "first sample row")
    features = row.get("features")
    if not isinstance(features, list):
        raise BoundedFeatureRestatementError("first row feature list is missing")
    return tuple(
        _require_text(feature.get("feature_id"), "feature.feature_id")
        for feature in features
        if isinstance(feature, dict)
    )


def _restated_feature_registry(
    source_registry: Mapping[str, Any], *, kernel_hash: Mapping[str, str]
) -> dict[str, Any]:
    registry = json.loads(_canonical_json(source_registry))
    definitions = registry.get("features")
    if not isinstance(definitions, list):
        raise BoundedFeatureRestatementError("feature registry is malformed")
    for definition in definitions:
        if definition.get("feature_id") not in TECHNICAL_FEATURE_IDS:
            continue
        old_record_hash = str(definition.get("record_hash", ""))
        definition["source_id"] = TECHNICAL_SOURCE_ID
        definition["table_name"] = "derived_technical_indicators"
        definition["record_hash"] = _sha256_json(
            {
                "schema_version": "restated-feature-definition.v1",
                "prior_record_hash": old_record_hash,
                "feature_id": definition["feature_id"],
                "source_id": TECHNICAL_SOURCE_ID,
                "table_name": "derived_technical_indicators",
                "scale": definition["scale"],
                "kernel_source_hashes": dict(kernel_hash),
            }
        )
    registry["features"].sort(key=lambda item: str(item["feature_id"]))
    return registry


def _new_source_manifest_hashes(
    source_hashes: Any,
    *,
    expected_sha: str,
    receipt_hash: str,
    kernel_hashes: Mapping[str, str],
    helper_hash: str,
    identity_hash: str,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(source_hashes, list):
        raise BoundedFeatureRestatementError("source manifest hashes are missing")
    pairs: dict[str, str] = {}
    for pair in source_hashes:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise BoundedFeatureRestatementError("invalid source manifest hash")
        pairs[str(pair[0])] = _require_sha256(str(pair[1]), "source manifest hash")
    pairs[TECHNICAL_SOURCE_ID] = _sha256_json(
        {
            "schema_version": "bounded-causal-technical-source.v1",
            "source_snapshot_sha256": expected_sha,
            "repair_receipt_sha256": receipt_hash,
            "kernel_source_hashes": dict(kernel_hashes),
            "grouped_numeric_helper_sha256": helper_hash,
            "recipe": "calculate_causal_indicators_full_prefix_gap_rewarm_v1",
        }
    )
    pairs[QUALITY_SOURCE_ID] = _sha256_json(
        {
            "schema_version": "bounded-restated-price-quality.v1",
            "dataset_identity_hash": identity_hash,
            "technical_source_hash": pairs[TECHNICAL_SOURCE_ID],
            "recipe": "price_liquidity_technical_event_clock_quality_v1",
        }
    )
    pairs["sidecar:historical_price_repair_receipt"] = receipt_hash
    pairs["sqlite.snapshot.twstock_snapshot_run02"] = expected_sha
    return tuple(sorted(pairs.items()))


def _kernel_source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "analysis_module" / "technical_analysis" / "technical_indicators.py",
        root / "analysis_module" / "technical_analysis" / "technical_date_support.py",
        root / "analysis_module" / "technical_analysis" / "indicator_kernels.py",
    )
    return {
        path.relative_to(root).as_posix(): _file_sha256(path)
        for path in paths
    }


def _verify_parent_lineage(
    original_manifest: Mapping[str, Any], label_manifest: Mapping[str, Any]
) -> None:
    restatement = _mapping(label_manifest.get("restatement"), "label restatement")
    if restatement.get("parent_publication_id") != original_manifest.get(
        "publication_id"
    ):
        raise BoundedFeatureRestatementError(
            "label-only parent points at a different original publication"
        )
    if restatement.get("parent_publication_manifest_hash") != original_manifest.get(
        "manifest_hash"
    ):
        raise BoundedFeatureRestatementError(
            "label-only parent manifest hash does not match original publication"
        )
    if label_manifest.get("sample_count") != original_manifest.get("sample_count"):
        raise BoundedFeatureRestatementError(
            "label-only parent changed the original row universe"
        )


def _verify_manifest_hash(
    manifest: Mapping[str, Any], label: str
) -> None:
    body = dict(manifest)
    claimed = body.pop("manifest_hash", None)
    if not isinstance(claimed, str) or claimed != _sha256_json(body):
        raise BoundedFeatureRestatementError(f"{label} manifest hash mismatch")


def _sample_record(record: Any) -> Mapping[str, Any]:
    payload = _mapping(record, "JSONL record")
    if payload.get("record_type") != "sample":
        raise BoundedFeatureRestatementError("expected sample record")
    return _mapping(payload.get("sample"), "sample")


def _labels_by_horizon(sample: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    labels = sample.get("horizon_labels")
    if not isinstance(labels, list):
        raise BoundedFeatureRestatementError("horizon labels are missing")
    result: dict[int, Mapping[str, Any]] = {}
    for value in labels:
        label = _mapping(value, "horizon label")
        horizon = int(label["horizon_trading_days"])
        if horizon in result:
            raise BoundedFeatureRestatementError("duplicate horizon label")
        result[horizon] = label
    return result


def _event_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BoundedFeatureRestatementError(f"invalid event_at: {value}") from exc
    return parsed.date().isoformat()


def _require_sha256(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise BoundedFeatureRestatementError(f"{field} must be a sha256 digest")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoundedFeatureRestatementError(f"{field} must be non-empty text")
    return value


def _research_publication_id(
    identity_hash: str, shards: list[Mapping[str, Any]] | None = None
) -> str:
    del shards
    return f"portfolio-ml-bounded-research-{identity_hash[7:31]}"


class _RestatementStats:
    def __init__(self, feature_ids: tuple[str, ...]) -> None:
        self.sample_count = 0
        self.replaced_technical_slots = 0
        self.replaced_quality_slots = 0
        self.revised_labels = 0
        self.indicator_finite: Counter[str] = Counter()
        self.indicator_missing: Counter[str] = Counter()
        self.quality_values: dict[str, Counter[int]] = {
            metric_id.rsplit(".", 1)[-1]: Counter()
            for metric_id in QUALITY_FEATURE_IDS
        }
        self.feature_ids = feature_ids
        self.preserved_digests = {
            key: hashlib.sha256()
            for key in ("row_ids", "unrestated_features", "targets", "state", "labels")
        }
        self.after_digests = {
            key: hashlib.sha256() for key in self.preserved_digests
        }

    def observe_indicator(self, column: str, value_int: int | None) -> None:
        self.replaced_technical_slots += 1
        (self.indicator_finite if value_int is not None else self.indicator_missing)[
            column
        ] += 1

    def observe_quality(self, metric: str, value_int: int) -> None:
        self.replaced_quality_slots += 1
        self.quality_values[metric][value_int] += 1

    def observe_sample_before(
        self, parent_record: Mapping[str, Any], original_sample: Mapping[str, Any]
    ) -> None:
        parent_sample = _sample_record(parent_record)
        row = _mapping(parent_sample.get("row"), "parent row")
        original_row = _mapping(original_sample.get("row"), "original row")
        row_id = str(row["row_id"])
        self._update_digest(self.preserved_digests["row_ids"], row_id)
        unchanged = [
            feature
            for feature in row["features"]
            if feature["feature_id"] not in RESTATED_FEATURE_IDS
        ]
        self._update_digest(
            self.preserved_digests["unrestated_features"],
            _canonical_json({"row_id": row_id, "features": unchanged}),
        )
        self._update_digest(
            self.preserved_digests["targets"],
            _canonical_json({"row_id": row_id, "targets": row["targets"]}),
        )
        self._update_digest(
            self.preserved_digests["state"],
            _canonical_json({"row_id": row_id, "state": row["portfolio_state"]}),
        )
        self._update_digest(
            self.preserved_digests["labels"],
            _canonical_json(
                {"row_id": row_id, "labels": parent_sample["horizon_labels"]}
            ),
        )
        if (
            row["targets"] != original_row["targets"]
            or row["portfolio_state"] != original_row["portfolio_state"]
        ):
            raise BoundedFeatureRestatementError(
                f"label-only output altered target/state for {row_id}"
            )

    def observe_sample_after(self, sample: Mapping[str, Any]) -> None:
        row = _mapping(sample.get("row"), "output row")
        row_id = str(row["row_id"])
        self.sample_count += 1
        self._update_digest(self.after_digests["row_ids"], row_id)
        unchanged = [
            feature
            for feature in row["features"]
            if feature["feature_id"] not in RESTATED_FEATURE_IDS
        ]
        self._update_digest(
            self.after_digests["unrestated_features"],
            _canonical_json({"row_id": row_id, "features": unchanged}),
        )
        self._update_digest(
            self.after_digests["targets"],
            _canonical_json({"row_id": row_id, "targets": row["targets"]}),
        )
        self._update_digest(
            self.after_digests["state"],
            _canonical_json({"row_id": row_id, "state": row["portfolio_state"]}),
        )
        self._update_digest(
            self.after_digests["labels"],
            _canonical_json({"row_id": row_id, "labels": sample["horizon_labels"]}),
        )

    @staticmethod
    def _update_digest(digest: Any, value: str) -> None:
        digest.update(value.encode("utf-8") + b"\n")

    def preservation_payload(self) -> dict[str, Any]:
        labels_equal = (
            self.preserved_digests["labels"].digest()
            == self.after_digests["labels"].digest()
        )
        return {
            "row_count_preserved": self.sample_count,
            "row_ids_sha256_before": "sha256:"
            + self.preserved_digests["row_ids"].hexdigest(),
            "row_ids_sha256_after": "sha256:"
            + self.after_digests["row_ids"].hexdigest(),
            "unrestated_features_sha256_before": "sha256:"
            + self.preserved_digests["unrestated_features"].hexdigest(),
            "unrestated_features_sha256_after": "sha256:"
            + self.after_digests["unrestated_features"].hexdigest(),
            "targets_sha256_before": "sha256:"
            + self.preserved_digests["targets"].hexdigest(),
            "targets_sha256_after": "sha256:"
            + self.after_digests["targets"].hexdigest(),
            "portfolio_state_sha256_before": "sha256:"
            + self.preserved_digests["state"].hexdigest(),
            "portfolio_state_sha256_after": "sha256:"
            + self.after_digests["state"].hexdigest(),
            "label_payloads_sha256_before": "sha256:"
            + self.preserved_digests["labels"].hexdigest(),
            "label_payloads_sha256_after": "sha256:"
            + self.after_digests["labels"].hexdigest(),
            "label_payloads_identical": labels_equal,
        }

    def assert_preserved(self) -> None:
        for field in ("row_ids", "unrestated_features", "targets", "state", "labels"):
            if self.preserved_digests[field].digest() != self.after_digests[field].digest():
                raise BoundedFeatureRestatementError(
                    f"full-feature restatement changed protected payload: {field}"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "rows": self.sample_count,
            "technical_slots_recomputed": self.replaced_technical_slots,
            "quality_slots_recomputed": self.replaced_quality_slots,
            "label_revision_rows": self.revised_labels,
            "indicator_finite_values": dict(sorted(self.indicator_finite.items())),
            "indicator_missing_values": dict(sorted(self.indicator_missing.items())),
            "quality_metric_value_counts": {
                metric: {
                    str(value): count
                    for value, count in sorted(
                        counts.items(), key=lambda item: str(item[0])
                    )
                }
                for metric, counts in sorted(self.quality_values.items())
            },
        }
