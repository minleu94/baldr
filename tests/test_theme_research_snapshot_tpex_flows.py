"""以型別化替身驗證題材 snapshot 的 TPEx 法人 v2 組裝邊界。"""

from __future__ import annotations

import csv
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sqlite3

import pytest

from app_module import theme_daily_service, theme_research_snapshot as snapshot_module
from app_module.institutional_daily_snapshot import InstitutionalDailySnapshotPin
from app_module.institutional_source_use import InstitutionalSourceUsePin
from app_module.theme_daily_service import ThemeFlowObservation, ThemeMarketInput
from app_module.theme_research_snapshot import read_theme_research_snapshot
from decision_module.industry_theme_map import ThemeMappingRow


TAIPEI = timezone(timedelta(hours=8), name="Asia/Taipei")
DATA_DATE = "2026-10-19"
COMPLETED_AT = "2026-10-19T05:05:12+00:00"
AVAILABLE_AT = datetime(2026, 10, 19, 14, 0, tzinfo=TAIPEI)
KNOWN_AT = AVAILABLE_AT + timedelta(hours=1)
V1_SCHEMA = "baldr.theme_research_snapshot.v1"
V2_SCHEMA = "baldr.theme_research_snapshot.tpex_flows.v2"
DAILY_MANIFEST_SHA = "a" * 64
DAILY_RECEIPT_SHA = "b" * 64
SOURCE_USE_SHA = "c" * 64
_MAPPING_FIELDS = tuple(field.name for field in fields(ThemeMappingRow))


def _mapping_record(
    chain_name: str,
    theme_name: str,
    stock_id: str,
    market_type: str,
) -> dict[str, str]:
    return {
        "snapshot_date": DATA_DATE,
        "available_date": DATA_DATE,
        "stock_id": stock_id,
        "stock_name": f"fixture-{stock_id}",
        "market_type": market_type,
        "l1_industry_category": "半導體",
        "chain_name": chain_name,
        "chain_tier": "中游",
        "theme_name": theme_name,
        "is_primary": "true",
        "assignment_method": "snapshot-tpex-flow-test",
        "source_name": "synthetic-test-mapping",
        "source_tier": "T1",
        "pit_mode": "quarterly_snapshot",
        "evidence_note": "synthetic test mapping; not a source qualification",
    }


def _mapping_bytes(
    rows: tuple[tuple[str, str, str, str], ...],
) -> bytes:
    stream = StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=_MAPPING_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(_mapping_record(*row) for row in rows)
    return stream.getvalue().encode("utf-8")


def _write_manifest(path: Path, value: dict[str, object]) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _write_snapshot_files(
    tmp_path: Path,
    *,
    rows: tuple[tuple[str, str, str, str], ...] = (
        ("半導體", "晶圓製造", "6488", "tpex"),
    ),
    saved_completed_at: str = COMPLETED_AT,
) -> tuple[Path, Path, Path, Path, bytes]:
    root = tmp_path / "saved-theme-version"
    root.mkdir(parents=True)
    mapping_path = root / "mapping.csv"
    mapping_raw = _mapping_bytes(rows)
    mapping_path.write_bytes(mapping_raw)

    daily_directory = root / "daily_snapshot"
    daily_directory.mkdir()
    source_use_path = root / "source_use.json"
    source_use_path.write_bytes(b"synthetic fixture only\n")

    manifest_path = root / "manifest.json"
    manifest_raw = _write_manifest(
        manifest_path,
        {
            "schema": V2_SCHEMA,
            "data_date": DATA_DATE,
            "saved_completed_at": saved_completed_at,
            "mapping": {
                "path": "mapping.csv",
                "sha256": sha256(mapping_raw).hexdigest(),
            },
            "institutional": {
                "daily_directory": str(daily_directory.resolve()),
                "manifest_sha256": DAILY_MANIFEST_SHA,
                "receipt_sha256": DAILY_RECEIPT_SHA,
                "source_use_path": str(source_use_path.resolve()),
                "source_use_sha256": SOURCE_USE_SHA,
            },
        },
    )
    return manifest_path, mapping_path, daily_directory, source_use_path, manifest_raw


