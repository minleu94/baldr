from app_module.evidence_pipeline_runner import _split_warning_and_advisory_counts
from scripts.scheduled.run_scheduled_evidence_pipeline_dry_run import _pipeline_status_fields


def test_informational_messages_do_not_hide_missing_position_evidence():
    warnings, advisories = _split_warning_and_advisory_counts([
        "portfolio_alerts:position_health_baseline_is_not_an_exit_instruction",
        "portfolio_alerts:position_health_daily_refresh_does_not_evaluate_transition",
        "portfolio_alerts:paper_position_identity_unproven:1418",
        "portfolio_alert_not_ready",
    ])
    assert len(advisories) == 2
    assert warnings == {
        "portfolio_alerts:paper_position_identity_unproven:1418": 1,
        "portfolio_alert_not_ready": 1,
    }


def test_sample_wait_preserves_real_blockers():
    fields = _pipeline_status_fields({
        "warning_counts": {
            "forward_summary_status:INSUFFICIENT_SAMPLE": 1,
            "missing_event_price": 2,
            "portfolio_alert_not_ready": 1,
        },
        "errors_count": 1,
    })
    assert fields["pipeline_natural_maturity_warning_count"] == 1
    assert fields["pipeline_actionable_warning_counts"] == {
        "missing_event_price": 2, "portfolio_alert_not_ready": 1,
    }
    assert fields["pipeline_errors_count"] == 1
