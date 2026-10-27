from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app_module.research_console_source_service import ResearchConsoleSourceService


P0_SOURCE_IDS = {
    "corporate_action.ex_dividend_timeline",
    "corporate_action.reduction_split_par_value",
    "microstructure.suspended_halt_resume",
    "microstructure.disposition_stock",
    "microstructure.periodic_call_auction",
    "microstructure.full_delivery",
    "microstructure.limit_lock",
    "institutional_flows",
    "credit_transactions",
    "tdcc_shareholding",
    "twse.monthly_revenue_announcement",
    "tpex.monthly_revenue_announcement",
    "pit.quarterly_financials",
}


def _projection() -> dict[str, object]:
    return {
        "identity": {
            "dataset_id": "terra-development-v0:g-1",
            "generation_id": "g-1",
            "research_run_id": "sha256:run-1",
        },
        "status": {
            "scope": "historical_research_seen_development_data",
            "formal_oos": False,
            "alpha_bp": 0,
            "apply_flags": {
                "apply_to_scoring": False,
                "apply_to_recommendation": False,
                "apply_to_portfolio": False,
                "apply_to_exit": False,
            },
            "promotion_eligible": False,
        },
        "frozen_metrics": {
            "sample_count": 48,
            "coverage_bp": 10000,
            "rule": {"status": "research_baseline", "sample_count": 48},
            "ml": {"status": "development_challenger", "sample_count": 48},
            "downside": {"status": "observed"},
        },
        "blockers": ["research_only_degraded"],
        "lineage": {
            "dataset_id": "terra-development-v0:g-1",
            "generation_id": "g-1",
            "dataset_manifest_hash": "sha256:manifest",
            "dataset_content_hash": "sha256:content",
            "feature_registry_hash": "sha256:features",
            "label_registry_hash": "sha256:labels",
            "rule_configuration_hash": "sha256:rule",
            "input_fit_row_count": 48,
            "input_evaluation_row_count": 0,
            "feature_names": ["rsi_normalized_bp", "adx_normalized_bp"],
            "max_label_available_date": "2025-02-18",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def test_missing_projection_is_fail_closed_without_zero_filling() -> None:
    console = ResearchConsoleSourceService().inspect()

    assert console.overall_status == "missing"
    assert console.boundary.formal_oos_allowed is False
    assert console.boundary.production_blend_alpha_bp == 0
    assert console.boundary.formal_rule_unchanged is True
    assert console.boundary.promotion_allowed is False
    assert console.boundary.retrain_allowed is False
    assert console.boundary.scheduler_allowed is False
    assert console.boundary.trading_allowed is False
    assert {row.gate_id for row in console.gates} == {"EV1", "EV2", "EV3", "EV4", "EV5"}
    assert all(row.status == "missing" for row in console.gates)
    p0_rows = tuple(row for row in console.sources if row.lane == "p0")
    broker_rows = tuple(row for row in console.sources if row.lane == "broker")
    assert {row.source_id for row in p0_rows} == P0_SOURCE_IDS
    assert len(broker_rows) == 1
    assert all(row.status == "missing" and row.observed_rows is None for row in console.sources)
    assert all(row.row_count is None for row in console.pipeline)


def test_projection_provider_is_copied_without_recomputing_domain_metrics() -> None:
    payload = _projection()
    console = ResearchConsoleSourceService(projection_provider=lambda: payload).inspect()

    assert console.overall_status == "degraded"
    assert [row.component_id for row in console.pipeline] == ["dataset", "rule", "ml", "e2e"]
    assert console.pipeline[0].identity == "terra-development-v0:g-1"
    assert console.pipeline[0].row_count == 48
    assert console.pipeline[0].feature_count == 2
    assert console.pipeline[1].status == "research_baseline"
    assert console.pipeline[2].status == "development_challenger"
    assert console.pipeline[3].blockers == ("research_only_degraded",)
    assert console.pipeline[3].artifact_hash is None
    assert console.frozen_metrics == payload["frozen_metrics"]
    assert console.frozen_metrics is not payload["frozen_metrics"]
    assert {item.artifact_id for item in console.artifacts} >= {
        "sha256:manifest",
        "sha256:content",
        "sha256:features",
        "sha256:labels",
    }


def test_explicit_p0_audit_path_is_projected_into_research_console(tmp_path: Path) -> None:
    audit_path = tmp_path / "p0-audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "p0-candidate-audit.v1",
                "formal_oos_allowed": False,
                "production_scheduler_allowed": False,
                "downstream_eligibility": "none",
                "human_decision": "requires_human_acceptance",
                "items": [
                    {
                        "source_id": source_id,
                        "audit_status": "observed_candidate",
                        "machine_status": "verified",
                        "row_count": 3,
                        "accepted_row_count": 3,
                        "blocked_row_count": 0,
                        "blockers": ["research_only_not_source_accepted"],
                    }
                    for source_id in sorted(P0_SOURCE_IDS)
                ],
            }
        ),
        encoding="utf-8",
    )

    console = ResearchConsoleSourceService(
        projection_provider=_projection,
        p0_audit_path=audit_path,
    ).inspect()

    assert console.source_control_center is not None
    assert console.source_control_center.p0_source_count == 13
    assert console.source_control_center.research_shadow_count == 13
    assert console.source_control_center.downstream_eligible_count == 0
    assert console.source_control_center.rows[0].observed_rows == 3