def _write_prices(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT)')
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?)', ("6488", DATA_DATE),
        )


def _install_flow_probe(
    monkeypatch: pytest.MonkeyPatch,
    flows: tuple[ThemeFlowObservation, ...],
) -> dict[str, list[object]]:
    events: dict[str, list[object]] = {"constructors": [], "reads": []}

    class FlowReaderProbe:
        def __init__(
            self,
            pin: InstitutionalDailySnapshotPin,
            *,
            source_use_pin: InstitutionalSourceUsePin,
            eligible_stock_ids: tuple[str, ...],
        ) -> None:
            events["constructors"].append((pin, source_use_pin, eligible_stock_ids))

        def read(
            self,
            stock_ids: tuple[str, ...],
            data_date: date,
            known_at: datetime,
        ) -> ThemeMarketInput:
            events["reads"].append((stock_ids, data_date, known_at))
            return ThemeMarketInput(flows=flows)

    monkeypatch.setattr(snapshot_module, "TPExThemeFlowReader", FlowReaderProbe)
    return events


def _flow(stock_id: str, net_shares: int) -> ThemeFlowObservation:
    return ThemeFlowObservation(
        stock_id=stock_id,
        data_date=date.fromisoformat(DATA_DATE),
        available_at=AVAILABLE_AT,
        source_id=f"fixture-flow:{stock_id}",
        net_shares=net_shares,
        net_turnover_twd=None,
    )


