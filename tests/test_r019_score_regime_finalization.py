"""Service accounting parity for the decision-owned late score gate."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from test_r019_reason_regime_parity import _build_service, _run


@pytest.mark.parametrize(
    ("final_score", "expected_status", "expected_summary"),
    [
        (None, "missing", "無結果=1, 異常=0"),
        ("not-a-score", "degraded", "無結果=0, 異常=1"),
        (Decimal("84.01"), "pass", "成功=1"),
    ],
)
def test_late_score_gate_keeps_missing_exception_and_success_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    final_score: Any,
    expected_status: str,
    expected_summary: str,
) -> None:
    caplog.set_level(logging.INFO, logger="app_module.recommendation_service")
    service, _mapper, _pit_reader, _source_reads, _observations = _build_service(
        tmp_path,
        industry_percent=None,
        final_score=final_score,
    )

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id=f"r019-final-score-accounting-{expected_status}",
    )

    assert execution.status.value == "completed"
    assert body.dispositions[0].status == expected_status
    assert expected_summary in caplog.text
    if expected_status == "missing":
        assert capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]["reason_codes"] == [
            "total_score_missing_or_nonfinite"
        ]
    elif expected_status == "degraded":
        assert body.dispositions[0].warnings == (
            "screening_exception:InvalidOperation",
        )
    else:
        assert len(execution.decision.items) == 1