def test_explicit_owner_review_decision_path_is_projected_fail_closed(tmp_path: Path) -> None:
    decision_path = tmp_path / "p0-owner-review.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "source-acceptance-owner-review-decision.v1",
                "source_id": "corporate_action.ex_dividend_timeline",
                "decision_revision_id": "decision:ex-dividend:deferred",
                "parent_revision_id": None,
                "status": "deferred",
                "owner_role": "owner",
                "reviewer_role": "reviewer",
                "decision_timestamp": "2026-08-27T12:00:00+08:00",
                "active_blockers": ["missing_publication_time_policy"],
                "rollback_reference": "owner-policy:disable",
                "formal_oos_allowed": False,
                "production_blend_alpha_bp": 0,
            }
        ),
        encoding="utf-8",
    )

    console = ResearchConsoleSourceService(
        projection_provider=_projection,
        p0_decision_path=decision_path,
    ).inspect()

    assert console.source_control_center is not None
    row = console.source_control_center.rows[0]
    assert row.decision_status == "deferred"
    assert row.revision == "decision:ex-dividend:deferred"
    assert row.governance_status == "deferred"
    assert "missing_publication_time_policy" in row.blockers
    assert "source_acceptance_deferred" in row.blockers
    assert console.source_control_center.accepted_count == 0
    assert console.source_control_center.downstream_eligible_count == 0


def test_invalid_owner_review_applying_decision_fails_closed(tmp_path: Path) -> None:
    decision_path = tmp_path / "p0-owner-review-accepted.json"
    decision_path.write_text(
        json.dumps(
            {
                "schema_version": "source-acceptance-owner-review-decision.v1",
                "source_id": "institutional_flows",
                "decision_revision_id": "decision:institutional_flows:accepted",
                "parent_revision_id": None,
                "status": "accepted",
                "owner_role": "owner",
                "reviewer_role": "reviewer",
                "decision_timestamp": "2026-08-27T12:00:00+08:00",
                "rollback_reference": "owner-policy:disable",
            }
        ),
        encoding="utf-8",
    )

    console = ResearchConsoleSourceService(
        projection_provider=_projection,
        p0_decision_path=decision_path,
    ).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_schema_invalid",)


def test_p0_decision_provider_and_path_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="either p0_decision_provider or p0_decision_path"):
        ResearchConsoleSourceService(
            p0_decision_provider=lambda: (),
            p0_decision_path=tmp_path / "p0-decision.json",
        )


def test_p0_audit_provider_and_path_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="either p0_audit_provider or p0_audit_path"):
        ResearchConsoleSourceService(
            p0_audit_provider=lambda: None,
            p0_audit_path=tmp_path / "p0.json",
        )


def test_explicit_projection_path_is_read_only(tmp_path: Path) -> None:
    projection_path = tmp_path / "ResearchConsoleProjection.json"
    projection_path.write_text(json.dumps(_projection()), encoding="utf-8")
    before = (projection_path.stat().st_size, projection_path.stat().st_mtime_ns, projection_path.read_bytes())

    console = ResearchConsoleSourceService(projection_path=projection_path).inspect()

    after = (projection_path.stat().st_size, projection_path.stat().st_mtime_ns, projection_path.read_bytes())
    assert console.source_reference == str(projection_path.resolve())
    assert console.pipeline[3].artifact_hash == "sha256:" + sha256(before[2]).hexdigest()
    assert before == after