def test_v1_still_requires_prices_and_rejects_the_v2_institutional_namespace(
    tmp_path: Path,
) -> None:
    missing_prices_dir = tmp_path / "v1-missing-prices"
    manifest_path, *_ = _write_snapshot_files(missing_prices_dir)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema"] = V1_SCHEMA
    manifest.pop("institutional")
    _write_manifest(manifest_path, manifest)

    with pytest.raises((KeyError, ValueError)):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    namespaced_dir = tmp_path / "v1-institutional-namespace"
    manifest_path, *_ = _write_snapshot_files(namespaced_dir)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema"] = V1_SCHEMA
    prices_path = manifest_path.parent / "prices.sqlite"
    _write_prices(prices_path)
    manifest["prices"] = {
        "path": prices_path.name,
        "sha256": sha256(prices_path.read_bytes()).hexdigest(),
    }
    _write_manifest(manifest_path, manifest)

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_v2_projects_only_upper_listed_flow_members_and_keeps_missing_metrics_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = (
        ("半導體", "部分覆蓋", "6488", "tpex"),
        ("半導體", "部分覆蓋", "8069", "tpex"),
        ("半導體", "部分覆蓋", "4321", "tpex"),
        ("半導體", "部分覆蓋", "2330", "twse"),
        ("航運", "相抵為零", "7777", "tpex"),
        ("航運", "相抵為零", "8888", "tpex"),
        ("光電", "負淨額", "4444", "tpex"),
        ("電機", "原始零值", "9999", "tpex"),
        ("材料", "未回傳資料", "5555", "tpex"),
    )
    manifest_path, _, daily_directory, source_use_path, raw = _write_snapshot_files(
        tmp_path,
        rows=rows,
    )
    assert set(json.loads(raw)) == {
        "schema", "data_date", "saved_completed_at", "mapping", "institutional",
    }
    assert "prices" not in json.loads(raw)

    probe = _install_flow_probe(
        monkeypatch,
        (
            _flow("6488", 130),
            _flow("8069", -30),
            _flow("7777", 20),
            _flow("8888", -20),
            _flow("4444", -7),
            _flow("9999", 0),
        ),
    )
    snapshot = read_theme_research_snapshot(manifest_path, known_at=AVAILABLE_AT)

    assert snapshot.identity_sha256 == sha256(raw).hexdigest()
    assert snapshot.report.data_date == date.fromisoformat(DATA_DATE)
    assert snapshot.report.known_at == AVAILABLE_AT
    assert snapshot.report.status == "current_research"
    assert snapshot.report.historical_pit_eligible is False
    assert len(probe["constructors"]) == 1
    pin, source_use_pin, eligible_stock_ids = probe["constructors"][0]
    assert type(pin) is InstitutionalDailySnapshotPin
    assert pin.directory == daily_directory.resolve()
    assert pin.manifest_sha256 == DAILY_MANIFEST_SHA
    assert pin.receipt_sha256 == DAILY_RECEIPT_SHA
    assert type(source_use_pin) is InstitutionalSourceUsePin
    assert source_use_pin.path == source_use_path.resolve()
    assert source_use_pin.sha256 == SOURCE_USE_SHA
    assert eligible_stock_ids == (
        "4321", "4444", "5555", "6488", "7777", "8069", "8888", "9999",
    )
    assert probe["reads"] == [
        (
            ("2330", "4321", "4444", "5555", "6488", "7777", "8069", "8888", "9999"),
            date.fromisoformat(DATA_DATE),
            AVAILABLE_AT,
        ),
    ]

    by_theme = {(row.chain_name, row.theme_name): row for row in snapshot.report.rows}
    partial = by_theme[("半導體", "部分覆蓋")]
    assert partial.institutional_net_shares == 100
    assert partial.coverage.members == 4
    assert partial.coverage.institutional_shares == 2
    assert partial.coverage.institutional_amount == 0
    assert partial.institutional_buy_count == 1
    assert partial.institutional_sell_count == 1

    offset = by_theme[("航運", "相抵為零")]
    assert offset.institutional_net_shares == 0
    assert offset.institutional_buy_count == 1
    assert offset.institutional_sell_count == 1
    assert offset.institutional_flat_count == 0

    negative = by_theme[("光電", "負淨額")]
    assert negative.institutional_net_shares == -7
    assert negative.institutional_sell_count == 1

    raw_zero = by_theme[("電機", "原始零值")]
    assert raw_zero.institutional_net_shares == 0
    assert raw_zero.institutional_flat_count == 1

    for row in snapshot.report.rows:
        assert row.mean_return_pct is None
        assert row.turnover_twd is None
        assert row.volume_multiple_5d is None
        assert row.institutional_net_turnover_twd is None
        assert row.coverage.returns == 0
        assert row.coverage.turnover == 0
        assert row.coverage.volume_history == 0
        assert row.coverage.institutional_amount == 0

    assert sum(row.coverage.members for row in snapshot.report.rows) == 9
    assert sum(row.coverage.institutional_shares for row in snapshot.report.rows) == 6
    assert sum(
        row.institutional_net_shares
        for row in snapshot.report.rows
        if row.institutional_net_shares is not None
    ) == 93
    no_flow = by_theme[("材料", "未回傳資料")]
    assert no_flow.institutional_net_shares is None
    assert no_flow.coverage.institutional_shares == 0


