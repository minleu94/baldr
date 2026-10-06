"""以新封存官方行情補回全日缺漏；只新增原本不存在的列、不改原始日檔。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_module.historical_session_revision import RECEIPT_DIR
from data_module.market_data_integrity import official_twse_price_table
from data_module.ml_storage_capacity import acquire_heavy_chain_reservation, release_heavy_chain_reservation
from scripts.repair_formal_market_data import atomic, encoded, file_hash, now, quote, readonly
from scripts.repair_historical_price_spike_20260921 import _official_row_values

CONFIRM = 'repair-historical-sessions'
NUMBER = re.compile(r'^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$')
FIELDS = ('日期', '證券代號', '證券名稱', '成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌', '漲跌價差', '最後揭示買價', '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比')


def number(value: object, *, integer: bool = False) -> str | int | None:
    text = re.sub(r'^([+-])\s+', r'\1', str(value).strip())
    if text in {'', '--', '---', '----', '-----', '--- ', 'None', '除權', '除息', '除權息'}:
        return None
    if not NUMBER.fullmatch(text):
        raise ValueError(f'不合法官方數值：{text}')
    parsed = Decimal(text.replace(',', ''))
    if not parsed.is_finite() or (integer and parsed != parsed.to_integral_value()):
        raise ValueError('官方數值不是有效整數')
    return int(parsed) if integer else str(parsed)


def parse_source(body: dict[str, Any], *, venue: str, day: str, allowed_symbols: set[str] | None = None) -> list[dict[str, Any]]:
    if str(body.get('date')) != day or str(body.get('stat')).lower() != 'ok':
        raise ValueError('官方回應狀態／日期不符')
    result = []
    if venue == 'twse':
        table = official_twse_price_table(body, day)
        if table is None:
            raise ValueError('官方上市行情表不存在')
        for raw in table['data']:
            symbol = str(raw[0]).strip()
            if not re.fullmatch(r'\d{4}', symbol) and symbol not in (allowed_symbols or set()):
                continue
            for field, value in zip(table['fields'], raw, strict=True):
                if field not in {'證券代號', '證券名稱', '漲跌(+/-)'}:
                    number(value, integer=field in {'成交股數', '成交筆數', '成交金額', '最後揭示買量', '最後揭示賣量'})
            parsed = _official_row_values(table['fields'], raw)
            symbol = parsed['symbol']
            row = {k: parsed.get(k) for k in FIELDS}
            row.update({'日期': day, '證券代號': symbol, '漲跌': parsed['漲跌(+/-)']})
            result.append(row)
    elif venue == 'tpex':
        tables = body.get('tables')
        if not isinstance(tables, list) or not tables:
            raise ValueError('官方上櫃行情表不存在')
        table = tables[0]
        roc = str(table.get('date')).split('/')
        if len(roc) != 3 or f'{int(roc[0])+1911:04d}{int(roc[1]):02d}{int(roc[2]):02d}' != day:
            raise ValueError('櫃買表內日期不符')
        fields = [str(f).strip() for f in table['fields']]
        aliases = {'成交金額': '成交金額(元)', '開盤價': '開盤', '最高價': '最高', '最低價': '最低', '收盤價': '收盤', '最後揭示買價': '最後買價', '最後揭示賣價': '最後賣價'}
        if not {'代號', '名稱', '成交股數', '成交金額(元)', '成交筆數', '開盤', '最高', '最低', '收盤', '漲跌'} <= set(fields):
            raise ValueError('櫃買原始欄位不完整')
        for values in table['data']:
            if len(values) != len(fields):
                raise ValueError('櫃買欄位長度不符')
            raw = dict(zip(fields, values, strict=True))
            symbol = str(raw['代號']).strip()
            if not re.fullmatch(r'\d{4}', symbol) and symbol not in (allowed_symbols or set()):
                continue
            row = {k: None for k in FIELDS}
            row.update({'日期': day, '證券代號': symbol, '證券名稱': str(raw['名稱']).strip()})
            for column in ('成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '最後揭示買價', '最後揭示賣價'):
                row[column] = number(raw.get(aliases.get(column, column)), integer=column in {'成交股數', '成交筆數', '成交金額'})
            change = number(raw['漲跌'])
            if change is not None:
                n = Decimal(str(change))
                row['漲跌'] = '+' if n > 0 else '-' if n < 0 else None
                row['漲跌價差'] = str(abs(n))
            result.append(row)
    else:
        raise ValueError('未知交易所')
    if not result or len({r['證券代號'] for r in result}) != len(result):
        raise ValueError('官方股票集合為空或重複')
    for row in result:
        prices = [row[c] for c in ('開盤價', '最高價', '最低價', '收盤價')]
        if any(v is not None and Decimal(str(v)) <= 0 for v in prices):
            raise ValueError('官方報價含非正價格')
        if row['成交股數'] is None or row['成交筆數'] is None or row['成交金額'] is None:
            raise ValueError('官方成交統計缺漏')
        if any(Decimal(str(row[k])) < 0 for k in ('成交股數', '成交筆數', '成交金額')):
            raise ValueError('官方成交統計為負值')
        if all(v is not None for v in prices):
            o, h, l, c = (Decimal(str(v)) for v in prices)
            if not Decimal(0) < l <= min(o, c) <= max(o, c) <= h:
                raise ValueError(f'官方 OHLC 不合法：{day}/{row["證券代號"]}')
    return result


def verified_rows(sources: list[dict[str, str]], allowed_symbols: set[str] | None = None) -> list[dict[str, Any]]:
    result, sessions = [], set()
    for source in sources:
        path, receipt_path = Path(source['path']), Path(source['receipt'])
        if file_hash(path) != source['sha256'] or file_hash(receipt_path) != source['receipt_sha256']:
            raise ValueError('官方封存 hash 漂移')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        day, venue = source['day'], source['venue']
        clock = datetime.fromisoformat(receipt['captured_at'])
        if clock.tzinfo is None or clock > datetime.now(timezone.utc) or receipt['sha256'] != source['sha256'] or receipt['historical_pit'] is not False or receipt['date'] != day:
            raise ValueError('官方封存日期／取得時鐘不符')
        url = urlparse(receipt['url'])
        host, endpoint = ('www.twse.com.tw', '/rwd/zh/afterTrading/MI_INDEX') if venue == 'twse' else ('www.tpex.org.tw', '/www/zh-tw/afterTrading/otc')
        query = parse_qs(url.query)
        if url.scheme != 'https' or url.netloc != host or url.path != endpoint or query.get('date', [''])[0].replace('/', '') != day:
            raise ValueError('官方來源 URL 不符')
        if (day, venue) in sessions:
            raise ValueError('來源日期／交易所重複')
        sessions.add((day, venue))
        result.extend(parse_source(json.loads(path.read_text(encoding='utf-8')), venue=venue, day=day, allowed_symbols=allowed_symbols))
    if not sessions or any((day, venue) not in sessions for day, _ in sessions for venue in ('twse', 'tpex')):
        raise ValueError('每個日期必須同時核對上市與上櫃')
    if len({(r['日期'], r['證券代號']) for r in result}) != len(result):
        raise ValueError('跨市場重複股票鍵')
    return sorted(result, key=lambda r: (r['日期'], r['證券代號']))


def build_plan(db: Path, sources: list[dict[str, str]]) -> dict[str, Any]:
    with readonly(db) as c:
        symbols = sorted(str(r[0]) for r in c.execute('SELECT DISTINCT 證券代號 FROM daily_prices'))
        rows = verified_rows(sources, set(symbols))
        dates = sorted({r['日期'] for r in rows})
        columns = [r[1] for r in c.execute('PRAGMA table_info(daily_prices)')]
        if not set(FIELDS) <= set(columns):
            raise ValueError('正式價格欄位不完整')
        for day in dates:
            if c.execute('SELECT count(*) FROM daily_prices WHERE 日期=?', (day,)).fetchone()[0] != 0:
                raise ValueError(f'日期並非整日缺漏：{day}')
    return {'schema_version': 'historical-session-repair.v1', 'database_path': str(db.resolve()),
            'sources': sources, 'dates': dates, 'source_start_date': datetime.strptime(dates[0], '%Y%m%d').date().isoformat(),
            'source_end_date': datetime.strptime(dates[-1], '%Y%m%d').date().isoformat(), 'rows': rows, 'columns': columns,
            'existing_universe': symbols, 'scope': 'existing daily_prices universe plus four-digit securities; no new product universe'}


def _readback(c: sqlite3.Connection, plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for day in plan['dates']:
        for values in c.execute(f'SELECT {",".join(quote(k) for k in FIELDS)} FROM daily_prices WHERE 日期=? ORDER BY 證券代號', (day,)):
            rows.append(dict(zip(FIELDS, values, strict=True)))
    return rows


def _same(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    text = {'日期', '證券代號', '證券名稱', '漲跌'}
    for left, right in zip(a, b, strict=True):
        for column in FIELDS:
            x, y = left[column], right[column]
            if column in text or x is None or y is None:
                if x != y:
                    return False
            elif Decimal(str(x)) != Decimal(str(y)):
                return False
    return True


def _state_hash(c: sqlite3.Connection, plan: dict[str, Any]) -> str:
    """連同未改動欄位一起比對，拒絕刪除修復後新增的資訊。"""
    import hashlib
    columns = [r[1] for r in c.execute('PRAGMA table_info(daily_prices)')]
    if columns != plan['columns']:
        raise ValueError('資料庫欄位已漂移')
    rows = []
    for day in plan['dates']:
        rows.extend(c.execute(f'SELECT * FROM daily_prices WHERE 日期=? ORDER BY 證券代號', (day,)).fetchall())
    return hashlib.sha256(encoded(rows)).hexdigest()


def _verify_archive(directory: Path, plan: dict[str, Any], expected_hash: str) -> None:
    if file_hash(directory / 'plan.json') != expected_hash:
        raise ValueError('封存計畫與要求回復的計畫不符')
    backup = json.loads((directory / 'backup.json').read_text(encoding='utf-8'))
    if file_hash(directory / 'sqlite_before.db') != backup['sha256']:
        raise ValueError('修復前備份 hash 不符')
    if not _same(verified_rows(plan['sources'], set(plan['existing_universe'])), plan['rows']):
        raise ValueError('回復計畫來源不符')
    with readonly(directory / 'sqlite_before.db') as saved:
        if _readback(saved, plan):
            raise ValueError('修復前備份並非空白目標日期')


def _finish(directory: Path, marker: dict[str, Any], plan: dict[str, Any], state: str) -> dict[str, Any]:
    result = {'schema_version': 'historical-session-repair.v1', 'state': state, 'completed_at': now(), 'rows': len(plan['rows']), 'dates': plan['dates'], 'plan_sha256': marker['plan_sha256']}
    receipt = directory / ('rollback.json' if state == 'rolled_back' else 'receipt.json')
    atomic(receipt, encoded(result))
    atomic(directory / 'revision.json', encoded({**marker, 'state': state, 'receipt_sha256': file_hash(receipt)}))
    return result


def apply(plan_path: Path, expected_hash: str, directory: Path, *, rollback: bool = False, resume: bool = False) -> dict[str, Any]:
    if file_hash(plan_path) != expected_hash:
        raise ValueError('計畫 hash 不符')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    db = Path(plan['database_path'])
    root = db.parent.parent if db.parent.name.lower() == 'sqlite' else db.parent
    if directory.resolve().parent != (root / RECEIPT_DIR).resolve():
        raise ValueError('receipt 位置不屬於正式資料根目錄')
    reservation = acquire_heavy_chain_reservation(root / 'output/release_v4/.ml_heavy_chain.lock')
    if reservation is None:
        raise ValueError('維護鎖忙碌')
    try:
        if rollback or resume:
            _verify_archive(directory, plan, expected_hash)
            marker = json.loads((directory / 'revision.json').read_text(encoding='utf-8'))
            if marker['database_path'] != str(db.resolve()) or marker['plan_sha256'] != expected_hash:
                raise ValueError('修訂標記與計畫不符')
            if (resume and marker['state'] != 'pending') or (rollback and marker['state'] != 'applied'):
                raise ValueError('只允許恢復 pending 或回復 applied；完成回復後不可再次刪除')
            if resume:
                with readonly(db) as c:
                    current = _readback(c, plan)
                    if not current:
                        state = 'rolled_back'
                    elif _same(current, plan['rows']) and _state_hash(c, plan) == json.loads((directory / 'after_state.json').read_text(encoding='utf-8'))['sha256']:
                        state = 'applied'
                    else:
                        raise ValueError('中斷後資料已漂移，拒絕自動恢復')
                return _finish(directory, marker, plan, state)
        else:
            if directory.exists() or build_plan(db, plan['sources']) != plan:
                raise ValueError('計畫漂移或 receipt 已存在')
            directory.mkdir(parents=True)
            atomic(directory / 'plan.json', encoded(plan))
            with readonly(db) as src, sqlite3.connect(directory / 'sqlite_before.db') as dst:
                src.backup(dst, pages=8192)
            with readonly(directory / 'sqlite_before.db') as saved:
                if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('備份驗證失敗')
            atomic(directory / 'backup.json', encoded({'sha256': file_hash(directory / 'sqlite_before.db')}))
        marker = {'schema_version': 'historical-session-revision.v1', 'state': 'pending', 'database_path': str(db.resolve()),
                  'plan_sha256': file_hash(directory / 'plan.json'), 'observed_at': now(), 'historical_pit': False}
        atomic(directory / 'revision.json', encoded(marker))
        with sqlite3.connect(db, timeout=30) as c:
            c.execute('BEGIN IMMEDIATE')
            current = _readback(c, plan)
            if rollback:
                if not _same(current, plan['rows']) or _state_hash(c, plan) != json.loads((directory / 'after_state.json').read_text(encoding='utf-8'))['sha256']:
                    raise ValueError('回復前資料已漂移')
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='technical_indicators'").fetchone():
                    with readonly(directory / 'sqlite_before.db') as saved:
                        for day in plan['dates']:
                            before = saved.execute('SELECT * FROM technical_indicators WHERE 日期=? ORDER BY 證券代號', (day,)).fetchall()
                            after = c.execute('SELECT * FROM technical_indicators WHERE 日期=? ORDER BY 證券代號', (day,)).fetchall()
                            if before != after:
                                raise ValueError('請先回復相依技術指標，再回復來源交易日')
                for day in plan['dates']:
                    c.execute('DELETE FROM daily_prices WHERE 日期=?', (day,))
            else:
                if current:
                    raise ValueError('套用前已有新來源資料')
                columns = [*FIELDS, *[k for k in ('漲跌(+/-)', '涨跌') if k in plan['columns']]]
                c.executemany(f'INSERT INTO daily_prices ({",".join(quote(k) for k in columns)}) VALUES ({",".join("?" for _ in columns)})',
                              [[row.get(k) if k not in {'漲跌(+/-)', '涨跌'} else row['漲跌'] for k in columns] for row in plan['rows']])
                if not _same(_readback(c, plan), plan['rows']):
                    raise ValueError('補入資料讀回不符')
                atomic(directory / 'after_state.json', encoded({'sha256': _state_hash(c, plan)}))
        state = 'rolled_back' if rollback else 'applied'
        return _finish(directory, marker, plan, state)
    finally:
        release_heavy_chain_reservation(reservation)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', type=Path)
    p.add_argument('--sources', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--expected-plan-hash')
    p.add_argument('--receipt-dir', type=Path)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--rollback', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--confirm')
    a = p.parse_args()
    if a.apply or a.rollback or a.resume:
        if a.confirm != CONFIRM or not a.plan or not a.expected_plan_hash or not a.receipt_dir or sum((a.apply, a.rollback, a.resume)) != 1:
            p.error('套用／回復／恢復需 plan、hash、receipt-dir 與 confirm；三模式互斥')
        result = apply(a.plan, a.expected_plan_hash, a.receipt_dir, rollback=a.rollback, resume=a.resume)
    else:
        if not a.db or not a.sources or not a.output or a.output.exists():
            p.error('dry-run 需要 db、sources 及新 output')
        plan = build_plan(a.db, json.loads(a.sources.read_text(encoding='utf-8')))
        atomic(a.output, encoded(plan))
        result = {'plan': str(a.output), 'sha256': file_hash(a.output), 'rows': len(plan['rows']), 'dates': plan['dates']}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
