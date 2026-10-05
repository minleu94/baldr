from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.stock_research_report_dtos import (
    ReportFreshness,
    StockFundamentalObservationDTO,
    StockPricePointDTO,
    StockReportSourceDTO,
)
from app_module.stock_research_report_provider_adapters import (
    CurrentRestatedMLRegistryError,
    CurrentRestatedMLRunRegistry,
    PortfolioExitReadProvider,
    _validate_prediction_payload,
    stock_price_row_fingerprint_sha256,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from ui_qt.views.stock_research_report_view import (
    _coverage_status_label,
    _fundamental_basis_tooltip,
    _metric_text,
    _quality_label,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_NOW = datetime(2026, 10, 4, 14, 0, tzinfo=_TAIPEI)
_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _price_fingerprint(data_date: str = "2026-10-02", stock_code: str = "1477") -> str:
    return stock_price_row_fingerprint_sha256(
        stock_code=stock_code,
        data_date=data_date,
        open_price=Decimal("54.0"),
        high_price=Decimal("56.0"),
        low_price=Decimal("53"),
        close_price=Decimal("55.00"),
        volume=1200,
        turnover=Decimal("66000.0"),
    )


def _service(**kwargs: object) -> StockResearchReportReadService:
    config = SimpleNamespace(db_file=None, sqlite_db_file=None, output_root=None)
    return StockResearchReportReadService(config, clock=lambda: _NOW, **kwargs)


def _ml_candidate(**overrides: object) -> dict[str, object]:
    fingerprint = _price_fingerprint()
    key = "final|CORE19|h5|ridge_logistic"
    value: dict[str, object] = {
        "stock_code": "1477",
        "status": "research_prediction_only",
        "scope_mode": "current_stock_research",
        "model_version": "current-restated-core19:12345678",
        "dataset_version": _SHA_A,
        "inference_at": "2026-10-04T05:00:00+00:00",
        "available_at": "2026-10-04T05:01:00+00:00",
        "model_available_at": "2026-10-04T04:00:00+00:00",
        "research_or_formal": "research_only",
        "source_id": "current_restated_ml_run:20261002-run",
        "run_id": "20261002-run",
        "cycle_id": "20261002-cycle",
        "event_date": "2026-10-02",
        "model_manifest_sha256": _SHA_A,
        "model_bundle_sha256": _SHA_B,
        "source_snapshot_hash": "c" * 64,
        "current_price_row_fingerprint_sha256": fingerprint,
        "target_metric": "benchmark_excess_after_standard_80bp_cost",
        "predicted_benchmark_excess_return_bp": {key: 125},
        "prediction_keys": (key,),
        "input_quality_summary": {"usable_feature_count": 10},
        "context_identity": {},
        "scope_symbols": ("1225", "1477"),
        "h5": {
            "status": "not_mature",
            "horizon": 5,
            "gross_stock_return_bp": None,
            "gross_benchmark_return_bp": None,
            "benchmark_excess_after_standard_80bp_cost": None,
            "after_lane_cost_stock_return_bp": None,
            "next_entry_date": None,
            "horizon_end_date": None,
            "round_trip_cost": None,
            "price_inputs": None,
        },
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_qualified": False,
        "production_action_allowed": False,
    }
    value.update(overrides)
    return value


def test_market_not_applicable_and_unverified_basis_have_explicit_ui_labels() -> None:
    source = StockReportSourceDTO(
        source_id="official.current_valuation.tpex",
        source_label="official current valuation (tpex)",
        status="not_applicable",
        quality="observed",
        row_count=0,
        coverage_status="ready",
    )
    assert "不適用" in _quality_label(source.status)
    assert "市場來源已完成" == _coverage_status_label(source.coverage_status)

    metric = StockFundamentalObservationDTO(
        kind="statement_item",
        label="營收",
        period="2026-Q2",
        value=Decimal("900"),
        unit="TWD",
        period_basis="unknown",
        basis_verified=False,
        aggregate_feature_eligible=False,
    )
    assert "900 TWD" in _metric_text(metric)
    tooltip = _fundamental_basis_tooltip(metric)
    assert "期間基礎尚未核實" in tooltip
    assert "未具聚合特徵資格" in tooltip
    assert "不供累計或比率運算" in tooltip


def _sidecar_payload(*, h5: dict[str, object], target_metric: str = "benchmark_excess_after_standard_80bp_cost",
                     keys: tuple[str, ...] = ("final|CORE19|h5|ridge_logistic",)) -> dict[str, object]:
    vector_sha = "d" * 64
    prediction = {
        "schema_version": "ml-current-restated-outcome-prediction.v1",
        "status": "research_prediction_only",
        "symbol": "1477",
        "event_date": "2026-10-02",
        "model_manifest_sha256": _SHA_A,
        "historical_pit": False,
        "decision_time_eligible": False,
        "production_action_allowed": False,
        "target_metric": target_metric,
        "model_available_at": "2026-10-04T04:00:00+00:00",
        "inference_at": "2026-10-04T05:00:00+00:00",
        "input_quality_summary": {"usable_feature_count": 10, "registry_feature_count": 19},
        "predicted_benchmark_excess_return_bp": {key: 125 for key in keys},
    }
    return {
        "predictions": [{
            "symbol": "1477",
            "event_date": "2026-10-02",
            "core19_numeric_vector_sha256": vector_sha,
            "model_prediction": prediction,
            "gross_outcome_and_cost": h5,
        }],
        "core19_numeric_vector_sha256_by_symbol": {"1477": vector_sha},
    }


def test_price_row_fingerprint_is_stable_and_rejects_inexact_inputs() -> None:
    assert _price_fingerprint() == stock_price_row_fingerprint_sha256(
        stock_code="1477",
        data_date=date(2026, 10, 2),
        open_price=Decimal("54"),
        high_price=Decimal("56.00"),
        low_price=Decimal("53.000"),
        close_price=Decimal("55"),
        volume=1200,
        turnover=Decimal("66000"),
    )
    assert _price_fingerprint() != _price_fingerprint("2026-10-01")
    with pytest.raises(CurrentRestatedMLRegistryError):
        stock_price_row_fingerprint_sha256(
            stock_code="1477", data_date="2026-10-02", open_price=54.0,
            high_price=56, low_price=53, close_price=55, volume=1, turnover=55,
        )


def test_registry_prediction_contract_rechecks_h5_dates_arithmetic_and_keys() -> None:
    h5 = {
        "status": "mature_gross_label",
        "horizon": 5,
        "next_entry_date": "2026-10-05",
        "horizon_end_date": "2026-10-09",
        "gross_stock_return_bp": 500,
        "gross_benchmark_return_bp": 100,
        "benchmark_excess_after_standard_80bp_cost": 320,
        "after_lane_cost_stock_return_bp": 450,
        "round_trip_cost": {"estimated_round_trip_cost_bp": 50},
        "price_inputs": {"stock_entry_source_hash": _SHA_A},
    }
    receipt = _sidecar_payload(h5=h5)
    bp, projected = _validate_prediction_payload(
        receipt=receipt,
        symbol="1477",
        event_date="2026-10-02",
        model_manifest_sha256=_SHA_A,
        model_keys=("final|CORE19|h5|ridge_logistic",),
        generated_at=datetime(2026, 10, 9, 13, 0, tzinfo=_TAIPEI),
    )
    assert bp == {"final|CORE19|h5|ridge_logistic": 125}
    assert projected["benchmark_excess_after_standard_80bp_cost"] == 320

    bad_math = dict(h5, benchmark_excess_after_standard_80bp_cost=321)
    with pytest.raises(CurrentRestatedMLRegistryError, match="arithmetic"):
        _validate_prediction_payload(
            receipt=_sidecar_payload(h5=bad_math), symbol="1477", event_date="2026-10-02",
            model_manifest_sha256=_SHA_A, model_keys=("final|CORE19|h5|ridge_logistic",),
            generated_at=datetime(2026, 10, 9, 13, 0, tzinfo=_TAIPEI),
        )
    with pytest.raises(CurrentRestatedMLRegistryError, match="receipt date"):
        _validate_prediction_payload(
            receipt=_sidecar_payload(h5=h5), symbol="1477", event_date="2026-10-02",
            model_manifest_sha256=_SHA_A, model_keys=("final|CORE19|h5|ridge_logistic",),
            generated_at=datetime(2026, 10, 8, 23, 0, tzinfo=_TAIPEI),
        )
    with pytest.raises(CurrentRestatedMLRegistryError, match="keys"):
        _validate_prediction_payload(
            receipt=_sidecar_payload(h5=h5, keys=("unexpected",)), symbol="1477",
            event_date="2026-10-02", model_manifest_sha256=_SHA_A,
            model_keys=("final|CORE19|h5|ridge_logistic",),
            generated_at=datetime(2026, 10, 9, 13, 0, tzinfo=_TAIPEI),
        )


def test_immature_h5_rejects_any_future_outcome_payload() -> None:
    h5 = {
        "status": "not_mature",
        "horizon": 5,
        "gross_stock_return_bp": None,
        "gross_benchmark_return_bp": None,
        "benchmark_excess_after_standard_80bp_cost": None,
        "after_lane_cost_stock_return_bp": None,
        "round_trip_cost": None,
        "price_inputs": None,
    }
    payload = _sidecar_payload(h5=h5)
    _validate_prediction_payload(
        receipt=payload, symbol="1477", event_date="2026-10-02",
        model_manifest_sha256=_SHA_A,
        model_keys=("final|CORE19|h5|ridge_logistic",),
        generated_at=datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc),
    )
    h5["horizon_end_date"] = "2026-10-09"
    with pytest.raises(CurrentRestatedMLRegistryError, match="immature"):
        _validate_prediction_payload(
            receipt=_sidecar_payload(h5=h5), symbol="1477", event_date="2026-10-02",
            model_manifest_sha256=_SHA_A, model_keys=("final|CORE19|h5|ridge_logistic",),
            generated_at=datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc),
        )


