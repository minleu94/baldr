from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from app_module.dtos import RecommendationDTO
from app_module.journal_service import JournalService
from app_module.personalization_contract import (
    PersonalizationDeliveryScope,
    canonical_payload_hash,
)
from app_module.v4_evidence_identity import build_strategy_config_identity
from data_module.ml_historical_snapshot_provider import (
    HistoricalPriceObservation,
    HistoricalRawSnapshot,
)
from ml_module.recommendation_inference_provenance import (
    RecommendationInferenceProjectionReceipt,
    build_inference_projection_receipt,
    build_inference_provenance,
    build_training_provenance,
    persist_inference_projection_receipt,
    validate_provenance_compatibility,
)
from ml_module.recommendation_probability_transform import PROBABILITY_TRANSFORM_ID


RESULT_ID = "rec_generation_cli_001"
STOCK_CODE = "2330"
PREDICTION_ID = "00000000-0000-0000-0000-000000000020"
SCOPE_ID = "scope_generation_cli_001"
COST_HASH = "sha256:" + ("b" * 64)
DATASET_HASH = "sha256:" + ("d" * 64)
UNIVERSE_HASH = "sha256:" + ("e" * 64)
LABEL_CONTRACT = "label_projection_v1"
RETURN_BASIS = "close_to_close_event_date"


