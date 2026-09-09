from app_module.v4_effectiveness_evaluator import evaluate_v4_effectiveness


def _row(day, outcome, score, result, *, horizon=5, status="ready", benchmark=10):
    return {
        "decision_date": day,
        "outcome_id": outcome,
        "horizon_days": horizon,
        "strategy_version": "rule-v4.1",
        "universe_id": "twse-liquid",
        "cost_model": "paper-balanced-v1",
        "benchmark_id": "twse-ew",
        "status": status,
        "score_bp": score,
        "return_bp": result,
        "benchmark_excess_bp": benchmark,
        "industry_excess_bp": 5,
    }


def test_top_k_is_calculated_per_decision_day_and_then_averaged():
    report = evaluate_v4_effectiveness(
        [
            _row("2026-09-01", "a", 9000, 100),
            _row("2026-09-01", "b", 8000, -100),
            _row("2026-09-02", "c", 7000, -100),
            _row("2026-09-02", "d", 6000, 100),
            _row("2026-09-03", "e", 5000, 100),
        ],
        k=1,
        minimum_decision_days=3,
        minimum_mature_outcomes=1,
    )

    slice_ = report.slices[0]
    # Day-level precision is 100%, 0%, 100%; global ranking would incorrectly
    # return 100% because it sees only the highest score.
    assert slice_.precision_at_k_bp == 6666
    assert slice_.decision_day_count == 3
    assert slice_.evaluation_status == "ready_for_manual_review"


def test_pending_and_missing_rows_do_not_count_as_mature_samples():
    report = evaluate_v4_effectiveness(
        [
            _row("2026-09-01", "ready", 9000, 100),
            _row("2026-09-01", "pending", 8000, 500, status="pending"),
            _row("2026-09-01", "missing", 7000, 500, status="missing"),
        ],
        minimum_decision_days=1,
        minimum_mature_outcomes=2,
    )

    slice_ = report.slices[0]
    assert slice_.mature_outcome_count == 1
    assert slice_.pending_outcome_count == 1
    assert slice_.missing_outcome_count == 1
    assert slice_.evaluation_status == "insufficient_mature_outcomes"


def test_cohort_fields_and_coverage_are_kept_separate():
    rows = [
        _row("2026-09-01", "a", 9000, 100, benchmark=20),
        _row("2026-09-02", "b", 8000, 100, benchmark=None),
        _row("2026-09-01", "other-horizon", 9000, 100, horizon=10),
    ]
    rows[1]["benchmark_excess_bp"] = None
    report = evaluate_v4_effectiveness(
        rows,
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )

    assert len(report.slices) == 2
    five_day = next(item for item in report.slices if item.horizon_days == 5)
    assert five_day.mature_outcome_count == 2
    assert five_day.benchmark_coverage_bp == 5000
    assert "benchmark_coverage_incomplete" in five_day.warnings


def test_unknown_status_is_conservative_and_empty_input_is_explicit():
    report = evaluate_v4_effectiveness(
        [_row("2026-09-01", "unknown", 9000, 100, status="unexpected")],
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )
    slice_ = report.slices[0]
    assert slice_.mature_outcome_count == 0
    assert slice_.missing_outcome_count == 1
    assert "unknown_status:unexpected" in slice_.warnings

    empty = evaluate_v4_effectiveness([])
    assert empty.slices == ()
    assert empty.warnings == ("no_valid_cohort_rows",)


def test_invalid_row_diagnostics_are_counted_instead_of_expanding_warning_list():
    rows = [
        {
            "decision_date": "2026-09-01",
            "horizon_days": 5,
            "strategy_version": "rule-v4.1",
            "universe_id": "",
            "cost_model": "paper-balanced-v1",
            "benchmark_id": "twse-ew",
            "status": "missing",
        }
        for _ in range(500)
    ]

    report = evaluate_v4_effectiveness(rows)

    assert report.slices == ()
    assert report.warnings == (
        "no_valid_cohort_rows",
        "rows_incomplete_cohort_identity:500",
    )


def test_known_unavailable_outcome_status_is_missing_without_unknown_warning():
    report = evaluate_v4_effectiveness(
        [_row("2026-09-01", "missing-price", 9000, 100, status="missing_price")],
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )

    slice_ = report.slices[0]
    assert slice_.mature_outcome_count == 0
    assert slice_.missing_outcome_count == 1
    assert "unknown_status:missing_price" not in slice_.warnings


def test_gross_no_cost_identity_is_explicitly_warned():
    row = _row("2026-09-01", "gross", 9000, 100)
    row["cost_model"] = "gross-close-to-close-no-cost-v1"

    report = evaluate_v4_effectiveness(
        [row],
        minimum_decision_days=1,
        minimum_mature_outcomes=1,
    )

    slice_ = report.slices[0]
    assert "cost_model_not_cost_adjusted" in slice_.warnings
    assert slice_.evaluation_status == "ready_for_manual_review_with_warnings"