def test_current_ml_provider_rejects_wrong_price_revision_target_and_clock() -> None:
    service = _service()
    context = {
        "ml_scope_mode": "current_stock_research",
        "current_event_date": "2026-10-02",
        "current_price_row_fingerprint_sha256": _price_fingerprint(),
    }
    # Call the private validator with an injected provider to keep the test isolated from storage.
    service.ml_provider = lambda code, cutoff, context=None: _ml_candidate()
    accepted = service._read_ml("1477", date(2026, 10, 4), context)
    assert accepted.status == "degraded"
    assert accepted.predicted_benchmark_excess_return_bp["final|CORE19|h5|ridge_logistic"] == 125
    assert accepted.h5_status == "not_mature"

    service.ml_provider = lambda code, cutoff, context=None: _ml_candidate(
        current_price_row_fingerprint_sha256=_SHA_B
    )
    assert service._read_ml("1477", date(2026, 10, 4), context).status == "unavailable"
    service.ml_provider = lambda code, cutoff, context=None: _ml_candidate(
        target_metric="unrelated_metric"
    )
    assert service._read_ml("1477", date(2026, 10, 4), context).status == "unavailable"
    service.ml_provider = lambda code, cutoff, context=None: _ml_candidate(
        available_at="2026-10-04T04:59:00+00:00"
    )
    assert service._read_ml("1477", date(2026, 10, 4), context).status == "unavailable"
    for flag, falsey in (
        ("research_only", 1),
        ("historical_pit_eligible", 0),
        ("formal_qualified", 0),
        ("production_action_allowed", 0),
    ):
        service.ml_provider = lambda code, cutoff, context=None, flag=flag, falsey=falsey: _ml_candidate(
            **{flag: falsey}
        )
        assert service._read_ml("1477", date(2026, 10, 4), context).status == "unavailable"


