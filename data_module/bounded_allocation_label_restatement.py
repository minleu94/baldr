"""為 bounded allocation 標籤建立封存的研究重述資料。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import gzip
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Mapping, Sequence, cast

from data_module.portfolio_ml_dataset_assembler import (
    _BUY_COST_BP,
    _SELL_COST_BP,
    _mae_loss_bp,
    _max_drawdown_bp,
    _mfe_gain_bp,
    _realized_volatility_bp,
    _return_bp,
    _t1_fill_feasible,
    _tail_loss_bp,
)


RESTATEMENT_SCHEMA = "bounded-allocation-label-restatement.v1"
PUBLICATION_SCHEMA = "portfolio-ml-training-shards.v2"
JSONL_SCHEMA = "allocation-training-jsonl-v2"
SOURCE_DATE = "20260520"
SOURCE_DATE_ISO = "2026-05-20"
PRICE_SCALE = 10_000
EXPECTED_AFFECTED_ROWS = 868
OUTCOME_FIELDS = (
    "benchmark_excess_return_bp",
    "downside_observed",
    "mae_bp",
    "mfe_bp",
    "realized_volatility_bp",
    "max_drawdown_bp",
    "tail_loss_bp",
    "fill_feasible_observed",
)
OHLC_COLUMNS = ("開盤價", "最高價", "最低價", "收盤價")
_GROUPED_DECIMAL = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")


class BoundedRestatementError(ValueError):
    """來源資料集或修復來源不符合資料契約。"""


def restate_bounded_training_publication(
    *,
    source_publication_dir: Path,
    source_snapshot_path: Path,
    repair_receipt_path: Path,
    output_directory: Path,
    expected_snapshot_sha256: str,
    revision_observed_at: str | None = None,
) -> dict[str, Any]:
    """將凍結樣本串流寫入新 lineage，只更新受影響的標籤。

    歷史標籤的 ``available_at`` 保留原成熟時鐘。``revision_observed_at``
    記錄較晚重建實際可用的時間，不會回填成來源日期。
    """

    source_dir = Path(source_publication_dir).resolve()
    snapshot_path = Path(source_snapshot_path).resolve()
    receipt_path = Path(repair_receipt_path).resolve()
    output_dir = Path(output_directory).resolve()
    if output_dir.exists():
        raise BoundedRestatementError(f"output directory already exists: {output_dir}")
    if output_dir == source_dir or output_dir.is_relative_to(source_dir):
        raise BoundedRestatementError("output must be outside the frozen publication")

    observed_at = _timestamp(
        revision_observed_at or datetime.now(timezone.utc).isoformat()
    )
    expected_snapshot_sha256 = _sha256_text(
        expected_snapshot_sha256, "expected_snapshot_sha256"
    )
    manifest_path = source_dir / "manifest.json"
    source_manifest = _read_json(manifest_path, "source manifest")
    _verify_publication_manifest(source_manifest)
    receipt = _read_json(receipt_path, "price repair receipt")
    receipt_body_sha256 = _verify_receipt(receipt)
    if receipt.get("schema_version") != "historical-price-spike-repair-20260921.v1":
        raise BoundedRestatementError("unsupported repair receipt schema")
    if receipt.get("source_date") != SOURCE_DATE:
        raise BoundedRestatementError("repair receipt source date mismatch")
    if receipt.get("allowlist_count") != EXPECTED_AFFECTED_ROWS:
        raise BoundedRestatementError("repair receipt allowlist count mismatch")
    if receipt.get("historical_decision_time_available") is not False:
        raise BoundedRestatementError("repair receipt must not claim historical PIT")

    actual_snapshot_sha256 = _file_sha256(snapshot_path)
    if actual_snapshot_sha256 != expected_snapshot_sha256:
        raise BoundedRestatementError(
            "snapshot hash mismatch: "
            f"expected={expected_snapshot_sha256}; actual={actual_snapshot_sha256}"
        )
    repair_rows = _repair_rows(receipt)
    affected_symbols = frozenset(repair_rows)
    shards = _source_shards(source_dir, source_manifest)
    headers = tuple(_read_header(path, entry, source_manifest) for path, entry in shards)
    _require_consistent_headers(headers, source_manifest)
    if headers[0].get("horizons") != [5, 10, 20, 60]:
        raise BoundedRestatementError("source horizons differ from 5/10/20/60")

    scan = _scan_publication(shards, source_manifest, affected_symbols)
    if scan["sample_count"] != int(source_manifest["sample_count"]):
        raise BoundedRestatementError("source aggregate sample count mismatch")
    if scan["non_cash_target_rows"]:
        raise BoundedRestatementError(
            "teacher targets are not cash-only; causal teacher replay is required"
        )
    if scan["h20_crossings"]:
        raise BoundedRestatementError(
            "an H20 teacher label crosses the repair date; target replay is required"
        )
    if not scan["crossings"]:
        raise BoundedRestatementError("no mature labels cross the repair date")

    with closing(_open_readonly_sqlite(snapshot_path)) as connection:
        _validate_snapshot_prices(connection, repair_rows)
        calendar, benchmark, prices = _load_prices(
            connection,
            symbols=affected_symbols & scan["symbols"],
            minimum_date=scan["min_decision_date"],
            maximum_date=scan["max_end_date"],
        )

    parent_identity = _sha256_text(
        str(source_manifest.get("dataset_identity_hash", "")),
        "source dataset_identity_hash",
    )
    identity_payload = {
        "schema_version": RESTATEMENT_SCHEMA,
        "parent_publication_id": source_manifest["publication_id"],
        "parent_publication_manifest_hash": source_manifest["manifest_hash"],
        "parent_dataset_identity_hash": parent_identity,
        "source_snapshot_sha256": actual_snapshot_sha256,
        "repair_receipt_sha256": receipt_body_sha256,
        "source_date": SOURCE_DATE_ISO,
        "revision_observed_at": observed_at,
        "training_as_of": observed_at,
        "label_recipe": "portfolio_ml_dataset_assembler_decimal_bp_v1",
        "scope": "bounded_matured_label_only",
    }
    identity_hash = _sha256_json(identity_payload)
    dataset_id = f"{source_manifest['dataset_id']}-restated-{identity_hash[7:19]}"
    source_hashes = _restate_source_hashes(
        source_manifest.get("source_manifest_hashes", ()),
        snapshot_hash=actual_snapshot_sha256,
        receipt_hash=receipt_body_sha256,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    stats = _WriteStats()
    try:
        new_shards = []
        for (source_path, source_entry), source_header in zip(
            shards, headers, strict=True
        ):
            output_path = staging / str(source_entry["path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            header = dict(source_header)
            header.update(
                {
                    "dataset_id": dataset_id,
                    "dataset_identity_hash": identity_hash,
                    "training_as_of": observed_at,
                    "source_manifest_hashes": [list(pair) for pair in source_hashes],
                    "research_only": True,
                    "formal_consumer_compatible": False,
                    "promotion_eligible": False,
                    "research_shadow_included": True,
                    "formal_source_only": False,
                }
            )
            shard_stats = _write_shard(
                source_path=source_path,
                expected_source_sha256=str(source_entry["compressed_sha256"]),
                output_path=output_path,
                header=header,
                affected_symbols=affected_symbols,
                repair_rows=repair_rows,
                calendar=calendar,
                benchmark=benchmark,
                prices=prices,
                dataset_identity_hash=identity_hash,
                source_manifest_hashes=source_hashes,
                stats=stats,
            )
            new_shards.append(
                {
                    "year": int(source_entry["year"]),
                    "path": output_path.relative_to(staging).as_posix(),
                    "format": "gzip_jsonl",
                    "schema_version": JSONL_SCHEMA,
                    "compressed_sha256": _file_sha256(output_path),
                    "content_sha256": shard_stats["content_sha256"],
                    "compressed_bytes": output_path.stat().st_size,
                    "sample_count": shard_stats["sample_count"],
                    "min_decision_date": source_entry["min_decision_date"],
                    "max_decision_date": source_entry["max_decision_date"],
                    "direct_training_input": True,
                }
            )

        if stats.sample_count != scan["sample_count"]:
            raise BoundedRestatementError("sample count changed during restatement")
        if dict(stats.changed_horizons) != dict(scan["crossings"]):
            raise BoundedRestatementError("not every crossing label was restated once")
        if stats.changed_horizons.get(20, 0):
            raise BoundedRestatementError("H20 outcomes changed; teacher targets are stale")
        if stats.non_cash_target_rows:
            raise BoundedRestatementError("teacher targets changed during output pass")
        stats.assert_preserved()

        manifest = dict(source_manifest)
        manifest.pop("manifest_hash", None)
        manifest.update(
            {
                "publication_id": _publication_id(
                    str(source_manifest["publication_id"]), identity_hash, new_shards
                ),
                "stage": "portfolio_ml_bounded_label_only_restatement",
                "dataset_temporality": "restated_research",
                "dataset_id": dataset_id,
                "dataset_identity_hash": identity_hash,
                "source_manifest_hashes": [list(pair) for pair in source_hashes],
                "training_as_of": observed_at,
                "sample_count": stats.sample_count,
                "shards": new_shards,
                "research_only": True,
                "formal_consumer_compatible": False,
                "formal_oos_allowed": False,
                "production_alpha_bp": 0,
                "production_action_allowed": False,
                "promotion_eligible": False,
                "research_shadow_included": True,
                "formal_source_only": False,
                "safety": {
                    **dict(source_manifest.get("safety", {})),
                    "historical_pit": False,
                    "source_revision_observed_at": observed_at,
                    "source_revision_availability_backfilled": False,
                    "sqlite_source_write": False,
                },
                "restatement": {
                    "schema_version": RESTATEMENT_SCHEMA,
                    "status": "completed_research_only",
                    "dataset_temporality": "restated_research",
                    "historical_pit": False,
                    "formal_training_allowed": False,
                    "source_date": SOURCE_DATE_ISO,
                    "source_correction_recorded_at": receipt["corrected_at"],
                    "revision_observed_at": observed_at,
                    "training_as_of": observed_at,
                    "source_snapshot_path": str(snapshot_path),
                    "source_snapshot_sha256": actual_snapshot_sha256,
                    "source_repair_receipt_path": str(receipt_path),
                    "source_repair_receipt_sha256": receipt_body_sha256,
                    "source_repair_receipt_file_sha256": _file_sha256(receipt_path),
                    "parent_publication_id": source_manifest["publication_id"],
                    "parent_publication_manifest_hash": source_manifest["manifest_hash"],
                    "parent_dataset_identity_hash": parent_identity,
                    "label_recipe": identity_payload["label_recipe"],
                    "changed_labels_by_horizon": dict(sorted(stats.changed_horizons.items())),
                    "changed_label_rows": stats.changed_labels,
                    "changed_outcome_fields": dict(sorted(stats.changed_fields.items())),
                    "teacher_target_audit": stats.teacher_target_payload(scan),
                    "preservation": stats.preservation_payload(),
                },
            }
        )
        manifest["manifest_hash"] = _sha256_json(manifest)
        _write_json(staging / "manifest.json", manifest)
        os.replace(staging, output_dir)
    except Exception as exc:
        raise BoundedRestatementError(
            f"restatement failed; incomplete staging retained at {staging}: {exc}"
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
        "changed_labels": stats.changed_labels,
        "changed_labels_by_horizon": dict(sorted(stats.changed_horizons.items())),
        "revision_observed_at": observed_at,
        "historical_pit": False,
        "production_action_allowed": False,
    }


class _WriteStats:
    def __init__(self) -> None:
        self.sample_count = 0
        self.changed_labels = 0
        self.changed_horizons: Counter[int] = Counter()
        self.changed_fields: Counter[str] = Counter()
        self.non_cash_target_rows = 0
        self.cash_only_target_rows = 0
        self.cash_distribution: Counter[int] = Counter()
        self.risky_budget_distribution: Counter[int] = Counter()
        self.max_positions = 0
        self.row_ids: set[str] = set()
        self.digests_before = {
            field: hashlib.sha256()
            for field in ("row_ids", "features", "targets", "state")
        }
        self.digests_after = {
            field: hashlib.sha256()
            for field in ("row_ids", "features", "targets", "state")
        }

    def observe_sample(self, sample: Mapping[str, Any]) -> None:
        row = _mapping(sample.get("row"), "sample.row")
        row_id = _required_text(row.get("row_id"), "sample.row.row_id")
        if row_id in self.row_ids:
            raise BoundedRestatementError(f"duplicate row id: {row_id}")
        self.row_ids.add(row_id)
        self.sample_count += 1
        payloads = {
            "row_ids": row_id,
            "features": _canonical_json(
                {
                    "row_id": row_id,
                    "features": row.get("features"),
                    "missing_family_ids": row.get("missing_family_ids"),
                }
            ),
            "targets": _canonical_json({"row_id": row_id, "targets": row.get("targets")}),
            "state": _canonical_json({"row_id": row_id, "portfolio_state": row.get("portfolio_state")}),
        }
        for key, payload in payloads.items():
            self.digests_before[key].update(payload.encode("utf-8") + b"\n")
        target = _mapping(row.get("targets"), "sample.row.targets")
        weight = _mapping(target.get("target_weights"), "target_weights")
        positions = weight.get("positions_bp")
        if not isinstance(positions, list):
            raise BoundedRestatementError("target positions must be an array")
        self.max_positions = max(self.max_positions, len(positions))
        self.non_cash_target_rows += int(bool(positions))
        self.cash_only_target_rows += int(not positions)
        self.cash_distribution[int(weight["cash_bp"])] += 1
        self.risky_budget_distribution[int(target["risky_budget_bp"])] += 1

    def observe_after_sample(self, sample: Mapping[str, Any]) -> None:
        row = _mapping(sample.get("row"), "sample.row")
        row_id = _required_text(row.get("row_id"), "sample.row.row_id")
        payloads = {
            "row_ids": row_id,
            "features": _canonical_json(
                {
                    "row_id": row_id,
                    "features": row.get("features"),
                    "missing_family_ids": row.get("missing_family_ids"),
                }
            ),
            "targets": _canonical_json({"row_id": row_id, "targets": row.get("targets")}),
            "state": _canonical_json({"row_id": row_id, "portfolio_state": row.get("portfolio_state")}),
        }
        for key, payload in payloads.items():
            self.digests_after[key].update(payload.encode("utf-8") + b"\n")

    def teacher_target_payload(self, scan: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "row_count": self.sample_count,
            "cash_only_rows": self.cash_only_target_rows,
            "non_cash_rows": self.non_cash_target_rows,
            "maximum_position_count": self.max_positions,
            "target_cash_bp_distribution": dict(sorted(self.cash_distribution.items())),
            "target_risky_budget_bp_distribution": dict(sorted(self.risky_budget_distribution.items())),
            "h20_horizon_end_max": scan["max_h20_end_date"],
            "h20_windows_crossing_source_date": scan["h20_crossings"],
            "teacher_target_recomputed": False,
            "reason": (
                "frozen targets are all cash-only; the original teacher's "
                "candidate gate requires accepted point-in-time sector membership"
            ),
        }

    def preservation_payload(self) -> dict[str, Any]:
        return {
            "row_count_preserved": self.sample_count,
            "unique_row_ids": len(self.row_ids),
            "row_ids_sha256_before": "sha256:" + self.digests_before["row_ids"].hexdigest(),
            "row_ids_sha256_after": "sha256:" + self.digests_after["row_ids"].hexdigest(),
            "features_and_masks_sha256_before": "sha256:" + self.digests_before["features"].hexdigest(),
            "features_and_masks_sha256_after": "sha256:" + self.digests_after["features"].hexdigest(),
            "teacher_targets_sha256_before": "sha256:" + self.digests_before["targets"].hexdigest(),
            "teacher_targets_sha256_after": "sha256:" + self.digests_after["targets"].hexdigest(),
            "portfolio_state_sha256_before": "sha256:" + self.digests_before["state"].hexdigest(),
            "portfolio_state_sha256_after": "sha256:" + self.digests_after["state"].hexdigest(),
        }

    def assert_preserved(self) -> None:
        for field in ("row_ids", "features", "targets", "state"):
            if self.digests_before[field].digest() != self.digests_after[field].digest():
                raise BoundedRestatementError(f"source preservation check failed: {field}")


def _scan_publication(
    shards: tuple[tuple[Path, Mapping[str, Any]], ...],
    manifest: Mapping[str, Any],
    affected_symbols: frozenset[str],
) -> dict[str, Any]:
    row_ids: set[str] = set()
    symbols: set[str] = set()
    min_decision = "99999999"
    max_end = "00000000"
    max_h20_end = ""
    h20_crossings = 0
    crossings: Counter[int] = Counter()
    sample_count = 0
    non_cash_target_rows = 0
    for path, entry in shards:
        content_digest = hashlib.sha256()
        shard_count = 0
        with gzip.open(path, "rb") as stream:
            for raw_line in stream:
                if not raw_line.strip():
                    continue
                content_digest.update(raw_line)
                record = json.loads(raw_line.decode("utf-8"))
                if record.get("record_type") == "header":
                    continue
                if record.get("record_type") != "sample":
                    raise BoundedRestatementError(f"invalid record in {path.name}")
                sample = _mapping(record.get("sample"), "sample")
                row = _mapping(sample.get("row"), "sample.row")
                row_id = _required_text(row.get("row_id"), "row_id")
                if row_id in row_ids:
                    raise BoundedRestatementError(f"duplicate row id: {row_id}")
                row_ids.add(row_id)
                sample_count += 1
                shard_count += 1
                decision = _date_key(_required_text(row.get("decision_at"), "decision_at")[:10])
                symbol = _normalize_symbol(row.get("symbol"))
                if symbol in affected_symbols:
                    symbols.add(symbol)
                    min_decision = min(min_decision, decision)
                labels = sample.get("horizon_labels")
                if not isinstance(labels, list):
                    raise BoundedRestatementError("horizon_labels must be an array")
                h20 = None
                for label in labels:
                    label_map = _mapping(label, "horizon_label")
                    horizon = int(label_map["horizon_trading_days"])
                    end = _date_key(_required_text(label_map.get("horizon_end_date"), "horizon_end_date"))
                    max_end = max(max_end, end)
                    if horizon == 20:
                        h20 = end
                        max_h20_end = max(max_h20_end, end)
                    if symbol in affected_symbols and decision <= SOURCE_DATE <= end:
                        crossings[horizon] += 1
                if h20 is not None and decision <= SOURCE_DATE <= h20:
                    h20_crossings += 1
                target = _mapping(row.get("targets"), "sample.row.targets")
                weight = _mapping(target.get("target_weights"), "target_weights")
                positions = weight.get("positions_bp")
                if not isinstance(positions, list):
                    raise BoundedRestatementError("target positions must be an array")
                non_cash_target_rows += int(bool(positions))
        if shard_count != int(entry["sample_count"]):
            raise BoundedRestatementError(f"source shard sample count mismatch: {path.name}")
        if "sha256:" + content_digest.hexdigest() != entry["content_sha256"]:
            raise BoundedRestatementError(f"source shard content hash mismatch: {path.name}")
    if sample_count != int(manifest["sample_count"]):
        raise BoundedRestatementError("source sample count mismatch")
    if min_decision == "99999999" or max_end == "00000000":
        raise BoundedRestatementError("bounded data has no affected-symbol labels")
    return {
        "sample_count": sample_count,
        "symbols": frozenset(symbols),
        "min_decision_date": min_decision,
        "max_end_date": max_end,
        "max_h20_end_date": max_h20_end,
        "h20_crossings": h20_crossings,
        "crossings": crossings,
        "non_cash_target_rows": non_cash_target_rows,
    }


def _write_shard(
    *,
    source_path: Path,
    expected_source_sha256: str,
    output_path: Path,
    header: Mapping[str, Any],
    affected_symbols: frozenset[str],
    repair_rows: Mapping[str, Mapping[str, Any]],
    calendar: list[str],
    benchmark: Mapping[str, Mapping[str, int | None]],
    prices: Mapping[str, Mapping[str, Mapping[str, int | None]]],
    dataset_identity_hash: str,
    source_manifest_hashes: tuple[tuple[str, str], ...],
    stats: _WriteStats,
) -> dict[str, Any]:
    if _file_sha256(source_path) != expected_source_sha256:
        raise BoundedRestatementError(f"source shard changed before copy: {source_path.name}")
    content_digest = hashlib.sha256()
    shard_count = 0
    with gzip.open(source_path, "rb") as input_stream, output_path.open("wb") as output_file:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output_file, compresslevel=6, mtime=0) as output_stream:
            header_written = False
            for raw_line in input_stream:
                if not raw_line.strip():
                    continue
                record = json.loads(raw_line.decode("utf-8"))
                if not header_written:
                    if record.get("record_type") != "header":
                        raise BoundedRestatementError("source header is not first")
                    record = dict(record)
                    record.update(header)
                    header_written = True
                else:
                    if record.get("record_type") != "sample":
                        raise BoundedRestatementError(f"invalid sample in {source_path.name}")
                    sample = dict(_mapping(record.get("sample"), "sample"))
                    row = dict(_mapping(sample.get("row"), "sample.row"))
                    stats.observe_sample(sample)
                    symbol = _normalize_symbol(row.get("symbol"))
                    decision = _date_key(_required_text(row.get("decision_at"), "decision_at")[:10])
                    labels_raw = sample.get("horizon_labels")
                    if not isinstance(labels_raw, list):
                        raise BoundedRestatementError("horizon_labels must be an array")
                    labels: list[dict[str, Any]] = []
                    for raw_label in labels_raw:
                        label = dict(_mapping(raw_label, "horizon_label"))
                        horizon = int(label["horizon_trading_days"])
                        end = _date_key(_required_text(label.get("horizon_end_date"), "horizon_end_date"))
                        if symbol in affected_symbols and decision <= SOURCE_DATE <= end:
                            before = {field: label[field] for field in OUTCOME_FIELDS}
                            after = _recompute_label(
                                symbol=symbol,
                                decision_date=decision,
                                end_date=end,
                                horizon=horizon,
                                calendar=calendar,
                                benchmark=benchmark,
                                price_path=prices.get(symbol, {}),
                            )
                            label.update(after)
                            changed = [field for field in OUTCOME_FIELDS if before[field] != label[field]]
                            if changed:
                                stats.changed_labels += 1
                                stats.changed_horizons[horizon] += 1
                                for field in changed:
                                    stats.changed_fields[field] += 1
                        labels.append(label)
                    sample["horizon_labels"] = labels
                    row["dataset_identity_hash"] = dataset_identity_hash
                    row["source_manifest_hashes"] = [list(pair) for pair in source_manifest_hashes]
                    sample["row"] = row
                    stats.observe_after_sample(sample)
                    record = {"record_type": "sample", "sample": sample}
                    shard_count += 1
                encoded = (_canonical_json(record) + "\n").encode("utf-8")
                output_stream.write(encoded)
                content_digest.update(encoded)
            output_stream.close()
            output_file.flush()
            os.fsync(output_file.fileno())
    if _file_sha256(source_path) != expected_source_sha256:
        raise BoundedRestatementError(f"source shard changed during copy: {source_path.name}")
    return {
        "sample_count": shard_count,
        "content_sha256": "sha256:" + content_digest.hexdigest(),
    }


def _recompute_label(
    *,
    symbol: str,
    decision_date: str,
    end_date: str,
    horizon: int,
    calendar: list[str],
    benchmark: Mapping[str, Mapping[str, int | None]],
    price_path: Mapping[str, Mapping[str, int | None]],
) -> dict[str, Any]:
    try:
        start_index = calendar.index(decision_date)
        end_index = calendar.index(end_date)
    except ValueError as exc:
        raise BoundedRestatementError(
            f"label dates are absent from TAIEX calendar: {symbol} {decision_date} {end_date}"
        ) from exc
    path_dates = calendar[start_index : end_index + 1]
    if end_index != start_index + horizon - 1 or len(path_dates) != horizon:
        raise BoundedRestatementError("label horizon calendar is inconsistent")
    stock_rows = [price_path.get(day) for day in path_dates]
    benchmark_rows = [benchmark.get(day) for day in path_dates]
    if any(row is None or not _bar_complete(row) for row in stock_rows):
        raise BoundedRestatementError(f"incomplete stock path: {symbol} {decision_date}..{end_date}")
    if any(row is None or not _bar_complete(row) for row in benchmark_rows):
        raise BoundedRestatementError(f"incomplete TAIEX path: {decision_date}..{end_date}")
    concrete_stock = [row for row in stock_rows if row is not None]
    concrete_benchmark = [row for row in benchmark_rows if row is not None]
    stock_calculation_rows = [
        _as_calculation_row(row) for row in concrete_stock
    ]
    benchmark_calculation_rows = [
        _as_calculation_row(row) for row in concrete_benchmark
    ]
    entry = stock_calculation_rows[0]
    stock_return = _return_bp(
        entry_int=int(entry["open_int"]),
        entry_scale=int(entry["open_scale"]),
        exit_int=int(stock_calculation_rows[-1]["close_int"]),
        exit_scale=int(stock_calculation_rows[-1]["close_scale"]),
    )
    benchmark_return = _return_bp(
        entry_int=int(benchmark_calculation_rows[0]["open_int"]),
        entry_scale=int(benchmark_calculation_rows[0]["open_scale"]),
        exit_int=int(benchmark_calculation_rows[-1]["close_int"]),
        exit_scale=int(benchmark_calculation_rows[-1]["close_scale"]),
    )
    excess = stock_return - benchmark_return - _BUY_COST_BP - _SELL_COST_BP
    return {
        "benchmark_excess_return_bp": excess,
        "downside_observed": excess < 0,
        "mae_bp": _mae_loss_bp(entry, stock_calculation_rows),
        "mfe_bp": _mfe_gain_bp(entry, stock_calculation_rows),
        "realized_volatility_bp": _realized_volatility_bp(stock_calculation_rows),
        "max_drawdown_bp": _max_drawdown_bp(stock_calculation_rows),
        "tail_loss_bp": _tail_loss_bp(stock_calculation_rows),
        "fill_feasible_observed": _t1_fill_feasible(entry),
    }


def _load_prices(
    connection: sqlite3.Connection,
    *,
    symbols: frozenset[str],
    minimum_date: str,
    maximum_date: str,
) -> tuple[list[str], dict[str, dict[str, int | None]], dict[str, dict[str, dict[str, int | None]]]]:
    if not symbols:
        raise BoundedRestatementError("bounded training contains no repaired symbols")
    calendar = [
        str(row[0])
        for row in connection.execute(
            "SELECT 日期 FROM market_indices "
            "WHERE 指數名稱='TAIEX' AND 日期 BETWEEN ? AND ? ORDER BY 日期",
            (minimum_date, maximum_date),
        )
    ]
    if SOURCE_DATE not in calendar:
        raise BoundedRestatementError("repair date is absent from TAIEX calendar")
    benchmark = {
        str(row["日期"]): _scaled_bar(row)
        for row in connection.execute(
            "SELECT 日期, 開盤價, 最高價, 最低價, 收盤價 FROM market_indices "
            "WHERE 指數名稱='TAIEX' AND 日期 BETWEEN ? AND ?",
            (minimum_date, maximum_date),
        )
    }
    prices: dict[str, dict[str, dict[str, int | None]]] = {}
    for symbol in sorted(symbols):
        prices[symbol] = {
            str(row["日期"]): _scaled_bar(row)
            for row in connection.execute(
                "SELECT 日期, 開盤價, 最高價, 最低價, 收盤價 FROM daily_prices "
                "WHERE 證券代號=? AND 日期 BETWEEN ? AND ? ORDER BY 日期",
                (symbol, minimum_date, maximum_date),
            )
        }
    return calendar, benchmark, prices


def _scaled_bar(row: Mapping[str, Any]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for field, column in (
        ("open_int", "開盤價"),
        ("high_int", "最高價"),
        ("low_int", "最低價"),
        ("close_int", "收盤價"),
    ):
        value = row[column]
        if value is None:
            result[field] = None
            scale = PRICE_SCALE
        else:
            text = str(value).strip()
            if text == "--":
                result[field] = None
                scale = PRICE_SCALE
                result[field.replace("_int", "_scale")] = scale
                continue
            if "," in text:
                if not _GROUPED_DECIMAL.fullmatch(text):
                    raise BoundedRestatementError(
                        f"invalid grouped source price: {column}={value!r}"
                    )
                text = text.replace(",", "")
            decimal_value = _decimal(text, column)
            exponent = decimal_value.as_tuple().exponent
            if isinstance(exponent, bool) or not isinstance(exponent, int):
                raise BoundedRestatementError(
                    f"source price exponent is not finite: {column}={value!r}"
                )
            source_precision = max(0, -exponent)
            if source_precision > 12:
                raise BoundedRestatementError(
                    f"source price precision exceeds 12 decimal places: {column}={value!r}"
                )
            scale = max(PRICE_SCALE, 10**source_precision)
            scaled = decimal_value * scale
            integral = scaled.to_integral_value(rounding=ROUND_HALF_EVEN)
            if scaled != integral:
                raise BoundedRestatementError(
                    f"source price has unsupported precision: {column}={value!r}"
                )
            result[field] = int(integral)
        result[field.replace("_int", "_scale")] = scale
    return result


def _bar_complete(bar: Mapping[str, int | None]) -> bool:
    for field in ("open_int", "high_int", "low_int", "close_int"):
        value = bar.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return False
    return True


def _as_calculation_row(bar: Mapping[str, int | None]) -> sqlite3.Row:
    """將已驗證的純 mapping 適配至既有欄位索引計算 helper。"""

    fields = (
        "open_int",
        "open_scale",
        "high_int",
        "high_scale",
        "low_int",
        "low_scale",
        "close_int",
        "close_scale",
    )
    values: dict[str, int] = {}
    for field in fields:
        value = bar.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise BoundedRestatementError(
                f"price calculation row has invalid {field}"
            )
        values[field] = value
    # 既有純計算 helper 只按欄名取值；此 cast 是型別邊界，不改其 frozen API。
    return cast(sqlite3.Row, values)


def _validate_snapshot_prices(
    connection: sqlite3.Connection,
    repair_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    observed = {
        _normalize_symbol(row["證券代號"]): row
        for row in connection.execute(
            "SELECT 證券代號, 開盤價, 最高價, 最低價, 收盤價 "
            "FROM daily_prices WHERE 日期=?",
            (SOURCE_DATE,),
        )
    }
    for symbol, record in repair_rows.items():
        row = observed.get(symbol)
        if row is None:
            raise BoundedRestatementError(f"snapshot missing source row: {symbol}")
        after = record["after"]
        for column in OHLC_COLUMNS:
            expected = after.get(column)
            actual = row[column]
            if expected is None:
                if actual is not None:
                    raise BoundedRestatementError(f"snapshot NULL mismatch: {symbol}.{column}")
            elif actual is None or _decimal(actual, f"{symbol}.{column}") != _decimal(
                expected, f"receipt.{symbol}.{column}"
            ):
                raise BoundedRestatementError(f"snapshot after value mismatch: {symbol}.{column}")


def _open_readonly_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise BoundedRestatementError("SQLite snapshot is not query-only")
    return connection


def _source_shards(
    source_dir: Path, manifest: Mapping[str, Any]
) -> tuple[tuple[Path, Mapping[str, Any]], ...]:
    entries = manifest.get("shards")
    if not isinstance(entries, list) or not entries:
        raise BoundedRestatementError("source shard list is empty")
    root = source_dir.resolve()
    result = []
    for entry in entries:
        record = _mapping(entry, "manifest shard")
        relative = _required_text(record.get("path"), "shard.path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise BoundedRestatementError("source shard path escapes publication")
        if record.get("format") != "gzip_jsonl" or record.get("schema_version") != JSONL_SCHEMA:
            raise BoundedRestatementError(f"unsupported source shard: {relative}")
        if _file_sha256(path) != record.get("compressed_sha256"):
            raise BoundedRestatementError(f"source shard hash mismatch: {relative}")
        result.append((path, record))
    return tuple(sorted(result, key=lambda item: int(item[1]["year"])))


def _read_header(
    path: Path, entry: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        header = json.loads(next(stream))
    if not isinstance(header, dict) or header.get("record_type") != "header":
        raise BoundedRestatementError(f"invalid JSONL header: {path.name}")
    for key in (
        "dataset_id", "dataset_identity_hash", "feature_registry_hash",
        "training_as_of", "horizons", "feature_packs", "folds",
        "source_manifest_hashes", "corporate_action_custody",
    ):
        if _canonical_json(header.get(key)) != _canonical_json(manifest.get(key)):
            raise BoundedRestatementError(f"header/manifest mismatch for {key}")
    if header.get("year") != entry.get("year"):
        raise BoundedRestatementError(f"shard year mismatch: {path.name}")
    return header


def _require_consistent_headers(
    headers: tuple[dict[str, Any], ...], manifest: Mapping[str, Any]
) -> None:
    if not headers:
        raise BoundedRestatementError("source headers are empty")
    if any(h.get("dataset_identity_hash") != manifest.get("dataset_identity_hash") for h in headers):
        raise BoundedRestatementError("source shard identities are inconsistent")


def _verify_publication_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != PUBLICATION_SCHEMA:
        raise BoundedRestatementError("unsupported source publication manifest")
    if manifest.get("direct_training_input") is not True:
        raise BoundedRestatementError("source manifest is not direct training input")
    if manifest.get("target_schema_version") != JSONL_SCHEMA:
        raise BoundedRestatementError("source training JSONL schema mismatch")
    body = dict(manifest)
    claimed = body.pop("manifest_hash", None)
    if claimed != _sha256_json(body):
        raise BoundedRestatementError("source publication manifest hash mismatch")


def _repair_rows(receipt: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = receipt.get("rows")
    if not isinstance(raw, list) or len(raw) != EXPECTED_AFFECTED_ROWS:
        raise BoundedRestatementError("repair receipt row count mismatch")
    rows: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        record = _mapping(item, "repair row")
        before = _mapping(record.get("before"), "repair before row")
        after = _mapping(record.get("after"), "repair after row")
        symbol = _normalize_symbol(after.get("證券代號"))
        if symbol in rows or _normalize_symbol(before.get("證券代號")) != symbol:
            raise BoundedRestatementError(f"invalid duplicate/mismatched repair symbol: {symbol}")
        rows[symbol] = record
    if len(rows) != EXPECTED_AFFECTED_ROWS:
        raise BoundedRestatementError("repair receipt symbol count mismatch")
    return rows


def _verify_receipt(receipt: Mapping[str, Any]) -> str:
    body = dict(receipt)
    claimed = body.pop("receipt_sha256", None)
    actual = "sha256:" + hashlib.sha256(
        (_canonical_json(body) + "\n").encode("utf-8")
    ).hexdigest()
    if claimed != actual:
        raise BoundedRestatementError("repair receipt body hash mismatch")
    return actual


def _restate_source_hashes(
    source_hashes: Any, *, snapshot_hash: str, receipt_hash: str
) -> tuple[tuple[str, str], ...]:
    if not isinstance(source_hashes, list):
        raise BoundedRestatementError("source manifest hashes must be an array")
    pairs: dict[str, str] = {}
    for pair in source_hashes:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise BoundedRestatementError("invalid source manifest hash pair")
        pairs[str(pair[0])] = _sha256_text(str(pair[1]), f"source {pair[0]} hash")
    pairs["sidecar:historical_price_repair_receipt"] = receipt_hash
    pairs["sqlite.snapshot.twstock_snapshot_run02"] = snapshot_hash
    return tuple(sorted(pairs.items()))


def _publication_id(
    parent: str,
    identity_hash: str,
    shards: Sequence[Mapping[str, Any]],
) -> str:
    identity = {
        "parent_publication_id": parent,
        "dataset_identity_hash": identity_hash,
        "shards": [
            {"year": row["year"], "content_sha256": row["content_sha256"]}
            for row in shards
        ],
    }
    return "portfolio-ml-restated-" + _sha256_json(identity)[7:31]


def _manifest_shard_entry(
    *, path: Path, staging: Path, source: Mapping[str, Any], content_hash: str
) -> dict[str, Any]:
    return {
        "year": int(source["year"]),
        "path": path.relative_to(staging).as_posix(),
        "format": "gzip_jsonl",
        "schema_version": JSONL_SCHEMA,
        "compressed_sha256": _file_sha256(path),
        "content_sha256": content_hash,
        "compressed_bytes": path.stat().st_size,
        "sample_count": int(source["sample_count"]),
        "min_decision_date": source["min_decision_date"],
        "max_decision_date": source["max_decision_date"],
        "direct_training_input": True,
    }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BoundedRestatementError(f"{label} is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundedRestatementError(f"cannot read {label}: {path}") from exc
    return dict(_mapping(payload, label))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise BoundedRestatementError(f"{field} must be a non-null decimal")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BoundedRestatementError(f"{field} is not a decimal") from exc
    if not number.is_finite():
        raise BoundedRestatementError(f"{field} must be finite")
    return number


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BoundedRestatementError("revision_observed_at must be ISO datetime") from exc
    if parsed.tzinfo is None:
        raise BoundedRestatementError("revision_observed_at must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _date_key(value: str) -> str:
    normalized = value.replace("-", "")
    if len(normalized) != 8 or not normalized.isdigit():
        raise BoundedRestatementError(f"invalid date: {value}")
    return normalized


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise BoundedRestatementError("symbol must be text/integer")
    result = str(value).strip()
    return result.zfill(4) if result.isdigit() else result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BoundedRestatementError(f"{field} must be an object")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoundedRestatementError(f"{field} must be non-empty text")
    return value


def _sha256_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise BoundedRestatementError(f"{field} must be sha256:<64 hex>")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise BoundedRestatementError(f"{field} must be sha256:<64 hex>") from exc
    return value
