"""Candidate source profile 的固定來源、repair overlay 與失敗封閉測試。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import inspect
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from data_module import ml_restatement_research_candidate_source as candidate
from data_module import formal_market_revision, historical_session_revision, excluded_daily_price_revision
from data_module import ml_restatement_research_dataset_v3 as v3
from data_module.ml_restatement_official_market import load_official_market_capture
from data_module.ml_restatement_research_dataset import RestatedDatasetBuilder, _EXPECTED_SNAPSHOT_SHA
from tests.test_ml_restatement_research_dataset_v3 import _rehash, _source_manifest


def _sha(path: Path) -> str:
    return candidate.file_sha256(path)


def _row(day: str, symbol: str) -> dict[str, object]:
    return {
        "日期": day,
        "證券代號": symbol,
        "證券名稱": "測試公司",
        "成交股數": 1000,
        "成交筆數": 10,
        "成交金額": 10000,
        "開盤價": "10.0",
        "最高價": "11.0",
        "最低價": "9.5",
        "收盤價": "10.5",
        "漲跌": "+",
        "漲跌價差": "0.5",
        "最後揭示買價": "10.45",
        "最後揭示買量": 12,
        "最後揭示賣價": "10.55",
        "最後揭示賣量": 14,
        "本益比": "8.0",
    }


@pytest.fixture
def source_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    root = tmp_path / "formal"
    database = root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    database.touch()
    snapshot = root / "output" / "source.sqlite"
    snapshot.parent.mkdir(parents=True)
    source_manifest = snapshot.with_name("source.json")
    source_metadata = {
        "schema_version": "formal-technical-repair.v1",
        "root": str(root),
        "source_db": str(snapshot),
        "source_sha256": "pending",
        "daily_before_hash": "daily-before",
    }
    market_day = date(2026, 9, 23)
    market_values = {
        "日期": "20260923",
        "指數名稱": "TAIEX",
        "收盤指數": 100,
        "漲跌點數": 1,
        "漲跌百分比": None,
        "開盤價": 99,
        "最高價": 101,
        "最低價": 98,
        "收盤價": 100,
        "成交量": 123456,
    }
    session_expected = _row("20260922", "0050")
    session_expected_rows = [session_expected]
    daily_rows = [_row("20260520", "0050"), _row("20260520", "0051")]
    with sqlite3.connect(snapshot) as connection:
        connection.execute(
            "CREATE TABLE market_indices (日期 TEXT,指數名稱 TEXT,收盤指數 REAL,漲跌點數 REAL,"
            "漲跌百分比 REAL,開盤價 REAL,最高價 REAL,最低價 REAL,收盤價 REAL,成交量 REAL)"
        )
        connection.execute(
            "INSERT INTO market_indices VALUES (?,?,?,?,?,?,?,?,?,?)",
            tuple(market_values[field] for field in (
                "日期", "指數名稱", "收盤指數", "漲跌點數", "漲跌百分比", "開盤價",
                "最高價", "最低價", "收盤價", "成交量",
            )),
        )
        daily_columns = list(candidate._SESSION_COLUMNS)
        connection.execute(
            "CREATE TABLE daily_prices (" + ",".join(f'"{column}"' + " TEXT" for column in daily_columns) + ")"
        )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (" + ",".join("?" for _ in daily_columns) + ")",
            [tuple(row[column] for column in daily_columns) for row in [session_expected, *daily_rows]],
        )
        connection.commit()
    snapshot_sha = _sha(snapshot)
    source_metadata["source_sha256"] = snapshot_sha.removeprefix("sha256:")
    source_metadata["daily_before_hash"] = "daily-before"
    source_manifest.write_text(json.dumps(source_metadata), encoding="utf-8")

    capture_path = root / "capture.json"
    capture_path.write_text("{}", encoding="utf-8")
    capture_sha = _sha(capture_path)
    composition_path = capture_path.with_name("composition_receipt.json")
    composition = {
        "status": "pass",
        "manifest_path": str(capture_path),
        "manifest_sha256": capture_sha,
        "snapshot_sha256": snapshot_sha,
        "months": 153,
        "responses": 306,
        "market_rows": 1,
        "fields_checked": 10,
        "raw_response_bytes_and_capture_clocks_preserved": True,
        "producer_sha256": "producer",
        "official_reader_sha256": "reader",
    }
    composition_path.write_text(json.dumps(composition), encoding="utf-8")

    monkeypatch.setattr(candidate, "FORMAL_ROOT", root)
    monkeypatch.setattr(candidate, "FORMAL_DATABASE", database)
    monkeypatch.setattr(candidate, "CANDIDATE_SNAPSHOT", snapshot)
    monkeypatch.setattr(candidate, "CANDIDATE_SOURCE_MANIFEST", source_manifest)
    monkeypatch.setattr(candidate, "CANDIDATE_SNAPSHOT_SHA256", snapshot_sha)
    monkeypatch.setattr(candidate, "CANDIDATE_SOURCE_MANIFEST_SHA256", _sha(source_manifest))
    monkeypatch.setattr(candidate, "CANDIDATE_DAILY_BEFORE_SHA256", "daily-before")
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_CAPTURE", capture_path)
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_CAPTURE_SHA256", capture_sha)
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_COMPOSITION_SHA256", _sha(composition_path))
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_PRODUCER_SHA256", "producer")
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_READER_SHA256", "reader")
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_ROW_COUNT", 1)
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_FIELD_COUNT", 10)
    monkeypatch.setattr(candidate, "CANDIDATE_MARKET_CUTOFF", market_day)
    monkeypatch.setattr(candidate, "EXPECTED_SESSION_DATES", ("20260922",))
    monkeypatch.setattr(candidate, "EXPECTED_SESSION_ROW_COUNT", 1)
    monkeypatch.setattr(candidate, "EXPECTED_PRICE_ROWS", 1)
    monkeypatch.setattr(candidate, "EXPECTED_MAY20_SNAPSHOT_ROWS", 2)
    monkeypatch.setattr(candidate, "EXPECTED_EXCLUSION_KEY_COUNT", 1)
    monkeypatch.setattr(candidate, "EXPECTED_EXCLUSION_MAY20_KEY_COUNT", 1)
    monkeypatch.setattr(candidate, "EXPECTED_CLOSED_DATES", ())

    receipt_path = root / "daily-price-receipt.json"
    receipt_path.write_text(json.dumps({"source_update_columns": ["開盤價"]}), encoding="utf-8")
    plan_path = root / "session-plan.json"
    plan_path.write_text(json.dumps({"rows": session_expected_rows}), encoding="utf-8")
    identities = {
        "market": {"test": "market"},
        "historical_sessions": {"plan_path": str(plan_path)},
        "daily_price": {"receipt_path": str(receipt_path)},
        "excluded_daily_prices": {"key_count": 1},
    }
    monkeypatch.setattr(candidate, "_collect_revision_identities", lambda _db: (identities, ["20260922"]))
    capture = SimpleNamespace(
        manifest_path=capture_path.resolve(),
        manifest_file_sha256=capture_sha,
        available_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        cutoff_date=market_day,
        rows={market_day: {
            "開盤價": Decimal("99"), "最高價": Decimal("101"), "最低價": Decimal("98"),
            "收盤價": Decimal("100"), "收盤指數": Decimal("100"), "成交量": Decimal("123456"),
            "漲跌點數": Decimal("1"),
        }},
    )
    monkeypatch.setattr(candidate, "load_official_market_capture", lambda *_args, **_kwargs: capture)
    monkeypatch.setattr(formal_market_revision, "validate_market_replacement", lambda _db, _rows, **kwargs: kwargs == {"replace_all": True} or pytest.fail("market mode"))
    monkeypatch.setattr(historical_session_revision, "validate_session_replacement", lambda _db, _rows, **kwargs: kwargs == {"replace_all": True} or pytest.fail("session mode"))
    monkeypatch.setattr(excluded_daily_price_revision, "load_exclusion_evidence", lambda _db: [{"keys": [("20260520", "0999")], "closed_dates": [], "plan_sha256": "p", "receipt_sha256": "r", "market_plan_sha256": "m", "acquired_at": "2026-09-23T00:00:00+00:00", "source_start_date": "2026-05-20", "evidence_archive_relative": "evidence"}])
    monkeypatch.setattr(excluded_daily_price_revision, "validate_excluded_daily_price_rows", lambda *_args: None)

    class _FakePriceGuard:
        has_revision = True

        def __init__(self, *_args, **_kwargs):
            pass

        def prepare_frame(self, frame, *, replace_dates=(), **_kwargs):
            assert tuple(replace_dates) == ("20260520",)
            assert len(frame) == 2  # 真實來源中其餘 1,086 列 5/20 資料也需保留
            return frame

        def assert_dates_complete(self, dates):
            assert tuple(dates) == ("20260520",)

    monkeypatch.setattr(candidate, "DailyPriceRevisionWriteGuard", _FakePriceGuard)
    return {
        "snapshot": snapshot,
        "snapshot_sha": snapshot_sha,
        "source_manifest": source_manifest,
        "source_manifest_sha": _sha(source_manifest),
        "market_capture": capture_path,
        "market_sha": capture_sha,
        "formal_database": database,
        "market_values": market_values,
        "capture": capture,
    }


def _write_profile(source_fixture: dict[str, object], profile_path: Path):
    return candidate.write_candidate_source_profile(
        snapshot_db=source_fixture["snapshot"],
        expected_snapshot_sha256=source_fixture["snapshot_sha"],
        source_manifest=source_fixture["source_manifest"],
        expected_source_manifest_sha256=source_fixture["source_manifest_sha"],
        official_market_manifest=source_fixture["market_capture"],
        expected_market_sha256=source_fixture["market_sha"],
        profile_path=profile_path,
        formal_database=source_fixture["formal_database"],
    )


def test_candidate_profile_is_create_only_and_revalidates_receipt_bound_sources(source_fixture, tmp_path):
    profile_path = tmp_path / "custody" / "source_profile.json"
    built = _write_profile(source_fixture, profile_path)
    verified = candidate.verify_candidate_source_profile(
        profile_path, built.profile_file_sha256, formal_database=source_fixture["formal_database"],
    )
    assert verified.snapshot_sha256 == source_fixture["snapshot_sha"]
    assert verified.market_sha256 == source_fixture["market_sha"]
    assert verified.payload["verified_scope"]["may20_corrected_rows"] == 1
    assert verified.payload["verified_scope"]["may20_nonrevision_rows"] == 1
    assert verified.payload["snapshot"]["technical_indicators_read"] is False
    assert verified.payload["validator_source"]["file_sha256"] == _sha(Path(candidate.__file__))
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _write_profile(source_fixture, profile_path)


def test_candidate_profile_rejects_market_value_drift_before_writing(source_fixture, tmp_path, monkeypatch):
    capture = source_fixture["capture"]
    capture.rows[date(2026, 9, 23)]["收盤價"] = Decimal("99")
    profile_path = tmp_path / "bad-source-profile.json"
    with pytest.raises(ValueError, match="market capture 與 snapshot 不同"):
        _write_profile(source_fixture, profile_path)
    assert not profile_path.exists()


def test_candidate_profile_rejects_tampered_profile_hash(source_fixture, tmp_path):
    profile_path = tmp_path / "source_profile.json"
    profile = _write_profile(source_fixture, profile_path)
    profile_path.write_text(profile_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="profile SHA"):
        candidate.verify_candidate_source_profile(
            profile_path, profile.profile_file_sha256, formal_database=source_fixture["formal_database"],
        )


def test_candidate_profile_accepts_same_validator_bytes_after_relocation(source_fixture, tmp_path, monkeypatch):
    profile_path = tmp_path / "source_profile.json"
    profile = _write_profile(source_fixture, profile_path)
    recorded_validator_path = profile.payload["validator_source"]["path"]
    relocated_validator = tmp_path / "relocated" / "candidate_source.py"
    relocated_validator.parent.mkdir()
    relocated_validator.write_bytes(Path(candidate.__file__).read_bytes())
    monkeypatch.setattr(candidate, "__file__", str(relocated_validator))

    verified = candidate.verify_candidate_source_profile(
        profile_path, profile.profile_file_sha256, formal_database=source_fixture["formal_database"],
    )

    assert verified.payload["validator_source"]["path"] == recorded_validator_path
    assert verified.payload["validator_source"]["file_sha256"] == _sha(relocated_validator)


def test_candidate_profile_rejects_changed_validator_bytes(source_fixture, tmp_path, monkeypatch):
    profile_path = tmp_path / "source_profile.json"
    profile = _write_profile(source_fixture, profile_path)
    changed_validator = tmp_path / "changed_candidate_source.py"
    changed_validator.write_bytes(Path(candidate.__file__).read_bytes() + b"\n# changed bytes\n")
    monkeypatch.setattr(candidate, "__file__", str(changed_validator))

    with pytest.raises(ValueError, match="validator SHA"):
        candidate.verify_candidate_source_profile(
            profile_path, profile.profile_file_sha256, formal_database=source_fixture["formal_database"],
        )


def test_candidate_profile_rejects_rehashed_tampered_payload(source_fixture, tmp_path):
    profile_path = tmp_path / "source_profile.json"
    _write_profile(source_fixture, profile_path)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["verified_scope"]["may20_nonrevision_rows"] += 1
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    changed_profile_sha = _sha(profile_path)

    with pytest.raises(ValueError, match="目前 verified source/receipt identities"):
        candidate.verify_candidate_source_profile(
            profile_path, changed_profile_sha, formal_database=source_fixture["formal_database"],
        )


def test_candidate_source_sha_override_is_still_pinned(source_fixture, tmp_path):
    with pytest.raises(ValueError, match="snapshot SHA"):
        candidate.write_candidate_source_profile(
            snapshot_db=source_fixture["snapshot"],
            expected_snapshot_sha256="sha256:" + "0" * 64,
            source_manifest=source_fixture["source_manifest"],
            expected_source_manifest_sha256=source_fixture["source_manifest_sha"],
            official_market_manifest=source_fixture["market_capture"],
            expected_market_sha256=source_fixture["market_sha"],
            profile_path=tmp_path / "must-not-exist.json",
            formal_database=source_fixture["formal_database"],
        )


def test_legacy_builder_snapshot_hash_default_is_unchanged():
    parameter = inspect.signature(RestatedDatasetBuilder.__init__).parameters["expected_snapshot_sha256"]
    assert parameter.default == _EXPECTED_SNAPSHOT_SHA


def test_v3_candidate_snapshot_cannot_drop_profile_reference(tmp_path):
    manifest = _source_manifest(tmp_path)
    candidate_sha = candidate.CANDIDATE_SNAPSHOT_SHA256
    manifest["source_hashes"]["snapshot_db"]["sha256"] = candidate_sha
    manifest["revision"] = candidate_sha
    manifest["source_manifest_hashes"] = v3.expected_v3_source_pairs(manifest)
    _rehash(manifest)
    with pytest.raises(ValueError, match="candidate source profile"):
        v3.validate_v3_manifest_sources(manifest)


def test_v3_candidate_profile_is_identity_bound_and_preflighted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = _source_manifest(tmp_path)
    source_hashes = manifest["source_hashes"]
    snapshot_path = (tmp_path / "candidate-source.sqlite").resolve()
    candidate_sha = candidate.CANDIDATE_SNAPSHOT_SHA256
    source_hashes["snapshot_db"] = {"path": str(snapshot_path), "sha256": candidate_sha}
    profile_path = (tmp_path / "candidate_source_profile.json").resolve()
    source_hashes["candidate_source_profile"] = {
        "path": str(profile_path), "file_sha256": "sha256:" + "a" * 64,
    }
    manifest["revision"] = candidate_sha
    manifest["source_manifest_hashes"] = v3.expected_v3_source_pairs(manifest)
    _rehash(manifest)
    observed = datetime.fromisoformat(manifest["revision_observed_at"])
    market = load_official_market_capture(
        Path(manifest["market_source"]["manifest_path"]),
        expected_file_sha256=manifest["market_source"]["manifest_file_sha256"],
        as_of=observed,
    )
    verified_profile = SimpleNamespace(
        snapshot_db=snapshot_path,
        snapshot_sha256=candidate_sha,
        market_manifest=Path(manifest["market_source"]["manifest_path"]).resolve(),
        market_sha256=manifest["market_source"]["manifest_file_sha256"],
        market_capture=market,
    )
    calls = []

    def verify(path, digest, *, as_of):
        calls.append((path, digest, as_of))
        return verified_profile

    monkeypatch.setattr(v3, "verify_candidate_source_profile", verify)
    validated = v3.validate_v3_manifest_sources(manifest)
    assert validated is market
    assert calls == [(profile_path, "sha256:" + "a" * 64, observed)]
