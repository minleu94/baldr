"""R019 service-level compatibility for native integer industry changes."""

from __future__ import annotations

from typing import Any

import pytest

from test_r019_reason_regime_parity import _build_service, _run


@pytest.mark.parametrize(
    ("industry_percent", "expected_status", "expected_reason", "expected_items"),
    [
        (
            10**400,
            "degraded",
            "screening_exception",
            0,
        ),
        (
            -(10**400),
            "pass",
            "recommendation_selected",
            1,
        ),
    ],
)
def test_large_native_integer_industry_change_keeps_service_parity(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    industry_percent: int,
    expected_status: str,
    expected_reason: str,
    expected_items: int,
) -> None:
    service, _mapper, _pit_reader, source_reads, observations = _build_service(
        tmp_path,
        industry_percent=industry_percent,
    )

    execution, body, capture = _run(
        service,
        monkeypatch,
        result_id=f"r019-industry-integer-{expected_status}",
    )

    assert execution.status.value == "completed"
    assert len(execution.decision.items) == expected_items
    assert len(body.dispositions) == 1
    disposition = body.dispositions[0]
    assert disposition.status == expected_status
    assert disposition.reason_codes == (expected_reason,)

    matrix_row = capture["compatibility_snapshot"].materialize()["last_screening_matrix"][0]
    assert matrix_row["status"] == expected_status
    assert matrix_row["reason_codes"] == [expected_reason]

    # Both signs follow the same source read sequence. Only the positive path
    # fails when the old int * 0.5 expression converted the integer to float.
    order, _formatted_inputs = observations
    assert order[-5:] == [
        "pe",
        "monthly_revenue",
        "industry_mapper",
        "reason_engine",
        "industry_performance",
    ]
    assert [entry[0] for entry in source_reads] == ["pe", "monthly_revenue"]

    if industry_percent > 0:
        assert disposition.quality == "degraded"
        assert disposition.warnings == ("screening_exception:OverflowError",)
        assert matrix_row["quality"] == "degraded"
        assert matrix_row["warnings"] == ["screening_exception:OverflowError"]
    else:
        assert disposition.quality == "observed"
        assert disposition.warnings == ()
        assert body.decision.items[0].reasons == ("基本理由",)
