from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module.dtos import RecommendationDTO
from scripts.scheduled import run_scheduled_recommendation_snapshot


class FakeRecommendationService:
    instances: list["FakeRecommendationService"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.last_screening_matrix = [
            {
                "stock_code": "2330",
                "stock_name": "TSMC",
                "status": "pass",
                "reason_codes": ["recommendation_selected"],
                "quality": "observed",
            }
        ]
        self.last_excluded_candidates_json = []
        self.last_why_not_payload_json = [
            {
                "stock_code": "2317",
                "status": "fail",
                "reason_codes": ["recommendation_outside_top_n"],
                "quality": "observed",
            }
        ]
        self.last_liquidity_gate_payload_json = []
        self.last_exclusion_quality = "observed"
        self.last_exclusion_warnings_json = ["screening_matrix_persisted_v1"]
        self.last_run_context = {}
        self.calls: list[dict[str, object]] = []
        FakeRecommendationService.instances.append(self)

    def run_recommendation(
        self,
        *,
        config: dict[str, object],
        max_stocks: int,
        top_n: int,
    ) -> list[RecommendationDTO]:
        self.last_run_context = {
            "decision_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        }
        self.calls.append({"config": config, "max_stocks": max_stocks, "top_n": top_n})
        return [
            RecommendationDTO(
                stock_code="2330",
                stock_name="TSMC",
                close_price=100,
                price_change=1,
                total_score=80,
                indicator_score=30,
                pattern_score=30,
                volume_score=20,
                recommendation_reasons="fixture",
                industry="Semiconductor",
                regime_match=True,
            )
        ]


class FakeRecommendationRepository:
    saved_results: list[object] = []

    def __init__(self, config) -> None:
        self.config = config
        self.db_path = Path(config.output_root) / "recommendation" / "runs" / "recommendation_runs.db"
        self.runs_dir = self.db_path.parent
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def save_result(self, result) -> str:
        result.result_id = result.result_id or "scheduled_rec_fixture"
        FakeRecommendationRepository.saved_results.append(result)
        return result.result_id


class FakePersistingRecommendationRepository(FakeRecommendationRepository):
    def save_result(self, result) -> str:
        result.result_id = result.result_id or "scheduled_rec_fixture"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        (self.runs_dir / f"{result.result_id}.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False),
            encoding="utf-8",
        )
        return result.result_id


class FakeForwardCandidateProducer:
    calls: list[dict[str, object]] = []

    def __init__(self, output_root, *, calendar_cache_path=None) -> None:
        self.output_root = output_root
        self.calendar_cache_path = calendar_cache_path

    def produce(self, recommendation_path, *, policy_path=None, decision_at=None):
        self.calls.append(
            {
                "output_root": self.output_root,
                "recommendation_path": recommendation_path,
                "policy_path": policy_path,
                "calendar_cache_path": self.calendar_cache_path,
                "decision_at": decision_at,
            }
        )
        return {
            "status": "degraded",
            "candidate_count": 1,
            "candidates": [{"status": "awaiting_explicit_policy"}],
        }


def test_scheduled_recommendation_snapshot_saves_result_and_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeRecommendationService.instances.clear()
    FakeRecommendationRepository.saved_results.clear()
    monkeypatch.setattr(run_scheduled_recommendation_snapshot, "RecommendationService", FakeRecommendationService)
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationRepository",
        FakeRecommendationRepository,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "_build_result_id",
        lambda _now: "scheduled_rec_fixture",
    )

    output_root = tmp_path / "output"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--max-stocks",
            "25",
            "--top-n",
            "5",
        ]
    )

    status_path = output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["task"] == "baldr-recommendation-snapshot-daily"
    assert payload["result_id"] == "scheduled_rec_fixture"
    assert payload["recommendations_count"] == 1
    assert payload["screening_matrix_rows"] == 1
    assert payload["why_not_payload_rows"] == 1
    assert payload["writes_recommendation_result"] is True
    assert payload["writes_evidence_db"] is False
    assert payload["auto_trading"] is False
    assert payload["lifecycle_action"] is False
    assert payload["confirm"] is False
    assert payload["evidence_identity"]["strategy_version_id"] == "scheduled-recommendation-default-v1"
    assert payload["evidence_identity"]["cost_model_id"] == "gross-close-to-close-no-cost-v1"
    assert payload["evidence_identity"]["benchmark_id"] == "TAIEX"
    assert payload["evidence_identity"]["horizon_days"] == 20
    assert FakeRecommendationService.instances[0].calls[0]["max_stocks"] == 25
    assert FakeRecommendationService.instances[0].calls[0]["top_n"] == 5

    saved = FakeRecommendationRepository.saved_results[0]
    assert saved.config["scheduled_snapshot"] is True
    assert saved.config["research_only"] is True
    assert saved.recommendations[0].threshold_mode == "fixed"
    assert saved.recommendations[0].ranking_method == "fixed_threshold"
    assert saved.recommendations[0].score_percentile_bp is None
    assert saved.screening_matrix_json
    assert saved.why_not_payload_json