def test_projection_freshness_is_observed_within_seven_days() -> None:
    payload = _projection()
    payload["blockers"] = []
    payload["lineage"]["generated_at"] = "2026-07-14T08:00:00Z"  # type: ignore[index]

    console = ResearchConsoleSourceService(
        projection_provider=lambda: payload,
        clock=lambda: datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc),
    ).inspect()

    assert console.overall_status == "observed"
    assert "projection_stale" not in console.blockers


def test_stale_projection_is_visible_but_degraded() -> None:
    payload = _projection()
    payload["blockers"] = []
    payload["lineage"]["generated_at"] = "2026-07-01T08:00:00Z"  # type: ignore[index]

    console = ResearchConsoleSourceService(
        projection_provider=lambda: payload,
        clock=lambda: datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc),
    ).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_stale",)
    assert console.pipeline[3].identity == payload["identity"]["research_run_id"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("generated_at", "expected"),
    [
        (None, "projection_generated_at_missing"),
        ("not-a-timestamp", "projection_generated_at_invalid"),
        ("2026-07-17T09:00:01Z", "projection_generated_at_future"),
    ],
)
def test_projection_timestamp_diagnostics_fail_degraded(
    generated_at: str | None,
    expected: str,
) -> None:
    payload = _projection()
    payload["blockers"] = []
    if generated_at is None:
        payload["lineage"].pop("generated_at", None)  # type: ignore[union-attr]
    else:
        payload["lineage"]["generated_at"] = generated_at  # type: ignore[index]

    console = ResearchConsoleSourceService(
        projection_provider=lambda: payload,
        clock=lambda: datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc),
    ).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == (expected,)


def test_projection_age_threshold_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_projection_age"):
        ResearchConsoleSourceService(max_projection_age=timedelta(0))


def test_invalid_or_unsafe_projection_fails_closed() -> None:
    unsafe = _projection()
    unsafe["status"] = {
        "formal_oos": True,
        "alpha_bp": 100,
        "apply_flags": {"apply_trading": True},
    }

    console = ResearchConsoleSourceService(projection_provider=lambda: unsafe).inspect()

    assert console.overall_status == "degraded"
    assert "projection_boundary_violation" in console.blockers
    assert console.boundary.formal_oos_allowed is False
    assert console.boundary.production_blend_alpha_bp == 0


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"apply_to_scoring": False},
        {
            "apply_to_scoring": False,
            "apply_to_recommendation": False,
            "apply_to_portfolio": False,
            "apply_to_exit": False,
            "unexpected": False,
        },
        {
            "apply_to_scoring": True,
            "apply_to_recommendation": False,
            "apply_to_portfolio": False,
            "apply_to_exit": False,
        },
    ],
)
def test_noncanonical_apply_flags_fail_closed(flags: dict[str, bool]) -> None:
    unsafe = _projection()
    unsafe["status"]["apply_flags"] = flags  # type: ignore[index]

    console = ResearchConsoleSourceService(projection_provider=lambda: unsafe).inspect()

    assert console.overall_status == "degraded"
    assert "projection_boundary_violation" in console.blockers


@pytest.mark.parametrize("alpha", [False, 0.0])
def test_non_integer_zero_alpha_fails_closed(alpha: object) -> None:
    unsafe = _projection()
    unsafe["status"]["alpha_bp"] = alpha  # type: ignore[index]

    console = ResearchConsoleSourceService(projection_provider=lambda: unsafe).inspect()

    assert console.overall_status == "degraded"
    assert "projection_boundary_violation" in console.blockers


def test_canonical_apply_flags_and_integer_zero_alpha_are_accepted() -> None:
    console = ResearchConsoleSourceService(projection_provider=_projection).inspect()

    assert "projection_boundary_violation" not in console.blockers


@pytest.mark.parametrize("scope", [None, "production_ready"])
def test_noncanonical_or_missing_scope_fails_closed(scope: str | None) -> None:
    unsafe = _projection()
    if scope is None:
        unsafe["status"].pop("scope")  # type: ignore[union-attr]
    else:
        unsafe["status"]["scope"] = scope  # type: ignore[index]

    console = ResearchConsoleSourceService(projection_provider=lambda: unsafe).inspect()

    assert console.overall_status == "degraded"
    assert "projection_boundary_violation" in console.blockers


