"""FinMind 現金流量表候選抓取器。

FinMind ``TaiwanStockCashFlowsStatement`` 的列包含數值與觀測日期，但不提供
可驗證的官方公告／可得日期。本模組只產生帶 provenance 的研究候選檔，不寫入
正式 SQLite、availability mapping 或 ML 歷史資料；``eligibility`` 固定為
``numeric_only``，避免把第三方觀測時間誤當成 point-in-time 證據。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FINMIND_CASHFLOW_SOURCE = "finmind.cashflow_candidate"
FINMIND_CASHFLOW_DATASET = "TaiwanStockCashFlowsStatement"
FINMIND_CASHFLOW_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_CASHFLOW_SOURCE_VERSION_PREFIX = "finmind-taiwan-stock-cashflow"
FINMIND_CASHFLOW_COLUMNS = [
    "stock_code",
    "period",
    "date",
    "item_code",
    "item_name",
    "value",
    "source_row_hash",
    "observed_at",
    "available_date_candidate",
    "eligibility",
    "source",
    "source_version",
]


@dataclass(frozen=True)
class FinMindCashflowHarvestResult:
    """一次候選抓取的可審計摘要。"""

    rows: list[dict[str, str]]
    state: dict[str, list[str]]
    requested_stock_count: int
    fetched_stock_count: int
    failed_stock_count: int
    rejected_row_count: int
    rejection_reasons: tuple[tuple[str, int], ...]
    observed_at: str
    row_output: Path | None = None
    state_file: Path | None = None

    def to_markdown(self, sample_size: int = 5) -> str:
        lines = [
            "# FinMind Cashflow Candidate",
            "",
            f"- requested_stock_count: {self.requested_stock_count}",
            f"- fetched_stock_count: {self.fetched_stock_count}",
            f"- failed_stock_count: {self.failed_stock_count}",
            f"- rejected_row_count: {self.rejected_row_count}",
            f"- parsed_rows: {len(self.rows)}",
            f"- observed_at: {self.observed_at}",
            "- eligibility: numeric_only",
            "- formal_db_write: false",
            "",
            "## Sample Rows",
        ]
        for row in self.rows[:sample_size]:
            lines.append(
                "- "
                + ", ".join(
                    f"{key}={row[key]}"
                    for key in (
                        "stock_code",
                        "period",
                        "item_code",
                        "value",
                        "source_version",
                    )
                )
            )
        if not self.rows:
            lines.append("- none")
        if self.rejection_reasons:
            lines.extend(["", "## Rejections"])
            lines.extend(
                f"- {reason}: {count}"
                for reason, count in self.rejection_reasons
            )
        return "\n".join(lines)


def harvest_finmind_cashflow_candidate(
    *,
    stock_codes: tuple[str, ...],
    start_date: str,
    end_date: str,
    token: str,
    fetch_rows: Callable[[str, str, str, str], list[dict]] | None = None,
    output_dir: Path | None = None,
    state_file: Path | None = None,
    resume: bool = False,
    fetch_date: date | None = None,
    observed_at: str | None = None,
    sleep_seconds: float = 0.0,
) -> FinMindCashflowHarvestResult:
    """按股票抓取候選現金流列，支援中斷續跑但不寫正式資料。"""

    fetcher = fetch_rows or fetch_finmind_cashflow_rows
    fetch_date = fetch_date or date.today()
    output_dir = Path(output_dir) if output_dir is not None else None
    state_file = Path(state_file) if state_file is not None else (
        output_dir / "finmind_cashflow_fetch_state.json" if output_dir else None
    )
    state = _load_state(state_file) if resume and state_file is not None else _empty_state()
    completed = set(state["completed_stock_codes"])
    failed = set(state["failed_stock_codes"])
    rows: list[dict[str, str]] = []
    rejection_counts: dict[str, int] = {}
    fetched_stock_count = 0
    source_version = f"{FINMIND_CASHFLOW_SOURCE_VERSION_PREFIX}-{fetch_date.isoformat()}"
    capture_time = _normalise_observed_at(observed_at)

    for index, stock_code in enumerate(stock_codes):
        normalized_code = str(stock_code).strip()
        if not normalized_code:
            continue
        if resume and normalized_code in completed:
            continue
        try:
            source_rows = fetcher(normalized_code, start_date, end_date, token)
        except Exception:
            failed.add(normalized_code)
            state["failed_stock_codes"] = sorted(failed)
            _write_state(state_file, state)
            continue
        fetched_stock_count += 1
        completed.add(normalized_code)
        failed.discard(normalized_code)
        normalized_rows, row_rejections = _normalize_finmind_cashflow_rows(
            source_rows,
            normalized_code,
            source_version,
            capture_time,
        )
        rows.extend(normalized_rows)
        for reason, count in row_rejections.items():
            rejection_counts[reason] = rejection_counts.get(reason, 0) + count
        state["completed_stock_codes"] = sorted(completed)
        state["failed_stock_codes"] = sorted(failed)
        _write_state(state_file, state)
        if sleep_seconds > 0 and index < len(stock_codes) - 1:
            time.sleep(sleep_seconds)

    rows.sort(key=lambda row: (row["stock_code"], row["date"], row["item_code"]))
    row_output = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        row_output = output_dir / f"finmind_cashflow_candidate_{fetch_date.isoformat()}.csv"
        _write_csv(row_output, FINMIND_CASHFLOW_COLUMNS, rows)
    return FinMindCashflowHarvestResult(
        rows=rows,
        state=state,
        requested_stock_count=len(stock_codes),
        fetched_stock_count=fetched_stock_count,
        failed_stock_count=len(failed),
        rejected_row_count=sum(rejection_counts.values()),
        rejection_reasons=tuple(sorted(rejection_counts.items())),
        observed_at=capture_time,
        row_output=row_output,
        state_file=state_file,
    )


def fetch_finmind_cashflow_rows(
    stock_code: str,
    start_date: str,
    end_date: str,
    token: str,
) -> list[dict]:
    """呼叫 FinMind Data API，回傳未加工 rows 供候選層驗證。"""

    query = urlencode(
        {
            "dataset": FINMIND_CASHFLOW_DATASET,
            "data_id": stock_code,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    request = Request(
        f"{FINMIND_CASHFLOW_URL}?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "technical-analysis-v4-cashflow-candidate/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    if not payload.get("status"):
        raise RuntimeError(str(payload.get("msg") or "FinMind request failed"))
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise RuntimeError("FinMind response data is not a list")
    return data


def _normalize_finmind_cashflow_rows(
    source_rows: Iterable[dict],
    fallback_stock_code: str,
    source_version: str,
    observed_at: str,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    rows: list[dict[str, str]] = []
    rejection_counts: dict[str, int] = {}
    for source_row in source_rows:
        if not isinstance(source_row, dict):
            _increment(rejection_counts, "row_not_object")
            continue
        stock_code = str(source_row.get("stock_id") or fallback_stock_code).strip()
        source_stock_code = str(source_row.get("stock_id") or "").strip()
        date_text = str(source_row.get("date") or "").strip()[:10]
        item_code = str(source_row.get("type") or "").strip()
        item_name = str(source_row.get("origin_name") or "").strip()
        raw_value = source_row.get("value")
        if not stock_code:
            _increment(rejection_counts, "missing_stock_code")
            continue
        if source_stock_code and source_stock_code != fallback_stock_code:
            _increment(rejection_counts, "stock_code_mismatch")
            continue
        if _parse_iso_date(date_text) is None:
            _increment(rejection_counts, "invalid_date")
            continue
        if not item_code:
            _increment(rejection_counts, "missing_item_code")
            continue
        if raw_value is None or not str(raw_value).strip():
            _increment(rejection_counts, "missing_value")
            continue
        try:
            value = Decimal(str(raw_value).strip())
        except (InvalidOperation, ValueError):
            _increment(rejection_counts, "invalid_value")
            continue
        if not value.is_finite():
            _increment(rejection_counts, "non_finite_value")
            continue
        canonical_row = json.dumps(
            source_row,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        rows.append(
            {
                "stock_code": stock_code,
                "period": _quarter_from_date(date_text),
                "date": date_text,
                "item_code": item_code,
                "item_name": item_name,
                "value": format(value, "f"),
                "source_row_hash": "sha256:" + hashlib.sha256(canonical_row).hexdigest(),
                "observed_at": observed_at,
                "available_date_candidate": "",
                "eligibility": "numeric_only",
                "source": FINMIND_CASHFLOW_SOURCE,
                "source_version": source_version,
            }
        )
    return rows, rejection_counts


def _quarter_from_date(date_text: str) -> str:
    parsed = _parse_iso_date(date_text)
    if parsed is None:
        return ""
    return f"{parsed.year:04d}-Q{(parsed.month - 1) // 3 + 1}"


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _normalise_observed_at(value: str | None) -> str:
    if value is None or not str(value).strip():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must include an explicit timezone")
    return parsed.isoformat(timespec="seconds")


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _empty_state() -> dict[str, list[str]]:
    return {"completed_stock_codes": [], "failed_stock_codes": []}


def _load_state(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return _empty_state()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "completed_stock_codes": sorted(payload.get("completed_stock_codes") or []),
        "failed_stock_codes": sorted(payload.get("failed_stock_codes") or []),
    }


def _write_state(path: Path | None, state: dict[str, list[str]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


__all__ = [
    "FINMIND_CASHFLOW_COLUMNS",
    "FINMIND_CASHFLOW_DATASET",
    "FINMIND_CASHFLOW_SOURCE",
    "FINMIND_CASHFLOW_SOURCE_VERSION_PREFIX",
    "FINMIND_CASHFLOW_URL",
    "FinMindCashflowHarvestResult",
    "fetch_finmind_cashflow_rows",
    "harvest_finmind_cashflow_candidate",
]
