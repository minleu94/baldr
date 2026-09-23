"""讀取已封存的修訂資料當日列；僅在 prepare 階段執行明示 I/O。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from ml_module.allocation_contracts import (
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
    post_freeze_shadow_decision_scope,
)
from ml_module.restated_research_input_contract import (
    RestatedResearchInputBinding,
    research_rows_hash,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_SOURCE_ID = "sealed_restated_research_dataset"
_IDENTITY_FIELDS = (
    "schema_version", "source_hashes", "feature_ids", "feature_scales",
    "feature_order_hash", "kernel", "builder_code_sha256", "label_quality_recipe",
    "restated_research", "formal_historical_PIT", "training_as_of",
    "revision_observed_at", "row_count", "partition_files", "date_filter", "symbol_filter",
)
_COLUMNS = (
    "row_id", "symbol", "decision_date", "stock_event_date", "market_event_date",
    "feature_event_asof_at", "feature_available_at", "revision_observed_at",
    "source_revision_id", "feature_lineage_hash", "features_scaled_i64", "feature_missing_mask",
)


def _payload_hash(payload: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _aware(value: str, field: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} requires timezone")
    return parsed.astimezone(_TAIPEI)


@dataclass(frozen=True)
class PreparedRestatedCurrentInputs:
    """所有內容皆為不可變值；infer 不再讀取檔案或 latest pointer。"""

    rows: tuple[PortfolioMLDatasetRow, ...]
    binding: RestatedResearchInputBinding
    source_row_ids: tuple[str, ...]
    consumed_partitions: tuple[tuple[str, str, int], ...]
    dataset_manifest_path: str
    feature_asof_date: str

    def receipt(self) -> dict[str, object]:
        return {
            **self.binding.to_dict(),
            "binding_hash": self.binding.binding_hash,
            "dataset_manifest_path": self.dataset_manifest_path,
            "source_row_ids": list(self.source_row_ids),
            "consumed_partitions": [
                {"path": path, "file_sha256": digest, "byte_count": size}
                for path, digest, size in self.consumed_partitions
            ],
            "row_count": len(self.rows),
            "symbols": [row.symbol for row in self.rows],
            "feature_asof_date": self.feature_asof_date,
            "portfolio_state_semantics": "neutral cash-only research state; not user holdings",
        }


def prepare_restated_current_inputs(
    *,
    manifest_path: Path,
    expected_manifest_file_hash: str,
    symbols: Sequence[str],
    captured_at: datetime,
) -> PreparedRestatedCurrentInputs:
    """驗證封存來源後，只解碼當日指定股票與必要特徵欄位。

    呼叫端注入實際 capture 時鐘。來源日期不符時拒絕推論；不自動退回
    昨日列，更不把最新資料塞回某個歷史決策鐘。
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from data_module.ml_restatement_research_dataset import expected_feature_contract

    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("capture timestamp requires timezone")
    capture = captured_at.astimezone(_TAIPEI)
    decision_date = capture.date()
    if not symbols or len(symbols) > 250:
        raise ValueError("current research requires 1..250 explicit symbols")
    selected_symbols = tuple(sorted(symbols))
    if len(set(selected_symbols)) != len(selected_symbols) or any(
        not isinstance(symbol, str) or not symbol or symbol.strip() != symbol
        for symbol in selected_symbols
    ):
        raise ValueError("symbols must be unique nonempty strings")
    manifest_path = manifest_path.resolve(strict=True)
    raw = manifest_path.read_bytes()
    manifest_hash = _bytes_hash(raw)
    if manifest_hash != expected_manifest_file_hash:
        raise ValueError("research manifest file hash mismatch")
    manifest = json.loads(raw)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "portfolio-ml-restated-research-dataset.v1"
        or manifest.get("status") != "complete_research_build"
        or manifest.get("research_only") is not True
        or manifest.get("restated_research") is not True
        or manifest.get("formal_historical_PIT") is not False
        or manifest.get("promotion_eligible") is not False
    ):
        raise ValueError("completed restated research manifest is required")
    identity = _payload_hash({name: manifest[name] for name in _IDENTITY_FIELDS})
    if manifest.get("dataset_identity_hash") != identity or manifest.get("manifest_hash") != identity:
        raise ValueError("research manifest content identity mismatch")
    if manifest.get("dataset_id") != "ml-restated-research-" + identity[7:31]:
        raise ValueError("research dataset id mismatch")
    features, scales = expected_feature_contract()
    if tuple(manifest["feature_ids"]) != features or tuple(manifest["feature_scales"]) != scales:
        raise ValueError("research current feature order/scales differ from the 62-slot ABI")
    if manifest["feature_order_hash"] != _payload_hash(list(zip(features, scales))):
        raise ValueError("research current feature order hash mismatch")
    revision_clock = _aware(manifest["revision_observed_at"], "revision_observed_at")
    if revision_clock > capture:
        raise ValueError("research source was not available at capture")
    sessions = tuple(date.fromisoformat(value) for value in manifest["observed_session_dates"])
    if not sessions or tuple(sorted(set(sessions))) != sessions:
        raise ValueError("research observed sessions must be sorted and unique")
    previous_sessions = tuple(day for day in sessions if day < decision_date)
    if not previous_sessions:
        raise ValueError("research source has no T-1 market session")
    feature_day = previous_sessions[-1]
    if (decision_date - feature_day).days > 7:
        raise ValueError("research market snapshot is stale")
    families: dict[str, str] = {}
    packed_features: list[str] = []
    for pack in manifest["feature_packs"]:
        pack_id = str(pack["pack_id"])
        for feature_id in pack["feature_ids"]:
            if feature_id in families:
                raise ValueError("research feature pack contains duplicate feature")
            families[feature_id] = pack_id
            packed_features.append(feature_id)
    if tuple(packed_features) != features:
        raise ValueError("research feature packs differ from the ordered contract")
    source_pairs = tuple((str(name), str(digest)) for name, digest in manifest["source_manifest_hashes"])
    if len(dict(source_pairs)) != len(source_pairs) or _SOURCE_ID in dict(source_pairs):
        raise ValueError("research source ids must be unique")
    source_pairs = tuple(sorted((*source_pairs, (_SOURCE_ID, manifest_hash))))
    root = manifest_path.parent
    records: list[dict[str, Any]] = []
    consumed: list[tuple[str, str, int]] = []
    paths_seen: set[Path] = set()
    for partition in manifest["partition_files"]:
        if int(partition["year"]) != decision_date.year:
            continue
        path = (root / partition["path"]).resolve(strict=True)
        if not path.is_relative_to(root) or path in paths_seen:
            raise ValueError("research partition escapes the root or repeats a path")
        paths_seen.add(path)
        with path.open("rb") as stream:
            def stream_hash() -> str:
                stream.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                return "sha256:" + digest.hexdigest()

            if stream_hash() != partition["file_sha256"] or stream.tell() != partition["byte_count"]:
                raise ValueError("research partition hash or size mismatch")
            stream.seek(0)
            parquet = pq.ParquetFile(stream)
            if parquet.metadata.num_rows != partition["row_count"]:
                raise ValueError("research partition row count mismatch")
            schema = parquet.schema_arrow
            if (
                schema.field("features_scaled_i64").type != pa.list_(pa.int64(), 62)
                or schema.field("feature_missing_mask").type != pa.list_(pa.uint8(), 62)
                or schema.field("decision_date").type != pa.date32()
            ):
                raise ValueError("research partition feature wire schema mismatch")
            date_column = parquet.schema.names.index("decision_date")
            for group_index in range(parquet.num_row_groups):
                stats = parquet.metadata.row_group(group_index).column(date_column).statistics
                if stats is not None and stats.has_min_max and not stats.min <= decision_date <= stats.max:
                    continue
                table = parquet.read_row_group(group_index, columns=list(_COLUMNS))
                match = pc.and_(
                    pc.equal(table["decision_date"], pa.scalar(decision_date, type=pa.date32())),
                    pc.is_in(table["symbol"], value_set=pa.array(selected_symbols)),
                )
                records.extend(table.filter(match).to_pylist())
            if stream_hash() != partition["file_sha256"]:
                raise ValueError("research partition changed during preparation")
        consumed.append((str(path), partition["file_sha256"], partition["byte_count"]))
    if sorted(row["symbol"] for row in records) != list(selected_symbols):
        raise ValueError("research dataset lacks exact current symbols or contains duplicate rows")
    records.sort(key=lambda row: row["symbol"])
    state = CausalPortfolioState.create(
        as_of_date=feature_day.isoformat(),
        weights=AllocationWeightContract(positions_bp=(), cash_bp=10_000),
        weekly_turnover_used_bp=0,
    )
    prepared_rows: list[PortfolioMLDatasetRow] = []
    with post_freeze_shadow_decision_scope():
        for record in records:
            symbol = record["symbol"]
            if record["row_id"] != f"row:{decision_date.isoformat()}:{symbol}":
                raise ValueError("research row key does not match date/symbol")
            if record["market_event_date"] != feature_day:
                raise ValueError("research market event does not match the latest prior session")
            stock_day = record["stock_event_date"]
            if not isinstance(stock_day, date) or not stock_day <= feature_day < decision_date:
                raise ValueError("research stock event is not T-1 or earlier")
            event = _aware(record["feature_event_asof_at"], "feature_event_asof_at")
            available = _aware(record["feature_available_at"], "feature_available_at")
            observed = _aware(record["revision_observed_at"], "revision_observed_at")
            if event.date() >= decision_date or event > available or available > capture or observed != revision_clock or available < observed:
                raise ValueError("research feature event/availability/revision clocks are inconsistent")
            values = record["features_scaled_i64"]
            masks = record["feature_missing_mask"]
            if len(values) != 62 or len(masks) != 62:
                raise ValueError("research feature width mismatch")
            feature_values: list[PITFeatureValue] = []
            missing: set[str] = set()
            for feature_id, scale, value, mask in zip(features, scales, values, masks):
                if mask not in (0, 1) or (value is None) != (mask == 1):
                    raise ValueError("research feature null and missing mask disagree")
                if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                    raise ValueError("research observed feature must remain int64")
                family = families[feature_id]
                if mask:
                    missing.add(family)
                feature_values.append(PITFeatureValue(
                    feature_id=feature_id, family_id=family, source_id=_SOURCE_ID,
                    value_int=value, scale=scale, event_at=event.isoformat(),
                    available_at=available.isoformat(), revision_id=record["source_revision_id"],
                    quality="missing" if mask else "observed", observed=not bool(mask),
                    content_hash=_payload_hash({
                        "row_id": record["row_id"], "feature_id": feature_id,
                        "value_int": value, "scale": scale,
                        "revision_id": record["source_revision_id"],
                        "lineage_hash": record["feature_lineage_hash"],
                    }),
                ))
            prepared_rows.append(PortfolioMLDatasetRow(
                row_id=f"row:post-freeze-shadow:{decision_date.isoformat()}:{symbol}",
                decision_at=capture.isoformat(timespec="microseconds"), symbol=symbol,
                features=tuple(feature_values), missing_family_ids=tuple(sorted(missing)),
                portfolio_state=state, dataset_identity_hash=identity,
                feature_registry_hash=manifest["feature_registry_hash"],
                source_manifest_hashes=source_pairs, targets=None,
            ))
    rows = tuple(prepared_rows)
    binding = RestatedResearchInputBinding(
        dataset_id=manifest["dataset_id"], dataset_identity_hash=identity,
        dataset_manifest_file_hash=manifest_hash,
        feature_registry_hash=manifest["feature_registry_hash"],
        source_manifest_hashes=source_pairs, ordered_features=tuple(zip(features, scales)),
        prepared_rows_hash=research_rows_hash(rows), captured_at=capture.isoformat(timespec="microseconds"),
    )
    return PreparedRestatedCurrentInputs(
        rows=rows, binding=binding, source_row_ids=tuple(record["row_id"] for record in records),
        consumed_partitions=tuple(consumed), dataset_manifest_path=str(manifest_path),
        feature_asof_date=feature_day.isoformat(),
    )