@pytest.mark.parametrize(
    ("scope", "key"),
    [
        ("top", "prices"),
        ("top", "unexpected"),
        ("mapping", "extra"),
        ("mapping", "absolute"),
        ("mapping", "bad_sha"),
        ("mapping", "sha_type"),
        ("institutional", "extra"),
        ("institutional", "source_use_sha256"),
    ],
)
def test_v2_rejects_nonexact_manifest_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    key: str,
) -> None:
    manifest_path, *_ = _write_snapshot_files(tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    if scope == "top":
        manifest[key] = {} if key == "prices" else "unexpected"
    elif scope == "mapping":
        if key == "extra":
            manifest["mapping"][key] = "not-accepted"
        elif key == "absolute":
            manifest["mapping"]["path"] = str(
                (manifest_path.parent / "mapping.csv").resolve()
            )
        elif key == "bad_sha":
            manifest["mapping"]["sha256"] = "A" * 64
        else:
            manifest["mapping"]["sha256"] = 123
    elif key == "extra":
        manifest["institutional"][key] = "not-accepted"
    else:
        manifest["institutional"].pop(key)
    _write_manifest(manifest_path, manifest)
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert probe["reads"] == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("manifest_sha256", "A" * 64),
        ("receipt_sha256", "b" * 63),
        ("source_use_sha256", 123),
    ],
)
def test_v2_rejects_noncanonical_or_wrongtype_source_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid_value: object,
) -> None:
    manifest_path, *_ = _write_snapshot_files(tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["institutional"][field] = invalid_value
    _write_manifest(manifest_path, manifest)
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises((TypeError, ValueError)):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert probe["reads"] == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("daily_directory", "relative/daily_snapshot"),
        ("source_use_path", "missing-source-use.json"),
    ],
)
def test_v2_requires_existing_absolute_institutional_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid_value: str,
) -> None:
    manifest_path, *_ = _write_snapshot_files(tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    path_value = invalid_value
    if field == "source_use_path":
        path_value = str((manifest_path.parent / invalid_value).resolve())
    manifest["institutional"][field] = path_value
    _write_manifest(manifest_path, manifest)
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises((FileNotFoundError, OSError, TypeError, ValueError)):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert probe["reads"] == []


def test_v2_binds_new_taipei_completion_hour_and_expected_manifest_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, *_ = _write_snapshot_files(tmp_path)
    original = manifest_path.read_bytes()
    identity = sha256(original).hexdigest()
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises(ValueError, match="尚未到可用小時"):
        read_theme_research_snapshot(
            manifest_path,
            known_at=AVAILABLE_AT - timedelta(microseconds=1),
            expected_identity_sha256=identity,
        )
    assert probe["reads"] == []

    snapshot = read_theme_research_snapshot(
        manifest_path,
        known_at=AVAILABLE_AT,
        expected_identity_sha256=identity,
    )
    assert snapshot.identity_sha256 == identity
    assert snapshot.report.known_at == AVAILABLE_AT
    assert len(probe["reads"]) == 1

    changed = json.loads(original)
    changed["saved_completed_at"] = "2026-10-19T05:05:13+00:00"
    _write_manifest(manifest_path, changed)
    with pytest.raises(ValueError, match="保存身份SHA256"):
        read_theme_research_snapshot(
            manifest_path,
            known_at=AVAILABLE_AT,
            expected_identity_sha256=identity,
        )
    assert len(probe["reads"]) == 1


def test_v2_rejects_conflicting_market_types_for_same_stock_across_themes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, *_ = _write_snapshot_files(
        tmp_path,
        rows=(
            ("半導體", "晶圓製造", "6488", "tpex"),
            ("航運", "航運零件", "6488", "twse"),
        ),
    )
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert probe["reads"] == []


@pytest.mark.parametrize("unaccepted_market", ["twse", "emerging", "", "TPEX", "上櫃", " tpex "])
def test_v2_rejects_mapping_without_an_exact_upper_listed_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unaccepted_market: str,
) -> None:
    manifest_path, *_ = _write_snapshot_files(
        tmp_path,
        rows=(
            ("半導體", "晶圓製造", "2330", "twse"),
            ("光電", "顯示面板", "7777", unaccepted_market),
        ),
    )
    probe = _install_flow_probe(monkeypatch, ())

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert probe["constructors"] == []
    assert probe["reads"] == []


@pytest.mark.parametrize("changed_file", ["mapping", "manifest"])
def test_v2_rechecks_mapping_and_manifest_after_report_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_file: str,
) -> None:
    manifest_path, mapping_path, *_ = _write_snapshot_files(tmp_path)
    original_build = theme_daily_service.ThemeDailyService.build
    probe = _install_flow_probe(monkeypatch, ())

    def mutate_after_build(service, data_date, known_at):
        report = original_build(service, data_date, known_at)
        target = mapping_path if changed_file == "mapping" else manifest_path
        with target.open("ab") as stream:
            stream.write(b"\n# changed during read\n")
        return report

    monkeypatch.setattr(theme_daily_service.ThemeDailyService, "build", mutate_after_build)

    with pytest.raises(ValueError, match="讀取期間變動"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert len(probe["reads"]) == 1
