from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
from types import MappingProxyType
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_feature_snapshot_v4 as snapshot_module
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES,
    DailyMarketTechnicalFeatureSnapshotV4,
    _enforce_json_size,
    build_daily_market_technical_feature_snapshot_v4,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalReadSession


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)
_DECISION_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
_NO_MALFORMED_DATE = object()


def _build_snapshot(
    work_dir: Path,
    *,
    row_count: int = 120,
    malformed_date: object = _NO_MALFORMED_DATE,
    duplicate_last_date: bool = False,
    last_close: int | None = None,
) -> DailyMarketTechnicalFeatureSnapshotV4:
    suffix = "malformed" if malformed_date is not _NO_MALFORMED_DATE else "standard"
    if duplicate_last_date:
        suffix += "-duplicate"
    if last_close is not None:
        suffix += f"-close-{last_close}"
    database = work_dir / f"technical-v4-{row_count}-{suffix}.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE daily_prices ("
            "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
            "收盤價 TEXT, 成交股數 INTEGER)"
        )
        start = _DECISION_DATE - timedelta(days=row_count - 1)
        rows: list[tuple[object, str, str, str, str, str, int]] = []
        for index in range(row_count):
            day = start + timedelta(days=index)
            close = Decimal(
                last_close if last_close is not None and index == row_count - 1
                else 500 - index
            )
            rows.append((
                day.isoformat(),
                "2382",
                format(close, "f"),
                format(close + 1, "f"),
                format(close - 1, "f"),
                format(close, "f"),
                1000 + index,
            ))
        if malformed_date is not _NO_MALFORMED_DATE:
            rows.append((
                malformed_date,
                "2382",
                "100",
                "101",
                "99",
                "100",
                777,
            ))
        if duplicate_last_date:
            rows.append((
                _DECISION_DATE.isoformat(),
                "2382",
                "999",
                "1000",
                "998",
                "999",
                888,
            ))
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()

    with DailyMarketTechnicalReadSession(database, _DECISION_CUTOFF) as session:
        clock = session.clock
        session.load_batch(("2382",))
        windows = session.finish()
    assert len(windows) == 1
    return build_daily_market_technical_feature_snapshot_v4(
        windows[0],
        source_clock=clock,
    )


@pytest.fixture
def short_temp() -> Iterator[Path]:
    repository_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix=".t-", dir=repository_root) as path:
        yield Path(path)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refresh_snapshot_identity(payload: dict[str, Any]) -> None:
    payload["snapshot_identity_sha256"] = _sha256_json({
        key: value
        for key, value in payload.items()
        if key != "snapshot_identity_sha256"
    })


def _mutable_payload(snapshot: DailyMarketTechnicalFeatureSnapshotV4) -> dict[str, Any]:
    return cast(dict[str, Any], deepcopy(snapshot.to_dict()))


