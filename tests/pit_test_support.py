"""PIT caller acceptance fixtures built through the existing producers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from data_module.prospective_formal_clock import (
    build_clock_manifest,
    canonical_json,
    load_clock_manifest_for_capture,
    payload_hash,
)
from data_module.prospective_official_pit_source import (
    build_official_first_seen_capture,
)
from data_module.prospective_pit_sector_membership import (
    capture_prospective_pit_sector_membership,
)
from data_module.pit_sector_membership_reader import (
    PIT_TAXONOMY_IDENTITY_SCHEMA_VERSION,
    PIT_TAXONOMY_SOURCE_SCHEMA_VERSION,
)


DECISION_AT = datetime.fromisoformat("2026-08-25T08:30:00+08:00")
CAPTURE_NOW = datetime.fromisoformat("2026-08-25T08:31:00+08:00")
EFFECTIVE_FROM = date(2026, 8, 25)


@dataclass(frozen=True)
class PITFixture:
    artifact_path: Path
    bundle_root: Path
    clock_path: Path
    universe_symbols_path: Path
    universe_identity_path: Path
    taxonomy_identity_path: Path
    taxonomy_source_path: Path
    raw_path: Path
    symbols: tuple[str, ...]


def build_pit_fixture(
    tmp_path: Path,
    *,
    symbols: Sequence[str] = ("2330",),
    market: str = "twse",
    include_taxonomy: bool = True,
    taxonomy_symbols: Sequence[str] | None = None,
    taxonomy_mapping: Mapping[str, str] | None = None,
    security_types: Mapping[str, str] | None = None,
    clock_suffix: str = "fixture",
) -> PITFixture:
    expected_symbols = tuple(sorted(str(item) for item in symbols))
    if not expected_symbols:
        raise ValueError("fixture symbols must not be empty")
    score_by_symbol = {symbol: 8000 + index for index, symbol in enumerate(expected_symbols)}
    universe_hash = _sha256_json(
        {
            "schema_version": "manual-rule-only-universe.v1",
            "symbols": list(expected_symbols),
            "scores_bp": [score_by_symbol[symbol] for symbol in expected_symbols],
        }
    )

    bundle_root = tmp_path / f"bundle-{clock_suffix}"
    clock_path = bundle_root / "clock" / "manifest.json"
    metadata_root = bundle_root / "metadata"
    symbols_path = metadata_root / "universe_symbols.json"
    identity_path = metadata_root / "universe_identity.json"
    taxonomy_path = metadata_root / "taxonomy_identity.json"
    taxonomy_source_path = metadata_root / "taxonomy_source.json"
    if market not in {"twse", "tpex"}:
        raise ValueError("fixture market must be twse or tpex")
    raw_dataset = "t187ap03_L" if market == "twse" else "t187ap03_O"
    raw_path = bundle_root / "raw" / f"{raw_dataset}.raw.json"
    artifact_path = bundle_root / "pit_sector_membership" / "sidecar.json"
    for directory in (clock_path.parent, metadata_root, raw_path.parent, artifact_path.parent):
        directory.mkdir(parents=True, exist_ok=True)

    clock_body = _clock_body(
        universe_hash=universe_hash,
        clock_id=f"clock:prospective:20260825:{clock_suffix}",
    )
    clock_manifest = build_clock_manifest(clock_body)
    clock_path.write_text(canonical_json(clock_manifest), encoding="utf-8")
    clock = load_clock_manifest_for_capture(clock_path, now=DECISION_AT)

    raw_payload = _twse_raw_payload() if market == "twse" else _tpex_raw_payload()
    raw_path.write_bytes(raw_payload)
    source_market = "twse" if market == "twse" else "tpex"
    license_id = (
        "twse-open-data-license-v1"
        if market == "twse"
        else "tpex-open-data-license-v1"
    )
    license_url = (
        "https://openapi.twse.com.tw/"
        if market == "twse"
        else "https://www.tpex.org.tw/openapi/"
    )
    capture = build_official_first_seen_capture(
        raw_payloads={source_market: raw_payload},
        license_ids={source_market: license_id},
        license_urls={source_market: license_url},
        publication_at={
            source_market: datetime.fromisoformat("2026-08-20T00:00:00+08:00")
        },
        expected_symbols=expected_symbols,
        clock_id=clock.clock_id,
        clock_manifest_hash=clock.manifest_hash,
        universe_hash=universe_hash,
        available_at=datetime.fromisoformat("2026-08-25T05:00:00+08:00"),
        effective_from=EFFECTIVE_FROM,
        now=CAPTURE_NOW,
    )
    capture_prospective_pit_sector_membership(
        clock=clock,
        output_path=artifact_path,
        decision_timestamp=DECISION_AT.isoformat(),
        now=CAPTURE_NOW,
        rows=capture.rows,
        source_registry=capture.source_registry,
        expected_symbols=expected_symbols,
    )

    symbols_path.write_text(
        canonical_json(list(expected_symbols)),
        encoding="utf-8",
    )
    identity_path.write_text(
        canonical_json(
            {
                "schema_version": "manual-rule-only-universe.v1",
                "universe_hash": universe_hash,
                "symbols": list(expected_symbols),
                "scores_bp": [score_by_symbol[symbol] for symbol in expected_symbols],
                "candidate_count": len(expected_symbols),
                "source_id": "daily_prices",
            }
        ),
        encoding="utf-8",
    )
    if include_taxonomy:
        mapping = dict(taxonomy_mapping or {"24": "半導體業", "01": "水泥工業"})
        taxonomy_symbol_values = tuple(
            sorted(str(item) for item in (taxonomy_symbols or expected_symbols))
        )
        security_values = dict(
            security_types
            or {symbol: "common_equity" for symbol in taxonomy_symbol_values}
        )
        available_at = "2026-08-24T23:00:00+08:00"
        classification_source_id = "fixture:classification-catalog"
        classification_source_version = "fixture-classification.v1"
        security_source_id = "fixture:security-catalog"
        security_source_version = "fixture-security.v1"
        taxonomy_source = {
            "schema_version": PIT_TAXONOMY_SOURCE_SCHEMA_VERSION,
            "classification_version": "tw-industry-code-map.v1",
            "source_id": "fixture:taxonomy-custody",
            "source_version": "fixture-taxonomy.v1",
            "available_at": available_at,
            "effective_from": EFFECTIVE_FROM.isoformat(),
            "classification_source_id": classification_source_id,
            "classification_source_version": classification_source_version,
            "security_source_id": security_source_id,
            "security_source_version": security_source_version,
            "mapping": mapping,
            "security_type_by_symbol": security_values,
        }
        taxonomy_source_path.write_text(canonical_json(taxonomy_source), encoding="utf-8")
        taxonomy_source_hash = _file_hash(taxonomy_source_path)
        taxonomy_body = {
            "schema_version": PIT_TAXONOMY_IDENTITY_SCHEMA_VERSION,
            "classification_version": taxonomy_source["classification_version"],
            "source_id": taxonomy_source["source_id"],
            "source_version": taxonomy_source["source_version"],
            "source_hash": taxonomy_source_hash,
            "source_path": taxonomy_source_path.name,
            "available_at": available_at,
            "effective_from": EFFECTIVE_FROM.isoformat(),
            "classification_source_id": classification_source_id,
            "classification_source_version": classification_source_version,
            "security_source_id": security_source_id,
            "security_source_version": security_source_version,
            "universe_hash": universe_hash,
            "symbols": list(taxonomy_symbol_values),
            "mapping": mapping,
            "security_type_by_symbol": security_values,
        }
        taxonomy_payload = dict(taxonomy_body)
        taxonomy_payload["mapping_hash"] = _sha256_json(taxonomy_body)
        taxonomy_path.write_text(canonical_json(taxonomy_payload), encoding="utf-8")

    return PITFixture(
        artifact_path=artifact_path,
        bundle_root=bundle_root,
        clock_path=clock_path,
        universe_symbols_path=symbols_path,
        universe_identity_path=identity_path,
        taxonomy_identity_path=taxonomy_path,
        taxonomy_source_path=taxonomy_source_path,
        raw_path=raw_path,
        symbols=expected_symbols,
    )


def _clock_body(*, universe_hash: str, clock_id: str) -> dict[str, object]:
    seed = {"kind": "cash", "cash_bp": 10_000, "position_count": 0}
    seed["state_hash"] = payload_hash(seed)
    return {
        "schema_version": "prospective-formal-simulated-portfolio-clock.v1",
        "status": "planned",
        "clock_id": clock_id,
        "mode": "prospective_formal_simulation",
        "owner_decision_id": "owner-direction:pit-fixture:20260820:v1",
        "owner_decision_timestamp": "2026-08-20T12:00:00+08:00",
        "activation_trading_day": "2026-08-25",
        "decision_timezone": "Asia/Taipei",
        "decision_time": "08:30:00",
        "activation_calendar_evidence": {
            "schema_version": "official-trading-calendar-evidence.v1",
            "date": "2026-08-25",
            "is_trading_day": True,
            "reason_code": "twse_holiday_schedule_explicit_open",
            "source": "fixture:official-trading-calendar",
            "source_hash": _hash_token("calendar"),
        },
        "seed_state": seed,
        "virtual_notional_minor_units": 50_000_000,
        "strategy_version": "manual-rule-only-daily-rank-v1",
        "policy_version": "foreground-owner-bound-v1",
        "policy_hash": _hash_token("policy"),
        "universe_hash": universe_hash,
        "source_policy_hash": _hash_token("source-policy"),
        "candidate_model_hash": _hash_token("candidate-model"),
        "candidate_feature_manifest_hash": _hash_token("features"),
        "candidate_training_cutoff": "2026-08-20T08:30:00+08:00",
        "calibration_policy_hash": _hash_token("calibration"),
        "evaluation_policy_hash": _hash_token("evaluation"),
        "real_money": False,
        "broker_execution": False,
        "historical_backfill_claimed": False,
    }


def _twse_raw_payload() -> bytes:
    return canonical_json(
        [
            {"出表日期": "1150820", "公司代號": "1101", "產業別": "01", "公司名稱": "甲"},
            {"出表日期": "1150820", "公司代號": "2330", "產業別": "24", "公司名稱": "乙"},
        ]
    ).encode("utf-8")


def _tpex_raw_payload() -> bytes:
    return canonical_json(
        [
            {
                "Date": "115/08/20",
                "SecuritiesCompanyCode": "2317",
                "SecuritiesIndustryCode": "28",
                "CompanyName": "丙",
            }
        ]
    ).encode("utf-8")


def _hash_token(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    return _hash_token(canonical_json(value))


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(canonical_json(payload), encoding="utf-8")


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