def test_registry_publish_and_current_lookup_pin_cycle_price_source_and_scope(tmp_path) -> None:
    import hashlib
    import json

    research_root = tmp_path.parent / f"{tmp_path.name}_FA_ML_Research"
    research_root.mkdir(parents=True)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ml_research_storage.json").write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(research_root),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    manifest_dir = research_root / "model"
    sidecar_dir = research_root / "fit"
    projection_dir = research_root / "b_projection"
    manifest_dir.mkdir(parents=True)
    sidecar_dir.mkdir(parents=True)
    projection_dir.mkdir(parents=True)
    bundle_bytes = b"verified-test-model-bundle"
    (manifest_dir / "model.bundle").write_bytes(bundle_bytes)
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
    model_key = "final|CORE19|h5|ridge_logistic"
    manifest = {
        "schema_version": "ml-current-restated-base-outcome-model.v1",
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "production_action_allowed": False,
        "model_available_at": "2026-10-04T04:00:00+00:00",
        "target_contract": {"target_metric": "benchmark_excess_after_standard_80bp_cost"},
        "model_bundle": {
            "sha256": bundle_sha,
            "filename": "model.bundle",
            "model_keys": [model_key],
        },
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    context_sha = "c" * 64
    vector_hashes = {"1225": "d" * 64, "1477": "e" * 64}
    fingerprints = {
        "1225": _price_fingerprint(stock_code="1225"),
        "1477": _price_fingerprint(stock_code="1477"),
    }
    immature_h5 = {
        "status": "not_mature",
        "horizon": 5,
        "gross_stock_return_bp": None,
        "gross_benchmark_return_bp": None,
        "benchmark_excess_after_standard_80bp_cost": None,
        "after_lane_cost_stock_return_bp": None,
        "next_entry_date": None,
        "horizon_end_date": None,
        "round_trip_cost": None,
        "price_inputs": None,
    }
    predictions = []
    for symbol in ("1225", "1477"):
        predictions.append({
            "symbol": symbol,
            "event_date": "2026-10-02",
            "core19_numeric_vector_sha256": vector_hashes[symbol],
            "model_prediction": {
                "schema_version": "ml-current-restated-outcome-prediction.v1",
                "status": "research_prediction_only",
                "symbol": symbol,
                "event_date": "2026-10-02",
                "model_manifest_sha256": manifest_sha,
                "historical_pit": False,
                "decision_time_eligible": False,
                "production_action_allowed": False,
                "target_metric": "benchmark_excess_after_standard_80bp_cost",
                "model_available_at": "2026-10-04T04:00:00+00:00",
                "inference_at": "2026-10-04T05:00:00+00:00",
                "input_quality_summary": {"usable_feature_count": 19, "registry_feature_count": 19},
                "predicted_benchmark_excess_return_bp": {model_key: 125},
            },
            "gross_outcome_and_cost": dict(immature_h5),
        })
    sidecar = {
        "schema_version": "current-restated-source-row-learning-terminal.v1",
        "status": "verified_research_sidecar",
        "terminal": True,
        "mode": "source_row_outcome_research",
        "historical_pit_eligible": False,
        "formal_calibration_performed": False,
        "formal_order_allowed": False,
        "production_action_allowed": False,
        "model_training_performed": False,
        "verified_model_reused": True,
        "lane": "legacy",
        "generated_at": "2026-10-04T05:01:00+00:00",
        "inference_at": "2026-10-04T05:00:00+00:00",
        "input_binding": {
            "current_event_date": "2026-10-02",
            "current_symbols": ["1225", "1477"],
            "source_context_sha256": context_sha,
            "model_manifest_sha256": manifest_sha,
            "model_bundle_sha256": bundle_sha,
        },
        "source_pins": {
            "source_context_sha256": context_sha,
            "model_manifest_sha256": manifest_sha,
            "model_bundle_sha256": bundle_sha,
            "direct_manifest_sha256": "f" * 64,
        },
        "core19_numeric_vector_sha256_by_symbol": vector_hashes,
        "predictions": predictions,
        "sample_cohort_sha256": "a" * 64,
    }
    sidecar_bytes = json.dumps(
        sidecar, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sidecar_path = sidecar_dir / "receipt.json"
    sidecar_path.write_bytes(sidecar_bytes)
    projection_path = projection_dir / "projection_observations.jsonl"
    projection_bytes = b'{"event_date":"2026-10-02","schema_version":"fixture"}\n'
    projection_path.write_bytes(projection_bytes)
    projection_sha = hashlib.sha256(projection_bytes).hexdigest()

    registry = CurrentRestatedMLRunRegistry(
        repository_root=tmp_path,
        now_provider=lambda: datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc),
        model_loader=lambda *args, **kwargs: None,
    )
    published = registry.publish_sidecar(
        sidecar_receipt_path=sidecar_path,
        expected_sidecar_receipt_sha256=hashlib.sha256(sidecar_bytes).hexdigest(),
        model_manifest_path=manifest_path,
        expected_model_manifest_sha256=manifest_sha,
        expected_model_bundle_sha256=bundle_sha,
        cycle_id="cycle-20261004",
        current_price_row_fingerprint_sha256_by_symbol=fingerprints,
        current_price_rows_source_path=projection_path,
        expected_current_price_rows_source_sha256="sha256:" + projection_sha,
    )
    assert published.indexed is True
    assert Path(published.record_path).is_relative_to(research_root)
    current_context = {
        "stock_code": "1477",
        "ml_scope_mode": "current_stock_research",
        "current_event_date": "2026-10-02",
        "current_price_row_fingerprint_sha256": fingerprints["1477"],
    }
    current = registry("1477", date(2026, 10, 4), current_context)
    assert current is not None
    assert current["cycle_id"] == "cycle-20261004"

    active_index_bytes = registry.index_path.read_bytes()
    index_entry = json.loads(active_index_bytes.splitlines()[-1].decode("utf-8"))
    legacy_registry_root = tmp_path / "output" / "ml_research" / "current_stock_research_registry"
    legacy_record_path = legacy_registry_root / Path(index_entry["record_path"])
    legacy_record_path.parent.mkdir(parents=True)
    legacy_record_path.write_bytes(Path(published.record_path).read_bytes())
    (legacy_registry_root / "run_index.jsonl").write_bytes(active_index_bytes)
    registry.index_path.unlink()
    legacy = registry("1477", date(2026, 10, 4), current_context)
    assert legacy is not None
    assert legacy["cycle_id"] == "cycle-20261004"
    assert current["predicted_benchmark_excess_return_bp"] == {model_key: 125}
    assert current["h5_status"] == "not_mature"

    saved_context = {
        "stock_code": "1477",
        "ml_scope_mode": "selected_saved_decision",
        "result_id": "saved-result-1477",
        "source_snapshot_id": "saved-snapshot",
        "source_snapshot_hash": "b" * 64,
        "data_date": "2026-10-02",
    }
    assert registry("1477", date(2026, 10, 4), saved_context) is None
    wrong_price = dict(current_context, current_price_row_fingerprint_sha256="9" * 64)
    assert registry("1477", date(2026, 10, 4), wrong_price) is None

    projection_path.write_bytes(projection_bytes + b"tampered\n")
    assert registry("1477", date(2026, 10, 4), current_context) is None


def test_current_market_status_is_typed_and_historical_status_is_withheld() -> None:
    observation = SimpleNamespace(
        symbol="1477",
        observed_at="2026-10-04T05:30:00+00:00",
        listing_status="listed",
        market="上市",
        name="聚陽",
        trading_restrictions=(
            {
                "symbol": "1477",
                "restriction_type": "disposition",
                "restriction_state": "reported_on_source_date",
                "effective_from": "2026-10-05",
                "effective_to": None,
                "resumed_on": "2026-10-06",
                "published_date": "2026-10-03",
                "notice_reference": "notice-1",
                "source_id": "twse.current_restrictions",
                "evidence_type": "official_notice",
                "observed_at": "2026-10-04T05:20:00+00:00",
                "source_data_dates": ("2026-10-02",),
                "raw_sha256": "sha256:" + _SHA_A,
                "source_url": "https://example.invalid/notice",
                "market": "twse",
                "name": "聚陽",
                "details": "source text",
            },
        ),
        status_evidence=(
            {
                "symbol": "1477",
                "source_id": "twse.current_restrictions",
                "evidence_type": "listing_status_notice",
                "observed_at": "2026-10-04T05:20:00+00:00",
                "published_date": "2026-10-03",
                "notice_reference": "notice-1",
                "effective_from": "2026-10-05",
                "effective_to": None,
                "resumed_on": None,
                "source_data_dates": (),
                "raw_sha256": "sha256:" + _SHA_A,
                "source_url": "https://example.invalid/notice",
                "market": "twse",
                "name": "test",
                "details": "notice text",
                "restriction_type": "suspension",
                "restriction_state": "reported_on_source_date",
            },
        ),
        source_ids=("twse.current_restrictions",),
        source_data_dates=("2026-10-02",),
        source_warnings=(),
        partial_failure=False,
        scope="current_only",
        pit_eligible=False,
    )
    service = _service(market_status_provider=lambda code: observation)
    dto, source = service._read_market_status("1477", date(2026, 10, 4))
    assert source is not None
    assert dto.status == "available"
    assert dto.listing_status == "listed"
    assert dto.trading_restrictions[0].effective_to == ""
    assert dto.trading_restrictions[0].resumed_on == "2026-10-06"
    assert dto.trading_restrictions[0].published_date == "2026-10-03"
    assert dto.trading_restrictions[0].notice_reference == "notice-1"
    assert dto.status_evidence[0].published_date == "2026-10-03"
    assert dto.status_evidence[0].effective_from == "2026-10-05"
    assert dto.status_evidence[0].raw_sha256 == _SHA_A
    assert dto.pit_eligible is False

    def historical_provider(_: str) -> object:
        raise AssertionError("historical report must not read current status")

    historical_service = _service(market_status_provider=historical_provider)
    historical, historical_source = historical_service._read_market_status("1477", date(2026, 10, 2))
    assert historical.status == "unknown"
    assert historical_source is not None and historical_source.row_count == 0


def test_stale_official_valuation_remains_dated_current_only_annotation() -> None:
    observation = SimpleNamespace(
        stock_code="1477",
        metric_name="pe",
        value=Decimal("18.25"),
        unit="ratio",
        market="tpex",
        as_of_date="2026-09-18",
        available_at=datetime(2026, 10, 4, 5, 30, tzinfo=timezone.utc),
        source="official.tpex.valuation",
        source_version=f"official-tpex-valuation.v1:sha256:{_SHA_A}",
        raw_response_sha256=_SHA_A,
        formal_pit_eligible=False,
    )
    result = SimpleNamespace(
        stock_code="1477",
        report_date="2026-10-04",
        status="stale",
        formal_pit_eligible=False,
        observations=(observation,),
        market_coverage=(SimpleNamespace(
            market="tpex", status="stale", as_of_date="2026-09-18",
            source_version=observation.source_version,
            available_at=observation.available_at,
        ),),
        diagnostics=("market date does not match the latest daily-price date",),
    )
    service = _service()
    rows, sources = service._current_valuation_observations(
        "1477",
        date(2026, 10, 4),
        result,
        expected_market_date=date(2026, 10, 2),
        expected_market_session=date(2026, 10, 2),
        price_freshness=ReportFreshness.FRESH.value,
    )
    assert len(rows) == 1
    assert rows[0].value == Decimal("18.25")
    assert rows[0].as_of_date == "2026-09-18"
    assert rows[0].quality == "degraded"
    assert rows[0].formal_pit_eligible is False
    assert "不標示為當下可用" in rows[0].value_text
    assert sources and sources[0].quality == "degraded"
    assert sources[0].coverage_status == "stale"


def test_weekend_official_session_keeps_matching_valuation_current() -> None:
    observation = SimpleNamespace(
        stock_code="1477",
        metric_name="pe",
        value=Decimal("13.11"),
        unit="ratio",
        market="twse",
        as_of_date="2026-10-02",
        available_at=datetime(2026, 10, 4, 1, 23, tzinfo=timezone.utc),
        source="official.twse.valuation",
        source_version=f"official-twse-valuation.v1:sha256:{_SHA_A}",
        raw_response_sha256=_SHA_A,
        formal_pit_eligible=False,
    )
    result = SimpleNamespace(
        stock_code="1477",
        report_date="2026-10-04",
        status="ready",
        formal_pit_eligible=False,
        observations=(observation,),
        market_coverage=(
            SimpleNamespace(
                market="twse", status="ready", as_of_date="2026-10-02",
                source_version=observation.source_version,
                available_at=observation.available_at, diagnostic=None,
            ),
            SimpleNamespace(
                market="tpex", status="ready", as_of_date="2026-10-02",
                source_version="official-tpex-valuation.v1", available_at=None,
                diagnostic=None,
            ),
        ),
        diagnostics=(),
    )
    service = _service()
    rows, sources = service._current_valuation_observations(
        "1477",
        date(2026, 10, 4),
        result,
        expected_market_date=date(2026, 10, 2),
        expected_market_session=date(2026, 10, 2),
        price_freshness=ReportFreshness.FRESH.value,
    )
    assert len(rows) == 1
    assert rows[0].quality == "observed"
    assert rows[0].as_of_date == "2026-10-02"
    twse = next(source for source in sources if source.source_id.endswith("twse"))
    tpex = next(source for source in sources if source.source_id.endswith("tpex"))
    assert twse.coverage_status == tpex.coverage_status == "ready"
    assert twse.quality == tpex.quality == "observed"
    assert tpex.status == "not_applicable"
    assert tpex.row_count == 0
    assert any("不跨市場補值" in item for item in tpex.limitations)


def test_same_date_valuation_is_degraded_when_quote_source_is_stale() -> None:
    observation = SimpleNamespace(
        stock_code="1477",
        metric_name="pe",
        value=Decimal("13.11"),
        unit="ratio",
        market="twse",
        as_of_date="2026-10-02",
        available_at=datetime(2026, 10, 4, 1, 23, tzinfo=timezone.utc),
        source="official.twse.valuation",
        source_version=f"official-twse-valuation.v1:sha256:{_SHA_A}",
        raw_response_sha256=_SHA_A,
        formal_pit_eligible=False,
    )
    coverage = SimpleNamespace(
        market="twse", status="ready", as_of_date="2026-10-02",
        source_version=observation.source_version,
        available_at=observation.available_at, diagnostic=None,
    )
    result = SimpleNamespace(
        stock_code="1477", report_date="2026-10-04", status="ready",
        formal_pit_eligible=False, observations=(observation,),
        market_coverage=(coverage,), diagnostics=(),
    )
    rows, sources = _service()._current_valuation_observations(
        "1477",
        date(2026, 10, 4),
        result,
        expected_market_date=date(2026, 10, 2),
        expected_market_session=date(2026, 10, 2),
        price_freshness=ReportFreshness.STALE.value,
    )
    assert len(rows) == 1
    assert rows[0].quality == "degraded"
    assert "freshness 為 stale" in rows[0].value_text
    twse = next(source for source in sources if source.source_id.endswith("twse"))
    assert twse.quality == "degraded"


def test_unavailable_valuation_preserves_market_coverage_and_diagnostics() -> None:
    result = SimpleNamespace(
        stock_code="1477",
        report_date="2026-10-04",
        status="unavailable",
        formal_pit_eligible=False,
        observations=(),
        market_coverage=(
            SimpleNamespace(
                market="twse", status="missing", as_of_date=None,
                available_at=None, source_version="", diagnostic="twse_capture_missing",
            ),
            SimpleNamespace(
                market="tpex", status="missing", as_of_date=None,
                available_at=None, source_version="", diagnostic="tpex_capture_missing",
            ),
        ),
        diagnostics=("stock code has no official current valuation row",),
    )
    rows, sources = _service()._current_valuation_observations(
        "1477",
        date(2026, 10, 4),
        result,
        expected_market_date=date(2026, 10, 2),
        expected_market_session=date(2026, 10, 2),
        price_freshness=ReportFreshness.FRESH.value,
    )
    assert not rows
    assert {source.coverage_status for source in sources} == {"missing"}
    assert all(source.row_count == 0 and source.quality == "degraded" for source in sources)
    assert all("capture_missing" in " ".join(source.limitations) for source in sources)


class _FakeConditionMonitor:
    def __init__(self) -> None:
        self.current_prices: list[Decimal | None] = []
        self.current_snapshots: list[object] = []

    def evaluate(self, position: object, snapshot: object) -> object:
        del position
        self.current_snapshots.append(snapshot)
        self.current_prices.append(getattr(snapshot, "current_price"))
        return SimpleNamespace(
            stock_code="2382", status="ok", reasons=(), details={}
        )


def _position() -> SimpleNamespace:
    return SimpleNamespace(
        stock_code="2382",
        position_id="position-2382-1",
        portfolio_id="main",
        quantity=Decimal("100"),
        average_cost=Decimal("50"),
        invested_amount=Decimal("5000"),
        current_price=Decimal("999"),
        unrealized_pnl=Decimal("94900"),
        unrealized_pnl_pct=Decimal("18.98"),
        exposure_bp=None,
        is_holding=True,
        source_type="manual_trade_ledger",
        source_id="trades.jsonl",
        source_snapshot_hash=_SHA_A,
        opened_at="2025-01-01",
        last_trade_date="2026-09-01",
    )


def _price_point(*, data_date: str = "2026-10-02", fingerprint: str | None = None,
                 available_at: str = "") -> StockPricePointDTO:
    return StockPricePointDTO(
        data_date=data_date,
        open_price=Decimal("54"),
        high_price=Decimal("56"),
        low_price=Decimal("53"),
        close_price=Decimal("55"),
        volume=1200,
        turnover=Decimal("66000"),
        available_at=available_at,
        source_id="sqlite.daily_prices",
        source_snapshot_hash=fingerprint if fingerprint is not None else _price_fingerprint(data_date, "2382"),
    )


def test_position_exit_health_use_report_quote_date_and_fingerprint() -> None:
    position = _position()
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: position),
        condition_monitor=monitor,
    )
    snapshot, source = service._read_position(
        "2382", date(2026, 10, 4), {}, price_points=(_price_point(),)
    )
    assert source is not None and snapshot is not None
    assert snapshot.position_as_of == "2026-10-04"
    assert snapshot.quote_data_date == "2026-10-02"
    assert snapshot.quote_available_at == ""
    assert snapshot.last_trade_date == "2026-09-01"
    assert snapshot.current_price == Decimal("55")
    assert snapshot.unrealized_pnl == Decimal("500.00")
    assert monitor.current_prices == []
    assert snapshot.health_status == "UNKNOWN"
    assert snapshot.health_label == "未知（行情新鮮度未驗證）"
    assert snapshot.exit_status == "unavailable"
    assert snapshot.quote_source_snapshot_hash == _price_fingerprint(stock_code="2382")
    assert source.data_as_of == "2026-10-04"
    assert source.available_at == ""