def test_provider_failure_returns_degraded_console_instead_of_escaping() -> None:
    def failed_provider() -> dict[str, object]:
        raise RuntimeError("provider unavailable")

    console = ResearchConsoleSourceService(projection_provider=failed_provider).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_read_failed",)


def test_governance_provider_failure_returns_degraded_console() -> None:
    def failed_governance() -> dict[str, object]:
        raise RuntimeError("governance unavailable")

    console = ResearchConsoleSourceService(
        projection_provider=_projection,
        governance_provider=failed_governance,
    ).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_schema_invalid",)


def test_injected_governance_projection_copies_ev_p0_broker_and_artifact_status() -> None:
    governance = {
        "gates": [
            {
                "gate_id": "EV2",
                "status": "provisional",
                "detail": "Human source decision pending",
                "artifact_citation": "ev2:review-package",
            }
        ],
        "sources": [
            {
                "source_id": "institutional_flows",
                "lane": "p0",
                "status": "candidate",
                "allowed_use": "Development Only",
                "observed_rows": 12,
                "revision": "candidate-r1",
            },
            {
                "source_id": "broker_dataset",
                "lane": "broker",
                "status": "degraded",
                "allowed_use": "Research Only",
                "degraded_reason": "license_pending",
            },
        ],
        "artifacts": [
            {
                "artifact_type": "source_review",
                "artifact_id": "ev2:review-package",
                "status": "provisional",
                "citation": "sanitized-governance-projection",
            }
        ],
    }

    console = ResearchConsoleSourceService(
        projection_provider=_projection,
        governance_provider=lambda: governance,
    ).inspect()

    ev2 = next(row for row in console.gates if row.gate_id == "EV2")
    institutional = next(row for row in console.sources if row.source_id == "institutional_flows")
    broker = next(row for row in console.sources if row.lane == "broker")
    assert ev2.status == "provisional"
    assert institutional.status == "candidate" and institutional.observed_rows == 12
    assert broker.status == "degraded" and broker.degraded_reason == "license_pending"
    assert len(tuple(row for row in console.sources if row.lane == "p0")) == 13
    assert any(row.artifact_id == "ev2:review-package" for row in console.artifacts)


def test_mops_sanitized_projection_is_read_by_research_console_service(tmp_path: Path) -> None:
    from data_module.mops_daily_research_freshness import run_mops_daily_freshness_diagnostics
    from data_module.mops_ezsearch_statement_availability import MOPS_MARKETS, MOPS_STATEMENT_ITEMS, MOPSQueryResult

    # Create dummy full success matrix
    results = []
    for market in MOPS_MARKETS:
        for item in sorted(MOPS_STATEMENT_ITEMS):
            results.append(
                MOPSQueryResult(
                    market=market,
                    announcement_item=item,
                    rows=(
                        {
                            "CDATE": "115/07/27",
                            "CTIME": "18:17:06",
                            "TYPEK": market,
                            "COMPANY_ID": "2330",
                            "COMPANY_NAME": "台積電",
                            "CODE_NAME": "半導體業",
                            "AN_CODE": item,
                            "AN_NAME": "資產負債表",
                            "SUBJECT": "115年第2季資產負債表",
                            "HYPERLINK": "https://mopsov.twse.com.tw/mops/web/ajax_t164sb03?co_id=2330&year=115&season=2",
                        },
                    ),
                    response_sha256="a" * 64,
                    source_status="success",
                )
            )

    diag = run_mops_daily_freshness_diagnostics(
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 27),
        output_root=tmp_path,
        query_results=results,
        captured_at="2026-07-27T20:00:00+08:00",
    )

    console = ResearchConsoleSourceService(
        projection_path=diag.sanitized_projection_path,
        clock=lambda: datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc),
    ).inspect()

    assert console.blockers == ("mops_multi_day_baseline_missing",)
    assert console.overall_status == "degraded"
    mops_source = next(row for row in console.sources if row.source_id == "pit.quarterly_financials")
    assert mops_source.status == "observed"
    assert mops_source.observed_rows == 4


def test_mops_projection_unknown_schema_fails_closed(tmp_path: Path) -> None:
    payload = _projection()
    payload.update(
        {
            "schema_version": "mops-sanitized-research-projection.unknown",
            "source": "mops.ezsearch.statement_publication",
            "p0_lane": "pit.quarterly_financials",
        }
    )
    path = tmp_path / "unknown-mops-projection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    console = ResearchConsoleSourceService(projection_path=path).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_schema_invalid",)


