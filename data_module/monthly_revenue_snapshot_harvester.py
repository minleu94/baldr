"""MOPS 月營收歷史快照候選抓取器。

本模組只建立可追溯的 raw/candidate snapshot，不產生 availability mapping，
也不寫入 SQLite。snapshot 的 period 是營收月份，不得被解讀為 available_date。
"""

from __future__ import annotations

import csv
from hashlib import sha256
import re
import stat
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

from bs4 import BeautifulSoup

from data_module.contracts.fundamental import SourceDiagnostic
from data_module.monthly_revenue_availability_history import (
    _fetch_mops_static_monthly_revenue_html,
    _iter_periods,
)


MOPS_SNAPSHOT_SOURCE = "mops.monthly_revenue_static_snapshot"
MOPS_SNAPSHOT_COLUMNS = [
    "market",
    "period",
    "stock_code",
    "company_name",
    "current_month_revenue",
    "previous_month_revenue",
    "previous_year_month_revenue",
    "mom_pct",
    "yoy_pct",
    "cumulative_revenue",
    "previous_year_cumulative_revenue",
    "cumulative_yoy_pct",
    "note",
    "fetched_at",
    "source",
    "source_version",
]


@dataclass(frozen=True)
class MopsMonthlyRevenueSnapshotResult:
    rows: list[dict[str, str]]
    requested_periods: tuple[str, ...]
    fetched_periods: tuple[str, ...]
    diagnostics: tuple[SourceDiagnostic, ...] = ()
    cancelled: bool = False

    @property
    def valid_candidate(self) -> bool:
        return bool(self.fetched_periods) and not any(
            diagnostic.code.endswith("fetch_failed") for diagnostic in self.diagnostics
        )

    def to_markdown(self, sample_size: int = 5) -> str:
        lines = [
            "# MOPS Monthly Revenue Snapshot Candidate",
            "",
            f"- requested_periods: {len(self.requested_periods)}",
            f"- fetched_periods: {len(self.fetched_periods)}",
            f"- parsed_rows: {len(self.rows)}",
            f"- diagnostics: {len(self.diagnostics)}",
            "",
            "## Sample Rows",
        ]
        for row in self.rows[:sample_size]:
            lines.append(
                "- "
                + ", ".join(
                    f"{key}={row[key]}"
                    for key in (
                        "market",
                        "period",
                        "stock_code",
                        "company_name",
                        "current_month_revenue",
                        "source_version",
                    )
                )
            )
        if not self.rows:
            lines.append("- none")
        return "\n".join(lines)


def fetch_mops_static_monthly_revenue_html(*, market: str, period: str) -> str:
    return _fetch_mops_static_monthly_revenue_html(market=market, period=period)


def create_monthly_revenue_snapshot_capture_directory(
    output_base: Path, *, fetch_date: date
) -> Path:
    """為每次擷取建立一個唯一且不可重用的候選目錄。"""
    base = Path(output_base)
    base.mkdir(parents=True, exist_ok=True)
    if _is_reparse_point(base):
        raise ValueError(f"月營收輸出根目錄不可是 symlink/reparse point: {base}")
    capture_parent = base / "captures"
    capture_parent.mkdir(exist_ok=True)
    if _is_reparse_point(capture_parent):
        raise ValueError(f"月營收擷取目錄不可是 symlink/reparse point: {capture_parent}")

    for _ in range(3):
        capture_dir = capture_parent / f"run_{fetch_date.isoformat()}_{uuid4().hex}"
        try:
            capture_dir.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return capture_dir
    raise FileExistsError(f"無法配置唯一的月營收擷取目錄: {capture_parent}")


