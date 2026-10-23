from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.forward_daily_price_source_binding import (
    PRICE_PROJECTION_COLUMNS,
    ForwardDailyPriceSourceBinder,
    unknown_price_source_binding,
)
from app_module.forward_performance_service import ForwardPerformanceService


SOURCE_TWSE = "twse.mi_index.daily_price"
SOURCE_TPEX = "tpex.daily_close_quotes"


def _captured_bundle(tmp_path: Path, *source_ids: str) -> dict[str, object]:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    database = data / "market.sqlite3"
    database.write_bytes(b"fixture")
    info = database.stat()
    return {
        "status": "captured",
        "reference": {"manifest_path": "fixtures/source-bundle.json"},
        "descriptors": {source_id: {"source_id": source_id} for source_id in source_ids},
        "bundle": {"database_identity": {"device": info.st_dev, "inode": info.st_ino}},
    }


def _identity_result(source_id: str, **overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "source_identity_bound",
        "source_id": source_id,
        "source_published_at": None,
        "available_at": None,
        "source_use_accepted": False,
        "pit_eligible": False,
        "training_eligible": False,
    }
    result.update(overrides)
    return result


def _patch_verifiers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    twse_result: dict[str, object] | None,
    tpex_result: dict[str, object] | None = None,
) -> list[tuple[str, tuple[object, ...]]]:
    from data_module import tpex_daily_price_publication, twse_daily_price_publication

    calls: list[tuple[str, tuple[object, ...]]] = []

    def verifier(source_id: str, result: dict[str, object] | None):
        def verify(**kwargs):
            calls.append((source_id, tuple(kwargs["fetched_rows"])))
            if result is None:
                raise AssertionError(f"unexpected verifier call for {source_id}")
            return [dict(result) for _ in kwargs["fetched_rows"]]

        return verify

    monkeypatch.setattr(
        twse_daily_price_publication,
        "verify_fetched_daily_price_rows",
        verifier(SOURCE_TWSE, twse_result),
    )
    monkeypatch.setattr(
        tpex_daily_price_publication,
        "verify_fetched_daily_price_rows",
        verifier(SOURCE_TPEX, tpex_result),
    )
    return calls


def test_binder_returns_one_identity_match_without_granting_qualification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched_rows = ({"日期": "20260601", "證券代號": "2330", "收盤價": 100},)
    calls = _patch_verifiers(
        monkeypatch,
        twse_result=_identity_result(SOURCE_TWSE),
    )
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=_captured_bundle(tmp_path, SOURCE_TWSE),
    )

    result = binder.bind_rows(fetched_rows)

    assert len(calls) == 1
    assert calls[0] == (SOURCE_TWSE, fetched_rows)
    assert result[0]["status"] == "source_identity_bound"
    assert result[0]["source_id"] == SOURCE_TWSE
    assert result[0]["source_bundle_reference"] == {"manifest_path": "fixtures/source-bundle.json"}
    assert result[0]["source_use_accepted"] is False
    assert result[0]["source_published_at"] is None
    assert result[0]["available_at"] is None
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False


def test_binder_uses_exact_primary_for_identical_same_family_publications(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import tpex_daily_price_publication, twse_daily_price_publication

    fetched_rows = ({"日期": "20260601", "證券代號": "2330"},)
    primary = {
        "relative_path": "scheduled/twse/primary.json",
        "sha256": "sha256:" + "a" * 64,
    }
    secondary = {
        "relative_path": "scheduled/twse/secondary.json",
        "sha256": "sha256:" + "b" * 64,
    }

    def verifier(**kwargs):
        descriptor = kwargs["descriptor"]
        return [
            _identity_result(
                SOURCE_TWSE,
                publication_relative_path=descriptor["relative_path"],
                publication_sha256=descriptor["sha256"],
                source_date="20260601",
                stock_code="2330",
                parser_id="twse.mi_index.daily_price.v1",
                projection_row_sha256="sha256:" + "c" * 64,
                sqlite_projection_row_sha256="sha256:" + "d" * 64,
            )
            for _row in kwargs["fetched_rows"]
        ]

    monkeypatch.setattr(twse_daily_price_publication, "verify_fetched_daily_price_rows", verifier)
    monkeypatch.setattr(
        tpex_daily_price_publication,
        "verify_fetched_daily_price_rows",
        lambda **_kwargs: (),
    )
    bundle = _captured_bundle(tmp_path, SOURCE_TWSE)
    bundle["descriptors"][SOURCE_TWSE] = primary
    ledger = SimpleNamespace(
        _publication_descriptors_by_date={(SOURCE_TWSE, "20260601"): [secondary]}
    )
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=bundle,
        revision_ledger=ledger,
    )

    result = binder.bind_rows(fetched_rows)

    assert result[0]["status"] == "source_identity_bound"
    assert result[0]["publication_relative_path"] == primary["relative_path"]
    assert result[0]["publication_sha256"] == primary["sha256"]
    assert result[0]["source_use_accepted"] is False
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False

    unselected_bundle = dict(bundle)
    unselected_bundle["descriptors"] = {}
    unselected_ledger = SimpleNamespace(
        _publication_descriptors_by_date={
            (SOURCE_TWSE, "20260601"): [primary, secondary]
        }
    )
    unselected_binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=unselected_bundle,
        revision_ledger=unselected_ledger,
    )
    unselected = unselected_binder.bind_rows(fetched_rows)
    assert unselected[0]["status"] == "unknown"
    assert unselected[0]["reason_code"] == "same_key_revision_conflict"


