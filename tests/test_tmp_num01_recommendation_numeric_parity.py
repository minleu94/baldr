"""TMP-NUM-01 exact legacy numeric vectors through real recommendation callers.

Oracle provenance (read-only sources):

* ``docs/01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/
  R002_IMPLEMENTATION_REPORT.md`` records the pre-R020 boundary vectors
  50.0049/50.0050/50.0051, ``numpy.float64(91.5)``, and Decimal 70.0100
  quantum. It records historical R002 test SHA-256
  E438EE6B742D73C1676FEBAF85314F1B7048A1293D7C7D9605CC57EDFA8B37E5; that
  test blob is absent from the report's ending Git tree, so this test does not
  claim to reproduce or re-hash those historical bytes.
* The pre-R002 implementation in commit
  d81c896145e2f42a30da5518d03f3b0a6d0ebd5b computes
  ``Decimal(str(value)) * 100`` and applies ``ROUND_HALF_UP``. Its earlier
  committed tests in 2f738097d7565a6a98591a116e9ccaf2ba03cd54 independently
  lock 60.005 -> 6001, 0 -> 0, and 100 -> 10000. The expected values below
  follow that source algorithm and the archived R002 boundary report.
* R020 reports native-oracle passes on Windows CPython 3.11.9 with NumPy
  1.26.4 and 2.3.5. These are separate profile checks; no cross-version
  equality is asserted.

The first CLI test uses an isolated producer fixture and retains each real
caller's postprocess, save, canonical wire codec, query readback, and
personalization delivery/readback path. Separate scheduled and historical
personalization tests construct the real RecommendationService with fixed
market/scorer inputs. The personalization route injects only a named rule-only
calibration dependency backed by a verified test lineage; it covers the
historical ``population_only`` delivery path, not default ML inference or
natural ``linked_prediction`` behavior. The service tests also pin the
historical quantile and tie-break oracle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal
import json
import logging
from pathlib import Path
import sqlite3
import shutil
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import numpy as np
import pytest


NUMERIC_VECTOR = (
    ("BOUNDARY_HIGH", Decimal("50.0051")),
    ("TIE_FIRST", Decimal("50.0050")),
    ("TIE_SECOND", Decimal("50.0050")),
    ("BOUNDARY_LOW", Decimal("50.0049")),
)
EXPECTED_ORDER = tuple(code for code, _score in NUMERIC_VECTOR)
NUMERIC_TEXTS = tuple(str(score) for _code, score in NUMERIC_VECTOR)
CONSUMER_NUMERIC_VECTOR = (
    ("FLOAT64_COMPAT", np.float64(91.5)),
    ("DECIMAL_QUANTUM", Decimal("70.0100")),
    *NUMERIC_VECTOR,
)
CONSUMER_EXPECTED_ORDER = tuple(
    code for code, _score in CONSUMER_NUMERIC_VECTOR
)
CONSUMER_NUMERIC_TEXTS = tuple(
    str(score) for _code, score in CONSUMER_NUMERIC_VECTOR
)


@pytest.fixture
def _safe_canonical_store_root() -> Any:
    """Use a short repo-local temp root required by Windows no-follow reads."""

    workspace = Path(__file__).resolve().parents[1]
    root = workspace / f".tmp_num01_{uuid4().hex}"
    if root.exists():
        raise RuntimeError("refusing to reuse a pre-existing numeric test root")
    preexisting_handlers = {
        id(handler)
        for logger_value in logging.Logger.manager.loggerDict.values()
        if isinstance(logger_value, logging.Logger)
        for handler in logger_value.handlers
    }
    root.mkdir()
    try:
        yield root
    finally:
        resolved_workspace = workspace.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
        if (
            resolved_root.parent != resolved_workspace
            or not resolved_root.name.startswith(".tmp_num01_")
        ):
            raise RuntimeError("refusing to remove a path outside this test's temp root")
        for logger_value in logging.Logger.manager.loggerDict.values():
            if not isinstance(logger_value, logging.Logger):
                continue
            for handler in tuple(logger_value.handlers):
                if id(handler) in preexisting_handlers:
                    continue
                filename = getattr(handler, "baseFilename", None)
                if not filename:
                    continue
                try:
                    handler_path = Path(filename).resolve(strict=False)
                    handler_path.relative_to(resolved_root)
                except ValueError:
                    continue
                logger_value.removeHandler(handler)
                handler.close()
        shutil.rmtree(resolved_root)


def _install_numeric_producer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt_date: str,
    numeric_vector: tuple[tuple[str, object], ...] = NUMERIC_VECTOR,
) -> tuple[type[Any], Any, Any]:
    """Inject exact fixed candidates into the existing caller-test producer."""

    import test_personalization_generation_cli as fixture_module

    from app_module.dtos import RecommendationDTO
    from app_module.v4_evidence_identity import build_recommendation_universe_identity
    from decision_module.recommendation import contracts as decision_contracts
    from decision_module.recommendation import evaluate as decision_evaluate

    base_receipt_builder = fixture_module._receipt
    latest_receipt: list[Any] = []

    def build_numeric_receipt() -> Any:
        base = base_receipt_builder()
        source = base.payload
        source_row = dict(source["projections"][0])
        from datetime import date, timedelta

        feature_date = (date.fromisoformat(receipt_date) - timedelta(days=1)).isoformat()
        codes = [code for code, _score in numeric_vector]
        snapshot = fixture_module.HistoricalRawSnapshot(
            decision_date=receipt_date,
            feature_as_of_date=feature_date,
            prices=tuple(
                fixture_module.HistoricalPriceObservation(
                    symbol=code,
                    trading_date=feature_date,
                    open_price=Decimal("100"),
                    high_price=Decimal("101"),
                    low_price=Decimal("99"),
                    close_price=Decimal("100"),
                    volume=1_000,
                    turnover_amount_minor=100_000,
                )
                for code in codes
            ),
            technicals=(),
            market=(),
            industries=(),
            source_fingerprint="sha256:" + ("1" * 64),
            query_count=len(codes),
        )
        inference = fixture_module.build_inference_provenance(
            snapshot=snapshot,
            feature_rows=tuple(
                {
                    "symbol": code,
                    "decision_date": receipt_date,
                    "feature_as_of_date": feature_date,
                    "feature_available_date": feature_date,
                    "values": (("momentum_bp", 100),),
                }
                for code in codes
            ),
            feature_schema=(("momentum_bp", "int", "bp"),),
            feature_registry_hash="sha256:" + ("2" * 64),
            cost_scenario_hash=fixture_module.COST_HASH,
            probability_transform_id=fixture_module.PROBABILITY_TRANSFORM_ID,
        )
        training = fixture_module.build_training_provenance(lineage_payload=None)
        compatibility = fixture_module.validate_provenance_compatibility(
            training,
            inference,
            expected_cost_scenario_hash=fixture_module.COST_HASH,
            expected_probability_transform_id=fixture_module.PROBABILITY_TRANSFORM_ID,
        )
        projections = []
        for code, _score in numeric_vector:
            row = dict(source_row)
            row["stock_code"] = code
            row["prediction_id"] = str(uuid5(NAMESPACE_URL, f"tmp-num01:{code}"))
            projections.append(row)
        receipt = fixture_module.build_inference_projection_receipt(
            decision_date=receipt_date,
            result_id=fixture_module.RESULT_ID,
            candidate_identity=source["candidate_identity"],
            training_provenance=training,
            inference_provenance=inference,
            compatibility=compatibility,
            projections=tuple(projections),
        )
        latest_receipt[:] = [receipt]
        return receipt

    monkeypatch.setattr(fixture_module, "_receipt", build_numeric_receipt)

    class NumericProducer(fixture_module._FakeRecommendationProducer):
        calls = 0

        def _produce(self, config: dict[str, Any], **kwargs: Any) -> list[Any]:
            super()._produce(config, **kwargs)
            result_date = (
                str(kwargs.get("as_of_date") or "2025-02-10")[:10]
            )
            scheduled = config.get("strategy_version_id") == (
                "scheduled-recommendation-default-v1"
            )
            if scheduled:
                result_date = "2026-09-21"
                self.last_run_context.update(
                    {
                        "run_started_at": "2026-09-22T09:04:10.000000+00:00",
                        "available_at": "2026-09-22T09:04:30.000000+00:00",
                        "captured_at": "2026-09-22T09:04:30.000000+00:00",
                        "decision_at": "2026-09-22T09:05:06.000000+00:00",
                    }
                )
                self._personalization_execution_clocks = {
                    "run_started_at": self.last_run_context["run_started_at"],
                    "available_at": self.last_run_context["available_at"],
                }

            if config.get("strategy_version_id"):
                self.last_run_context["strategy_version_id"] = str(
                    config["strategy_version_id"]
                )
            self.last_run_context["as_of_date"] = result_date
            self.last_run_context["data_date"] = result_date
            selected_codes = [code for code, _score in numeric_vector]
            explicit_universe = kwargs.get("universe")
            selection_mode = (
                "explicit_universe" if explicit_universe is not None else "top_max_stocks"
            )
            self.last_run_context.update(
                build_recommendation_universe_identity(
                    decision_date=result_date,
                    selection_mode=selection_mode,
                    industry_filter="全部",
                    max_stocks=int(kwargs["max_stocks"]),
                    requested_codes=explicit_universe,
                    selected_codes=sorted(selected_codes),
                    source_provider_id="generation-cli-test-provider",
                )
            )
            self.last_run_context["universe_spec"].update(
                {
                    "codes": sorted(explicit_universe or []) or None,
                    "selected_codes": sorted(selected_codes),
                    "max_stocks": int(kwargs["max_stocks"]),
                    "selection_mode": selection_mode,
                    "industry_filter": "全部",
                }
            )
            assert latest_receipt
            self.last_run_context["calibration_projection_rows"] = {
                str(row["stock_code"]): dict(row)
                for row in latest_receipt[0].payload["projections"]
            }

            return [
                RecommendationDTO(
                    stock_code=code,
                    stock_name=code,
                    close_price=Decimal("100.0000"),
                    price_change=Decimal("-0.0000001"),
                    total_score=score,
                    indicator_score=Decimal("12345678901234567890.0000000001"),
                    pattern_score=Decimal("0.0000000001"),
                    volume_score=Decimal("70.0100"),
                    recommendation_reasons="TMP-NUM-01 fixed vector",
                    industry="synthetic",
                    regime_match=True,
                )
                for code, score in numeric_vector
            ]

        def _run_recommendation_body_result(self, **kwargs: Any) -> Any:
            original_evaluator = decision_evaluate.RecommendationEvaluator

            class EvidenceEvaluator(original_evaluator):
                def evaluate_batch_result(
                    self, outcomes: tuple[Any, ...], policy: Any
                ) -> Any:
                    enriched = []
                    for outcome in outcomes:
                        assessment = outcome.assessment
                        if assessment is None or outcome.score is None:
                            enriched.append(outcome)
                            continue
                        reason = "recommendation_selected"
                        evidence = {
                            "stock_code": outcome.stock_code,
                            "stock_name": outcome.stock_code,
                            "status": "pass",
                            "reason_codes": [reason],
                            "quality": "observed",
                            "stage": "final_selection",
                            "threshold_name": "",
                            "observed_value": "",
                            "required_value": "",
                            "total_score": str(outcome.score.ordering_value),
                            "score_bp": None,
                            "score_percentile_bp": None,
                            "eligible_universe_size": len(outcomes),
                            "threshold_mode": "fixed",
                            "warnings": [],
                            "industry": "synthetic",
                            "as_of_date": policy.decision_date_text,
                            "data_fingerprint": "generation-cli-test-data-fingerprint",
                        }
                        legacy = decision_contracts.FilterOutcome(
                            filter_id="legacy:final_selection",
                            passed=True,
                            reason=reason,
                            evidence=evidence,
                        )
                        complete_assessment = replace(
                            assessment,
                            filter_outcomes={"legacy:final_selection": legacy},
                        )
                        enriched.append(
                            replace(outcome, assessment=complete_assessment)
                        )
                    return super().evaluate_batch_result(tuple(enriched), policy)

            decision_evaluate.RecommendationEvaluator = EvidenceEvaluator
            try:
                return super()._run_recommendation_body_result(**kwargs)
            finally:
                decision_evaluate.RecommendationEvaluator = original_evaluator

    NumericProducer.calls = 0
    return NumericProducer, fixture_module, latest_receipt


def _saved_items(read_model: Any) -> tuple[Any, ...]:
    assert read_model is not None
    assert read_model.execution is not None
    assert read_model.execution.decision is not None
    return read_model.execution.decision.items


def _assert_numeric_wire_and_readback(
    read_model: Any,
    raw_payload: bytes,
    *,
    expected_order: tuple[str, ...] = EXPECTED_ORDER,
    score_texts: tuple[str, ...] = NUMERIC_TEXTS,
) -> None:
    items = _saved_items(read_model)
    assert tuple(item.stock_code for item in items) == expected_order
    assert tuple(str(item.rule_score) for item in items) == score_texts
    assert all(type(item.rule_score) is Decimal for item in items)
    assert all(str(item.close_price) == "100.0000" for item in items)
    assert all(str(item.price_change) == "-1E-7" for item in items)
    assert all(
        str(item.indicator_score) == "12345678901234567890.0000000001"
        for item in items
    )
    assert all(str(item.pattern_score) == "1E-10" for item in items)
    assert all(str(item.volume_score) == "70.0100" for item in items)
    assert all(item.confidence is None for item in items)

    # The read model is decoded from the saved artifact. Pin the exact wire
    # spellings as well as Decimal values, including exponent/scale details.
    decoded_wire = json.loads(raw_payload.decode("utf-8"))
    wire_text = json.dumps(decoded_wire, sort_keys=True, separators=(",", ":"))
    expected_decimal_texts = (
        *score_texts,
        "-1E-7",
        "1E-10",
        "12345678901234567890.0000000001",
        "70.0100",
    )
    for expected in (
        f'"$decimal":"{score_text}"' for score_text in expected_decimal_texts
    ):
        assert expected in wire_text


def _install_real_service_test_inputs(
    monkeypatch: pytest.MonkeyPatch,
    caller_module: Any,
    *,
    source_order: tuple[str, ...],
    calibration_consumer: Any | None = None,
) -> dict[str, Any]:
    """Inject only a fixed market frame and per-stock deterministic scorer."""

    import pandas as pd
    from app_module.recommendation.input_preparation import (
        build_default_recommendation_input_preparer,
    )
    from app_module.recommendation_service import (
        RecommendationService as RealRecommendationService,
    )
    from types import SimpleNamespace

    cutoff = pd.Timestamp("2026-09-22")
    dates = pd.bdate_range(end=cutoff, periods=25)
    rows: list[dict[str, object]] = []
    for code in source_order:
        for current_date in dates:
            rows.append(
                {
                    "日期": current_date,
                    "available_date": current_date,
                    "證券代號": code,
                    "證券名稱": f"{code}_NAME",
                    "收盤價": Decimal("100.00"),
                    "成交股數": 1000,
                }
            )
    frame = pd.DataFrame(
        rows,
        columns=[
            "日期",
            "available_date",
            "證券代號",
            "證券名稱",
            "收盤價",
            "成交股數",
        ],
    )

    class FixedMarketProvider:
        def __call__(self) -> Any:
            return frame.copy(deep=True)

    class FixedIndustryProvider:
        def filter_stocks_by_industry(
            self, stock_codes: Any, _industry: str
        ) -> list[str]:
            return [str(code) for code in stock_codes]

        def get_all_industries(self) -> list[str]:
            return []

        def get_stock_industries(self, _stock_code: str) -> list[str]:
            return []

        def get_industry_performance(
            self, _industry: str, *, date: str
        ) -> dict[str, object]:
            return {}

    class FixedRegimeProvider:
        def detect_regime(self) -> Any:
            return SimpleNamespace(
                regime="Trend", confidence=0.5, details={},
            )

        def get_strategy_config(self, _regime: str) -> dict[str, object]:
            return {}

    provider = FixedMarketProvider()
    scores = dict(CONSUMER_NUMERIC_VECTOR)
    scorer_calls: list[str] = []
    services: list[Any] = []

    def build_preparer(config: Any, **_kwargs: Any) -> Any:
        return build_default_recommendation_input_preparer(
            config,
            market_data_provider=provider,
        )

    def service_factory(
        config: Any,
        *,
        input_preparer: Any,
        regime_service: Any = None,
        **_kwargs: Any,
    ) -> Any:
        if input_preparer.market_data_provider is not provider:
            raise AssertionError("test market provider must be shared by preparer/service")
        service = RealRecommendationService(
            config,
            industry_mapper=FixedIndustryProvider(),
            market_data_provider=provider,
            calibration_consumer=calibration_consumer,
            input_preparer=input_preparer,
            regime_service=regime_service or FixedRegimeProvider(),
        )

        def score_stock(stock_frame: Any, _runtime_config: dict[str, object]) -> Any:
            code = str(stock_frame.iloc[-1]["證券代號"])
            scorer_calls.append(code)
            source_dates = pd.to_datetime(stock_frame["日期"])
            available_dates = pd.to_datetime(stock_frame["available_date"])
            if source_dates.max() > cutoff or available_dates.max() > cutoff:
                raise AssertionError("scorer received market data beyond the cutoff")
            score = scores[code]
            return pd.DataFrame(
                [
                    {
                        "FinalScore": score,
                        "TotalScore": score,
                        "IndicatorScore": Decimal(
                            "12345678901234567890.0000000001"
                        ),
                        "PatternScore": Decimal("0.0000000001"),
                        "VolumeScore": Decimal("70.0100"),
                        "收盤價": Decimal("100.0000"),
                    }
                ]
            )

        service.strategy_configurator.generate_recommendations = score_stock
        services.append(service)
        return service

    monkeypatch.setattr(
        caller_module,
        "build_default_recommendation_input_preparer",
        build_preparer,
    )
    monkeypatch.setattr(
        caller_module,
        "RegimeService",
        lambda _config, **_kwargs: FixedRegimeProvider(),
    )
    monkeypatch.setattr(caller_module, "RecommendationService", service_factory)
    return {"frame": frame, "scorer_calls": scorer_calls, "services": services}


def _write_real_service_source_database(path: Path, stock_codes: tuple[str, ...]) -> None:
    """Write isolated historical inputs for the service's real ML snapshot read."""

    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    dates = tuple(
        day.date()
        for day in pd.bdate_range(end="2026-09-22", periods=25)
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                成交股數 INTEGER,
                成交金額 INTEGER,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                RSI TEXT,
                MACD TEXT,
                ADX TEXT
            );
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL,
                收盤指數 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE industry_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT,
                收盤指數 TEXT
            );
            """
        )
        for day_index, current_day in enumerate(dates):
            date_text = current_day.strftime("%Y%m%d")
            connection.execute(
                "INSERT INTO market_indices VALUES (?, ?, ?)",
                (date_text, str(10_000 + day_index), str(10_000 + day_index)),
            )
            for stock_index, stock_code in enumerate(stock_codes):
                close = 100 + day_index + stock_index
                connection.execute(
                    "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        date_text,
                        stock_code,
                        1_000 + day_index,
                        close * 100,
                        str(close - 1),
                        str(close + 1),
                        str(close - 2),
                        str(close),
                    ),
                )
                connection.execute(
                    "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
                    (date_text, stock_code, "55", "1.5", "20"),
                )


def _build_rule_only_test_calibration_consumer(
    *,
    fixture_root: Path,
    data_root: Path,
    receipt_root: Path,
    decision_date: str,
) -> tuple[Any, dict[str, Any]]:
    """Build a nominal test consumer with real verified lineage, no ML prediction."""

    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationConsumer,
        RecommendationCalibrationProjection,
    )
    from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
    from ml_module.recommendation_inference_provenance import (
        build_training_provenance,
        validate_provenance_compatibility,
    )
    from ml_module.recommendation_training_lineage import (
        read_recommendation_training_lineage,
    )
    from test_recommendation_service_calibration_integration import (
        _core_feature_samples,
        _verified_candidate,
    )

    registry = CORE_LONG_HISTORY_FEATURE_REGISTRY
    trained_result, candidate_root, candidate_metadata = _verified_candidate(
        fixture_root,
        candidate_day="2026-09-21",
        training_as_of="2026-09-21",
        samples=_core_feature_samples(),
        feature_names=registry.canonical_ids,
        feature_schema=registry.canonical_schema,
        feature_registry_hash=registry.registry_hash,
        dataset_id="tmp-num01-personal-rule-only",
    )
    del trained_result  # The candidate is a verified lineage fixture, never loaded or inferred.
    lineage_path = Path(str(candidate_metadata["training_lineage_manifest_path"]))
    lineage = read_recommendation_training_lineage(
        lineage_path,
        expected_manifest_hash=str(
            candidate_metadata["training_lineage_manifest_hash"]
        ),
        expected_dataset_hash=str(candidate_metadata["dataset_hash"]),
        expected_candidate_id=str(candidate_metadata["candidate_id"]),
    )
    assert lineage.payload["decision_date"] <= decision_date
    assert lineage.payload["training_as_of"] <= decision_date
    training_provenance = build_training_provenance(
        lineage_payload=lineage.payload,
        manifest_hash=lineage.manifest_hash,
        manifest_path=str(lineage_path),
        candidate_payload=candidate_metadata,
    )
    assert training_provenance["status"] == "verified"
    assert training_provenance["label_registry_hash"]
    assert training_provenance["label_contract_id"]
    assert training_provenance["return_basis"]

    candidate_identity = {
        "kind": "active_model",
        "pointer_version": "tmp-num01-test-dependency-only",
        "candidate_id": str(candidate_metadata["candidate_id"]),
        "candidate_root": str(candidate_root),
        "candidate_manifest_hash": str(candidate_metadata["manifest_hash"]),
        "candidate_artifact_hash": str(candidate_metadata["artifact_hash"]),
        "candidate_freeze_hash": str(candidate_metadata["candidate_freeze_hash"]),
        "dataset_hash": str(candidate_metadata["dataset_hash"]),
        "model_id": str(candidate_metadata["model_id"]),
        "cost_scenario_hash": str(candidate_metadata["cost_scenario_hash"]),
        "cost_scenario_id": str(candidate_metadata["cost_scenario_id"]),
        "cost_scenario_version": str(candidate_metadata["cost_scenario_version"]),
        "training_provenance": training_provenance,
    }
    pointer_sentinel = receipt_root / "uncreated-active-pointer.json"
    pointer_sentinel.parent.mkdir(parents=True, exist_ok=True)

    class RuleOnlyTestCalibrationConsumer(RecommendationCalibrationConsumer):
        """Test-only identity/projection dependency; it never predicts with a model."""

        def __init__(self) -> None:
            super().__init__(
                pointer_path=pointer_sentinel,
                feature_schema=registry.canonical_schema,
                feature_registry_hash=registry.registry_hash,
                data_root=data_root,
            )
            self.projection_outputs: dict[str, RecommendationCalibrationProjection] = {}
            self.inference_provenance_seen: dict[str, Any] | None = None

        def active_identity(self, *, decision_date: str) -> dict[str, Any]:
            assert decision_date == decision_date_expected
            return dict(candidate_identity)

        def active_cost_scenario(self, *, decision_date: str) -> None:
            assert decision_date == decision_date_expected
            return None

        def active_after_cost_baseline(self, *, decision_date: str) -> None:
            assert decision_date == decision_date_expected
            return None

        def project_many(self, **kwargs: Any) -> dict[str, RecommendationCalibrationProjection]:
            assert kwargs["decision_date"] == decision_date_expected
            assert kwargs["selection_authority"] == "rule_top_n"
            inference_provenance = dict(kwargs["inference_provenance"])
            assert inference_provenance["decision_date"] == decision_date_expected
            compatibility = validate_provenance_compatibility(
                training_provenance,
                inference_provenance,
                expected_cost_scenario_hash=str(
                    training_provenance["cost_scenario_hash"]
                ),
                expected_probability_transform_id=str(
                    inference_provenance["probability_transform_id"]
                ),
            )
            assert compatibility["status"] == "verified"
            self.inference_provenance_seen = inference_provenance
            outputs: dict[str, RecommendationCalibrationProjection] = {}
            for stock_code in sorted(kwargs["feature_values_by_symbol"]):
                outputs[stock_code] = RecommendationCalibrationProjection(
                    stock_code=stock_code,
                    ranking_score_bp=None,
                    ranking_percentile_bp=kwargs[
                        "ranking_percentile_by_symbol"
                    ].get(stock_code),
                    ranking_method="rule_only",
                    calibrated_probability_bp=None,
                    calibrated_probability_status="unavailable",
                    after_cost_profit_probability_bp=None,
                    after_cost_profit_probability_status="unavailable",
                    confidence_tier="unavailable",
                    evidence_confidence="missing",
                    sample_size=None,
                    horizon="20 trading days",
                    cost_basis="verified_test_lineage_no_prediction",
                    cost_basis_bp=None,
                    model_version="",
                    dataset_version="",
                    source_trace=("tmp_num01_test_rule_only_dependency",),
                    status="rule_only",
                    cost_scenario_hash=str(training_provenance["cost_scenario_hash"]),
                    training_provenance=training_provenance,
                    inference_provenance=inference_provenance,
                    provenance_compatibility=compatibility,
                    provenance_status="verified",
                    label_registry_hash=str(
                        training_provenance["label_registry_hash"]
                    ),
                    label_contract_id=str(training_provenance["label_contract_id"]),
                    return_basis=str(training_provenance["return_basis"]),
                )
            self.projection_outputs = outputs
            return outputs

    decision_date_expected = decision_date
    return RuleOnlyTestCalibrationConsumer(), candidate_identity


def _assert_real_service_numeric_readback(
    read_model: Any,
    raw_payload: bytes,
) -> None:
    """Pin the archived quantile order, exact score values, and wire decimals."""

    expected_order = (
        "FLOAT64_COMPAT",
        "DECIMAL_QUANTUM",
        "BOUNDARY_HIGH",
        "TIE_FIRST",
        "TIE_SECOND",
        "BOUNDARY_LOW",
    )
    expected_scores = (
        "91.5",
        "70.0100",
        "50.0051",
        "50.0050",
        "50.0050",
        "50.0049",
    )
    expected_percentiles = (10000, 8334, 6667, 6667, 6667, 1667)
    items = _saved_items(read_model)
    assert tuple(item.stock_code for item in items) == expected_order
    assert tuple(str(item.rule_score) for item in items) == expected_scores
    assert all(type(item.rule_score) is Decimal for item in items)
    assert tuple(item.score_percentile_bp for item in items) == expected_percentiles
    assert all(item.threshold_mode == "quantile" for item in items)
    assert all(item.ranking_method == "nearest_rank" for item in items)
    assert all(item.eligible_universe_size == 6 for item in items)
    assert all(str(item.indicator_score) == "12345678901234567890.0000000001" for item in items)
    assert all(str(item.pattern_score) == "1E-10" for item in items)
    assert all(str(item.volume_score) == "70.0100" for item in items)
    assert all(item.confidence is None for item in items)

    decoded_wire = json.loads(raw_payload.decode("utf-8"))
    wire_text = json.dumps(decoded_wire, sort_keys=True, separators=(",", ":"))
    for expected in (
        f'"$decimal":"{score_text}"' for score_text in expected_scores
    ):
        assert expected in wire_text
    for expected in (
        '"$decimal":"12345678901234567890.0000000001"',
        '"$decimal":"1E-10"',
        '"$decimal":"70.0100"',
    ):
        assert expected in wire_text


def test_half_up_vector_round_trips_through_scheduled_and_personalization_callers(
    _safe_canonical_store_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    from decision_module.score_threshold_policy import quantize_score_to_basis_points
    from app_module.recommendation.composition import build_recommendation_composition
    from scripts.scheduled import run_scheduled_recommendation_snapshot as scheduled
    import scripts.run_personalization_recommendation as personalization

    assert tuple(
        quantize_score_to_basis_points(score)
        for score in (
            Decimal("50.0049"),
            Decimal("50.0050"),
            Decimal("50.0051"),
            np.float64(91.5),
            Decimal("70.0100"),
        )
    ) == (5000, 5001, 5001, 9150, 7001)

    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv(
        "DATA_ROOT", str(_safe_canonical_store_root / "ignored-data-root")
    )

    schedule_date = "2026-09-21"
    producer_type, fixture_module, receipt_box = _install_numeric_producer(
        monkeypatch,
        receipt_date=schedule_date,
        numeric_vector=CONSUMER_NUMERIC_VECTOR,
    )
    monkeypatch.setattr(scheduled, "RecommendationService", producer_type)
    monkeypatch.setattr(
        scheduled,
        "scheduled_now",
        lambda: datetime(2026, 9, 22, 9, 4, tzinfo=timezone.utc),
    )
    original_default_config = scheduled._scheduled_default_config

    def scheduled_config_with_fixed_result() -> dict[str, Any]:
        value = original_default_config()
        value["result_id"] = fixture_module.RESULT_ID
        return value

    monkeypatch.setattr(
        scheduled, "_scheduled_default_config", scheduled_config_with_fixed_result
    )
    scheduled_composition: dict[str, Any] = {}
    original_build_composition = scheduled.build_recommendation_composition

    def capture_scheduled_composition(config: Any) -> Any:
        composition = original_build_composition(config)
        scheduled_composition["value"] = composition
        return composition

    monkeypatch.setattr(
        scheduled, "build_recommendation_composition", capture_scheduled_composition
    )
    schedule_root = _safe_canonical_store_root / "scheduled"
    assert scheduled.main(
        [
            "--data-root",
            str(_safe_canonical_store_root / "scheduled-data"),
            "--output-root",
            str(schedule_root),
            "--max-stocks",
            "25",
            "--top-n",
            str(len(CONSUMER_NUMERIC_VECTOR)),
        ]
    ) == 0
    schedule_payload = json.loads(capsys.readouterr().out)
    assert schedule_payload["status"] == "passed"
    assert schedule_payload["recommendations_count"] == len(CONSUMER_NUMERIC_VECTOR)
    assert receipt_box
    scheduled_composition_value = scheduled_composition["value"]
    scheduled_read_model = scheduled_composition_value.queries.get(
        fixture_module.RESULT_ID
    )
    scheduled_raw = scheduled_composition_value.store.read_artifact(
        fixture_module.RESULT_ID
    )
    assert scheduled_raw is not None
    _assert_numeric_wire_and_readback(
        scheduled_read_model,
        scheduled_raw,
        expected_order=CONSUMER_EXPECTED_ORDER,
        score_texts=CONSUMER_NUMERIC_TEXTS,
    )

    # Run the actual personalization CLI with a fresh output root and the same
    # independently fixed vector. Its producer, receipt, save, query and
    # delivery readback are all isolated below tmp_path.
    personalization_date = "2025-02-10"
    personal_producer_type, personal_fixture, personal_receipt_box = (
        _install_numeric_producer(
            monkeypatch,
            receipt_date=personalization_date,
            numeric_vector=CONSUMER_NUMERIC_VECTOR,
        )
    )
    monkeypatch.setattr(
        personalization, "RecommendationService", personal_producer_type
    )
    personal_root = _safe_canonical_store_root / "personalization"
    personal_data_root = _safe_canonical_store_root / "personalization-data"
    config_path = _safe_canonical_store_root / "personalization-config.json"
    config_path.write_text(json.dumps({"filters": {}}), encoding="utf-8")
    journal_path = _safe_canonical_store_root / "personalization-journal.jsonl"
    evidence_path = _safe_canonical_store_root / "personalization-evidence.sqlite"
    personal_result = personalization.main(
        [
            "--data-root",
            str(personal_data_root),
            "--output-root",
            str(personal_root),
            "--config-json",
            str(config_path),
            "--result-id",
            personal_fixture.RESULT_ID,
            "--result-name",
            "TMP-NUM-01 numeric vector",
            "--as-of-date",
            personalization_date,
            "--max-stocks",
            "25",
            "--top-n",
            str(len(CONSUMER_NUMERIC_VECTOR)),
            "--scope-id",
            "tmp-num01-scope",
            "--scope-type",
            "local",
            "--delivery-id",
            "tmp-num01-delivery",
            "--request-id",
            "tmp-num01-request",
            "--profile",
            "test",
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
        ]
    )
    personal_payload = json.loads(capsys.readouterr().out)
    assert personal_result == 0, personal_payload
    assert personal_payload["ok"] is True
    assert personal_payload["delivery_status"] == "delivered"
    assert tuple(row["stock_code"] for row in personal_payload["readback"]) == (
        CONSUMER_EXPECTED_ORDER
    )
    assert personal_receipt_box

    personal_composition = build_recommendation_composition(
        personalization._OutputPathConfig(personal_root / "_test")
    )
    personal_read_model = personal_composition.queries.get(personal_fixture.RESULT_ID)
    personal_raw = personal_composition.store.read_artifact(personal_fixture.RESULT_ID)
    assert personal_raw is not None
    _assert_numeric_wire_and_readback(
        personal_read_model,
        personal_raw,
        expected_order=CONSUMER_EXPECTED_ORDER,
        score_texts=CONSUMER_NUMERIC_TEXTS,
    )


def test_real_recommendation_service_numeric_vector_round_trips_through_scheduled_caller(
    _safe_canonical_store_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    """Keep the scheduled producer/evaluator/postprocess/save/query path real."""

    import tempfile

    from scripts.scheduled import run_scheduled_recommendation_snapshot as scheduled
    from app_module.recommendation.composition import build_recommendation_composition

    source_order = (
        "BOUNDARY_LOW",
        "TIE_SECOND",
        "FLOAT64_COMPAT",
        "BOUNDARY_HIGH",
        "TIE_FIRST",
        "DECIMAL_QUANTUM",
    )
    service_fixture = _install_real_service_test_inputs(
        monkeypatch,
        scheduled,
        source_order=source_order,
    )
    monkeypatch.setattr(tempfile, "tempdir", str(_safe_canonical_store_root))
    schedule_data_root = _safe_canonical_store_root / "scheduled-real-data"
    schedule_output_root = _safe_canonical_store_root / "scheduled-real-output"
    learning_root = _safe_canonical_store_root / "scheduled-real-learning"
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(schedule_data_root))
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(learning_root))
    monkeypatch.setattr(
        scheduled,
        "scheduled_now",
        lambda: datetime(2026, 9, 22, 9, 4, tzinfo=timezone.utc),
    )

    result_id = "tmp-num01-real-service-scheduled-v1"
    original_default_config = scheduled._scheduled_default_config

    def configured_numeric_fixture() -> dict[str, Any]:
        config = original_default_config()
        config["result_id"] = result_id
        # The test uses the normal quantile evaluator with its valid minimum
        # threshold, so the fixed source vector remains fully selectable.
        config["recommendation_ranking"] = {
            "threshold_mode": "quantile",
            "recommendation_min_percentile_bp": 0,
            "recommendation_min_universe_size": len(CONSUMER_NUMERIC_VECTOR),
            "recommendation_ranking_method": "nearest_rank",
        }
        return config

    monkeypatch.setattr(
        scheduled, "_scheduled_default_config", configured_numeric_fixture
    )

    compositions: list[Any] = []

    def capture_composition(config: Any) -> Any:
        composition = build_recommendation_composition(config)
        compositions.append(composition)
        return composition

    monkeypatch.setattr(
        scheduled, "build_recommendation_composition", capture_composition
    )
    assert scheduled.main(
        [
            "--data-root",
            str(schedule_data_root),
            "--output-root",
            str(schedule_output_root),
            "--max-stocks",
            str(len(CONSUMER_NUMERIC_VECTOR)),
            "--top-n",
            str(len(CONSUMER_NUMERIC_VECTOR)),
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["recommendations_count"] == len(CONSUMER_NUMERIC_VECTOR)
    assert len(service_fixture["services"]) == 1
    assert service_fixture["scorer_calls"] == list(source_order)
    assert len(compositions) == 1

    composition = compositions[0]
    read_model = composition.queries.get(result_id)
    raw_payload = composition.store.read_artifact(result_id)
    assert raw_payload is not None
    assert read_model is not None and read_model.execution is not None
    saved_context = read_model.execution.context
    assert saved_context.as_of_date is not None
    assert saved_context.as_of_date.isoformat() == "2026-09-22"
    assert saved_context.result_config_snapshot is not None
    saved_result_config = json.loads(
        saved_context.result_config_snapshot.raw_result_config_json
    )
    assert saved_result_config["temporal_mode"] == "natural_producer_clock"
    assert saved_result_config["cutoff_selection"] == (
        "producer_selected_latest_available_cutoff"
    )
    assert saved_result_config["cutoff_policy"] == "source_latest_available_exact"
    assert saved_result_config["data_as_of_date"] == "2026-09-22"
    _assert_real_service_numeric_readback(read_model, raw_payload)


def test_real_recommendation_service_numeric_vector_round_trips_through_personalization_caller(
    _safe_canonical_store_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
) -> None:
    """Run real producer and durable personal receipt with a rule-only test dependency."""

    from app_module.recommendation.composition import build_recommendation_composition
    from app_module.recommendation_calibration_consumer import (
        RecommendationCalibrationProjection,
    )
    from ml_module.recommendation_inference_provenance import (
        read_inference_projection_receipt,
    )
    import scripts.run_personalization_recommendation as personalization

    source_order = (
        "BOUNDARY_LOW",
        "TIE_SECOND",
        "FLOAT64_COMPAT",
        "BOUNDARY_HIGH",
        "TIE_FIRST",
        "DECIMAL_QUANTUM",
    )
    personal_data_root = _safe_canonical_store_root / "personalization-real-data"
    personal_output_root = _safe_canonical_store_root / "personalization-real-output"
    effective_data_root = personal_data_root / "_test"
    database_path = effective_data_root / "sqlite" / "twstock.db"
    _write_real_service_source_database(database_path, source_order)

    training_fixture_root = _safe_canonical_store_root / "personalization-training"
    receipt_root = _safe_canonical_store_root / "personalization-test-consumer"
    consumer, candidate_identity = _build_rule_only_test_calibration_consumer(
        fixture_root=training_fixture_root,
        data_root=effective_data_root,
        receipt_root=receipt_root,
        decision_date="2026-09-22",
    )
    service_fixture = _install_real_service_test_inputs(
        monkeypatch,
        personalization,
        source_order=source_order,
        calibration_consumer=consumer,
    )
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(personal_data_root))
    learning_root = _safe_canonical_store_root / "personalization-real-learning"
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(learning_root))

    result_id = "tmp-num01-real-service-personalization-v1"
    config_path = _safe_canonical_store_root / "personalization-real-config.json"
    config_path.write_text(
        json.dumps(
            {
                "filters": {},
                "cost_model_id": "cost_generation_cli",
                "benchmark_id": "TAIEX",
                "industry_benchmark_id": "industry_index",
                "horizon_days": 20,
                "recommendation_ranking": {
                    "threshold_mode": "quantile",
                    "recommendation_min_percentile_bp": 0,
                    "recommendation_min_universe_size": len(
                        CONSUMER_NUMERIC_VECTOR
                    ),
                    "recommendation_ranking_method": "nearest_rank",
                },
            }
        ),
        encoding="utf-8",
    )
    journal_path = _safe_canonical_store_root / "personalization-real-journal.jsonl"
    evidence_path = _safe_canonical_store_root / "personalization-real-evidence.sqlite"
    result = personalization.main(
        [
            "--data-root",
            str(personal_data_root),
            "--output-root",
            str(personal_output_root),
            "--config-json",
            str(config_path),
            "--result-id",
            result_id,
            "--result-name",
            "TMP-NUM-01 real-service numeric vector",
            "--as-of-date",
            "2026-09-22",
            "--historical-research",
            "--max-stocks",
            str(len(CONSUMER_NUMERIC_VECTOR)),
            "--top-n",
            str(len(CONSUMER_NUMERIC_VECTOR)),
            "--scope-id",
            "tmp-num01-real-service-scope",
            "--scope-type",
            "local",
            "--delivery-id",
            "tmp-num01-real-service-delivery",
            "--request-id",
            "tmp-num01-real-service-request",
            "--profile",
            "test",
            "--journal-path",
            str(journal_path),
            "--evidence-db",
            str(evidence_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert result == 0, payload
    assert payload["ok"] is True
    assert payload["delivery_status"] == "delivered"
    assert payload["temporal_mode"] == "historical_research_not_as_if_available"
    assert all(
        row["temporal_tier"] == "historical_research_only"
        and row["delivery_status"] == "delivered"
        for row in payload["readback"]
    )
    assert tuple(row["stock_code"] for row in payload["readback"]) == (
        CONSUMER_EXPECTED_ORDER
    )
    assert len(service_fixture["services"]) == 1
    assert service_fixture["scorer_calls"] == list(source_order)
    assert consumer.inference_provenance_seen is not None
    assert consumer.inference_provenance_seen["decision_date"] == "2026-09-22"
    assert consumer.projection_outputs
    assert all(
        type(projection) is RecommendationCalibrationProjection
        and projection.status == "rule_only"
        and projection.calibrated_probability_bp is None
        and projection.after_cost_profit_probability_bp is None
        for projection in consumer.projection_outputs.values()
    )
    assert not consumer.pointer_path.exists()
    receipt_paths = tuple(receipt_root.rglob("*.json"))
    assert len(receipt_paths) == 1
    receipt = read_inference_projection_receipt(
        receipt_paths[0],
        expected_decision_date="2026-09-22",
        expected_candidate_id=str(candidate_identity["candidate_id"]),
        expected_result_id=result_id,
    )
    assert tuple(row["stock_code"] for row in receipt.payload["projections"]) == tuple(
        sorted(CONSUMER_EXPECTED_ORDER)
    )
    assert all(
        row["status"] == "rule_only"
        and row["calibrated_probability_bp"] is None
        and row["after_cost_profit_probability_bp"] is None
        for row in receipt.payload["projections"]
    )
    assert receipt.payload["formal_order_allowed"] is False
    assert receipt.payload["production_action_allowed"] is False

    composition = build_recommendation_composition(
        personalization._OutputPathConfig(personal_output_root / "_test")
    )
    read_model = composition.queries.get(result_id)
    raw_payload = composition.store.read_artifact(result_id)
    assert raw_payload is not None
    _assert_real_service_numeric_readback(read_model, raw_payload)


def test_real_recommendation_service_quantile_order_matches_pre_r002_oracle(
    tmp_path: Path,
) -> None:
    """Exercise source-to-ranking order using the independently archived oracle.

    The pre-R002 ranking pipeline quantized Decimal scores to basis points,
    assigned percentile ``ceil(count(score_bp <= candidate_bp) / N * 10000)``,
    then ordered eligible rows by stock code ascending before score descending.
    These expectations are calculated from that source rule and the archived
    R002 boundary report, rather than copied from the current service output.
    """

    from test_recommendation_refactor_characterization import (
        DECISION_DATE,
        _matrix_by_code,
        _service,
    )

    # Deliberately unsorted source order catches accidental pass-through and
    # preserves a same-quantized-score tie across distinct raw Decimal values.
    source_codes = ("Q50D", "Q90", "Q20", "Q50B", "Q50A", "Q50C")
    source_scores = {
        "Q50C": Decimal("50.0051"),
        "Q90": Decimal("90.0000"),
        "Q20": Decimal("20.0000"),
        "Q50B": Decimal("50.0050"),
        "Q50A": Decimal("50.0049"),
        "Q50D": Decimal("50.0050"),
    }
    service, calls = _service(tmp_path, source_codes, source_scores)

    recommendations = service.run_recommendation(
        {
            "recommendation_ranking": {
                "threshold_mode": "quantile",
                "recommendation_min_percentile_bp": 8000,
                "recommendation_min_universe_size": 6,
                "recommendation_ranking_method": "nearest_rank",
            }
        },
        top_n=3,
        as_of_date=DECISION_DATE,
        result_id="tmp-num01-service-quantile-001",
    )

    assert calls == list(source_codes)
    assert [item.stock_code for item in recommendations] == ["Q90", "Q50C", "Q50B"]
    assert [
        (
            str(item.total_score),
            item.score_percentile_bp,
            item.eligible_universe_size,
            item.ranking_method,
        )
        for item in recommendations
    ] == [
        ("90.0000", 10000, 6, "nearest_rank"),
        ("50.0051", 8334, 6, "nearest_rank"),
        ("50.0050", 8334, 6, "nearest_rank"),
    ]

    # Half-up creates 5001 for both 50.0050 and 50.0051, while 50.0049
    # remains 5000. The equal-score Q50B/Q50D tie is resolved by code, so
    # Q50D follows the three-item cutoff despite being evaluated first.
    matrix = _matrix_by_code(service)
    assert {
        code: matrix[code]["score_percentile_bp"] for code in source_codes
    } == {
        "Q50D": 8334,
        "Q90": 10000,
        "Q20": 1667,
        "Q50B": 8334,
        "Q50A": 3334,
        "Q50C": 8334,
    }
    # score_bp is intentionally None in the historical matrix schema; the
    # separately pinned quantizer values above and the actual service ranking
    # establish the 5000/5001 boundary without changing that schema.
    assert all(matrix[code]["score_bp"] is None for code in source_codes)
    assert matrix["Q50D"]["status"] == "fail"
    assert matrix["Q50D"]["stage"] == "top_n_gate"
    assert matrix["Q50D"]["reason_codes"] == ["recommendation_outside_top_n"]
