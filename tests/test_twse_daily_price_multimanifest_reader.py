"""多 projection manifest 與同次 scalar/readback 的合成回歸。"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader
from data_module.twse_daily_price_publication import (
    DailyPriceScalarEvidenceReadResult,
    DailyPriceEvidenceReadResult,
    PROJECTION_SCHEMA_V1,
    PUBLICATION_SCHEMA_V1,
    _atomic_row_readback,
    _parse_csv_projection,
    _payload_bytes,
    _row_hash,
    _sha256,
    publish_sqlite_row_evidence,
    read_sqlite_daily_price_evidence,
    read_sqlite_daily_price_scalar_evidence,
)


_SOURCE_ID = "twse.mi_index.daily_price"
_PARSER_ID = "twse.mi_index.v1"
_WRITTEN_AT = "2026-07-06T00:00:00+00:00"
_COLUMNS = ["日期", "證券代號", "收盤價"]
_CUSTODY_SCHEMA = "official-daily-price-response-capture.v1"
_TWSE_FIELDS = [
    "證券代號",
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
]


def _write_immutable_json(root: Path, relative: str, body: dict[str, object]) -> dict[str, object]:
    raw = _payload_bytes(body)
    digest = _sha256(raw)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {
        "status": "captured",
        "schema_version": str(body["schema_version"]),
        "relative_path": relative,
        "sha256": digest,
        "capture_id": digest.removeprefix("sha256:")[:24],
    }


def _append_projection(
    *,
    output_root: Path,
    data_root: Path,
    date_key: str,
    stock_code: str,
    close_price: str,
    numeric_index: int,
) -> tuple[dict[str, object], dict[str, object]]:
    captured_at = f"2026-07-0{numeric_index + 2}T08:00:00+00:00"
    raw_relative = f"source/{date_key}/raw_response.bin"
    raw_path = output_root / raw_relative
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = json.dumps(
        {"date": date_key, "code": stock_code, "close": close_price},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    raw_path.write_bytes(raw_bytes)
    raw_hash = _sha256(raw_bytes)

    receipt_body = {
        "schema_version": _CUSTODY_SCHEMA,
        "source_id": _SOURCE_ID,
        "source_date": f"2026-07-0{numeric_index + 2}",
        "parser_id": _PARSER_ID,
        "raw_response_sha256": raw_hash,
        "captured_at": captured_at,
        "formal_source_contract_eligible": False,
    }
    receipt_relative = f"source/{date_key}/receipt.json"
    observation_relative = f"source/{date_key}/observation.json"
    receipt_descriptor = _write_immutable_json(
        output_root, receipt_relative, receipt_body
    )
    observed_at = (
        datetime.fromisoformat(captured_at) + timedelta(seconds=1)
    ).isoformat()
    observation_body = {**receipt_body, "captured_at": observed_at}
    observation_descriptor = _write_immutable_json(
        output_root, observation_relative, observation_body
    )

    csv_relative = f"daily_prices/{date_key}.csv"
    csv_bytes = (
        "日期,證券代號,收盤價\n"
        f"{date_key},{stock_code},{close_price}\n"
    ).encode("utf-8-sig")
    csv_path = data_root / csv_relative
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(csv_bytes)
    columns, parsed_rows = _parse_csv_projection(csv_bytes, date_key)
    projection_row_hash = _row_hash(parsed_rows[0], columns)

    projection_body = {
        "schema_version": PROJECTION_SCHEMA_V1,
        "source_id": _SOURCE_ID,
        "parser_id": _PARSER_ID,
        "venue": "twse",
        "source_date": date_key,
        "source_published_at": None,
        "first_observed_at": captured_at,
        "observed_at": observed_at,
        "raw_response_relative_path": raw_relative,
        "raw_response_sha256": raw_hash,
        "custody_receipt_relative_path": receipt_relative,
        "custody_receipt_sha256": receipt_descriptor["sha256"],
        "observation_receipt_relative_path": observation_relative,
        "observation_receipt_sha256": observation_descriptor["sha256"],
        "csv_relative_path": csv_relative,
        "csv_sha256": _sha256(csv_bytes),
        "projection_columns": list(columns),
        "observed_response_rows": [
            {
                "source_date": date_key,
                "stock_code": stock_code,
                "projection_row_sha256": projection_row_hash,
            }
        ],
        "coverage_basis": "keys_observed_in_this_twse_response_only",
    }
    manifest_descriptor = _write_immutable_json(
        output_root,
        f"projection/{date_key}/manifest.json",
        projection_body,
    )

    return manifest_descriptor, {
        "source_date": date_key,
        "stock_code": stock_code,
        "source_id": _SOURCE_ID,
        "parser_id": _PARSER_ID,
        "first_observed_at": captured_at,
        "written_at": _WRITTEN_AT,
        "source_published_at": None,
        "raw_response_sha256": raw_hash,
        "custody_receipt_sha256": receipt_descriptor["sha256"],
        "observation_receipt_sha256": observation_descriptor["sha256"],
        "csv_sha256": _sha256(csv_bytes),
        "projection_row_sha256": projection_row_hash,
        "projection_columns": list(columns),
        "projection_manifest_relative_path": manifest_descriptor["relative_path"],
        "projection_manifest_sha256": manifest_descriptor["sha256"],
    }


def _two_manifest_publication(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    output_root = tmp_path / "output"
    data_root = tmp_path / "data"
    output_root.mkdir()
    data_root.mkdir()
    database_path = data_root / "daily_prices.sqlite"
    manifests: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL)'
        )
        for index, (date_key, code, close) in enumerate(
            (("20260702", "2330", "505"), ("20260703", "2317", "210"))
        ):
            manifest, row = _append_projection(
                output_root=output_root,
                data_root=data_root,
                date_key=date_key,
                stock_code=code,
                close_price=close,
                numeric_index=index,
            )
            connection.execute(
                'INSERT INTO daily_prices ("日期", "證券代號", "收盤價") VALUES (?, ?, ?)',
                (date_key, code, int(close)),
            )
            manifests.append(manifest)
            rows.append(row)
        connection.commit()
    finally:
        connection.close()

    for row in rows:
        actual = _atomic_row_readback(
            database_path=database_path,
            source_date=str(row["source_date"]),
            stock_code=str(row["stock_code"]),
            columns=row["projection_columns"],
        )
        assert actual is not None
        row["sqlite_projection_row_sha256"] = actual[1]

    publication_body: dict[str, object] = {
        "schema_version": PUBLICATION_SCHEMA_V1,
        "source_id": _SOURCE_ID,
        "source_published_at": None,
        "written_at": _WRITTEN_AT,
        "database_relative_path": "daily_prices.sqlite",
        "projection_manifests": manifests,
        "coverage_basis": "keys_observed_in_this_twse_response_only",
        "rows": rows,
    }
    descriptor = _write_immutable_json(
        output_root, "publication/multi.json", publication_body
    )
    return output_root, data_root, descriptor


def _rewrite_publication(
    output_root: Path,
    descriptor: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    raw = _payload_bytes(body)
    digest = _sha256(raw)
    relative = f"publication/tampered-{digest.removeprefix('sha256:')}.json"
    path = output_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {**descriptor, "relative_path": relative, "sha256": digest}


def _rewrite_projection_manifest_clock(
    output_root: Path,
    descriptor: dict[str, object],
    publication: dict[str, object],
    *,
    row_index: int,
    field_name: str,
    changed_at: str,
) -> dict[str, object]:
    row = publication["rows"][row_index]
    old_relative = str(row["projection_manifest_relative_path"])
    manifest_path = output_root / old_relative
    stored_manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest = {
        key: value
        for key, value in stored_manifest.items()
        if key != "content_sha256"
    }
    manifest[field_name] = changed_at
    manifest_descriptor = _write_immutable_json(
        output_root,
        f"projection/tampered/{field_name}-{row_index}-{_sha256(_payload_bytes(manifest)).removeprefix('sha256:')}.json",
        manifest,
    )
    references = publication["projection_manifests"]
    reference_index = next(
        index
        for index, reference in enumerate(references)
        if reference["relative_path"] == old_relative
    )
    references[reference_index] = manifest_descriptor
    row["projection_manifest_relative_path"] = manifest_descriptor["relative_path"]
    row["projection_manifest_sha256"] = manifest_descriptor["sha256"]
    if field_name == "first_observed_at":
        row["first_observed_at"] = changed_at
    return _rewrite_publication(output_root, descriptor, publication)


def _reader_arguments(
    output_root: Path,
    data_root: Path,
    descriptor: dict[str, object],
    *,
    date_key: str,
    code: str,
) -> dict[str, object]:
    return {
        "output_root": output_root,
        "data_root": data_root,
        "database_path": data_root / "daily_prices.sqlite",
        "descriptor": descriptor,
        "source_date": date_key,
        "stock_code": code,
    }


class _SyntheticResponse:
    status_code = 200
    url = "https://example.invalid/exchangeReport/MI_INDEX"
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.content = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._payload


class _SyntheticSession:
    def __init__(self, payload: dict[str, object]) -> None:
        self.response = _SyntheticResponse(payload)

    def get(self, *_args, **_kwargs) -> _SyntheticResponse:
        return self.response


def _twse_row(code: str, name: str, close: str) -> list[str]:
    return [
        code,
        name,
        "1,000",
        "10",
        "500,000",
        "500.00",
        "510.00",
        "499.00",
        close,
        "<p style= color:red>+</p>",
        "5.00",
        close,
        "1",
        "506.00",
        "2",
        "20.00",
    ]


def _real_two_manifest_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    written_at: datetime | None = None,
) -> tuple[TWStockConfig, dict[str, object]]:
    """經實際 collector/custody/projection/publication API 建合成雙 manifest。"""

    config = TWStockConfig(
        data_root=tmp_path / "collector_data",
        output_root=tmp_path / "collector_output",
        profile="test",
        use_sqlite=True,
    )
    service = UpdateService(config)
    diagnostics: list[dict[str, object]] = []
    frames: list[pd.DataFrame] = []
    for date_text, code, name, close in (
        ("2026-07-02", "2330", "台積電", "505.00"),
        ("2026-07-03", "2317", "鴻海", "210.00"),
    ):
        payload: dict[str, object] = {
            "stat": "OK",
            "tables": [
                {"fields": _TWSE_FIELDS, "data": [_twse_row(code, name, close)]}
            ],
        }
        monkeypatch.setattr(
            "data_module.data_loader.requests.Session",
            lambda payload=payload: _SyntheticSession(payload),
        )
        monkeypatch.setattr(
            "data_module.data_loader.time.sleep", lambda _seconds: None
        )
        monkeypatch.setattr(
            "data_module.data_loader.random.uniform", lambda _a, _b: 0
        )
        loader = DataLoader(config)
        frame = loader.download_from_api(date_text)
        assert frame is not None
        diagnostic = dict(loader.last_daily_download_diagnostics)
        assert diagnostic["row_projection_manifest"]["status"] == "captured"
        sync = service.sync_source_to_sqlite(
            "daily_price_files",
            date_text,
            date_text,
            row_evidence_source_diagnostics=[diagnostic],
        )
        assert sync["success"] is True
        frame = frame.copy()
        frame.insert(0, "日期", date_text.replace("-", ""))
        diagnostics.append(diagnostic)
        frames.append(frame)

    publish_arguments: dict[str, object] = {}
    if written_at is not None:
        publish_arguments["written_at"] = written_at
    descriptor = publish_sqlite_row_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        source_diagnostics=diagnostics,
        merged_frame=pd.concat(frames, ignore_index=True),
        **publish_arguments,
    )
    if descriptor["status"] == "captured":
        assert descriptor["row_count"] == 2
    return config, descriptor


def _rewrite_collector_publication(
    config: TWStockConfig,
    descriptor: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    raw = _payload_bytes(body)
    digest = _sha256(raw)
    relative = (
        "synthetic/twse_daily_price_sqlite_publication/"
        f"{digest.removeprefix('sha256:')}.json"
    )
    path = config.output_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {**descriptor, "relative_path": relative, "sha256": digest}


def test_first_and_last_projection_manifest_rows_attest_and_scalar_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    publication = json.loads(
        (output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    assert len(publication["projection_manifests"]) == 2

    import data_module.twse_daily_price_publication as module

    original_readback = module._atomic_row_readback_readonly
    snapshots: list[tuple[dict[str, object], str] | None] = []
    connect_calls: list[tuple[str, dict[str, object]]] = []
    original_connect = module.sqlite3.connect
    connection_probes: list[dict[str, object]] = []

    class _ConnectionProbe:
        def __init__(self, connection):
            self.connection = connection
            self.statements: list[str] = []
            self.write_rejected = False

        @property
        def row_factory(self):
            return self.connection.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self.connection.row_factory = value

        def execute(self, statement, *parameters):
            self.statements.append(str(statement).strip().upper())
            result = self.connection.execute(statement, *parameters)
            if str(statement).strip().upper() == "PRAGMA QUERY_ONLY = ON":
                assert self.connection.execute("PRAGMA query_only").fetchone()[0] == 1
                with pytest.raises(sqlite3.OperationalError):
                    self.connection.execute(
                        'CREATE TABLE "blocked_write" ("id" INTEGER)'
                    )
                self.write_rejected = True
            return result

        def rollback(self):
            self.statements.append("ROLLBACK")
            self.connection.rollback()

        def close(self):
            self.connection.close()

        def __getattr__(self, name):
            return getattr(self.connection, name)

    def capture_snapshot(**kwargs):
        result = original_readback(**kwargs)
        snapshots.append(result)
        return result

    def capture_connect(database, *args, **kwargs):
        connect_calls.append((str(database), dict(kwargs)))
        probe = _ConnectionProbe(original_connect(database, *args, **kwargs))
        connection_probes.append(probe)
        return probe

    monkeypatch.setattr(module, "_atomic_row_readback", lambda **_kwargs: pytest.fail("reader used RW readback"))
    monkeypatch.setattr(module, "_atomic_row_readback_readonly", capture_snapshot)
    monkeypatch.setattr(module.sqlite3, "connect", capture_connect)
    first = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            descriptor,
            date_key="20260702",
            code="2330",
        ),
        scalar_column="收盤價",
    )
    last = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            descriptor,
            date_key="20260703",
            code="2317",
        ),
        scalar_column="收盤價",
    )

    assert isinstance(first, DailyPriceScalarEvidenceReadResult)
    assert first.status == last.status == "attested"
    assert first.row is not None and last.row is not None
    assert Decimal(str(first.scalar_value)) == Decimal("505.0")
    assert Decimal(str(last.scalar_value)) == Decimal("210.0")
    assert len(snapshots) == 2
    assert len(connect_calls) == 2
    assert all("?mode=ro" in uri and options.get("uri") is True for uri, options in connect_calls)
    for probe in connection_probes:
        assert "PRAGMA QUERY_ONLY = ON" in probe.statements
        assert "BEGIN" in probe.statements
        assert "ROLLBACK" in probe.statements
        assert "COMMIT" not in probe.statements
        assert probe.write_rejected is True
    assert snapshots[0] is not None and snapshots[1] is not None
    assert snapshots[0][0]["收盤價"] == first.scalar_value
    assert snapshots[1][0]["收盤價"] == last.scalar_value

    legacy = read_sqlite_daily_price_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            descriptor,
            date_key="20260702",
            code="2330",
        )
    )
    assert legacy.status == "attested"
    assert legacy.row is not None
    assert tuple(field.name for field in fields(DailyPriceEvidenceReadResult)) == (
        "status",
        "reason_code",
        "row",
    )
    assert set(asdict(legacy)) == {"status", "reason_code", "row"}
    assert "scalar_column" not in inspect.signature(read_sqlite_daily_price_evidence).parameters
    assert len(snapshots) == 3
    assert len(connection_probes) == 3


@pytest.mark.parametrize("row_index", [0, 1], ids=["first_manifest", "last_manifest"])
def test_cross_manifest_provenance_tamper_is_rejected_for_each_selected_row(
    tmp_path: Path,
    row_index: int,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    path = output_root / str(descriptor["relative_path"])
    payload = json.loads(path.read_text("utf-8"))
    selected = payload["rows"][row_index]
    other = payload["rows"][1 - row_index]
    for field_name in (
        "raw_response_sha256",
        "custody_receipt_sha256",
        "observation_receipt_sha256",
        "csv_sha256",
    ):
        selected[field_name] = other[field_name]
    tampered = _rewrite_publication(output_root, descriptor, payload)

    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            tampered,
            date_key=str(selected["source_date"]),
            code=str(selected["stock_code"]),
        ),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "evidence_validation_failed"
    assert result.row is None
    assert result.scalar_value is None


def test_scalar_reader_rejects_a_column_outside_the_attested_projection(
    tmp_path: Path,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            descriptor,
            date_key="20260702",
            code="2330",
        ),
        scalar_column="not_in_projection",
    )
    assert result.status == "unknown"
    assert result.reason_code == "scalar_not_attested"
    assert result.row is None
    assert result.scalar_value is None


@pytest.mark.parametrize("scalar_column", [None, False, 1, ""], ids=["none", "bool", "integer", "empty"])
def test_scalar_reader_rejects_missing_or_invalid_scalar_column(
    tmp_path: Path,
    scalar_column: object,
) -> None:
    result = read_sqlite_daily_price_scalar_evidence(
        output_root=tmp_path,
        data_root=tmp_path,
        database_path=tmp_path / "missing.sqlite",
        descriptor=None,
        source_date="20260702",
        stock_code="2330",
        scalar_column=scalar_column,  # type: ignore[arg-type]
    )
    assert result.status == "unknown"
    assert result.reason_code == "scalar_not_attested"
    assert result.scalar_column is None
    assert result.scalar_value is None
    assert result.row is None


def test_real_collector_and_publisher_path_reads_first_and_last_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, descriptor = _real_two_manifest_publication(tmp_path, monkeypatch)
    payload = json.loads(
        (config.output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    assert len(payload["projection_manifests"]) == 2

    first = read_sqlite_daily_price_scalar_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        source_date="20260702",
        stock_code="2330",
        scalar_column="收盤價",
    )
    last = read_sqlite_daily_price_scalar_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        source_date="20260703",
        stock_code="2317",
        scalar_column="收盤價",
    )
    assert first.status == last.status == "attested"
    assert first.row is not None and last.row is not None
    assert Decimal(str(first.scalar_value)) == Decimal("505.0")
    assert Decimal(str(last.scalar_value)) == Decimal("210.0")


def test_real_collector_publication_rejects_backdated_first_observed_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, descriptor = _real_two_manifest_publication(tmp_path, monkeypatch)
    payload = json.loads(
        (config.output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    row = payload["rows"][0]
    row["first_observed_at"] = "2000-01-01T00:00:00+00:00"
    tampered = _rewrite_collector_publication(config, descriptor, payload)

    result = read_sqlite_daily_price_scalar_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=tampered,
        source_date=str(row["source_date"]),
        stock_code=str(row["stock_code"]),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "first_observed_at_mismatch"
    assert result.row is None and result.scalar_value is None


@pytest.mark.parametrize("row_index", [0, 1], ids=["first_manifest", "last_manifest"])
@pytest.mark.parametrize("offset_seconds", [-1, 1], ids=["earlier", "later"])
def test_publication_first_observed_clock_must_match_selected_manifest(
    tmp_path: Path,
    row_index: int,
    offset_seconds: int,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    publication_path = output_root / str(descriptor["relative_path"])
    publication = json.loads(publication_path.read_text("utf-8"))
    row = publication["rows"][row_index]
    original_at = datetime.fromisoformat(str(row["first_observed_at"]))
    row["first_observed_at"] = (
        original_at + timedelta(seconds=offset_seconds)
    ).isoformat()
    tampered = _rewrite_publication(output_root, descriptor, publication)
    assert _sha256((output_root / str(tampered["relative_path"])).read_bytes()) == tampered["sha256"]

    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            tampered,
            date_key=str(row["source_date"]),
            code=str(row["stock_code"]),
        ),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "first_observed_at_mismatch"
    assert result.row is None and result.scalar_value is None


def test_equivalent_aware_first_observed_clock_is_canonicalized(
    tmp_path: Path,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    publication = json.loads(
        (output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    row = publication["rows"][0]
    original = datetime.fromisoformat(str(row["first_observed_at"]))
    row["first_observed_at"] = original.astimezone(
        timezone(timedelta(hours=-8))
    ).isoformat()
    tampered = _rewrite_publication(output_root, descriptor, publication)
    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            tampered,
            date_key=str(row["source_date"]),
            code=str(row["stock_code"]),
        ),
        scalar_column="收盤價",
    )
    assert result.status == "attested"
    assert result.row is not None
    assert result.row.first_observed_at == original.astimezone(timezone.utc).isoformat()


@pytest.mark.parametrize(
    ("field_name", "clock_delta"),
    [
        ("first_observed_at", timedelta(seconds=-1)),
        ("observed_at", timedelta(seconds=-1)),
    ],
    ids=["manifest-first-observed-backdated", "manifest-observed-backdated"],
)
def test_rehashed_manifest_clock_backdating_is_rejected_against_receipts(
    tmp_path: Path,
    field_name: str,
    clock_delta: timedelta,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    publication = json.loads(
        (output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    row_index = 0
    row = publication["rows"][row_index]
    manifest_path = output_root / str(row["projection_manifest_relative_path"])
    manifest = json.loads(manifest_path.read_text("utf-8"))
    original_at = datetime.fromisoformat(str(manifest[field_name]))
    changed_at = original_at + clock_delta
    if field_name == "observed_at":
        first = datetime.fromisoformat(str(manifest["first_observed_at"]))
        changed_at = max(first, changed_at)
    tampered = _rewrite_projection_manifest_clock(
        output_root,
        descriptor,
        publication,
        row_index=row_index,
        field_name=field_name,
        changed_at=changed_at.isoformat(),
    )
    assert _sha256((output_root / str(tampered["relative_path"])).read_bytes()) == tampered["sha256"]

    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            tampered,
            date_key=str(row["source_date"]),
            code=str(row["stock_code"]),
        ),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "manifest_clock_mismatch"
    assert result.row is None and result.scalar_value is None


def test_publisher_rejects_written_at_before_observation_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, descriptor = _real_two_manifest_publication(
        tmp_path,
        monkeypatch,
        written_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    assert descriptor["status"] == "unknown"
    assert descriptor["reason_code"] == "publication_written_before_source_available"


def test_reader_rejects_rehashed_publication_written_before_observation(
    tmp_path: Path,
) -> None:
    output_root, data_root, descriptor = _two_manifest_publication(tmp_path)
    publication = json.loads(
        (output_root / str(descriptor["relative_path"])).read_text("utf-8")
    )
    backdated = "2000-01-01T00:00:00+00:00"
    publication["written_at"] = backdated
    publication["rows"][0]["written_at"] = backdated
    tampered = _rewrite_publication(output_root, descriptor, publication)
    result = read_sqlite_daily_price_scalar_evidence(
        **_reader_arguments(
            output_root,
            data_root,
            tampered,
            date_key="20260702",
            code="2330",
        ),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "publication_written_before_source_available"
    assert result.row is None and result.scalar_value is None


@pytest.mark.parametrize("row_index", [0, 1], ids=["first_manifest", "last_manifest"])
def test_real_collector_publication_rejects_cross_manifest_provenance_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row_index: int,
) -> None:
    config, descriptor = _real_two_manifest_publication(tmp_path, monkeypatch)
    publication_path = config.output_root / str(descriptor["relative_path"])
    payload = json.loads(publication_path.read_text("utf-8"))
    selected = payload["rows"][row_index]
    other = payload["rows"][1 - row_index]
    for field_name in (
        "raw_response_sha256",
        "custody_receipt_sha256",
        "observation_receipt_sha256",
        "csv_sha256",
    ):
        selected[field_name] = other[field_name]
    tampered = _rewrite_collector_publication(config, descriptor, payload)

    result = read_sqlite_daily_price_scalar_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=tampered,
        source_date=str(selected["source_date"]),
        stock_code=str(selected["stock_code"]),
        scalar_column="收盤價",
    )
    assert result.status == "unknown"
    assert result.reason_code == "evidence_validation_failed"
    assert result.row is None
    assert result.scalar_value is None