def test_exit_provider_requires_quote_identity_bound_to_requested_stock() -> None:
    provider = PortfolioExitReadProvider()
    common = {
        "position": _position(),
        "condition_result": SimpleNamespace(stock_code="2382"),
        "health_result": SimpleNamespace(stock_code="2382", state="HEALTHY", reasons=()),
    }

    # StockPricePointDTO intentionally has no stock_code field; production quote
    # identity is bound into the existing exact-row fingerprint.
    valid = provider(
        "2382",
        date(2026, 10, 4),
        quote_snapshot=_price_point(fingerprint=_price_fingerprint(stock_code="2382")),
        **common,
    )
    assert valid is not None
    assert valid.stock_code == "2382"

    wrong_symbol_quote = _price_point(fingerprint=_price_fingerprint(stock_code="1477"))
    assert (
        provider(
            "2382",
            date(2026, 10, 4),
            quote_snapshot=wrong_symbol_quote,
            **common,
        )
        is None
    )
    assert (
        provider(
            "",
            date(2026, 10, 4),
            quote_snapshot=_price_point(fingerprint=_price_fingerprint(stock_code="2382")),
            **common,
        )
        is None
    )


def test_fresh_weekend_price_does_not_call_manual_price_only_health_or_exit() -> None:
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: _position()),
        condition_monitor=monitor,
    )
    snapshot, _ = service._read_position(
        "2382",
        date(2026, 10, 4),
        {},
        price_points=(_price_point(),),
        price_source=SimpleNamespace(
            source_id="sqlite.daily_prices",
            data_as_of="2026-10-02",
            freshness=ReportFreshness.FRESH.value,
        ),
    )
    assert snapshot is not None
    assert snapshot.quote_data_date == "2026-10-02"
    assert snapshot.current_price == Decimal("55")
    assert snapshot.unrealized_pnl == Decimal("500.00")
    assert monitor.current_prices == []
    assert monitor.current_snapshots == []
    assert snapshot.health_status == "UNKNOWN"
    assert snapshot.health_label == "未知（僅價格／成本觀察）"
    assert snapshot.exit_status == "unavailable"


