from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.security_lifecycle_contract import (
    MOPS_DETAIL_ENDPOINT,
    MOPS_LIST_ENDPOINT,
    ScoreEligibility,
    SecurityLifecycleContractError,
    SecurityLifecyclePhase,
    SecurityLifecycleScope,
    SecurityMarketStatus,
    RawResponseRef,
    ShareRatio,
    SuccessorSessionEvidence,
    parse_mops_security_lifecycle,
    read_security_lifecycle_contract,
    security_lifecycle_state_as_of,
    write_security_lifecycle_contract,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "security_lifecycle"
LIST_NAME = "mops_api_t05st01_5371_115.json"
CONVERSION_NAME = "mops_api_t05st01_detail_5371_1150729_1.json"
LISTING_NAME = "mops_api_t05st01_detail_5371_1150729_2.json"
CAPTURED_AT = datetime(2026, 9, 15, 18, 7, tzinfo=timezone.utc)


def _load_payload(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write_payload(root: Path, name: str, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _build_refs(root: Path, captured_at: datetime = CAPTURED_AT) -> tuple[RawResponseRef, ...]:
    list_payload = _load_payload(root, LIST_NAME)
    conversion_payload = _load_payload(root, CONVERSION_NAME)
    listing_payload = _load_payload(root, LISTING_NAME)
    company_id = str(conversion_payload["result"]["companyId"])
    conversion_row = conversion_payload["result"]["data"][0]
    listing_row = listing_payload["result"]["data"][0]
    list_request = {
        "companyId": company_id,
        "year": str(conversion_row[1])[:3],
        "month": "all",
        "firstDay": "",
        "lastDay": "",
    }
    return (
        RawResponseRef.from_file(
            kind="mops_list",
            path=root / LIST_NAME,
            source_url=MOPS_LIST_ENDPOINT,
            request_payload=list_request,
            captured_at=captured_at,
        ),
        RawResponseRef.from_file(
            kind="mops_conversion_detail",
            path=root / CONVERSION_NAME,
            source_url=MOPS_DETAIL_ENDPOINT,
            request_payload={
                "marketKind": "pub",
                "enterDate": str(conversion_row[1]).replace("/", ""),
                "serialNumber": str(conversion_row[0]),
                "companyId": company_id,
            },
            captured_at=captured_at,
        ),
        RawResponseRef.from_file(
            kind="mops_listing_detail",
            path=root / LISTING_NAME,
            source_url=MOPS_DETAIL_ENDPOINT,
            request_payload={
                "marketKind": "pub",
                "enterDate": str(listing_row[1]).replace("/", ""),
                "serialNumber": str(listing_row[0]),
                "companyId": company_id,
            },
            captured_at=captured_at,
        ),
    )


def _parse_from(root: Path, *, captured_at: datetime = CAPTURED_AT, **kwargs: Any):
    return parse_mops_security_lifecycle(
        _load_payload(root, LIST_NAME),
        _load_payload(root, CONVERSION_NAME),
        _load_payload(root, LISTING_NAME),
        raw_refs=_build_refs(root, captured_at),
        captured_at=captured_at,
        **kwargs,
    )


def _copy_fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "mops_raw"
    for name in (LIST_NAME, CONVERSION_NAME, LISTING_NAME):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes((FIXTURE_ROOT / name).read_bytes())
    return root


def _session(session_date: date, *, symbol: str = "3718") -> SuccessorSessionEvidence:
    return SuccessorSessionEvidence(
        session_date=session_date,
        symbol=symbol,
        official_trading_day_verified=True,
        price_source_id="tpex.daily_prices",
        price_lineage_sha256="sha256:" + "a" * 64,
    )


def _replace_all_strings(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_all_strings(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_all_strings(item, old, new) for key, item in value.items()}
    return value


def test_mops_raw_positive_derives_identity_ratio_dates_and_lineage() -> None:
    event = _parse_from(FIXTURE_ROOT)

    assert event.original.symbol == "5371"
    assert event.predecessor.symbol == "5371"
    assert event.successor.symbol == "3718"
    assert event.ratio == ShareRatio(1, 1)
    assert event.converted_share_count == 390_981_110
    assert event.last_trade_date == date(2026, 8, 21)
    assert event.halt_from == date(2026, 8, 24)
    assert event.conversion_base_date == date(2026, 9, 3)
    assert event.termination_date == date(2026, 9, 3)
    assert event.successor_listed_date == date(2026, 9, 3)
    assert event.source_available_at == datetime(2026, 9, 15, 18, 6, 46, tzinfo=timezone.utc)
    assert event.available_at == CAPTURED_AT
    assert len(event.raw_response_hashes) == 3
    assert event.research_only is True
    assert event.formal_credit_allowed is False
    assert event.historical_price_score_carry_forward_allowed is False


def test_state_after_listing_separates_market_and_score_readiness() -> None:
    event = _parse_from(FIXTURE_ROOT)
    state = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        observed_sessions=(
            _session(date(2026, 9, 3)),
            _session(date(2026, 9, 4)),
            _session(date(2026, 9, 7)),
            _session(date(2026, 9, 8)),
            _session(date(2026, 9, 9)),
        ),
        required_warmup_sessions=5,
    )

    assert state.visible is True
    assert state.phase is SecurityLifecyclePhase.SUCCESSOR_ACTIVE_WARMUP
    assert state.market_status is SecurityMarketStatus.PREDECESSOR_TERMINATED_SUCCESSOR_TRADABLE
    assert state.current_symbol == "3718"
    assert state.market_tradable is True
    assert state.history_warmup_complete is True
    assert state.score_eligibility is ScoreEligibility.HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER
    assert state.historical_price_score_carry_forward_allowed is False


def test_prelisting_sessions_do_not_count_for_successor_warmup() -> None:
    event = _parse_from(FIXTURE_ROOT)
    state = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        observed_sessions=(
            _session(date(2026, 8, 31)),
            _session(date(2026, 9, 3)),
            _session(date(2026, 9, 4)),
        ),
        required_warmup_sessions=3,
    )

    assert state.history_warmup_complete is False
    assert state.score_eligibility is ScoreEligibility.WARMUP_REQUIRED
    assert "session_outside_successor_window" in state.reason_codes


def test_bare_date_window_does_not_claim_verified_warmup() -> None:
    event = _parse_from(FIXTURE_ROOT)
    state = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        observed_sessions=(date(2026, 9, 3), date(2026, 9, 4)),
        required_warmup_sessions=1,
    )

    assert state.history_warmup_complete is None
    assert state.score_eligibility is ScoreEligibility.WARMUP_REQUIRED
    assert "date_window_not_caller_verified" in state.reason_codes


def test_duplicate_or_future_successor_session_evidence_is_invalid() -> None:
    event = _parse_from(FIXTURE_ROOT)
    duplicate = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        observed_sessions=(_session(date(2026, 9, 3)), _session(date(2026, 9, 3))),
        required_warmup_sessions=2,
    )
    future = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
        observed_sessions=(_session(date(2026, 9, 16)),),
        required_warmup_sessions=1,
    )

    assert duplicate.history_warmup_complete is False
    assert "duplicate_session_date" in duplicate.reason_codes
    assert future.history_warmup_complete is False
    assert "session_outside_successor_window" in future.reason_codes


