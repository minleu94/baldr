"""以原始HTML重驗月營收，只追加現況研究觀測，不回填歷史PIT。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from bs4 import BeautifulSoup

from data_module.current_fundamental_snapshots import insert_observations, monthly_snapshot_rows
from data_module.monthly_revenue_snapshot_harvester import (
    MOPS_SNAPSHOT_COLUMNS, MOPS_SNAPSHOT_SOURCE,
    _snapshot_source_version, parse_mops_monthly_revenue_snapshot_html,
)
from data_module.scheduled_research_acquisition_binding import _read_stable_bytes


@dataclass(frozen=True)
class CurrentRevenuePlan:
    records: list[dict[str, str]]
    custody: dict[str, Any]


def plan_current_revenue(snapshot: Path, *, raw_html_dir: Path | None = None) -> CurrentRevenuePlan:
    """完整重解析並比對CSV與兩市場原件；金額單位必須有原件明示。"""
    snapshot = Path(snapshot)
    raw = _read_stable_bytes(snapshot, max_bytes=32 * 1024 * 1024)
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if reader.fieldnames != MOPS_SNAPSHOT_COLUMNS:
        raise ValueError('月營收候選欄位契約不符')
    rows = list(reader)
    if not rows:
        raise ValueError('月營收候選沒有資料')
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        if row['source'] != MOPS_SNAPSHOT_SOURCE or row['market'] not in {'twse', 'tpex'}:
            raise ValueError('候選來源身分不符')
        groups.setdefault((row['market'], row['period']), []).append(row)
    periods = {period for _, period in groups}
    if any({market for market, p in groups if p == period} != {'twse', 'tpex'} for period in periods):
        raise ValueError('候選缺少完整兩市場範圍')
    pins = []
    for (market, period), expected in sorted(groups.items()):
        path = (raw_html_dir or snapshot.parent / 'raw_html') / f'{market}_{period}.html'
        entity = _read_stable_bytes(path, max_bytes=32 * 1024 * 1024)
        html = entity.decode('utf-8-sig')
        text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
        year, month = map(int, period.split('-'))
        title = re.match(r'(上市|上櫃)公司(\d{2,3})年(\d{1,2})月份', text)
        if title is None or int(title[2]) + 1911 != year or int(title[3]) != month or title[1] != ('上市' if market == 'twse' else '上櫃'):
            raise ValueError('原始HTML的市場／期別不符')
        if not re.search(r'單位\s*[:：]\s*(?:新[臺台]幣\s*)?[千仟]元', text):
            raise ValueError('官方原件未明示千元，不能猜測金額單位')
        if len({row['fetched_at'] for row in expected}) != 1:
            raise ValueError('同一原件有不同抓取時間')
        captured_at: str | None = None
        source_version = expected[0]["source_version"]
        if source_version.startswith("mops-static-snapshot.v2:"):
            captured_at = expected[0]["fetched_at"]
        version = _snapshot_source_version(
            market=market,
            period=period,
            html=html,
            captured_at=captured_at,
        )
        if version != source_version:
            raise ValueError("候選來源版本與原始HTML捕獲身分不符")
        parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(
            html, market=market, period=period, fetched_at=expected[0]['fetched_at'], source_version=version,
        )
        key = lambda r: r['stock_code']
        if diagnostics or sorted(parsed, key=key) != sorted(expected, key=key):
            raise ValueError('候選CSV與原始HTML逐列內容／來源hash不符')
        pins.append({'path': str(path), 'bytes': len(entity), 'sha256': hashlib.sha256(entity).hexdigest(), 'source_version': version, 'source_available_at': captured_at, 'rows': len(parsed), 'market': market, 'period': period, 'source_unit': '千元'})
    # 逐列吻合且原始 HTML 雜湊已核對後，才傳入來源版本供月流量基礎驗證。
    verified_source_versions = frozenset(str(pin["source_version"]) for pin in pins)
    records = monthly_snapshot_rows(
        snapshot, verified_source_versions=verified_source_versions
    )
    if _read_stable_bytes(snapshot, max_bytes=32 * 1024 * 1024) != raw:
        raise ValueError('驗證期間候選檔案變動')
    custody = {'schema_version': 'current-monthly-revenue-plan.v3', 'normalization_version': 'mops-current-revenue-normalizer.v2', 'snapshot_path': str(snapshot), 'snapshot_sha256': hashlib.sha256(raw).hexdigest(), 'raw_artifacts': pins, 'raw_row_count': len(rows), 'normalized_record_count': len(records), 'same_report_yoy_comparator_count': sum(row['item_code'] == 'revenue_yoy_comparator' for row in records), 'periods': sorted(periods), 'observed_at': records[0]['observed_at'], 'target_table': 'fundamental_current_observations', 'formal_pit_eligible': False, 'formal_monthly_table_written': False, 'unit': 'TWD', 'period_basis': 'monthly_flow', 'basis_verified': all(row['basis_verified'] == '1' for row in records), 'aggregate_feature_eligible': False}
    return CurrentRevenuePlan(records, custody)


def apply_current_revenue(plan: CurrentRevenuePlan, *, db_file: Path, backup_dir: Path, receipt_dir: Path) -> dict[str, Any]:
    """先備份，再以完整交易追加不可變版本，冪等重試保留第一次觀測時間。"""
    if not db_file.is_file():
        raise FileNotFoundError(db_file)
    run_id = uuid4().hex
    backup_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f'current-revenue-before-{run_id}.sqlite'
    with sqlite3.connect(db_file.resolve().as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
        source.backup(target)
        if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite備份驗證失敗')
    with sqlite3.connect(db_file) as conn:
        conn.execute('BEGIN IMMEDIATE')
        inserted = insert_observations(conn, plan.records)
        conn.commit()
    result = dict(plan.custody, schema_version='current-monthly-revenue-apply.v1', run_id=run_id, inserted_count=inserted, backup_file=str(backup), database=str(db_file), applied=True, completed_at=datetime.now(timezone.utc).isoformat())
    receipt = receipt_dir / f'{run_id}.json'
    with receipt.open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    result['receipt_file'] = str(receipt)
    return result
