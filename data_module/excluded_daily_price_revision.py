"""驗證官方證明的錯日價量列排除修訂及其歷史來源保護。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import parse_qs, urlparse


RECEIPT_DIR = Path("output/scheduled/excluded_daily_price_repair_receipts")
SOURCE_DIR = Path("output/scheduled/excluded_daily_price_repair_sources")
SCHEMA = "excluded-daily-price-repair.v1"
REVISION_SCHEMA = "excluded-daily-price-revision.v1"
OFFICIAL_DATES = ("20160211", "20241002", "20250929", "20260520")
CLOSED_DATES = ("20160211", "20241002", "20250929")
_EVIDENCE_FILES = tuple(
    f"{venue}-{day}.{suffix}"
    for day in OFFICIAL_DATES
    for venue in ("twse", "tpex")
    for suffix in ("json", "receipt.json")
)
_CLOSURE_TPEX_ROC = {
    "20160211": "105/02/11",
    "20241002": "113/10/02",
    "20250929": "114/09/29",
    "20260520": "115/05/20",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE_FIELDS = ("日期", "date", "Date", "trading_date", "tradingDate")
_SYMBOL_FIELDS = ("證券代號", "代號", "symbol", "stock_id", "code", "ticker")


def _encoded(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必須是物件：{path}")
    return value


def _root(database_path: Path) -> Path:
    resolved = Path(database_path).resolve()
    parent = resolved.parent
    return parent.parent if parent.name.lower() == "sqlite" else parent


def _resolve_relative(root: Path, value: object, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("修訂路徑必須是資料根目錄下的相對 POSIX 路徑")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("修訂路徑越界")
    candidate = root.joinpath(*relative.parts)
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("修訂路徑越界資料根目錄") from exc
    return resolved


def _normal_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip().replace("-", "").replace("/", "")
    if not re.fullmatch(r"\d{8}", text):
        raise ValueError(f"日期格式不符：{value!r}")
    date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return text


def _normal_symbol(value: object) -> str:
    if value is None:
        raise ValueError("缺少證券代號")
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if not text or text.lower() in {"nan", "<na>", "none"}:
        raise ValueError("缺少證券代號")
    return text.upper()


def _clock(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"缺少實際取得時鐘：{name}")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"取得時鐘必須含時區：{name}")
    return result


def _verify_archive(
    root: Path,
    archive_relative: object,
    expected_archive_sha256: object,
    source_files: object,
) -> tuple[dict[str, Any], datetime, set[str]]:
    """驗證封存的八份官方回應、八個 acquisition receipt 和 archive manifest。"""
    archive_dir = _resolve_relative(root, archive_relative)
    if not archive_dir.relative_to(root.resolve()).as_posix().startswith(
        SOURCE_DIR.as_posix() + "/"
    ):
        raise ValueError("官方來源封存目錄不在指定來源區")
    archive_path = archive_dir / "archive.json"
    archive_bytes = archive_path.read_bytes()
    if _hash_bytes(archive_bytes) != expected_archive_sha256:
        raise ValueError("官方來源 archive manifest hash 不符")
    archive = _read_json(archive_path)
    if archive.get("historical_pit") is not False:
        raise ValueError("官方證據不得宣稱歷史 PIT")
    entries = archive.get("files")
    if not isinstance(entries, list):
        raise ValueError("官方來源 archive 缺少 files")
    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("官方來源 archive entry 格式不符")
        archived = entry.get("archived")
        name = Path(str(archived)).name
        if name in by_name:
            raise ValueError("官方來源 archive 檔名重複")
        expected_path = (archive_dir / name).resolve(strict=True)
        if Path(str(archived)).resolve(strict=True) != expected_path:
            raise ValueError("官方來源 archive 路徑不符")
        by_name[name] = entry
    if set(by_name) != set(_EVIDENCE_FILES):
        raise ValueError("官方來源 archive 必須剛好包含八份回應及八份 receipt")

    declared = source_files
    if not isinstance(declared, list) or len(declared) != len(_EVIDENCE_FILES):
        raise ValueError("修訂計畫缺少完整官方來源清冊")
    declared_by_name = {item.get("name"): item for item in declared if isinstance(item, dict)}
    if set(declared_by_name) != set(_EVIDENCE_FILES):
        raise ValueError("修訂計畫官方來源清冊與 archive 不符")
    received: list[datetime] = []
    payloads: dict[tuple[str, str], dict[str, Any]] = {}
    for day in OFFICIAL_DATES:
        for venue in ("twse", "tpex"):
            payload_name = f"{venue}-{day}.json"
            receipt_name = f"{venue}-{day}.receipt.json"
            for name in (payload_name, receipt_name):
                entry = by_name[name]
                path = archive_dir / name
                data = path.read_bytes()
                actual_hash = _hash_bytes(data)
                item = declared_by_name[name]
                if (
                    actual_hash != entry.get("sha256")
                    or actual_hash != item.get("sha256")
                    or len(data) != entry.get("bytes")
                    or len(data) != item.get("bytes")
                ):
                    raise ValueError(f"官方來源 hash/大小不符：{name}")
            body = _read_json(archive_dir / payload_name)
            receipt = _read_json(archive_dir / receipt_name)
            expected_url = _expected_url(venue, day)
            captured_at = _clock(receipt.get("captured_at"), f"{venue}/{day}")
            if (
                receipt.get("venue") != venue
                or receipt.get("date") != day
                or receipt.get("http_status") != 200
                or receipt.get("historical_pit") is not False
                or receipt.get("url") != expected_url
                or receipt.get("sha256") != _hash_file(archive_dir / payload_name)
            ):
                raise ValueError(f"官方來源 receipt 不符：{receipt_name}")
            if receipt_name in declared_by_name and declared_by_name[receipt_name].get(
                "captured_at"
            ) != receipt.get("captured_at"):
                raise ValueError(f"官方來源取得時鐘與計畫不符：{receipt_name}")
            received.append(captured_at)
            payloads[(venue, day)] = body
    _validate_official_payloads(payloads)
    twse_table = next(
        table for table in payloads[("twse", "20260520")]["tables"]
        if isinstance(table, dict) and str(table.get("title", "")).endswith("每日收盤行情(全部)")
    )
    tpex_table = payloads[("tpex", "20260520")]["tables"][0]
    official_codes = _unique_codes(
        twse_table["data"], expected_width=len(twse_table["fields"]), label="TWSE 20260520",
    ) | _unique_codes(
        tpex_table["data"], expected_width=len(tpex_table["fields"]), label="TPEx 20260520",
    )
    if not received:
        raise ValueError("官方來源缺少取得時鐘")
    return archive, max(received), official_codes


def _expected_url(venue: str, day: str) -> str:
    if venue == "twse":
        return f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={day}&type=ALL&response=json"
    if venue == "tpex":
        year, month, number = day[:4], day[4:6], day[6:]
        return (
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?"
            f"date={year}%2F{month}%2F{number}&type=EW&response=json"
        )
    raise ValueError("未知官方市場")


def _validate_official_payloads(payloads: Mapping[tuple[str, str], dict[str, Any]]) -> None:
    for day in CLOSED_DATES:
        twse = payloads[("twse", day)]
        if twse != {"stat": "很抱歉，沒有符合條件的資料!", "type": "ALL"}:
            raise ValueError(f"TWSE 未證明整日無資料：{day}")
        tpex = payloads[("tpex", day)]
        tables = tpex.get("tables")
        if (
            tpex.get("stat") != "ok"
            or tpex.get("date") != day
            or not isinstance(tables, list)
            or len(tables) != 1
            or tables[0].get("title") != "上櫃股票每日收盤行情(不含定價)"
            or tables[0].get("date") != _CLOSURE_TPEX_ROC[day]
            or tables[0].get("totalCount") != 0
            or tables[0].get("data") != []
        ):
            raise ValueError(f"TPEx 未證明整日無資料：{day}")
    twse = payloads[("twse", "20260520")]
    if twse.get("stat") != "OK" or twse.get("date") != "20260520" or twse.get("type") != "ALL":
        raise ValueError("TWSE 20260520 回應不是完整 ALL 報表")
    twse_tables = [
        table for table in twse.get("tables", [])
        if isinstance(table, dict) and str(table.get("title", "")).endswith("每日收盤行情(全部)")
    ]
    expected_twse_fields = [
        "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價",
        "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量",
        "最後揭示賣價", "最後揭示賣量", "本益比",
    ]
    if len(twse_tables) != 1 or twse_tables[0].get("fields") != expected_twse_fields:
        raise ValueError("TWSE 20260520 每日收盤行情表缺少完整欄位")
    twse_rows = twse_tables[0].get("data")
    if not isinstance(twse_rows, list) or len(twse_rows) != 31124:
        raise ValueError("TWSE 20260520 ALL 行數不符完整捕獲證據")
    _unique_codes(twse_rows, expected_width=len(expected_twse_fields), label="TWSE 20260520")
    tpex = payloads[("tpex", "20260520")]
    tpex_tables = tpex.get("tables")
    if (
        tpex.get("stat") != "ok"
        or tpex.get("date") != "20260520"
        or not isinstance(tpex_tables, list)
        or len(tpex_tables) != 1
        or tpex_tables[0].get("title") != "上櫃股票每日收盤行情(不含定價)"
        or tpex_tables[0].get("date") != _CLOSURE_TPEX_ROC["20260520"]
        or tpex_tables[0].get("totalCount") != 1007
    ):
        raise ValueError("TPEx 20260520 未包含完整收盤報表")
    tpex_rows = tpex_tables[0].get("data")
    if not isinstance(tpex_rows, list) or len(tpex_rows) != 1007:
        raise ValueError("TPEx 20260520 行數不符完整捕獲證據")
    _unique_codes(tpex_rows, expected_width=len(tpex_tables[0].get("fields", [])), label="TPEx 20260520")


def _unique_codes(rows: list[Any], *, expected_width: int, label: str) -> set[str]:
    codes: set[str] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != expected_width:
            raise ValueError(f"{label} 欄位列長度不一致")
        code = _normal_symbol(row[0])
        if code in codes:
            raise ValueError(f"{label} 證券代號重複：{code}")
        codes.add(code)
    return codes


def _validate_market_chain(
    database_path: Path,
    root: Path,
    market_relative: object,
    *,
    full_source_validation: bool,
) -> dict[str, Any]:
    market_dir = _resolve_relative(root, market_relative)
    revision_path = market_dir / "revision.json"
    marker = _read_json(revision_path)
    journal = _read_json(market_dir / "journal.json")
    receipt_bytes = (market_dir / "receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    plan_bytes = (market_dir / "plan.json").read_bytes()
    plan_sha = _hash_bytes(plan_bytes)
    if (
        marker.get("schema_version") != "formal-market-revision.v1"
        or marker.get("state") != "applied"
        or Path(str(marker.get("database_path"))).resolve() != Path(database_path).resolve()
        or marker.get("receipt_sha256") != _hash_bytes(receipt_bytes)
        or journal.get("schema_version") != "formal-market-repair.v1"
        or journal.get("state") != "prepared"
        or journal.get("plan_sha256") != plan_sha
        or receipt.get("state") != "applied"
        or receipt.get("plan_sha256") != plan_sha
    ):
        raise ValueError("正式市場修訂 receipt/journal/plan 鏈不符")
    if marker.get("plan_sha256", plan_sha) != plan_sha:
        raise ValueError("正式市場修訂標記 plan hash 不符")
    plan = json.loads(plan_bytes)
    if plan.get("database_path") != str(Path(database_path).resolve()):
        raise ValueError("正式市場修訂資料庫路徑不符")
    sources = plan.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("正式市場計畫缺少雙報表封存來源")
    required_months = {day[:6] for day in CLOSED_DATES}
    covered: set[str] = set()
    absent_dates: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            raise ValueError("正式市場來源清冊格式不符")
        source_path = Path(source["path"]).resolve(strict=True)
        try:
            source_path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("正式市場來源清冊越界") from exc
        if full_source_validation:
            from data_module.ml_restatement_official_market import load_official_market_capture

            capture = load_official_market_capture(
                source_path,
                expected_file_sha256="sha256:" + str(source.get("sha256", "")).removeprefix("sha256:"),
                as_of=datetime.now(timezone.utc),
            )
            covered.update(month.strftime("%Y%m") for month in capture.rows)
            absent_dates.update(
                day for day in CLOSED_DATES
                if date(int(day[:4]), int(day[4:6]), int(day[6:8])) not in capture.rows
            )
        else:
            if _hash_file(source_path) != str(source.get("sha256", "")).removeprefix("sha256:"):
                raise ValueError("正式市場來源清冊 hash 不符")
            manifest = _read_json(source_path)
            months = manifest.get("months")
            receipts = manifest.get("receipts")
            if not isinstance(months, list) or not isinstance(receipts, list):
                raise ValueError("正式市場來源清冊月份／receipt 欄位不完整")
            covered.update(str(month) for month in months)
            pairs = {(str(item.get("month")), str(item.get("report"))) for item in receipts if isinstance(item, dict)}
            for month in required_months & set(map(str, months)):
                if not {(month, "FMTQIK"), (month, "MI_5MINS_HIST")} <= pairs:
                    raise ValueError(f"正式市場來源缺少月報雙份 custody：{month}")
            rows = manifest.get("rows")
            if isinstance(rows, dict):
                absent_dates.update(
                    day for day in CLOSED_DATES
                    if f"{day[:4]}-{day[4:6]}-{day[6:8]}" not in rows
                )
    if not required_months <= covered or not set(CLOSED_DATES) <= absent_dates:
        raise ValueError("正式市場雙報表來源未覆蓋休市日月份或錯列日期")
    after_rows = plan.get("after", {}).get("rows") if isinstance(plan.get("after"), dict) else None
    if not isinstance(after_rows, list):
        raise ValueError("正式市場修訂計畫缺少 after rows")
    market_days = {
        _normal_date(row.get("日期"))
        for row in after_rows
        if isinstance(row, dict) and row.get("指數名稱") == "TAIEX"
    }
    if market_days & set(CLOSED_DATES):
        raise ValueError("已核驗休市日仍存在官方大盤列")
    return {
        "receipt_relative_dir": str(market_relative),
        "plan_sha256": plan_sha,
        "receipt_sha256": _hash_bytes(receipt_bytes),
        "source_captures": sources,
        "verified_months": sorted(required_months),
        "closed_dates_absent": list(CLOSED_DATES),
    }


def _marker_paths(database_path: Path) -> list[Path]:
    root = _root(database_path)
    directory = root / RECEIPT_DIR
    if not directory.exists():
        return []
    return sorted(directory.glob("*/revision.json"))


def _validate_revision(path: Path, database_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = _root(database_path)
    marker = _read_json(path)
    if (
        marker.get("schema_version") != REVISION_SCHEMA
        or Path(str(marker.get("database_path"))).resolve() != Path(database_path).resolve()
        or marker.get("state") not in {"pending", "applied", "rolled_back"}
    ):
        raise ValueError("錯日排除修訂標記不符")
    plan_path = path.parent / "plan.json"
    journal_path = path.parent / "journal.json"
    plan_bytes = plan_path.read_bytes()
    plan_sha = _hash_bytes(plan_bytes)
    plan = json.loads(plan_bytes)
    journal = _read_json(journal_path)
    if (
        plan.get("schema_version") != SCHEMA
        or plan.get("database_path") != str(Path(database_path).resolve())
        or plan.get("run_id") != path.parent.name
        or marker.get("plan_sha256") != plan_sha
        or journal.get("schema_version") != SCHEMA
        or journal.get("plan_sha256") != plan_sha
        or journal.get("database_path") != plan.get("database_path")
        or journal.get("backup_sha256") != marker.get("backup_sha256")
    ):
        raise ValueError("錯日排除修訂 plan/journal hash 鏈不符")
    if marker["state"] == "pending":
        return marker, plan, journal
    receipt_name = "receipt.json" if marker["state"] == "applied" else "rollback.json"
    receipt_bytes = (path.parent / receipt_name).read_bytes()
    receipt = json.loads(receipt_bytes)
    sha_field = "receipt_sha256" if marker["state"] == "applied" else "rollback_sha256"
    if (
        marker.get(sha_field) != _hash_bytes(receipt_bytes)
        or receipt.get("schema_version") != SCHEMA
        or receipt.get("state") != marker["state"]
        or receipt.get("plan_sha256") != plan_sha
        or receipt.get("backup_sha256") != journal.get("backup_sha256")
    ):
        raise ValueError("錯日排除修訂完成／回復 receipt 不符")
    if marker["state"] == "applied":
        _archive, acquired_at, official_codes = _verify_archive(
            root,
            plan.get("evidence_archive_relative"),
            plan.get("evidence_archive_sha256"),
            plan.get("source_files"),
        )
        if (
            receipt.get("evidence_archive_sha256") != plan.get("evidence_archive_sha256")
            or receipt.get("source_available_at") != plan.get("source_available_at")
            or acquired_at.isoformat() != plan.get("source_available_at")
        ):
            raise ValueError("錯日排除 receipt 的來源版本／取得時間不符")
        market = _validate_market_chain(
            Path(database_path), root, plan.get("market_receipt_relative_dir"),
            full_source_validation=False,
        )
        if (
            market["plan_sha256"] != plan.get("market_plan_sha256")
            or market["receipt_sha256"] != plan.get("market_receipt_sha256")
        ):
            raise ValueError("正式市場修訂 identity 與排除計畫不符")
        _validate_scope(plan, official_codes)
    else:
        _validate_scope(plan)
    return marker, plan, journal


def _validate_scope(
    plan: Mapping[str, Any], official_codes: set[str] | None = None,
) -> tuple[set[tuple[str, str]], set[str]]:
    raw_keys = plan.get("keys")
    raw_dates = plan.get("closed_dates")
    if not isinstance(raw_keys, list) or not isinstance(raw_dates, list):
        raise ValueError("錯日排除計畫缺少 keys／closed_dates")
    keys: list[tuple[str, str]] = []
    for row in raw_keys:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("錯日排除 key 格式不符")
        keys.append((_normal_date(row[0]), _normal_symbol(row[1])))
    if keys != sorted(set(keys)):
        raise ValueError("錯日排除 key 重複或未排序")
    dates = {_normal_date(value) for value in raw_dates}
    if sorted(dates) != list(CLOSED_DATES):
        raise ValueError("錯日排除休市日範圍不符")
    allowed_dates = dates | {"20260520"}
    if any(day not in allowed_dates for day, _symbol in keys):
        raise ValueError("錯日排除計畫超出官方證據日期範圍")
    may20_symbols = {symbol for day, symbol in keys if day == "20260520"}
    if len(may20_symbols) != 54:
        raise ValueError("錯日排除計畫須有54個 May 20 精確 key")
    if official_codes is not None and may20_symbols & official_codes:
        raise ValueError("May 20 排除 key 出現在官方完整市場報表")
    scope = {"closed_dates": sorted(dates), "keys": [list(row) for row in keys]}
    if _hash_bytes(_encoded(scope)) != plan.get("scope_sha256"):
        raise ValueError("錯日排除 scope hash 不符")
    if plan.get("source_start_date") != min(dates):
        raise ValueError("錯日排除 PIT 起始日不符")
    return set(keys), dates


def load_exclusion_evidence(database_path: Path) -> list[dict[str, Any]]:
    """回傳已驗證且仍作用中的排除修訂；pending/格式錯誤一律 fail closed。

    此函式只讀小型 revision/journal/receipt/plan、官方來源封存檔和市場
    capture manifests；不讀備份 DB、不重 hash 大型 SQLite 或掃描整表。
    """
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    seen_dates: set[str] = set()
    for path in _marker_paths(database_path):
        try:
            marker, plan, _journal = _validate_revision(path, database_path)
            if marker["state"] == "pending":
                raise ValueError("錯日排除修訂進行中，來源讀寫必須暫停")
            if marker["state"] == "rolled_back":
                continue
            keys, dates = _validate_scope(plan)
            if seen & keys:
                raise ValueError("多個已套用排除修訂的精確 keys 重疊")
            if seen_dates & dates:
                raise ValueError("多個已套用排除修訂的休市日重疊")
            seen.update(keys)
            seen_dates.update(dates)
            result.append(
                {
                    "keys": sorted(keys),
                    "closed_dates": sorted(dates),
                    "plan_sha256": marker["plan_sha256"],
                    "receipt_sha256": marker["receipt_sha256"],
                    "receipt_path": str((path.parent / "receipt.json").resolve()),
                    "acquired_at": plan["source_available_at"],
                    "source_start_date": plan["source_start_date"],
                    "evidence_archive_relative": plan["evidence_archive_relative"],
                    "market_plan_sha256": plan["market_plan_sha256"],
                }
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"錯日排除來源修訂證據無法驗證：{path}: {exc}") from exc
    return result


def load_exclusions(database_path: Path) -> set[tuple[str, str]]:
    """載入全部已套用的精確錯日 key；進行中或損壞證據會拒絕讀取。"""
    return {
        (str(day), str(symbol))
        for evidence in load_exclusion_evidence(database_path)
        for day, symbol in evidence["keys"]
    }


def load_excluded_dates(database_path: Path) -> set[str]:
    """載入所有已核驗的整日休市排除日期。"""
    return {
        str(day)
        for evidence in load_exclusion_evidence(database_path)
        for day in evidence["closed_dates"]
    }


def _record_key(record: Mapping[str, object]) -> tuple[str, str]:
    day_field = next((field for field in _DATE_FIELDS if field in record), None)
    symbol_field = next((field for field in _SYMBOL_FIELDS if field in record), None)
    if day_field is None or symbol_field is None:
        raise ValueError("待驗證資料列缺少日期或證券代號")
    return _normal_date(record[day_field]), _normal_symbol(record[symbol_field])


def validate_excluded_daily_price_rows(
    database_path: Path, records: Iterable[Mapping[str, object]],
) -> None:
    """拒絕重匯整個已核驗休市日，或重匯已證明的精確錯日 key。"""
    evidence = load_exclusion_evidence(database_path)
    if not evidence:
        return
    excluded = {tuple(key) for item in evidence for key in item["keys"]}
    closed = {str(day) for item in evidence for day in item["closed_dates"]}
    source: Iterable[Mapping[str, object]] = records
    if hasattr(records, "to_dict"):
        try:
            source = records.to_dict(orient="records")  # type: ignore[union-attr,assignment]
        except (TypeError, ValueError) as exc:
            raise ValueError("無法讀取待驗證的每日價量列") from exc
    for record in source:
        if not isinstance(record, Mapping):
            raise ValueError("待驗證資料列格式不符")
        key = _record_key(record)
        if key[0] in closed or key in excluded:
            raise ValueError(f"每日價量來源含已核驗排除列：{key[0]}/{key[1]}")


def assert_excluded_source_revision_safe(
    database_path: Path, decision_date: date | datetime | str,
) -> None:
    """拒絕從最早受影響休市日前起使用目前來源修訂資料做歷史 PIT。"""
    try:
        normalized = _normal_date(decision_date)
        cutoff = date(int(normalized[:4]), int(normalized[4:6]), int(normalized[6:8]))
    except (TypeError, ValueError) as exc:
        raise ValueError("決策日期格式不符") from exc
    evidence = load_exclusion_evidence(database_path)
    starts = [date.fromisoformat(item["source_start_date"]) for item in evidence]
    if starts and cutoff >= min(starts):
        raise ValueError(
            "excluded daily-price source revision blocks historical PIT from "
            f"{min(starts).isoformat()}; rebuild from explicitly revised sources"
        )
