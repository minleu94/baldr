"""Read-only diagnostics bound to retained official daily quote response bytes."""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


class OfficialQuoteExclusionDiagnostics:
    def __init__(
        self,
        custody_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.custody_root = custody_root
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._twse_cache: dict[str, dict[str, tuple[dict[str, object], ...]]] = {}

    def twse_change_evidence(
        self,
        session_key: str,
        decision_date: date,
        stock_codes: list[str],
    ) -> dict[str, tuple[dict[str, object], ...]]:
        """讀回指定日、指定代碼的 hash-verified TWSE 原始變動列。"""

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return {}
        taipei_today = now.astimezone(ZoneInfo("Asia/Taipei")).date()
        if decision_date > taipei_today:
            return {}
        cutoff = (
            now
            if decision_date == taipei_today
            else datetime.combine(decision_date, time.max, ZoneInfo("Asia/Taipei"))
        )
        key = str(session_key).replace("-", "").replace("/", "")
        try:
            cached = self._twse_cache.get(key)
            if cached is None:
                from data_module.price_change_direction import (
                    CHANGE_SIGN_COLUMNS,
                )
                from data_module.twse_daily_price_publication import (
                    _verify_custody_payload,
                )

                requested = {str(code) for code in stock_codes}
                root = self.custody_root / "twse" / key
                receipt_paths = sorted(root.glob("*/receipt.json"))
                if len(receipt_paths) > 128:
                    return {}
                candidates: dict[str, list[dict[str, object]]] = {
                    code: [] for code in requested
                }
                for receipt_path in receipt_paths:
                    receipt_bytes = receipt_path.read_bytes()
                    if len(receipt_bytes) > 1024 * 1024:
                        continue
                    receipt = json.loads(receipt_bytes.decode("utf-8"))
                    if not isinstance(receipt, dict):
                        continue
                    _verify_custody_payload(receipt)
                    if (
                        receipt.get("source_id") != "twse.mi_index.daily_price"
                        or str(receipt.get("source_date", "")).replace("-", "") != key
                        or receipt.get("parser_id") != "twse.mi_index.direction_text.v2"
                        or receipt.get("raw_response_path") != "raw_response.bin"
                        or receipt.get("availability_basis") != "response_body_read_completed_at"
                    ):
                        continue
                    available = datetime.fromisoformat(str(receipt["available_at"]))
                    if available.tzinfo is None or available > cutoff:
                        continue
                    raw_path = receipt_path.parent / "raw_response.bin"
                    if raw_path.stat().st_size > 64 * 1024 * 1024:
                        continue
                    raw_bytes = raw_path.read_bytes()
                    digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
                    if (
                        digest != receipt.get("raw_response_sha256")
                        or len(raw_bytes) != receipt.get("raw_response_bytes")
                    ):
                        continue
                    raw_source = json.loads(raw_bytes.decode("utf-8-sig"))
                    tables = raw_source.get("tables") if isinstance(raw_source, dict) else None
                    if not isinstance(tables, list):
                        continue
                    table_matches = [
                        table for table in tables
                        if isinstance(table, dict)
                        and isinstance(table.get("fields"), list)
                        and {"證券代號", "收盤價", "漲跌價差", "成交股數"}.issubset(table["fields"])
                    ]
                    if len(table_matches) != 1:
                        continue
                    fields = table_matches[0]["fields"]
                    raw_rows = table_matches[0].get("data")
                    if (
                        not all(isinstance(field, str) for field in fields)
                        or len(set(fields)) != len(fields)
                        or not isinstance(raw_rows, list)
                    ):
                        continue
                    rows_by_code: dict[str, list[dict[str, object]]] = {}
                    for values in raw_rows:
                        if not isinstance(values, list) or len(values) != len(fields):
                            continue
                        raw_row = dict(zip(fields, values))
                        code = raw_row.get("證券代號")
                        if isinstance(code, str) and code in requested:
                            rows_by_code.setdefault(code, []).append(raw_row)
                    for code, rows in rows_by_code.items():
                        if len(rows) != 1:
                            continue
                        raw_row = rows[0]
                        candidates[code].append({
                            "source_date": key,
                            "stock_code": code,
                            "raw_change": raw_row.get("漲跌價差"),
                            "raw_close": raw_row.get("收盤價"),
                            "raw_volume": raw_row.get("成交股數"),
                            "raw_signs": {
                                column: raw_row.get(column)
                                for column in CHANGE_SIGN_COLUMNS
                                if column in fields
                            },
                            "source_id": receipt["source_id"],
                            "available_at": receipt["available_at"],
                            "receipt_path": str(receipt_path),
                            "receipt_sha256": "sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
                            "raw_response_sha256": digest,
                            "historical_pit": False,
                            "quote_values_bound": True,
                        })
                    if receipt_path.read_bytes() != receipt_bytes or raw_path.read_bytes() != raw_bytes:
                        candidates.clear()
                        break
                cached = {code: tuple(rows) for code, rows in candidates.items() if rows}
                self._twse_cache[key] = cached
            eligible: dict[str, tuple[dict[str, object], ...]] = {}
            for code, cached_rows in cached.items():
                kept: list[dict[str, object]] = []
                for row in cached_rows:
                    available_value = row.get("available_at")
                    available = (
                        available_value
                        if isinstance(available_value, datetime)
                        else datetime.fromisoformat(str(available_value))
                    )
                    if available.tzinfo is None or available > cutoff:
                        continue
                    kept.append(row)
                if kept:
                    eligible[code] = tuple(kept)
            return eligible
        except (OSError, ValueError, TypeError, KeyError):
            return {}

    def corporate_action(self, code: str, session_key: str, decision_date: date,
                         close: Decimal, volume: Decimal | None) -> dict[str, Any] | None:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return None
        today = now.astimezone(ZoneInfo("Asia/Taipei")).date()
        if decision_date > today:
            return None
        decision_at = now if decision_date == today else datetime.combine(decision_date, time.max, ZoneInfo("Asia/Taipei"))
        root = self.custody_root / "tpex" / session_key
        for receipt_path in sorted(root.glob("*/receipt.json"))[:100]:
            try:
                receipt_bytes = receipt_path.read_bytes()
                if len(receipt_bytes) > 1024 * 1024:
                    continue
                receipt = json.loads(receipt_bytes)
                if (receipt.get("source_id") != "tpex.daily_close_quotes"
                        or str(receipt.get("source_date", "")).replace("-", "") != session_key
                        or receipt.get("raw_response_path") != "raw_response.bin"):
                    continue
                available = datetime.fromisoformat(receipt["available_at"])
                if available.tzinfo is None or available > decision_at:
                    continue
                raw_path = receipt_path.parent / "raw_response.bin"
                if raw_path.stat().st_size > 4 * 1024 * 1024:
                    continue
                raw = raw_path.read_bytes()
                digest = "sha256:" + hashlib.sha256(raw).hexdigest()
                if digest != receipt.get("raw_response_sha256") or len(raw) != receipt.get("raw_response_bytes"):
                    continue
                payload = json.loads(raw)
                for table in payload.get("tables", []):
                    fields = [str(field).replace(" ", "").replace("<br>", "") for field in table.get("fields", [])]
                    for values in table.get("data", []):
                        row = dict(zip(fields, values))
                        if str(row.get("代號")) != code or row.get("漲跌") not in {"除權", "除息", "除權息"}:
                            continue
                        if Decimal(str(row.get("收盤")).replace(",", "")) != close:
                            continue
                        if volume is None or Decimal(str(row.get("成交股數")).replace(",", "")) != volume:
                            continue
                        if receipt_path.read_bytes() != receipt_bytes or raw_path.read_bytes() != raw:
                            continue
                        return {"reason": "official_corporate_action_noncomparable_change", "raw_change_marker": row["漲跌"],
                            "source_id": receipt["source_id"], "source_date": receipt["source_date"], "available_at": receipt["available_at"],
                            "receipt_path": str(receipt_path), "raw_response_sha256": digest,
                            "historical_pit": False, "quote_values_bound": True}
            except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
                continue
        return None
