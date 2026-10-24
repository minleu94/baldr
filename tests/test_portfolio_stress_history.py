from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from app_module.portfolio_stress_history import (
    PortfolioStressHistoryReadService,
    PortfolioStressHistoryRecord,
    PortfolioStressHistoryRepository,
)
from app_module.portfolio_stress_lab_service import PortfolioStressLabService


def _stress_payload(*, research_only: bool = True) -> dict[str, object]:
    position = SimpleNamespace(
        is_holding=True,
        stock_code="2330",
        stock_name="台積電",
        quantity=Decimal("10"),
        current_price=Decimal("100.00"),
    )
    result = PortfolioStressLabService().evaluate_positions(
        [position],
        scenario_id="fast_drop",
        as_of_date="2026-08-27",
    )
    payload = result.to_dict()
    payload["research_only"] = research_only
    return payload


def _positions_payload(positions, *, scenario_id: str = "fast_drop") -> dict[str, object]:
    return PortfolioStressLabService().evaluate_positions(
        positions,
        scenario_id=scenario_id,
        as_of_date="2026-08-27",
    ).to_dict()


def test_record_from_stress_payload_is_deterministic_and_research_only() -> None:
    payload = _stress_payload()

    first = PortfolioStressHistoryRecord.from_payload(payload)
    second = PortfolioStressHistoryRecord.from_payload(payload)

    assert first.record_id == second.record_id
    assert first.payload_hash == second.payload_hash
    assert first.as_of_date == "2026-08-27"
    assert first.value_delta == Decimal("-100.00")
    assert first.research_only is True
    assert first.investment_effectiveness_claim is False


def test_saved_position_projection_uses_payload_order_and_exact_quote_fields() -> None:
    positions = (
        SimpleNamespace(
            is_holding=True,
            position_id="position-a",
            portfolio_id="default",
            stock_code="2330",
            stock_name="持倉 A",
            quantity=Decimal("10"),
            current_price=Decimal("100.00"),
            quote_data_date="2026-08-26",
            quote_source_id="sqlite.daily_prices",
            quote_source_snapshot_hash="a" * 64,
            quote_freshness_status="current",
        ),
        SimpleNamespace(
            is_holding=True,
            position_id="position-b",
            portfolio_id="default",
            stock_code="2330",
            stock_name="持倉 B",
            quantity=Decimal("20"),
            current_price=Decimal("101.00"),
            quote_data_date="2026-08-25",
            quote_source_id="csv.daily_prices",
            quote_source_snapshot_hash="b" * 64,
            quote_freshness_status="stale",
        ),
    )
    record = PortfolioStressHistoryRecord.from_payload(_positions_payload(positions))

    projection = record.project_position_rows()

    assert projection.status == "available"
    assert projection.blockers == ()
    assert projection.missing_price_codes == ()
    assert [row.row_index for row in projection.rows] == [0, 1]
    assert [row.stock_code for row in projection.rows] == ["2330", "2330"]
    assert [row.position_id for row in projection.rows] == ["position-a", "position-b"]
    assert [row.quantity for row in projection.rows] == ["10", "20"]
    assert [row.mark_price for row in projection.rows] == ["100.00", "101.00"]
    assert [row.quote_data_date for row in projection.rows] == [
        "2026-08-26",
        "2026-08-25",
    ]
    assert [row.quote_source_snapshot_hash for row in projection.rows] == [
        "a" * 64,
        "b" * 64,
    ]


def test_saved_position_projection_keeps_duplicate_position_identity_without_collapsing():
    position = SimpleNamespace(
        is_holding=True,
        position_id="same-id",
        portfolio_id="default",
        stock_code="2330",
        stock_name="持倉",
        quantity=Decimal("10"),
        current_price=Decimal("100.00"),
    )
    record = PortfolioStressHistoryRecord.from_payload(
        _positions_payload((position, position))
    )

    projection = record.project_position_rows()

    assert projection.status == "available"
    assert len(projection.rows) == 2
    assert [row.row_index for row in projection.rows] == [0, 1]
    assert [row.position_id for row in projection.rows] == ["same-id", "same-id"]
    assert "stress_history_duplicate_position_identity" in projection.diagnostics


def test_saved_position_projection_keeps_partial_rows_and_missing_codes_separate():
    positions = (
        SimpleNamespace(
            is_holding=True,
            position_id="position-priced",
            portfolio_id="default",
            stock_code="2330",
            stock_name="台積電",
            quantity=Decimal("10"),
            current_price=Decimal("100.00"),
        ),
        SimpleNamespace(
            is_holding=True,
            position_id="position-missing",
            portfolio_id="default",
            stock_code="2317",
            stock_name="鴻海",
            quantity=Decimal("20"),
            current_price=None,
        ),
    )

    projection = PortfolioStressHistoryRecord.from_payload(
        _positions_payload(positions)
    ).project_position_rows()

    assert projection.status == "available"
    assert len(projection.rows) == 1
    assert projection.rows[0].stock_code == "2330"
    assert projection.missing_price_codes == ("2317",)


def test_saved_position_projection_distinguishes_legacy_missing_rows_from_empty_rows():
    legacy_payload = _stress_payload()
    legacy_payload.pop("positions")
    legacy_payload.pop("missing_price_codes")
    legacy = PortfolioStressHistoryRecord.from_payload(legacy_payload)
    empty_payload = _positions_payload(())
    empty = PortfolioStressHistoryRecord.from_payload(empty_payload)

    legacy_projection = legacy.project_position_rows()
    empty_projection = empty.project_position_rows()

    assert legacy_projection.status == "not_recorded"
    assert legacy_projection.rows == ()
    assert legacy_projection.missing_price_codes is None
    assert empty_projection.status == "available"
    assert empty_projection.rows == ()
    assert empty_projection.missing_price_codes == ()