def test_scheduled_default_config_uses_recommendation_service_tokens() -> None:
    config = run_scheduled_recommendation_snapshot._scheduled_default_config()

    assert config["filters"]["industry"] == "全部"
    assert config["patterns"]["selected"] == ["旗形", "三角形", "矩形", "V形反轉"]
    assert config["strategy_version_id"] == "scheduled-recommendation-default-v1"
    assert config["cost_model_id"] == "gross-close-to-close-no-cost-v1"
    assert config["benchmark_id"] == "TAIEX"
    assert config["horizon_days"] == 20


def test_scheduled_snapshot_emits_forward_candidate_after_result_is_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(run_scheduled_recommendation_snapshot, "RecommendationService", FakeRecommendationService)
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationRepository",
        FakePersistingRecommendationRepository,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "_build_result_id",
        lambda _now: "scheduled_rec_fixture",
    )

    output_root = tmp_path / "output"
    forward_root = tmp_path / "forward"
    cache_path = tmp_path / "calendar.json"
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "b" * 64,
                "captured_at": "2026-09-16T23:15:00+00:00",
                "expires_at": "2026-09-23T23:15:00+00:00",
            }
        ),
    )
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(forward_root),
            "--forward-thesis-policy-path",
            str(tmp_path / "policy.json"),
            "--forward-calendar-cache-path",
            str(cache_path),
        ]
    )

    assert exit_code == 0
    assert len(FakeForwardCandidateProducer.calls) == 1
    call = FakeForwardCandidateProducer.calls[0]
    assert call["output_root"] == str(forward_root)
    assert Path(call["recommendation_path"]).is_file()
    assert call["policy_path"] == str(tmp_path / "policy.json")
    assert call["calendar_cache_path"] == str(cache_path.resolve())
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["forward_position_thesis"]["status"] == "degraded"
    assert "forward_position_thesis_candidate_degraded" in status["warnings"]
    assert status["forward_calendar_observation"]["status"] == "explicit_path_verified"


def test_scheduled_snapshot_selects_verified_calendar_from_refresh_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationService",
        FakeRecommendationService,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationRepository",
        FakePersistingRecommendationRepository,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "_build_result_id",
        lambda _now: "scheduled_rec_refresh_fixture",
    )

    cache_path = tmp_path / "calendar" / "twse_holiday_schedule_2026_refresh.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "cache_valid_for_forward_horizon",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(cache_path.parent),
                "calendar_year": 2026,
                "observed_at": "2026-09-16T23:15:01+00:00",
                "inspection": {
                    "selected": {
                        "calendar_year": 2026,
                        "path": str(cache_path),
                        "file_sha256": cache_file_sha256,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "a" * 64,
                "captured_at": "2026-09-14T23:15:03+00:00",
                "expires_at": "2026-09-21T23:15:03+00:00",
            }
        ),
    )

    output_root = tmp_path / "output"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(tmp_path / "forward"),
            "--forward-thesis-policy-path",
            str(tmp_path / "policy.json"),
            "--forward-calendar-refresh-status-path",
            str(refresh_status_path),
        ]
    )

    assert exit_code == 0
    assert len(FakeForwardCandidateProducer.calls) == 1
    call = FakeForwardCandidateProducer.calls[0]
    assert call["calendar_cache_path"] == str(cache_path.resolve())
    status = json.loads(
        (output_root / "scheduled" / "recommendation_snapshot" / "latest_status.json").read_text(
            encoding="utf-8"
        )
    )
    observation = status["forward_calendar_observation"]
    assert observation["status"] == "verified_refresh_receipt"
    assert observation["path"] == str(cache_path.resolve())
    assert observation["file_sha256"] == cache_file_sha256
    assert observation["refresh_status_file_sha256"].startswith("sha256:")


def test_calendar_refresh_selector_fails_closed_without_fallback(
    tmp_path: Path,
) -> None:
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "blocked_refresh",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(tmp_path / "calendar"),
            }
        ),
        encoding="utf-8",
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=None,
        refresh_status_path=refresh_status_path,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "not_usable:blocked_refresh" in str(evidence["blocker"])