def test_binder_rejects_same_family_publications_with_changed_full_row_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import tpex_daily_price_publication, twse_daily_price_publication

    fetched_rows = ({"日期": "20260601", "證券代號": "2330"},)
    primary = {
        "relative_path": "scheduled/twse/primary.json",
        "sha256": "sha256:" + "a" * 64,
    }
    secondary = {
        "relative_path": "scheduled/twse/secondary.json",
        "sha256": "sha256:" + "b" * 64,
    }

    def verifier(**kwargs):
        descriptor = kwargs["descriptor"]
        projection_hash = "c" if descriptor["sha256"] == primary["sha256"] else "e"
        return [
            _identity_result(
                SOURCE_TWSE,
                publication_relative_path=descriptor["relative_path"],
                publication_sha256=descriptor["sha256"],
                source_date="20260601",
                stock_code="2330",
                parser_id="twse.mi_index.daily_price.v1",
                projection_row_sha256="sha256:" + projection_hash * 64,
                sqlite_projection_row_sha256="sha256:" + projection_hash * 64,
            )
            for _row in kwargs["fetched_rows"]
        ]

    monkeypatch.setattr(twse_daily_price_publication, "verify_fetched_daily_price_rows", verifier)
    monkeypatch.setattr(
        tpex_daily_price_publication,
        "verify_fetched_daily_price_rows",
        lambda **_kwargs: (),
    )
    bundle = _captured_bundle(tmp_path, SOURCE_TWSE)
    bundle["descriptors"][SOURCE_TWSE] = primary
    ledger = SimpleNamespace(
        _publication_descriptors_by_date={(SOURCE_TWSE, "20260601"): [secondary]}
    )
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=bundle,
        revision_ledger=ledger,
    )

    result = binder.bind_rows(fetched_rows)

    assert result[0]["status"] == "unknown"
    assert result[0]["reason_code"] == "same_key_revision_conflict"
    assert result[0]["source_use_accepted"] is False
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False


def test_binder_marks_two_family_matches_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched_rows = ({"日期": "20260601", "證券代號": "2330"},)
    _patch_verifiers(
        monkeypatch,
        twse_result=_identity_result(SOURCE_TWSE),
        tpex_result=_identity_result(SOURCE_TPEX),
    )
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=_captured_bundle(tmp_path, SOURCE_TWSE, SOURCE_TPEX),
    )

    result = binder.bind_rows(fetched_rows)

    assert result == (unknown_price_source_binding("dual_source_ambiguity"),)
    assert result[0]["status"] == "unknown"
    assert result[0]["source_use_accepted"] is False
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_use_accepted": True},
        {"pit_eligible": True},
        {"training_eligible": True},
        {"available_at": "2026-06-02T00:00:00Z"},
        {"source_published_at": "2026-06-02T00:00:00Z"},
    ],
)
def test_binder_rejects_verifier_result_that_escalates_qualification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
) -> None:
    fetched_rows = ({"日期": "20260601", "證券代號": "2330"},)
    _patch_verifiers(
        monkeypatch,
        twse_result=_identity_result(SOURCE_TWSE, **overrides),
    )
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3",
        bundle=_captured_bundle(tmp_path, SOURCE_TWSE),
    )

    result = binder.bind_rows(fetched_rows)

    assert result[0]["status"] == "unknown"
    assert result[0]["reason_code"] == "no_verified_source_identity"
    assert result[0]["source_reasons"][SOURCE_TWSE] == "source_verifier_qualification_contract_invalid"
    assert result[0]["source_use_accepted"] is False
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False


@pytest.mark.parametrize(
    "bundle",
    [
        {"status": "unavailable", "descriptors": {SOURCE_TWSE: {}}},
        {"status": "captured"},
    ],
)
def test_binder_keeps_missing_or_invalid_bundle_unqualified(
    tmp_path: Path, bundle: dict[str, object],
) -> None:
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output",
        data_root=tmp_path / "data",
        database_path=tmp_path / "market.sqlite3",
        bundle=bundle,
    )

    result = binder.bind_rows(({"日期": "20260601", "證券代號": "2330"},))

    assert result[0]["status"] == "unknown"
    assert result[0]["source_use_accepted"] is False
    assert result[0]["source_published_at"] is None
    assert result[0]["available_at"] is None
    assert result[0]["pit_eligible"] is False
    assert result[0]["training_eligible"] is False


