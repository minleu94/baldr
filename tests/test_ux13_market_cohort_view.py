from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from app_module.daily_market_cohort_projection import (
    DailyMarketCohortMember,
    DailyMarketCohortMethodCount,
    DailyMarketCohortProjection,
)
from app_module.daily_market_method_contract import method_contracts_payload
from app_module.daily_market_research_screener import (
    DailyMarketResearchConditionResult,
    DailyMarketResearchScreenRow,
)
from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.research_session import ResearchStockContextDTO
from ui_qt.views import daily_market_research_view as daily_market_view_module
from ui_qt.views.daily_market_research_view import DailyMarketResearchView


_METHOD_KEYS = ("close_above_ma20", "close_above_ma60")
_DECISION_DATE = "2026-10-05"
_DATA_DATE = "2026-10-02"
_ROOT = Path("C:/qa/daily-market")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _snapshot(tag: str, *, codes: tuple[str, ...]) -> VerifiedDailyMarketSnapshot:
    manifest_hash = (tag * 64)[:64]
    identity_hash = (chr(ord(tag) + 1) * 64)[:64]
    return VerifiedDailyMarketSnapshot(
        cohort_id="controlled-cohort",
        decision_date=date.fromisoformat(_DECISION_DATE),
        manifest_sha256=manifest_hash,
        manifest_identity_sha256=identity_hash,
        completeness="complete_declared_cohort",
        manifest={
            "cohort_id": "controlled-cohort",
            "decision_date": _DECISION_DATE,
            "decision_cutoff": f"{_DECISION_DATE}T10:30:00+08:00",
            "declared_stock_codes": list(codes),
        },
        stock_snapshots={},
    )


def _condition(key: str, state: str, *, decision_date: str = _DECISION_DATE):
    contract = method_contracts_payload()[key]
    relation = "above" if state == "match" else "below" if state == "no_match" else "unknown"
    return DailyMarketResearchConditionResult(
        key=key,
        state=state,
        relation=relation,
        reason="snapshot_missing" if state == "unknown" else "",
        method_id=contract["method_id"],
        family=contract["family"],
        version=contract["version"],
        parameters=contract["parameters"],
        decision_date=decision_date,
        eligibility="unknown" if state == "unknown" else "eligible",
        unknown_reason="snapshot_missing" if state == "unknown" else None,
    )


def _screen_row(
    snapshot: VerifiedDailyMarketSnapshot,
    stock_code: str,
    state: str,
) -> DailyMarketResearchScreenRow:
    contract_by_key = method_contracts_payload()
    conditions = tuple(
        _condition(key, state if state == "unknown" else ("match" if index == 0 else state))
        for index, key in enumerate(_METHOD_KEYS)
    )
    return DailyMarketResearchScreenRow(
        stock_code=stock_code,
        cohort_id=snapshot.cohort_id,
        decision_date=snapshot.decision_date.isoformat(),
        data_date=_DATA_DATE,
        condition_keys=_METHOD_KEYS,
        combine_mode="AND",
        conditions=conditions,
        combined_state=state,
        why=("兩項觀察符合",) if state == "match" else (),
        why_not=("至少一項觀察不符合",) if state == "no_match" else (),
        source_snapshot_id=snapshot.manifest_identity_sha256,
        source_snapshot_hash=snapshot.manifest_sha256,
        snapshot_identity_sha256=(stock_code[-1] * 64)[:64],
        input_fingerprint_sha256="c" * 64,
        snapshot_root=str(_ROOT),
        completeness=snapshot.completeness,
    )


def _member(
    stock_code: str,
    *,
    close: str | None,
    ma20: str | None,
    ma60: str | None,
    snapshot_missing: bool = False,
) -> DailyMarketCohortMember:
    values = {
        "close_above_ma20": "unknown" if snapshot_missing else "match",
        "close_above_ma60": "unknown" if snapshot_missing else "match",
    }
    if stock_code == "2382":
        values["close_above_ma20"] = "no_match"
    if close is None:
        values["close_above_ma20"] = "unknown"
    conditions = tuple(_condition(key, values[key]) for key in _METHOD_KEYS)
    return DailyMarketCohortMember(
        stock_code=stock_code,
        data_date=None if snapshot_missing else _DATA_DATE,
        close=Decimal(close) if close is not None else None,
        ma20=Decimal(ma20) if ma20 is not None else None,
        ma60=Decimal(ma60) if ma60 is not None else None,
        conditions=conditions,
        source_refs=() if snapshot_missing else (
            ("daily_prices", "configured-main-daily-prices"),
            ("technical_indicators", "configured-main-technical-indicators"),
        ),
        snapshot_missing=snapshot_missing,
    )


