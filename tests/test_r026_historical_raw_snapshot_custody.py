from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
import sqlite3
from pathlib import Path

import pytest

from app_module.recommendation.historical_snapshot_custody import (
    HistoricalRawSnapshotQueryScopeV1,
    build_historical_raw_snapshot_custody_facts_v1,
)
from data_module.ml_historical_snapshot_provider import (
    HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
    HistoricalRawSnapshot,
    MLHistoricalSnapshotProvider,
)
from ml_module.prepared_input_contract import (
    AvailabilityStatus,
    SnapshotQualityStatus,
    SnapshotScopeStatus,
)


def _database(path: Path, *, extra_column: bool = False) -> None:
    connection = sqlite3.connect(path)
    extra = ", auxiliary TEXT" if extra_column else ""
    connection.executescript(
        f"""
        CREATE TABLE daily_prices (
            日期 TEXT, 證券代號 TEXT, 成交股數 INTEGER, 成交金額 INTEGER,
            開盤價 REAL, 最高價 REAL, 最低價 REAL, 收盤價 REAL{extra}
        );
        CREATE TABLE technical_indicators (
            日期 TEXT, 證券代號 TEXT, RSI REAL, MACD REAL, ADX REAL
        );
        CREATE TABLE market_indices (日期 TEXT, 收盤指數 REAL, 收盤價 REAL);
        CREATE TABLE industry_indices (日期 TEXT, 指數名稱 TEXT, 收盤指數 REAL);
        """
    )
    connection.executemany(
        "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?"
        + (", ?" if extra_column else "")
        + ")",
        [
            ("20240102", "2330", 100, 1000, 10, 11, 9, 10)
            + (("same-schema",) if extra_column else ()),
            ("20240103", "2330", 110, 1210, 10, 12, 10, 11)
            + (("same-schema",) if extra_column else ()),
            ("20240102", "2317", 200, 2000, 20, 21, 19, 20)
            + (("same-schema",) if extra_column else ()),
            ("20240103", "2317", 220, 2420, 20, 22, 20, 21)
            + (("same-schema",) if extra_column else ()),
        ],
    )
    connection.executemany(
        "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)",
        [
            (day, symbol, 55, 0.1, 20)
            for day in ("20240102", "20240103")
            for symbol in ("2330", "2317")
        ],
    )
    connection.executemany(
        "INSERT INTO market_indices VALUES (?, ?, ?)",
        [("20240102", None, 100), ("20240103", None, 102)],
    )
    connection.executemany(
        "INSERT INTO industry_indices VALUES (?, ?, ?)",
        [
            (day, "半導體類指數", value)
            for day, value in (("20240102", 200), ("20240103", 204))
        ],
    )
    connection.commit()
    connection.close()


def _load(
    database: Path,
    *,
    history_start_date: str = "2024-01-01",
    symbols: tuple[str, ...] = ("2317", "2330"),
) -> HistoricalRawSnapshot:
    return MLHistoricalSnapshotProvider(database).load(
        decision_date="2024-01-04",
        history_start_date=history_start_date,
        symbols=symbols,
        industry_index_names=("半導體類指數",),
    )


def _scope(
    *,
    history_start_date: date = date(2024, 1, 1),
    symbols: tuple[str, ...] = ("2317", "2330"),
    source_id: str = HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1,
) -> HistoricalRawSnapshotQueryScopeV1:
    return HistoricalRawSnapshotQueryScopeV1(
        source_id=source_id,
        decision_date=date(2024, 1, 4),
        history_start_date=history_start_date,
        symbols=symbols,
        industry_index_names=("半導體類指數",),
    )


def _facts(snapshot: HistoricalRawSnapshot, scope: HistoricalRawSnapshotQueryScopeV1):
    return build_historical_raw_snapshot_custody_facts_v1(
        snapshot=snapshot,
        query_scope=scope,
    )