class _BindingSpy:
    def __init__(self) -> None:
        self.rows: tuple[dict[str, object], ...] | None = None
        self.calls = 0

    def bind_rows(self, rows):
        self.calls += 1
        self.rows = tuple(dict(row) for row in rows)
        return tuple(unknown_price_source_binding("test_identity_unqualified") for _ in rows)


def test_binder_refuses_database_replaced_after_bundle_load(tmp_path, monkeypatch):
    bundle = _captured_bundle(tmp_path, SOURCE_TWSE)
    calls = _patch_verifiers(monkeypatch, twse_result=_identity_result(SOURCE_TWSE))
    bundle["bundle"]["database_identity"]["inode"] = -1
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output", data_root=tmp_path / "data",
        database_path=tmp_path / "data" / "market.sqlite3", bundle=bundle,
    )
    result = binder.bind_rows(({"日期": "20260601", "證券代號": "2330"},))
    assert result[0]["reason_code"] == "source_bundle_database_identity_changed"
    assert result[0]["source_use_accepted"] is False
    assert not calls


def test_binder_rechecks_database_after_source_verification(tmp_path, monkeypatch):
    from data_module import twse_daily_price_publication

    bundle = _captured_bundle(tmp_path, SOURCE_TWSE)
    database = tmp_path / "data" / "market.sqlite3"
    replacement = tmp_path / "data" / "replacement.sqlite3"
    replacement.write_bytes(b"replacement")

    def verify(**kwargs):
        replacement.replace(database)
        return [_identity_result(SOURCE_TWSE) for _ in kwargs["fetched_rows"]]

    monkeypatch.setattr(twse_daily_price_publication, "verify_fetched_daily_price_rows", verify)
    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path / "output", data_root=tmp_path / "data",
        database_path=database, bundle=bundle,
    )
    result = binder.bind_rows(({"日期": "20260601", "證券代號": "2330"},))
    assert result[0]["reason_code"] == "source_bundle_database_identity_changed"


class _ObservationSpy:
    def __init__(self) -> None:
        self.queries: list[dict[str, object]] = []
        self.uses: list[tuple[str, str]] = []

    def observe_query(self, **kwargs) -> str:
        self.queries.append(kwargs)
        return f"query-{len(self.queries)}"

    def record_use(self, query_id: str, *, purpose: str) -> None:
        self.uses.append((query_id, purpose))


def test_service_binds_same_full_17_column_fetch_and_reuses_captured_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "market.sqlite3"
    column_sql = ", ".join(f'"{column}" TEXT' for column in PRICE_PROJECTION_COLUMNS)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"CREATE TABLE daily_prices ({column_sql})")
        row = (
            "20260601", "2330", "台積電", "1000", "10", "10500",
            "10.0", "11.0", "9.5", "10.5", "0.5", "0.5",
            "10.4", "100", "10.5", "200", "20.0",
        )
        placeholders = ", ".join("?" for _ in PRICE_PROJECTION_COLUMNS)
        connection.execute(f"INSERT INTO daily_prices VALUES ({placeholders})", row)

    binder = _BindingSpy()
    observer = _ObservationSpy()
    service = ForwardPerformanceService(
        SimpleNamespace(db_file=db_path),
        db_path=db_path,
        source_observer=observer,
        price_source_binder=binder,
    )

    first_result = service._daily_price_series("2330")

    assert first_result == (("20260601",), (("20260601", Decimal("10.5")),))
    assert binder.calls == 1
    assert binder.rows is not None and len(binder.rows) == 1
    assert len(binder.rows[0]) == len(PRICE_PROJECTION_COLUMNS)
    assert set(binder.rows[0]) == set(PRICE_PROJECTION_COLUMNS)
    assert binder.rows[0] == dict(zip(PRICE_PROJECTION_COLUMNS, row, strict=True))
    assert len(observer.queries) == 1
    assert observer.queries[0]["columns"] == (
        "日期", "收盤價", *(column for column in PRICE_PROJECTION_COLUMNS if column not in {"日期", "收盤價"})
    )
    assert observer.queries[0]["source_bindings"] == (
        unknown_price_source_binding("test_identity_unqualified"),
    )

    with sqlite3.connect(db_path) as connection:
        connection.execute('UPDATE daily_prices SET "收盤價" = ? WHERE "證券代號" = ?', ("999", "2330"))
        connection.execute('UPDATE daily_prices SET "日期" = ? WHERE "證券代號" = ?', ("20260602", "2330"))

    second_result = service._daily_price_series("2330")

    assert second_result == first_result
    assert binder.calls == 1
    assert binder.rows[0]["收盤價"] == "10.5"
    assert len(observer.queries) == 1
    assert observer.uses == [("query-1", "daily_price_series_cache_reuse")]
