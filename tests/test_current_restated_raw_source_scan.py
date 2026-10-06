from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal

import pytest

import ml_module.current_restated_research_bridge as research_bridge
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.portfolio_ml_current_restated_outcome_store import (
    CurrentRestatedOutcomeFeatureV1,
)


def _research_resolver_for(repository: Path) -> Callable[..., Path]:
    def resolve(
        path: Path | str,
        *,
        access: Literal["read", "write"] = "read",
    ) -> Path:
        return resolve_ml_research_output_path(
            path,
            repository_root=repository,
            access=access,
        )

    return resolve


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _build_fixture(
    tmp_path: Path,
    *,
    unrelated_rows: int = 0,
    benchmark_dates: tuple[date, ...] | None = None,
    declared_rows: int | None = None,
    manifest_rows: int | None = None,
    benchmark_year_override: int | None = None,
) -> tuple[Any, tuple[date, ...], Path]:
    repository = tmp_path / "fixture-repository"
    run_root = repository / "output" / "ml_research" / "raw-scan-fixture"
    raw_root = run_root / "core_long_history"
    raw_root.mkdir(parents=True)

    dates = tuple(date(2026, 1, 5) + timedelta(days=index) for index in range(4))
    selected_benchmark_dates = benchmark_dates or dates
    context_sha = "sha256:" + _digest(b"fixture source context")
    source_observed = datetime(2026, 10, 3, 0, 23, tzinfo=timezone.utc)
    current_available = datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)
    source_ids = ("market_indices.close_index", "market_indices.close_alias")
    market_close_ids = tuple(f"benchmark/{source_id}" for source_id in source_ids)
    direct_registry = {
        stable_id: CurrentRestatedOutcomeFeatureV1(
            feature_id=stable_id,
            source_feature_id=source_id,
            source_table="market_indices",
            role="benchmark",
            unit="index_1e4",
            decimal_exponent=4,
            eligibility_status="formal_backfill",
        )
        for stable_id, source_id in zip(market_close_ids, source_ids, strict=True)
    }
    raw_feature_registry = [
        {
            "feature_id": source_id,
            "source_id": "sqlite.market_indices",
            "table_name": "market_indices",
            "unit": "index_1e4",
            "scale": 4,
        }
        for source_id in source_ids
    ]

    def benchmark_row(index: int, event_date: date) -> dict[str, Any]:
        if benchmark_year_override is not None and index == 0:
            event_date = date(benchmark_year_override, 12, 31)
        row_sha = "sha256:" + _digest(f"market-row-{index}".encode("ascii"))
        value_int = 100_000 + index * 1_000
        return {
            "source_table": "market_indices",
            "source_id": "sqlite.market_indices",
            "entity_id": "TAIEX",
            "event_date": event_date.isoformat(),
            "source_row_hash": row_sha,
            "source_context_bundle_sha256": context_sha,
            "source_observed_at": source_observed.isoformat(),
            "current_value_available_at": current_available.isoformat(),
            "current_restated": True,
            "event_reference_only": True,
            "source_available_at": None,
            "historical_pit_eligible": False,
            "formal_training_eligible": False,
            "values": [
                {
                    "feature_id": source_id,
                    "value_int": value_int,
                    "scale": 4,
                    "unit": "index_1e4",
                    "missing_mask": False,
                    "quality_blocked_mask": False,
                    "staleness_mask": False,
                }
                for source_id in source_ids
            ],
        }

    rows: list[dict[str, Any]] = [
        {
            "source_table": "industry_indices",
            "entity_id": f"industry-{index % 20}",
            "event_date": dates[index % len(dates)].isoformat(),
        }
        for index in range(unrelated_rows)
    ]
    rows.extend(
        benchmark_row(index, event_date)
        for index, event_date in enumerate(selected_benchmark_dates)
    )

    shard_path = raw_root / "year=2026.jsonl.gz"
    content_hash = hashlib.sha256()
    content_bytes = 0
    with shard_path.open("wb") as compressed_file:
        with gzip.GzipFile(fileobj=compressed_file, mode="wb", mtime=0) as stream:
            for row in rows:
                raw_line = json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8") + b"\n"
                stream.write(raw_line)
                content_hash.update(raw_line)
                content_bytes += len(raw_line)
    compressed_bytes = shard_path.read_bytes()
    shard_stat = shard_path.stat()
    actual_row_count = len(rows)
    declared_shard_rows = actual_row_count if declared_rows is None else declared_rows
    declared_dataset_rows = actual_row_count if manifest_rows is None else manifest_rows
    dataset_identity = "sha256:" + _digest(b"fixture dataset identity")
    dataset_manifest = {
        "schema_version": "ml-current-restated-year-shard-dataset.v1",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "manifest_hash": dataset_identity,
        "row_count": declared_dataset_rows,
        "source_context_bundle_sha256": context_sha,
        "features": raw_feature_registry,
        "shards": [
            {
                "year": 2026,
                "path": "core_long_history/year=2026.jsonl.gz",
                "compressed_bytes": len(compressed_bytes),
                "compressed_sha256": "sha256:" + _digest(compressed_bytes),
                "content_sha256": "sha256:" + content_hash.hexdigest(),
                "row_count": declared_shard_rows,
            }
        ],
    }
    dataset_path = raw_root / "manifest.json"
    dataset_bytes = json.dumps(
        dataset_manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    dataset_path.write_bytes(dataset_bytes)
    publication_manifest = {
        "schema_version": "ml-current-restated-year-shards.v1",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "source_context_bundle_sha256": context_sha,
        "datasets": {
            "core_long_history": {
                "manifest_path": "core_long_history/manifest.json",
                "manifest_hash": dataset_identity,
            }
        },
    }
    publication_path = run_root / "manifest.json"
    publication_bytes = json.dumps(
        publication_manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    publication_path.write_bytes(publication_bytes)
    artifact = SimpleNamespace(
        raw_publication_manifest_path=str(publication_path.resolve()),
        raw_publication_manifest_bytes_sha256=_digest(publication_bytes),
        raw_dataset_manifest_path=str(dataset_path.resolve()),
        raw_dataset_manifest_bytes_sha256=_digest(dataset_bytes),
        raw_shard_pins=(
            SimpleNamespace(
                role_id="raw_shard_year_2026",
                path=str(shard_path.resolve()),
                bytes=len(compressed_bytes),
                mtime_ns=shard_stat.st_mtime_ns,
                sha256=_digest(compressed_bytes),
                content_sha256="sha256:" + content_hash.hexdigest(),
                row_count=declared_shard_rows,
            ),
        ),
        benchmark_entity_id="TAIEX",
        source_observed_at=source_observed,
        current_observation_freeze=datetime(2026, 10, 3, 3, 20, tzinfo=timezone.utc),
    )
    artifact._fixture_content_bytes = content_bytes
    artifact._fixture_actual_rows = actual_row_count
    artifact._fixture_registry = direct_registry
    artifact._fixture_market_close_ids = market_close_ids
    return artifact, dates, repository


def _load(
    artifact: Any,
    calendar: tuple[date, ...],
    *,
    include_scan: bool = True,
) -> Any:
    return research_bridge._load_verified_current_restated_market_history(
        artifact=artifact,
        calendar_dates=calendar,
        registry_by_source=artifact._fixture_registry,
        market_close_ids=artifact._fixture_market_close_ids,
        include_scan=include_scan,
    )


def test_reader_streams_full_raw_row_inventory_above_old_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path, unrelated_rows=100_001)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )

    states, hashes, scan = _load(artifact, calendar)

    assert tuple(sorted(states)) == calendar
    assert set(hashes) == set(calendar)
    assert scan["actual_row_count"] == 100_005
    assert scan["declared_row_count"] == 100_005
    assert scan["dataset_manifest_declared_row_count"] == 100_005
    assert scan["benchmark_row_count"] == 4
    assert scan["decompressed_byte_count"] == artifact._fixture_content_bytes
    assert scan["maximum_raw_rows"] == 1_000_000
    assert scan["maximum_benchmark_rows"] == 100_000
    research_bridge._verify_current_restated_raw_source_scan(scan)

    over_semantic_limit = dict(scan)
    over_semantic_limit["benchmark_row_count"] = 100_001
    with pytest.raises(ValueError, match="resource metrics"):
        research_bridge._verify_current_restated_raw_source_scan(over_semantic_limit)

    tampered = dict(scan)
    tampered["actual_row_count"] = 100_004
    with pytest.raises(ValueError, match="resource metrics"):
        research_bridge._verify_current_restated_raw_source_scan(tampered)