def test_stale_quote_keeps_dated_pnl_but_withholds_health_and_exit() -> None:
    position = _position()
    position.source_summary = {"stop_loss_pct": "0.05"}
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: position),
        condition_monitor=monitor,
    )
    snapshot, _ = service._read_position(
        "2382",
        date(2026, 10, 4),
        {},
        price_points=(_price_point(),),
        price_source=SimpleNamespace(
            source_id="sqlite.daily_prices",
            data_as_of="2026-10-02",
            freshness=ReportFreshness.STALE.value,
        ),
    )
    assert snapshot is not None
    assert snapshot.current_price == Decimal("55")
    assert snapshot.unrealized_pnl == Decimal("500.00")
    assert snapshot.health_status == "UNKNOWN"
    assert snapshot.health_label == "未知（行情已過期）"
    assert snapshot.exit_status == "unavailable"
    assert monitor.current_prices == []
    assert monitor.current_snapshots == []


def test_fresh_weekend_quote_with_structured_thesis_allows_health_read() -> None:
    position = _position()
    position.source_summary = {"stop_loss_pct": "0.05"}
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: position),
        condition_monitor=monitor,
    )
    snapshot, _ = service._read_position(
        "2382",
        date(2026, 10, 4),
        {},
        price_points=(_price_point(),),
        price_source=SimpleNamespace(
            source_id="sqlite.daily_prices",
            data_as_of="2026-10-02",
            freshness=ReportFreshness.FRESH.value,
        ),
    )
    assert snapshot is not None
    assert monitor.current_prices == [Decimal("55")]
    assert len(monitor.current_snapshots) == 1
    proof = monitor.current_snapshots[0]
    assert getattr(proof, "quote_data_date") == date(2026, 10, 2)
    assert getattr(proof, "quote_source_id") == "sqlite.daily_prices"
    assert getattr(proof, "quote_source_snapshot_hash") == _price_fingerprint(
        stock_code="2382"
    )
    assert getattr(proof, "quote_freshness_status") == "current"
    assert getattr(proof, "quote_expected_date") == date(2026, 10, 2)
    assert position.last_trade_date == "2026-09-01"
    assert snapshot.health_status == "HEALTHY"


