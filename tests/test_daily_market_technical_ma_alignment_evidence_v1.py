"""F02 四均線排列只由嚴格保存的 v4 原料計算。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Sequence, cast
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_ma_alignment_evidence_v1 as evidence_module
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_ma_alignment_evidence_v1 import (
    DailyMarketTechnicalMaAlignmentEvidenceV1,
    DailyMarketTechnicalMaAlignmentEvidenceV1Error,
    build_daily_market_technical_ma_alignment_evidence_v1,
    verify_daily_market_technical_ma_alignment_evidence_v1,
)
from app_module.daily_market_technical_read_session import (
    DailyMarketTechnicalReadSession,
    DailyMarketTechnicalSourceClockV4,
)
from app_module.daily_market_technical_snapshot_v4_producer import (
    write_daily_market_technical_snapshot_v4_batch,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
    canonical_v4_json_bytes,
    sha256_bytes,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 7)
_STOCK_CODE = "2330"


def _cohort(stock_code: str, decision_date: date) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "daily-market-technical-cohort.v4",
        "universe_id": "f02-synthetic-universe",
        "population_version": "f02-synthetic-population.v1",
        "decision_date": decision_date.isoformat(),
        "included_stock_codes": [stock_code],
        "excluded_stock_codes": [],
        "exclusion_reasons": {},
        "declared_count": 1,
    }
    return {**body, "cohort_identity_sha256": sha256_bytes(canonical_v4_json_bytes(body))}


def _close_text(value: Decimal | str) -> str:
    return str(value) if isinstance(value, Decimal) else value


def _write_database(
    path: Path,
    closes: Sequence[Decimal | str],
    *,
    last_row_lag_days: int = 0,
    duplicate_current: bool = False,
) -> tuple[date, date]:
    path.parent.mkdir(parents=True, exist_ok=True)
    decision_date = _DECISION_DATE
    current_date = decision_date - timedelta(days=last_row_lag_days)
    first_date = current_date - timedelta(days=len(closes) - 1)
    connection = sqlite3.connect(to_internal_io_path(path))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            with localcontext() as context:
                context.prec = 300
                for index, close_value in enumerate(closes):
                    observed_date = first_date + timedelta(days=index)
                    if isinstance(close_value, Decimal):
                        close = close_value
                        open_text = str(close)
                        high_text = str(close + Decimal("1"))
                        low_text = str(close / Decimal("2"))
                        close_token = str(close)
                    else:
                        open_text = "1"
                        high_text = "2"
                        low_text = "0.5"
                        close_token = close_value
                    row = (
                        observed_date.isoformat(),
                        _STOCK_CODE,
                        open_text,
                        high_text,
                        low_text,
                        close_token,
                        1000 + index,
                    )
                    rows.append(row)
                    if duplicate_current and observed_date == current_date:
                        rows.append(row)
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    finally:
        connection.close()
    return decision_date, current_date


def _saved_snapshot(
    tmp_path: Path,
    closes: Sequence[Decimal | str],
    *,
    last_row_lag_days: int = 0,
    duplicate_current: bool = False,
) -> tuple[
    DailyMarketTechnicalFeatureSnapshotV4,
    DailyMarketTechnicalSourceClockV4,
    Path,
]:
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    database = source_root / "daily-prices.sqlite"
    decision_date, _current_date = _write_database(
        database,
        closes,
        last_row_lag_days=last_row_lag_days,
        duplicate_current=duplicate_current,
    )
    scope = ResearchCaptureWriteScope(tmp_path / "configured-output", database)
    output_root = scope.root / "saved-v4"
    output_root.parent.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.combine(decision_date, time(16, 0), tzinfo=_TAIPEI)
    with DailyMarketTechnicalReadSession(database, cutoff) as source_session:
        clock = source_session.clock
        source_session.load_batch((_STOCK_CODE,))
        windows = source_session.finish()
    written = write_daily_market_technical_snapshot_v4_batch(
        output_root=output_root,
        cohort=_cohort(_STOCK_CODE, decision_date),
        source_clock=clock,
        finished_windows=windows,
        research_scope=scope,
    )
    assert written.status == "complete"
    assert written.artifact is not None
    artifact = written.artifact
    exact = DailyMarketTechnicalSnapshotV4Repository(output_root).read_exact(
        artifact.manifest_path,
        expected_manifest_sha256=artifact.manifest_sha256,
        expected_cohort_identity_sha256=artifact.cohort_identity_sha256,
        expected_source_clock_sha256=artifact.source_clock_identity_sha256,
        expected_method_contract_sha256=artifact.method_contract_sha256,
        expected_decision_date=artifact.decision_date,
    )
    assert len(exact.snapshots) == 1
    return exact.snapshots[0], exact.source_clock, database


def _build(
    snapshot: DailyMarketTechnicalFeatureSnapshotV4,
    clock: DailyMarketTechnicalSourceClockV4,
    *,
    expected_stock_code: str = _STOCK_CODE,
    expected_snapshot_identity_sha256: str | None = None,
    expected_source_identity: str | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> Any:
    return build_daily_market_technical_ma_alignment_evidence_v1(
        snapshot,
        expected_stock_code=expected_stock_code,
        expected_snapshot_identity_sha256=(
            expected_snapshot_identity_sha256 or snapshot.snapshot_identity_sha256
        ),
        expected_source_identity=expected_source_identity or snapshot.source_identity,
        expected_source_clock=clock,
        cancel_callback=cancel_callback,
    )


def _linear_closes(count: int, *, reverse: bool = False) -> tuple[Decimal, ...]:
    values = tuple(Decimal(index) for index in range(1, count + 1))
    return tuple(reversed(values)) if reverse else values


def test_true_saved_sixty_rows_produce_exact_strict_alignment_and_roundtrip(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))

    evidence = _build(snapshot, clock)

    assert evidence.state == "match"
    assert evidence.reason_codes == ("ma_alignment_strictly_descending",)
    assert evidence.stock_code == _STOCK_CODE
    assert evidence.feature_date == snapshot.current_session.feature_date  # type: ignore[union-attr]
    assert evidence.feature_date == snapshot.decision_date
    assert evidence.raw_source_window_fingerprint_sha256 == snapshot.raw_source_window_fingerprint_sha256
    assert evidence.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256
    assert evidence.warmup_required_sessions == 60
    assert evidence.warmup_observed_sessions == 60
    assert evidence.warmup_contiguous is True
    assert evidence.official_calendar_completeness == "unknown"
    assert evidence.source_available_at is None
    assert evidence.availability_status == "unknown"
    assert evidence.historical_pit_eligible is False
    assert tuple(item[0] for item in evidence.period_close_scaled_sums) == (5, 10, 20, 60)
    assert tuple(item.relation for item in evidence.comparisons) == (
        "greater",
        "greater",
        "greater",
    )
    restored = type(evidence).from_json(evidence.to_json())
    assert restored == evidence
    assert verify_daily_market_technical_ma_alignment_evidence_v1(
        restored,
        snapshot,
        expected_stock_code=_STOCK_CODE,
        expected_snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
        expected_source_identity=snapshot.source_identity,
        expected_source_clock=clock,
    ) == evidence


def test_json_depth_preflight_ignores_quoted_brackets_and_escaped_quotes() -> None:
    text_value = ('[' * 80) + ' { "quoted" } ' + ('}' * 80) + " \\\" tail"
    raw = json.dumps({"text": text_value}, separators=(",", ":"))

    evidence_module._preflight_json_depth(
        raw,
        error_code="technical_ma_alignment_v1_evidence_json_depth_limit",
    )

    assert json.loads(raw) == {"text": text_value}
    at_limit = ("[" * evidence_module.DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_JSON_DEPTH_V1)
    at_limit += "0" + (
        "]" * evidence_module.DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_JSON_DEPTH_V1
    )
    evidence_module._preflight_json_depth(
        at_limit,
        error_code="technical_ma_alignment_v1_evidence_json_depth_limit",
    )


def test_evidence_json_depth_limit_precedes_recursive_decoder_failure() -> None:
    nesting = evidence_module.DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_JSON_DEPTH_V1 + 1
    raw = ("[" * nesting) + "0" + ("]" * nesting)

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as error:
        DailyMarketTechnicalMaAlignmentEvidenceV1.from_json(raw)

    assert error.value.code == "technical_ma_alignment_v1_evidence_json_depth_limit"


def test_source_clock_json_depth_duplicate_and_byte_limits_are_named() -> None:
    deep_clock = ("[" * 40) + "0" + ("]" * 40)
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as depth_error:
        evidence_module._parse_source_clock_json(
            deep_clock,
            expected_sha256="0" * 64,
        )
    assert depth_error.value.code == "technical_ma_alignment_v1_source_clock_json_depth_limit"

    duplicate_clock = (
        '{"availability_status":"unknown","availability_status":"unknown"}'
    )
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as duplicate_error:
        evidence_module._parse_source_clock_json(
            duplicate_clock,
            expected_sha256="0" * 64,
        )
    assert duplicate_error.value.code == "technical_ma_alignment_v1_source_clock_duplicate_key"

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as bytes_error:
        evidence_module._parse_source_clock_json(
            " " * 8193,
            expected_sha256="0" * 64,
        )
    assert bytes_error.value.code == "technical_ma_alignment_v1_source_clock_invalid"


def test_evidence_json_duplicate_key_and_byte_limits_are_named(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))
    evidence = _build(snapshot, clock)
    raw = evidence.to_json()
    duplicate = raw[:-1] + ',"schema_version":"duplicate"}'

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as duplicate_error:
        type(evidence).from_json(duplicate)
    assert duplicate_error.value.code == "technical_ma_alignment_v1_evidence_duplicate_key"

    oversized = " " * (evidence_module.DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_MAX_EVIDENCE_BYTES_V1 + 1)
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as bytes_error:
        type(evidence).from_json(oversized)
    assert bytes_error.value.code == "technical_ma_alignment_v1_evidence_byte_limit"


def test_decision_date_may_be_after_current_feature_date_without_backfill(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(
        tmp_path,
        _linear_closes(60),
        last_row_lag_days=2,
    )

    evidence = _build(snapshot, clock)

    assert evidence.state == "match"
    assert evidence.decision_date == date(2026, 10, 7)
    assert evidence.feature_date == date(2026, 10, 5)
    assert evidence.feature_date < evidence.decision_date


def test_fifty_nine_rows_are_unknown_and_do_not_use_an_older_window(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(59))

    evidence = _build(snapshot, clock)

    assert evidence.state == "unknown"
    assert evidence.reason_codes == ("ma_alignment_insufficient_observed_sessions",)
    assert evidence.warmup_required_sessions == 60
    assert evidence.warmup_observed_sessions == 59
    assert evidence.period_close_scaled_sums == ()


def test_invalid_old_close_inside_current_sixty_rows_is_not_skipped_for_warmup(
    tmp_path: Path,
) -> None:
    closes: tuple[Decimal | str, ...] = ("invalid-close", *_linear_closes(59))
    snapshot, clock, _database = _saved_snapshot(tmp_path, closes)

    evidence = _build(snapshot, clock)

    assert evidence.state == "unknown"
    assert evidence.reason_codes in {
        ("ma_alignment_tail_session_pin_missing",),
        ("ma_alignment_insufficient_observed_sessions",),
    }
    assert evidence.period_close_scaled_sums == ()
    assert evidence.feature_date == snapshot.current_session.feature_date  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("closes", "expected_relation"),
    (
        (tuple(Decimal("10") for _ in range(60)), "equal"),
        (_linear_closes(60, reverse=True), "less"),
    ),
)
def test_equal_or_reverse_averages_are_valid_no_match(
    tmp_path: Path,
    closes: Sequence[Decimal],
    expected_relation: str,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, closes)

    evidence = _build(snapshot, clock)

    assert evidence.state == "no_match"
    assert evidence.reason_codes == ("ma_alignment_not_strictly_descending",)
    assert expected_relation in {item.relation for item in evidence.comparisons}


def test_high_precision_close_values_keep_exact_order_below_float_resolution(
    tmp_path: Path,
) -> None:
    with localcontext() as context:
        context.prec = 80
        epsilon = Decimal("0.000000000000000000000000000001")
        base = Decimal("1")
        closes = (
            tuple(base - Decimal("3") * epsilon for _ in range(40))
            + tuple(base - Decimal("3") * epsilon for _ in range(10))
            + tuple(base - epsilon for _ in range(5))
            + tuple(base + Decimal("3") * epsilon for _ in range(5))
        )
    snapshot, clock, _database = _saved_snapshot(tmp_path, closes)

    evidence = _build(snapshot, clock)

    assert evidence.state == "match"
    assert evidence.common_decimal_exponent == -30
    assert tuple(item.relation for item in evidence.comparisons) == (
        "greater",
        "greater",
        "greater",
    )


def test_extreme_decimal_exponent_is_rejected_before_integer_scaling() -> None:
    assert evidence_module._scale_and_sum((Decimal("1"), Decimal("1E-129"))) is None
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as close_error:
        evidence_module._canonical_close_text(Decimal("1E+999999999"))
    assert close_error.value.code == "technical_ma_alignment_v1_decimal_scale_out_of_bounds"
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as text_error:
        evidence_module._parse_close_text("1E+999999999")
    assert text_error.value.code == "technical_ma_alignment_v1_decimal_scale_out_of_bounds"


def test_duplicate_current_row_and_invalid_current_close_remain_unknown(
    tmp_path: Path,
) -> None:
    duplicate_snapshot, duplicate_clock, _database = _saved_snapshot(
        tmp_path / "duplicate",
        _linear_closes(60),
        duplicate_current=True,
    )
    duplicate_evidence = _build(duplicate_snapshot, duplicate_clock)
    assert duplicate_evidence.state == "unknown"
    assert duplicate_evidence.reason_codes == (
        "ma_alignment_current_session_pin_nonunique",
    )

    invalid_snapshot, invalid_clock, _invalid_database = _saved_snapshot(
        tmp_path / "invalid-current",
        (*_linear_closes(59), "invalid-close"),
    )
    invalid_evidence = _build(invalid_snapshot, invalid_clock)
    assert invalid_evidence.state == "unknown"
    assert invalid_evidence.reason_codes == ("ma_alignment_current_session_missing",)


def test_future_tampered_or_different_current_pins_are_rejected(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))

    tampered_row = replace(snapshot.rows[-1], close_price=Decimal("999"))
    tampered = replace(snapshot, rows=(*snapshot.rows[:-1], tampered_row))
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as tamper_error:
        _build(tampered, clock)
    assert tamper_error.value.code == "technical_ma_alignment_v1_snapshot_invalid"

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as identity_error:
        _build(snapshot, clock, expected_snapshot_identity_sha256="0" * 64)
    assert identity_error.value.code == "technical_ma_alignment_v1_current_pin_mismatch"

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as source_error:
        source_identity_prefix, _source_digest = snapshot.source_identity.rsplit(":", 1)
        _build(
            snapshot,
            clock,
            expected_source_identity=f"{source_identity_prefix}:{'0' * 64}",
        )
    assert source_error.value.code == "technical_ma_alignment_v1_current_pin_mismatch"

    later_cutoff = datetime.combine(
        snapshot.decision_date + timedelta(days=1),
        time(16, 0),
        tzinfo=_TAIPEI,
    )
    with DailyMarketTechnicalReadSession(clock.database_path, later_cutoff) as session:
        other_clock = session.clock
        session.load_batch((_STOCK_CODE,))
        session.finish()
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as clock_error:
        _build(snapshot, other_clock)
    assert clock_error.value.code == "technical_ma_alignment_v1_current_pin_mismatch"

    evidence = _build(snapshot, clock)
    future_payload = evidence.to_dict()
    future_payload["feature_date"] = (snapshot.decision_date + timedelta(days=1)).isoformat()
    future_body = {
        key: value for key, value in future_payload.items()
        if key != "evidence_identity_sha256"
    }
    future_payload["evidence_identity_sha256"] = hashlib.sha256(
        json.dumps(
            future_body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="technical_ma_alignment_v1_future_feature_date"):
        type(evidence).from_dict(future_payload)


def test_self_consistent_rehashed_transport_does_not_gain_reader_qualification(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))
    evidence = _build(snapshot, clock)
    payload = evidence.to_dict()
    source_identity_prefix, _source_digest = evidence.source_identity.rsplit(":", 1)
    payload["source_identity"] = f"{source_identity_prefix}:{'0' * 64}"
    body = {key: value for key, value in payload.items() if key != "evidence_identity_sha256"}
    payload["evidence_identity_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    self_consistent = type(evidence).from_dict(payload)
    assert self_consistent.source_identity == f"{source_identity_prefix}:{'0' * 64}"
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as error_info:
        verify_daily_market_technical_ma_alignment_evidence_v1(
            self_consistent,
            snapshot,
            expected_stock_code=_STOCK_CODE,
            expected_snapshot_identity_sha256=snapshot.snapshot_identity_sha256,
            expected_source_identity=snapshot.source_identity,
            expected_source_clock=clock,
        )
    assert error_info.value.code == "technical_ma_alignment_v1_reader_projection_mismatch"


def test_cancel_during_projection_and_after_dto_construction_never_returns_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))
    call_count = 0

    def cancel_during_scan() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 10

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as scan_error:
        _build(snapshot, clock, cancel_callback=cancel_during_scan)
    assert scan_error.value.code == "technical_ma_alignment_v1_cancelled"

    cancelled = [False]
    original_issue = evidence_module._issue_evidence

    def cancel_after_issue(**kwargs: Any) -> Any:
        result = original_issue(**kwargs)
        cancelled[0] = True
        return result

    monkeypatch.setattr(evidence_module, "_issue_evidence", cancel_after_issue)
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as barrier_error:
        _build(snapshot, clock, cancel_callback=lambda: cancelled[0])
    assert barrier_error.value.code == "technical_ma_alignment_v1_cancelled"


def test_cancel_callback_must_return_strict_bool_and_errors_keep_named_code(
    tmp_path: Path,
) -> None:
    snapshot, clock, _database = _saved_snapshot(tmp_path, _linear_closes(60))
    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as invalid_error:
        _build(snapshot, clock, cancel_callback=lambda: cast(Any, 1))
    assert invalid_error.value.code == "technical_ma_alignment_v1_cancel_callback_invalid"

    def failed_callback() -> bool:
        raise RuntimeError("callback failure")

    with pytest.raises(DailyMarketTechnicalMaAlignmentEvidenceV1Error) as callback_error:
        _build(snapshot, clock, cancel_callback=failed_callback)
    assert callback_error.value.code == "technical_ma_alignment_v1_cancel_callback_failed"
