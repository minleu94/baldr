from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

import pytest

import ml_module.current_observed_natural_research_fit as research_fit
from ml_module.feature_registry import CORE_LONG_HISTORY_FEATURE_REGISTRY
from ml_module.recommendation_calibration_training import RecommendationCalibrationSample
from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario
from ml_module.recommendation_probability_transform import (
    NULL_BENCHMARK_BASELINE_ID,
    NULL_BENCHMARK_PROBABILITY_BP,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


@pytest.fixture
def short_output_root() -> Iterator[Path]:
    # The runner intentionally persists several hash-scoped lineage layers;
    # keep this real-fit test short enough for native Windows path limits.
    with TemporaryDirectory(prefix="g9fit-") as directory:
        yield Path(directory)


def _fixture_batch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    count: int,
    start: date = date(2025, 1, 2),
    pending: bool = False,
) -> tuple[tuple[RecommendationCalibrationSample, ...], tuple[dict[str, str], ...]]:
    scenario = build_legacy_cost_scenario(50)
    samples: list[RecommendationCalibrationSample] = []
    references: list[dict[str, str]] = []
    payloads: dict[str, Mapping[str, Any]] = {}
    feature_count = len(CORE_LONG_HISTORY_FEATURE_REGISTRY.canonical_ids)

    decision = start
    for index in range(count):
        while decision.weekday() >= 5:
            decision += timedelta(days=1)
        capture_id = f"current-observed:{decision.isoformat()}:{index:04d}"
        capture_row_id = f"row-{index:04d}"
        row_id = f"current-observed-natural:{capture_id}:{capture_row_id}"
        sign = 1 if index % 2 else -1
        feature_values = tuple(
            (index + 1) * (slot + 1) * sign for slot in range(feature_count)
        )
        sample = RecommendationCalibrationSample.from_forward_return(
            row_id=row_id,
            symbol="2330",
            decision_date=decision.isoformat(),
            feature_as_of_date=(decision - timedelta(days=1)).isoformat(),
            feature_available_date=(decision - timedelta(days=1)).isoformat(),
            label_end_date=(decision + timedelta(days=20)).isoformat(),
            label_available_date=(decision + timedelta(days=20)).isoformat(),
            feature_values=feature_values,
            stock_return_bp=sign * 750,
            benchmark_return_bp=125,
            fixed_round_trip_cost_bp=50,
            observed_liquidity_cost_bp=None,
            rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
            rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
            source_quality=research_fit.CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
            cost_scenario=scenario,
        )
        samples.append(sample)
        capture_path = f"capture-{index:04d}.json"
        outcome_path = f"outcome-{index:04d}.json"
        capture_sha256 = "sha256:" + f"{index + 1:064x}"
        outcome_sha256 = "sha256:" + f"{index + 10_000:064x}"
        reference = {
            "capture_path": capture_path,
            "capture_sha256": capture_sha256,
            "capture_id": capture_id,
            "outcome_path": outcome_path,
            "outcome_sha256": outcome_sha256,
            "outcome_status": "pending" if pending else "matured",
            "verification_status": "verified_pending" if pending else "verified",
        }
        references.append(reference)
        outcome: dict[str, Any] = {
            "capture_row_id": capture_row_id,
            "symbol": sample.symbol,
            "capture_decision_date": sample.decision_date,
            "feature_as_of_date": sample.feature_as_of_date,
            "feature_available_date": sample.feature_available_date,
            "label_end_date": sample.label_end_date,
            "label_available_date": sample.label_available_date,
            "feature_values": list(sample.feature_values),
            "stock_return_bp": sample.stock_return_bp,
            "benchmark_return_bp": sample.benchmark_return_bp,
            "upside_label": sample.upside_label,
            "cost_scenario_hash": sample.cost_scenario_hash,
            "cost_scenario_id": sample.cost_scenario_id,
            "cost_scenario_version": sample.cost_scenario_version,
            "cost_basis": sample.cost_basis,
            "observed_liquidity_cost_bp": None,
            "estimated_round_trip_cost_twd": None,
            "estimated_round_trip_cost_bp": 50,
            "estimated_buy_cost_twd": None,
            "estimated_sell_cost_twd": None,
            "gross_buy_amount_twd": None,
            "gross_sell_amount_twd": None,
            "net_profit_twd": None,
            "after_cost_profit_label": None,
        }
        payloads[outcome_path] = {
            "schema_version": "recommendation-current-observed-natural-outcome-receipt.v1",
            "verification_status": reference["verification_status"],
            "status": reference["outcome_status"],
            "capture_id": capture_id,
            "capture_sha256": capture_sha256,
            "current_restated": True,
            "historical_pit_eligible": False,
            "formal_training_allowed": False,
            "research_only": True,
            "natural_outcome_only": True,
            "promotion_credit_created": False,
            "historical_replay_is_natural_evidence": False,
            "outcomes": [] if pending else [outcome],
        }
        decision += timedelta(days=1)

    def verify_receipt(
        path: str | Path,
        *,
        expected_sha256: str | None = None,
        capture_path: str | Path | None = None,
    ) -> Mapping[str, Any]:
        payload = payloads[str(path)]
        if expected_sha256 is not None:
            reference = next(item for item in references if item["outcome_path"] == str(path))
            if reference["outcome_sha256"] != expected_sha256:
                raise ValueError("fixture hash mismatch")
        if capture_path is not None:
            reference = next(item for item in references if item["outcome_path"] == str(path))
            if reference["capture_path"] != str(capture_path):
                raise ValueError("fixture capture mismatch")
        return payload

    monkeypatch.setattr(research_fit, "verify_current_observed_outcome_receipt", verify_receipt)
    return tuple(samples), tuple(references)