@pytest.mark.parametrize("declared_rows", [3, 5])
def test_reader_rejects_declared_actual_row_count_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declared_rows: int,
) -> None:
    artifact, calendar, repository = _build_fixture(
        tmp_path,
        declared_rows=declared_rows,
        manifest_rows=declared_rows,
    )
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    with pytest.raises(ValueError, match="row count differs"):
        _load(artifact, calendar)


def test_reader_rejects_manifest_row_count_disagreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(
        tmp_path,
        declared_rows=4,
        manifest_rows=3,
    )
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    with pytest.raises(ValueError, match="row_count differs"):
        _load(artifact, calendar)


def test_reader_requires_publisher_dataset_row_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path)
    dataset_path = Path(artifact.raw_dataset_manifest_path)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    del dataset["row_count"]
    dataset_bytes = json.dumps(
        dataset, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    dataset_path.write_bytes(dataset_bytes)
    artifact.raw_dataset_manifest_bytes_sha256 = _digest(dataset_bytes)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    with pytest.raises(ValueError, match="declared row_count is invalid"):
        _load(artifact, calendar)


def test_reader_rejects_declared_row_count_over_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    monkeypatch.setattr(research_bridge, "_MAX_CURRENT_RESTATED_RAW_ROWS", 3)
    with pytest.raises(ValueError, match="declared row count exceeds its bound"):
        _load(artifact, calendar)


def test_reader_rejects_long_jsonl_row_before_unbounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    monkeypatch.setattr(research_bridge, "_MAX_CURRENT_RESTATED_RAW_ROW_BYTES", 32)
    with pytest.raises(ValueError, match="JSONL row exceeds its byte bound"):
        _load(artifact, calendar)


def test_reader_rejects_cumulative_decompressed_content_over_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path, unrelated_rows=20)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    monkeypatch.setattr(research_bridge, "_MAX_CURRENT_RESTATED_RAW_ROW_BYTES", 1_024)
    monkeypatch.setattr(
        research_bridge,
        "_MAX_CURRENT_RESTATED_RAW_DATASET_CONTENT_BYTES",
        1_500,
    )
    with pytest.raises(ValueError, match="dataset decompressed bytes exceed its bound"):
        _load(artifact, calendar)


