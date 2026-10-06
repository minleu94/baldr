from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app_module.industry_strength_service import IndustryStrengthData, IndustryStrengthService
from app_module.security_lifecycle_caller import (
    LegacyParentReference,
    SecurityLifecycleCallerError,
    SecurityLifecycleIndustryCaller,
)
from data_module.formal_pit_sector_publisher import publish_daily_pit_taxonomy_sidecar
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.pit_sector_membership_reader import PITSectorMembershipReader
from data_module.pit_taxonomy_definition_adapter import parse_official_classification_definition
from data_module.pit_taxonomy_source_producer import build_daily_pit_taxonomy_bundle
from data_module.prospective_formal_clock import build_clock_manifest, canonical_json
from data_module.security_lifecycle_contract import (
    ScoreEligibility,
    SuccessorSessionEvidence,
    parse_mops_security_lifecycle,
    write_security_lifecycle_contract,
)

from tests.pit_test_support import (
    _file_hash,
    _sha256_json,
    build_pit_fixture,
    load_json,
    write_json,
)
from tests.test_security_lifecycle_contract import (
    CAPTURED_AT,
    CONVERSION_NAME,
    FIXTURE_ROOT,
    LISTING_NAME,
    LIST_NAME,
    _build_refs,
    _copy_fixture_root,
    _load_payload,
)


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_AT = datetime(2026, 9, 16, 8, 30, tzinfo=TAIPEI)
PREOPEN_AT = datetime(2026, 9, 16, 7, 55, tzinfo=TAIPEI)
POSTCUTOFF_AT = datetime(2026, 9, 16, 9, 0, tzinfo=TAIPEI)
RESEARCH_DATE = date(2026, 9, 16)
COHORT_SYMBOLS = ("3718", "9103")


class _IndustryProvider:
    def __init__(self, data: IndustryStrengthData, latest: date) -> None:
        self.data = data
        self.latest = latest

    def latest_available_date(self) -> date:
        return self.latest

    def fetch(
        self,
        _as_of_date: date,
        *,
        session_limit: int = 25,
    ) -> IndustryStrengthData:
        del session_limit
        return self.data


def _http(url: str, captured_at: str, content_type: str) -> dict[str, object]:
    return {
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "content_type": content_type,
        "captured_at": captured_at,
    }


def _cohort_company_raw(publication_date: str = "1150903") -> bytes:
    return canonical_json(
        [
            {
                "出表日期": publication_date,
                "公司代號": "3718",
                "產業別": "24",
                "公司名稱": "中光電投控",
            },
            {
                "出表日期": publication_date,
                "公司代號": "9103",
                "產業別": "24",
                "公司名稱": "研究範圍存託憑證",
            },
        ]
    ).encode("utf-8")


def _cohort_security_raw() -> bytes:
    return (
        """
        <html><body><table>
          <tr><th>ISIN Code</th><th>Security Code</th><th>Security Name</th>
              <th>Market</th><th>Type of security</th><th>Industrial Group</th>
              <th>CFICode</th><th>Remarks</th></tr>
          <tr><td colspan="8">Stocks</td></tr>
          <tr><td>TW0003718001</td><td>3718</td><td>中光電投控</td><td>TWSE</td>
              <td></td><td>Optoelectronics</td><td>ESVUFR</td><td></td></tr>
          <tr><td>TW0009103001</td><td>9103</td><td>研究範圍存託憑證</td><td>TWSE</td>
              <td>TDR</td><td>Optoelectronics</td><td>ESVUFR</td><td></td></tr>
        </table></body></html>
        """
        .encode("utf-8")
    )