def test_mops_projection_with_raw_or_credential_key_fails_closed(
    tmp_path: Path,
) -> None:
    payload = {
        **_projection(),
        "schema_version": "mops-sanitized-research-projection.v1",
        "source": "mops.ezsearch.statement_publication",
        "p0_lane": "pit.quarterly_financials",
        "source_decision": "decision:mops.ezsearch.statement_publication:20260727-r1",
        "acceptance": "limited",
        "formal_allowed": False,
        "production_allowed": False,
        "current_artifact_hash": "sha256:" + "a" * 64,
        "multi_day_evidence_ready": False,
        "current_run_status": "observed",
        "counts": {"events": 1},
        "sources": [
            {
                "source_id": "pit.quarterly_financials",
                "lane": "p0",
                "status": "observed",
            }
        ],
        "headers": {"Cookie": "must-not-be-projected"},
    }
    path = tmp_path / "unsafe-mops-projection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    console = ResearchConsoleSourceService(projection_path=path).inspect()

    assert console.overall_status == "degraded"
    assert console.blockers == ("projection_schema_invalid",)


def test_mops_capture_failure_projection_is_degraded(tmp_path: Path) -> None:
    from data_module.mops_daily_research_freshness import (
        run_mops_daily_freshness_diagnostics,
    )

    diag = run_mops_daily_freshness_diagnostics(
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 27),
        output_root=tmp_path,
        captured_at="2026-07-27T20:00:00+08:00",
    )
    console = ResearchConsoleSourceService(
        projection_path=diag.sanitized_projection_path,
        clock=lambda: datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc),
    ).inspect()

    assert diag.exit_code == 1
    assert console.overall_status == "degraded"
    assert console.blockers == ("mops_capture_failed",)
    mops_source = next(
        row for row in console.sources if row.source_id == "pit.quarterly_financials"
    )
    assert mops_source.status == "degraded"


