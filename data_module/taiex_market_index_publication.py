"""TAIEX 專用的合成資料同步與前瞻列證據。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping, Sequence

import pandas as pd

from data_module.market_data_integrity import normalize_market_index_frame
from data_module.ml_restatement_official_market import parse_monthly_report


_SCHEMA_VERSION = "twse-taiex-market-index-row-evidence.v1"
_CAPTURE_SCHEMA_VERSION = "official-market-daily-source-capture.v1"
_REPORTS = ("FMTQIK", "MI_5MINS_HIST")
_SOURCE_COLUMNS = ("日期", "指數名稱", "收盤價", "開盤價", "最高價", "最低價", "成交量")
_SQLITE_EVIDENCE_COLUMNS = ("日期", "指數名稱", "收盤指數", "開盤價", "最高價", "最低價", "成交量")
_SQLITE_EXPECTED_VALUE_COLUMNS = ("收盤價", "收盤指數", "開盤價", "最高價", "最低價", "成交量")
_DATE_COLUMN_ALIASES = ("日期", "date", "Date", "trade_date", "decision_date")
_DATE_CSV_DTYPES = {
    "日期": str,
    "date": str,
    "Date": str,
    "trade_date": str,
    "decision_date": str,
}


@dataclass(frozen=True)
class TaiexMarketIndexRowEvidence:
    """SQLite 目前列與一份明確 TWSE capture 相符時的窄幅證據。"""

    source_date: str
    source_published_at: None
    first_observed_at: str
    historical_pit: bool
    close: Decimal
    opening: Decimal
    high: Decimal
    low: Decimal
    volume: int
    sqlite_storage_types: Mapping[str, str]


@dataclass(frozen=True)
class TaiexMarketIndexEvidence:
    """讀取證據 sidecar 後的 attested 或 unknown 結果。"""

    status: str
    reason_code: str | None
    row: TaiexMarketIndexRowEvidence | None = None


@dataclass(frozen=True)
class _VerifiedCapture:
    source_date: str
    row: Mapping[str, str | int]
    captured_at: str
    relative_manifest: str
    manifest_sha256: str
    reports: tuple[Mapping[str, str | int], ...]


class _EvidenceValidationError(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _UnsupportedMarketSchema(ValueError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _decimal_text(value: object) -> str:
    if value is None or pd.isna(value):
        raise ValueError("市場指數列缺少數值")
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("市場指數列含無效數值") from exc
    if not result.is_finite():
        raise ValueError("市場指數列含非有限數值")
    return format(result, "f")


def _normal_date_key(value: object) -> str:
    if value is None:
        key = ""
    else:
        text = str(value).strip()
        if not text or text.lower() == "nan":
            key = ""
        else:
            text = text.replace("/", "-")
            if text.endswith(".0") and text[:-2].isdigit():
                text = text[:-2]
            compact = text.replace("-", "")
            if len(compact) == 8 and compact.isdigit():
                key = compact
            else:
                parts = text.split("-")
                if len(parts) == 3 and all(part.isdigit() for part in parts):
                    year_text, month_text, day_text = parts
                    if len(year_text) == 4:
                        year = int(year_text)
                    elif 0 < len(year_text) < 4:
                        year = int(year_text) + 1911
                    else:
                        year = 0
                    if year:
                        key = f"{year:04d}{int(month_text):02d}{int(day_text):02d}"
                    else:
                        key = ""
                else:
                    parsed = pd.to_datetime(text, errors="coerce")
                    key = "" if pd.isna(parsed) else parsed.strftime("%Y%m%d")
    if len(key) != 8 or not key.isdigit():
        raise ValueError("市場指數日期格式無效")
    try:
        parsed = date(int(key[:4]), int(key[4:6]), int(key[6:]))
    except ValueError as exc:
        raise ValueError("市場指數日期格式無效") from exc
    return parsed.strftime("%Y%m%d")


def _verified_capture(manifest_path: Path, data_root: Path) -> _VerifiedCapture:
    source_root = (data_root / "meta_data" / "official_market_daily_sources").resolve(strict=True)
    lexical_manifest = Path(manifest_path)
    if lexical_manifest.is_symlink():
        raise ValueError("TWSE capture manifest 不可為連結")
    resolved_manifest = lexical_manifest.resolve(strict=True)
    if not _under(resolved_manifest, source_root) or not resolved_manifest.is_file():
        raise ValueError("TWSE capture manifest 超出固定來源目錄")
    manifest_bytes = resolved_manifest.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != _CAPTURE_SCHEMA_VERSION:
        raise ValueError("TWSE capture manifest 格式不支援")
    if manifest.get("historical_pit") is not False or manifest.get("row_count") != 1:
        raise ValueError("TWSE capture 不是單列前瞻資料")
    captured_at = str(manifest.get("captured_at", ""))
    observed_at = datetime.fromisoformat(captured_at)
    if not captured_at or observed_at.tzinfo is None:
        raise ValueError("TWSE capture 缺少時區明確的本機觀測時間")
    start = date.fromisoformat(str(manifest.get("requested_start_date", "")))
    cutoff = date.fromisoformat(str(manifest.get("requested_cutoff_date", "")))
    if start != cutoff:
        raise ValueError("TWSE capture 日期範圍不是單日")
    month = start.strftime("%Y%m")
    report_items = manifest.get("reports")
    if not isinstance(report_items, list) or len(report_items) != len(_REPORTS):
        raise ValueError("TWSE capture 報表數量不符")

    parsed_by_report: dict[str, dict[date, dict[str, Decimal]]] = {}
    report_evidence: list[Mapping[str, str | int]] = []
    seen_reports: set[str] = set()
    for item in report_items:
        if not isinstance(item, dict):
            raise ValueError("TWSE capture 報表描述格式無效")
        report = str(item.get("report", ""))
        if report not in _REPORTS or report in seen_reports:
            raise ValueError("TWSE capture 報表角色重複或無效")
        seen_reports.add(report)
        if item.get("month") != month or item.get("historical_pit") is not False:
            raise ValueError("TWSE capture 報表期別或 PIT 標記不符")
        report_captured_at = str(item.get("captured_at", ""))
        report_observed_at = datetime.fromisoformat(report_captured_at)
        if not report_captured_at or report_observed_at.tzinfo is None:
            raise ValueError("TWSE capture 報表缺少時區明確觀測時間")
        filename = f"{month}-{report}.json"
        if item.get("file") != filename:
            raise ValueError("TWSE capture 報表檔名不符")
        report_path = resolved_manifest.parent / filename
        if report_path.is_symlink():
            raise ValueError("TWSE 原始報表不可為連結")
        resolved_report = report_path.resolve(strict=True)
        if resolved_report.parent != resolved_manifest.parent or not resolved_report.is_file():
            raise ValueError("TWSE 原始報表路徑不符")
        raw = resolved_report.read_bytes()
        digest = _sha256(raw)
        declared = str(item.get("sha256", ""))
        if declared != f"sha256:{digest}" or item.get("byte_count") != len(raw):
            raise ValueError("TWSE 原始報表 hash 或長度不符")
        payload = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("TWSE 原始報表不是 JSON 物件")
        parsed_by_report[report] = parse_monthly_report(payload, report=report, month=month)
        report_evidence.append({
            "report": report,
            "month": month,
            "file": filename,
            "sha256": digest,
            "byte_count": len(raw),
            "captured_at": report_captured_at,
        })
    if seen_reports != set(_REPORTS):
        raise ValueError("TWSE capture 缺少必要報表")

    totals = parsed_by_report["FMTQIK"]
    prices = parsed_by_report["MI_5MINS_HIST"]
    if set(totals) != set(prices) or start not in totals:
        raise ValueError("TWSE 原始報表整月日期集合不一致或缺少指定日")
    if any(
        totals[trading_day]["發行量加權股價指數"]
        != prices[trading_day]["收盤指數"]
        for trading_day in totals
    ):
        raise ValueError("TWSE 整月兩份報表收盤值不一致")
    volume = totals[start]["成交股數"]
    if volume < 0 or volume != volume.to_integral_value():
        raise ValueError("TWSE 成交量不是非負整數")
    price = prices[start]
    row: dict[str, str | int] = {
        "日期": start.strftime("%Y%m%d"),
        "指數名稱": "TAIEX",
        "收盤價": format(price["收盤指數"], "f"),
        "開盤價": format(price["開盤指數"], "f"),
        "最高價": format(price["最高指數"], "f"),
        "最低價": format(price["最低指數"], "f"),
        "成交量": int(volume),
    }
    relative_manifest = resolved_manifest.relative_to(data_root.resolve(strict=True)).as_posix()
    return _VerifiedCapture(
        source_date=start.strftime("%Y%m%d"),
        row=row,
        captured_at=captured_at,
        relative_manifest=relative_manifest,
        manifest_sha256=_sha256(manifest_bytes),
        reports=tuple(sorted(report_evidence, key=lambda value: str(value["report"]))),
    )


def _read_csv_frame(config: Any) -> tuple[pd.DataFrame, bytes]:
    path = Path(config.market_index_file)
    csv_bytes = path.read_bytes()
    frame = pd.read_csv(
        io.BytesIO(csv_bytes), encoding="utf-8-sig",
        dtype=_DATE_CSV_DTYPES, low_memory=False,
    )
    date_column = next((column for column in _DATE_COLUMN_ALIASES if column in frame.columns), None)
    if date_column is not None:
        if date_column != "日期" and "日期" not in frame.columns:
            frame = frame.rename(columns={date_column: "日期"})
        frame["日期"] = frame["日期"].map(_normal_date_key)
    frame = normalize_market_index_frame(frame)
    if frame.empty:
        return frame, csv_bytes
    if not {"日期", "指數名稱", "收盤指數"} <= set(frame.columns):
        raise ValueError("market_index.csv 缺少同步必要欄位")
    frame["日期"] = frame["日期"].map(_normal_date_key)
    if frame["日期"].duplicated().any():
        raise ValueError("TAIEX market_index.csv 日期重複")
    if not frame["指數名稱"].eq("TAIEX").all():
        raise ValueError("TAIEX 專用同步不接受其他指數名稱")
    return frame, csv_bytes


def _csv_row_matches(frame: pd.DataFrame, capture: _VerifiedCapture) -> bool:
    rows = frame.loc[frame["日期"] == capture.source_date]
    if len(rows) != 1:
        return False
    csv_row = rows.iloc[0]
    for column in ("收盤價", "開盤價", "最高價", "最低價"):
        if column not in frame.columns:
            return False
        try:
            if Decimal(_decimal_text(csv_row[column])) != Decimal(str(capture.row[column])):
                return False
        except ValueError:
            return False
    try:
        volume = Decimal(str(csv_row["成交量"]).replace(",", ""))
    except (InvalidOperation, ValueError):
        return False
    return (
        volume.is_finite()
        and volume == volume.to_integral_value()
        and int(volume) == capture.row["成交量"]
    )


def _db_scalar(value: Any) -> Any:
    if value is None:
        return {"type": "null", "value": None}
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return {"type": "integer", "value": int(value)}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        if not pd.notna(value):
            return {"type": "null", "value": None}
        return {"type": "real", "value_hex": value.hex()}
    if isinstance(value, bytes):
        return {"type": "blob", "value_hex": value.hex()}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    raise ValueError(f"不支援的 SQLite 型別：{type(value).__name__}")


def _ensure_columns_in_transaction(connection: sqlite3.Connection, columns: Sequence[str]) -> None:
    existing = {
        str(row["name"])
        for row in connection.execute('PRAGMA table_info("market_indices")').fetchall()
    }
    for column in columns:
        if column in existing:
            continue
        if not column or "\x00" in column:
            raise ValueError("market_index.csv 欄位名稱無效")
        if column in {"日期", "指數名稱", "證券代號", "證券名稱", "漲跌", "trade_type"}:
            column_type = "TEXT"
        elif column in {
            "成交股數", "成交筆數", "成交金額", "最後揭示買量", "最後揭示賣量",
            "買進股數", "賣出股數", "買賣超股數", "買進金額千元", "賣出金額千元",
            "買賣超金額千元", "lots_observed", "amount_observed", "lots_rank", "amount_rank",
        }:
            column_type = "INTEGER"
        else:
            column_type = "REAL"
        quoted = '"' + column.replace('"', '""') + '"'
        connection.execute(f'ALTER TABLE "market_indices" ADD COLUMN {quoted} {column_type}')
        existing.add(column)


def _sqlite_typed_row(
    connection: sqlite3.Connection, columns: Sequence[str], source_date: str,
) -> tuple[list[Any], dict[str, str]]:
    if not connection.in_transaction:
        raise ValueError("SQLite typed row 必須在明確 read transaction 中讀取")
    quoted_values = ['"' + column.replace('"', '""') + '"' for column in columns]
    projections: list[str] = []
    for expression in quoted_values:
        projections.extend((expression, f"typeof({expression})"))
    rows = connection.execute(
        f'SELECT {", ".join(projections)} FROM "market_indices" '
        'WHERE "指數名稱"=? AND "日期"=?',
        ("TAIEX", source_date),
    ).fetchmany(2)
    if len(rows) != 1:
        raise ValueError("SQLite TAIEX row readback missing or duplicated")
    row = rows[0]
    values = [_db_scalar(row[index * 2]) for index in range(len(columns))]
    storage_types = {
        column: str(row[index * 2 + 1])
        for index, column in enumerate(columns)
        if column in _SQLITE_EXPECTED_VALUE_COLUMNS
    }
    if not set(_SQLITE_EXPECTED_VALUE_COLUMNS) <= set(storage_types):
        raise ValueError("SQLite typed row 缺少 evidence 欄位型別")
    return values, storage_types


def _typed_decimal(value: Any) -> Decimal:
    if not isinstance(value, dict):
        raise ValueError("SQLite typed value 格式無效")
    if value.get("type") == "real" and isinstance(value.get("value_hex"), str):
        decoded: object = float.fromhex(value["value_hex"])
    elif value.get("type") == "integer" and isinstance(value.get("value"), int):
        decoded = value["value"]
    else:
        raise ValueError("SQLite 數值欄位型別不符")
    result = Decimal(str(decoded))
    if not result.is_finite():
        raise ValueError("SQLite 數值欄位不是有限數值")
    return result


def _sqlite_row_matches_capture(
    columns: Sequence[str], typed_values: Sequence[Any], capture: _VerifiedCapture,
) -> bool:
    row = dict(zip(columns, typed_values, strict=True))
    for column, expected in (("日期", capture.source_date), ("指數名稱", "TAIEX")):
        value = row.get(column)
        if not isinstance(value, dict) or value.get("type") != "text" or value.get("value") != expected:
            return False
    expected_numbers = {
        "收盤價": capture.row["收盤價"],
        "收盤指數": capture.row["收盤價"],
        "開盤價": capture.row["開盤價"],
        "最高價": capture.row["最高價"],
        "最低價": capture.row["最低價"],
        "成交量": capture.row["成交量"],
    }
    try:
        return all(
            _typed_decimal(row[column]) == Decimal(str(expected))
            for column, expected in expected_numbers.items()
        )
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return False


def _write_sidecar(output_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = _canonical_json(payload)
    digest = _sha256(body)
    relative = Path("scheduled") / "taiex_market_index_evidence" / f"{digest}.json"
    destination = output_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".taiex-evidence-", suffix=".tmp",
            dir=destination.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != body:
                raise ValueError("TAIEX evidence sidecar create-only conflict")
        return {
            "schema_version": 1,
            "status": "captured",
            "relative_path": relative.as_posix(),
            "sha256": digest,
        }
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _unknown(reason_code: str) -> dict[str, Any]:
    return {"status": "unknown", "reason_code": reason_code}


def publish_taiex_market_index(
    *, config: Any, capture_manifests: Sequence[Path], market_update_result: Mapping[str, Any],
) -> dict[str, Any]:
    """同步整份 TAIEX CSV，並只為明確 capture 的同次列發布證據。"""
    if market_update_result.get("success") is not True:
        return {
            "success": False,
            "message": "大盤更新未成功，略過 TAIEX SQLite 同步",
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("market_update_not_successful"),
        }
    if not getattr(config, "use_sqlite", False):
        return {
            "success": True,
            "message": "SQLite 未啟用，略過同步",
            "source": "market_index",
            "synced_records": 0,
            "skipped": True,
            "row_evidence": _unknown("sqlite_disabled"),
        }

    from data_module.formal_market_revision import validate_market_replacement

    database_path = Path(config.db_file)
    try:
        frame, csv_bytes = _read_csv_frame(config)
    except (OSError, ValueError, TypeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        return {
            "success": False,
            "message": f"TAIEX CSV 無法讀取：{type(exc).__name__}",
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("csv_read_failed"),
        }
    if frame.empty:
        return {
            "success": True,
            "message": "market_index.csv 沒有可同步的 CSV 資料",
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("no_rows_to_read_back"),
        }

    captures: list[_VerifiedCapture] = []
    capture_failure: str | None = None
    try:
        for manifest_path in capture_manifests:
            captures.append(_verified_capture(Path(manifest_path), Path(config.data_root)))
        source_dates = [capture.source_date for capture in captures]
        if len(source_dates) != len(set(source_dates)):
            capture_failure = "duplicate_capture_date"
        elif any(not _csv_row_matches(frame, capture) for capture in captures):
            capture_failure = "csv_capture_mismatch"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        capture_failure = "capture_validation_failed"

    # 此 writer 會替換 CSV 所含日期的 TAIEX 列，但不刪同日 sibling；
    # replace_dates 只要求 formal guard 核對日期替換所需的完整受保護欄位，
    # 不會執行日期級刪除。先於 DBManager 初始化，避免 guard 前的 schema side effect。
    records = frame.to_dict(orient="records")
    try:
        validate_market_replacement(database_path, records, replace_dates=True)
    except Exception as exc:
        return {
            "success": False,
            "message": f"TAIEX 匯入遭正式市場修訂保護拒絕：{type(exc).__name__}",
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("formal_market_guard_rejected"),
        }

    from data_module.db_manager import DBManager

    db = DBManager(config)
    try:
        if frame.columns.has_duplicates:
            raise ValueError("CSV duplicate columns")
        columns = [str(column) for column in frame.columns]
        quoted_columns = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        statement = (
            f'INSERT INTO "market_indices" ({quoted_columns}) VALUES ({placeholders})'
        )
        values: list[tuple[Any, ...]] = []
        for row in frame.itertuples(index=False, name=None):
            normalized: list[Any] = []
            for value in row:
                try:
                    missing = bool(pd.isna(value))
                except (TypeError, ValueError):
                    missing = False
                if missing:
                    normalized.append(None)
                elif hasattr(value, "item"):
                    normalized.append(value.item())
                else:
                    normalized.append(value)
            values.append(tuple(normalized))

        with db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_schema = {
                str(row["name"])
                for row in connection.execute('PRAGMA table_info("market_indices")').fetchall()
            }
            if not {"日期", "指數名稱"} <= existing_schema:
                raise _UnsupportedMarketSchema("market_indices 缺少 TAIEX 複合鍵欄位")
            _ensure_columns_in_transaction(connection, columns)
            dates = sorted(set(frame["日期"].astype(str).tolist()))
            date_placeholders = ", ".join("?" for _ in dates)
            connection.execute(
                'DELETE FROM "market_indices" '
                f'WHERE "指數名稱"=? AND "日期" IN ({date_placeholders})',
                ("TAIEX", *dates),
            )
            connection.executemany(statement, values)
    except _UnsupportedMarketSchema as exc:
        return {
            "success": False,
            "message": str(exc),
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("sqlite_schema_unsupported"),
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"TAIEX SQLite 同步失敗：{type(exc).__name__}",
            "source": "market_index",
            "synced_records": 0,
            "row_evidence": _unknown("sqlite_sync_failed"),
        }

    result: dict[str, Any] = {
        "success": True,
        "message": "TAIEX CSV 已依複合鍵同步至 SQLite",
        "source": "market_index",
        "table": "market_indices",
        "synced_records": int(len(frame)),
        "row_evidence": _unknown(capture_failure or "no_explicit_capture"),
    }
    if capture_failure is not None or not captures:
        return result

    try:
        with db.connect() as connection:
            connection.execute("BEGIN")
            db_columns = [
                str(row["name"])
                for row in connection.execute('PRAGMA table_info("market_indices")').fetchall()
            ]
            evidence_columns = [column for column in db_columns if column in columns]
            if not set(_SQLITE_EXPECTED_VALUE_COLUMNS) <= set(evidence_columns):
                raise ValueError("SQLite TAIEX typed columns missing")
            sqlite_rows: dict[str, dict[str, Any]] = {}
            storage_types_by_date: dict[str, dict[str, str]] = {}
            for capture in captures:
                typed_values, storage_types = _sqlite_typed_row(
                    connection, evidence_columns, capture.source_date,
                )
                if not _sqlite_row_matches_capture(evidence_columns, typed_values, capture):
                    raise ValueError("SQLite row differs from exact capture/CSV values")
                sqlite_rows[capture.source_date] = {
                    "columns": evidence_columns,
                    "values": typed_values,
                    "row_sha256": _sha256(_canonical_json({
                        "columns": evidence_columns,
                        "values": typed_values,
                    })),
                }
                storage_types_by_date[capture.source_date] = storage_types
            connection.commit()
    except Exception as exc:
        result["row_evidence"] = _unknown("sqlite_row_readback_mismatch")
        result["message"] = (
            "TAIEX CSV 已同步；SQLite 列證據無法驗證：" + type(exc).__name__
        )
        return result

    database_identity = _sha256(str(database_path.resolve()).casefold().encode("utf-8"))
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "index_name": "TAIEX",
        "database_identity_sha256": database_identity,
        "csv_sha256": _sha256(csv_bytes),
        "csv_byte_count": len(csv_bytes),
        "source_published_at": None,
        "historical_pit": False,
        "captures": [
            {
                "source_date": capture.source_date,
                "row": dict(capture.row),
                "first_observed_at": capture.captured_at,
                "manifest_path": capture.relative_manifest,
                "manifest_sha256": capture.manifest_sha256,
                "reports": [dict(item) for item in capture.reports],
                "sqlite_row": sqlite_rows[capture.source_date],
                "sqlite_storage_types": storage_types_by_date[capture.source_date],
            }
            for capture in captures
        ],
    }
    try:
        result["row_evidence"] = _write_sidecar(Path(config.output_root), payload)
    except (OSError, ValueError) as exc:
        result["row_evidence"] = _unknown("sidecar_publication_failed")
    return result


def read_taiex_market_index_evidence(
    *, output_root: Path, data_root: Path, database_path: Path,
    descriptor: Mapping[str, Any] | None, source_date: str,
) -> TaiexMarketIndexEvidence:
    """重新驗證 sidecar、原始 capture、CSV 與 SQLite 列；不推測未提供的來源。"""
    if not isinstance(descriptor, Mapping) or descriptor.get("status") != "captured":
        reason = descriptor.get("reason_code") if isinstance(descriptor, Mapping) else None
        return TaiexMarketIndexEvidence("unknown", str(reason or "missing_descriptor"))
    try:
        expected_date = _normal_date_key(source_date)
        relative = Path(str(descriptor.get("relative_path", "")))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("sidecar path invalid")
        output_base = Path(output_root).resolve(strict=True)
        sidecar = output_base / relative
        if sidecar.is_symlink():
            raise ValueError("sidecar link rejected")
        resolved_sidecar = sidecar.resolve(strict=True)
        if not _under(resolved_sidecar, output_base) or not resolved_sidecar.is_file():
            raise ValueError("sidecar outside output root")
        body = resolved_sidecar.read_bytes()
        digest = _sha256(body)
        if digest != descriptor.get("sha256"):
            raise ValueError("sidecar hash mismatch")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
            raise ValueError("sidecar schema mismatch")
        if payload.get("source_published_at") is not None or payload.get("historical_pit") is not False:
            raise ValueError("sidecar availability semantics invalid")
        db_identity = _sha256(str(Path(database_path).resolve()).casefold().encode("utf-8"))
        if payload.get("database_identity_sha256") != db_identity:
            raise ValueError("database identity mismatch")
        csv_path = Path(data_root) / "meta_data" / "market_index.csv"
        csv_bytes = csv_path.read_bytes()
        if _sha256(csv_bytes) != payload.get("csv_sha256") or len(csv_bytes) != payload.get("csv_byte_count"):
            raise ValueError("CSV bytes changed")
        frame = pd.read_csv(
            io.BytesIO(csv_bytes), encoding="utf-8-sig",
            dtype=_DATE_CSV_DTYPES, low_memory=False,
        )
        date_column = next((column for column in _DATE_COLUMN_ALIASES if column in frame.columns), None)
        if date_column is not None:
            if date_column != "日期" and "日期" not in frame.columns:
                frame = frame.rename(columns={date_column: "日期"})
            frame["日期"] = frame["日期"].map(_normal_date_key)
        frame = normalize_market_index_frame(frame)
        if frame.empty:
            raise ValueError("CSV has no rows")
        frame["日期"] = frame["日期"].map(_normal_date_key)
        captures = payload.get("captures")
        if not isinstance(captures, list):
            raise ValueError("sidecar captures invalid")
        matching = [item for item in captures if isinstance(item, dict) and item.get("source_date") == expected_date]
        if not matching:
            raise _EvidenceValidationError("key_not_observed_in_capture")
        if len(matching) != 1:
            raise ValueError("sidecar source date missing or duplicated")
        capture = matching[0]
        manifest_relative = Path(str(capture.get("manifest_path", "")))
        if manifest_relative.is_absolute() or any(part in {"", ".", ".."} for part in manifest_relative.parts):
            raise ValueError("manifest path invalid")
        verified_capture = _verified_capture(Path(data_root) / manifest_relative, Path(data_root))
        if (
            verified_capture.source_date != expected_date
            or verified_capture.manifest_sha256 != capture.get("manifest_sha256")
            or dict(verified_capture.row) != capture.get("row")
            or verified_capture.captured_at != capture.get("first_observed_at")
            or [dict(item) for item in verified_capture.reports] != capture.get("reports")
            or not _csv_row_matches(frame, verified_capture)
        ):
            raise ValueError("capture/source row no longer matches")
        csv_rows = frame.loc[frame["日期"] == expected_date]
        if len(csv_rows) != 1:
            raise ValueError("CSV row missing or duplicated")
        sqlite_record = capture.get("sqlite_row")
        if not isinstance(sqlite_record, dict):
            raise ValueError("SQLite attestation missing")
        sqlite_storage_types = capture.get("sqlite_storage_types")
        if (
            not isinstance(sqlite_storage_types, dict)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in sqlite_storage_types.items())
        ):
            raise ValueError("SQLite storage type attestation invalid")
        columns = sqlite_record.get("columns")
        if (
            not isinstance(columns, list)
            or len(columns) > 256
            or any(not isinstance(column, str) for column in columns)
            or len(set(columns)) != len(columns)
            or not set(_SQLITE_EXPECTED_VALUE_COLUMNS) <= set(columns)
        ):
            raise ValueError("SQLite attestation columns invalid")
        read_only_uri = f"{Path(database_path).resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(read_only_uri, uri=True)
        try:
            connection.execute("BEGIN")
            existing_columns = {
                str(row[1]) for row in connection.execute('PRAGMA table_info("market_indices")')
            }
            if not set(columns) <= existing_columns:
                raise ValueError("SQLite attestation columns unavailable")
            typed_values, storage_types = _sqlite_typed_row(connection, columns, expected_date)
            connection.commit()
        finally:
            connection.close()
        current_digest = _sha256(_canonical_json({"columns": columns, "values": typed_values}))
        if (
            current_digest != sqlite_record.get("row_sha256")
            or typed_values != sqlite_record.get("values")
            or storage_types != sqlite_storage_types
            or not _sqlite_row_matches_capture(columns, typed_values, verified_capture)
        ):
            raise _EvidenceValidationError("sqlite_row_drift")
        source_row = capture["row"]
        return TaiexMarketIndexEvidence(
            "attested",
            None,
            TaiexMarketIndexRowEvidence(
                source_date=expected_date,
                source_published_at=None,
                first_observed_at=verified_capture.captured_at,
                historical_pit=False,
                close=Decimal(str(source_row["收盤價"])),
                opening=Decimal(str(source_row["開盤價"])),
                high=Decimal(str(source_row["最高價"])),
                low=Decimal(str(source_row["最低價"])),
                volume=int(source_row["成交量"]),
                sqlite_storage_types=storage_types,
            ),
        )
    except _EvidenceValidationError as exc:
        return TaiexMarketIndexEvidence("unknown", exc.reason_code)
    except (
        OSError, ValueError, TypeError, KeyError, InvalidOperation,
        sqlite3.Error, json.JSONDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError,
    ) as exc:
        return TaiexMarketIndexEvidence("unknown", "evidence_validation_failed")