def build_mops_monthly_revenue_snapshot(
    *,
    start_period: str,
    end_period: str,
    markets: tuple[str, ...],
    fetch_date: date,
    fetch_html: Callable[..., str] = fetch_mops_static_monthly_revenue_html,
    save_html_dir: Path | None = None,
    sleep_seconds: float = 0.0,
    sleep: Callable[[float], object] = time.sleep,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> MopsMonthlyRevenueSnapshotResult:
    requested_periods = tuple(_iter_periods(start_period, end_period))
    rows: list[dict[str, str]] = []
    fetched_periods: set[str] = set()
    diagnostics: list[SourceDiagnostic] = []
    request_pairs = [(market, period) for period in requested_periods for market in markets]
    cancelled = False
    for index, (market, period) in enumerate(request_pairs):
            if cancel_callback is not None:
                try:
                    if cancel_callback():
                        cancelled = True
                        break
                except Exception:
                    # 取消 callback 的故障不應假造取消或丟棄已取得來源。
                    pass
            try:
                html = fetch_html(market=market, period=period)
            except Exception as exc:
                diagnostics.append(
                    _diagnostic(
                        "monthly_revenue_snapshot.mops_static_fetch_failed",
                        market,
                        f"failed to fetch MOPS static monthly revenue; period={period}; error={exc}",
                    )
                )
                continue
            # fetch_html returns only after the official response body has been read.
            fetched_at = _utc_now_text()
            fetched_periods.add(period)
            if save_html_dir is not None:
                save_html_dir.mkdir(parents=True, exist_ok=True)
                raw_path = save_html_dir / f"{market}_{period}.html"
                with raw_path.open("x", encoding="utf-8-sig", newline="") as handle:
                    handle.write(html)
            source_version = _snapshot_source_version(
                market=market,
                period=period,
                html=html,
                captured_at=fetched_at,
            )
            parsed_rows, parse_diagnostics = parse_mops_monthly_revenue_snapshot_html(
                html,
                market=market,
                period=period,
                fetched_at=fetched_at,
                source_version=source_version,
            )
            rows.extend(parsed_rows)
            diagnostics.extend(parse_diagnostics)
            if sleep_seconds > 0 and index < len(request_pairs) - 1:
                sleep(sleep_seconds)
            if progress_callback is not None:
                try:
                    progress_callback(
                        f"已處理 MOPS {market} {period}",
                        int(((index + 1) / max(len(request_pairs), 1)) * 100),
                    )
                except Exception:
                    pass

    rows.sort(key=lambda row: (row["period"], row["market"], row["stock_code"]))
    return MopsMonthlyRevenueSnapshotResult(
        rows=rows,
        requested_periods=requested_periods,
        fetched_periods=tuple(sorted(fetched_periods)),
        diagnostics=tuple(diagnostics),
        cancelled=cancelled,
    )


def parse_mops_monthly_revenue_snapshot_html(
    html: str,
    *,
    market: str,
    period: str,
    fetched_at: str,
    source_version: str,
) -> tuple[list[dict[str, str]], tuple[SourceDiagnostic, ...]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    diagnostics: list[SourceDiagnostic] = []
    saw_company_column = False
    saw_required_columns = False
    seen_stock_codes: set[str] = set()

    for table in soup.find_all("table"):
        header: list[str] | None = None
        for tr in table.find_all("tr"):
            cells = [_cell_text(cell) for cell in tr.find_all(["th", "td"])]
            if not cells:
                continue
            normalized_cells = [_normalize_header(cell) for cell in cells]
            if "公司代號" in normalized_cells:
                saw_company_column = True
                if _has_required_headers(normalized_cells):
                    saw_required_columns = True
                    header = normalized_cells
                continue
            if header is None:
                continue
            mapped = dict(zip(header, cells, strict=False))
            stock_code = _clean_text(mapped.get("公司代號", ""))
            if not re.fullmatch(r"\d{4,6}", stock_code):
                continue
            if stock_code in seen_stock_codes:
                continue
            seen_stock_codes.add(stock_code)
            rows.append(
                {
                    "market": market,
                    "period": period,
                    "stock_code": stock_code,
                    "company_name": _clean_text(mapped.get("公司名稱", "")),
                    "current_month_revenue": _clean_number(mapped.get("當月營收", "")),
                    "previous_month_revenue": _clean_number(mapped.get("上月營收", "")),
                    "previous_year_month_revenue": _clean_number(
                        mapped.get("去年當月營收", "")
                    ),
                    "mom_pct": _clean_number(_lookup(mapped, ("上月比較增減(%)", "上月比較增減%"))),
                    "yoy_pct": _clean_number(_lookup(mapped, ("去年同月增減(%)", "去年同月增減%"))),
                    "cumulative_revenue": _clean_number(mapped.get("當月累計營收", "")),
                    "previous_year_cumulative_revenue": _clean_number(
                        mapped.get("去年累計營收", "")
                    ),
                    "cumulative_yoy_pct": _clean_number(
                        _lookup(mapped, ("前期比較增減(%)", "前期比較增減%"))
                    ),
                    "note": _clean_text(mapped.get("備註", "")),
                    "fetched_at": fetched_at,
                    "source": MOPS_SNAPSHOT_SOURCE,
                    "source_version": source_version,
                }
            )

    if not saw_company_column or not saw_required_columns:
        diagnostics.append(
            _diagnostic(
                "monthly_revenue_snapshot.mops_missing_required_columns",
                market,
                f"MOPS monthly revenue snapshot missing required columns; period={period}",
            )
        )
    elif not rows:
        diagnostics.append(
            _diagnostic(
                "monthly_revenue_snapshot.mops_no_data_rows",
                market,
                f"MOPS monthly revenue snapshot has no parseable company rows; period={period}",
            )
        )
    return rows, tuple(diagnostics)


def write_mops_snapshot_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MOPS_SNAPSHOT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _has_required_headers(headers: list[str]) -> bool:
    required = {
        "公司代號",
        "公司名稱",
        "當月營收",
        "上月營收",
        "去年當月營收",
        "當月累計營收",
        "去年累計營收",
    }
    return required.issubset(set(headers))


def _snapshot_source_version(
    *, market: str, period: str, html: str, captured_at: str | None = None
) -> str:
    """以市場、實際期別與回應內容雜湊建立可重現的來源版本。"""
    digest = sha256(html.encode("utf-8")).hexdigest()
    if captured_at is None:
        return f"mops-static-{market}-{period}-sha256-{digest}"
    parsed = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("monthly source capture time must include a timezone")
    completed = parsed.astimezone(timezone.utc).isoformat()
    return (
        f"mops-static-snapshot.v2:{market}:{period}:body_completed_at:{completed}"
        f":sha256:{digest}"
    )


def _lookup(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in row:
            return row[name]
    return ""


def _cell_text(cell) -> str:
    return cell.get_text("", strip=True).replace("\xa0", " ")


def _clean_text(value: str) -> str:
    return str(value).strip().replace("\xa0", " ")


def _normalize_header(value: str) -> str:
    cleaned = _clean_text(value)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = cleaned.replace("％", "%")
    return cleaned


def _clean_number(value: str) -> str:
    cleaned = _clean_text(value)
    cleaned = cleaned.replace(",", "").replace("％", "").replace("%", "")
    return cleaned


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_reparse_point(path: Path) -> bool:
    try:
        file_info = path.lstat()
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(getattr(file_info, "st_file_attributes", 0) & reparse_flag)


def _diagnostic(code: str, market: str, message: str) -> SourceDiagnostic:
    return SourceDiagnostic(
        code=code,
        stock_code="",
        message=message,
        market=market,
    )
