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
    def __init__(self, custody_root: Path, *, clock: Callable[[], datetime] | None = None):
        self.custody_root = custody_root
        self.clock = clock or (lambda: datetime.now(timezone.utc))

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