def _receipt() -> RecommendationInferenceProjectionReceipt:
    snapshot = HistoricalRawSnapshot(
        decision_date="2025-02-10",
        feature_as_of_date="2025-02-09",
        prices=(
            HistoricalPriceObservation(
                symbol=STOCK_CODE,
                trading_date="2025-02-09",
                open_price=Decimal("100"),
                high_price=Decimal("101"),
                low_price=Decimal("99"),
                close_price=Decimal("100"),
                volume=1_000,
                turnover_amount_minor=100_000,
            ),
        ),
        technicals=(),
        market=(),
        industries=(),
        source_fingerprint="sha256:" + ("1" * 64),
        query_count=1,
    )
    inference = build_inference_provenance(
        snapshot=snapshot,
        feature_rows=(
            {
                "symbol": STOCK_CODE,
                "decision_date": "2025-02-10",
                "feature_as_of_date": "2025-02-09",
                "feature_available_date": "2025-02-09",
                "values": (("momentum_bp", 100),),
            },
        ),
        feature_schema=(("momentum_bp", "int", "bp"),),
        feature_registry_hash="sha256:" + ("2" * 64),
        cost_scenario_hash=COST_HASH,
        probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    training = build_training_provenance(lineage_payload=None)
    compatibility = validate_provenance_compatibility(
        training,
        inference,
        expected_cost_scenario_hash=COST_HASH,
        expected_probability_transform_id=PROBABILITY_TRANSFORM_ID,
    )
    return build_inference_projection_receipt(
        decision_date="2025-02-10",
        result_id=RESULT_ID,
        candidate_identity={"candidate_id": "model_generation_cli"},
        training_provenance=training,
        inference_provenance=inference,
        compatibility=compatibility,
        projections=(
            {
                "stock_code": STOCK_CODE,
                "model_version": "model_generation_cli",
                "dataset_version": "dataset_generation_cli",
                "dataset_hash": DATASET_HASH,
                "cost_scenario_hash": COST_HASH,
                "horizon": "20 trading days",
                "prediction_id": PREDICTION_ID,
                "label_contract_id": LABEL_CONTRACT,
                "return_basis": RETURN_BASIS,
                "universe_policy_hash": UNIVERSE_HASH,
                "population_probability_bp": 5000,
                "calibrated_probability_bp": 5200,
                "status": "active_candidate",
            },
        ),
    )


def _scope() -> PersonalizationDeliveryScope:
    return PersonalizationDeliveryScope.create(
        scope_id=SCOPE_ID,
        scope_type="local",
        delivery_id="delivery_generation_cli_001",
        declared_at="2025-02-10T08:50:00+00:00",
        decision_at="2025-02-10T09:00:00+00:00",
        available_at="2025-02-10T08:55:00+00:00",
        captured_at="2025-02-10T08:55:00+00:00",
        receipt_created_at="2025-02-10T09:01:00+00:00",
    )


class _FakeRecommendationProducer:
    calls = 0

    def __init__(self, config: Any) -> None:
        self.config = config
        self.last_run_context: dict[str, Any] = {}

    def run_recommendation(self, config: dict[str, Any], **kwargs: Any) -> list[RecommendationDTO]:
        assert kwargs["result_id"] == RESULT_ID
        receipt = _receipt()
        receipt_path = persist_inference_projection_receipt(
            self.config.output_root,
            receipt,
        )
        type(self).calls += 1
        self.last_run_context = {
            "schema_version": "recommendation-context.v1",
            "strategy_config": dict(config),
            "universe_spec": {
                "codes": sorted(kwargs.get("universe") or []) or None,
                "max_stocks": kwargs["max_stocks"],
            },
            "result_id": RESULT_ID,
            "as_of_date": "2025-02-10",
            "data_date": "2025-02-10",
            "run_started_at": "2025-02-10T08:50:00.000000+00:00",
            "personalization_scope_declared_at": "2025-02-10T08:50:00.000000+00:00",
            "available_at": "2025-02-10T08:55:00.000000+00:00",
            "captured_at": "2025-02-10T08:55:00.000000+00:00",
            "decision_at": "2025-02-10T09:00:00.000000+00:00",
            "calibration_projection_receipt_created_at": "2025-02-10T09:01:00.000000+00:00",
            "calibration_projection_receipt": {
                "path": str(receipt_path),
                "receipt_hash": receipt.receipt_hash,
                "result_id": RESULT_ID,
                "receipt_created_at": "2025-02-10T09:01:00.000000+00:00",
            },
            "calibration_projection_rows": {
                STOCK_CODE: dict(receipt.payload["projections"][0]),
            },
            "temporal_contract": "recommendation-producer-clock.v1",
            "decision_clock_timezone": "UTC",
            "market_calendar_timezone": "Asia/Taipei",
            "temporal_mode": (
                "historical_research_not_as_if_available"
                if bool(kwargs.get("historical_research"))
                else "natural_producer_clock"
            ),
            "cutoff_selection": (
                "explicit_historical_cutoff"
                if bool(kwargs.get("historical_research"))
                else "producer_selected_latest_available_cutoff"
            ),
            "cutoff_policy": (
                "explicit_historical_research"
                if bool(kwargs.get("historical_research"))
                else "source_latest_available_exact"
            ),
            "prediction_decision_anchor": "actual_producer_decision_at",
            "horizon_anchor": "immutable_projection_receipt",
            **build_strategy_config_identity(
                config,
                max_stocks=kwargs["max_stocks"],
                top_n=kwargs["top_n"],
            ),
        }
        return [
            RecommendationDTO(
                stock_code=STOCK_CODE,
                stock_name="台積電",
                close_price=Decimal("100.00"),
                price_change=1.0,
                total_score=80.0,
                indicator_score=80.0,
                pattern_score=80.0,
                volume_score=80.0,
                recommendation_reasons="generation CLI test",
                industry="半導體",
                regime_match=True,
            )
        ]


def _args(output_root: Path, data_root: Path, config_path: Path) -> list[str]:
    return [
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--config-json",
        str(config_path),
        "--result-id",
        RESULT_ID,
        "--result-name",
        "generation CLI test",
        "--as-of-date",
        "2025-02-10",
        "--scope-id",
        SCOPE_ID,
        "--scope-type",
        "local",
        "--delivery-id",
        "delivery_generation_cli_001",
        "--request-id",
        "request_generation_cli_001",
    ]


def test_generation_cli_explicit_scope_save_ack_and_retry_use_custom_journal(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    monkeypatch.setattr(module, "RecommendationService", _FakeRecommendationProducer)
    _FakeRecommendationProducer.calls = 0
    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    custom_journal = tmp_path / "custom" / "journal.jsonl"
    args = _args(output_root, data_root, config_path)
    args.extend(["--journal-path", str(custom_journal), "--evidence-db", str(tmp_path / "evidence.sqlite")])

    first_code = module.main(args)
    first_payload = json.loads(capsys.readouterr().out)
    assert first_code == 0, first_payload
    assert first_payload["ok"] is True
    assert first_payload["delivery_status"] == "delivered"
    assert first_payload["readback"][0]["delivery_status"] == "delivered"
    assert custom_journal.is_file()
    assert not (output_root / "portfolio").exists()
    result_json = output_root / "recommendation" / "runs" / f"{RESULT_ID}.json"
    result_bytes = result_json.read_bytes()
    journal_bytes = custom_journal.read_bytes()

    retry_code = module.main(args)
    retry_payload = json.loads(capsys.readouterr().out)
    assert retry_code == 0
    assert retry_payload["ok"] is True
    assert retry_payload["delivery_status"] == "already_delivered"
    assert len(
        JournalService(
            cast(Any, SimpleNamespace(output_root=output_root)),
            journal_path=custom_journal,
        ).list_decision_revisions()
    ) == 1
    assert _FakeRecommendationProducer.calls == 1
    assert result_json.read_bytes() == result_bytes
    assert custom_journal.read_bytes() == journal_bytes

    changed_args = [*args, "--top-n", "49"]
    changed_code = module.main(changed_args)
    changed_payload = json.loads(capsys.readouterr().out)
    assert changed_code == 2
    assert changed_payload["ok"] is False
    assert any(
        "existing_result_strategy_identity_conflict" in item
        for item in changed_payload["diagnostics"]
    )
    assert changed_payload["write_attempted"] is False
    assert _FakeRecommendationProducer.calls == 1
    assert result_json.read_bytes() == result_bytes
    assert custom_journal.read_bytes() == journal_bytes


def test_temporal_contract_accepts_t_minus_one_cutoff_on_next_taipei_market_day(
    tmp_path: Path,
) -> None:
    import scripts.run_personalization_recommendation as module

    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    producer = _FakeRecommendationProducer(SimpleNamespace(output_root=output_root))
    producer.run_recommendation(
        {"filters": {}},
        max_stocks=200,
        top_n=50,
        as_of_date=None,
        universe=None,
        result_id=RESULT_ID,
        historical_research=False,
        select_latest_available_cutoff=True,
    )
    context = dict(producer.last_run_context)
    next_market_day_clocks = {
        "run_started_at": "2025-02-10T16:40:00.000000+00:00",
        "personalization_scope_declared_at": "2025-02-10T16:40:00.000000+00:00",
        "available_at": "2025-02-10T16:45:00.000000+00:00",
        "captured_at": "2025-02-10T16:45:00.000000+00:00",
        "decision_at": "2025-02-10T16:50:00.000000+00:00",
        "calibration_projection_receipt_created_at": "2025-02-10T16:51:00.000000+00:00",
    }
    context.update(next_market_day_clocks)
    receipt_metadata = dict(context["calibration_projection_receipt"])
    receipt_metadata["receipt_created_at"] = next_market_day_clocks[
        "calibration_projection_receipt_created_at"
    ]
    context["calibration_projection_receipt"] = receipt_metadata
    args = module._parser().parse_args(
        _args(output_root, data_root, config_path)
    )

    diagnostics, temporal = module._validate_producer_temporal_contract(
        args,
        producer_context=context,
        as_of_date="2025-02-10",
    )

    assert diagnostics == []
    assert temporal["temporal_mode"] == "natural_producer_clock"
    assert temporal["decision_market_date"] == "2025-02-11"
    assert temporal["available_market_date"] == "2025-02-11"


def test_generation_cli_separates_natural_latest_cutoff_from_historical_research(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    import scripts.run_personalization_recommendation as module

    monkeypatch.setattr(module, "RecommendationService", _FakeRecommendationProducer)
    _FakeRecommendationProducer.calls = 0
    config_path = tmp_path / "strategy.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")

    natural_output = tmp_path / "natural-output"
    natural_journal = tmp_path / "natural-journal.jsonl"
    natural_args = _args(natural_output, tmp_path / "natural-data", config_path)
    natural_args[natural_args.index("--as-of-date") + 1] = "2025-02-09"
    natural_args.extend(
        [
            "--journal-path",
            str(natural_journal),
            "--evidence-db",
            str(tmp_path / "natural-evidence.sqlite"),
        ]
    )

    natural_code = module.main(natural_args)
    natural_payload = json.loads(capsys.readouterr().out)
    assert natural_code == 2
    assert natural_payload["ok"] is False
    assert any(
        item in natural_payload["diagnostics"]
        for item in (
            "producer_as_of_date_mismatch",
            "producer_durable_receipt_unverified:RecommendationProvenanceError",
        )
    )
    assert not (
        natural_output / "recommendation" / "runs" / f"{RESULT_ID}.json"
    ).exists()
    assert not natural_journal.exists()

    historical_output = tmp_path / "historical-output"
    historical_journal = tmp_path / "historical-journal.jsonl"
    historical_args = _args(historical_output, tmp_path / "historical-data", config_path)
    historical_args.extend(
        [
            "--historical-research",
            "--journal-path",
            str(historical_journal),
            "--evidence-db",
            str(tmp_path / "historical-evidence.sqlite"),
        ]
    )

    historical_code = module.main(historical_args)
    historical_payload = json.loads(capsys.readouterr().out)
    assert historical_code == 0, historical_payload
    assert historical_payload["temporal_mode"] == (
        "historical_research_not_as_if_available"
    )
    assert historical_payload["cutoff_selection"] == "explicit_historical_cutoff"
    assert historical_payload["cutoff_policy"] == "explicit_historical_research"
    assert _FakeRecommendationProducer.calls == 2