def _v2_fixture(
    *,
    symbol_count: int = 17,
    later_source_schema: str = research_fit._FEATURE_SNAPSHOT_SCHEMA_V2,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    symbols = [f"{index:04d}" for index in range(symbol_count)]
    capture_sha = "sha256:" + "c" * 64
    cohort_hash = "sha256:" + "d" * 64
    composition_sha = "sha256:" + "e" * 64
    feature_content_sha = "sha256:" + "f" * 64
    table_names = sorted(research_fit._CURRENT_OBSERVED_SOURCE_TABLES)
    entry_pins = {
        symbol: {
            "symbol": symbol,
            "source_date": "2026-10-05",
            "close_price_twd": "100.00",
            "source_row_sha256": "sha256:" + f"{index + 1:064x}",
        }
        for index, symbol in enumerate(symbols)
    }
    benchmark_pin = {
        "symbol": "TAIEX",
        "source_date": "2026-10-05",
        "close": "22000.00",
        "source_row_sha256": "sha256:" + "1" * 64,
    }
    feature_snapshot = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v2",
        "scope_mode": "verified_scheduled_snapshot_cohort",
        "content_sha256": feature_content_sha,
        "composition_sha256": composition_sha,
        "cohort_hash": cohort_hash,
        "cycle_id": "raw-cycle-20261005",
        "raw_run_id": "raw-cycle-20261005",
        "cycle_source_date": "2026-10-05",
        "snapshot_database_path": r"D:\research\snapshot.sqlite",
        "snapshot_database_sha256": "sha256:" + "2" * 64,
        "snapshot_receipt_path": r"D:\research\receipt.json",
        "snapshot_receipt_sha256": "sha256:" + "3" * 64,
        "source_context_envelope_path": r"D:\research\context.json",
        "source_context_envelope_sha256": "sha256:" + "4" * 64,
    }
    capture = {
        "schema_version": "recommendation-current-observed-input-capture.v2",
        "capture_id": "current-observed:2026-10-05:raw-cycle-20261005",
        "captured_at": "2026-10-05T16:00:00+08:00",
        "_verified_capture_sha256": capture_sha,
        "composition_sha256": composition_sha,
        "cohort_hash": cohort_hash,
        "scope_mode": "verified_scheduled_snapshot_cohort",
        "feature_snapshot_sha256": feature_content_sha,
        "symbols": symbols,
        "entry_price_pin_by_symbol": entry_pins,
        "benchmark_entry_price_pin": benchmark_pin,
        "source_contract_binding": {
            "scope_mode": "verified_scheduled_snapshot_cohort",
            "composition_sha256": composition_sha,
            "cohort_hash": cohort_hash,
            "current_observed_feature_snapshot": feature_snapshot,
        },
    }
    batches: list[dict[str, Any]] = []
    symbol_to_batch: dict[str, dict[str, Any]] = {}
    for ordinal, offset in enumerate(range(0, len(symbols), 16)):
        batch_symbols = symbols[offset : offset + 16]
        table_hashes = {
            table: "sha256:" + f"{ordinal * 10 + index + 10:064x}"
            for index, table in enumerate(table_names)
        }
        body: dict[str, Any] = {
            "schema_version": "recommendation-current-observed-outcome-query-batch.v1",
            "ordinal": ordinal,
            "symbols": batch_symbols,
            "row_count": len(batch_symbols),
            "query_identity_sha256": research_fit._hash_payload(
                {"symbols": batch_symbols, "source_rows_sha256_by_table": table_hashes}
            ),
            "source_rows_sha256_by_table": table_hashes,
            "input_entry_observation_sha256": research_fit._hash_payload(
                {
                    "entry_price_pin_by_symbol": {
                        symbol: entry_pins[symbol] for symbol in batch_symbols
                    },
                    "benchmark_entry_price_pin": benchmark_pin,
                }
            ),
        }
        batch = {**body, "batch_sha256": research_fit._hash_payload(body)}
        batches.append(batch)
        for symbol in batch_symbols:
            symbol_to_batch[symbol] = batch
    aggregate_sha = research_fit._hash_payload(
        {
            "schema_version": "recommendation-current-observed-outcome-query-composition.v1",
            "capture_symbols": symbols,
            "batches": batches,
        }
    )
    current_snapshot = {
        "schema_version": later_source_schema,
        "cycle_id": "later-cycle-20261103",
        "raw_run_id": "later-raw-run-20261103",
        "source_date": "2026-11-03",
        "decision_date": "2026-11-03",
        "feature_as_of_date": "2026-11-02",
        "observed_at": "2026-11-03T16:00:00+08:00",
        "local_observed_at": "2026-11-03T16:00:00+08:00",
        "discovery_status_path": r"D:\research\later\latest_status.json",
        "discovery_status_sha256": "sha256:" + "6" * 64,
        "cycle_terminal_path": r"D:\research\later\terminal.json",
        "cycle_terminal_sha256": "sha256:" + "7" * 64,
        "snapshot_database_path": r"D:\research\later\snapshot.sqlite",
        "snapshot_database_sha256": "sha256:" + "8" * 64,
        "snapshot_receipt_path": r"D:\research\later\receipt.json",
        "snapshot_receipt_sha256": "sha256:" + "9" * 64,
        "source_context_envelope_path": r"D:\research\later\context.json",
        "source_context_envelope_sha256": "sha256:" + "a" * 64,
        "feature_snapshot_sha256": "sha256:" + "b" * 64,
        "source_contract_path": r"D:\research\later\source-contract.json",
        "source_contract_file_sha256": "sha256:" + "c" * 64,
        "source_contract_content_sha256": "sha256:" + "d" * 64,
        "source_contract_binding_sha256": "sha256:" + "e" * 64,
        "resolver_session_proof": {"endpoint_date": "2026-11-02", "session_count": 20},
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "outcome_query_batches": batches,
        "outcome_query_batches_sha256": aggregate_sha,
    }
    if later_source_schema == research_fit._FEATURE_SNAPSHOT_SCHEMA_V1:
        current_snapshot["feature_source_rows_sha256_by_table"] = {
            table: "sha256:" + f"{index + 20:064x}"
            for index, table in enumerate(table_names)
        }
    else:
        current_snapshot["composition_sha256"] = "sha256:" + "f" * 64
    outcome_symbol = symbols[0]
    outcome_batch = symbol_to_batch[outcome_symbol]
    scenario = build_legacy_cost_scenario(50)
    feature_values = [index * 10 for index in range(20)]
    receipt = {
        "schema_version": "recommendation-current-observed-natural-outcome-receipt.v2",
        "verification_status": "verified",
        "status": "matured",
        "capture_id": capture["capture_id"],
        "capture_sha256": capture_sha,
        "evaluation_at": "2026-11-03T16:30:00+08:00",
        "current_restated": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "research_only": True,
        "natural_outcome_only": True,
        "promotion_credit_created": False,
        "historical_replay_is_natural_evidence": False,
        "current_observed_snapshot": current_snapshot,
        "outcomes": [
            {
                "capture_row_id": "row-v2-1",
                "symbol": outcome_symbol,
                "capture_decision_date": "2026-10-05",
                "feature_as_of_date": "2026-10-02",
                "feature_available_date": "2026-10-05",
                "label_end_date": "2026-11-02",
                "label_available_date": "2026-11-02",
                "feature_values": feature_values,
                "stock_return_bp": 750,
                "benchmark_return_bp": 125,
                "upside_label": 1,
                "cost_scenario_hash": scenario.scenario_hash,
                "cost_scenario_id": scenario.scenario_id,
                "cost_scenario_version": scenario.scenario_version,
                "cost_basis": "fixed_round_trip_bp",
                "observed_liquidity_cost_bp": None,
                "estimated_round_trip_cost_twd": None,
                "estimated_round_trip_cost_bp": 50,
                "estimated_buy_cost_twd": None,
                "estimated_sell_cost_twd": None,
                "gross_buy_amount_twd": None,
                "gross_sell_amount_twd": None,
                "net_profit_twd": None,
                "after_cost_profit_label": None,
                "label_source_batch_ordinal": outcome_batch["ordinal"],
                "label_source_batch_sha256": outcome_batch["batch_sha256"],
                "label_source_rows_sha256_by_table": dict(outcome_batch["source_rows_sha256_by_table"]),
            }
        ],
    }
    reference = {
        "capture_path": "capture-v2.json",
        "capture_sha256": capture_sha,
        "capture_id": capture["capture_id"],
        "outcome_path": "outcome-v2.json",
        "outcome_sha256": "sha256:" + "5" * 64,
        "outcome_status": "matured",
        "verification_status": "verified",
    }
    return capture, receipt, reference


