from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_module.ml_restatement_current_inputs import (
    PreparedRestatedCurrentInputs,
    _IDENTITY_FIELDS,
    _payload_hash,
    prepare_restated_current_inputs,
)
from data_module.ml_restatement_research_dataset import expected_feature_contract
from ml_module.restated_research_input_contract import RestatedResearchInputBinding


_DAY = date(2026, 9, 23)
_EVENT_DAY = date(2026, 9, 22)
_CAPTURE = datetime.fromisoformat("2026-09-23T13:00:00+08:00")
_REVISION = "2026-09-23T12:00:00+08:00"
_HASH = "sha256:" + "a" * 64


def _fixture_dataset(root: Path, *, bad_mask: bool = False, revision: str = _REVISION) -> tuple[Path, str]:
    root.mkdir()
    features, scales = expected_feature_contract()
    values: list[int | None] = [0] * 62
    values[11] = None
    masks = [0] * 62
    masks[11] = 0 if bad_mask else 1
    schema = pa.schema([
        ("row_id", pa.string()), ("symbol", pa.string()), ("decision_date", pa.date32()),
        ("stock_event_date", pa.date32()), ("market_event_date", pa.date32()),
        ("feature_event_asof_at", pa.string()), ("feature_available_at", pa.string()),
        ("revision_observed_at", pa.string()), ("source_revision_id", pa.string()),
        ("feature_lineage_hash", pa.string()),
        ("features_scaled_i64", pa.list_(pa.int64(), 62)),
        ("feature_missing_mask", pa.list_(pa.uint8(), 62)),
    ])
    records = [{
        "row_id": f"row:{_DAY}:{symbol}", "symbol": symbol, "decision_date": _DAY,
        "stock_event_date": _EVENT_DAY, "market_event_date": _EVENT_DAY,
        "feature_event_asof_at": "2026-09-22T14:30:00+08:00",
        "feature_available_at": revision, "revision_observed_at": revision,
        "source_revision_id": "corrected-20260923", "feature_lineage_hash": _HASH,
        "features_scaled_i64": values, "feature_missing_mask": masks,
    } for symbol in ("1256", "1477")]
    partition = root / "research.parquet"
    pq.write_table(pa.Table.from_pylist(records, schema=schema), partition)
    manifest = {
        "schema_version": "portfolio-ml-restated-research-dataset.v1",
        "source_hashes": {"snapshot": _HASH},
        "feature_ids": features, "feature_scales": scales,
        "feature_order_hash": _payload_hash(list(zip(features, scales))),
        "kernel": {"sha256": _HASH}, "builder_code_sha256": _HASH,
        "label_quality_recipe": {}, "restated_research": True,
        "formal_historical_PIT": False, "training_as_of": revision,
        "revision_observed_at": revision, "row_count": 2,
        "partition_files": [{
            "path": partition.name, "year": 2026, "row_count": 2,
            "file_sha256": "sha256:" + hashlib.sha256(partition.read_bytes()).hexdigest(),
            "byte_count": partition.stat().st_size,
        }],
        "date_filter": {}, "symbol_filter": ["1256", "1477"],
        "status": "complete_research_build", "research_only": True, "promotion_eligible": False,
        "feature_registry_hash": _HASH,
        "feature_packs": [{"pack_id": "price", "feature_ids": features}],
        "observed_session_dates": [_EVENT_DAY.isoformat()],
        "source_manifest_hashes": [["snapshot", _HASH]],
    }
    identity = _payload_hash({key: manifest[key] for key in _IDENTITY_FIELDS})
    manifest.update(dataset_identity_hash=identity, manifest_hash=identity, dataset_id="ml-restated-research-" + identity[7:31])
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_prepare_preserves_zero_missing_and_only_requested_symbols(tmp_path: Path) -> None:
    manifest, digest = _fixture_dataset(tmp_path / "data")
    prepared = prepare_restated_current_inputs(
        manifest_path=manifest, expected_manifest_file_hash=digest,
        symbols=("1477",), captured_at=_CAPTURE,
    )
    assert tuple(row.symbol for row in prepared.rows) == ("1477",)
    row = prepared.rows[0]
    assert row.features[0].value_int == 0 and row.features[0].observed
    assert row.features[11].value_int is None and not row.features[11].observed
    assert row.targets is None
    assert row.decision_at == _CAPTURE.isoformat(timespec="microseconds")
    assert prepared.feature_asof_date == "2026-09-22"
    assert prepared.receipt()["historical_pit"] is False


def test_prepared_inputs_require_a_binding_instance_but_keep_subclass_compatibility(
    tmp_path: Path,
) -> None:
    manifest, digest = _fixture_dataset(tmp_path / "data")
    prepared = prepare_restated_current_inputs(
        manifest_path=manifest,
        expected_manifest_file_hash=digest,
        symbols=("1256",),
        captured_at=_CAPTURE,
    )

    class CompatibleBinding(RestatedResearchInputBinding):
        pass

    compatible_binding = CompatibleBinding(**vars(prepared.binding))
    compatible = replace(prepared, binding=compatible_binding)
    assert isinstance(compatible, PreparedRestatedCurrentInputs)
    assert compatible.binding is compatible_binding

    with pytest.raises(TypeError, match="require a RestatedResearchInputBinding"):
        replace(prepared, binding=cast(Any, object()))


@pytest.mark.parametrize("failure", ["manifest_hash", "partition_hash", "missing_symbol", "wrong_day", "future_revision", "mask"])
def test_current_prepare_rejects_untrustworthy_inputs(tmp_path: Path, failure: str) -> None:
    manifest, digest = _fixture_dataset(
        tmp_path / "data", bad_mask=failure == "mask",
        revision="2026-09-23T14:00:00+08:00" if failure == "future_revision" else _REVISION,
    )
    if failure == "partition_hash":
        with (manifest.parent / "research.parquet").open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises(ValueError):
        prepare_restated_current_inputs(
            manifest_path=manifest,
            expected_manifest_file_hash=_HASH if failure == "manifest_hash" else digest,
            symbols=("2330",) if failure == "missing_symbol" else ("1256",),
            captured_at=datetime.fromisoformat("2026-09-24T13:00:00+08:00") if failure == "wrong_day" else _CAPTURE,
        )