def _projection(
    snapshot: VerifiedDailyMarketSnapshot,
    *,
    members: tuple[DailyMarketCohortMember, ...],
    published_codes: tuple[str, ...],
    missing_codes: tuple[str, ...] = (),
) -> DailyMarketCohortProjection:
    contracts = method_contracts_payload()
    method_counts = []
    for key in _METHOD_KEYS:
        states = tuple(member.condition(key).state for member in members)
        contract = contracts[key]
        method_counts.append(
            DailyMarketCohortMethodCount(
                key=key,
                method_id=contract["method_id"],
                family=contract["family"],
                version=contract["version"],
                parameters=tuple(sorted(contract["parameters"].items())),
                match_count=states.count("match"),
                no_match_count=states.count("no_match"),
                unknown_count=states.count("unknown"),
                denominator=len(members),
            )
        )
    return DailyMarketCohortProjection(
        cohort_id=snapshot.cohort_id,
        decision_date=snapshot.decision_date.isoformat(),
        manifest_schema_version="daily-market-research-manifest.v2",
        source_snapshot_id=snapshot.manifest_identity_sha256,
        source_snapshot_hash=snapshot.manifest_sha256,
        method_contracts_sha256="e" * 64,
        completeness=snapshot.completeness,
        declared_stock_codes=tuple(member.stock_code for member in members),
        published_stock_codes=published_codes,
        missing_stock_codes=missing_codes,
        published_count=len(published_codes),
        method_counts=tuple(method_counts),
        members=members,
    )


class _ProjectionService:
    def __init__(self, snapshots: tuple[VerifiedDailyMarketSnapshot, ...]) -> None:
        self.snapshot_root = _ROOT
        self.current = snapshots[0]
        self.snapshots = snapshots
        self.source_error = False
        self.filter_calls: list[tuple[object, tuple[str, ...], str]] = []
        self.produce_calls: list[tuple[object, ...]] = []

    def filter_rows(self, snapshot, condition_keys, combine_mode):
        keys = tuple(condition_keys)
        self.filter_calls.append((snapshot, keys, combine_mode))
        states = ("match", "no_match", "unknown")
        codes = tuple(snapshot.manifest["declared_stock_codes"])
        return tuple(
            _screen_row(snapshot, code, states[index % len(states)])
            for index, code in enumerate(codes)
            if code not in {"1101"}
        )

    def read_snapshot(self, cohort_id, decision_date, *, manifest_sha256=None, cancel_callback=None):
        del cohort_id, decision_date, manifest_sha256
        if cancel_callback and cancel_callback():
            raise RuntimeError("cancelled")
        if self.source_error:
            raise RuntimeError("snapshot_input_hash_mismatch")
        return self.current

    def produce_snapshot(self, *args, **kwargs):
        self.produce_calls.append((*args, kwargs))
        raise AssertionError("sort/filter must not produce snapshots")

    def context_for_stock(self, row, *, stock_name=""):
        return ResearchStockContextDTO(
            stock_code=row.stock_code,
            stock_name=stock_name,
            decision_date=row.decision_date,
            data_date=row.data_date,
            source_kind="daily_market_research_snapshot",
            source_workspace="recommendation",
            source_snapshot_id=row.source_snapshot_id,
            source_snapshot_hash=row.source_snapshot_hash,
            daily_snapshot_root=str(self.snapshot_root),
            daily_snapshot_cohort_id=row.cohort_id,
            daily_snapshot_condition_keys=",".join(row.condition_keys),
            daily_snapshot_combine_mode=row.combine_mode,
        )


def _install_projection(monkeypatch, projections, calls):
    def project(snapshot, rows, *, expected_snapshot_root=None):
        calls.append((snapshot, tuple(rows), expected_snapshot_root))
        return projections[snapshot.manifest_identity_sha256]

    monkeypatch.setattr(
        daily_market_view_module, "project_daily_market_cohort", project
    )


def _wait(view: DailyMarketResearchView) -> None:
    app = _app()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.processEvents()
        if view._worker is None:
            return
        QTest.qWait(5)
    assert view._worker is None


