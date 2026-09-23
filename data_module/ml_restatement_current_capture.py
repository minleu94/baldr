"""從唯讀交易快照建立新的當日研究輸入，不改寫正式資料或訓練集。"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from analysis_module.technical_analysis import indicator_kernels
from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
from data_module.ml_restatement_research_dataset import (
    SUPPORTED_HORIZONS,
    TECHNICAL_FIELDS,
    _iso_date,
    arrow_schema,
    build_restated_feature_values,
    canonical_hash,
    expected_feature_contract,
    sha256_file,
)
from data_module.ml_restatement_current_inputs import _IDENTITY_FIELDS, _aware


_TAIPEI = ZoneInfo("Asia/Taipei")
_PRICE_COLUMNS = (
    "日期", "證券代號", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價",
    "最低價", "收盤價", "涨跌", "漲跌價差", "最後揭示買價", "最後揭示買量",
    "最後揭示賣價", "最後揭示賣量", "本益比",
)
_MARKET_COLUMNS = (
    "日期", "指數名稱", "收盤指數", "漲跌點數", "漲跌百分比", "開盤價",
    "最高價", "最低價", "收盤價", "成交量",
)
_COMPARE_COLUMNS = tuple(name for name in _PRICE_COLUMNS if name not in {"日期", "證券代號", "涨跌"})


def _same_number(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return False


def _bound_json(path: Path, digest: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"current capture source hash mismatch: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("current capture requires JSON objects")
    return value


def _source_date(value: object) -> date:
    day = _iso_date(value)
    if day is None:
        raise ValueError("current source contains an empty date")
    return day


def capture_restated_current_dataset(
    *,
    database_path: Path,
    template_manifest_path: Path,
    expected_template_manifest_hash: str,
    price_repair_receipt: Path,
    expected_price_receipt_hash: str,
    symbols: Sequence[str],
    output_root: Path,
) -> tuple[Path, str]:
    """以一個 SQLite read transaction 封存當日 T-1 前綴與 62 欄特徵。

    同一呼叫不接受歷史時間參數。模型 schema 取自已核對的修訂資料集，
    但新的資料來源、實際觀測鐘與 dataset identity 都重新建立。
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    started = datetime.now(timezone.utc)
    decision = started.astimezone(_TAIPEI).date()
    chosen = tuple(sorted(symbols))
    if not chosen or len(chosen) > 250 or len(chosen) != len(set(chosen)) or any(
        not isinstance(value, str) or not value or value.strip() != value for value in chosen
    ):
        raise ValueError("current capture requires 1..250 unique explicit symbols")
    template = _bound_json(template_manifest_path, expected_template_manifest_hash)
    names, scales = expected_feature_contract()
    if (
        template.get("schema_version") != "portfolio-ml-restated-research-dataset.v1"
        or template.get("status") != "complete_research_build"
        or template.get("restated_research") is not True
        or template.get("formal_historical_PIT") is not False
        or tuple(template.get("feature_ids", ())) != names
        or tuple(template.get("feature_scales", ())) != scales
        or canonical_hash({name: template[name] for name in _IDENTITY_FIELDS}) != template.get("dataset_identity_hash")
    ):
        raise ValueError("current capture template does not match the sealed research contract")
    receipt = _bound_json(price_repair_receipt, expected_price_receipt_hash)
    if (
        receipt.get("schema_version") != "historical-price-spike-repair-20260921.v1"
        or receipt.get("receipt_kind") != "historical_price_spike_repair"
        or receipt.get("status") != "applied"
        or receipt.get("available_at_backfilled") is not False
        or receipt.get("historical_decision_time_available") is not False
    ):
        raise ValueError("current capture requires the completed, non-backdated price repair receipt")
    corrected = _aware(receipt["corrected_at"], "corrected_at")
    if corrected > started:
        raise ValueError("price correction was not observed before current capture")
    repair_day = _iso_date(receipt["source_date"])
    repair_rows = {str(row["symbol"]): row["after"] for row in receipt["rows"]}
    if len(repair_rows) != receipt["allowlist_count"] or repair_day is None:
        raise ValueError("price repair receipt row identities are inconsistent")
    source = database_path.resolve(strict=True)
    output = output_root.resolve()
    if output == source.parent or output.is_relative_to(source.parent):
        raise ValueError("current capture output must be outside the database directory")
    if output == template_manifest_path.resolve().parent or output.is_relative_to(template_manifest_path.resolve().parent):
        raise ValueError("current capture must not write into the frozen template dataset")
    run = output / ("capture-" + started.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    source_prefix = run / "source_prefix.jsonl.gz"
    code_paths = {
        "capture": Path(__file__),
        "features": Path(build_restated_feature_values.__code__.co_filename),
        "kernel_facade": Path(calculate_causal_indicators.__code__.co_filename),
        "kernel": Path(indicator_kernels.__file__),
    }
    code_hashes = {name: sha256_file(path) for name, path in code_paths.items()}
    connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    rows: list[dict[str, Any]] = []
    verified_repair_symbols: list[str] = []
    try:
        market_rows = [dict(row) for row in connection.execute(
            "SELECT " + ",".join('"' + name + '"' for name in _MARKET_COLUMNS)
            + " FROM market_indices WHERE 指數名稱='TAIEX' AND 日期<? ORDER BY 日期",
            (decision.strftime("%Y%m%d"),),
        )]
        market = {_source_date(row["日期"]): row for row in market_rows}
        if len(market) != len(market_rows):
            raise ValueError("current market dates are missing or repeated")
        calendar = sorted(market)
        if not calendar or calendar[-1] >= decision or (decision - calendar[-1]).days > 7:
            raise ValueError("current capture has no fresh T-1 market source")
        with gzip.open(source_prefix, "wt", encoding="utf-8", newline="\n") as prefix:
            def save_source(kind: str, payload: object) -> None:
                prefix.write(json.dumps({"kind": kind, "rows": payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")

            save_source("market_indices", market_rows)
            for symbol in chosen:
                raw = [dict(row) for row in connection.execute(
                    "SELECT " + ",".join('"' + name + '"' for name in _PRICE_COLUMNS)
                    + " FROM daily_prices WHERE 證券代號=? AND 日期<? ORDER BY 日期",
                    (symbol, decision.strftime("%Y%m%d")),
                )]
                dates = [_source_date(row["日期"]) for row in raw]
                if not raw or any(day >= decision for day in dates) or dates != sorted(set(dates)):
                    raise ValueError(f"{symbol}: invalid or missing causal price prefix")
                if symbol in repair_rows:
                    affected = [row for row, day in zip(raw, dates) if day == repair_day]
                    if len(affected) != 1 or any(
                        not _same_number(affected[0][name], repair_rows[symbol].get(name))
                        for name in _COMPARE_COLUMNS
                    ):
                        raise ValueError(f"{symbol}: current source does not contain the verified corrected prices")
                    verified_repair_symbols.append(symbol)
                save_source("daily_prices:" + symbol, raw)
                frame = calculate_causal_indicators(pd.DataFrame(raw))
                if len(frame) != len(raw) or any(name not in frame for name in TECHNICAL_FIELDS):
                    raise ValueError("current causal kernel output is incomplete")
                values, masks, stock_day, market_day = build_restated_feature_values(
                    decision=decision, stock=frame, dates=dates, raw_rows=raw,
                    market_dates=calendar, market_rows=market, feature_scales=scales,
                )
                if stock_day is None or market_day is None:
                    raise ValueError("current features lack a causal stock/market event")
                rows.append({
                    "row_id": f"row:{decision.isoformat()}:{symbol}", "symbol": symbol,
                    "decision_date": decision,
                    "decision_at": datetime.combine(decision, time(8, 30), _TAIPEI).isoformat(),
                    "local_row_index": None, "fold_role": "current_inference_only", "fold_ids": [],
                    "calendar_basis": "actual_capture_date; T-1 observed TAIEX prefix",
                    "stock_event_date": stock_day, "market_event_date": market_day,
                    "feature_event_asof_at": datetime.combine(max(stock_day, market_day), time(14, 30), _TAIPEI).isoformat(),
                    "features_scaled_i64": [None if mask else value for value, mask in zip(values, masks)],
                    "feature_missing_mask": masks,
                    "target_values_i32": [None] * 6, "target_missing_mask": [1] * 6,
                    **{f"{field}_h{horizon}{suffix}": value for horizon in SUPPORTED_HORIZONS for field, suffix, value in (
                        ("label_end_date", "", None), ("maturity_at", "", None),
                        ("labels", "_i64", [None] * 9), ("labels", "_missing_mask", [1] * 9),
                        ("label_basis", "", None),
                    )},
                })
    finally:
        connection.rollback()
        connection.close()
    observed = datetime.now(timezone.utc)
    if observed.astimezone(_TAIPEI).date() != decision:
        raise ValueError("current capture crossed Taipei midnight; retry in a new run")
    if {name: sha256_file(path) for name, path in code_paths.items()} != code_hashes:
        raise ValueError("current capture source code changed during execution")
    prefix_hash = sha256_file(source_prefix)
    for row in rows:
        row.update(
            feature_available_at=observed.isoformat(), revision_observed_at=observed.isoformat(),
            source_revision_id="current-prefix-" + prefix_hash[7:],
        )
        row["feature_lineage_hash"] = canonical_hash({
            "row_id": row["row_id"], "prefix_hash": prefix_hash,
            "values": row["features_scaled_i64"], "mask": row["feature_missing_mask"],
        })
    partition = run / "current.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=arrow_schema()), partition, compression="zstd")
    manifest = dict(template)
    manifest.update(
        source_hashes={
            "prepared_source_prefix": {"path": source_prefix.name, "sha256": prefix_hash},
            "price_repair_receipt": {"path": str(price_repair_receipt.resolve()), "sha256": expected_price_receipt_hash},
            "template_manifest": {"path": str(template_manifest_path.resolve()), "sha256": expected_template_manifest_hash},
            "capture_code": code_hashes,
        },
        source_manifest_hashes=sorted([
            ["sqlite.current_read_transaction_prefix", prefix_hash],
            ["custody.price_repair", expected_price_receipt_hash],
            ["schema.template_manifest", expected_template_manifest_hash],
            *[["code." + name, value] for name, value in code_hashes.items()],
        ]),
        kernel={"recipe_version": "causal-indicators.full-prefix.gap-reset.v1", "source_hashes": code_hashes},
        builder_code_sha256=code_hashes["capture"],
        training_as_of=observed.isoformat(), revision_observed_at=observed.isoformat(),
        row_count=len(rows), partition_files=[{
            "year": decision.year, "path": partition.name, "row_count": len(rows),
            "baseline_row_count": 0, "appended_row_count": len(rows),
            "file_sha256": sha256_file(partition), "byte_count": partition.stat().st_size,
        }],
        date_filter={"start": decision.isoformat(), "end": decision.isoformat(), "limit_rows": None},
        symbol_filter=list(chosen), observed_session_dates=[day.isoformat() for day in calendar],
        original_row_target_audit={"current_targets": "all missing; current dataset contains no labels or teacher targets"},
        label_quality_recipe={**template["label_quality_recipe"], "label_recipe_version": "not_computed_current_inputs_only"},
        corporate_action_basis={"status": "not_used_current_inputs_contain_no_outcomes"},
        dataset_purpose="current_inference_only", fold_boundaries=[], fold_policy={},
        latest_inference_row_policy="actual current capture date with causal T-1 events",
        capture_source_database=str(source), capture_started_at=started.isoformat(),
        verified_repair_symbols=verified_repair_symbols,
    )
    identity = canonical_hash({name: manifest[name] for name in _IDENTITY_FIELDS})
    manifest.update(dataset_id="ml-restated-research-" + identity[7:31], dataset_identity_hash=identity, manifest_hash=identity)
    path = run / "manifest.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    return path, sha256_file(path)
