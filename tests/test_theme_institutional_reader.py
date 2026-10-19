from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

import app_module.institutional_source_use as source_use_module
import app_module.theme_institutional_reader as reader_module
from app_module.institutional_daily_snapshot import (
    InstitutionalDailyRow,
    InstitutionalDailySnapshotBatchRead,
    InstitutionalDailySnapshotPin,
)
from app_module.institutional_source_use import (
    InstitutionalSourceUsePin,
    InstitutionalSourceUseRead,
    TPEX_INSTITUTIONAL_USE_SCOPE,
)
from app_module.theme_institutional_reader import TPExThemeFlowReader
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.tpex_institutional_openapi import TPEX_OPENAPI_VERSION


_TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
_DATA_DATE = date(2026, 10, 15)
_KNOWN_AT = datetime(2026, 10, 17, 9, 0, tzinfo=_TAIPEI)
_AVAILABLE = datetime(2026, 10, 16, 17, 0, tzinfo=_TAIPEI)
_ACCEPTED_AT = datetime(2026, 10, 16, 18, 0, tzinfo=_TAIPEI)


def _daily_pin() -> InstitutionalDailySnapshotPin:
    return InstitutionalDailySnapshotPin(
        directory=Path("C:/fixture/tpex/daily_snapshot"),
        manifest_sha256="a" * 64,
        receipt_sha256="b" * 64,
    )


def _source_use_pin(suffix: str = "c") -> InstitutionalSourceUsePin:
    return InstitutionalSourceUsePin(
        path=Path("C:/fixture/tpex/source-use/source_use.json"),
        sha256=suffix * 64,
    )


def _source_use(
    pin: InstitutionalSourceUsePin | None = None,
    *,
    accepted_at: datetime = _ACCEPTED_AT,
) -> InstitutionalSourceUseRead:
    evidence = source_use_module._evidence_identity()
    acceptance = DailySourceUseAcceptance(
        scope=TPEX_INSTITUTIONAL_USE_SCOPE,
        acceptance_id="machine:tpex-institutional:" + evidence,
        accepted_at=accepted_at,
        official_source_endpoint=source_use_module.TPEX_OPENAPI_URL,
        document_chain=tuple(
            item["url"] for item in source_use_module._DOCUMENT_POLICY
        ),
        acceptance_evidence_ref="sha256:" + evidence,
        authorization_scope="diagnostics",
    )
    return InstitutionalSourceUseRead(
        pin=pin or _source_use_pin(),
        acceptance=acceptance,
        attribution=source_use_module._ATTRIBUTION,
    )


def _reader(
    *,
    eligible_stock_ids: tuple[str, ...] = ("2330", "2317", "6488"),
) -> TPExThemeFlowReader:
    return TPExThemeFlowReader(
        _daily_pin(),
        source_use_pin=_source_use_pin(),
        eligible_stock_ids=eligible_stock_ids,
    )


def _row(
    stock_code: str,
    *,
    decision_date: date = _DATA_DATE,
    foreign_net: int = 10,
    trust_net: int = -3,
    dealer_net: int = 2,
    raw_sha256: str = "d" * 64,
    source_version: str = TPEX_OPENAPI_VERSION,
) -> InstitutionalDailyRow:
    return InstitutionalDailyRow(
        stock_code=stock_code,
        decision_date=decision_date.isoformat(),
        foreign_investor_buy=max(foreign_net, 0),
        foreign_investor_sell=max(-foreign_net, 0),
        foreign_investor_net=foreign_net,
        investment_trust_buy=max(trust_net, 0),
        investment_trust_sell=max(-trust_net, 0),
        investment_trust_net=trust_net,
        dealer_buy=max(dealer_net, 0),
        dealer_sell=max(-dealer_net, 0),
        dealer_net=dealer_net,
        raw_sha256=raw_sha256,
        source_version=source_version,
        official_timestamp_original_text="2026-10-15T15:00:00+08:00",
        official_timestamp="2026-10-15T15:00:00+08:00",
    )


def _batch(
    *,
    stock_codes: tuple[str, ...],
    rows: tuple[InstitutionalDailyRow, ...],
    source_use: InstitutionalSourceUseRead | None = None,
    pin: InstitutionalDailySnapshotPin | None = None,
    **changes: object,
) -> InstitutionalDailySnapshotBatchRead:
    values: dict[str, object] = {
        "pin": pin or _daily_pin(),
        "stock_codes": stock_codes,
        "rows": rows,
        "total_records": 898,
        "first_persisted_at": datetime(2026, 10, 16, 16, 5, tzinfo=_TAIPEI),
        "successful_batch_completed_at": datetime(
            2026, 10, 16, 16, 6, tzinfo=_TAIPEI
        ),
        "available_hour": _AVAILABLE,
        "availability_basis": "successful_batch_completion_fallback",
        "candidate_only": True,
        "source_use_accepted": True,
        "historical_pit_eligible": False,
        "market": "TPEx",
        "source_use": source_use or _source_use(),
    }
    values.update(changes)
    return InstitutionalDailySnapshotBatchRead(**values)  # type: ignore[arg-type]