def test_quote_source_mismatch_cannot_reach_position_health_or_exit() -> None:
    position = _position()
    position.source_summary = {"stop_loss_pct": "0.05"}
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: position),
        condition_monitor=monitor,
    )
    point = _price_point()
    point = replace(point, source_id="csv.daily_prices")
    snapshot, _ = service._read_position(
        "2382",
        date(2026, 10, 4),
        {},
        price_points=(point,),
        price_source=SimpleNamespace(
            source_id="sqlite.daily_prices",
            data_as_of="2026-10-02",
            freshness=ReportFreshness.FRESH.value,
        ),
    )
    assert snapshot is not None
    assert snapshot.current_price == Decimal("55")
    assert snapshot.unrealized_pnl == Decimal("500.00")
    assert snapshot.health_status == "UNKNOWN"
    assert snapshot.exit_status == "unavailable"
    assert monitor.current_prices == []
    assert monitor.current_snapshots == []


@pytest.mark.parametrize("point", [
    None,
    _price_point(data_date="2026-10-05"),
    _price_point(fingerprint=""),
    _price_point(available_at="2026-10-04T07:00:00+00:00"),
])
def test_position_with_missing_future_or_unfingerprinted_quote_withholds_pnl_and_exit(
    point: StockPricePointDTO | None,
) -> None:
    position = _position()
    monitor = _FakeConditionMonitor()
    service = _service(
        portfolio_service=SimpleNamespace(get_position_detail=lambda _: position),
        condition_monitor=monitor,
    )
    prices = (point,) if point is not None else ()
    snapshot, _ = service._read_position("2382", date(2026, 10, 4), {}, price_points=prices)
    assert snapshot is not None
    assert snapshot.current_price is None
    assert snapshot.unrealized_pnl is None
    assert snapshot.quote_data_date == ""
    assert snapshot.exit_status == "unavailable"
    assert monitor.current_prices == []