def test_reader_rejects_wrong_content_hash_and_cross_year_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(tmp_path)
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    pin = artifact.raw_shard_pins[0]
    artifact.raw_shard_pins = (
        SimpleNamespace(
            **{
                **vars(pin),
                "content_sha256": "sha256:" + _digest(b"wrong content"),
            }
        ),
    )
    with pytest.raises(ValueError, match="differ from the verified loader pins"):
        _load(artifact, calendar)

    wrong_year_artifact, wrong_year_calendar, wrong_year_repo = _build_fixture(
        tmp_path / "wrong-year",
        benchmark_year_override=2025,
    )
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(wrong_year_repo),
    )
    with pytest.raises(ValueError, match="cross-year row"):
        _load(wrong_year_artifact, wrong_year_calendar)


def test_reader_rejects_duplicate_benchmark_dates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact, calendar, repository = _build_fixture(
        tmp_path,
        benchmark_dates=(
            date(2026, 1, 5),
            date(2026, 1, 5),
            date(2026, 1, 7),
            date(2026, 1, 8),
        ),
    )
    monkeypatch.setattr(
        research_bridge,
        "resolve_ml_research_output_path",
        _research_resolver_for(repository),
    )
    with pytest.raises(ValueError, match="repeat a TAIEX source date"):
        _load(artifact, calendar)