def test_scheduled_snapshot_does_not_start_candidate_producer_when_refresh_is_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeForwardCandidateProducer.calls.clear()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationService",
        FakeRecommendationService,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "RecommendationRepository",
        FakePersistingRecommendationRepository,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "ForwardPositionThesisCandidateProducer",
        FakeForwardCandidateProducer,
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "_build_result_id",
        lambda _now: "scheduled_rec_refresh_blocked_fixture",
    )

    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "refresh_blocked",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(tmp_path / "calendar"),
            }
        ),
        encoding="utf-8",
    )
    # This represents a still-readable old policy pin.  The caller must not
    # let the producer fall back to it while the current observation is blocked.
    policy_path = tmp_path / "approved-old-policy.json"
    policy_path.write_text("policy-pin-remains-readable\n", encoding="utf-8")

    output_root = tmp_path / "output"
    forward_root = tmp_path / "forward"
    exit_code = run_scheduled_recommendation_snapshot.main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "--output-root",
            str(output_root),
            "--forward-candidate-output-root",
            str(forward_root),
            "--forward-thesis-policy-path",
            str(policy_path),
            "--forward-calendar-refresh-status-path",
            str(refresh_status_path),
        ]
    )

    status = json.loads(
        (
            output_root
            / "scheduled"
            / "recommendation_snapshot"
            / "latest_status.json"
        ).read_text(encoding="utf-8")
    )
    candidate = status["forward_position_thesis"]
    receipt = json.loads(
        (forward_root / "latest_status.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert FakeForwardCandidateProducer.calls == []
    assert candidate["status"] == "blocked"
    assert candidate["candidate_count"] == 0
    assert candidate["producer_started"] is False
    assert candidate["blockers"]
    assert receipt["status"] == "blocked"
    assert receipt["candidate_count"] == 0
    assert receipt["producer_started"] is False


def test_calendar_observation_custody_blocks_capture_after_decision_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "calendar" / "twse_holiday_schedule_2026.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    refresh_status_path = tmp_path / "refresh" / "latest_status.json"
    refresh_status_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_status_path.write_text(
        json.dumps(
            {
                "schema_version": "official-calendar-refresh-status.v1",
                "status": "cache_valid_for_forward_horizon",
                "candidate_only": True,
                "read_only": True,
                "forward_child_started": False,
                "forward_credit_granted": False,
                "production_action_allowed": False,
                "broker_order_allowed": False,
                "cache_root": str(cache_path.parent),
                "calendar_year": 2026,
                "inspection": {
                    "selected": {
                        "calendar_year": 2026,
                        "path": str(cache_path),
                        "file_sha256": cache_file_sha256,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "c" * 64,
                "captured_at": "2026-09-17T12:00:01+00:00",
                "expires_at": "2026-09-24T12:00:01+00:00",
            }
        ),
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=None,
        refresh_status_path=refresh_status_path,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        decision_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "captured_after_decision_at" in str(evidence["blocker"])


def test_explicit_calendar_path_cannot_bypass_observation_custody(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "calendar.json"
    cache_path.write_bytes(b"verified-calendar-fixture\n")
    cache_file_sha256 = "sha256:" + hashlib.sha256(cache_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        run_scheduled_recommendation_snapshot,
        "load_verified_twse_calendar_cache",
        lambda path, *, calendar_year, observed_at: SimpleNamespace(
            evidence={
                "path": str(Path(path).resolve()),
                "calendar_year": calendar_year,
                "cache_file_sha256": cache_file_sha256,
                "cache_content_sha256": "sha256:" + "d" * 64,
                "captured_at": "2026-09-17T12:00:01+00:00",
                "expires_at": "2026-09-24T12:00:01+00:00",
            }
        ),
    )

    path, evidence = run_scheduled_recommendation_snapshot._resolve_forward_calendar_cache(
        explicit_path=cache_path,
        refresh_status_path=None,
        observed_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        decision_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert path is None
    assert evidence["status"] == "blocked"
    assert "captured_after_decision_at" in str(evidence["blocker"])


def test_recommendation_decision_at_requires_saved_run_context_clock(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "recommendation.json"
    source_path.write_text(
        json.dumps(
            {
                "created_at": "2026-09-17T12:00:00+00:00",
                "run_context": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="recommendation_decision_at_missing"):
        run_scheduled_recommendation_snapshot._recommendation_decision_at(source_path)


def test_scheduled_recommendation_snapshot_script_help_bootstraps_repo_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/scheduled/run_scheduled_recommendation_snapshot.py",
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Scheduled research-only recommendation snapshot wrapper" in result.stdout
