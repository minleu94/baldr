"""驗證 2026-09-23 修訂來源的 additive candidate-only profile。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

import pandas as pd

from data_module import excluded_daily_price_revision, formal_market_revision, historical_session_revision
from data_module.daily_price_revision_write_guard import DailyPriceRevisionWriteGuard
from data_module.ml_daily_price_revision_gate import REPAIR_RECEIPT_RELATIVE_DIR
from data_module.ml_restatement_official_market import (
    OfficialMarketCapture,
    load_official_market_capture,
)


PROFILE_SCHEMA = "ml-restated-research-candidate-source-profile.v1"
PROFILE_REFERENCE_KEYS = frozenset({"path", "file_sha256"})

FORMAL_ROOT = Path(r"D:\Min\Python\Project\FA_Data")
FORMAL_DATABASE = FORMAL_ROOT / "sqlite" / "twstock.db"
CANDIDATE_SNAPSHOT = FORMAL_ROOT / "output" / "scheduled" / "formal_technical_repair_receipts" / "20260923_run02" / "source.sqlite"
CANDIDATE_SOURCE_MANIFEST = CANDIDATE_SNAPSHOT.with_name("source.json")
CANDIDATE_SNAPSHOT_SHA256 = "sha256:05658755b956680a614aa67fa481971abe83c649e2ea7b39202e3486e232cd65"
CANDIDATE_SOURCE_MANIFEST_SHA256 = "sha256:39fc67ab49b991f4ac46ceb1c49cb973bab270c920201f0878a903cfe73ae2e0"
CANDIDATE_DAILY_BEFORE_SHA256 = "16570e7e93d90997bdecd522f3afbb6abbf53666b81b728df78a29b57e1cfa59"

CANDIDATE_MARKET_CAPTURE = Path(
    r"E:\codex_model_repair_20260923\candidate_formal_repair_run01\official_market\capture.json"
)
CANDIDATE_MARKET_CAPTURE_SHA256 = "sha256:e10d2d4a779850700580e1f3959c834645d533447108a5f642015f8677cc0d4b"
CANDIDATE_MARKET_COMPOSITION_SHA256 = "sha256:1c5804ae6cfa236ef649e3666a62514457390141bfd3f503a3931db31e0eb881"
CANDIDATE_MARKET_PRODUCER_SHA256 = "sha256:4ccdfb16b4c4702f568cccfd1e983242d86d2430e55a9b40f6a7152f5b7d8887"
CANDIDATE_MARKET_READER_SHA256 = "sha256:8850e49797f3b9884b45e7214be7c495eb593ed07e0cc06c63671609c93ce25b"
CANDIDATE_MARKET_ROW_COUNT = 3_106
CANDIDATE_MARKET_FIELD_COUNT = 31_060
CANDIDATE_MARKET_CUTOFF = date(2026, 9, 23)

EXPECTED_MARKET_PLAN_SHA256 = "2c490f8aa336f646e9570f05d2a0c46e68346b3b2ba55d8e2fa2049b3b756d86"
EXPECTED_MARKET_RECEIPT_SHA256 = "c3b7625f10f7a7a4c4784ce6d385911f86f8a4fb2762b66253ff81294f10a58e"
EXPECTED_MARKET_MARKER_SHA256 = "801375e37a6f3c387d80178c775bfa73a1bf21ec914e73f7a014233078c700d2"
EXPECTED_SESSION_PLAN_SHA256 = "c97c3f85c42ec2ab14a0fa39473526e033578ea76a7559b9b186a5a06cb1e96c"
EXPECTED_SESSION_RECEIPT_SHA256 = "03dd86224a5485de5c91b3461e2f4e366abacd5895480e2d34ed8a085433127b"
EXPECTED_SESSION_MARKER_SHA256 = "8eea7d1ffc8a72588612c4b8379f8a2cd63fbedfdd1855cc557dd86bf7d3f21a"
EXPECTED_SESSION_ROW_COUNT = 14_869
EXPECTED_SESSION_DATES = (
    "20141227", "20160130", "20160604", "20160910", "20170218",
    "20170603", "20170930", "20180331", "20181222",
)
EXPECTED_PRICE_RECEIPT_SHA256 = "a157a401b21f3eaac8ae82fd21859161f37acc277fcd3d26a0614ccb6a6d280f"
EXPECTED_PRICE_ROWS = 868
EXPECTED_MAY20_SNAPSHOT_ROWS = 1_954
EXPECTED_EXCLUSION_PLAN_SHA256 = "27a56f4dcec575d7b93c80353b6c0d6430f503013f2aae97e9a8eb0bea47d287"
EXPECTED_EXCLUSION_RECEIPT_SHA256 = "2223d8ce29558d7aca78b69774c6380be7f03f2d91adaf135abddffd67ced617"
EXPECTED_EXCLUSION_MARKER_SHA256 = "f68e4068f9aca157dc1871160df6433900b47c5ad26912b51b711badff2f7573"
EXPECTED_EXCLUSION_KEY_COUNT = 2_942
EXPECTED_EXCLUSION_MAY20_KEY_COUNT = 54
EXPECTED_CLOSED_DATES = ("20160211", "20241002", "20250929")

_MARKET_VALUE_COLUMNS = (
    "開盤價", "最高價", "最低價", "收盤價", "收盤指數", "成交量", "漲跌點數",
)
_SESSION_COLUMNS = (
    "日期", "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
    "最高價", "最低價", "收盤價", "漲跌", "漲跌價差", "最後揭示買價",
    "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比",
)
_SESSION_TEXT_COLUMNS = frozenset({"日期", "證券代號", "證券名稱", "漲跌"})


@dataclass(frozen=True)
class CandidateSourceProfile:
    """已通過本輪固定證據鏈驗證的候選來源。"""

    profile_path: Path
    profile_file_sha256: str
    payload: dict[str, Any]
    snapshot_db: Path
    snapshot_sha256: str
    market_manifest: Path
    market_sha256: str
    market_capture: OfficialMarketCapture


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _path(value: Path | str, label: str) -> Path:
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"候選來源缺少 {label}：{value}") from exc


def _same_path(actual: Path | str, expected: Path | str, label: str) -> Path:
    resolved = _path(actual, label)
    expected_path = Path(expected).expanduser().resolve(strict=False)
    if resolved != expected_path:
        raise ValueError(f"候選來源 {label} 路徑不在已核驗 profile 範圍")
    return resolved


def _sha_matches(path: Path, declared: str, expected: str, label: str) -> None:
    if declared != expected or file_sha256(path) != expected:
        raise ValueError(f"候選來源 {label} SHA 不符")


def _root(database_path: Path) -> Path:
    resolved = database_path.resolve()
    parent = resolved.parent
    return parent.parent if parent.name.casefold() == "sqlite" else parent


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"候選來源證據無法讀取：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"候選來源證據必須是 JSON object：{path}")
    return payload


def _marker_identity(
    database_path: Path,
    relative_dir: Path,
    *,
    schema_version: str,
    plan_schema_version: str,
    receipt_schema_version: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    marker_paths = sorted((_root(database_path) / relative_dir).glob("*/revision.json"))
    if len(marker_paths) != 1:
        raise ValueError(f"候選來源預期一份已套用修訂標記，實際 {len(marker_paths)} 份：{relative_dir}")
    marker_path = marker_paths[0].resolve(strict=True)
    marker = _read_json(marker_path)
    receipt_path = marker_path.parent / "receipt.json"
    plan_path = marker_path.parent / "plan.json"
    receipt_bytes = receipt_path.read_bytes()
    plan_bytes = plan_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    plan = json.loads(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    if (
        marker.get("schema_version") != schema_version
        or marker.get("state") != "applied"
        or marker.get("historical_pit") is not False
        or Path(str(marker.get("database_path", ""))).resolve() != database_path.resolve()
        or receipt.get("schema_version") != receipt_schema_version
        or receipt.get("state") != "applied"
        or receipt.get("plan_sha256") != plan_sha
        or plan.get("schema_version") != plan_schema_version
        or marker.get("receipt_sha256") != receipt_sha
        or marker.get("plan_sha256", plan_sha) != plan_sha
    ):
        raise ValueError(f"候選來源修訂 marker/receipt/plan 鏈不一致：{marker_path}")
    identity = {
        "marker_path": str(marker_path),
        "marker_sha256": file_sha256(marker_path),
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": receipt_sha,
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": plan_sha,
        "observed_at": marker.get("observed_at"),
        "completed_at": receipt.get("completed_at"),
    }
    return identity, plan, marker_path


def _collect_revision_identities(database_path: Path) -> tuple[dict[str, Any], list[str]]:
    market_identity, market_plan, market_marker = _marker_identity(
        database_path,
        formal_market_revision.RECEIPT_DIR,
        schema_version="formal-market-revision.v1",
        plan_schema_version="formal-market-repair.v1",
        receipt_schema_version="formal-market-repair.v1",
    )
    session_identity, session_plan, _session_marker = _marker_identity(
        database_path,
        historical_session_revision.RECEIPT_DIR,
        schema_version="historical-session-revision.v1",
        plan_schema_version="historical-session-repair.v1",
        receipt_schema_version="historical-session-repair.v1",
    )
    if (
        market_identity["plan_sha256"] != EXPECTED_MARKET_PLAN_SHA256
        or market_identity["receipt_sha256"] != EXPECTED_MARKET_RECEIPT_SHA256
        or market_identity["marker_sha256"].removeprefix("sha256:") != EXPECTED_MARKET_MARKER_SHA256
        or session_identity["plan_sha256"] != EXPECTED_SESSION_PLAN_SHA256
        or session_identity["receipt_sha256"] != EXPECTED_SESSION_RECEIPT_SHA256
        or session_identity["marker_sha256"].removeprefix("sha256:") != EXPECTED_SESSION_MARKER_SHA256
    ):
        raise ValueError("候選來源 market/session receipt 不等於本輪已核准修訂")
    session_dates = session_plan.get("dates")
    if (
        not isinstance(session_dates, list)
        or tuple(session_dates) != EXPECTED_SESSION_DATES
        or session_plan.get("rows") is None
        or len(session_plan["rows"]) != EXPECTED_SESSION_ROW_COUNT
    ):
        raise ValueError("候選來源 session 修訂日期或列數不符")
    market_plan_range = (market_plan.get("source_start_date"), market_plan.get("source_end_date"))
    if market_plan_range != ("2014-01-02", "2026-09-23"):
        raise ValueError("候選來源 market 修訂涵蓋範圍不符")
    market_summary = market_plan.get("summary")
    if not isinstance(market_summary, dict) or market_summary.get("after_rows") != CANDIDATE_MARKET_ROW_COUNT:
        raise ValueError("候選來源 market 修訂列數不符")

    price_dir = _root(database_path) / REPAIR_RECEIPT_RELATIVE_DIR
    price_receipt_path = (price_dir / "receipt.json").resolve(strict=True)
    price_receipt = _read_json(price_receipt_path)
    rollback_path = price_dir / "rollback_receipt.json"
    if (
        file_sha256(price_receipt_path).removeprefix("sha256:") != EXPECTED_PRICE_RECEIPT_SHA256
        or price_receipt.get("schema_version") != "historical-price-spike-repair-20260921.v1"
        or price_receipt.get("receipt_kind") != "historical_price_spike_repair"
        or price_receipt.get("status") != "applied"
        or Path(str(price_receipt.get("db_path", ""))).resolve() != database_path.resolve()
        or price_receipt.get("source_date") != "20260520"
        or price_receipt.get("allowlist_count") != EXPECTED_PRICE_ROWS
        or rollback_path.exists()
    ):
        raise ValueError("候選來源 May20 價格修訂 receipt 不符或非 applied")
    for field in ("allowlist_hash", "plan_hash", "canonical_sha256"):
        value = price_receipt.get(field)
        if not isinstance(value, str) or not value.startswith("sha256:"):
            raise ValueError(f"候選來源 May20 receipt 欄位錯誤：{field}")
    price_identity = {
        "receipt_path": str(price_receipt_path),
        "receipt_sha256": file_sha256(price_receipt_path),
        "plan_sha256": price_receipt["plan_hash"],
        "source_date": price_receipt["source_date"],
        "row_count": price_receipt["allowlist_count"],
        "applied_at": price_receipt.get("corrected_at"),
    }

    exclusion_rows = excluded_daily_price_revision.load_exclusion_evidence(database_path)
    if len(exclusion_rows) != 1:
        raise ValueError("候選來源預期一份已套用的錯日排除證據")
    exclusion = exclusion_rows[0]
    exclusion_receipt_path = Path(str(exclusion.get("receipt_path", ""))).resolve(strict=True)
    exclusion_marker_path = exclusion_receipt_path.parent / "revision.json"
    exclusion_marker = _read_json(exclusion_marker_path)
    keys = sorted((str(day), str(symbol)) for day, symbol in exclusion.get("keys", []))
    closed_dates = sorted(str(day) for day in exclusion.get("closed_dates", []))
    may20_keys = [key for key in keys if key[0] == "20260520"]
    if (
        exclusion.get("plan_sha256") != EXPECTED_EXCLUSION_PLAN_SHA256
        or exclusion.get("receipt_sha256") != EXPECTED_EXCLUSION_RECEIPT_SHA256
        or file_sha256(exclusion_marker_path).removeprefix("sha256:") != EXPECTED_EXCLUSION_MARKER_SHA256
        or exclusion_marker.get("schema_version") != "excluded-daily-price-revision.v1"
        or exclusion_marker.get("state") != "applied"
        or len(keys) != EXPECTED_EXCLUSION_KEY_COUNT
        or tuple(closed_dates) != EXPECTED_CLOSED_DATES
        or len(may20_keys) != EXPECTED_EXCLUSION_MAY20_KEY_COUNT
        or exclusion.get("market_plan_sha256") != EXPECTED_MARKET_PLAN_SHA256
    ):
        raise ValueError("候選來源錯日排除 evidence identities/scope 不符")
    exclusion_identity = {
        "receipt_path": str(exclusion_receipt_path),
        "receipt_sha256": str(exclusion["receipt_sha256"]),
        "plan_sha256": str(exclusion["plan_sha256"]),
        "marker_path": str(exclusion_marker_path.resolve()),
        "marker_sha256": file_sha256(exclusion_marker_path),
        "market_plan_sha256": str(exclusion["market_plan_sha256"]),
        "closed_dates": closed_dates,
        "key_count": len(keys),
        "may20_exact_key_count": len(may20_keys),
        "keys_sha256": "sha256:" + hashlib.sha256(_canonical_json([list(key) for key in keys])).hexdigest(),
        "acquired_at": exclusion.get("acquired_at"),
        "source_start_date": exclusion.get("source_start_date"),
        "evidence_archive_relative": exclusion.get("evidence_archive_relative"),
    }
    return {
        "market": market_identity,
        "historical_sessions": session_identity,
        "daily_price": price_identity,
        "excluded_daily_prices": exclusion_identity,
    }, list(session_dates)


def _number(value: object, label: str) -> Decimal:
    if value is None or str(value).strip() in {"", "nan", "NaN", "<NA>", "--"}:
        raise ValueError(f"候選來源 market 欄位缺值：{label}")
    try:
        result = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"候選來源 market 欄位無法解析：{label}") from exc
    if not result.is_finite():
        raise ValueError(f"候選來源 market 欄位不是有限值：{label}")
    return result


def _market_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = connection.execute(
        "SELECT 日期,指數名稱,收盤指數,漲跌點數,漲跌百分比,開盤價,最高價,最低價,收盤價,成交量 "
        "FROM market_indices WHERE 指數名稱='TAIEX' ORDER BY 日期"
    )
    return [dict(row) for row in cursor.fetchall()]


def _assert_market_capture_matches_snapshot(
    capture: OfficialMarketCapture,
    snapshot_rows: Sequence[Mapping[str, Any]],
) -> None:
    expected_by_day: dict[date, Mapping[str, Any]] = {}
    for row in snapshot_rows:
        raw = str(row.get("日期", "")).replace("-", "").replace("/", "")[:8]
        try:
            day = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"候選來源 market 日期格式不符：{raw}") from exc
        if day in expected_by_day:
            raise ValueError(f"候選來源 market 日期重複：{raw}")
        expected_by_day[day] = row
    if len(expected_by_day) != CANDIDATE_MARKET_ROW_COUNT or set(expected_by_day) != set(capture.rows):
        raise ValueError("候選來源 market 官方日曆必須與修訂快照 3,106 日完全一致")
    if capture.cutoff_date != CANDIDATE_MARKET_CUTOFF or max(capture.rows) != CANDIDATE_MARKET_CUTOFF:
        raise ValueError("候選來源 official capture 未涵蓋 2026-09-23")
    for day, official in capture.rows.items():
        source = expected_by_day[day]
        for field in _MARKET_VALUE_COLUMNS:
            if _number(source.get(field), f"{day}/{field}") != _number(official.get(field), f"{day}/{field}/official"):
                raise ValueError(f"候選來源 market capture 與 snapshot 不同：{day}/{field}")


def _read_session_rows(connection: sqlite3.Connection, dates: Sequence[str]) -> list[dict[str, Any]]:
    if not dates:
        raise ValueError("候選來源缺少已修訂 session 日期")
    placeholders = ",".join("?" for _ in dates)
    cursor = connection.execute(
        "SELECT " + ",".join(_SESSION_COLUMNS) + " FROM daily_prices "
        f"WHERE 日期 IN ({placeholders}) ORDER BY 日期,證券代號",
        tuple(dates),
    )
    return [dict(row) for row in cursor.fetchall()]


def _session_key(row: Mapping[str, Any]) -> tuple[str, str]:
    raw_date = str(row.get("日期", "")).replace("-", "").replace("/", "")[:8]
    return raw_date, str(row.get("證券代號", "")).strip()


def _assert_session_rows_match_plan(
    actual_rows: Sequence[Mapping[str, Any]],
    expected_rows: Sequence[Mapping[str, Any]],
) -> None:
    actual_by_key = {_session_key(row): row for row in actual_rows}
    expected_by_key = {_session_key(row): row for row in expected_rows}
    if len(actual_by_key) != len(actual_rows) or len(expected_by_key) != len(expected_rows):
        raise ValueError("候選來源補回 session 有重複 key")
    if set(actual_by_key) != set(expected_by_key):
        raise ValueError("候選來源補回 session key 集合與 applied plan 不同")
    for key, expected in expected_by_key.items():
        actual = actual_by_key[key]
        for column in _SESSION_COLUMNS:
            value, wanted = actual.get(column), expected.get(column)
            if column in _SESSION_TEXT_COLUMNS:
                if value != wanted:
                    raise ValueError(f"候選來源補回 session 欄位與 applied plan 不同：{key}/{column}")
                continue
            if value is None or wanted is None:
                if value is not None or wanted is not None:
                    raise ValueError(f"候選來源補回 session 缺值與 applied plan 不同：{key}/{column}")
                continue
            if _number(value, f"{key}/{column}") != _number(wanted, f"{key}/{column}/plan"):
                raise ValueError(f"候選來源補回 session 數值與 applied plan 不同：{key}/{column}")


def _read_daily_price_rows(connection: sqlite3.Connection, source_date: str, columns: Sequence[str]) -> list[dict[str, Any]]:
    available = {str(row[1]) for row in connection.execute("PRAGMA table_info(daily_prices)")}
    requested = [name for name in ("日期", "證券代號", *columns) if name in available]
    if set(columns) - set(requested):
        raise ValueError("候選來源 daily_prices 缺少 May20 修訂欄位")
    cursor = connection.execute(
        "SELECT " + ",".join(f'"{name}"' for name in requested) +
        " FROM daily_prices WHERE 日期=? ORDER BY 證券代號",
        (source_date,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _validate_daily_repair_source(
    database_path: Path,
    connection: sqlite3.Connection,
    revision_identity: Mapping[str, Any],
) -> None:
    receipt_path = Path(str(revision_identity["receipt_path"]))
    receipt = _read_json(receipt_path)
    columns = receipt.get("source_update_columns")
    if not isinstance(columns, list) or any(not isinstance(column, str) for column in columns):
        raise ValueError("候選來源 May20 receipt 缺少修訂欄位")
    rows = _read_daily_price_rows(connection, "20260520", columns)
    if len(rows) != EXPECTED_MAY20_SNAPSHOT_ROWS:
        raise ValueError("候選來源 May20 全日 rows 數量不符")
    guard = DailyPriceRevisionWriteGuard(database_path)
    if not guard.has_revision:
        raise ValueError("候選來源缺少已套用 May20 價格修訂")
    frame = pd.DataFrame(rows)
    guard.prepare_frame(frame, replace_dates=("20260520",))
    guard.assert_dates_complete(("20260520",))


def _validate_exclusion_source(
    database_path: Path,
    connection: sqlite3.Connection,
    exclusion_identity: Mapping[str, Any],
) -> None:
    evidence = excluded_daily_price_revision.load_exclusion_evidence(database_path)
    if len(evidence) != 1:
        raise ValueError("候選來源錯日排除 evidence 在驗證期間變更")
    dates = sorted({str(day) for day, _symbol in evidence[0]["keys"]})
    placeholders = ",".join("?" for _ in dates)
    cursor = connection.execute(
        f"SELECT 日期,證券代號 FROM daily_prices WHERE 日期 IN ({placeholders}) ORDER BY 日期,證券代號",
        tuple(dates),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    excluded_daily_price_revision.validate_excluded_daily_price_rows(database_path, rows)
    if exclusion_identity.get("key_count") != EXPECTED_EXCLUSION_KEY_COUNT:
        raise ValueError("候選來源錯日排除範圍驗證失敗")


def _validate_profile_inputs(
    *,
    snapshot_db: Path,
    expected_snapshot_sha256: str,
    source_manifest: Path,
    expected_source_manifest_sha256: str,
    official_market_manifest: Path,
    expected_market_sha256: str,
    formal_database: Path,
    as_of: datetime,
) -> tuple[dict[str, Any], OfficialMarketCapture]:
    snapshot_path = _same_path(snapshot_db, CANDIDATE_SNAPSHOT, "run02 source.sqlite")
    source_json_path = _same_path(source_manifest, CANDIDATE_SOURCE_MANIFEST, "run02 source.json")
    market_path = _same_path(official_market_manifest, CANDIDATE_MARKET_CAPTURE, "official market capture")
    database_path = _same_path(formal_database, FORMAL_DATABASE, "formal database")
    _sha_matches(snapshot_path, expected_snapshot_sha256, CANDIDATE_SNAPSHOT_SHA256, "snapshot")
    _sha_matches(source_json_path, expected_source_manifest_sha256, CANDIDATE_SOURCE_MANIFEST_SHA256, "source.json")
    if not database_path.is_file():
        raise ValueError("候選來源 formal DB 不存在")

    source_metadata = _read_json(source_json_path)
    if (
        source_metadata.get("schema_version") != "formal-technical-repair.v1"
        or Path(str(source_metadata.get("root", ""))).resolve() != FORMAL_ROOT.resolve()
        or Path(str(source_metadata.get("source_db", ""))).resolve() != snapshot_path
        or source_metadata.get("source_sha256") != CANDIDATE_SNAPSHOT_SHA256.removeprefix("sha256:")
        or source_metadata.get("daily_before_hash") != CANDIDATE_DAILY_BEFORE_SHA256
    ):
        raise ValueError("候選來源 source.json 未綁定 run02 immutable snapshot")

    composition_path = (market_path.parent / "composition_receipt.json").resolve(strict=True)
    _sha_matches(market_path, expected_market_sha256, CANDIDATE_MARKET_CAPTURE_SHA256, "official capture")
    _sha_matches(
        composition_path,
        file_sha256(composition_path),
        CANDIDATE_MARKET_COMPOSITION_SHA256,
        "official capture composition receipt",
    )
    composition = _read_json(composition_path)
    if (
        composition.get("status") != "pass"
        or Path(str(composition.get("manifest_path", ""))).resolve() != market_path
        or composition.get("manifest_sha256") != expected_market_sha256
        or composition.get("snapshot_sha256") != CANDIDATE_SNAPSHOT_SHA256
        or composition.get("months") != 153
        or composition.get("responses") != 306
        or composition.get("market_rows") != CANDIDATE_MARKET_ROW_COUNT
        or composition.get("fields_checked") != CANDIDATE_MARKET_FIELD_COUNT
        or composition.get("raw_response_bytes_and_capture_clocks_preserved") is not True
        or composition.get("producer_sha256") != CANDIDATE_MARKET_PRODUCER_SHA256
        or composition.get("official_reader_sha256") != CANDIDATE_MARKET_READER_SHA256
    ):
        raise ValueError("候選來源 official capture composition evidence 不符")

    capture = load_official_market_capture(
        market_path, expected_file_sha256=expected_market_sha256, as_of=as_of,
    )
    if len(capture.rows) != CANDIDATE_MARKET_ROW_COUNT:
        raise ValueError("候選來源 official market capture 列數不符")

    revision_identities, session_dates = _collect_revision_identities(database_path)
    uri = f"file:{snapshot_path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        market_rows = _market_rows(connection)
        _assert_market_capture_matches_snapshot(capture, market_rows)
        formal_market_revision.validate_market_replacement(
            database_path, market_rows, replace_all=True,
        )
        session_rows = _read_session_rows(connection, session_dates)
        if len(session_rows) != EXPECTED_SESSION_ROW_COUNT:
            raise ValueError("候選來源已補回 9 個 session 的完整 rows 缺漏")
        historical_session_revision.validate_session_replacement(
            database_path, session_rows, replace_all=True,
        )
        session_plan = _read_json(Path(revision_identities["historical_sessions"]["plan_path"]))
        _assert_session_rows_match_plan(session_rows, session_plan["rows"])
        _validate_daily_repair_source(database_path, connection, revision_identities["daily_price"])
        _validate_exclusion_source(database_path, connection, revision_identities["excluded_daily_prices"])
    finally:
        connection.close()

    payload: dict[str, Any] = {
        "schema_version": PROFILE_SCHEMA,
        "profile_kind": "candidate_only_formal_source_repair",
        "historical_pit": False,
        "formal_oos": False,
        "promotion_eligible": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": {
            "path": str(snapshot_path),
            "sha256": expected_snapshot_sha256,
            "source_manifest_path": str(source_json_path),
            "source_manifest_sha256": expected_source_manifest_sha256,
            "daily_before_hash": CANDIDATE_DAILY_BEFORE_SHA256,
            "technical_indicators_read": False,
        },
        "formal_database_path": str(database_path),
        "repair_evidence": revision_identities,
        "validator_source": {
            "path": str(Path(__file__).resolve()),
            "file_sha256": file_sha256(Path(__file__).resolve()),
        },
        "official_market_capture": {
            "path": str(market_path),
            "file_sha256": expected_market_sha256,
            "composition_receipt_path": str(composition_path),
            "composition_receipt_sha256": file_sha256(composition_path),
            "available_at": capture.available_at.isoformat(),
            "cutoff_date": capture.cutoff_date.isoformat(),
            "row_count": len(capture.rows),
            "session_date_count": len(session_dates),
        },
        "verified_scope": {
            "market_rows": CANDIDATE_MARKET_ROW_COUNT,
            "market_fields": CANDIDATE_MARKET_FIELD_COUNT,
            "historical_session_dates": session_dates,
            "historical_session_rows": EXPECTED_SESSION_ROW_COUNT,
            "may20_corrected_rows": EXPECTED_PRICE_ROWS,
            "may20_snapshot_rows": EXPECTED_MAY20_SNAPSHOT_ROWS,
            "may20_nonrevision_rows": EXPECTED_MAY20_SNAPSHOT_ROWS - EXPECTED_PRICE_ROWS,
            "excluded_daily_price_keys": EXPECTED_EXCLUSION_KEY_COUNT,
            "excluded_may20_exact_keys": EXPECTED_EXCLUSION_MAY20_KEY_COUNT,
            "closed_dates": list(EXPECTED_CLOSED_DATES),
        },
    }
    return payload, capture


def write_candidate_source_profile(
    *,
    snapshot_db: Path,
    expected_snapshot_sha256: str,
    source_manifest: Path,
    expected_source_manifest_sha256: str,
    official_market_manifest: Path,
    expected_market_sha256: str,
    profile_path: Path,
    formal_database: Path = FORMAL_DATABASE,
) -> CandidateSourceProfile:
    """驗證固定來源與全部 applied receipts 後，create-only 寫一份外部 profile。"""
    target = profile_path.expanduser().resolve(strict=False)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite candidate source profile: {target}")
    validator_path = Path(__file__).resolve()
    validator_sha_start = file_sha256(validator_path)
    payload, capture = _validate_profile_inputs(
        snapshot_db=snapshot_db,
        expected_snapshot_sha256=expected_snapshot_sha256,
        source_manifest=source_manifest,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        official_market_manifest=official_market_manifest,
        expected_market_sha256=expected_market_sha256,
        formal_database=formal_database,
        as_of=datetime.now(timezone.utc),
    )
    if file_sha256(validator_path) != validator_sha_start:
        raise ValueError("candidate source validator changed while creating profile")
    if payload["validator_source"]["file_sha256"] != validator_sha_start:
        raise ValueError("candidate source validator identity changed while creating profile")
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    digest = file_sha256(target)
    return CandidateSourceProfile(
        profile_path=target,
        profile_file_sha256=digest,
        payload=payload,
        snapshot_db=Path(payload["snapshot"]["path"]),
        snapshot_sha256=str(payload["snapshot"]["sha256"]),
        market_manifest=Path(payload["official_market_capture"]["path"]),
        market_sha256=str(payload["official_market_capture"]["file_sha256"]),
        market_capture=capture,
    )


def verify_candidate_source_profile(
    profile_path: Path,
    expected_file_sha256: str,
    *,
    formal_database: Path = FORMAL_DATABASE,
    as_of: datetime | None = None,
) -> CandidateSourceProfile:
    """重驗 profile bytes、固定來源、receipts、snapshot列與official市場列。"""
    target = _path(profile_path, "candidate source profile")
    if file_sha256(target) != expected_file_sha256 or not expected_file_sha256.startswith("sha256:"):
        raise ValueError("candidate source profile SHA 不符")
    payload = _read_json(target)
    if (
        payload.get("schema_version") != PROFILE_SCHEMA
        or payload.get("profile_kind") != "candidate_only_formal_source_repair"
        or payload.get("historical_pit") is not False
        or payload.get("formal_oos") is not False
        or payload.get("promotion_eligible") is not False
    ):
        raise ValueError("candidate source profile schema 或研究限制不符")
    snapshot = payload.get("snapshot")
    capture_payload = payload.get("official_market_capture")
    validator_source = payload.get("validator_source")
    if not isinstance(snapshot, dict) or not isinstance(capture_payload, dict):
        raise ValueError("candidate source profile 缺少來源 identity")
    if not isinstance(validator_source, dict):
        raise ValueError("candidate source profile 缺少 validator source identity")
    validator_path = Path(__file__).resolve()
    validator_sha_start = file_sha256(validator_path)
    recorded_validator_path = validator_source.get("path")
    if (
        not isinstance(recorded_validator_path, str)
        or not Path(recorded_validator_path).is_absolute()
        or validator_source.get("file_sha256") != validator_sha_start
    ):
        raise ValueError("candidate source profile validator SHA 不符")
    verified_payload, capture = _validate_profile_inputs(
        snapshot_db=Path(str(snapshot.get("path", ""))),
        expected_snapshot_sha256=str(snapshot.get("sha256", "")),
        source_manifest=Path(str(snapshot.get("source_manifest_path", ""))),
        expected_source_manifest_sha256=str(snapshot.get("source_manifest_sha256", "")),
        official_market_manifest=Path(str(capture_payload.get("path", ""))),
        expected_market_sha256=str(capture_payload.get("file_sha256", "")),
        formal_database=formal_database,
        as_of=as_of or datetime.now(timezone.utc),
    )
    created_at = payload.get("created_at")
    if not isinstance(created_at, str):
        raise ValueError("candidate source profile 缺少建立時鐘")
    created_clock = datetime.fromisoformat(created_at)
    current_clock = as_of or datetime.now(timezone.utc)
    if created_clock.tzinfo is None or created_clock.utcoffset() is None or created_clock > current_clock:
        raise ValueError("candidate source profile 建立時鐘無效")
    verified_payload["created_at"] = created_at
    if (
        file_sha256(validator_path) != validator_sha_start
        or verified_payload["validator_source"]["file_sha256"] != validator_sha_start
    ):
        raise ValueError("candidate profile validator code changed during verification")
    # 建立時路徑保留作來源紀錄；程式身分以內容雜湊核對。
    verified_payload["validator_source"]["path"] = recorded_validator_path
    if _canonical_json(payload) != _canonical_json(verified_payload):
        raise ValueError("candidate source profile 與目前 verified source/receipt identities 不一致")
    return CandidateSourceProfile(
        profile_path=target,
        profile_file_sha256=expected_file_sha256,
        payload=payload,
        snapshot_db=Path(str(snapshot["path"])),
        snapshot_sha256=str(snapshot["sha256"]),
        market_manifest=Path(str(capture_payload["path"])),
        market_sha256=str(capture_payload["file_sha256"]),
        market_capture=capture,
    )


def candidate_profile_reference(profile: CandidateSourceProfile) -> dict[str, str]:
    """V3 manifest 的唯一 additive reference，仍由 source_hashes identity hash 綁定。"""
    return {
        "path": str(profile.profile_path.resolve()),
        "file_sha256": profile.profile_file_sha256,
    }