def test_reader_calls_one_exact_tpex_batch_and_preserves_original_integer_nets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader()
    codes = ("2330", "2317", "6488")
    rows = (
        _row(
            "2317",
            foreign_net=-7,
            trust_net=2,
            dealer_net=3,
            raw_sha256="1" * 64,
        ),
        _row(
            "2330",
            foreign_net=2**100,
            trust_net=-7,
            dealer_net=3,
            raw_sha256="2" * 64,
        ),
        _row(
            "6488",
            foreign_net=0,
            trust_net=0,
            dealer_net=0,
            raw_sha256="3" * 64,
        ),
    )
    batch = _batch(stock_codes=codes, rows=rows)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def read_batch(*args: object, **kwargs: object) -> InstitutionalDailySnapshotBatchRead:
        calls.append((args, kwargs))
        return batch

    monkeypatch.setattr(
        reader_module, "read_institutional_daily_snapshot_batch", read_batch
    )
    result = reader.read((*codes, "9999"), _DATA_DATE, _KNOWN_AT)

    assert len(calls) == 1
    assert calls[0][0] == (reader.pin,)
    assert calls[0][1] == {
        "stock_codes": codes,
        "decision_cutoff": _KNOWN_AT,
        "source_use_pin": reader.source_use_pin,
        "_expected_scope": "tpex_openapi_institutional",
    }
    assert [flow.stock_id for flow in result.flows] == list(codes)
    assert [flow.net_shares for flow in result.flows] == [
        2**100 - 4,
        -2,
        0,
    ]
    assert all(flow.net_turnover_twd is None for flow in result.flows)
    assert all(flow.available_at == _ACCEPTED_AT for flow in result.flows)
    raw_by_stock = {row.stock_code: row.raw_sha256 for row in rows}
    assert all(
        "TPEx" in flow.source_id
        and f"stock_id={flow.stock_id}" in flow.source_id
        and f"raw_sha256={raw_by_stock[flow.stock_id]}" in flow.source_id
        and f"daily_manifest_sha256={reader.pin.manifest_sha256}" in flow.source_id
        and f"daily_receipt_sha256={reader.pin.receipt_sha256}" in flow.source_id
        and f"source_use_sha256={reader.source_use_pin.sha256}" in flow.source_id
        for flow in result.flows
    )
    assert "institutional_tpex_diagnostics_only" in result.warnings
    assert "non_tpex_members_excluded" in result.warnings
    assert result.prices == ()
    assert result.previous_sessions == ()


def test_empty_tpex_intersection_returns_reason_without_reading_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader(eligible_stock_ids=())

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("空交集不可讀取法人批次")

    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        fail_if_called,
    )
    result = reader.read(("9999",), _DATA_DATE, _KNOWN_AT)

    assert result.flows == ()
    assert "no_selected_members" in result.warnings
    assert "non_tpex_members_excluded" in result.warnings
    assert "institutional_tpex_diagnostics_only" in result.warnings


def test_missing_and_other_date_rows_are_not_filled_or_borrowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader(eligible_stock_ids=("2330", "2317"))
    codes = ("2330", "2317")
    old_row = _row(
        "2330",
        decision_date=date(2026, 10, 14),
        raw_sha256="4" * 64,
    )
    batch = _batch(stock_codes=codes, rows=(old_row,))
    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        lambda *_args, **_kwargs: batch,
    )

    result = reader.read(codes, date(2026, 10, 16), _KNOWN_AT)

    assert result.flows == ()
    assert "institutional_date_mismatch" in result.warnings
    assert "institutional_selected_member_not_found" in result.warnings


@pytest.mark.parametrize(
    "bad_row",
    [
        _row("2330", raw_sha256="not-a-sha"),
        _row("2330", source_version="other-source"),
        _row("2330", foreign_net=True),
        _row("2330", trust_net=False),
        _row("2330", dealer_net=cast(int, 1.5)),
    ],
)
def test_same_date_projection_rejects_incomplete_raw_provenance_or_noninteger_net(
    monkeypatch: pytest.MonkeyPatch,
    bad_row: InstitutionalDailyRow,
) -> None:
    reader = _reader(eligible_stock_ids=("2330",))
    batch = _batch(stock_codes=("2330",), rows=(bad_row,))
    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        lambda *_args, **_kwargs: batch,
    )

    with pytest.raises(ValueError):
        reader.read(("2330",), _DATA_DATE, _KNOWN_AT)


