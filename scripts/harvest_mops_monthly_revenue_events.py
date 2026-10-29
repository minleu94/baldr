"""MOPS ezSearch 月營收公告事件（含更正紀錄）批次取得工具。

依據排查規範：
- 使用 .venv-scrapling 執行環境中的 Scrapling / curl_cffi 進行純 HTTP 存取。
- 嚴格遵守 10 秒間隔（含隨機微幅抖動）。
- 市場分流（上市 sii、上櫃 otc）與高峰期細分（6~8 日、9~10 日），徹底避免單次 1,000 筆上限。
- 完整保留不可變 raw JSON、計算 SHA-256、產出 manifest.csv 與 events.csv。
- 支援斷點續傳（Checkpointing），中斷重啟自動跳過已完成視窗。
"""

from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Mapping

from scrapling import Fetcher

EZSEARCH_URL = "https://mopsov.twse.com.tw/mops/web/ezsearch_query"
EZSEARCH_REFERER = "https://mopsov.twse.com.tw/mops/web/ezsearch"
TAIPEI_TZ = timezone(timedelta(hours=8))
MARKET_LABELS = {
    "sii": "上市",
    "otc": "上櫃",
    "rotc": "興櫃",
    "pub": "公開發行",
}

_SUBJECT_PERIOD_RE = re.compile(r"(?P<roc_year>\d{2,3})年(?P<month>\d{1,2})月")


def _sha256_of_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _gregorian_to_roc_date(dt: date) -> str:
    if dt.year <= 1911:
        raise ValueError("year must be after 1911")
    return f"{dt.year - 1911:03d}/{dt.month:02d}/{dt.day:02d}"


def _roc_to_iso_date(roc_str: str) -> str:
    parts = roc_str.strip().split("/")
    if len(parts) == 3:
        year = int(parts[0]) + 1911
        month = int(parts[1])
        day = int(parts[2])
        return f"{year:04d}-{month:02d}-{day:02d}"
    return roc_str


def parse_subject(subject: str) -> tuple[str, bool]:
    period = ""
    match = _SUBJECT_PERIOD_RE.search(subject)
    if match:
        year = int(match.group("roc_year")) + 1911
        month = int(match.group("month"))
        period = f"{year:04d}-{month:02d}"
    is_correction = any(kw in subject for kw in ("更正", "補正", "重新申報", "勘誤"))
    return period, is_correction


def generate_windows(
    year: int,
    start_month: int,
    end_month: int,
    max_date: date,
) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    for month in range(start_month, end_month + 1):
        _, last_day = calendar.monthrange(year, month)
        # 拆分原則：平日 5~10 天，高峰期 6~8 日、9~10 日切細以避開 1000 筆上限
        ranges = [(1, 5), (6, 8), (9, 10), (11, 15), (16, 20), (21, last_day)]
        for s_day, e_day in ranges:
            start_d = date(year, month, s_day)
            end_limit = (
                min(e_day, max_date.day)
                if (year == max_date.year and month == max_date.month)
                else e_day
            )
            end_d = date(year, month, end_limit)
            if start_d > max_date:
                continue
            if end_d > max_date:
                end_d = max_date
            windows.append((start_d, end_d))
    return windows


def generate_multi_year_windows(
    start_year: int,
    end_year: int,
    start_month: int,
    end_month: int,
    max_date: date,
    reverse_years: bool = True,
) -> list[tuple[date, date]]:
    years = list(range(start_year, end_year + 1))
    if reverse_years:
        years.reverse()

    all_windows: list[tuple[date, date]] = []
    for y in years:
        if start_year == end_year:
            s_m, e_m = start_month, end_month
        else:
            s_m = start_month if y == start_year else 1
            e_m = end_month if y == end_year else 12
        all_windows.extend(generate_windows(y, s_m, e_m, max_date))
    return all_windows


def load_checkpoint(checkpoint_path: Path) -> dict[str, Any]:
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception as err:
            print(f"[WARN] Failed to read checkpoint {checkpoint_path}: {err}", file=sys.stderr)
    return {}


def save_checkpoint(checkpoint_path: Path, data: dict[str, Any]) -> None:
    temp_path = checkpoint_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(checkpoint_path)


