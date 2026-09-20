"""共用的真實 session proof 與 prospective source contract 測試 fixture。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from data_module.natural_maturity_session_resolver import (
    NaturalMaturitySessionResolver,
)
from data_module.official_trading_calendar_cache import (
    build_twse_calendar_cache,
    write_twse_calendar_cache,
)
from data_module.recommendation_calibration_source_contract import (
    _hash_payload,
    write_source_contract,
)
from ml_module.recommendation_calibration_evidence import (
    MaturedRecommendationOutcome,
    RecommendationPredictionCaptureInput,
    _feature_snapshot_fingerprint,
    _sha256_file,
)
from ml_module.recommendation_calibration_training import feature_schema_hash


FEATURE_SCHEMA: tuple[tuple[str, str, str], ...] = (
    ("momentum_bp", "int", "bp"),
    ("volume_ratio_bp", "int", "bp"),
)
FEATURE_REGISTRY_HASH = "sha256:" + "3" * 64
_UTC = timezone.utc


@dataclass(frozen=True)
class VerifiedNaturalFixture:
    """供 daily、cost、projection tests 共用的唯讀來源與 proof。"""

    db_path: Path
    calendar_root: Path
    calendar_paths: tuple[Path, ...]
    resolver: NaturalMaturitySessionResolver
    evaluation_at: datetime
    evaluation_day: str
    capture_dates: tuple[date, ...]
    capture_inputs: Mapping[str, RecommendationPredictionCaptureInput]
    source_contract_bindings: Mapping[str, Mapping[str, Any]]
    source_contract_paths: Mapping[str, Path]
    session_proofs: Mapping[str, Mapping[str, Any]]
    endpoint_dates: Mapping[str, str]

    def input_for(self, capture_day: date | str) -> RecommendationPredictionCaptureInput:
        key = capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
        return self.capture_inputs[key]

    def binding_for(self, capture_day: date | str) -> Mapping[str, Any]:
        key = capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
        return self.source_contract_bindings[key]

    def proof_for(self, capture_day: date | str) -> Mapping[str, Any]:
        key = capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
        return self.session_proofs[key]

    def outcome_for(
        self,
        capture_day: date | str,
        *,
        capture_row_id: str,
        stock_return_bp: int,
        symbol: str | None = None,
    ) -> MaturedRecommendationOutcome:
        key = capture_day.isoformat() if isinstance(capture_day, date) else str(capture_day)[:10]
        return MaturedRecommendationOutcome(
            capture_row_id=capture_row_id,
            label_end_date=self.endpoint_dates[key],
            label_available_date=self.endpoint_dates[key],
            stock_return_bp=stock_return_bp,
            observed_liquidity_cost_bp=20,
            benchmark_return_bp=100,
            session_proof=self.session_proofs[key],
        )


def make_verified_natural_fixture(
    tmp_path: Path,
    capture_dates: Sequence[date | str],
    evaluation_day: str,
    direction: str = "price_up",
    *,
    feature_schema: tuple[tuple[str, str, str], ...] = FEATURE_SCHEMA,
    feature_registry_hash: str = FEATURE_REGISTRY_HASH,
) -> VerifiedNaturalFixture:
    """建立 exact-20 official sessions 及可重驗 source contract。

    這個 fixture 只在測試暫存目錄建立 SQLite、calendar cache 與 lineage
    artifacts；不讀寫正式資料，也不替 production caller 省略任何 proof。
    """

    if direction != "price_up":
        raise ValueError("fixture only supports the price_up lane")
    normalized_dates = tuple(
        sorted(
            {
                date.fromisoformat(item.isoformat() if isinstance(item, date) else str(item)[:10])
                for item in capture_dates
            }
        )
    )
    if not normalized_dates:
        raise ValueError("at least one capture date is required")
    evaluation = date.fromisoformat(str(evaluation_day)[:10])
    evaluation_at = datetime(
        evaluation.year,
        evaluation.month,
        evaluation.day,
        8,
        0,
        tzinfo=_UTC,
    )
    endpoint_dates = {
        capture.isoformat(): _twentieth_weekday(capture).isoformat()
        for capture in normalized_dates
    }
    if any(date.fromisoformat(endpoint) >= evaluation for endpoint in endpoint_dates.values()):
        raise ValueError("evaluation_day must follow every exact-20 session endpoint")

    fixture_key = _hash_payload(
        {"capture_dates": [item.isoformat() for item in normalized_dates], "evaluation_day": evaluation.isoformat()}
    )[7:23]
    fixture_root = (tmp_path / "verified-natural" / fixture_key).resolve()
    db_path = (fixture_root / "source.db").resolve()
    _write_market_database(
        db_path,
        start=min(normalized_dates),
        end=max(date.fromisoformat(item) for item in endpoint_dates.values()),
    )
    calendar_root = (fixture_root / "calendar").resolve()
    years = tuple(
        range(min(normalized_dates).year, max(date.fromisoformat(item) for item in endpoint_dates.values()).year + 1)
    )
    calendar_paths = tuple(
        _write_calendar(calendar_root, year=year, captured_at=evaluation_at - timedelta(days=1))
        for year in years
    )
    resolver = NaturalMaturitySessionResolver(db_path, calendar_root)

    inputs: dict[str, RecommendationPredictionCaptureInput] = {}
    bindings: dict[str, Mapping[str, Any]] = {}
    contract_paths: dict[str, Path] = {}
    proofs: dict[str, Mapping[str, Any]] = {}
    for index, capture in enumerate(normalized_dates):
        capture_text = capture.isoformat()
        capture_input = _capture_input(index, capture, feature_schema)
        inputs[capture_text] = capture_input
        source_contract, receipt = _write_source_lineage(
            tmp_path=tmp_path,
            capture_day=capture,
            capture_inputs=(capture_input,),
            source_database=db_path,
            feature_schema=feature_schema,
            feature_registry_hash=feature_registry_hash,
        )
        binding = _source_binding(
            source_contract,
            receipt,
            capture_day=capture,
            capture_inputs=(capture_input,),
        )
        resolution = resolver.resolve(capture_text, evaluation_at, horizon_sessions=20)
        if resolution.status != "ready" or not isinstance(resolution.proof, Mapping):
            raise ValueError(f"fixture session resolution failed: {capture_text}:{resolution.reason}")
        endpoint = endpoint_dates[capture_text]
        if resolution.endpoint_date != endpoint:
            raise ValueError(f"fixture endpoint mismatch: {capture_text}")
        bindings[capture_text] = binding
        contract_paths[capture_text] = Path(str(receipt["contract_path"])).resolve()
        proofs[capture_text] = dict(resolution.proof)

    return VerifiedNaturalFixture(
        db_path=db_path,
        calendar_root=calendar_root,
        calendar_paths=calendar_paths,
        resolver=resolver,
        evaluation_at=evaluation_at,
        evaluation_day=evaluation.isoformat(),
        capture_dates=normalized_dates,
        capture_inputs=inputs,
        source_contract_bindings=bindings,
        source_contract_paths=contract_paths,
        session_proofs=proofs,
        endpoint_dates=endpoint_dates,
    )


def _twentieth_weekday(capture: date) -> date:
    sessions: list[date] = []
    current = capture + timedelta(days=1)
    while len(sessions) < 20:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions[-1]


def _capture_input(
    index: int,
    capture: date,
    feature_schema: tuple[tuple[str, str, str], ...],
) -> RecommendationPredictionCaptureInput:
    return RecommendationPredictionCaptureInput(
        row_id=f"forward-{index:02d}",
        symbol="1101" if index % 2 == 0 else "2330",
        decision_date=capture.isoformat(),
        feature_as_of_date=(capture - timedelta(days=1)).isoformat(),
        feature_available_date=(capture - timedelta(days=1)).isoformat(),
        feature_values=tuple(
            (
                ((index % 6) - 2) * 1000
                if feature_index == 0
                else 1000 + index * 10
                if feature_index == 1
                else (index + 1) * (feature_index + 1)
            )
            for feature_index in range(len(feature_schema))
        ),
        rule_probability_bp=5000,
        rule_after_cost_probability_bp=5000,
    )


def _write_market_database(path: Path, *, start: date, end: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            'CREATE TABLE market_indices ("日期" TEXT NOT NULL, "指數名稱" TEXT NOT NULL, '
            '"收盤指數" TEXT NOT NULL, "收盤價" TEXT NOT NULL)'
        )
        current = start
        value = 20_000
        while current <= end:
            if current.weekday() < 5:
                compact = current.strftime("%Y%m%d")
                connection.execute(
                    'INSERT INTO market_indices VALUES (?, ?, ?, ?)',
                    (compact, "TAIEX", str(value), str(value)),
                )
                value += 1
            current += timedelta(days=1)


def _write_calendar(root: Path, *, year: int, captured_at: datetime) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        [
            {
                "Name": "測試年度休市",
                "Date": f"{year - 1911:03d}0101",
                "Weekday": "四",
                "Description": "測試用年度休市紀錄。",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    cache = build_twse_calendar_cache(
        calendar_year=year,
        raw_response=raw,
        requested_at=captured_at - timedelta(seconds=1),
        captured_at=captured_at,
        response_status=200,
        response_headers={"ETag": f'"fixture-calendar-{year}"'},
        max_age=timedelta(days=31),
    )
    path = root / f"twse_holiday_schedule_{year}_fixture.json"
    write_twse_calendar_cache(path, cache, allowed_root=root)
    return path


def _write_source_lineage(
    *,
    tmp_path: Path,
    capture_day: date,
    capture_inputs: Sequence[RecommendationPredictionCaptureInput],
    source_database: Path,
    feature_schema: tuple[tuple[str, str, str], ...],
    feature_registry_hash: str,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    capture_text = capture_day.isoformat()
    if not capture_inputs:
        raise ValueError("at least one source-contract capture input is required")
    available_at = f"{capture_text}T08:00:00+08:00"
    source_key = _hash_payload({"symbols": sorted({item.symbol for item in capture_inputs})})[7:19]
    root = (tmp_path / "verified-source-lineage" / capture_text / source_key).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "row_id": item.row_id,
            "symbol": item.symbol,
            "decision_date": item.decision_date,
            "feature_as_of_date": item.feature_as_of_date,
            "feature_available_date": item.feature_available_date,
            "feature_values": list(item.feature_values),
        }
        for item in capture_inputs
    ]
    symbols = sorted({item.symbol for item in capture_inputs})
    feature_body = {
        "component": "prospective_recommendation_features",
        "source_db": str(source_database),
        "decision_date": capture_text,
        "history_start_date": "2025-01-01",
        "feature_registry_hash": feature_registry_hash,
        "feature_schema_hash": feature_schema_hash(feature_schema),
        "symbols": symbols,
        "rows": rows,
    }
    feature_snapshot: dict[str, Any] = {
        "status": "captured",
        "verified": True,
        **feature_body,
        "row_count": len(rows),
        "rows_sha256": _hash_payload(feature_body),
        "captured_at": available_at,
        "reason": None,
    }
    feature_snapshot["content_sha256"] = _hash_payload(feature_snapshot)

    raw_path = root / "daily-source.raw.json"
    raw_path.write_text(
        json.dumps(
            {"decision_date": capture_text, "symbols": symbols, "source": "verified-test"},
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    daily_receipt_path = root / "daily-source.receipt.json"
    daily_receipt = _hashed_payload(
        {
            "schema_version": "fixture-daily-source-receipt.v1",
            "decision_date": capture_text,
            "available_at": available_at,
            "raw_response_path": str(raw_path.resolve()),
            "symbols": symbols,
        },
        "content_sha256",
    )
    daily_receipt_path.write_text(json.dumps(daily_receipt, sort_keys=True) + "\n", encoding="utf-8")

    technical_output = _hashed_payload(
        {
            "component": "technical_indicators",
            "decision_date": capture_text,
            "symbols": symbols,
            "rows_sha256": _hash_payload({"rows": rows}),
        },
        "content_sha256",
    )
    publication_payload = _hashed_payload(
        {
            "schema_version": "fixture-technical-publication-receipt.v1",
            "decision_date": capture_text,
            "available_at": available_at,
            "technical_step_status": "fixture",
            "technical_output": technical_output,
            "source_receipts": [
                {
                    "receipt_path": str(daily_receipt_path.resolve()),
                    "receipt_sha256": _sha256_file(daily_receipt_path),
                    "raw_response_path": str(raw_path.resolve()),
                    "raw_response_sha256": _sha256_file(raw_path),
                    "available_at": available_at,
                }
            ],
        },
        "content_sha256",
    )
    publication_path = root / "technical-publication.receipt.json"
    publication_path.write_text(json.dumps(publication_payload, sort_keys=True) + "\n", encoding="utf-8")

    section_paths: dict[str, Path] = {}
    for section_name in ("adjustments", "coverage"):
        section_path = root / f"corporate-{section_name}.json"
        section_path.write_text(
            json.dumps(
                {"decision_date": capture_text, "section": section_name, "symbols": symbols},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        section_paths[section_name] = section_path
    adjustment_manifest = _hashed_payload(
        {
            "schema_version": "fixture-corporate-adjustment-manifest.v1",
            "decision_date": capture_text,
            "adjustments": {
                "path": section_paths["adjustments"].name,
                "file_hash": _sha256_file(section_paths["adjustments"]),
            },
            "coverage": {
                "path": section_paths["coverage"].name,
                "file_hash": _sha256_file(section_paths["coverage"]),
            },
        },
        "manifest_hash",
    )
    adjustment_path = root / "corporate-adjustment.manifest.json"
    adjustment_path.write_text(json.dumps(adjustment_manifest, sort_keys=True) + "\n", encoding="utf-8")
    event_manifest = _hashed_payload(
        {
            "schema_version": "fixture-official-event-manifest.v1",
            "decision_date": capture_text,
            "symbols": symbols,
        },
        "manifest_hash",
    )
    event_path = root / "official-events.manifest.json"
    event_path.write_text(json.dumps(event_manifest, sort_keys=True) + "\n", encoding="utf-8")

    contract_body: dict[str, Any] = {
        "schema_version": "recommendation-calibration-source-contract.v1",
        "status": "blocked",
        "decision_date": capture_text,
        "symbols": symbols,
        "source_root": str(tmp_path.resolve()),
        "data_root": str(tmp_path.resolve()),
        "source_database": str(source_database.resolve()),
        "technical": {
            "status": "ready",
            "formal_source_contract": {"verified": True},
            "prospective_available": True,
            "prospective_blockers": [],
            "publication_receipt": {
                "path": str(publication_path.resolve()),
                "sha256": _sha256_file(publication_path),
                "payload": publication_payload,
                "available_at": available_at,
            },
            "publication_available_at": available_at,
            "source_receipt_available_ats": [available_at],
            "prospective_feature_snapshot": feature_snapshot,
        },
        "corporate_actions": {
            "status": "ready",
            "formal_source_contract": {"verified": True},
            "adjustment_custody": {
                "prospective_verified": True,
                "manifest_hash": adjustment_manifest["manifest_hash"],
                "manifest_path": str(adjustment_path.resolve()),
                "manifest_file_hash": _sha256_file(adjustment_path),
                "available_at": available_at,
            },
            "event_publication": {
                "manifest_path": str(event_path.resolve()),
                "manifest_file_sha256": _sha256_file(event_path),
                "manifest_hash": event_manifest["manifest_hash"],
                "source_publication_available_at": available_at,
            },
        },
        "lanes": {
            "price_up_calibration": {
                "status": "blocked",
                "prospective_status": "ready",
                "blockers": [],
                "prospective_blockers": [],
            },
            "after_cost_calibration": {
                "status": "blocked",
                "prospective_status": "blocked",
                "blockers": ["observed_liquidity_cost_not_matured_with_fill_lineage"],
                "prospective_blockers": ["observed_liquidity_cost_not_matured_with_fill_lineage"],
            },
            "actual_execution": {
                "status": "blocked",
                "blockers": ["broker_actual_fill_custody_not_in_scope"],
            },
        },
        "historical_pit_policy": {"eligible": False, "reason": "prospective_test_fixture_only"},
        "replay_vs_prospective": {
            "historical_replay_status": "separately_verified_fixture",
            "prospective_input_status": "ready_for_future_capture_only",
        },
    }
    contract = {**contract_body, "contract_sha256": _hash_payload(contract_body)}
    receipt = write_source_contract(contract, learning_output_root=tmp_path)
    return contract, receipt


def _source_binding(
    contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    capture_day: date,
    capture_inputs: Sequence[RecommendationPredictionCaptureInput],
) -> dict[str, Any]:
    technical = contract["technical"]
    publication = technical["publication_receipt"]
    feature = technical["prospective_feature_snapshot"]
    corporate = contract["corporate_actions"]
    adjustment = corporate["adjustment_custody"]
    event = corporate["event_publication"]
    rows = [
        {
            "row_id": item.row_id,
            "symbol": item.symbol,
            "decision_date": item.decision_date,
            "feature_as_of_date": item.feature_as_of_date,
            "feature_available_date": item.feature_available_date,
            "feature_values": list(item.feature_values),
        }
        for item in capture_inputs
    ]
    symbols = sorted({item.symbol for item in capture_inputs})
    return {
        "schema_version": "recommendation-calibration-capture-source-binding.v1",
        "contract_path": receipt["contract_path"],
        "contract_content_sha256": receipt["contract_content_sha256"],
        "contract_file_sha256": receipt["contract_file_sha256"],
        "decision_date": contract["decision_date"],
        "symbols": list(contract["symbols"]),
        "price_up_prospective_status": "ready",
        "price_up_prospective_blockers": [],
        "technical_publication_receipt_file_sha256": publication["sha256"],
        "technical_publication_content_sha256": publication["payload"]["content_sha256"],
        "technical_publication_available_at": technical["publication_available_at"],
        "technical_source_available_ats": list(technical["source_receipt_available_ats"]),
        "feature_snapshot_content_sha256": feature["content_sha256"],
        "feature_snapshot_rows_sha256": feature["rows_sha256"],
        "feature_snapshot_captured_at": feature["captured_at"],
        "corporate_adjustment_manifest_hash": adjustment["manifest_hash"],
        "corporate_adjustment_available_at": adjustment["available_at"],
        "official_event_available_at": event["source_publication_available_at"],
        "historical_pit_eligible": False,
        "source_semantics": "prospective_input_only;not_historical_backfill",
        "capture_decision_date": capture_day.isoformat(),
        "capture_symbols": symbols,
        "feature_row_count": len(rows),
        "feature_snapshot_fingerprint": _feature_snapshot_fingerprint(capture_day, rows),
    }


def make_verified_source_binding(
    tmp_path: Path,
    capture_day: date | str,
    capture_inputs: Sequence[RecommendationPredictionCaptureInput],
    source_database: Path,
    *,
    feature_schema: tuple[tuple[str, str, str], ...] = FEATURE_SCHEMA,
    feature_registry_hash: str = FEATURE_REGISTRY_HASH,
) -> Mapping[str, Any]:
    """以既有 source DB 建立一筆可重驗 capture binding。"""

    normalized_day = (
        capture_day if isinstance(capture_day, date) else date.fromisoformat(str(capture_day)[:10])
    )
    contract, receipt = _write_source_lineage(
        tmp_path=tmp_path,
        capture_day=normalized_day,
        capture_inputs=tuple(capture_inputs),
        source_database=Path(source_database).resolve(),
        feature_schema=feature_schema,
        feature_registry_hash=feature_registry_hash,
    )
    return _source_binding(
        contract,
        receipt,
        capture_day=normalized_day,
        capture_inputs=tuple(capture_inputs),
    )


def _hashed_payload(body: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return {**dict(body), field_name: _hash_payload(dict(body))}


__all__ = [
    "VerifiedNaturalFixture",
    "make_verified_natural_fixture",
    "make_verified_source_binding",
]
