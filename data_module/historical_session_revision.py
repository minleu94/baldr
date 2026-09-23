"""補回真實歷史交易日後，保護新來源可得時間及重匯完整性。"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any

RECEIPT_DIR = Path('output/scheduled/historical_session_repair_receipts')


def _root(database_path: Path) -> Path:
    parent = database_path.resolve().parent
    return parent.parent if parent.name.lower() == 'sqlite' else parent


def _plan(path: Path, database_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        marker = json.loads(path.read_text(encoding='utf-8'))
        if marker['schema_version'] != 'historical-session-revision.v1' or Path(marker['database_path']).resolve() != database_path.resolve():
            raise ValueError('修訂標記不符')
        plan_bytes = (path.parent / 'plan.json').read_bytes()
        if hashlib.sha256(plan_bytes).hexdigest() != marker['plan_sha256']:
            raise ValueError('修訂計畫 hash 不符')
        plan = json.loads(plan_bytes)
        if marker['state'] not in {'pending', 'applied', 'rolled_back'} or plan['database_path'] != marker['database_path'] or marker.get('historical_pit') is not False:
            raise ValueError('修訂狀態不符')
        if plan['schema_version'] != 'historical-session-repair.v1' or plan['source_start_date'].replace('-', '') != min(plan['dates']):
            raise ValueError('修訂範圍不符')
        if marker['state'] in {'applied', 'rolled_back'}:
            receipt_bytes = (path.parent / ('receipt.json' if marker['state'] == 'applied' else 'rollback.json')).read_bytes()
            if hashlib.sha256(receipt_bytes).hexdigest() != marker['receipt_sha256']:
                raise ValueError('修訂完成證據不符')
            receipt = json.loads(receipt_bytes)
            if receipt['state'] != marker['state'] or receipt['plan_sha256'] != marker['plan_sha256'] or receipt['dates'] != plan['dates']:
                raise ValueError('完成證據與修訂計畫不符')
        return marker, plan
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'歷史交易日修訂證據無法驗證：{path}') from exc


def assert_session_revision_safe(database_path: Path, decision_date: date) -> None:
    for path in sorted((_root(database_path) / RECEIPT_DIR).glob('*/revision.json')):
        marker, plan = _plan(path, database_path)
        first = date.fromisoformat(plan['source_start_date'])
        if marker['state'] != 'rolled_back' and decision_date >= first:
            raise ValueError('historical session source revision blocks historical PIT; rebuild from explicitly revised sources')


def validate_session_replacement(
    database_path: Path, records: Iterable[Mapping[str, object]], *, replace_all: bool = False,
    replace_dates: bool = False,
) -> None:
    """缺少已補回日期的來源不能整表／整日清除；僅驗證提供的值。"""
    paths = sorted((_root(database_path) / RECEIPT_DIR).glob('*/revision.json'))
    if not paths:
        return
    incoming = {(str(r.get('日期', '')).replace('-', '').replace('/', '')[:8], str(r.get('證券代號', '')).strip()): r for r in records}
    incoming_days = {k[0] for k in incoming}
    for path in paths:
        marker, plan = _plan(path, database_path)
        if marker['state'] == 'rolled_back':
            continue
        if marker['state'] != 'applied':
            raise ValueError('歷史交易日修復進行中，暫停來源重新匯入')
        dates = set(plan['dates'])
        if not replace_all and not dates & incoming_days:
            continue
        expected = {(r['日期'], r['證券代號']): r for r in plan['rows']}
        protected = {k for k in expected if replace_all or (replace_dates and k[0] in incoming_days)}
        if not protected <= set(incoming):
            raise ValueError('匯入來源缺少已補回的歷史股票／交易日，拒絕清除')
        for k in set(expected) & set(incoming):
            row = incoming[k]
            for column in ('成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌價差'):
                if column not in row:
                    if k in protected:
                        raise ValueError(f'替換資料缺少歷史價量欄位：{k}/{column}')
                    continue
                value, wanted = row[column], expected[k].get(column)
                try:
                    actual = None if value is None or str(value) in {'', 'nan', 'NaN', '<NA>', '--'} else Decimal(str(value).replace(',', ''))
                    canonical = None if wanted is None else Decimal(str(wanted))
                except InvalidOperation as exc:
                    raise ValueError('重匯歷史價量格式不符') from exc
                if actual != canonical:
                    raise ValueError(f'重匯會覆蓋已核驗的歷史價量：{k}/{column}')