@pytest.mark.parametrize("source_available_at", [None, ""])
def test_current_fundamental_blank_or_null_source_clock_remains_visible(
    tmp_path, source_available_at: str | None,
) -> None:
    import sqlite3

    from data_module.current_fundamental_snapshots import COLUMNS, SCHEMA

    db_path = tmp_path / "fundamentals.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        row = dict(zip(COLUMNS, (
            "2382", "statement_item", "2026-Q3", "2026-09-30", "raw-revenue",
            "Quarter revenue", "123456", "TWD", "2026-10-04T05:00:00+00:00",
            "official.source", "official.source.v1", "twse", "unknown", 0, 0,
            source_available_at,
        )))
        conn.execute(
            f"INSERT INTO fundamental_current_observations ({','.join(COLUMNS)}) "
            f"VALUES ({','.join('?' for _ in COLUMNS)})",
            tuple(row[key] for key in COLUMNS),
        )
    config = SimpleNamespace(db_file=db_path, sqlite_db_file=db_path, output_root=None)
    service = StockResearchReportReadService(config, clock=lambda: _NOW)
    rows, sources, _ = service._read_fundamentals("2382", date(2026, 10, 4), include_current=True)
    current = next(row for row in rows if row.metric_name == "raw-revenue")
    assert current.value == Decimal("123456")
    assert current.available_at == ""
    assert current.period_basis == "unknown"
    assert current.aggregate_feature_eligible is False
    assert any(source.row_count == 1 for source in sources)