def _prepare_cohort_fixture(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    fixture = build_pit_fixture(
        tmp_path / "cohort-input",
        symbols=COHORT_SYMBOLS,
        # The legacy fixture builder's own prospective capture is anchored at
        # 2026-08-25; overwrite its raw path below for the 2026-09-16 daily
        # bundle.  The initial sidecar is intentionally not consumed here.
        raw_payloads={"twse": _cohort_company_raw("1150820")},
    )
    fixture.raw_path.write_bytes(_cohort_company_raw())
    symbols = list(COHORT_SYMBOLS)
    scores = [0, 0]
    identity = dict(load_json(fixture.universe_identity_path))
    universe_hash = _sha256_json(
        {
            "schema_version": "manual-rule-only-universe.v1",
            "symbols": symbols,
            "scores_bp": scores,
        }
    )
    identity.update(
        {
            "universe_hash": universe_hash,
            "universe_hash_symbols": symbols,
            "scores_bp": scores,
            "symbols": symbols,
            "candidate_count": len(symbols),
            "source_id": "daily_prices",
        }
    )
    write_json(fixture.universe_identity_path, identity)
    write_json(fixture.universe_symbols_path, symbols)

    clock = dict(load_json(fixture.clock_path))
    clock.pop("manifest_hash", None)
    clock["clock_id"] = "clock:research:20260916:lifecycle-cohort"
    clock["owner_decision_id"] = "owner-direction:lifecycle-research:20260915:v1"
    clock["owner_decision_timestamp"] = "2026-09-15T12:00:00+08:00"
    clock["activation_trading_day"] = RESEARCH_DATE.isoformat()
    clock["candidate_training_cutoff"] = "2026-09-14T08:30:00+08:00"
    calendar_evidence = dict(clock["activation_calendar_evidence"])
    calendar_evidence["date"] = RESEARCH_DATE.isoformat()
    calendar_evidence["reason_code"] = "twse_holiday_schedule_explicit_open"
    clock["activation_calendar_evidence"] = calendar_evidence
    clock["universe_hash"] = universe_hash
    clock = build_clock_manifest(clock)
    write_json(fixture.clock_path, clock)
    return fixture.artifact_path, identity, clock


def _build_published_taxonomy(
    tmp_path: Path,
) -> tuple[Path, dict[str, object], Path]:
    _, identity, clock = _prepare_cohort_fixture(tmp_path)
    company_raw = _cohort_company_raw()
    security_raw = _cohort_security_raw()
    definition_payload = canonical_json({"mapping": {"24": "光電業"}}).encode("utf-8")
    definition = parse_official_classification_definition(
        definition_payload,
        market_scope="twse_listed",
        classification_version="tw-industry-explicit-map.v1",
        source_id="official:twse:industry-definition",
        source_version="2026-09-16",
        effective_from=RESEARCH_DATE,
    )
    bundle = build_daily_pit_taxonomy_bundle(
        bundle_root=tmp_path / "taxonomy-bundle",
        capture_date=RESEARCH_DATE,
        decision_at=DECISION_AT,
        now=PREOPEN_AT,
        expected_symbols=COHORT_SYMBOLS,
        universe_hash=str(identity["universe_hash"]),
        universe_hash_symbols=COHORT_SYMBOLS,
        scores_bp=(0, 0),
        rank_order=COHORT_SYMBOLS,
        clock_id=str(clock["clock_id"]),
        clock_manifest_hash=str(clock["manifest_hash"]),
        clock_payload=clock,
        universe_identity_payload=identity,
        company_raw_payloads={"twse": company_raw},
        company_http={
            "twse": _http(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                "2026-09-16T06:00:00+08:00",
                "application/json",
            )
        },
        classification_payloads={"twse_listed": definition_payload},
        classification_definitions={"twse_listed": definition},
        classification_http={
            "twse_listed": _http(
                "https://example.invalid/official-industry-definition",
                "2026-09-16T06:10:00+08:00",
                "application/json",
            )
        },
        security_raw_payloads={"twse_listed": security_raw},
        security_http={
            "twse_listed": _http(
                "https://isin.twse.com.tw/isin/e_single_main.jsp",
                "2026-09-16T06:20:00+08:00",
                "text/html",
            )
        },
        license_scope={
            "status": "owner_accepted_research_scope",
            "formal_acceptance_granted": True,
            "acceptance_id": "qa-lifecycle-cohort-20260916",
            "accepted_by": "qa-owner",
            "decision_at": DECISION_AT.isoformat(),
            "allowed_use_cases": ["formal_pit_sector_membership"],
            "redistribution_allowed": False,
        },
    )
    published = publish_daily_pit_taxonomy_sidecar(
        bundle_manifest_path=bundle.bundle_manifest_path,
        publication_root=tmp_path / "taxonomy-publication",
        decision_at=DECISION_AT,
        now=POSTCUTOFF_AT,
    )
    assert published["status"] == "formal_source_publication"
    assert published["industry_filter_usable"] is True
    sidecar_path = Path(str(published["sidecar_path"]))
    return sidecar_path, identity, Path(str(published["taxonomy_identity_path"]))


def _industry_data() -> IndustryStrengthData:
    dates = [date(2026, 8, 17) + timedelta(days=index) for index in range(31)]
    industry_rows = [
        {
            "日期": current.isoformat(),
            "指數名稱": "光電類指數",
            "收盤指數": str(1000 + index * 2),
        }
        for index, current in enumerate(dates)
    ]
    market_rows = [
        {
            "日期": current.isoformat(),
            "指數名稱": "TAIEX",
            "收盤指數": str(1000 + index),
        }
        for index, current in enumerate(dates)
    ]
    price_rows = [
        {
            "日期": current.isoformat(),
            "證券代號": symbol,
            "證券名稱": symbol,
            "收盤價": str(base + index),
        }
        for index, current in enumerate(dates)
        for symbol, base in (("3718", 100), ("9103", 200))
    ]
    return IndustryStrengthData(
        industry_indices=pd.DataFrame(industry_rows),
        market_indices=pd.DataFrame(market_rows),
        daily_prices=pd.DataFrame(price_rows),
        companies=pd.DataFrame(),
    )


def _write_calendar_evidence(db_path: Path, *, missing: date | None = None) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            'CREATE TABLE market_indices ("日期" TEXT, "指數名稱" TEXT, "收盤指數" TEXT)'
        )
        current = date(2026, 9, 3)
        end = date(2026, 9, 9)
        while current <= end:
            if current.weekday() < 5 and current != missing:
                connection.execute(
                    'INSERT INTO market_indices VALUES (?, ?, ?)',
                    (current.strftime("%Y%m%d"), "TAIEX", "1000"),
                )
            current += timedelta(days=1)
        connection.commit()