def _verify_v2_fixture_references(
    monkeypatch: pytest.MonkeyPatch,
    capture: Mapping[str, Any],
    receipt: Mapping[str, Any],
    reference: Mapping[str, str],
) -> tuple[tuple[dict[str, str], ...], dict[str, Mapping[str, Any]]]:
    import ml_module.current_observed_feature_snapshot_composer as composer
    import ml_module.recommendation_calibration_evidence as evidence

    monkeypatch.setattr(
        research_fit,
        "verify_current_observed_outcome_receipt",
        lambda *_args, **_kwargs: receipt,
    )
    monkeypatch.setattr(
        evidence,
        "verify_current_observed_input_capture",
        lambda *_args, **_kwargs: capture,
    )
    monkeypatch.setattr(
        composer,
        "verify_current_observed_feature_snapshot_v2",
        lambda snapshot: snapshot,
    )
    return research_fit._verify_receipt_references((reference,))


def test_v2_outcome_receipt_verifies_full_batch_composition_and_row_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, receipt, reference = _v2_fixture()
    refs, rows = _verify_v2_fixture_references(monkeypatch, capture, receipt, reference)

    assert refs == (dict(reference),)
    assert len(rows) == 1
    outcome = next(iter(rows.values()))
    assert outcome["label_source_batch_ordinal"] == 0
    sample = RecommendationCalibrationSample.from_forward_return(
        row_id=next(iter(rows)),
        symbol=str(outcome["symbol"]),
        decision_date=str(outcome["capture_decision_date"]),
        feature_as_of_date=str(outcome["feature_as_of_date"]),
        feature_available_date=str(outcome["feature_available_date"]),
        label_end_date=str(outcome["label_end_date"]),
        label_available_date=str(outcome["label_available_date"]),
        feature_values=tuple(outcome["feature_values"]),
        stock_return_bp=int(outcome["stock_return_bp"]),
        benchmark_return_bp=int(outcome["benchmark_return_bp"]),
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=None,
        rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
        rule_baseline_id=NULL_BENCHMARK_BASELINE_ID,
        source_quality=research_fit.CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
        cost_scenario=build_legacy_cost_scenario(50),
    )
    research_fit._verify_sample_receipt_binding((sample,), refs, rows)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_batch", "do not cover the complete captured cohort"),
        ("aggregate_hash", "query composition hash mismatch"),
        ("row_batch", "not bound to its verified query batch"),
        ("feature_composition", "later v2 source composition is invalid"),
        ("later_source_schema", "later source feature snapshot schema is unsupported"),
        ("later_feature_hash", "later feature snapshot hash is invalid"),
        ("capture_composition", "capture feature composition identity is inconsistent"),
    ],
)
def test_v2_outcome_receipt_rejects_incomplete_or_mixed_batch_identity(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    capture, receipt, reference = _v2_fixture()
    receipt = json.loads(json.dumps(receipt))
    if mutation == "missing_batch":
        receipt["current_observed_snapshot"]["outcome_query_batches"].pop()
    elif mutation == "aggregate_hash":
        receipt["current_observed_snapshot"]["outcome_query_batches_sha256"] = "sha256:" + "9" * 64
    elif mutation == "row_batch":
        receipt["outcomes"][0]["label_source_batch_ordinal"] = 1
    elif mutation == "feature_composition":
        receipt["current_observed_snapshot"]["composition_sha256"] = "invalid-sha256"
    elif mutation == "later_source_schema":
        receipt["current_observed_snapshot"]["schema_version"] = (
            "recommendation-current-observed-feature-snapshot.v3"
        )
    elif mutation == "later_feature_hash":
        receipt["current_observed_snapshot"]["feature_snapshot_sha256"] = "invalid-sha256"
    elif mutation == "capture_composition":
        capture["composition_sha256"] = "sha256:" + "8" * 64
    else:
        raise AssertionError(mutation)

    with pytest.raises(ValueError, match=message):
        _verify_v2_fixture_references(monkeypatch, capture, receipt, reference)


@pytest.mark.parametrize(
    "later_source_schema",
    [
        research_fit._FEATURE_SNAPSHOT_SCHEMA_V1,
        research_fit._FEATURE_SNAPSHOT_SCHEMA_V2,
    ],
)
def test_v2_capture_accepts_distinct_later_v1_or_v2_source(
    monkeypatch: pytest.MonkeyPatch,
    later_source_schema: str,
) -> None:
    capture, receipt, reference = _v2_fixture(later_source_schema=later_source_schema)

    captured = capture["source_contract_binding"]["current_observed_feature_snapshot"]
    later = receipt["current_observed_snapshot"]
    assert captured["cycle_id"] != later["cycle_id"]
    assert captured["raw_run_id"] != later["raw_run_id"]
    assert captured["snapshot_database_sha256"] != later["snapshot_database_sha256"]
    assert captured["cycle_source_date"] != later["source_date"]
    if later_source_schema == research_fit._FEATURE_SNAPSHOT_SCHEMA_V1:
        assert "composition_sha256" not in later
        assert set(later["feature_source_rows_sha256_by_table"]) == set(
            research_fit._CURRENT_OBSERVED_SOURCE_TABLES
        )
    else:
        assert later["composition_sha256"] != captured["composition_sha256"]
        assert "feature_source_rows_sha256_by_table" not in later

    _, rows = _verify_v2_fixture_references(monkeypatch, capture, receipt, reference)
    assert len(rows) == 1


def _evaluation_clock() -> datetime:
    return datetime.now(_TAIPEI)


def _fit(
    *,
    tmp_path: Path,
    samples: tuple[RecommendationCalibrationSample, ...],
    references: tuple[dict[str, str], ...],
    evaluation_at: datetime,
) -> Mapping[str, Any]:
    scenario = build_legacy_cost_scenario(50)
    return research_fit.fit_current_observed_natural_research(
        learning_output_root=tmp_path / "learning-root",
        samples=samples,
        training_as_of=evaluation_at.date(),
        evaluation_at=evaluation_at,
        fixed_round_trip_cost_bp=50,
        cost_scenario=scenario,
        outcome_receipts=references,
        source_identity={"cycle_id": "fixture-current-cycle", "snapshot_sha256": "sha256:" + "a" * 64},
        data_root=tmp_path / "formal-data",
    )


def test_insufficient_rows_returns_pending_without_creating_isolated_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples, references = _fixture_batch(monkeypatch, count=19)
    evaluation_at = _evaluation_clock()
    result = _fit(
        tmp_path=tmp_path,
        samples=samples,
        references=references,
        evaluation_at=evaluation_at,
    )

    assert result["status"] == "pending"
    assert result["reason"] == "insufficient_current_observed_natural_research_rows"
    assert result["candidate_id"] is None
    assert result["receipt_path"] is None
    assert result["isolated_output_root"] == str(
        (tmp_path / "learning-root" / "current_observed_natural_research").resolve()
    )
    assert not Path(str(result["isolated_output_root"])).exists()
    assert result["evaluation_at"] == evaluation_at.isoformat(timespec="microseconds")
    assert result["training_semantics"] == "historical_research_only"
    assert result["natural_evidence"] is None
    assert result["decision_time_eligible"] is False
    assert result["historical_pit_eligible"] is False
    assert result["formal_training_allowed"] is False
    assert result["promotion_credit_created"] is False


def test_pending_receipts_with_no_matured_rows_do_not_create_a_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, references = _fixture_batch(monkeypatch, count=1, pending=True)
    evaluation_at = _evaluation_clock()
    result = _fit(
        tmp_path=tmp_path,
        samples=(),
        references=references,
        evaluation_at=evaluation_at,
    )

    assert result["status"] == "pending"
    assert result["sample_count"] == 0
    assert result["candidate_id"] is None
    assert not Path(str(result["isolated_output_root"])).exists()


def test_verified_receipt_cost_mismatch_fails_closed_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples, references = _fixture_batch(monkeypatch, count=1)
    original_verifier = research_fit.verify_current_observed_outcome_receipt

    def mismatch_cost(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
        original = original_verifier(*args, **kwargs)
        payload = dict(original)
        outcomes = [dict(row) for row in payload["outcomes"]]
        outcomes[0]["estimated_round_trip_cost_bp"] = 49
        payload["outcomes"] = outcomes
        return payload

    monkeypatch.setattr(research_fit, "verify_current_observed_outcome_receipt", mismatch_cost)
    evaluation_at = _evaluation_clock()
    with pytest.raises(ValueError, match="sample payload differs|fixed receipt cost differs"):
        _fit(
            tmp_path=tmp_path,
            samples=samples,
            references=references,
            evaluation_at=evaluation_at,
        )
    assert not (tmp_path / "learning-root" / "current_observed_natural_research").exists()


def test_real_runner_writes_only_current_observed_research_candidate(
    short_output_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    from ml_module import recommendation_calibration_evidence as evidence
    from scripts.scheduled.run_daily_recommendation_learning import (
        _deduplicate_current_observed_samples,
    )

    samples, references = _fixture_batch(monkeypatch, count=180)
    captures: dict[str, Mapping[str, Any]] = {}
    semantic_pairs: list[tuple[RecommendationCalibrationSample, str]] = []
    for sample, reference in zip(samples, references, strict=True):
        outcome = research_fit.verify_current_observed_outcome_receipt(
            reference["outcome_path"]
        )["outcomes"][0]
        capture_row = {
            "row_id": outcome["capture_row_id"],
            "symbol": sample.symbol,
            "decision_date": sample.decision_date,
            "feature_values": list(sample.feature_values),
        }
        captures[reference["capture_path"]] = {"rows": [capture_row]}
        semantic_hash = research_fit._current_observed_capture_semantic_hash(
            capture_row=capture_row, outcome_row=outcome
        )
        semantic_pairs.append((sample, semantic_hash))

    def verify_capture(path: str | Path, **kwargs: Any) -> Mapping[str, Any]:
        reference = next(item for item in references if item["capture_path"] == str(path))
        assert kwargs["expected_sha256"] == reference["capture_sha256"]
        return captures[str(path)]

    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", verify_capture)
    samples = _deduplicate_current_observed_samples(semantic_pairs + semantic_pairs)
    assert len(samples) == 180
    assert all(row.row_id.startswith("current-observed-natural-semantic:") for row in samples)
    evaluation_at = _evaluation_clock()
    learning_root = short_output_root / "l"
    formal_root = short_output_root / "d"
    canonical_root = learning_root / "recommendation_learning"
    canonical_root.mkdir(parents=True)
    formal_root.mkdir(parents=True)
    formal_marker = formal_root / "formal-state.json"
    canonical_marker = canonical_root / "formal-evidence-marker.json"
    formal_marker.write_text('{"formal":"unchanged"}\n', encoding="utf-8")
    canonical_marker.write_text('{"canonical":"unchanged"}\n', encoding="utf-8")
    before = {
        formal_marker: formal_marker.read_bytes(),
        canonical_marker: canonical_marker.read_bytes(),
    }

    # 在真實 learner 啟動前，錯來源必須拒絕，且不得留下候選或收據。
    first_capture_row = captures[references[0]["capture_path"]]["rows"][0]
    first_capture_row["entry_price_pin"] = {"source_row_sha256": "sha256:" + "f" * 64}
    with pytest.raises(ValueError, match="identities differ"):
        research_fit.fit_current_observed_natural_research(
            learning_output_root=learning_root,
            samples=samples,
            training_as_of=evaluation_at.date(),
            evaluation_at=evaluation_at,
            fixed_round_trip_cost_bp=50,
            cost_scenario=build_legacy_cost_scenario(50),
            outcome_receipts=references,
            source_identity={"cycle_id": "fixture-current-cycle", "snapshot_sha256": "sha256:" + "b" * 64},
            data_root=formal_root,
        )
    assert not (learning_root / "current_observed_natural_research").exists()
    del first_capture_row["entry_price_pin"]

    result = research_fit.fit_current_observed_natural_research(
        learning_output_root=learning_root,
        samples=samples,
        training_as_of=evaluation_at.date(),
        evaluation_at=evaluation_at,
        fixed_round_trip_cost_bp=50,
        cost_scenario=build_legacy_cost_scenario(50),
        outcome_receipts=references,
        source_identity={"cycle_id": "fixture-current-cycle", "snapshot_sha256": "sha256:" + "b" * 64},
        data_root=formal_root,
    )

    isolated_root = learning_root / "current_observed_natural_research"
    isolated_learning_root = isolated_root / "recommendation_learning"
    assert result["status"] == "fitted_research_only", (
        result["status"],
        result["reason"],
        result["training_lineage"],
    )
    assert result["run_id"] is not None
    assert result["dataset_hash"] is not None
    assert result["candidate_id"] is not None
    assert result["candidate_root"] is not None
    assert Path(str(result["candidate_root"])).is_relative_to(isolated_learning_root.resolve())
    assert Path(str(result["receipt_path"])).is_relative_to(isolated_learning_root.resolve())
    assert result["decision"] in {"retain_current", "no_change"}
    assert result["training_semantics"] == "historical_research_only"
    assert result["decision_date"] == max(row.decision_date for row in samples)
    assert result["training_as_of"] == evaluation_at.date().isoformat()
    assert result["evaluation_at"] == evaluation_at.isoformat(timespec="microseconds")
    assert result["active_pointer_created"] is False
    assert result["research_only"] is True
    assert result["current_restated"] is True
    assert result["decision_time_eligible"] is False
    assert result["historical_pit_eligible"] is False
    assert result["formal_training_allowed"] is False
    assert result["formal_candidate_eligible"] is False
    assert result["promotion_credit_created"] is False
    assert result["natural_evidence"] is None
    assert not (isolated_learning_root / "recommendation-calibration-active-pointer.json").exists()
    assert json.loads(Path(str(result["receipt_path"])).read_text(encoding="utf-8"))["research_only"] is True
    assert {path: path.read_bytes() for path in before} == before
    assert result["candidate_manifest_hash"] is not None
    assert result["candidate_artifact_hash"] is not None
    for field in (
        "status", "run_id", "dataset_hash", "candidate_id", "receipt_sha256",
        "candidate_manifest_hash", "candidate_artifact_hash", "outcome_receipt_refs_sha256",
    ):
        record_property(field, result[field])
    record_property("semantic_sample_count", len(samples))
    record_property("source_verifiers", "controlled_fixture; actual_learner_candidate_receipt")


def test_null_benchmark_probability_is_required_and_no_after_cost_probability_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples, _ = _fixture_batch(monkeypatch, count=1)
    sample = samples[0]
    bad_probability = RecommendationCalibrationSample.from_forward_return(
        row_id="bad-probability",
        symbol=sample.symbol,
        decision_date=sample.decision_date,
        feature_as_of_date=sample.feature_as_of_date,
        feature_available_date=sample.feature_available_date,
        label_end_date=sample.label_end_date,
        label_available_date=sample.label_available_date,
        feature_values=sample.feature_values,
        stock_return_bp=sample.stock_return_bp,
        benchmark_return_bp=sample.benchmark_return_bp,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=None,
        rule_probability_bp=5_100,
        source_quality=research_fit.CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
        cost_scenario=build_legacy_cost_scenario(50),
    )
    with pytest.raises(ValueError, match="5000 bp null baseline"):
        research_fit._validate_samples(
            (bad_probability,),
            training_as_of=date(2026, 10, 4),
            scenario=build_legacy_cost_scenario(50),
            fixed_round_trip_cost_bp=50,
            feature_count=20,
        )

    after_cost_probability = RecommendationCalibrationSample.from_forward_return(
        row_id="bad-after-cost-probability",
        symbol=sample.symbol,
        decision_date=sample.decision_date,
        feature_as_of_date=sample.feature_as_of_date,
        feature_available_date=sample.feature_available_date,
        label_end_date=sample.label_end_date,
        label_available_date=sample.label_available_date,
        feature_values=sample.feature_values,
        stock_return_bp=sample.stock_return_bp,
        benchmark_return_bp=sample.benchmark_return_bp,
        fixed_round_trip_cost_bp=50,
        observed_liquidity_cost_bp=100,
        rule_probability_bp=NULL_BENCHMARK_PROBABILITY_BP,
        source_quality=research_fit.CURRENT_OBSERVED_NATURAL_RESEARCH_QUALITY,
        cost_scenario=build_legacy_cost_scenario(50),
    )
    with pytest.raises(ValueError, match="after-cost probabilities"):
        research_fit._validate_samples(
            (after_cost_probability,),
            training_as_of=date(2026, 10, 4),
            scenario=build_legacy_cost_scenario(50),
            fixed_round_trip_cost_bp=50,
            feature_count=20,
        )


def test_estimated_fee_and_net_values_are_recomputed_exactly() -> None:
    receipt_costs = {
        "gross_buy_amount_twd": "100000.00",
        "gross_sell_amount_twd": "102500.00",
        "estimated_buy_cost_twd": "20.00",
        "estimated_sell_cost_twd": "30.00",
        "estimated_round_trip_cost_twd": "50.00",
        "net_profit_twd": "2450.00",
        "after_cost_profit_label": None,
    }

    research_fit._verify_estimated_cost_math(receipt_costs)
    assert research_fit._declared_after_cost_label(receipt_costs) == 1

    receipt_costs["net_profit_twd"] = "2451.00"
    with pytest.raises(ValueError, match="net profit does not reconcile"):
        research_fit._verify_estimated_cost_math(receipt_costs)


def test_isolated_output_rejects_reparse_leaf_when_windows_allows_symlink(
    tmp_path: Path,
) -> None:
    learning_root = tmp_path / "learning-root"
    learning_root.mkdir()
    elsewhere_inside = learning_root / "other"
    elsewhere_inside.mkdir()
    requested = learning_root / "current_observed_natural_research"
    try:
        requested.symlink_to(elsewhere_inside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable in this Windows runtime: {exc}")

    with pytest.raises(ValueError, match="symlinks or reparse points"):
        research_fit._isolated_output_root(
            learning_root,
            data_root=tmp_path / "formal-data",
        )


@pytest.mark.parametrize("retry", [False, True])
def test_runner_semantic_dedup_rebinds_verified_receipts_before_pending_fit(tmp_path, monkeypatch, retry):
    from dataclasses import replace
    from ml_module import recommendation_calibration_evidence as evidence
    from scripts.scheduled.run_daily_recommendation_learning import _deduplicate_current_observed_samples

    samples, references = _fixture_batch(monkeypatch, count=1)
    reference = references[0]
    outcome = research_fit.verify_current_observed_outcome_receipt(reference["outcome_path"])["outcomes"][0]
    capture_row = {"row_id": outcome["capture_row_id"], "symbol": samples[0].symbol,
                   "decision_date": samples[0].decision_date, "feature_values": list(samples[0].feature_values)}
    capture = {"rows": [capture_row]}
    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", lambda *args, **kwargs: capture)
    semantic_hash = research_fit._current_observed_capture_semantic_hash(capture_row=capture_row, outcome_row=outcome)
    dedup = _deduplicate_current_observed_samples([(samples[0], semantic_hash)])
    if retry:
        second = dict(reference, capture_path="retry.json", capture_id="retry", outcome_path="retry-outcome.json")
        original_verify = research_fit.verify_current_observed_outcome_receipt
        payload = dict(original_verify(reference["outcome_path"]), capture_id="retry")
        monkeypatch.setattr(research_fit, "verify_current_observed_outcome_receipt",
                            lambda path, **kwargs: payload if str(path) == "retry-outcome.json" else original_verify(path, **kwargs))
        references = (*references, second)
    result = _fit(tmp_path=tmp_path, samples=dedup, references=references, evaluation_at=_evaluation_clock())
    assert result["status"] == "pending"
    assert result["sample_count"] == 1
    assert result["formal_training_allowed"] is False
    assert not Path(str(result["isolated_output_root"])).exists()
    for tampered in (replace(dedup[0], row_id="current-observed-natural-semantic:" + "0" * 32),
                     replace(dedup[0], feature_values=tuple(value + 1 for value in dedup[0].feature_values))):
        with pytest.raises(ValueError, match="identities differ|payload differs"):
            _fit(tmp_path=tmp_path, samples=(tampered,), references=references, evaluation_at=_evaluation_clock())
    capture_row["entry_price_pin"] = {"source_row_sha256": "sha256:" + "f" * 64}
    with pytest.raises(ValueError, match="identities differ"):
        _fit(tmp_path=tmp_path, samples=dedup, references=references, evaluation_at=_evaluation_clock())


def test_semantic_fit_requires_capture_reverification(tmp_path, monkeypatch):
    from dataclasses import replace
    from ml_module import recommendation_calibration_evidence as evidence
    samples, references = _fixture_batch(monkeypatch, count=1)
    semantic = replace(samples[0], row_id="current-observed-natural-semantic:" + "a" * 32)
    def reject_capture(*args, **kwargs):
        raise ValueError("capture bytes changed")
    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", reject_capture)
    with pytest.raises(ValueError, match="capture failed independent re-verification"):
        _fit(tmp_path=tmp_path, samples=(semantic,), references=references, evaluation_at=_evaluation_clock())
    assert not (tmp_path / "learning-root").exists()
