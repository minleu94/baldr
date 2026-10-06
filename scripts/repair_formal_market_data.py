"""核驗官方來源後受控修訂正式 TAIEX；預設 dry-run，保留原始檔及逐列回復資料。"""

from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_module.ml_restatement_official_market import load_official_market_capture
from data_module.ml_storage_capacity import acquire_heavy_chain_reservation, release_heavy_chain_reservation
from data_module.formal_market_revision import RECEIPT_DIR


SCHEMA = 'formal-market-repair.v1'
CONFIRM = 'repair-formal-market-data'
CSV_FIELDS = ('開盤價', '最高價', '最低價', '收盤價', '成交量')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('需要 JSON 物件')
    return payload


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve(strict=True).as_uri() + '?mode=ro', uri=True, timeout=30)
    connection.execute('PRAGMA query_only=ON')
    return connection


def key(value: object) -> str:
    text = str(value).replace('-', '').replace('/', '')
    return datetime.strptime(text, '%Y%m%d').strftime('%Y%m%d')


def quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    columns = [row[1] for row in connection.execute('PRAGMA table_info(market_indices)')]
    required = {'日期', '指數名稱', '收盤指數', *CSV_FIELDS}
    if not required <= set(columns):
        raise ValueError('正式大盤表欄位不完整；拒絕自動改 schema')
    rows = []
    for row in connection.execute('SELECT * FROM market_indices ORDER BY 日期, 指數名稱'):
        # SQLite REAL 僅為既有儲存邊界；運算與官方對比均用 Decimal。
        rows.append({column: (str(value) if isinstance(value, float) else value) for column, value in zip(columns, row, strict=True)})
    identity = [(row['日期'], row['指數名稱']) for row in rows]
    if len(set(identity)) != len(identity):
        raise ValueError('正式大盤表有重複 key，拒絕模糊更新')
    objects = list(connection.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name='market_indices' ORDER BY type,name"))
    return {'columns': columns, 'objects_hash': digest(encoded(objects)), 'rows': rows}


def official(sources: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    coverage: dict[str, date] = {}
    for item in sources:
        capture = load_official_market_capture(
            Path(item['path']), expected_file_sha256='sha256:' + item['sha256'].removeprefix('sha256:'),
            as_of=datetime.now(timezone.utc),
        )
        for month in read_json(Path(item['path']))['months']:
            coverage[month] = max(coverage.get(month, date.min), capture.cutoff_date)
        for day, raw in capture.rows.items():
            row = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}
            k = day.strftime('%Y%m%d')
            if k in combined and row != combined[k]:
                raise ValueError(f'兩份官方封存對同日有差異：{k}')
            combined[k] = row
    if not combined:
        raise ValueError('官方來源沒有可用列')
    months = sorted(coverage)
    numbers = [int(m[:4]) * 12 + int(m[4:]) for m in months]
    if numbers != list(range(numbers[0], numbers[-1] + 1)):
        raise ValueError('官方來源月份不連續，拒絕跨缺口刪除資料')
    for month in months[:-1]:
        year, number = int(month[:4]), int(month[4:])
        if coverage[month] < date(year, number, calendar.monthrange(year, number)[1]):
            raise ValueError('中間月份未涵蓋月底，拒絕跨缺口刪除資料')
    return combined


def derive(before: dict[str, Any], csv_body: bytes, source: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    first, last = min(source), max(source)
    old = {key(row['日期']): row for row in before['rows'] if row['指數名稱'] == 'TAIEX' and first <= key(row['日期']) <= last}
    result = [row for row in before['rows'] if row['指數名稱'] != 'TAIEX' or not first <= key(row['日期']) <= last]
    for day, row in sorted(source.items()):
        new = dict(old.get(day, {column: None for column in before['columns']}))
        new.update({column: row[column] for column in before['columns'] if column in row})
        new['日期'], new['指數名稱'] = day, 'TAIEX'
        change = Decimal(row['漲跌點數'])
        if '漲跌' in new:
            new['漲跌'] = '+' if change > 0 else '-' if change < 0 else None
        # 轉為既有 REAL 欄位的規格化表示，避免 100 與 100.0 誤報漂移。
        for column in (*CSV_FIELDS, '收盤指數', '漲跌點數'):
            if column in new and new[column] is not None:
                new[column] = str(Decimal(str(new[column])).normalize())
        result.append(new)
    after = {**before, 'rows': sorted(result, key=lambda r: (r['日期'], r['指數名稱']))}
    reader = csv.DictReader(io.StringIO(csv_body.decode('utf-8-sig')))
    fields = reader.fieldnames
    if fields is None or not {'日期', *CSV_FIELDS} <= set(fields):
        raise ValueError('大盤 CSV 欄位不完整')
    csv_rows = list(reader)
    if len({key(row['日期']) for row in csv_rows}) != len(csv_rows):
        raise ValueError('大盤 CSV 日期重複')
    if '指數名稱' in fields and any(row['指數名稱'] not in ('', 'TAIEX') for row in csv_rows):
        raise ValueError('CSV 不是單一 TAIEX series')
    by_date = {key(row['日期']): row for row in csv_rows}
    keep = [row for row in csv_rows if not first <= key(row['日期']) <= last]
    for day, row in sorted(source.items()):
        new_csv = dict(by_date.get(day, {column: '' for column in fields}))
        for column in fields:
            if column in row:
                new_csv[column] = '' if row[column] is None else str(row[column])
        new_csv['日期'] = datetime.strptime(day, '%Y%m%d').date().isoformat()
        keep.append(new_csv)
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(sorted(keep, key=lambda r: key(r['日期'])))
    return after, output.getvalue().encode('utf-8-sig')


def normalized(state: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in state['rows']:
        new = dict(row)
        for column in (*CSV_FIELDS, '收盤指數', '漲跌點數', '漲跌百分比'):
            if new.get(column) is not None:
                new[column] = str(Decimal(str(new[column])).normalize())
        rows.append(new)
    return {**state, 'rows': rows}


def build_plan(db: Path, csv_path: Path, sources: list[dict[str, str]]) -> dict[str, Any]:
    source = official(sources)
    with readonly(db) as connection:
        before = normalized(snapshot(connection))
    csv_before = csv_path.read_bytes()
    after, csv_after = derive(before, csv_before, source)
    first, last = min(source), max(source)
    old_keys = {key(r['日期']) for r in before['rows'] if r['指數名稱'] == 'TAIEX' and first <= key(r['日期']) <= last}
    return {
        'schema_version': SCHEMA, 'created_at': now(), 'database_path': str(db.resolve()),
        'csv_path': str(csv_path.resolve()), 'sources': sources,
        'source_start_date': datetime.strptime(first, '%Y%m%d').date().isoformat(),
        'source_end_date': datetime.strptime(last, '%Y%m%d').date().isoformat(),
        'before': before, 'after': normalized(after),
        'csv_before_sha256': digest(csv_before), 'csv_after_sha256': digest(csv_after),
        'csv_after_text': csv_after.decode('utf-8-sig'),
        'summary': {'official_rows': len(source), 'existing_target_rows': len(old_keys),
                    'insert_dates': sorted(set(source) - old_keys), 'remove_dates': sorted(old_keys - set(source)),
                    'before_rows': len(before['rows']), 'after_rows': len(after['rows'])},
    }


def write_target(connection: sqlite3.Connection, plan: dict[str, Any], desired: dict[str, Any]) -> None:
    start, end = key(plan['source_start_date']), key(plan['source_end_date'])
    connection.execute('DELETE FROM market_indices WHERE 指數名稱=? AND 日期>=? AND 日期<=?', ('TAIEX', start, end))
    columns = desired['columns']
    rows = [r for r in desired['rows'] if r['指數名稱'] == 'TAIEX' and start <= key(r['日期']) <= end]
    connection.executemany(
        f"INSERT INTO market_indices ({','.join(quote(c) for c in columns)}) VALUES ({','.join('?' for _ in columns)})",
        [[row[column] for column in columns] for row in rows],
    )
    if normalized(snapshot(connection)) != desired:
        raise ValueError('正式交易內讀回不符；將回滾')


def marker(plan: dict[str, Any], directory: Path, state: str, **extra: object) -> None:
    atomic(directory / 'revision.json', encoded({
        'schema_version': 'formal-market-revision.v1', 'state': state,
        'database_path': plan['database_path'], 'source_start_date': plan['source_start_date'],
        'source_end_date': plan['source_end_date'], 'observed_at': now(),
        'historical_pit': False, **extra,
    }))


def _locks(db: Path, csv_path: Path) -> tuple[Any, Any]:
    root = db.parent.parent if db.parent.name.lower() == 'sqlite' else db.parent
    first = acquire_heavy_chain_reservation(root / 'output/release_v4/.ml_heavy_chain.lock')
    if first is None:
        raise ValueError('維護鎖正在使用')
    try:
        second = acquire_heavy_chain_reservation(csv_path.with_suffix('.csv.lock'))
        if second is None:
            raise ValueError('市場 CSV 正在更新')
        return first, second
    except BaseException:
        release_heavy_chain_reservation(first)
        raise


def apply(plan_path: Path, expected_hash: str, directory: Path, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM or file_hash(plan_path) != expected_hash.removeprefix('sha256:'):
        raise ValueError('缺少確認或 dry-run hash 不符')
    plan = read_json(plan_path)
    if plan.get('schema_version') != SCHEMA:
        raise ValueError('不支援修復計畫')
    db, csv_path = Path(plan['database_path']), Path(plan['csv_path'])
    root = db.parent.parent if db.parent.name.lower() == 'sqlite' else db.parent
    expected_parent = (root / RECEIPT_DIR).resolve()
    if directory.resolve().parent != expected_parent or directory.exists():
        raise ValueError('receipt 必須位於資料根目錄指定的新修復目錄')
    held = _locks(db, csv_path)
    try:
        # 重建 dry-run，拒絕任意修改 after 值或修訂前漂移。
        fresh = build_plan(db, csv_path, plan['sources'])
        if {k: v for k, v in fresh.items() if k != 'created_at'} != {k: v for k, v in plan.items() if k != 'created_at'}:
            raise ValueError('來源／資料已漂移或計畫被改寫')
        if shutil.disk_usage(root).free < db.stat().st_size + 128 * 1024 * 1024:
            raise ValueError('備份容量不足')
        directory.mkdir(parents=True)
        atomic(directory / 'plan.json', encoded(plan))
        atomic(directory / 'market_before.csv', csv_path.read_bytes())
        csv_after = plan['csv_after_text'].encode('utf-8-sig')
        if digest(csv_after) != plan['csv_after_sha256']:
            raise ValueError('CSV 計畫 hash 不符')
        atomic(directory / 'market_after.csv', csv_after)
        backup = directory / 'sqlite_before.db'
        with readonly(db) as source, sqlite3.connect(backup) as destination:
            source.backup(destination, pages=8192)
        with readonly(backup) as saved:
            if saved.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or normalized(snapshot(saved)) != plan['before']:
                raise ValueError('備份驗證失敗')
        journal = {'schema_version': SCHEMA, 'plan_sha256': file_hash(directory / 'plan.json'),
                   'backup_sha256': file_hash(backup), 'started_at': now(), 'state': 'prepared'}
        atomic(directory / 'journal.json', encoded(journal))
        marker(plan, directory, 'pending')
        connection = sqlite3.connect(db, timeout=30)
        try:
            connection.execute('BEGIN IMMEDIATE')
            if normalized(snapshot(connection)) != plan['before'] or file_hash(csv_path) != plan['csv_before_sha256']:
                raise ValueError('正式套用前有其他寫入')
            write_target(connection, plan, plan['after'])
            atomic(csv_path, csv_after)
            if file_hash(csv_path) != plan['csv_after_sha256']:
                raise ValueError('CSV 套用讀回不符')
            connection.commit()
        except BaseException:
            connection.rollback()
            # 可捕捉例外在鎖釋放前恢復一致；真正程序終止由 --resume 判斷。
            current = normalized(snapshot(connection))
            current_csv = file_hash(csv_path)
            if current != plan['before'] or current_csv not in (plan['csv_before_sha256'], plan['csv_after_sha256']):
                raise ValueError('套用失敗且來源漂移；保留 pending 待維護恢復')
            # 不呼叫可被測試注入的發佈 hook，回復已驗證的 before bytes。
            atomic(csv_path, (directory / 'market_before.csv').read_bytes())
            raise
        finally:
            connection.close()
        receipt = {**journal, 'state': 'applied', 'completed_at': now(), 'summary': plan['summary'],
                   'source_available_at_policy': 'actual_capture_only_not_historical_pit'}
        atomic(directory / 'receipt.json', encoded(receipt))
        marker(plan, directory, 'applied', receipt_sha256=file_hash(directory / 'receipt.json'))
        return receipt
    finally:
        for lock in reversed(held):
            release_heavy_chain_reservation(lock)


def recover(directory: Path, *, rollback: bool, confirm: str) -> dict[str, Any]:
    if confirm != CONFIRM:
        raise ValueError('缺少回復確認')
    journal = read_json(directory / 'journal.json')
    if file_hash(directory / 'plan.json') != journal['plan_sha256'] or file_hash(directory / 'sqlite_before.db') != journal['backup_sha256']:
        raise ValueError('回復計畫或備份 hash 不符')
    plan = read_json(directory / 'plan.json')
    db, csv_path = Path(plan['database_path']), Path(plan['csv_path'])
    root = db.parent.parent if db.parent.name.lower() == 'sqlite' else db.parent
    if directory.resolve().parent != (root / RECEIPT_DIR).resolve():
        raise ValueError('回復 receipt 不屬於此資料根目錄')
    before_csv, after_csv = directory / 'market_before.csv', directory / 'market_after.csv'
    if file_hash(before_csv) != plan['csv_before_sha256'] or file_hash(after_csv) != plan['csv_after_sha256']:
        raise ValueError('回復 CSV hash 不符')
    held = _locks(db, csv_path)
    try:
        current_marker = read_json(directory / 'revision.json')
        if (rollback and current_marker['state'] != 'applied') or (not rollback and current_marker['state'] != 'pending'):
            raise ValueError('只允許回復 applied 或恢復 pending，拒絕重複回復已結束修訂')
        with sqlite3.connect(db, timeout=30) as connection:
            connection.execute('BEGIN IMMEDIATE')
            current = normalized(snapshot(connection))
            current_csv = file_hash(csv_path)
            if current not in (plan['before'], plan['after']) or current_csv not in (plan['csv_before_sha256'], plan['csv_after_sha256']):
                raise ValueError('修復後有資料漂移，拒絕整批回復')
            committed = current == plan['after']
            if rollback or not committed:
                write_target(connection, plan, plan['before'])
                atomic(csv_path, before_csv.read_bytes())
                state = 'rolled_back'
            else:
                atomic(csv_path, after_csv.read_bytes())
                state = 'applied'
        result = {**journal, 'state': state, 'recovered_at': now(), 'rollback': rollback}
        output = directory / ('rollback.json' if state == 'rolled_back' else 'receipt.json')
        atomic(output, encoded(result))
        marker(plan, directory, state, **{('rollback_sha256' if state == 'rolled_back' else 'receipt_sha256'): file_hash(output)})
        return result
    finally:
        for lock in reversed(held):
            release_heavy_chain_reservation(lock)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--source', type=Path, action='append', default=[])
    parser.add_argument('--source-sha256', action='append', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-hash')
    parser.add_argument('--receipt-dir', type=Path)
    parser.add_argument('--confirm', default='')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--resume', type=Path)
    modes.add_argument('--rollback', type=Path)
    args = parser.parse_args(argv)
    if args.resume or args.rollback:
        result = recover(args.resume or args.rollback, rollback=bool(args.rollback), confirm=args.confirm)
    elif args.apply:
        if args.plan is None or args.expected_plan_hash is None or args.receipt_dir is None:
            parser.error('--apply 需要 --plan、--expected-plan-hash、--receipt-dir')
        result = apply(args.plan, args.expected_plan_hash, args.receipt_dir, args.confirm)
    else:
        if not args.source or len(args.source) != len(args.source_sha256) or not args.db or not args.csv or not args.output:
            parser.error('dry-run 需要 --db、--csv、成對 --source／--source-sha256、--output')
        result = build_plan(args.db, args.csv, [{'path': str(p.resolve()), 'sha256': h.removeprefix('sha256:')} for p, h in zip(args.source, args.source_sha256, strict=True)])
        if args.output.exists():
            raise ValueError('拒絕覆寫既有 dry-run')
        atomic(args.output, encoded(result))
        result = {'plan': str(args.output), 'plan_sha256': file_hash(args.output), 'summary': result['summary']}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