def _successor_sessions() -> tuple[SuccessorSessionEvidence, ...]:
    dates = (
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 7),
        date(2026, 9, 8),
        date(2026, 9, 9),
    )
    result = []
    for current in dates:
        raw = canonical_json(
            {
                "source": "fixture:new-cohort-price",
                "symbol": "3718",
                "session_date": current.isoformat(),
                "close_minor_units": 10000 + len(result),
            }
        ).encode("utf-8")
        result.append(
            SuccessorSessionEvidence(
                session_date=current,
                symbol="3718",
                official_trading_day_verified=True,
                price_source_id="fixture:new-cohort-price",
                price_lineage_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(result)


def _build_lifecycle_contract(tmp_path: Path) -> Path:
    root = _copy_fixture_root(tmp_path / "mops-raw")
    event = parse_mops_security_lifecycle(
        _load_payload(root, LIST_NAME),
        _load_payload(root, CONVERSION_NAME),
        _load_payload(root, LISTING_NAME),
        raw_refs=_build_refs(root, CAPTURED_AT),
        captured_at=CAPTURED_AT,
        declared_predecessor_symbol="5371",
        declared_successor_symbol="3718",
    )
    contract_path = tmp_path / "lifecycle-contract.json"
    write_security_lifecycle_contract(contract_path, event)
    return contract_path


def _build_parent_reference(tmp_path: Path) -> LegacyParentReference:
    parent_path = tmp_path / "legacy-parent" / "parent-identity.json"
    parent_path.parent.mkdir(parents=True, exist_ok=True)
    parent_path.write_bytes(b"legacy parent custody reference; no score or price payload")
    return LegacyParentReference(
        parent_id="legacy-parent:5371:20260821",
        predecessor_symbol="5371",
        parent_path=parent_path,
        parent_file_hash=_file_hash(parent_path),
        parent_universe_hash=_sha256_json({"legacy_parent_symbol": "5371"}),
    )


def test_lifecycle_caller_wires_published_new_cohort_to_pit_and_industry(
    tmp_path: Path,
) -> None:
    sidecar_path, identity, taxonomy_identity_path = _build_published_taxonomy(tmp_path)
    contract_path = _build_lifecycle_contract(tmp_path)
    calendar_db = tmp_path / "calendar.sqlite"
    _write_calendar_evidence(calendar_db)
    service = IndustryStrengthService(
        provider=_IndustryProvider(_industry_data(), RESEARCH_DATE),
        pit_membership_reader=PITSectorMembershipReader([sidecar_path]),
        pit_market_scope="twse_listed",
    )
    caller = SecurityLifecycleIndustryCaller(
        calendar=OfficialTradingCalendar(db_path=calendar_db),
        industry_service=service,
        required_warmup_sessions=5,
    )

    result = caller.evaluate(
        contract_path=contract_path,
        decision_at=DECISION_AT,
        as_of_date=RESEARCH_DATE,
        new_cohort_symbols=COHORT_SYMBOLS,
        legacy_parent_reference=_build_parent_reference(tmp_path),
        successor_sessions=_successor_sessions(),
        allow_online_probe=False,
    )

    assert result.accepted is True
    assert result.event.predecessor.symbol == "5371"
    assert result.event.successor.symbol == "3718"
    assert result.state.history_warmup_complete is True
    assert result.state.score_eligibility is ScoreEligibility.HISTORY_WARMUP_COMPLETE_REQUIRES_SCORER
    assert result.full_cohort_symbols == COHORT_SYMBOLS
    assert result.full_cohort_row_count == 2
    assert result.eligible_symbols == ("3718",)
    assert result.excluded_symbols == ("9103",)
    assert result.excluded_row_count == 1
    assert result.unknown_symbols == ()
    assert result.membership.industry_filter_usable is True
    assert {
        row.symbol: row.security_type for row in result.membership.rows
    } == {"3718": "common_equity", "9103": "tdr"}
    assert result.membership.lineage["taxonomy_identity_path"] == str(taxonomy_identity_path)
    assert result.industry_summary.coverage["mapping_mode"] == "pit_accepted_prospective"
    assert result.industry_summary.coverage["coverage_denominator"] == "accepted_pit_membership_rows"
    assert result.industry_summary.coverage["pit_full_symbol_count"] == 2
    assert result.industry_summary.coverage["pit_eligible_symbol_count"] == 1
    assert result.industry_summary.coverage["pit_excluded_symbol_count"] == 1
    optoelectronics = next(
        row for row in result.industry_summary.rows if row.industry_name == "光電業"
    )
    assert optoelectronics.constituent_count == 1
    assert optoelectronics.representative_stocks[0].stock_code == "3718"
    assert result.legacy_parent.predecessor_symbol == "5371"
    assert result.event.historical_price_score_carry_forward_allowed is False
    assert result.state.historical_price_score_carry_forward_allowed is False
    assert result.to_payload()["quality"] == {
        "research_only": True,
        "formal_credit_allowed": False,
        "natural_credit_allowed": False,
        "historical_price_score_carry_forward_allowed": False,
    }
    assert result.to_payload()["warmup"]["observed_sessions"] == 5

    # The new cohort's source identity is retained for the caller, while the
    # lifecycle result contains no copied historical price/score vector.
    assert identity["symbols"] == list(COHORT_SYMBOLS)
    assert "scores_bp" not in result.to_payload()["event"]


def test_lifecycle_caller_fails_closed_when_calendar_has_an_unresolved_session(
    tmp_path: Path,
) -> None:
    sidecar_path, _, _ = _build_published_taxonomy(tmp_path)
    contract_path = _build_lifecycle_contract(tmp_path)
    calendar_db = tmp_path / "calendar-missing.sqlite"
    _write_calendar_evidence(calendar_db, missing=date(2026, 9, 8))
    service = IndustryStrengthService(
        provider=_IndustryProvider(_industry_data(), RESEARCH_DATE),
        pit_membership_reader=PITSectorMembershipReader([sidecar_path]),
        pit_market_scope="twse_listed",
    )
    caller = SecurityLifecycleIndustryCaller(
        calendar=OfficialTradingCalendar(db_path=calendar_db),
        industry_service=service,
        required_warmup_sessions=5,
    )

    with pytest.raises(SecurityLifecycleCallerError, match="official successor calendar"):
        caller.evaluate(
            contract_path=contract_path,
            decision_at=DECISION_AT,
            as_of_date=RESEARCH_DATE,
            new_cohort_symbols=COHORT_SYMBOLS,
            legacy_parent_reference=_build_parent_reference(tmp_path),
            successor_sessions=_successor_sessions(),
            allow_online_probe=False,
        )