def test_saved_calculation_binding_roundtrips_without_current_kernel_reads(
    short_temp: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot(short_temp)
    encoded = snapshot.to_json()
    binding = json.loads(snapshot.calculation_binding_json)
    assert _sha256_json(binding) == snapshot.calculation_identity_sha256
    assert binding["numpy_version"] != "unknown"
    assert binding["pandas_version"] != "unknown"
    assert len(binding["technical_indicators_module_sha256"]) == 64
    assert len(binding["indicator_kernels_module_sha256"]) == 64

    def forbidden_current_payload() -> None:
        raise AssertionError("重開保存來源不應讀取目前的計算核心")

    monkeypatch.setattr(
        "app_module.daily_market_technical_source._calculation_binding_payload",
        forbidden_current_payload,
    )
    assert DailyMarketTechnicalFeatureSnapshotV4.from_json(encoded).to_json() == encoded


@pytest.mark.parametrize("field", [
    "technical_indicators_module_sha256", "indicator_kernels_module_sha256",
    "numpy_version", "pandas_version", "talib_version", "parameters",
])
def test_rehashed_snapshot_rejects_changed_calculation_binding(
    short_temp: Path, field: str,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    binding = payload["calculation"]["binding"]
    if field.endswith("sha256"):
        binding[field] = "a" * 64
    elif field == "parameters":
        binding[field] = {}
    else:
        binding[field] = "different-version"
    _refresh_snapshot_identity(payload)
    with pytest.raises(ValueError):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_snapshot_requires_saved_calculation_binding(short_temp: Path) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    del payload["calculation"]["binding"]
    _refresh_snapshot_identity(payload)
    with pytest.raises(ValueError, match="calculation_invalid"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_120_row_snapshot_roundtrips_with_unknown_availability_and_negative_macd(
    short_temp: Path,
) -> None:
    snapshot = _build_snapshot(short_temp, row_count=120)
    encoded = snapshot.to_json()
    restored = DailyMarketTechnicalFeatureSnapshotV4.from_json(encoded)

    assert len(snapshot.rows) == 120
    assert len(snapshot.session_pins) == 120
    assert len(snapshot.feature_sessions) == 2
    assert len(snapshot.rules) == 5
    assert len(encoded.encode("utf-8")) <= DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES
    assert snapshot.source_clock["availability_status"] == "unknown"
    assert snapshot.source_clock["source_available_at"] is None
    assert snapshot.source_clock["historical_pit_eligible"] is False
    assert snapshot.current_session is not None
    macd = next(item for item in snapshot.current_session.features if item.key == "MACD")
    assert macd.state == "observed"
    assert macd.value is not None and macd.value < 0
    assert restored.to_json() == encoded


def test_short_history_preserves_warmup_unknowns_without_claiming_pit(
    short_temp: Path,
) -> None:
    snapshot = _build_snapshot(short_temp, row_count=10)
    rules = {item.key: item for item in snapshot.rules}

    assert rules["ma5_20_golden_cross"].state == "unknown"
    assert rules["volume_ratio_20_including_current"].state == "unknown"
    assert rules["volume_ratio_5_including_current"].state in {"match", "no_match"}
    assert snapshot.availability_status == "unknown"
    assert all(item.availability_result == "available_at_unknown" for item in snapshot.rules)


@pytest.mark.parametrize(
    "mutation",
    ("wrong_stock", "wrong_date", "wrong_reference", "wrong_pin", "corrupt_row"),
)
def test_snapshot_rejects_identity_date_reference_pin_and_raw_row_tampering(
    short_temp: Path,
    mutation: str,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    if mutation == "wrong_stock":
        payload["stock_code"] = "2330"
    elif mutation == "wrong_date":
        payload["decision_date"] = "2026-10-05"
    elif mutation == "wrong_reference":
        payload["rules"][0]["raw_fact_refs"][0]["source_fingerprint_sha256"] = "0" * 64
    elif mutation == "wrong_pin":
        payload["source_clock"]["source_file_pin"][0][3] += 1
        payload["source_clock_sha256"] = _sha256_json(payload["source_clock"])
    else:
        payload["raw_rows"][0]["close_price"] = "999999"

    with pytest.raises(ValueError):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_snapshot_rejects_json_float_duplicate_keys_and_oversize_payload(
    short_temp: Path,
) -> None:
    snapshot = _build_snapshot(short_temp)
    payload = _mutable_payload(snapshot)
    payload["feature_sessions"][-1]["features"][0]["value"] = 1.25
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)

    encoded = snapshot.to_json()
    duplicate = encoded.replace(
        '"schema_version":',
        '"schema_version":"daily-market-technical-feature-snapshot.v4","schema_version":',
        1,
    )
    with pytest.raises(ValueError, match="technical_snapshot_v4_duplicate_json_key"):
        DailyMarketTechnicalFeatureSnapshotV4.from_json(duplicate)

    with pytest.raises(ValueError, match="technical_snapshot_v4_byte_limit"):
        _enforce_json_size({"oversized": "x" * DAILY_MARKET_TECHNICAL_FEATURE_SNAPSHOT_MAX_BYTES})


def test_reject_float_tree_fast_path_preserves_container_and_float_subclass_contracts() -> None:
    class FloatSubclass(float):
        pass

    class ListSubclass(list):
        pass

    class TupleSubclass(tuple):
        pass

    class StringSubclass(str):
        pass

    valid_payload = {
        "nested": [1, True, None, "text", {StringSubclass("key"): 2}],
        "tuple_values": (False, 3),
    }
    snapshot_module._reject_float_tree(valid_payload)

    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        snapshot_module._reject_float_tree({"value": 1.25})
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        snapshot_module._reject_float_tree({"value": FloatSubclass(1.25)})
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        snapshot_module._reject_float_tree(ListSubclass([FloatSubclass(1.25)]))
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        snapshot_module._reject_float_tree(TupleSubclass((1.25,)))
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_float_forbidden"):
        snapshot_module._reject_float_tree(MappingProxyType({"nested": 1.25}))
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_key_invalid"):
        snapshot_module._reject_float_tree({1: "non-string key"})
    with pytest.raises(ValueError, match="technical_snapshot_v4_json_key_invalid"):
        snapshot_module._reject_float_tree(MappingProxyType({1: "non-string key"}))

    encoded = snapshot_module._canonical_json({"nested": [1, True, None, "text"]})
    assert encoded == '{"nested":[1,true,null,"text"]}'


@pytest.mark.parametrize(
    "rule_key",
    ("ma5_20_golden_cross", "kd_golden_cross", "macd_golden_cross"),
)
def test_rehashed_snapshot_cannot_flip_a_cross_rule_state(
    short_temp: Path,
    rule_key: str,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    rule = next(item for item in payload["rules"] if item["key"] == rule_key)
    assert rule["state"] in {"match", "no_match"}
    if rule["state"] == "match":
        rule["state"] = "no_match"
        rule["supports"] = []
        rule["counterevidence"] = ["tampered explanation"]
    else:
        rule["state"] = "match"
        rule["supports"] = ["tampered explanation"]
        rule["counterevidence"] = []
    _refresh_snapshot_identity(payload)

    with pytest.raises(ValueError, match="technical_snapshot_v4_rule_semantics_mismatch"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_rehashed_snapshot_cannot_flip_ma_cross_in_either_direction(
    short_temp: Path,
) -> None:
    no_match = _mutable_payload(_build_snapshot(short_temp))
    match = _mutable_payload(_build_snapshot(short_temp, last_close=1000))
    no_match_rule = next(
        item for item in no_match["rules"] if item["key"] == "ma5_20_golden_cross"
    )
    match_rule = next(
        item for item in match["rules"] if item["key"] == "ma5_20_golden_cross"
    )
    assert no_match_rule["state"] == "no_match"
    assert match_rule["state"] == "match"

    for payload, rule in ((no_match, no_match_rule), (match, match_rule)):
        if rule["state"] == "match":
            rule["state"] = "no_match"
            rule["supports"] = []
            rule["counterevidence"] = ["tampered"]
        else:
            rule["state"] = "match"
            rule["supports"] = ["tampered"]
            rule["counterevidence"] = []
        _refresh_snapshot_identity(payload)
        with pytest.raises(ValueError, match="technical_snapshot_v4_rule_semantics_mismatch"):
            DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_rehashed_snapshot_cannot_turn_insufficient_warmup_into_match(
    short_temp: Path,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp, row_count=10))
    rule = next(item for item in payload["rules"] if item["key"] == "ma5_20_golden_cross")
    assert rule["state"] == "unknown"
    rule["state"] = "match"
    rule["unknown_reasons"] = []
    rule["supports"] = ["tampered warmup result"]
    rule["counterevidence"] = []
    _refresh_snapshot_identity(payload)

    with pytest.raises(ValueError):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_rehashed_snapshot_cannot_hide_a_known_volume_ratio_as_unknown(
    short_temp: Path,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    rule = next(
        item for item in payload["rules"]
        if item["key"] == "volume_ratio_20_including_current"
    )
    assert rule["state"] in {"match", "no_match"}
    rule["state"] = "unknown"
    rule["supports"] = []
    rule["counterevidence"] = []
    rule["unknown_reasons"] = ["tampered"]
    rule["numerator"] = None
    rule["denominator"] = None
    rule["ratio"] = None
    _refresh_snapshot_identity(payload)

    with pytest.raises(ValueError, match="technical_snapshot_v4_rule_semantics_mismatch"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


def test_rehashed_snapshot_cannot_change_volume_ratio_or_rule_parameters(
    short_temp: Path,
) -> None:
    payload = _mutable_payload(_build_snapshot(short_temp))
    rule = next(
        item for item in payload["rules"]
        if item["key"] == "volume_ratio_20_including_current"
    )
    rule["ratio"] = "999"
    _refresh_snapshot_identity(payload)
    with pytest.raises(ValueError, match="technical_snapshot_v4_rule_semantics_mismatch"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)

    payload = _mutable_payload(_build_snapshot(short_temp, last_close=777))
    rule = next(
        item for item in payload["rules"]
        if item["key"] == "volume_ratio_20_including_current"
    )
    rule["parameters"]["threshold_ratio"] = "1"
    _refresh_snapshot_identity(payload)
    with pytest.raises(ValueError, match="technical_snapshot_v4_rule_parameters_mismatch"):
        DailyMarketTechnicalFeatureSnapshotV4.from_dict(payload)


@pytest.mark.parametrize("raw_date", (None, "", "invalid-date"))
def test_null_empty_and_invalid_raw_dates_roundtrip_as_unknown_evidence(
    short_temp: Path,
    raw_date: object,
) -> None:
    snapshot = _build_snapshot(
        short_temp,
        row_count=10,
        malformed_date=raw_date,
    )

    invalid_rows = [row for row in snapshot.rows if row.feature_date is None]
    assert len(invalid_rows) == 1
    assert invalid_rows[0].raw_date == (
        raw_date.strip() if isinstance(raw_date, str) else ""
    )
    assert snapshot.observed_prefix_contiguous is False
    assert all(rule.state == "unknown" for rule in snapshot.rules)
    assert DailyMarketTechnicalFeatureSnapshotV4.from_json(snapshot.to_json()).to_json() == snapshot.to_json()


def test_duplicate_observed_dates_preserve_distinct_pins_and_rule_references(
    short_temp: Path,
) -> None:
    snapshot = _build_snapshot(
        short_temp,
        row_count=10,
        duplicate_last_date=True,
    )

    assert len(snapshot.rows) == 11
    assert snapshot.session_pins[-1].feature_date == snapshot.session_pins[-2].feature_date
    assert snapshot.session_pins[-1].source_fingerprint_sha256 != snapshot.session_pins[-2].source_fingerprint_sha256
    assert snapshot.observed_prefix_contiguous is False
    restored = DailyMarketTechnicalFeatureSnapshotV4.from_json(snapshot.to_json())
    assert restored.to_json() == snapshot.to_json()


def test_from_json_reuses_the_validated_typed_parts_once_per_decode(
    short_temp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _build_snapshot(short_temp, row_count=10)
    encoded = snapshot.to_json()
    calls = {
        "rows": 0,
        "pins": 0,
        "sessions": 0,
        "rules": 0,
        "session_fingerprints": 0,
    }
    original_row = snapshot_module._row_from_dict
    original_pin = snapshot_module._session_pin_from_dict
    original_session = snapshot_module._session_from_dict
    original_rule = snapshot_module._rule_from_dict
    original_fingerprint = snapshot_module.technical_session_fingerprint_sha256

    def count_row(value: object) -> Any:
        calls["rows"] += 1
        return original_row(value)

    def count_pin(value: object) -> Any:
        calls["pins"] += 1
        return original_pin(value)

    def count_session(value: object) -> Any:
        calls["sessions"] += 1
        return original_session(value)

    def count_rule(value: object) -> Any:
        calls["rules"] += 1
        return original_rule(value)

    def count_fingerprint(value: Any) -> str:
        calls["session_fingerprints"] += 1
        return original_fingerprint(value)

    monkeypatch.setattr(snapshot_module, "_row_from_dict", count_row)
    monkeypatch.setattr(snapshot_module, "_session_pin_from_dict", count_pin)
    monkeypatch.setattr(snapshot_module, "_session_from_dict", count_session)
    monkeypatch.setattr(snapshot_module, "_rule_from_dict", count_rule)
    monkeypatch.setattr(
        snapshot_module,
        "technical_session_fingerprint_sha256",
        count_fingerprint,
    )

    restored = DailyMarketTechnicalFeatureSnapshotV4.from_json(encoded)

    assert calls == {
        "rows": len(snapshot.rows),
        "pins": len(snapshot.session_pins),
        "sessions": len(snapshot.feature_sessions),
        "rules": len(snapshot.rules),
        "session_fingerprints": len(snapshot.feature_sessions),
    }
    assert restored.rows == snapshot.rows
    assert restored.session_pins == snapshot.session_pins
    assert restored.feature_sessions == snapshot.feature_sessions
    assert tuple(item.to_dict() for item in restored.rules) == tuple(
        item.to_dict() for item in snapshot.rules
    )
    assert restored.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256


def test_fresh_from_json_rejects_changed_session_after_valid_decode(
    short_temp: Path,
) -> None:
    encoded = _build_snapshot(short_temp, row_count=10).to_json()
    restored = DailyMarketTechnicalFeatureSnapshotV4.from_json(encoded)
    assert restored.snapshot_identity_sha256

    payload = json.loads(encoded)
    payload["feature_sessions"][-1]["features"][0]["value"] = "123456"
    _refresh_snapshot_identity(payload)
    tampered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    with pytest.raises(
        ValueError,
        match="technical_snapshot_v4_session_fingerprint_mismatch",
    ):
        DailyMarketTechnicalFeatureSnapshotV4.from_json(tampered)


def test_snapshot_cold_reopen_in_new_process_keeps_canonical_bytes(
    short_temp: Path,
) -> None:
    encoded = _build_snapshot(short_temp, row_count=10).to_json()
    script = "\n".join((
        "import sys",
        "from app_module.daily_market_technical_feature_snapshot_v4 import DailyMarketTechnicalFeatureSnapshotV4",
        "snapshot = DailyMarketTechnicalFeatureSnapshotV4.from_json(sys.stdin.buffer.read().decode('utf-8'))",
        "sys.stdout.buffer.write(snapshot.to_json().encode('utf-8'))",
    ))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        input=encoded.encode("utf-8"),
        capture_output=True,
        cwd=Path(__file__).resolve().parents[1],
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == encoded.encode("utf-8")