def test_decision_between_source_response_and_client_capture_is_not_visible() -> None:
    event = _parse_from(FIXTURE_ROOT)
    state = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 15, 18, 6, 50, tzinfo=timezone.utc),
    )

    assert state.visible is False
    assert state.phase is SecurityLifecyclePhase.UNKNOWN
    assert state.score_eligibility is ScoreEligibility.NOT_VISIBLE


def test_future_effective_date_is_visible_but_not_effective(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    for name in (CONVERSION_NAME, LISTING_NAME):
        payload = _load_payload(root, name)
        _write_payload(root, name, _replace_all_strings(payload, "115年9月3日", "115年9月20日"))
    event = _parse_from(root)
    state = security_lifecycle_state_as_of(
        event,
        datetime(2026, 9, 15, 23, 0, tzinfo=timezone.utc),
    )

    assert event.successor_listed_date == date(2026, 9, 20)
    assert state.visible is True
    assert state.phase is SecurityLifecyclePhase.NOT_EFFECTIVE
    assert state.current_symbol == "5371"


def test_future_announcement_cannot_be_captured_before_announcement(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    for name in (LIST_NAME, CONVERSION_NAME, LISTING_NAME):
        payload = _load_payload(root, name)
        _write_payload(root, name, _replace_all_strings(payload, "115/07/29", "115/09/17"))

    with pytest.raises(SecurityLifecycleContractError, match="future_announcement_at_capture"):
        _parse_from(root)


def test_capture_before_source_available_is_rejected() -> None:
    with pytest.raises(SecurityLifecycleContractError, match="capture_before_source_available"):
        _parse_from(
            FIXTURE_ROOT,
            captured_at=datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc),
        )


def test_ratio_tamper_is_rejected_against_explicit_declaration(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    payload = _load_payload(root, CONVERSION_NAME)
    row = payload["result"]["data"][0]
    row[9] = row[9].replace("持股1股換發中光電投控股份1股", "持股1股換發中光電投控股份2股")
    _write_payload(root, CONVERSION_NAME, payload)

    with pytest.raises(SecurityLifecycleContractError, match="declared_ratio_conflict"):
        _parse_from(root, declared_ratio=(1, 1))


def test_symbol_tamper_between_conversion_and_listing_details_is_rejected(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    payload = _load_payload(root, CONVERSION_NAME)
    row = payload["result"]["data"][0]
    row[9] = row[9].replace("股票代號：3718", "股票代號：9999", 1)
    _write_payload(root, CONVERSION_NAME, payload)

    with pytest.raises(SecurityLifecycleContractError, match="successor_symbol_conflict"):
        _parse_from(root)


def test_conversion_and_listing_dates_must_agree(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    payload = _load_payload(root, LISTING_NAME)
    row = payload["result"]["data"][0]
    row[9] = row[9].replace("115年9月3日", "115年9月4日")
    _write_payload(root, LISTING_NAME, payload)

    with pytest.raises(SecurityLifecycleContractError, match="listing_termination_date_conflict"):
        _parse_from(root)


def test_declared_old_to_new_conflict_is_rejected() -> None:
    with pytest.raises(SecurityLifecycleContractError, match="declared_predecessor_symbol_conflict"):
        _parse_from(FIXTURE_ROOT, declared_predecessor_symbol="9999")


def test_contract_write_readback_is_immutable_and_reparses_raw(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    event = _parse_from(root, source_scope=SecurityLifecycleScope.HISTORICAL_RESEARCH_REPLAY)
    contract_path = tmp_path / "contract.json"

    contract_hash = write_security_lifecycle_contract(contract_path, event)
    loaded = read_security_lifecycle_contract(contract_path)

    assert contract_hash.startswith("sha256:")
    assert loaded.to_payload() == event.to_payload()
    assert loaded.source_scope is SecurityLifecycleScope.HISTORICAL_RESEARCH_REPLAY
    assert loaded.formal_credit_allowed is False

    tampered = _load_payload(root, LISTING_NAME)
    tampered["result"]["data"][0][9] = tampered["result"]["data"][0][9].replace(
        "3718", "3719", 1
    )
    _write_payload(root, LISTING_NAME, tampered)
    with pytest.raises(SecurityLifecycleContractError, match="raw_response_hash_mismatch"):
        read_security_lifecycle_contract(contract_path)


def test_required_warmup_sessions_must_be_integer() -> None:
    event = _parse_from(FIXTURE_ROOT)
    with pytest.raises(SecurityLifecycleContractError, match="required_warmup_sessions_invalid"):
        security_lifecycle_state_as_of(
            event,
            datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
            required_warmup_sessions=20.0,  # type: ignore[arg-type]
        )


def test_synthetic_projection_exposes_suspended_predecessor_without_score_credit() -> None:
    event = _parse_from(FIXTURE_ROOT)
    suspended = replace(
        event,
        last_trade_date=date(2026, 9, 9),
        halt_from=date(2026, 9, 10),
        conversion_base_date=date(2026, 9, 20),
        termination_date=date(2026, 9, 20),
        successor_listed_date=date(2026, 9, 20),
    )
    state = security_lifecycle_state_as_of(
        suspended,
        datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc),
    )

    assert state.phase is SecurityLifecyclePhase.NOT_EFFECTIVE
    assert state.market_status is SecurityMarketStatus.TRADING_SUSPENDED
    assert state.market_tradable is False
    assert state.score_eligibility is ScoreEligibility.MARKET_BLOCKED