def test_provider_captures_same_call_validated_schema_without_changing_load_abi(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)

    snapshot = _load(database)
    repeated = _load(database)

    assert type(snapshot) is HistoricalRawSnapshot
    assert snapshot.query_count == 5
    assert snapshot.validated_schema is not None
    schema = snapshot.validated_schema
    assert snapshot.validated_schema == repeated.validated_schema
    assert schema.table_columns[0] == (
        "daily_prices",
        ("日期", "證券代號", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"),
    )
    assert schema.schema_version.startswith(
        "historical-sqlite-schema.v1:sha256:"
    )
    assert snapshot.source_fingerprint.startswith("sha256:")


def test_raw_custody_facts_are_stable_and_reference_stays_explicitly_unknown(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)

    facts = _facts(snapshot, _scope())
    same = _facts(snapshot, _scope())
    reference = facts.to_snapshot_reference()
    assert snapshot.validated_schema is not None
    schema = snapshot.validated_schema

    assert facts == same
    assert facts.row_count == 12
    assert facts.table_row_counts == (
        ("daily_prices", 4),
        ("technical_indicators", 4),
        ("market_indices", 2),
        ("industry_indices", 2),
    )
    assert facts.row_range_start == date(2024, 1, 2)
    assert facts.row_range_end == date(2024, 1, 3)
    assert reference.snapshot_id == facts.snapshot_id
    assert reference.source_id == HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1
    assert reference.kind.value == "bounded"
    assert reference.dataset_id is None
    assert reference.schema_version == schema.schema_version
    assert reference.source_revision is None
    assert reference.availability.status is AvailabilityStatus.UNKNOWN
    assert reference.quality_status is SnapshotQualityStatus.UNKNOWN
    assert reference.missing_inputs == ()
    assert reference.scope_status is SnapshotScopeStatus.UNKNOWN
    assert facts.validated_schema_version == (
        "historical-sqlite-schema.v1:sha256:"
        "9b237aec08147e1e613746e0db232fc8d9c7fc2849c735031accf948b6ceec3f"
    )
    assert facts.content_hash == (
        "sha256:b9d243446ad5dc4d7ca532cf433376d308fe91a1df07cc52ec153c9dbbe07d5e"
    )
    assert facts.row_identity_hash == (
        "sha256:55861b7de16eeaad327852170bba46265996d48bf3d9dc530b361f68d72f7a24"
    )
    assert facts.snapshot_id == (
        "historical-raw-snapshot-custody.v1:sha256:"
        "4c47f6dc64e8a53e5dca5ec88f1985a327c06c260637215164ef9106ecbc804d"
    )

    with pytest.raises(FrozenInstanceError):
        facts.query_scope.source_id = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        schema.schema_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(TypeError):
        facts.query_scope.symbols[0] = "9999"  # type: ignore[index]


def test_value_only_change_changes_content_and_snapshot_but_not_row_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    original = _facts(snapshot, _scope())
    changed_row = replace(snapshot.prices[0], close_price=Decimal("10.25"))
    changed = _facts(replace(snapshot, prices=(changed_row, *snapshot.prices[1:])), _scope())

    assert changed.content_hash != original.content_hash
    assert changed.snapshot_id != original.snapshot_id
    assert changed.row_identity_hash == original.row_identity_hash


def test_row_key_only_change_changes_content_identity_and_snapshot(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    # Keep the same captured scope; the exact row key remains in the request.
    facts_scope = _scope()
    original = _facts(snapshot, facts_scope)
    changed_row = replace(snapshot.prices[0], symbol="2330")
    changed_rows = (changed_row, *snapshot.prices[1:])
    changed = _facts(replace(snapshot, prices=changed_rows), facts_scope)

    assert changed.content_hash != original.content_hash
    assert changed.row_identity_hash != original.row_identity_hash
    assert changed.snapshot_id != original.snapshot_id


def test_value_assignment_swap_changes_content_but_preserves_row_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    original = _facts(snapshot, _scope())

    first = snapshot.prices[0]
    second = snapshot.prices[2]
    swapped_rows = list(snapshot.prices)
    swapped_rows[0] = replace(first, close_price=second.close_price)
    swapped_rows[2] = replace(second, close_price=first.close_price)
    swapped = _facts(replace(snapshot, prices=tuple(swapped_rows)), _scope())

    assert swapped.content_hash != original.content_hash
    assert swapped.row_identity_hash == original.row_identity_hash
    assert swapped.snapshot_id != original.snapshot_id


def test_row_order_is_canonical_and_duplicate_rows_remain_counted(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    original = _facts(snapshot, _scope())
    reordered = _facts(
        replace(
            snapshot,
            prices=tuple(reversed(snapshot.prices)),
            technicals=tuple(reversed(snapshot.technicals)),
            market=tuple(reversed(snapshot.market)),
            industries=tuple(reversed(snapshot.industries)),
        ),
        _scope(),
    )
    duplicate = _facts(
        replace(snapshot, prices=(*snapshot.prices, snapshot.prices[0])),
        _scope(),
    )

    assert reordered == original
    assert duplicate.row_count == original.row_count + 1
    assert duplicate.content_hash != original.content_hash
    assert duplicate.row_identity_hash != original.row_identity_hash
    assert duplicate.snapshot_id != original.snapshot_id


def test_schema_version_comes_from_same_call_columns_not_file_fingerprint(
    tmp_path: Path,
) -> None:
    base_db = tmp_path / "base.db"
    expanded_db = tmp_path / "expanded.db"
    _database(base_db)
    _database(expanded_db, extra_column=True)

    base = _load(base_db)
    expanded = _load(expanded_db)
    base_facts = _facts(base, _scope())
    expanded_facts = _facts(expanded, _scope())

    assert base.prices == expanded.prices
    assert base_facts.validated_schema_version != expanded_facts.validated_schema_version
    assert base_facts.content_hash == expanded_facts.content_hash
    assert base_facts.row_identity_hash == expanded_facts.row_identity_hash
    assert base_facts.snapshot_id != expanded_facts.snapshot_id


def test_empty_rows_and_different_query_scope_have_distinct_snapshot_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    # The provider still observes a T-1 cutoff, while the requested history
    # range begins after that cutoff and returns no rows.
    empty = _load(database, history_start_date="2024-01-10")
    other_empty = _load(
        database,
        history_start_date="2024-01-10",
        symbols=("2317", "2330", "9999"),
    )
    first = _facts(
        empty,
        _scope(history_start_date=date(2024, 1, 10), symbols=("2317", "2330")),
    )
    other_scope = _facts(
        other_empty,
        _scope(history_start_date=date(2024, 1, 10), symbols=("2317", "2330", "9999")),
    )

    assert first.row_count == 0
    assert first.row_range_start is None
    assert first.row_range_end is None
    assert first.content_hash == other_scope.content_hash
    assert first.row_identity_hash == other_scope.row_identity_hash
    assert first.snapshot_id != other_scope.snapshot_id
    assert first.to_snapshot_reference().row_range is None


def test_fact_builder_rejects_source_id_not_carried_by_provider(tmp_path: Path) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    with pytest.raises(ValueError, match="source ID does not match provider"):
        _facts(snapshot, replace(_scope(), source_id="twstock.research.shadow"))


def test_provider_contract_id_is_kw_only_non_identity_abi(tmp_path: Path) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)
    no_contract_id = replace(snapshot, provider_contract_id=None)

    assert snapshot.provider_contract_id == HISTORICAL_SNAPSHOT_PROVIDER_CONTRACT_ID_V1
    assert no_contract_id == snapshot
    assert repr(snapshot) == repr(no_contract_id)
    with pytest.raises(ValueError, match="provider-carried"):
        _facts(no_contract_id, _scope())


def test_fact_builder_rejects_unvalidated_schema_future_rows_and_scope_mismatch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)

    with pytest.raises(ValueError, match="validated schema"):
        _facts(replace(snapshot, validated_schema=None), _scope())
    with pytest.raises(ValueError, match="scope|decision"):
        _facts(snapshot, replace(_scope(), decision_date=date(2024, 1, 5)))
    with pytest.raises(ValueError, match="same-call provider request"):
        _facts(snapshot, replace(_scope(), symbols=("2317",)))

    future_row = replace(snapshot.prices[-1], trading_date="2024-01-04")
    with pytest.raises(ValueError, match="cutoff|decision|future"):
        _facts(replace(snapshot, prices=(*snapshot.prices[:-1], future_row)), _scope())


def test_fact_builder_does_not_reopen_or_requery_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "history.db"
    _database(database)
    snapshot = _load(database)

    def forbidden_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        raise AssertionError("custody builder must not reopen SQLite")

    monkeypatch.setattr(sqlite3, "connect", forbidden_connect)
    facts = _facts(snapshot, _scope())

    assert facts.row_count == 12


def test_sidecar_file_changes_are_not_inputs_to_raw_row_custody(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history.db"
    sidecar = tmp_path / "validated-sidecar.json"
    _database(database)
    snapshot = _load(database)
    scope = _scope()

    sidecar.write_text('{"digest":"one"}', encoding="utf-8")
    before = _facts(snapshot, scope)
    sidecar.write_text('{"digest":"two"}', encoding="utf-8")
    after = _facts(snapshot, scope)

    assert before == after
    assert before.content_hash == after.content_hash
    assert before.row_identity_hash == after.row_identity_hash
