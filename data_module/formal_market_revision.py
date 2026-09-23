"""正式大盤歷史修訂的可得時間保護；不把晚取得資料追認為歷史 PIT。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from collections.abc import Iterable, Mapping


RECEIPT_DIR = Path('output/scheduled/formal_market_repair_receipts')


def validate_market_replacement(
    database_path: Path, records: Iterable[Mapping[str, object]], *, replace_all: bool = False,
    replace_dates: bool = False,
) -> None:
    """阻止舊 CSV 重匯覆蓋已修訂市場值；只驗證、不改輸入或資料庫。"""
    root = database_path.resolve().parent
    if root.name.lower() == 'sqlite':
        root = root.parent
    markers = sorted((root / RECEIPT_DIR).glob('*/revision.json'))
    if not markers:
        return
    incoming: dict[str, Mapping[str, object]] = {}
    incoming_dates: set[str] = set()
    for row in records:
        day = str(row.get('日期', '')).replace('-', '').replace('/', '')[:8]
        date.fromisoformat(f'{day[:4]}-{day[4:6]}-{day[6:]}')
        incoming_dates.add(day)
        name = row.get('指數名稱', 'TAIEX')
        if name not in ('TAIEX', '', None):
            continue
        if day in incoming:
            raise ValueError('市場匯入日期重複')
        incoming[day] = row
    for path in markers:
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
            if state['schema_version'] != 'formal-market-revision.v1' or Path(state['database_path']).resolve() != database_path.resolve():
                raise ValueError('市場修訂標記不符')
            if state['state'] == 'rolled_back':
                if hashlib.sha256((path.parent / 'rollback.json').read_bytes()).hexdigest() != state['rollback_sha256']:
                    raise ValueError('市場回復證據不符')
                continue
            if state['state'] != 'applied':
                raise ValueError('市場修訂尚未完成')
            receipt_bytes = (path.parent / 'receipt.json').read_bytes()
            if hashlib.sha256(receipt_bytes).hexdigest() != state['receipt_sha256']:
                raise ValueError('市場修訂 receipt 不符')
            receipt = json.loads(receipt_bytes)
            plan_bytes = (path.parent / 'plan.json').read_bytes()
            if hashlib.sha256(plan_bytes).hexdigest() != receipt['plan_sha256']:
                raise ValueError('市場修訂計畫不符')
            plan = json.loads(plan_bytes)
            first = plan['source_start_date'].replace('-', '')
            last = plan['source_end_date'].replace('-', '')
            expected = {row['日期']: row for row in plan['after']['rows'] if row['指數名稱'] == 'TAIEX' and first <= row['日期'] <= last}
            if replace_all and not set(expected) <= set(incoming):
                raise ValueError('整表匯入缺少已修訂市場日期')
            if replace_dates and not (set(expected) & incoming_dates) <= set(incoming):
                raise ValueError('整日匯入缺少已修訂 TAIEX 市場資料')
            for day, row in incoming.items():
                if not first <= day <= last:
                    continue
                if day not in expected:
                    raise ValueError('舊市場資料含已剔除的非交易日')
                for column in ('開盤價', '最高價', '最低價', '收盤價', '成交量', '收盤指數'):
                    if column not in row and not (replace_all or replace_dates):
                        continue
                    value = row.get(column, row.get('收盤價') if column == '收盤指數' else None)
                    if Decimal(str(value)) != Decimal(str(expected[day][column])):
                        raise ValueError(f'舊來源會覆蓋已修訂市場資料：{day}/{column}')
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
            raise ValueError(f'市場匯入遭修訂保護拒絕：{path}: {exc}') from exc


def assert_market_revision_safe(database_path: Path, decision_date: date) -> None:
    """既有歷史入口在修訂影響區間拒絕使用現況表，研究需用獨立來源。"""
    root = database_path.resolve().parent
    if root.name.lower() == 'sqlite':
        root = root.parent
    for marker in sorted((root / RECEIPT_DIR).glob('*/revision.json')):
        try:
            payload = json.loads(marker.read_text(encoding='utf-8'))
            if payload['schema_version'] != 'formal-market-revision.v1':
                raise ValueError('不支援的大盤修訂標記')
            if Path(payload['database_path']).resolve() != database_path.resolve():
                raise ValueError('大盤修訂資料庫不符')
            state = payload['state']
            if state not in {'pending', 'applied', 'rolled_back'}:
                raise ValueError('未知大盤修訂狀態')
            journal_bytes = (marker.parent / 'journal.json').read_bytes()
            journal = json.loads(journal_bytes)
            plan_bytes = (marker.parent / 'plan.json').read_bytes()
            if hashlib.sha256(plan_bytes).hexdigest() != journal['plan_sha256']:
                raise ValueError('大盤修訂計畫 hash 不符')
            plan = json.loads(plan_bytes)
            if any(payload[field] != plan[field] for field in ('database_path', 'source_start_date', 'source_end_date')):
                raise ValueError('大盤修訂標記與計畫範圍不符')
            if state == 'applied':
                receipt_bytes = (marker.parent / 'receipt.json').read_bytes()
                if hashlib.sha256(receipt_bytes).hexdigest() != payload['receipt_sha256'] or json.loads(receipt_bytes)['plan_sha256'] != journal['plan_sha256']:
                    raise ValueError('大盤修訂完成紀錄不符')
            start = date.fromisoformat(plan['source_start_date'])
            if state == 'rolled_back':
                receipt = marker.parent / 'rollback.json'
                if hashlib.sha256(receipt.read_bytes()).hexdigest() != payload['rollback_sha256']:
                    raise ValueError('大盤回復紀錄不符')
                continue
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f'大盤來源修訂紀錄無法驗證：{marker}') from exc
        if decision_date >= start:
            raise ValueError(
                f'formal market source revision blocks historical PIT from {start}; '
                'use a revision-aware rebuilt dataset; current data is not historical availability'
            )