def _select_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_cohort_panel_counts_declared_members_and_marks_partial_rows_unknown(monkeypatch) -> None:
    _app()
    snapshot = _snapshot("b", codes=("1101", "1477", "2382"))
    members = (
        _member("1101", close=None, ma20=None, ma60=None, snapshot_missing=True),
        _member("1477", close="100.000", ma20="90", ma60="95"),
        _member("2382", close="9.99", ma20="10.01", ma60="8.5"),
    )
    projection = _projection(
        snapshot,
        members=members,
        published_codes=("1477", "2382"),
        missing_codes=("1101",),
    )
    service = _ProjectionService((snapshot,))
    calls: list[tuple[object, tuple[object, ...], object]] = []
    _install_projection(monkeypatch, {snapshot.manifest_identity_sha256: projection}, calls)
    view = DailyMarketResearchView(service)
    accepted: list[object] = []
    view.snapshotAccepted.connect(accepted.append)

    view._accept_snapshot(snapshot, sync_cutoff=True)

    assert len(accepted) == 1 and accepted[0] is snapshot
    assert calls[0][0] is snapshot
    assert calls[0][2] == str(service.snapshot_root)
    assert calls[0][1][0].condition_keys == _METHOD_KEYS
    assert calls[0][1][0].combine_mode == "AND"
    assert "具名研究 cohort；非全市場／非正式推薦" in view.cohort_identity_label.text()
    assert "2026-10-05" in view.cohort_identity_label.text()
    assert "configured-main-daily-prices" in view.cohort_identity_label.toolTip()
    assert f"method_contracts_sha256 {'e' * 64}" in view.cohort_identity_label.toolTip()
    assert "已發布列 2/3" in view.cohort_identity_label.text()
    assert "缺少已發布列：1101" in view.cohort_identity_label.text()
    assert "分母 3" in view.cohort_summary_label.text()
    assert "daily_market.close_above_ma20" in view.cohort_summary_label.toolTip()
    assert "window=20" in view.cohort_summary_label.toolTip()
    assert "daily_market.close_above_ma60" in view.cohort_summary_label.toolTip()
    assert "window=60" in view.cohort_summary_label.toolTip()
    assert "原排名未提供；指標排序非投資分數。" in view.cohort_summary_label.text()
    assert view.results_table.rowCount() == 2
    assert "1101" not in tuple(
        view.results_table.item(row, 0).text()
        for row in range(view.results_table.rowCount())
    )
    assert view.results_table.item(0, 6).text() == "100.000"
    assert view.results_table.item(0, 7).text() == "90"
    assert view.sort_key_combo.isEnabled()
    assert service.produce_calls == []
    view.close()


def test_sort_controls_use_exact_values_keep_unknown_last_and_preserve_open_identity(monkeypatch) -> None:
    _app()
    snapshot = _snapshot("b", codes=("1477", "2382", "9999"))
    members = (
        _member("1477", close="100.000", ma20="90", ma60="95"),
        _member("2382", close="9.99", ma20="10.01", ma60="8.5"),
        _member("9999", close=None, ma20="12", ma60="13"),
    )
    projection = _projection(
        snapshot, members=members, published_codes=("1477", "2382", "9999")
    )
    service = _ProjectionService((snapshot,))
    calls: list[tuple[object, tuple[object, ...], object]] = []
    _install_projection(monkeypatch, {snapshot.manifest_identity_sha256: projection}, calls)
    view = DailyMarketResearchView(service)
    emitted: list[ResearchStockContextDTO] = []
    view.stockResearchRequested.connect(emitted.append)
    view._accept_snapshot(snapshot, sync_cutoff=True)

    _select_data(view.sort_key_combo, "close")
    _select_data(view.sort_direction_combo, "asc")
    assert tuple(view.results_table.item(row, 0).text() for row in range(3)) == (
        "2382",
        "1477",
        "9999",
    )
    assert view.results_table.item(2, 6).text() == "未知"

    _select_data(view.sort_direction_combo, "desc")
    assert tuple(view.results_table.item(row, 0).text() for row in range(3)) == (
        "1477",
        "2382",
        "9999",
    )
    identities = view.visible_research_row_identities()
    assert tuple(item[0] for item in identities) == ("1477", "2382", "9999")
    assert {item[1] for item in identities} == {snapshot.manifest_identity_sha256}
    assert {item[2] for item in identities} == {snapshot.manifest_sha256}

    _select_data(view.filter_state_combo, "unknown")
    assert tuple(view.visible_research_row_identities()[i][0] for i in range(len(view.visible_research_row_identities()))) == ("9999",)
    assert "分母 3" in view.cohort_summary_label.text()
    _select_data(view.filter_state_combo, "all")
    view.results_table.selectRow(0)
    assert view.open_selected_stock()
    assert len(emitted) == 1
    assert emitted[0].stock_code == "1477"
    assert emitted[0].source_snapshot_id == snapshot.manifest_identity_sha256
    assert emitted[0].source_snapshot_hash == snapshot.manifest_sha256
    assert service.produce_calls == []
    view.close()


