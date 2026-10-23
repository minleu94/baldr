"""實際取價列與固定每日價格來源 publication 的純檔案綁定測試。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import requests

from app_module.forward_daily_price_source_binding import ForwardDailyPriceSourceBinder
from app_module.forward_performance_service import ForwardOutcomeSummary, ForwardPerformanceService
from app_module.forward_source_observation import verify_forward_source_observation_readback
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module import scheduled_forward_outcome_service as scheduled_forward
from app_module.update_service import UpdateService
from data_module.daily_price_source_bundle import (
    load_daily_price_source_bundle,
    publish_daily_price_source_bundle,
)
from data_module.daily_price_qualification_binding import (
    DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
    DailyPriceRevisionLedger,
    PinnedDailyPriceQualificationResolver,
    _canonical_bytes,
    verify_qualified_binding_payload,
)
from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader
from data_module.tpex_daily_price_publication import (
    _COLUMNS as TPEX_COLUMNS,
    publish_sqlite_row_evidence as publish_tpex,
    verify_fetched_daily_price_rows as verify_tpex,
)
from data_module.tpex_daily_price_source import (
    TPEX_AFTER_TRADING_OTC_URL,
    TpexDailyPriceSource,
)
from data_module.twse_daily_price_publication import (
    publish_sqlite_row_evidence as publish_twse,
    verify_fetched_daily_price_rows as verify_twse,
)


_TWSE_FIELDS = [
    "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
    "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價",
    "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
]


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._payload


class _Session:
    def __init__(self, payload: dict[str, object]) -> None:
        self.response = _Response(payload)

    def get(self, *_args, **_kwargs) -> _Response:
        return self.response


def _twse_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = TWStockConfig(
        data_root=tmp_path / "twse-data",
        output_root=tmp_path / "twse-output",
        profile="test",
        use_sqlite=True,
    )
    source_row = [
        "2330", "台積電", "1,000", "10", "500,000", "500.00", "510.00",
        "499.00", "505.00", "<p style= color:red>+</p>", "5.00", "506.00",
        "1", "507.00", "2", "20.00",
    ]
    payload: dict[str, object] = {
        "stat": "OK",
        "tables": [{"fields": _TWSE_FIELDS, "data": [source_row]}],
    }
    monkeypatch.setattr("data_module.data_loader.requests.Session", lambda: _Session(payload))
    monkeypatch.setattr("data_module.data_loader.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("data_module.data_loader.random.uniform", lambda _a, _b: 0)
    loader = DataLoader(config)
    frame = loader.download_from_api("2026-07-02")
    assert frame is not None
    diagnostic = dict(loader.last_daily_download_diagnostics)
    assert UpdateService(config).sync_source_to_sqlite(
        "daily_price_files", "2026-07-02", "2026-07-02",
        row_evidence_source_diagnostics=[diagnostic],
    )["success"] is True
    merged = frame.copy()
    merged.insert(0, "日期", "20260702")
    descriptor = publish_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        source_diagnostics=[diagnostic],
        merged_frame=merged,
    )
    assert descriptor["status"] == "captured"
    with sqlite3.connect(config.db_file) as connection:
        connection.row_factory = sqlite3.Row
        fetched = dict(connection.execute(
            'SELECT * FROM daily_prices WHERE "證券代號" = ?', ("2330",)
        ).fetchone())
    return config, descriptor, fetched


def _tpex_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw_payload: dict[str, object] = {
        "tables": [{
            "date": "1150616",
            "fields": ["代號", "名稱", "收盤"],
            "data": [["3207", "耀勝", "42.50"], ["3219", "倚強", "37.00"]],
        }]
    }
    raw_bytes = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    class Response:
        url = TPEX_AFTER_TRADING_OTC_URL + "?date=2026/06/16&type=EW&response=json"
        status_code = 200
        headers = {"content-type": "application/json"}
        content = raw_bytes

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return raw_payload

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    data_root = tmp_path / "tpex-data"
    output_root = tmp_path / "tpex-output"
    result = TpexDailyPriceSource(
        output_dir=data_root / "daily_price_tpex",
        source_custody_root=output_root,
    ).update_for_date("2026-06-16")
    assert result.success and result.source_custody is not None
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    with result.output_file.open("r", encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(pd.read_csv(stream, dtype=str).to_dict(orient="records"))
    columns_sql = ", ".join(f'"{column}" TEXT' for column in TPEX_COLUMNS)
    with sqlite3.connect(database) as connection:
        connection.execute(
            f'CREATE TABLE daily_prices ({columns_sql}, PRIMARY KEY ("證券代號", "日期"))'
        )
        names_sql = ", ".join(f'"{column}"' for column in TPEX_COLUMNS)
        placeholders = ", ".join("?" for _ in TPEX_COLUMNS)
        connection.executemany(
            f"INSERT INTO daily_prices ({names_sql}) VALUES ({placeholders})",
            [tuple(row.get(column) or None for column in TPEX_COLUMNS) for row in csv_rows],
        )
    frame = pd.read_csv(result.output_file, encoding="utf-8-sig", dtype={"日期": str, "證券代號": str})
    descriptor = publish_tpex(
        output_root=output_root,
        data_root=data_root,
        database_path=database,
        source_diagnostics=[result.source_custody],
        merged_frame=frame,
    )
    assert descriptor["status"] == "captured"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        fetched = dict(connection.execute(
            'SELECT * FROM daily_prices WHERE "證券代號" = ?', ("3207",)
        ).fetchone())
    return output_root, data_root, database, descriptor, fetched


@pytest.mark.parametrize("tamper", ["close_only", "other_column"])
def test_twse_binding_checks_complete_fetched_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    config, descriptor, fetched = _twse_fixture(tmp_path, monkeypatch)
    bound = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[fetched],
    )
    assert len(bound) == 1
    assert bound[0]["status"] == "source_identity_bound", bound[0]
    assert bound[0]["source_row_ordinal_basis"] == "derived_verified_raw_ordinal"
    assert bound[0]["available_at"] is None
    assert bound[0]["source_use_accepted"] is False
    alias_null = dict(fetched)
    alias_null["漲跌"] = None
    alias_null_result = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[alias_null],
    )
    assert alias_null_result[0]["status"] == "source_identity_bound", alias_null_result[0]
    alias_conflict = dict(alias_null)
    alias_conflict["漲跌"] = "-"
    conflicting = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[alias_conflict],
    )
    assert conflicting[0]["status"] == "unknown"
    assert "aliases conflict" in str(conflicting[0]["reason_code"])
    altered = dict(fetched)
    altered["收盤價" if tamper == "close_only" else "證券名稱"] = "different"
    rejected = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[altered],
    )
    assert rejected[0]["status"] == "unknown"


def test_twse_binding_rejects_missing_descriptor_and_raw_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, descriptor, fetched = _twse_fixture(tmp_path, monkeypatch)
    missing = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=None,
        fetched_rows=[fetched],
    )
    assert missing[0]["status"] == "unknown"
    absent_key = dict(fetched)
    absent_key["證券代號"] = "9999"
    absent = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[absent_key],
    )
    assert absent[0]["status"] == "unknown"
    publication_path = config.output_root / Path(*str(descriptor["relative_path"]).split("/"))
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    projection_ref = publication["projection_manifests"][0]
    manifest_path = config.output_root / Path(*projection_ref["relative_path"].split("/"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = config.output_root / Path(*manifest["raw_response_relative_path"].split("/"))
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    rejected = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[fetched],
    )
    assert rejected[0]["status"] == "unknown"


def test_twse_binding_rejects_projection_manifest_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, descriptor, fetched = _twse_fixture(tmp_path, monkeypatch)
    publication_path = config.output_root / Path(*str(descriptor["relative_path"]).split("/"))
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    projection_ref = publication["projection_manifests"][0]
    manifest_path = config.output_root / Path(*projection_ref["relative_path"].split("/"))
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    rejected = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[fetched],
    )
    assert rejected[0]["status"] == "unknown"


def test_twse_binding_cache_reuses_verified_artifacts_but_rechecks_each_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import data_module.twse_daily_price_publication as twse_publication

    config, descriptor, fetched = _twse_fixture(tmp_path, monkeypatch)
    verified_cache: dict[tuple[object, ...], object] = {}
    first = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[fetched],
        verified_source_cache=verified_cache,
    )
    assert first[0]["status"] == "source_identity_bound", first[0]
    monkeypatch.setattr(
        twse_publication,
        "_read_evidence_relative",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache miss")),
    )
    second = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[fetched],
        verified_source_cache=verified_cache,
    )
    assert second[0]["status"] == "source_identity_bound"
    changed = dict(fetched)
    changed["證券名稱"] = "different"
    rejected = verify_twse(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        fetched_rows=[changed],
        verified_source_cache=verified_cache,
    )
    assert rejected[0]["status"] == "unknown"


def test_tpex_binding_checks_complete_row_and_explicit_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, data, database, descriptor, fetched = _tpex_fixture(tmp_path, monkeypatch)
    bound = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[fetched],
    )
    assert bound[0]["status"] == "source_identity_bound"
    assert bound[0]["source_row_ordinal_basis"] == "captured_raw_ordinal"
    assert bound[0]["source_use_accepted"] is False
    altered = dict(fetched)
    altered["收盤價"] = "41.50"
    rejected = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[altered],
    )
    assert rejected[0]["status"] == "unknown"
    changed_nonprice = dict(fetched)
    changed_nonprice["證券名稱"] = "different"
    rejected_nonprice = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[changed_nonprice],
    )
    assert rejected_nonprice[0]["status"] == "unknown"
    missing = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=None, fetched_rows=[fetched],
    )
    assert missing[0]["status"] == "unknown"
    absent_key = dict(fetched)
    absent_key["證券代號"] = "9999"
    absent = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[absent_key],
    )
    assert absent[0]["status"] == "unknown"


def test_twse_bundle_binds_actual_forward_full_projection_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, descriptor, _fetched = _twse_fixture(tmp_path, monkeypatch)
    bundle_descriptor = publish_daily_price_source_bundle(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        quick_run_id="20261022T123456123456Z",
        completed_at="2026-10-22T20:30:00+00:00",
        quick_status="passed",
        descriptors={"twse.mi_index.daily_price": descriptor},
    )
    bundle = load_daily_price_source_bundle(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=bundle_descriptor,
    )
    assert bundle["status"] == "captured", bundle
    binder = ForwardDailyPriceSourceBinder(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        bundle=bundle,
    )

    class _Observer:
        def __init__(self) -> None:
            self.queries: list[dict[str, object]] = []

        def observe_query(self, **kwargs: object) -> str:
            self.queries.append(dict(kwargs))
            return "query-1"

        def record_use(self, *_args: object, **_kwargs: object) -> None:
            return None

    observer = _Observer()
    service = ForwardPerformanceService(
        SimpleNamespace(db_file=config.db_file),
        db_path=config.db_file,
        source_observer=observer,
        price_source_binder=binder,
    )
    _keys, values = service._daily_price_series("2330")
    assert values and values[0][1] > 0
    assert len(observer.queries) == 1
    query = observer.queries[0]
    columns = query["columns"]
    assert isinstance(columns, tuple)
    assert "漲跌(+/-)" in columns and "漲跌" in columns
    bindings = query["source_bindings"]
    assert isinstance(bindings, tuple) and len(bindings) == 1
    assert bindings[0]["status"] == "source_identity_bound", bindings[0]
    assert bindings[0]["source_use_accepted"] is False
    assert bindings[0]["pit_eligible"] is False
    assert bindings[0]["training_eligible"] is False
    conflicting_row = dict(zip(columns, query["rows"][0], strict=True))
    conflicting_row["漲跌"] = "-"
    assert binder.bind_rows([conflicting_row])[0]["status"] == "unknown"


def test_tpex_binding_cache_reuses_verified_artifacts_but_rechecks_each_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import data_module.tpex_daily_price_publication as tpex_publication

    output, data, database, descriptor, fetched = _tpex_fixture(tmp_path, monkeypatch)
    verified_cache: dict[tuple[object, ...], object] = {}
    first = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[fetched],
        verified_source_cache=verified_cache,
    )
    assert first[0]["status"] == "source_identity_bound"
    monkeypatch.setattr(
        tpex_publication,
        "_read_under_root",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache miss")),
    )
    second = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[fetched],
        verified_source_cache=verified_cache,
    )
    assert second[0]["status"] == "source_identity_bound"
    changed = dict(fetched)
    changed["證券名稱"] = "different"
    rejected = verify_tpex(
        output_root=output, data_root=data, database_path=database,
        descriptor=descriptor, fetched_rows=[changed],
        verified_source_cache=verified_cache,
    )
    assert rejected[0]["status"] == "unknown"


def test_scheduled_forward_qualification_accepts_verified_row_and_keeps_training_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, descriptor, fetched = _twse_fixture(tmp_path, monkeypatch)
    (config.output_root / "scheduled" / "tpex_daily_price_sqlite_publication").mkdir(
        parents=True,
        exist_ok=True,
    )
    EvidenceEventRepository(config).ensure_schema()
    completed_at = datetime.now(timezone.utc)
    exact_bundle = publish_daily_price_source_bundle(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        quick_run_id="20261022T123456123456Z",
        completed_at=completed_at.isoformat(),
        quick_status="passed",
        descriptors={"twse.mi_index.daily_price": descriptor},
    )
    decision = {
        "source_id": "twse.mi_index.daily_price",
        "decision_revision_id": "accept-forward-outcome-test",
        "parent_revision_id": None,
        "status": "accepted",
        "allowed_use_cases": ["forward_outcome_evaluation"],
        "blockers": [],
        "license_evidence_ids": ["sha256:" + "a" * 64],
        "quality_evidence_ids": ["sha256:" + "b" * 64],
        "pit_evidence_ids": ["sha256:" + "c" * 64],
        "owner_role": "quant_data_architect",
        "reviewer_role": "operations_owner",
        "decided_at": (completed_at - timedelta(hours=1)).isoformat(),
        "rollback_reference": "initial_decision",
    }
    qualification_payload = {
        "schema_version": DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
        "binding_id": "scheduled-forward-test-binding-v1",
        "created_at": completed_at.isoformat(),
        "decision": decision,
    }
    qualification_raw = _canonical_bytes(qualification_payload) + b"\n"
    qualification_path = tmp_path / "qualification-binding.json"
    qualification_path.write_bytes(qualification_raw)
    qualification_sha = "sha256:" + hashlib.sha256(qualification_raw).hexdigest()
    qualification_resolver = PinnedDailyPriceQualificationResolver(
        qualification_path,
        qualification_sha,
    )
    qualification_policy = qualification_resolver.build_policy(
        temporal_role="outcome_realization",
        cutoff_at=completed_at + timedelta(hours=3),
    )
    revision_ledger = DailyPriceRevisionLedger(
        output_root=config.output_root,
        data_root=config.data_root,
    )
    assert revision_ledger.scan_scheduled_publications() == 2
    assert revision_ledger.revision_closure_verified is True
    observed_bindings: list[dict[str, object]] = []

    class _Calendar:
        def describe(self) -> dict[str, str]:
            return {"schema_version": "fixture-calendar.v1"}

    class _ForwardService:
        def __init__(self, _config, _repository, **kwargs) -> None:
            self.observer = kwargs["source_observer"]
            self.binder = kwargs["price_source_binder"]

        def calculate(self, **_kwargs):
            self.observer.begin_calculation()
            self.observer.begin_outcome(event_id="fixture-event", window_days=5)
            binding = self.binder.bind_rows([fetched])[0]
            observed_bindings.append(binding)
            columns = tuple(fetched)
            self.observer.observe_query(
                table="daily_prices",
                query="SELECT fixture daily price row",
                parameters=("2330",),
                rows=[tuple(fetched[column] for column in columns)],
                columns=columns,
                source_bindings=[binding],
                symbol="2330",
                purpose="daily_price_series",
                observed_at=completed_at,
            )
            query_ids = self.observer.end_outcome()
            self.observer.record_outcome(
                event_id="fixture-event",
                window_days=5,
                return_basis="close_to_close_event_date",
                outcome_status="pending_insufficient_future_data",
                outcome_payload={"status": "pending"},
                query_ids=query_ids,
            )
            self.observer.persist()
            return ForwardOutcomeSummary(
                events_scanned=1,
                pending_insufficient_future_data=1,
                dry_run=True,
            )

    monkeypatch.setattr(
        scheduled_forward,
        "build_official_maturity_calendar",
        lambda **_kwargs: _Calendar(),
    )
    monkeypatch.setattr(
        scheduled_forward,
        "_read_calendar_observation",
        lambda *_args: {"status": "fixture"},
    )
    monkeypatch.setattr(
        scheduled_forward,
        "_build_daily_health",
        lambda **_kwargs: {
            "classification": "waiting_for_natural_maturity",
            "blockers": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(scheduled_forward, "ForwardPerformanceService", _ForwardService)
    qualification_cutoff = completed_at + timedelta(hours=3)
    run_now = (completed_at + timedelta(hours=4)).astimezone(
        ZoneInfo("Asia/Taipei")
    )
    result = scheduled_forward.run_scheduled_forward_outcomes(
        config=config,
        now=run_now,
        confirm=False,
        windows=(5,),
        price_source_bundle_descriptor=exact_bundle,
        daily_price_qualification_binding_path=qualification_path,
        daily_price_qualification_binding_sha256=qualification_sha,
        daily_price_qualification_role="outcome_realization",
        daily_price_qualification_cutoff_at=qualification_cutoff.isoformat(),
    )

    assert result["exit_code"] == 0, result
    assert observed_bindings[0]["status"] == "source_qualified", observed_bindings[0]
    assert observed_bindings[0]["source_use_accepted"] is True
    assert observed_bindings[0]["pit_eligible"] is True
    assert observed_bindings[0]["training_eligible"] is False
    assert result["daily_price_qualification"]["training_eligible"] is False
    observation_reference = result["source_observation"]
    assert observation_reference["training_eligible"] is False

    def reverify(binding: dict[str, object]) -> bool:
        return verify_qualified_binding_payload(
            binding,
            resolver=qualification_resolver,
            policy=qualification_policy,
            revision_ledger=revision_ledger,
        )

    readback = verify_forward_source_observation_readback(
        output_root=config.output_root,
        reference=observation_reference,
        qualification_verifier=reverify,
    )
    bindings = [
        binding
        for query in readback["queries"]
        for binding in query["source_bindings"]
    ]
    assert readback["status"] == "verified"
    assert bindings[0]["status"] == "source_qualified"
    assert bindings[0]["training_eligible"] is False