def _append_csv_with_retry(path: Path, rows: list[list[Any]], max_retries: int = 10, delay: float = 0.5) -> None:
    for attempt in range(max_retries):
        try:
            with path.open("a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise


def _save_checkpoint_with_retry(checkpoint_path: Path, data: dict[str, Any], max_retries: int = 10, delay: float = 0.5) -> None:
    for attempt in range(max_retries):
        try:
            save_checkpoint(checkpoint_path, data)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise


def fetch_ezsearch_window(
    market: str,
    start_date: date,
    end_date: date,
    timeout: int = 30,
) -> tuple[int, bytes, dict[str, Any]]:
    payload = {
        "step": "00",
        "RADIO_CM": "1",
        "TYPEK": market,
        "CO_MARKET": "",
        "CO_ID": "",
        "PRO_ITEM": "F22",
        "SUBJECT": "",
        "SDATE": _gregorian_to_roc_date(start_date),
        "EDATE": _gregorian_to_roc_date(end_date),
        "lang": "TW",
        "AN": "",
    }
    headers = {
        "Referer": EZSEARCH_REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }
    res = Fetcher.post(EZSEARCH_URL, data=payload, headers=headers, timeout=timeout)
    status_code = res.status
    body = res.body

    parsed_json: dict[str, Any] = {}
    if status_code == 200:
        try:
            text = body.decode("utf-8-sig", errors="strict")
            parsed_json = json.loads(text)
        except Exception as err:
            raise ValueError(f"MOPS returned HTTP 200 but the response is not valid UTF-8 JSON: {err}") from err

        if not isinstance(parsed_json, dict):
            raise ValueError("MOPS returned HTTP 200 JSON with an unexpected top-level shape")
        rows = parsed_json.get("data")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("MOPS returned HTTP 200 JSON without a valid data row list")

    return status_code, body, parsed_json


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="MOPS ezSearch F22 月營收公告事件批次取得工具")
    parser.add_argument("--year", type=int, default=None, help="目標單一西元年 (如 2026)")
    parser.add_argument("--start-year", type=int, default=None, help="目標起始西元年 (如 2020)")
    parser.add_argument("--end-year", type=int, default=None, help="目標結束西元年 (如 2025)")
    parser.add_argument("--start-month", type=int, default=1, help="起始月份 (預設 1)")
    parser.add_argument("--end-month", type=int, default=12, help="結束月份 (預設 12)")
    parser.add_argument(
        "--markets",
        nargs="+",
        default=["sii", "otc"],
        choices=["sii", "otc", "rotc", "pub"],
        help="市場別 (預設 sii otc)",
    )
    parser.add_argument("--delay", type=float, default=10.0, help="請求間隔秒數 (預設 10.0)")
    parser.add_argument("--jitter", type=float, default=1.0, help="隨機增加秒數上限 (預設 1.0)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="原件輸出目錄 (若未指定，單年為 output/mops_harvest_<year>，多年為 output/mops_harvest_<start>_<end>)",
    )
    parser.add_argument("--no-reverse", action="store_true", help="依年代正序 (舊到新) 採集；預設為倒序 (新到舊)")
    parser.add_argument("--dry-run", action="store_true", help="僅列印計畫窗，不發送網路請求")

    args = parser.parse_args()

    # 解析目標年度範圍
    if args.year is not None:
        start_year = args.year
        end_year = args.year
    elif args.start_year is not None or args.end_year is not None:
        start_year = args.start_year if args.start_year is not None else 2020
        end_year = args.end_year if args.end_year is not None else 2025
    else:
        start_year = 2026
        end_year = 2026

    if start_year > end_year:
        start_year, end_year = end_year, start_year

    if args.output_dir is not None:
        output_dir: Path = args.output_dir.resolve()
    else:
        if start_year == end_year:
            output_dir = Path(f"output/mops_harvest_{start_year}").resolve()
        else:
            output_dir = Path(f"output/mops_harvest_{start_year}_{end_year}").resolve()

    raw_dir = output_dir / "raw"
    checkpoint_file = output_dir / "checkpoint.json"
    manifest_file = output_dir / "manifest.csv"
    events_file = output_dir / "events.csv"

    today_taipei = datetime.now(TAIPEI_TZ).date()
    windows = generate_multi_year_windows(
        start_year=start_year,
        end_year=end_year,
        start_month=args.start_month,
        end_month=args.end_month,
        max_date=today_taipei,
        reverse_years=not args.no_reverse,
    )

    planned_tasks: list[tuple[str, date, date]] = []
    for m in args.markets:
        for w_start, w_end in windows:
            planned_tasks.append((m, w_start, w_end))

    total_tasks = len(planned_tasks)
    print(
        f"[INFO] 總計規劃 {total_tasks} 個查詢視窗 "
        f"({start_year}~{end_year} 年，市場: {', '.join(args.markets)}，輸出: {output_dir})"
    )

    if args.dry_run:
        print("[DRY-RUN] 計畫視窗清冊前 10 筆：")
        for i, (m, s, e) in enumerate(planned_tasks[:10], 1):
            print(f"  {i}. ({m}) {s} ~ {e} ({_gregorian_to_roc_date(s)} ~ {_gregorian_to_roc_date(e)})")
        print(f"[DRY-RUN] ... 總共 {total_tasks} 筆任務。結束。")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = load_checkpoint(checkpoint_file)

    # 確保 manifest.csv 與 events.csv 表頭存在
    manifest_headers = [
        "file_path",
        "file_name",
        "source_url",
        "http_method",
        "http_status",
        "acquired_at_utc",
        "acquired_at_taipei",
        "market",
        "query_window",
        "row_count",
        "sha256",
        "byte_count",
    ]
    if not manifest_file.exists():
        with manifest_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(manifest_headers)

    event_headers = [
        "market",
        "stock_code",
        "stock_name",
        "industry",
        "announcement_item",
        "announced_date",
        "announced_time",
        "announced_at",
        "subject",
        "period",
        "is_correction",
        "detail_url",
        "raw_file",
        "raw_sha256",
    ]
    if not events_file.exists():
        with events_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(event_headers)

    success_count = 0
    skip_count = 0
    total_events = 0
    total_corrections = 0
    start_wall_time = time.time()

    for idx, (market, w_start, w_end) in enumerate(planned_tasks, 1):
        s_roc = _gregorian_to_roc_date(w_start)
        e_roc = _gregorian_to_roc_date(w_end)
        s_slug = s_roc.replace("/", "")
        e_slug = e_roc.replace("/", "")
        window_key = f"{market}_F22_{s_slug}_{e_slug}"
        raw_filename = f"ezsearch_F22_{market}_{s_slug}_{e_slug}.json"
        raw_filepath = raw_dir / raw_filename

        # 斷點續傳檢查
        if window_key in checkpoint and raw_filepath.exists():
            cp_data = checkpoint[window_key]
            current_sha = _sha256_of_bytes(raw_filepath.read_bytes())
            if current_sha == cp_data.get("sha256"):
                skip_count += 1
                total_events += cp_data.get("row_count", 0)
                total_corrections += cp_data.get("corrections_count", 0)
                print(
                    f"[{idx}/{total_tasks}] [SKIP] ({market}) {s_roc} ~ {e_roc} "
                    f"已存在 ({cp_data.get('row_count', 0)} 列, {cp_data.get('corrections_count', 0)} 更正)"
                )
                continue

        # 執行網路請求 (最多重試 3 次)
        attempts = 0
        max_attempts = 3
        fetch_ok = False
        status_code = 0
        raw_body = b""
        parsed_json: dict[str, Any] = {}
        acquired_at_utc = ""
        acquired_at_taipei = ""

        while attempts < max_attempts and not fetch_ok:
            attempts += 1
            try:
                status_code, raw_body, parsed_json = fetch_ezsearch_window(
                    market=market,
                    start_date=w_start,
                    end_date=w_end,
                )
                if status_code == 200:
                    # Record when the response was received and validated, not request start.
                    acquired_at_utc = datetime.now(timezone.utc).isoformat()
                    acquired_at_taipei = datetime.now(TAIPEI_TZ).isoformat()
                    fetch_ok = True
                elif status_code in (429, 403):
                    print(
                        f"\n[ALERT] MOPS 返回 HTTP {status_code}！觸發速率保護，安全中止作業以防封鎖 IP！",
                        file=sys.stderr,
                    )
                    return 2
                else:
                    print(
                        f"[RETRY {attempts}/{max_attempts}] ({market}) {s_roc}~{e_roc} HTTP {status_code}, 等待 15s...",
                        file=sys.stderr,
                    )
                    time.sleep(15.0)
            except Exception as err:
                print(
                    f"[RETRY {attempts}/{max_attempts}] ({market}) {s_roc}~{e_roc} 連線異常: {err}, 等待 15s...",
                    file=sys.stderr,
                )
                if attempts < max_attempts:
                    time.sleep(15.0)

        if not fetch_ok:
            print(f"[FAIL] ({market}) {s_roc} ~ {e_roc} 重試失敗，中斷流程以保完整性。", file=sys.stderr)
            return 1

        # 寫入 raw 檔案（未經改動之原始 bytes）
        raw_filepath.write_bytes(raw_body)
        raw_sha = _sha256_of_bytes(raw_body)
        byte_count = len(raw_body)

        # 解析結果列
        rows = parsed_json.get("data", [])
        row_count = len(rows)
        corrections_in_window = 0

        # 1000 筆上限警告
        if row_count >= 1000:
            print(
                f"[WARNING] 視窗 ({market}) {s_roc} ~ {e_roc} 筆數達到 {row_count}！可能觸發 1000 筆截斷！",
                file=sys.stderr,
            )

        # 寫入 events.csv
        parsed_event_rows = []
        for r in rows:
            subject = str(r.get("SUBJECT", "")).strip()
            period, is_corr = parse_subject(subject)
            if is_corr:
                corrections_in_window += 1

            cdate = str(r.get("CDATE", "")).strip()
            ctime = str(r.get("CTIME", "")).strip()
            announced_d = _roc_to_iso_date(cdate)
            announced_at = f"{announced_d}T{ctime}+08:00" if (announced_d and ctime) else ""

            parsed_event_rows.append([
                market,
                str(r.get("COMPANY_ID", "")).strip(),
                str(r.get("COMPANY_NAME", "")).strip(),
                str(r.get("CODE_NAME", "")).strip(),
                str(r.get("AN_CODE", "")).strip(),
                announced_d,
                ctime,
                announced_at,
                subject,
                period,
                "TRUE" if is_corr else "FALSE",
                str(r.get("HYPERLINK", "")).strip(),
                f"raw/{raw_filename}",
                raw_sha,
            ])

        if parsed_event_rows:
            _append_csv_with_retry(events_file, parsed_event_rows)

        # 寫入 manifest.csv
        manifest_row = [
            f"raw/{raw_filename}",
            raw_filename,
            EZSEARCH_URL,
            "POST",
            status_code,
            acquired_at_utc,
            acquired_at_taipei,
            market,
            f"{s_roc}-{e_roc}",
            row_count,
            raw_sha,
            byte_count,
        ]
        _append_csv_with_retry(manifest_file, [manifest_row])

        # 更新 Checkpoint
        checkpoint[window_key] = {
            "market": market,
            "start_date": w_start.isoformat(),
            "end_date": w_end.isoformat(),
            "start_roc": s_roc,
            "end_roc": e_roc,
            "raw_file": f"raw/{raw_filename}",
            "sha256": raw_sha,
            "byte_count": byte_count,
            "http_status": status_code,
            "row_count": row_count,
            "corrections_count": corrections_in_window,
            "acquired_at_utc": acquired_at_utc,
            "acquired_at_taipei": acquired_at_taipei,
        }
        _save_checkpoint_with_retry(checkpoint_file, checkpoint)

        success_count += 1
        total_events += row_count
        total_corrections += corrections_in_window

        corr_msg = f", 含 {corrections_in_window} 筆更正" if corrections_in_window > 0 else ""
        print(
            f"[{idx}/{total_tasks}] [OK] ({market}) {s_roc} ~ {e_roc} "
            f"-> {row_count} 筆事件{corr_msg} (SHA: {raw_sha[:15]}...)"
        )

        # 隨機抖動間隔保護
        sleep_sec = args.delay + random.uniform(0.0, max(0.0, args.jitter))
        if idx < total_tasks:
            time.sleep(sleep_sec)

    elapsed = time.time() - start_wall_time
    print("\n" + "=" * 60)
    print(f"[SUMMARY] 批次作業圓滿完成！")
    print(f"  - 總視窗數: {total_tasks} (新取得: {success_count}, 續傳跳過: {skip_count})")
    print(f"  - 累計事件列數: {total_events} 筆")
    print(f"  - 累計更正紀錄: {total_corrections} 筆")
    print(f"  - 總耗時: {elapsed / 60:.1f} 分鐘")
    print(f"  - 輸出目錄: {output_dir}")
    print(f"    * Manifest: {manifest_file}")
    print(f"    * Events: {events_file}")
    print(f"    * Checkpoint: {checkpoint_file}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