def test_p0_quarterly_source_service_attaches_read_only_formal_impact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.research_console_source_service as source_module
    from data_module.open_data_quarterly_announcement_crosswalk import AUDIT_SCHEMA

    database = tmp_path / "formal.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE fundamental_statement_items (
                stock_code TEXT NOT NULL,
                statement_type TEXT NOT NULL,
                period TEXT NOT NULL,
                announced_date TEXT,
                source_version TEXT NOT NULL,
                item_code TEXT NOT NULL
            )
            """
        )
    crosswalk = {
        "schema_version": AUDIT_SCHEMA,
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "status": "available",
        "resources": [
            {
                "market": "TWSE",
                "statement": "income_statement",
                "rows": [
                    {
                        "issuer_code": "2330",
                        "fiscal_period": "2026-Q2",
                        "status": "one_announcement_candidate",
                        "announcement_timestamp_resolution": "unique_candidate_timestamp",
                        "announcement_count": 1,
                        "announcement_candidates": [
                            {
                                "announcement_at": "2026-08-14T14:00:00+08:00",
                                "event_sha256": "a" * 64,
                                "source_sha256": "b" * 64,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        source_module,
        "audit_quarterly_candidate_root",
        lambda _root: type("Audit", (), {"to_dict": lambda self: {"errors": []}})(),
    )
    monkeypatch.setattr(
        source_module, "build_quarterly_announcement_crosswalk", lambda **_kwargs: crosswalk
    )

    def capture_build(_service: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        source_module.P0SourceControlCenterService, "build", capture_build
    )
    service = ResearchConsoleSourceService(
        p0_quarterly_candidate_root=tmp_path,
        p0_mops_announcement_candidate_roots=(tmp_path,),
        p0_formal_db_path=database,
    )

    service._build_p0_source_control_center(None, None)

    projected = captured["quarterly_announcement_crosswalk"]
    assert isinstance(projected, dict)
    impact = projected["formal_impact"]
    assert impact["status"] == "observed"
    assert impact["candidate_unique_keys"] == 1
    assert impact["formal_identity_overlap"] == 0
    assert impact["formal_item_rows"] == 0
    assert impact["missing_announcement_date_rows"] == 0
    assert impact["exact_version_links"] == 0
    assert impact["rows_cleared"] == 0
    assert "candidate_event_to_content_version_bridge_missing" in impact["blockers"]


def test_p0_source_service_projects_formal_monthly_quality_at_top_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.research_console_source_service as source_module

    database = tmp_path / "formal-monthly.db"
    quality = {
        "schema_version": "baldr.formal_monthly_revenue_quality_by_period.v2",
        "status": "observed",
        "periods": [
            {
                "period": "2026-01",
                "formal_row_count": 2,
                "missing_announcement_date_row_count": 1,
                "report_level_date_unverified_row_count": 0,
                "distinct_stock_code_count": 2,
                "distinct_source_version_count": 1,
            }
        ],
        "blockers": [],
        "scope": "formal_monthly_revenue_rows_grouped_by_period",
        "formal_db_write": False,
        "financial_values_returned": False,
    }
    captured: dict[str, object] = {}

    def read_quality(
        path: Path, availability_mapping_path: Path | None = None
    ) -> dict[str, object]:
        captured["path"] = path
        captured["availability_mapping_path"] = availability_mapping_path
        return quality

    monkeypatch.setattr(
        source_module,
        "read_formal_monthly_revenue_quality_by_period",
        read_quality,
    )
    service = ResearchConsoleSourceService(p0_formal_db_path=database)

    center = service._build_p0_source_control_center(None, None)
    payload = center.to_dict()

    assert captured["path"] == database
    assert captured["availability_mapping_path"] is None
    assert payload["formal_monthly_revenue_quality"] == quality
    assert all(
        "formal_monthly_revenue_quality" not in row
        for row in payload["rows"]
    )


def test_p0_source_service_without_formal_db_keeps_monthly_quality_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.research_console_source_service as source_module

    def unexpected_read(_path: Path) -> dict[str, object]:
        raise AssertionError("reader must not be called without configured DB path")

    monkeypatch.setattr(
        source_module,
        "read_formal_monthly_revenue_quality_by_period",
        unexpected_read,
    )
    center = ResearchConsoleSourceService()._build_p0_source_control_center(None, None)

    quality = center.to_dict()["formal_monthly_revenue_quality"]
    assert quality == {
        "schema_version": "baldr.formal_monthly_revenue_quality_by_period.v2",
        "status": "unavailable",
        "periods": None,
        "blockers": ["formal_monthly_revenue_database_path_not_configured"],
        "scope": "unknown",
        "formal_db_write": False,
        "financial_values_returned": False,
    }


def test_p0_source_service_reads_monthly_quality_details_from_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app_module.research_console_source_service as source_module

    database = tmp_path / "formal-monthly.db"
    availability = tmp_path / "availability.csv"
    expected = {
        "schema_version": "baldr.formal_monthly_revenue_quality_rows.v2",
        "status": "observed",
        "period": "2026-04",
        "mapping_status": "verified",
        "rows": [
            {
                "stock_code": "2330",
                "source": "fixture.monthly_revenue",
                "source_version": "source-v1",
                "stored_announced_date": None,
                "mapping_match_state": "exact_version_mapping_present",
                "mapping_announced_date": "2026-05-08",
            }
        ],
        "total_count": 1,
        "limit": 100,
        "offset": 0,
        "has_more": False,
        "blockers": [],
        "scope": "formal_monthly_revenue_announcement_quality_identity_page",
        "formal_db_write": False,
        "financial_values_returned": False,
    }
    captured: dict[str, object] = {}

    def read_details(
        path: Path,
        *,
        period: str,
        offset: int,
        limit: int,
        availability_mapping_path: Path | None,
    ) -> dict[str, object]:
        captured.update(
            path=path,
            period=period,
            offset=offset,
            limit=limit,
            availability_mapping_path=availability_mapping_path,
        )
        return expected

    monkeypatch.setattr(
        source_module,
        "read_formal_monthly_revenue_quality_missing_rows",
        read_details,
    )
    service = ResearchConsoleSourceService(
        p0_formal_db_path=database,
        p0_monthly_revenue_availability_path=availability,
    )

    result = service.read_formal_monthly_revenue_quality_missing_rows(
        "2026-04", offset=0, limit=100
    )

    assert captured == {
        "path": database,
        "period": "2026-04",
        "offset": 0,
        "limit": 100,
        "availability_mapping_path": availability,
    }
    assert result == expected