def test_duplicate_same_stock_same_date_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _reader(eligible_stock_ids=("2330",))
    duplicate = _row("2330")
    batch = _batch(stock_codes=("2330",), rows=(duplicate, duplicate))
    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        lambda *_args, **_kwargs: batch,
    )

    with pytest.raises(ValueError, match="同一股票同日原列重複"):
        reader.read(("2330",), _DATA_DATE, _KNOWN_AT)


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_market",
        "not_candidate",
        "not_accepted",
        "historical",
        "wrong_pin",
        "wrong_codes",
        "missing_use",
        "wrong_use_pin",
        "wrong_scope",
    ),
)
def test_batch_must_retain_exact_pin_market_and_qualified_diagnostics_scope(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    reader = _reader(eligible_stock_ids=("2330",))
    row = _row("2330")
    source_use = _source_use(reader.source_use_pin)
    changes: dict[str, object] = {}
    if mutation == "wrong_market":
        changes["market"] = "TWSE"
    elif mutation == "not_candidate":
        changes["candidate_only"] = False
    elif mutation == "not_accepted":
        changes["source_use_accepted"] = False
    elif mutation == "historical":
        changes["historical_pit_eligible"] = True
    elif mutation == "wrong_pin":
        changes["pin"] = InstitutionalDailySnapshotPin(
            Path("C:/fixture/other/daily_snapshot"), "e" * 64, "f" * 64
        )
    elif mutation == "wrong_codes":
        changes["stock_codes"] = ("2317",)
    elif mutation == "missing_use":
        changes["source_use"] = None
        changes["source_use_accepted"] = False
    elif mutation == "wrong_use_pin":
        source_use = _source_use(_source_use_pin("9"))
    elif mutation == "wrong_scope":
        object.__setattr__(source_use.acceptance, "scope", None)
    batch = replace(
        _batch(stock_codes=("2330",), rows=(row,), source_use=source_use),
        **changes,
    )
    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        lambda *_args, **_kwargs: batch,
    )

    with pytest.raises((TypeError, ValueError)):
        reader.read(("2330",), _DATA_DATE, _KNOWN_AT)


@pytest.mark.parametrize(
    ("available_hour", "accepted_at"),
    [
        (datetime(2026, 10, 17, 10, 0, tzinfo=_TAIPEI), _ACCEPTED_AT),
        (_AVAILABLE, datetime(2026, 10, 17, 10, 0, tzinfo=_TAIPEI)),
        (datetime(2026, 10, 16, 17, 0), _ACCEPTED_AT),
    ],
)
def test_future_or_naive_source_clock_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    available_hour: datetime,
    accepted_at: datetime,
) -> None:
    reader = _reader(eligible_stock_ids=("2330",))
    source_use = _source_use(reader.source_use_pin, accepted_at=accepted_at)
    batch = _batch(
        stock_codes=("2330",),
        rows=(_row("2330"),),
        source_use=source_use,
        available_hour=available_hour,
    )
    monkeypatch.setattr(
        reader_module,
        "read_institutional_daily_snapshot_batch",
        lambda *_args, **_kwargs: batch,
    )

    with pytest.raises((TypeError, ValueError)):
        reader.read(("2330",), _DATA_DATE, _KNOWN_AT)


def test_input_validation_precedes_batch_io(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _reader()
    calls = 0

    def read_batch(*_args: object, **_kwargs: object) -> InstitutionalDailySnapshotBatchRead:
        nonlocal calls
        calls += 1
        raise AssertionError("無效輸入不可呼叫批次讀者")

    monkeypatch.setattr(
        reader_module, "read_institutional_daily_snapshot_batch", read_batch
    )
    with pytest.raises(ValueError):
        reader.read(("2330", "2330"), _DATA_DATE, _KNOWN_AT)
    with pytest.raises(ValueError):
        reader.read(("2330",), _DATA_DATE, datetime(2026, 10, 17, 9, 0))
    with pytest.raises(ValueError):
        reader.read(("233A",), _DATA_DATE, _KNOWN_AT)
    assert calls == 0


@pytest.mark.parametrize(
    "eligible_stock_ids",
    [
        ("233A",),
        ("2330", "2330"),
    ],
)
def test_constructor_rejects_invalid_or_duplicate_tpex_members(
    eligible_stock_ids: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        TPExThemeFlowReader(
            _daily_pin(),
            source_use_pin=_source_use_pin(),
            eligible_stock_ids=eligible_stock_ids,
        )


@pytest.mark.parametrize(
    "failure",
    [InterruptedError("原批次合作取消"), RuntimeError("原reader錯誤")],
)
def test_batch_cancellation_and_reader_errors_propagate_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    reader = _reader(eligible_stock_ids=("2330",))

    def fail(*_args: object, **_kwargs: object) -> InstitutionalDailySnapshotBatchRead:
        raise failure

    monkeypatch.setattr(
        reader_module, "read_institutional_daily_snapshot_batch", fail
    )
    with pytest.raises(type(failure)) as caught:
        reader.read(("2330",), _DATA_DATE, _KNOWN_AT)
    assert caught.value is failure
