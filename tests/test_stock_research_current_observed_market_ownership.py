from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

from app_module.stock_research_report_service import StockResearchReportReadService
from data_module.current_observed_market_ownership_reader import (
    CurrentOwnershipObservation,
    CurrentOwnershipReadResult,
)
import data_module.current_observed_market_ownership_reader as ownership_reader


def _service(tmp_path, monkeypatch, result, *, clock: datetime):
    main_db = tmp_path / "formal.sqlite"
    with sqlite3.connect(main_db):
        pass
    output_root = tmp_path / "output"
    config = SimpleNamespace(
        db_file=main_db,
        data_root=tmp_path,
        output_root=output_root,
        resolve_output_path=lambda relative: output_root / relative,
    )
    observed_calls: list[dict[str, object]] = []

    def fake_reader(**kwargs):
        observed_calls.append(kwargs)
        return result

    monkeypatch.setattr(ownership_reader, "read_current_observed_market_ownership", fake_reader)
    service = StockResearchReportReadService(
        config,
        clock=lambda: clock,
        candidate_db_file=None,
        current_ownership_capture_root=tmp_path / "isolated-capture-root",
    )
    return service, observed_calls


def _observations() -> CurrentOwnershipReadResult:
    observed = "2026-10-05T01:42:44Z"
    return CurrentOwnershipReadResult(
        observations={
            "institutional": CurrentOwnershipObservation(
                source_kind="institutional",
                stock_code="1477",
                data_as_of="2026-10-02",
                values={"foreign_investor_net": -6732},
                source_version="twse-official-T86",
                custody_kind="normalized_custody",
                custody_sha256="a" * 64,
                observed_at=observed,
                row_count=1,
                limitations=(),
                quantity_unit="shares",
            ),
            "credit": CurrentOwnershipObservation(
                source_kind="credit",
                stock_code="1477",
                data_as_of="2026-10-02",
                values={"margin_purchase": 16, "margin_balance": 1758, "short_sale": 0},
                source_version="tpex-mainboard-margin-openapi.v1",
                custody_kind="normalized_custody",
                custody_sha256="b" * 64,
                observed_at=observed,
                row_count=2,
                limitations=(),
                quantity_unit="shares",
            ),
            "tdcc": CurrentOwnershipObservation(
                source_kind="tdcc",
                stock_code="1477",
                data_as_of="2026-10-02",
                values={
                    "large_holder_ratio_bp": 5013,
                    "retail_holder_ratio_bp": 2101,
                    "dispersion_index_bp": -2912,
                    "shareholding_tiers": "[]",
                },
                source_version="tdcc-official-od-1-5",
                custody_kind="raw_capture_replayed",
                custody_sha256="c" * 64,
                observed_at=observed,
                row_count=17,
                limitations=(),
            ),
        },
        diagnostics={},
    )


def test_current_report_surfaces_candidate_values_and_non_pit_provenance(tmp_path, monkeypatch) -> None:
    clock = datetime(2026, 10, 5, 9, 42, tzinfo=timezone.utc)
    service, calls = _service(tmp_path, monkeypatch, _observations(), clock=clock)

    report = service.read_report("1477")

    assert len(calls) == 1
    assert calls[0]["stock_code"] == "1477"
    assert calls[0]["cutoff"] == date(2026, 10, 5)
    assert calls[0]["observed_at"] == clock
    assert calls[0]["capture_root"] == tmp_path / "isolated-capture-root"
    institutional = next(item for item in report.institutional if item.key == "foreign_investor_net")
    assert institutional.value == Decimal("-6732")
    assert institutional.unit == "股"
    assert institutional.data_as_of == "2026-10-02"
    assert institutional.available_at == ""
    credit = next(item for item in report.credit if item.key == "margin_purchase")
    assert credit.value == Decimal("16")
    assert credit.unit == "股"
    assert next(item for item in report.credit if item.key == "short_sale").value == Decimal("0")
    tdcc = {item.key: item for item in report.shareholding}
    assert tdcc["large_holder_ratio_bp"].value == Decimal("5013")
    assert tdcc["large_holder_ratio_bp"].unit == "基點"
    assert tdcc["shareholding_tiers"].value_text == "[]"
    sources = {item.source_id: item for item in report.sources}
    expected_ids = {
        "candidate.phase3c.institutional_normalized",
        "candidate.phase3c.credit_normalized",
        "candidate.tdcc.raw_current_observed",
    }
    assert expected_ids.issubset(sources)
    for source_id in expected_ids:
        source = sources[source_id]
        assert source.candidate_only is True
        assert source.current_observed_only is True
        assert source.historical_pit_eligible is False
        assert source.available_at == ""
        assert source.observed_at == "2026-10-05T01:42:44Z"
        assert "非歷史 PIT" in source.source_label
        assert "可用時間未知" in source.freshness_reason


def test_explicit_historical_report_does_not_read_current_ownership(tmp_path, monkeypatch) -> None:
    service, calls = _service(
        tmp_path,
        monkeypatch,
        _observations(),
        clock=datetime(2026, 10, 5, 9, 42, tzinfo=timezone.utc),
    )

    report = service.read_report("1477", as_of_date="2026-10-02")

    assert calls == []
    assert report.institutional == ()
    assert report.credit == ()
    assert report.shareholding == ()
    assert not any(source.source_id.startswith("candidate.") for source in report.sources)


def test_current_report_exposes_rejected_source_diagnostic_without_relabeling_old_rows(
    tmp_path, monkeypatch
) -> None:
    result = CurrentOwnershipReadResult(
        observations={},
        diagnostics={
            "institutional": "selected newest normalized observation hash mismatch",
            "credit": "no verified latest credit observation contains this stock",
            "tdcc": "newest TDCC manifest body completion is later than readback clock",
        },
    )
    service, _calls = _service(
        tmp_path,
        monkeypatch,
        result,
        clock=datetime(2026, 10, 5, 9, 42, tzinfo=timezone.utc),
    )

    report = service.read_report("1477")

    sources = {item.source_id: item for item in report.sources}
    for source_id, expected in (
        ("candidate.phase3c.institutional_normalized", "hash mismatch"),
        ("candidate.phase3c.credit_normalized", "contains this stock"),
        ("candidate.tdcc.raw_current_observed", "later than readback clock"),
    ):
        source = sources[source_id]
        assert source.row_count == 0
        assert source.candidate_only is True
        assert source.current_observed_only is True
        assert source.historical_pit_eligible is False
        assert expected in source.freshness_reason
        assert source.available_at == ""