def test_saved_position_projection_accepts_legacy_v1_rows_without_optional_fields():
    payload = _stress_payload()
    for row in payload["positions"]:
        for field in (
            "position_id",
            "portfolio_id",
            "quote_data_date",
            "quote_source_id",
            "quote_source_snapshot_hash",
            "quote_freshness_status",
        ):
            row.pop(field, None)

    projection = PortfolioStressHistoryRecord.from_payload(
        payload
    ).project_position_rows()

    assert projection.status == "available"
    assert len(projection.rows) == 1
    assert projection.rows[0].position_id is None
    assert projection.rows[0].portfolio_id is None
    assert projection.rows[0].quote_data_date is None
    assert projection.rows[0].quote_source_id is None
    assert projection.rows[0].quote_source_snapshot_hash is None
    assert projection.rows[0].quote_freshness_status is None


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("quote_data_date", "2026-99-99"),
        ("quote_source_id", " "),
        ("quote_source_snapshot_hash", "not-a-hash"),
        ("quote_freshness_status", "trusted"),
    ),
)
def test_saved_position_projection_fails_closed_on_malformed_provenance(
    field: str, value: str
) -> None:
    payload = _stress_payload()
    payload["positions"][0][field] = value

    projection = PortfolioStressHistoryRecord.from_payload(
        payload
    ).project_position_rows()

    assert projection.status == "invalid"
    assert projection.rows == ()
    assert "stress_history_position_rows_invalid" in projection.blockers


def test_saved_position_projection_rejects_row_count_mismatch_without_recomputing_values():
    payload = _stress_payload()
    payload["priced_position_count"] = 2
    payload["total_position_count"] = 2

    record = PortfolioStressHistoryRecord.from_payload(payload)
    projection = record.project_position_rows()

    assert projection.status == "invalid"
    assert projection.rows == ()
    assert "stress_history_position_rows_invalid" in projection.blockers


def test_saved_position_projection_marks_missing_price_codes_unknown_not_zero():
    payload = _stress_payload()
    payload.pop("missing_price_codes")

    projection = PortfolioStressHistoryRecord.from_payload(
        payload
    ).project_position_rows()

    assert projection.status == "available"
    assert projection.missing_price_codes is None


def test_saved_position_projection_rejects_malformed_row_shape():
    payload = _stress_payload()
    payload["positions"][0] = ["not", "a", "mapping"]

    projection = PortfolioStressHistoryRecord.from_payload(
        payload
    ).project_position_rows()

    assert projection.status == "invalid"
    assert projection.rows == ()


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("scenario_id", "tampered-scenario"),
        ("scenario_label", "tampered label"),
        ("status", "partial"),
        ("priced_position_count", 0),
        ("total_position_count", 0),
        ("base_market_value", "999.00"),
        ("stressed_market_value", "999.00"),
        ("value_delta", "999.00"),
        ("as_of_date", "2026-08-28"),
        ("research_only", 0),
        ("investment_effectiveness_claim", 1),
    ),
)
def test_read_service_rejects_top_level_columns_that_disagree_with_payload(
    tmp_path: Path, column: str, value: object
) -> None:
    db_path = tmp_path / "stress_history.sqlite"
    record = PortfolioStressHistoryRecord.from_payload(_stress_payload())
    PortfolioStressHistoryRepository(db_path).append(record)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f"UPDATE portfolio_stress_history SET {column} = ? WHERE record_id = ?",
            (value, record.record_id),
        )
        connection.commit()

    result = PortfolioStressHistoryReadService(db_path).inspect()

    assert result.status == "degraded"
    assert result.records == ()
    assert "stress_history_invalid_row" in result.blockers


def test_repository_append_and_read_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "portfolio" / "stress_history.sqlite"
    record = PortfolioStressHistoryRecord.from_payload(_stress_payload())

    PortfolioStressHistoryRepository(db_path).append(record)
    result = PortfolioStressHistoryReadService(db_path).inspect()

    assert result.status == "ready"
    assert len(result.records) == 1
    assert result.records[0].payload_hash == record.payload_hash
    assert result.records[0].base_market_value == Decimal("1000.00")
    assert result.read_only is True
    assert result.writes_allowed is False


def test_read_service_missing_database_is_read_only_and_does_not_initialize(tmp_path: Path) -> None:
    db_path = tmp_path / "not_created" / "stress_history.sqlite"

    result = PortfolioStressHistoryReadService(db_path).inspect()

    assert result.status == "not_configured"
    assert "stress_history_not_configured" in result.warnings
    assert not db_path.exists()
    assert not db_path.parent.exists()


def test_repository_rejects_duplicate_deterministic_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "stress_history.sqlite"
    record = PortfolioStressHistoryRecord.from_payload(_stress_payload())
    repository = PortfolioStressHistoryRepository(db_path)
    repository.append(record)

    with pytest.raises(ValueError, match="already exists"):
        repository.append(record)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM portfolio_stress_history").fetchone()[0] == 1


def test_record_rejects_unsafe_input() -> None:
    with pytest.raises(ValueError, match="research_only"):
        PortfolioStressHistoryRecord.from_payload(_stress_payload(research_only=False))


def test_read_service_fails_closed_on_tampered_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "stress_history.sqlite"
    record = PortfolioStressHistoryRecord.from_payload(_stress_payload())
    PortfolioStressHistoryRepository(db_path).append(record)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE portfolio_stress_history SET payload_json = ? WHERE record_id = ?",
            (json.dumps({"tampered": True}), record.record_id),
        )
        connection.commit()

    result = PortfolioStressHistoryReadService(db_path).inspect()

    assert result.status == "degraded"
    assert result.records == ()
    assert "stress_history_invalid_row" in result.blockers
