"""隔離短 TEMP 中驗證每日技術來源 adapter 的因果與 lineage 契約。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_read_session as read_session_adapter
import app_module.daily_market_technical_source as source_adapter
import analysis_module.technical_analysis.technical_indicators as technical_indicators
from app_module.daily_market_technical_source import (
    DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
    DailyMarketTechnicalSourceError,
    load_daily_market_technical_window,
)
from decision_module.factors.selection_technical_rules import (
    TECHNICAL_SOURCE_ID,
    TechnicalFeatureEvidence,
    TechnicalObservedSession,
    evaluate_daily_technical_rules,
    technical_observation_window_fingerprint_sha256,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _short_temp() -> tempfile.TemporaryDirectory[str]:
    """用 repository 下的短暫路徑避免 Windows SQLite 長路徑問題。"""

    repository_root = Path(__file__).resolve().parents[1]
    return tempfile.TemporaryDirectory(prefix=".t-", dir=repository_root)


def _write_source(
    path: Path,
    rows: list[tuple[date, str, str | None, str | None, str | None, str | None, int | str | None]],
    *,
    legacy_rows: bool = False,
) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
            )
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        day.isoformat(), code, open_price, high, low, close, volume
                    )
                    for day, code, open_price, high, low, close, volume in rows
                ],
            )
            if legacy_rows:
                connection.execute(
                    "CREATE TABLE technical_indicators ("
                    "日期 TEXT, 證券代號 TEXT, MA5 TEXT, MA20 TEXT, slowk TEXT, slowd TEXT, MACD TEXT, MACD_signal TEXT)"
                )
                connection.executemany(
                    "INSERT INTO technical_indicators VALUES (?,?,?,?,?,?,?,?)",
                    [
                        (day.isoformat(), code, "999", "1", "2", "98", "-50", "50")
                        for day, code, *_rest in rows
                    ],
                )
    finally:
        connection.close()


def _write_source_with_raw_dates(
    path: Path,
    rows: list[
        tuple[object, str, str | None, str | None, str | None, str | None, int | str | None]
    ],
) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, 收盤價 TEXT, 成交股數 INTEGER)"
            )
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _ohlcv_rows(
    count: int,
    *,
    stock_code: str = "2382",
    start: date = date(2026, 8, 1),
    close_values: list[int] | None = None,
) -> list[tuple[date, str, str | None, str | None, str | None, str | None, int | str | None]]:
    closes = close_values or [100] * count
    assert len(closes) == count
    result: list[
        tuple[date, str, str | None, str | None, str | None, str | None, int | str | None]
    ] = []
    for offset, close_int in enumerate(closes):
        close = Decimal(close_int)
        result.append((
            start + timedelta(days=offset),
            stock_code,
            str(close),
            str(close + Decimal("1")),
            str(close - Decimal("1")),
            str(close),
            1_000 + offset,
        ))
    return result


def _cutoff(day: date) -> datetime:
    return datetime.combine(day, time(16, 0), tzinfo=_TAIPEI)


def test_aware_source_dates_normalize_to_taipei_but_naive_dates_stay_local() -> None:
    assert source_adapter._parse_date(
        datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
    ) == date(2026, 8, 1)
    assert source_adapter._parse_date("2026-07-31T20:00:00Z") == date(2026, 8, 1)
    assert source_adapter._parse_date("2026-08-01T04:00:00+08:00") == date(2026, 8, 1)

    assert source_adapter._parse_date(datetime(2026, 7, 31, 20, 0)) == date(2026, 7, 31)
    assert source_adapter._parse_date("2026-07-31T20:00:00") == date(2026, 7, 31)
    assert source_adapter._parse_date("2026-08-01junk") is None


def _rule(window, key: str):
    return next(item for item in window.evaluate() if item.key == key)


def _write_frozen_bundle_contract_fixture(
    bundle_root: Path,
    *,
    channel: str = "release",
    dirty: bool = False,
) -> dict[str, Path]:
    """建立合成 frozen bundle，只驗契約，不代表實際 exe 驗證。"""

    kernel_sources = {
        "analysis_module/technical_analysis/technical_indicators.py": b"fixture technical kernel source\n",
        "analysis_module/technical_analysis/indicator_kernels.py": b"fixture helper kernel source\n",
    }
    for relative_path, content in kernel_sources.items():
        path = bundle_root / Path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    icon_path = bundle_root / "ui_qt" / "app_icon.png"
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_bytes(b"fixture icon bytes")
    lock_path = bundle_root / "packaging" / "windows-dependencies.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_bytes(b"fixture dependency lock\n")

    resource_paths = [*kernel_sources, "ui_qt/app_icon.png"]
    resources = {
        relative_path: hashlib.sha256((bundle_root / Path(relative_path)).read_bytes()).hexdigest()
        for relative_path in resource_paths
    }
    commit = "1234567890abcdef1234567890abcdef12345678"
    metadata = {
        "schema": "baldr-application-build.v1",
        "version": f"2026.10.06+{commit[:12]}",
        "source_commit": commit,
        "channel": channel,
        "dirty": dirty,
        "dependency_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "resource_sha256": resources,
    }
    metadata_path = bundle_root / "application_build.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return {
        "metadata": metadata_path,
        **{
            relative_path.rsplit("/", maxsplit=1)[-1]: bundle_root / Path(relative_path)
            for relative_path in kernel_sources
        },
    }


def _set_frozen_bundle(monkeypatch: pytest.MonkeyPatch, bundle_root: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)


def test_source_calculation_identity_keeps_inspect_source_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    identity, version, talib_version = source_adapter._calculation_identity()

    assert len(identity) == 64
    assert version == source_adapter.CAUSAL_INDICATOR_LINEAGE_VERSION
    assert talib_version


@pytest.mark.parametrize(
    ("hour", "minute"),
    ((9, 0), (15, 59)),
    ids=("morning", "before-cutoff"),
)
def test_intraday_cutoff_is_rejected_before_source_access(
    monkeypatch: pytest.MonkeyPatch,
    hour: int,
    minute: int,
) -> None:
    def unexpected_access(*_args, **_kwargs):
        pytest.fail("cutoff guard must run before source access or calculation")

    monkeypatch.setattr(source_adapter, "_source_pin", unexpected_access)
    monkeypatch.setattr(read_session_adapter, "connect_read_only_sqlite", unexpected_access)
    monkeypatch.setattr(source_adapter, "_calculation_identity", unexpected_access)
    cutoff = datetime.combine(date(2026, 8, 1), time(hour, minute), tzinfo=_TAIPEI)

    with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
        load_daily_market_technical_window(
            Path("missing-daily-prices.sqlite"), "2382", cutoff
        )

    assert error_info.value.code == "daily_technical_requires_after_close_cutoff"


def test_frozen_calculation_identity_uses_verified_bundle_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _short_temp() as root_text:
        bundle_root = Path(root_text) / "bundle"
        paths = _write_frozen_bundle_contract_fixture(bundle_root)
        _set_frozen_bundle(monkeypatch, bundle_root)
        monkeypatch.setattr(
            source_adapter,
            "inspect",
            SimpleNamespace(
                getfile=lambda _value: pytest.fail(
                    "frozen mode must not inspect or fall back to source files"
                )
            ),
        )

        hashes = source_adapter._frozen_calculation_source_hashes()
        calculation_identity = source_adapter._calculation_identity()
        expected_hashes = (
            hashlib.sha256(paths["technical_indicators.py"].read_bytes()).hexdigest(),
            hashlib.sha256(paths["indicator_kernels.py"].read_bytes()).hexdigest(),
        )

    assert hashes == expected_hashes
    assert len(calculation_identity[0]) == 64
    assert calculation_identity[1] == source_adapter.CAUSAL_INDICATOR_LINEAGE_VERSION


def test_frozen_calculation_identity_rejects_missing_meipass_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(
        source_adapter,
        "inspect",
        SimpleNamespace(
            getfile=lambda _value: pytest.fail(
                "missing _MEIPASS must not fall back to inspect.getfile"
            )
        ),
    )

    with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
        source_adapter._calculation_identity()

    assert error_info.value.code == "daily_technical_frozen_root_unavailable"


def test_frozen_calculation_identity_rejects_missing_build_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _short_temp() as root_text:
        bundle_root = Path(root_text) / "bundle"
        paths = _write_frozen_bundle_contract_fixture(bundle_root)
        paths["metadata"].unlink()
        _set_frozen_bundle(monkeypatch, bundle_root)

        with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
            source_adapter._calculation_identity()

    assert error_info.value.code == "daily_technical_frozen_build_identity_unverified"


@pytest.mark.parametrize(
    "missing_resource",
    (
        "analysis_module/technical_analysis/technical_indicators.py",
        "analysis_module/technical_analysis/indicator_kernels.py",
    ),
)
def test_frozen_calculation_identity_rejects_missing_kernel_manifest_key(
    monkeypatch: pytest.MonkeyPatch,
    missing_resource: str,
) -> None:
    with _short_temp() as root_text:
        bundle_root = Path(root_text) / "bundle"
        paths = _write_frozen_bundle_contract_fixture(bundle_root)
        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        del metadata["resource_sha256"][missing_resource]
        paths["metadata"].write_text(json.dumps(metadata), encoding="utf-8")
        _set_frozen_bundle(monkeypatch, bundle_root)

        with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
            source_adapter._calculation_identity()

    assert error_info.value.code == "daily_technical_frozen_kernel_hash_missing"


def test_frozen_calculation_identity_rejects_tampered_kernel_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _short_temp() as root_text:
        bundle_root = Path(root_text) / "bundle"
        paths = _write_frozen_bundle_contract_fixture(bundle_root)
        paths["indicator_kernels.py"].write_bytes(b"tampered helper kernel source\n")
        _set_frozen_bundle(monkeypatch, bundle_root)

        with pytest.raises(DailyMarketTechnicalSourceError):
            source_adapter._calculation_identity()


@pytest.mark.parametrize(
    ("channel", "dirty"),
    (("development", False), ("release", True)),
    ids=("non-release", "dirty-release"),
)
def test_frozen_calculation_identity_rejects_unverified_release_state(
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
    dirty: bool,
) -> None:
    with _short_temp() as root_text:
        bundle_root = Path(root_text) / "bundle"
        _write_frozen_bundle_contract_fixture(bundle_root, channel=channel, dirty=dirty)
        _set_frozen_bundle(monkeypatch, bundle_root)

        with pytest.raises(DailyMarketTechnicalSourceError) as error_info:
            source_adapter._calculation_identity()

    assert error_info.value.code == "daily_technical_frozen_build_identity_unverified"


@pytest.mark.parametrize(
    "configured_output_root",
    ("caller-owned-output", None),
    ids=("configured", "unset"),
)
def test_causal_kernel_observes_unchanged_process_output_root(
    monkeypatch: pytest.MonkeyPatch,
    configured_output_root: str | None,
) -> None:
    if configured_output_root is None:
        monkeypatch.delenv("OUTPUT_ROOT", raising=False)
    else:
        monkeypatch.setenv("OUTPUT_ROOT", configured_output_root)
    expected_output_root = os.environ.get("OUTPUT_ROOT")
    frame = object()
    marker = object()
    observed: list[tuple[object, str | None]] = []

    def kernel_during_call(received_frame: object) -> object:
        observed.append((received_frame, os.environ.get("OUTPUT_ROOT")))
        return marker

    monkeypatch.setattr(
        technical_indicators,
        "calculate_causal_indicators",
        kernel_during_call,
    )

    result = source_adapter._run_causal_calculation(frame)

    assert result is marker
    assert observed == [(frame, expected_output_root)]
    assert os.environ.get("OUTPUT_ROOT") == expected_output_root


@pytest.mark.parametrize(
    "use_utc_cutoff",
    (False, True),
    ids=("taipei-1600", "utc-converts-to-taipei-1600"),
)
def test_source_uses_pinned_readonly_ohlcv_and_emits_ma_cross_with_unknown_availability(
    use_utc_cutoff: bool,
) -> None:
    # 最後一日讓 MA5 在前四個下跌交易日後上穿 MA20。
    closes = [100] * 35 + [50, 50, 50, 50, 500]
    rows = _ohlcv_rows(len(closes), close_values=closes)
    decision_date = rows[-1][0]
    future = _ohlcv_rows(1, start=decision_date + timedelta(days=1), close_values=[900])[0]
    with _short_temp() as root_text:
        root = Path(root_text)
        db = root / "m.db"
        _write_source(db, [*rows, future], legacy_rows=True)
        before = db.read_bytes()
        cutoff = _cutoff(decision_date)
        if use_utc_cutoff:
            cutoff = cutoff.astimezone(timezone.utc)

        window = load_daily_market_technical_window(db, "2382", cutoff)

        assert db.read_bytes() == before
        assert len(window.rows) == len(rows)
        assert window.rows[-1].feature_date == decision_date
        assert window.decision_date == decision_date
        assert window.decision_cutoff == cutoff
        assert window.source_id == "sqlite.daily_prices"
        assert window.source_identity.startswith(f"{TECHNICAL_SOURCE_ID}:")
        assert window.schema_identity_sha256
        assert window.source_pin_sha256
        assert window.raw_source_window_fingerprint_sha256
        assert window.source_window_fingerprint_sha256 == window.observation_window.source_window_fingerprint_sha256
        assert window.availability_status == "unknown"
        assert window.source_available_at is None
        assert window.evaluate()[0].pit_eligible is False

        current = next(feature for feature in window.sessions[-1].features if feature.key == "MA5")
        assert current.source_id == TECHNICAL_SOURCE_ID
        assert current.method_id.endswith("calculate_causal_indicators")
        assert current.lineage_verified is True
        assert current.value is not None and isinstance(current.value, Decimal)
        assert current.warmup_required_sessions == 5
        assert current.warmup_observed_sessions == len(rows)

        ma_cross = _rule(window, "ma5_20_golden_cross")
        assert ma_cross.state == "match"
        assert ma_cross.feature_date == decision_date
        assert ma_cross.previous_feature_date == rows[-2][0]
        assert ma_cross.availability_result == "available_at_unknown"
        assert ma_cross.pit_eligible is False
        assert {fact.feature_date for fact in ma_cross.raw_facts} == {rows[-2][0], decision_date}
        serialized = json.dumps(window.to_dict(), ensure_ascii=False, sort_keys=True)
        assert all(row.close_price != Decimal("999") for row in window.rows)
        assert all(row.feature_date != future[0] for row in window.rows)
        assert "float" not in serialized.lower()


def test_window_is_bounded_and_reports_20_and_34_session_warmup() -> None:
    rows = _ohlcv_rows(DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS + 5)
    decision_date = rows[-1][0]
    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source(db, rows)
        window = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))

    assert len(window.rows) == DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
    latest_features = {item.key: item for item in window.sessions[-1].features}
    assert latest_features["MA20"].warmup_required_sessions == 20
    assert latest_features["MA20"].warmup_observed_sessions == DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
    assert latest_features["MACD"].warmup_required_sessions == 34
    assert latest_features["MACD"].warmup_observed_sessions == DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
    assert latest_features["MACD"].value is not None
    assert latest_features["MACD_signal"].value is not None


def test_invalid_ohlc_breaks_warmup_without_dropping_the_source_row() -> None:
    rows = _ohlcv_rows(40)
    damaged = list(rows[10])
    damaged[3] = None  # 保留來源列，但中斷因果 OHLC 區段。
    rows[10] = tuple(damaged)  # type: ignore[assignment]
    missing_volume = list(rows[-10])
    missing_volume[6] = None
    rows[-10] = tuple(missing_volume)  # type: ignore[assignment]
    decision_date = rows[-1][0]
    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source(db, rows)
        window = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))

    assert len(window.rows) == 40
    assert window.rows[10].feature_date == rows[10][0]
    assert window.rows[10].ohlc_valid is False
    assert window.rows[10].invalid_reasons
    assert window.observed_prefix_contiguous is True  # 缺口後的尾段仍連續。
    assert len(window.sessions) == len(rows) - 11
    # 缺口後前一日只有 28 列有效資料，當日有 29 列；34 日 MACD 暖機不能跨越缺口。
    macd = _rule(window, "macd_golden_cross")
    assert macd.state == "unknown"
    assert any("feature_not_observed" in item for item in macd.unknown_reasons)
    previous_macd = next(
        fact.evidence for fact in macd.raw_facts
        if fact.feature_date == rows[-2][0] and fact.evidence.key == "MACD"
    )
    assert previous_macd.warmup_observed_sessions == 28
    volume20 = _rule(window, "volume_ratio_20_including_current")
    assert volume20.state == "unknown"
    assert any("feature_not_observed" in item for item in volume20.unknown_reasons)


def test_duplicate_dates_are_preserved_and_all_crosses_fail_closed() -> None:
    rows = _ohlcv_rows(40)
    rows[22] = rows[21]
    decision_date = rows[-1][0]
    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source(db, rows)
        window = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))

    assert len(window.rows) == 40
    assert len(window.sessions) == 40
    assert window.observed_prefix_contiguous is False
    for result in window.evaluate()[:3]:
        assert result.state == "unknown"
        assert "observed_sessions_not_unique_ascending" in result.unknown_reasons


def test_legacy_technical_table_without_lineage_is_ignored_and_leaf_rejects_it() -> None:
    rows = _ohlcv_rows(40, close_values=[100] * 35 + [50, 50, 50, 50, 500])
    decision_date = rows[-1][0]
    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source(db, rows, legacy_rows=True)
        window = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))

    current = window.sessions[-1]
    old_table_feature = next(item for item in current.features if item.key == "MA5")
    downgraded = replace(
        old_table_feature,
        source_id="sqlite.technical_indicators",
        lineage_verified=False,
    )
    changed_current = replace(
        current,
        features=tuple(downgraded if item.key == "MA5" else item for item in current.features),
    )
    changed_sessions = (*window.sessions[:-1], changed_current)
    changed_fingerprint = technical_observation_window_fingerprint_sha256(
        stock_code=window.stock_code,
        decision_date=window.decision_date,
        source_identity=window.source_identity,
        sessions=changed_sessions,
    )
    changed_window = replace(
        window.observation_window,
        sessions=changed_sessions,
        source_window_fingerprint_sha256=changed_fingerprint,
    )
    result = next(
        item for item in evaluate_daily_technical_rules(changed_window)
        if item.key == "ma5_20_golden_cross"
    )

    assert window.evaluate()[0].state == "match"
    assert result.state == "unknown"
    assert any("feature_lineage_unverified" in item for item in result.unknown_reasons)
    assert all(
        feature.source_id != "sqlite.technical_indicators"
        for session in window.sessions
        for feature in session.features
    )


def test_exact_raw_window_fingerprint_changes_with_any_source_value() -> None:
    rows = _ohlcv_rows(40)
    decision_date = rows[-1][0]
    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source(db, rows)
        first = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))
        connection = sqlite3.connect(db)
        try:
            with connection:
                connection.execute(
                    "UPDATE daily_prices SET 收盤價='101.25' WHERE 日期=? AND 證券代號='2382'",
                    (rows[4][0].isoformat(),),
                )
        finally:
            connection.close()
        second = load_daily_market_technical_window(db, "2382", _cutoff(decision_date))

    assert first.raw_source_window_fingerprint_sha256 != second.raw_source_window_fingerprint_sha256
    assert first.source_identity != second.source_identity
    first_row = next(row for row in first.rows if row.feature_date == rows[4][0])
    second_row = next(row for row in second.rows if row.feature_date == rows[4][0])
    assert first_row.row_fingerprint_sha256 != second_row.row_fingerprint_sha256
    assert first.sessions[4].source_fingerprint_sha256 != second.sessions[4].source_fingerprint_sha256
    expected = hashlib.sha256(json.dumps({
        "schema_version": "daily-market-technical-source.v1",
        "schema_identity_sha256": first.schema_identity_sha256,
        "stock_code": first.stock_code,
        "decision_date": first.decision_date.isoformat(),
        "decision_cutoff": first.decision_cutoff.isoformat(),
        "cutoff_guard_version": source_adapter.DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        "rows": [row.to_dict() for row in first.rows],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert first.raw_source_window_fingerprint_sha256 == expected


@pytest.mark.parametrize(
    "bad_date",
    (None, "", "not-a-date", "2026-08-01junk"),
    ids=("null", "empty", "invalid", "partial-invalid"),
)
def test_unknown_source_dates_are_retained_and_future_rows_are_excluded(
    bad_date: object,
) -> None:
    valid_rows = _ohlcv_rows(40)
    cutoff_date = valid_rows[-1][0]
    future_row = _ohlcv_rows(1, start=cutoff_date + timedelta(days=1))[0]
    raw_rows: list[
        tuple[object, str, str | None, str | None, str | None, str | None, int | str | None]
    ] = [
        (row[0].isoformat(), row[1], row[2], row[3], row[4], row[5], row[6])
        for row in valid_rows
    ]
    raw_rows.append((bad_date, *valid_rows[-1][1:]))
    raw_rows.append((
        future_row[0].isoformat(), future_row[1], future_row[2], future_row[3],
        future_row[4], future_row[5], future_row[6],
    ))

    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source_with_raw_dates(db, raw_rows)
        before_bytes = db.read_bytes()
        source_path = db.resolve()
        before_pin = source_adapter._source_pin(source_path)
        assert before_pin is not None

        window = load_daily_market_technical_window(db, "2382", _cutoff(cutoff_date))

        assert db.read_bytes() == before_bytes
        assert source_adapter._source_pin(source_path) == before_pin

    invalid_rows = [row for row in window.rows if row.feature_date is None]
    assert len(window.rows) == len(valid_rows) + 1
    assert len(window.rows) <= DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS
    assert len(invalid_rows) == 1
    assert "source_date_invalid" in invalid_rows[0].invalid_reasons
    assert window.observed_prefix_contiguous is False
    assert window.source_file_pin == before_pin
    assert window.availability_status == "unknown"
    assert window.source_available_at is None
    assert all(result.state == "unknown" for result in window.evaluate())
    assert all(row.feature_date != future_row[0] for row in window.rows)
    serialized = json.loads(json.dumps(window.to_dict(), ensure_ascii=False))
    invalid_payload = next(
        row for row in serialized["rows"] if row["feature_date"] is None
    )
    assert invalid_payload["raw_values"]["date"] == source_adapter._raw_token(bad_date)


def test_utc_timestamp_after_taipei_cutoff_day_is_excluded_and_raw_token_is_preserved() -> None:
    same_day_token = "2026-07-31T04:00:00Z"
    future_taipei_token = "2026-07-31T20:00:00Z"
    raw_rows: list[
        tuple[object, str, str | None, str | None, str | None, str | None, int | str | None]
    ] = [
        ("2026-07-30", "2382", "100", "101", "99", "100", 1000),
        (same_day_token, "2382", "101", "102", "100", "101", 1100),
        (future_taipei_token, "2382", "102", "103", "101", "102", 1200),
    ]

    with _short_temp() as root_text:
        db = Path(root_text) / "m.db"
        _write_source_with_raw_dates(db, raw_rows)
        before_bytes = db.read_bytes()
        source_path = db.resolve()
        before_pin = source_adapter._source_pin(source_path)
        assert before_pin is not None

        window = load_daily_market_technical_window(db, "2382", _cutoff(date(2026, 7, 31)))

        assert db.read_bytes() == before_bytes
        assert source_adapter._source_pin(source_path) == before_pin

    assert [row.feature_date for row in window.rows] == [date(2026, 7, 30), date(2026, 7, 31)]
    serialized = json.loads(json.dumps(window.to_dict(), ensure_ascii=False))
    same_day_row = next(row for row in serialized["rows"] if row["feature_date"] == "2026-07-31")
    assert same_day_row["raw_values"]["date"] == source_adapter._raw_token(same_day_token)
    assert all(row["raw_values"]["date"] != source_adapter._raw_token(future_taipei_token) for row in serialized["rows"])
    assert window.availability_status == "unknown"
    assert window.source_available_at is None