def test_reload_replaces_snapshot_version_and_failed_reload_clears_unknown_identity(monkeypatch) -> None:
    _app()
    first = _snapshot("b", codes=("1477", "2382"))
    second = _snapshot("c", codes=("1477", "2382"))
    first_projection = _projection(
        first,
        members=(
            _member("1477", close="100", ma20="90", ma60="95"),
            _member("2382", close="10", ma20="11", ma60="8"),
        ),
        published_codes=("1477", "2382"),
    )
    second_projection = _projection(
        second,
        members=(
            _member("1477", close="150", ma20="140", ma60="145"),
            _member("2382", close="25", ma20="26", ma60="20"),
        ),
        published_codes=("1477", "2382"),
    )
    service = _ProjectionService((first, second))
    calls: list[tuple[object, tuple[object, ...], object]] = []
    _install_projection(
        monkeypatch,
        {
            first.manifest_identity_sha256: first_projection,
            second.manifest_identity_sha256: second_projection,
        },
        calls,
    )
    view = DailyMarketResearchView(service)
    accepted: list[object] = []
    cleared: list[bool] = []
    view.snapshotAccepted.connect(accepted.append)
    view.snapshotCleared.connect(lambda: cleared.append(True))

    view._accept_snapshot(first, sync_cutoff=True)
    service.current = second
    view.reload_published_snapshot()
    _wait(view)

    assert len(accepted) == 2 and accepted[0] is first and accepted[1] is second
    assert view._snapshot is second
    assert view._manifest_sha256 == second.manifest_sha256
    assert f"source hash {second.manifest_sha256}" in view.cohort_identity_label.toolTip()
    assert first.manifest_sha256 not in view.cohort_identity_label.toolTip()
    assert view._cohort_members_by_code["1477"].close == Decimal("150")
    assert view.results_table.item(0, 6).text() == "150"
    assert cleared == []

    service.source_error = True
    view.reload_published_snapshot()
    _wait(view)
    assert cleared == [True]
    assert view._snapshot is None
    assert view.results_table.rowCount() == 0
    assert second.manifest_sha256 not in view.cohort_identity_label.toolTip()
    assert not view.sort_key_combo.isEnabled()
    view.close()


def test_rejecting_snapshot_with_unknown_identity_clears_old_cohort(monkeypatch) -> None:
    _app()
    snapshot = _snapshot("b", codes=("1477", "2382"))
    projection = _projection(
        snapshot,
        members=(
            _member("1477", close="100", ma20="90", ma60="95"),
            _member("2382", close="10", ma20="11", ma60="8"),
        ),
        published_codes=("1477", "2382"),
    )
    service = _ProjectionService((snapshot,))
    _install_projection(
        monkeypatch,
        {snapshot.manifest_identity_sha256: projection},
        [],
    )
    view = DailyMarketResearchView(service)
    cleared: list[bool] = []
    view.snapshotCleared.connect(lambda: cleared.append(True))
    view._accept_snapshot(snapshot, sync_cutoff=True)
    assert view.results_table.rowCount() == 2

    invalid_identity = VerifiedDailyMarketSnapshot(
        cohort_id=snapshot.cohort_id,
        decision_date=snapshot.decision_date,
        manifest_sha256=snapshot.manifest_sha256,
        manifest_identity_sha256="unknown",
        completeness=snapshot.completeness,
        manifest=snapshot.manifest,
        stock_snapshots=snapshot.stock_snapshots,
    )
    view._accept_snapshot(invalid_identity, sync_cutoff=False)

    assert cleared == [True]
    assert view._snapshot is None
    assert view.results_table.rowCount() == 0
    assert "原排名" not in view.cohort_identity_label.text()
    view.close()
