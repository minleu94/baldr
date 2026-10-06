"""個人自然結果日常入口的隔離來源、嚴格讀回與 create-only 回歸。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

import app_module.recommendation.personal_prediction_capture as capture_module
import app_module.recommendation.personal_natural_outcome_daily as outcome_daily
from app_module.recommendation.personal_natural_outcome_daily import (
    PersonalNaturalOutcomeConflict,
    PersonalNaturalOutcomeDailyError,
    _read_plain_optional,
    run_personal_natural_outcome_daily,
)
from data_module.ml_historical_snapshot_provider import MLHistoricalSnapshotProvider
from data_module.natural_maturity_session_resolver import NaturalMaturitySessionResolver
from ml_module.recommendation_calibration_evidence import (
    verify_natural_maturity_session_proof,
)
from ml_module.recommendation_natural_outcome_service import (
    RecommendationNaturalOutcomeService,
)
from scripts.run_personal_recommendation_outcomes import _parse_evaluation_at
from tests.test_recommendation_personal_natural_outcomes import (
    _complete_cost_personal_capture,
    _structural_v3_capture_fixture,
    _write_natural_source,
)


_UTC = timezone.utc


def _case(tmp_path: Path, *, include_calendar: bool = True, endpoints: bool = True):
    capture = _complete_cost_personal_capture(tmp_path)
    personal_root = tmp_path / "personal-root"
    capture_path = personal_root / "captures" / f"{capture['capture_id'][7:]}.json"
    provider, resolver, sessions = _write_natural_source(
        tmp_path / "market",
        capture_day=datetime.fromisoformat(
            str(capture["receipt_binding"]["decision_date"])
        ).date(),
        include_calendar=include_calendar,
        include_stock_endpoints=endpoints,
    )
    return {
        "capture": capture,
        "capture_path": capture_path,
        "personal_root": personal_root,
        "canonical_root": tmp_path / "canonical",
        "market_db": provider.database_path,
        "calendar_root": resolver.calendar_cache_path,
        "sessions": sessions,
        "evaluation_at": datetime.now(_UTC),
        "isolated_root": tmp_path / "isolated-outcomes",
    }


def _run(case: dict[str, object]):
    return run_personal_natural_outcome_daily(
        canonical_recommendation_output_root=case["canonical_root"],
        capture_paths=[case["capture_path"]],
        personal_capture_root=case["personal_root"],
        market_source_db=case["market_db"],
        calendar_cache_path=case["calendar_root"],
        evaluation_at=case["evaluation_at"],
        isolated_output_root=case["isolated_root"],
    )


def test_daily_runner_publishes_verified_full_projection_and_reruns_idempotently(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    market_db = Path(case["market_db"])
    before = market_db.read_bytes()

    first = _run(case)
    assert first.status == "completed"
    assert first.capture_statuses == ("matured",)
    assert len(first.outcome_paths) == 1
    assert first.idempotent_outcomes == (False,)
    outcome_path = first.outcome_paths[0]
    payload = json.loads(outcome_path.read_text(encoding="utf-8"))
    projection = payload["projection"]
    assert payload["lane"] == "personal_only"
    assert payload["schema_version"] == outcome_daily.PERSONAL_NATURAL_OUTCOME_SCHEMA_V1
    assert projection["status"] == "matured"
    assert projection["horizon_sessions"] == 20
    assert projection["matured_sample_count"] == 2
    assert projection["pending_sample_count"] == 0
    assert payload["source"]["session_proof"]["proof_hash"]
    assert payload["global_natural_evidence_created"] is False
    assert payload["promotion_credit_created"] is False
    assert market_db.read_bytes() == before


def test_v3_adapter_publishes_only_active_model_rows_with_forward_return_semantics(
    tmp_path: Path,
) -> None:
    """Structural adapter coverage; canonical v3 ingress is covered by full-stack tests."""

    case = _case(tmp_path)
    capture = _structural_v3_capture_fixture(
        case["capture"],
        active_codes=("1101",),
    )
    market_db = Path(case["market_db"])
    evaluation_at = case["evaluation_at"]
    capture_date = str(capture["receipt_binding"]["decision_date"])
    provider = MLHistoricalSnapshotProvider(market_db)
    resolver = NaturalMaturitySessionResolver(
        market_db,
        Path(case["calendar_root"]),
    )
    projection = RecommendationNaturalOutcomeService(
        provider,
        evidence_db_path=market_db,
        session_resolver=resolver,
    ).project_personal_prediction_outcomes(
        capture,
        evaluation_at=evaluation_at,
    )
    resolution = resolver.resolve_personal_prediction_horizon(capture_date, evaluation_at)
    assert resolution.status == "ready", resolution.reason
    assert resolution.proof is not None
    assert resolution.endpoint_date is not None
    verified_proof = dict(
        verify_natural_maturity_session_proof(
            resolution.proof,
            capture_date=capture_date,
            label_end_date=resolution.endpoint_date,
            evaluation_at=evaluation_at,
            expected_db_path=market_db,
        )
    )
    calendar_status = str(verified_proof["calendar"]["status"])

    payload = outcome_daily._build_outcome_payload(
        capture=capture,
        projection=projection,
        verified_proof=verified_proof,
        calendar_status=calendar_status,
        market_db=market_db,
    )

    assert projection.status == "matured", (projection.reason, projection.diagnostics)
    assert payload["schema_version"] == outcome_daily.PERSONAL_NATURAL_OUTCOME_SCHEMA_V2
    assert payload["model_scope"] == {
        "delivered_count": 2,
        "model_active_count": 1,
        "rule_only_fallback_count": 1,
        "model_coverage_bp": 5_000,
        "model_active_stock_codes": ["1101"],
        "rule_only_fallback_stock_codes": ["2330"],
        "fallback_rows_have_model_probability": False,
    }
    assert [item["stock_code"] for item in payload["delivered_universe"]] == [
        "1101",
        "2330",
    ]
    assert [item["stock_code"] for item in payload["projection"]["outcomes"]] == [
        "1101"
    ]
    row = payload["projection"]["outcomes"][0]
    assert row["return_basis"] == "close_to_close_event_date"
    assert row["return_start_date"] == capture_date
    assert row["return_end_date"] == resolution.endpoint_date
    assert row["is_execution_pnl"] is False
    assert payload["return_semantics"] == {
        "basis": "close_to_close_event_date",
        "start_date": capture_date,
        "end_date": resolution.endpoint_date,
        "is_execution_pnl": False,
    }
    assert payload["capture_binding"]["decision_at"] == capture["decision_at"]
    assert "event_date" not in payload["return_semantics"]
    assert row["after_cost_profit_probability_bp"] == 8_500
    assert row["after_cost_baseline_probability_bp"] is None
    assert payload["global_natural_evidence_created"] is False
    assert payload["promotion_credit_created"] is False

    fallback_row = dict(row)
    fallback_row["stock_code"] = "2330"
    fallback_row["rank"] = 1
    forged_projection = replace(projection, outcomes=(fallback_row,))
    with pytest.raises(PersonalNaturalOutcomeDailyError, match="模型機率"):
        outcome_daily._build_outcome_payload(
            capture=capture,
            projection=forged_projection,
            verified_proof=verified_proof,
            calendar_status=calendar_status,
            market_db=market_db,
        )


def test_rehashed_v2_baseline_forgery_is_rejected_by_strict_ingress(
    tmp_path: Path,
) -> None:
    """不能把有效 v1 捕獲重包成自我重算雜湊的 v2 baseline。"""

    from tests.test_recommendation_personal_natural_outcomes import (
        _structural_v2_capture_fixture,
    )

    case = _case(tmp_path, include_calendar=False)
    assert case["capture"]["schema_version"] == (
        "recommendation-personal-prediction-capture.v1"
    )
    forged = _structural_v2_capture_fixture(case["capture"])
    baseline = forged["probability_baseline_snapshot"]
    first_symbol = baseline["projected_stock_codes"][0]
    baseline["upside_probability_bp_by_symbol"][first_symbol] = 5_001
    baseline_body = {
        key: value for key, value in baseline.items() if key != "snapshot_sha256"
    }
    baseline["snapshot_sha256"] = "sha256:" + hashlib.sha256(
        capture_module._canonical_json_bytes(baseline_body)
    ).hexdigest()
    forged["capture_id"] = capture_module._capture_id(forged)
    forged["payload_sha256"] = capture_module._payload_hash(forged)
    forged_path = Path(case["personal_root"]) / "captures" / (
        str(forged["capture_id"])[7:] + ".json"
    )
    forged_path.write_bytes(capture_module._canonical_json_bytes(forged))

    case["capture_path"] = forged_path
    rejected = _run(case)
    assert rejected.status == "completed_with_unknown"
    assert rejected.capture_statuses == ("unknown",)
    assert rejected.outcome_paths == ()
    rejected_summary = json.loads(rejected.summary_path.read_text(encoding="utf-8"))
    assert rejected_summary["captures"][0]["reason"] == (
        "validation_failed:PersonalPredictionCaptureError"
    )
    assert rejected_summary["captures"][0]["outcome_artifact"] is None


def test_missing_official_calendar_is_explicit_pending_without_outcome_rows(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, include_calendar=False)
    result = _run(case)
    assert result.status == "completed_with_pending"
    assert result.capture_statuses == ("pending",)
    assert result.outcome_paths == ()
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["captures"][0]["projection_status"] == "pending"
    assert summary["captures"][0]["outcome_artifact"] is None
    outcome_dir = Path(case["isolated_root"]) / "personal_natural_outcomes" / "outcomes"
    assert not outcome_dir.exists()


def test_partial_maturity_never_publishes_partial_outcome_rows(tmp_path: Path) -> None:
    case = _case(tmp_path, endpoints=False)
    result = _run(case)
    assert result.status == "completed_with_pending"
    assert result.capture_statuses == ("pending",)
    assert result.outcome_paths == ()
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["captures"][0]["matured_sample_count"] == 0
    assert summary["captures"][0]["pending_sample_count"] == 2
    assert summary["captures"][0]["outcome_artifact"] is None


def test_capture_tampering_is_unknown_and_never_publishes_outcomes(tmp_path: Path) -> None:
    case = _case(tmp_path)
    capture_path = Path(case["capture_path"])
    body = json.loads(capture_path.read_text(encoding="utf-8"))
    body["receipt_binding"]["receipt_hash"] = "sha256:" + "0" * 64
    capture_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    result = _run(case)
    assert result.status == "completed_with_unknown"
    assert result.capture_statuses == ("unknown",)
    assert result.outcome_paths == ()
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["captures"][0]["reason"].startswith("validation_failed:")
    assert summary["captures"][0]["outcome_artifact"] is None


def test_isolated_root_may_not_overlap_any_input_tree(tmp_path: Path) -> None:
    case = _case(tmp_path)
    case["isolated_root"] = Path(case["canonical_root"]) / "personal-natural-outcomes"
    with pytest.raises(PersonalNaturalOutcomeDailyError, match="分離"):
        _run(case)
    assert not Path(case["isolated_root"]).exists()


def test_same_capture_and_evaluation_with_changed_source_conflicts_without_overwrite(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path)
    first = _run(case)
    outcome_path = first.outcome_paths[0]
    original_bytes = outcome_path.read_bytes()
    endpoint = str(case["sessions"][-1]).replace("-", "")
    with sqlite3.connect(Path(case["market_db"])) as connection:
        connection.execute(
            "UPDATE daily_prices SET 收盤價 = ? WHERE 日期 = ? AND 證券代號 = ?",
            ("111", endpoint, "1101"),
        )

    with pytest.raises(PersonalNaturalOutcomeConflict, match="不同 bytes"):
        _run(case)
    assert outcome_path.read_bytes() == original_bytes


def test_missing_market_database_fails_before_creating_isolated_output(tmp_path: Path) -> None:
    case = _case(tmp_path)
    case["market_db"] = tmp_path / "missing.db"
    with pytest.raises(PersonalNaturalOutcomeDailyError, match="market_source_db"):
        _run(case)
    assert not Path(case["isolated_root"]).exists()


def test_cli_evaluation_clock_requires_explicit_timezone() -> None:
    assert _parse_evaluation_at("2026-09-27T16:00:00+08:00").utcoffset() is not None
    with pytest.raises(ValueError, match="含時區"):
        _parse_evaluation_at("2026-09-27T16:00:00")


def test_existing_output_symlink_replacement_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    target = root / "personal_natural_outcomes" / "runs" / "existing.json"
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.write_bytes(b"original")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"此 Windows 帳戶不能建立測試 symlink：{type(exc).__name__}")

    with pytest.raises(PersonalNaturalOutcomeDailyError):
        _read_plain_optional(target, root)
    assert outside.read_bytes() == b"outside"


def test_existing_output_over_limit_is_rejected_without_unbounded_read(
    tmp_path: Path,
) -> None:
    root = tmp_path / "isolated"
    target = root / "personal_natural_outcomes" / "runs" / "oversized.json"
    target.parent.mkdir(parents=True)
    with target.open("wb") as handle:
        handle.truncate(64 * 1024 * 1024 + 1)

    with pytest.raises(PersonalNaturalOutcomeDailyError, match="64 MiB"):
        _read_plain_optional(target, root)


def test_existing_output_replaced_after_open_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "isolated"
    target = root / "personal_natural_outcomes" / "runs" / "existing.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    replacement = target.with_name("replacement.json")
    replacement.write_bytes(b"replacement")

    replacement_blocked: list[str] = []

    def open_then_replace(path: Path) -> int:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
        )
        try:
            os.replace(replacement, path)
        except OSError as exc:
            if os.name != "nt":
                os.close(descriptor)
                raise
            replacement_blocked.append(type(exc).__name__)
        return descriptor

    monkeypatch.setattr(outcome_daily, "_open_regular_file_no_follow", open_then_replace)
    if os.name == "nt":
        assert _read_plain_optional(target, root) == b"original"
        assert replacement_blocked == ["PermissionError"]
        assert target.read_bytes() == b"original"
    else:
        with pytest.raises(PersonalNaturalOutcomeDailyError, match="已被替換"):
            _read_plain_optional(target, root)
        assert target.read_bytes() == b"replacement"
