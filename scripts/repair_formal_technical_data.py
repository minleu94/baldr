"""正式技術衍生資料的隔離重算、有限記憶體發布與中斷回復。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_module.technical_analysis.technical_indicators import CAUSAL_INDICATOR_COLUMNS
from data_module.ml_storage_capacity import acquire_heavy_chain_reservation, release_heavy_chain_reservation
from scripts.repair_formal_market_data import atomic, encoded, file_hash, now, quote, readonly

CONFIRM = 'repair-formal-technical-data'
RECEIPT_DIR = Path('output/scheduled/formal_technical_repair_receipts')
KEYS = ('日期', '證券代號')


def table_hash(c: sqlite3.Connection, table: str) -> str:
    columns = [r[1] for r in c.execute(f'PRAGMA table_info({quote(table)})')]
    h = hashlib.sha256(encoded(columns))
    cursor = c.execute(f'SELECT * FROM {quote(table)} ORDER BY 證券代號, 日期')
    while rows := cursor.fetchmany(5000):
        h.update(encoded(rows))
    return h.hexdigest()


def _location(root: Path, directory: Path) -> None:
    if directory.resolve().parent != (root.resolve() / RECEIPT_DIR).resolve():
        raise ValueError('修復紀錄不在資料根目錄指定位置')


def prepare(root: Path, directory: Path) -> dict[str, Any]:
    _location(root, directory)
    if directory.exists():
        raise ValueError('拒絕覆寫既有修復紀錄')
    db = root / 'sqlite/twstock.db'
    if shutil.disk_usage(root).free < db.stat().st_size * 4:
        raise ValueError('隔離重算與備份容量不足')
    directory.mkdir(parents=True)
    source = directory / 'source.sqlite'
    with readonly(db) as src, sqlite3.connect(source) as dst:
        src.backup(dst, pages=8192)
    with readonly(source) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('重算來源備份驗證失敗')
        evidence = {'schema_version':'formal-technical-repair.v1', 'root':str(root.resolve()),
                    'source_db':str(source.resolve()), 'source_sha256':file_hash(source),
                    'daily_before_hash':table_hash(c, 'daily_prices'),
                    'technical_before_hash':table_hash(c, 'technical_indicators'), 'prepared_at':now()}
    atomic(directory / 'source.json', encoded(evidence))
    print(json.dumps({'stage':'source_prepared','source_db':str(source)}, ensure_ascii=False), flush=True)
    return evidence


def stage(directory: Path) -> dict[str, Any]:
    from scripts.technical_cache_rebuild_stage import stage_rebuild
    evidence = json.loads((directory / 'source.json').read_text(encoding='utf-8'))
    source = Path(evidence['source_db'])
    if file_hash(source) != evidence['source_sha256']:
        raise ValueError('重算來源備份 hash 漂移')
    return stage_rebuild(source, Path(evidence['root']), directory / 'stage')


def copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as dst, source.open('rb') as src:
            shutil.copyfileobj(src, dst, length=1024*1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _file_state(path: Path) -> str | None:
    return file_hash(path) if path.exists() else None


def _load(directory: Path, expected_hash: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = json.loads((directory / 'source.json').read_text(encoding='utf-8'))
    root = Path(evidence['root'])
    _location(root, directory)
    manifest_path = directory / 'stage/manifest.json'
    if expected_hash and file_hash(manifest_path) != expected_hash:
        raise ValueError('staging manifest hash 不符')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    from data_module.excluded_daily_price_revision import load_exclusion_evidence
    exclusions = load_exclusion_evidence(root/'sqlite/twstock.db')
    from scripts.technical_cache_rebuild_stage import exclusion_identities
    if manifest.get('exclusion_evidence_identities', []) != exclusion_identities(exclusions):
        raise ValueError('技指 staging 綁定的排除證據身分已變更')
    excluded_keys = {(str(day),str(symbol)) for item in exclusions for day,symbol in item['keys']}
    closed_dates = {str(day) for item in exclusions for day in item['closed_dates']}
    if set(map(tuple, manifest.get('excluded_source_keys', []))) != excluded_keys or set(manifest.get('excluded_closed_dates', [])) != closed_dates:
        raise ValueError('技指 staging 與目前核驗的錯日排除範圍不同')
    if Path(manifest['source_db']).resolve() != Path(evidence['source_db']).resolve() or manifest['source_sha256'] != evidence['source_sha256']:
        raise ValueError('重算結果來源不符')
    for name, checksum in (('source_db','source_sha256'),('computed_db','computed_sha256')):
        path = Path(manifest[name]).resolve()
        if not path.is_relative_to(directory.resolve()) or file_hash(path) != manifest[checksum]:
            raise ValueError('重算資料／來源 hash 不符')
    targets = set()
    for item in manifest['files']:
        target, staged = Path(item['target_path']).resolve(), Path(item['staged_path']).resolve()
        valid_target = target.parent == (root/'technical_analysis').resolve() and target.name.endswith('_indicators.csv') or target == (root/'meta_data/all_stocks_data.csv').resolve()
        if not valid_target or not staged.is_relative_to((directory/'stage').resolve()) or target in targets:
            raise ValueError('不合法或重複的衍生檔目標')
        targets.add(target)
        if file_hash(staged) != item['after_sha256']:
            raise ValueError('staging CSV hash 不符')
    return evidence, manifest


def _publish_files(directory: Path, journal: dict[str, Any], *, after: bool) -> None:
    for item in journal['files']:
        target = Path(item['target_path'])
        current = _file_state(target)
        if current not in (item['before_sha256'], item['after_sha256']):
            raise ValueError(f'衍生檔發生其他寫入，拒絕覆蓋：{target}')
        desired = item['after_sha256'] if after else item['before_sha256']
        if current == desired:
            continue
        if desired is None:
            # 僅限本輪建立、已核對 after hash 的衍生 CSV，路徑已由 _load 核驗。
            target.unlink()
        else:
            source = Path(item['staged_path']) if after else directory / item['backup']
            if file_hash(source) != desired:
                raise ValueError('衍生檔回復來源 hash 不符')
            copy_atomic(source, target)


def _finish(directory: Path, journal: dict[str, Any], state: str) -> dict[str, Any]:
    result = {**journal, 'state':state, 'completed_at':now()}
    atomic(directory / ('receipt.json' if state=='applied' else 'rollback.json'), encoded(result))
    atomic(directory / 'journal.json', encoded(result))
    return {'state':state, 'rows':journal['rows'], 'files':len(journal['files']), 'directory':str(directory)}


def apply(directory: Path, expected_hash: str) -> dict[str, Any]:
    evidence, manifest = _load(directory, expected_hash)
    if (directory/'journal.json').exists():
        raise ValueError('已有發布紀錄，請使用 resume／rollback')
    root = Path(evidence['root'])
    lock = acquire_heavy_chain_reservation(root/'output/release_v4/.ml_heavy_chain.lock')
    if lock is None:
        raise ValueError('維護鎖忙碌')
    try:
        files = []
        for i,item in enumerate(manifest['files']):
            if _file_state(Path(item['target_path'])) != item['before_sha256']:
                raise ValueError('CSV 在 staging 後已更新，拒絕覆蓋')
            backup = f'csv_before/{i:05d}.csv'
            if item['before_sha256'] is not None:
                copy_atomic(Path(item['target_path']), directory/backup)
                if file_hash(directory/backup) != item['before_sha256']:
                    raise ValueError('CSV 備份 hash 不符')
            files.append({**item,'backup':backup})
        journal = {**evidence,'state':'pending','manifest_sha256':expected_hash,'rows':manifest['rows'],'files':files}
        atomic(directory/'journal.json', encoded(journal))
        with sqlite3.connect(root/'sqlite/twstock.db', timeout=30) as c:
            c.execute('BEGIN IMMEDIATE')
            if table_hash(c,'daily_prices') != evidence['daily_before_hash'] or table_hash(c,'technical_indicators') != evidence['technical_before_hash']:
                raise ValueError('正式價量／技指在 staging 後已更新，拒絕覆蓋')
            columns = [*KEYS, *CAUSAL_INDICATOR_COLUMNS]
            existing_columns = [r[1] for r in c.execute('PRAGMA table_info(technical_indicators)')]
            if not set(columns) <= set(existing_columns):
                raise ValueError('技術指標 schema 不符，修復不進行 schema 變更')
            names = ','.join(quote(k) for k in columns)
            updates = ','.join(f'{quote(k)}=excluded.{quote(k)}' for k in CAUSAL_INDICATOR_COLUMNS)
            sql = f'INSERT INTO technical_indicators ({names}) VALUES ({",".join("?" for _ in columns)}) ON CONFLICT(證券代號,日期) DO UPDATE SET {updates}'
            with readonly(Path(manifest['computed_db'])) as calculated:
                cursor = calculated.execute(f'SELECT {names} FROM {quote(manifest["computed_table"])} ORDER BY 證券代號,日期')
                count = 0
                while rows := cursor.fetchmany(10000):
                    c.executemany(sql, rows)
                    count += len(rows)
                    if count % 500000 == 0:
                        print(json.dumps({'stage':'database_publication','rows':count}), flush=True)
                if count != manifest['rows']:
                    raise ValueError('重算筆數不符')
            journal['technical_after_hash'] = table_hash(c,'technical_indicators')
            atomic(directory/'journal.json', encoded(journal))
            _publish_files(directory,journal,after=True)
        return _finish(directory,journal,'applied')
    except BaseException:
        # DB context 已回滾；若檔案已發布，於維護鎖內恢復成 before。
        if 'journal' in locals():
            with readonly(root/'sqlite/twstock.db') as c:
                if table_hash(c,'technical_indicators') == evidence['technical_before_hash']:
                    _publish_files(directory,journal,after=False)
        raise
    finally:
        release_heavy_chain_reservation(lock)


def recover(directory: Path, *, rollback: bool) -> dict[str, Any]:
    journal = json.loads((directory/'journal.json').read_text(encoding='utf-8'))
    evidence,manifest = _load(directory,journal['manifest_sha256'])
    if len(journal['files']) != len(manifest['files']):
        raise ValueError('發布紀錄檔案集合不符')
    for i,(entry,planned) in enumerate(zip(journal['files'],manifest['files'],strict=True)):
        if entry != {**planned,'backup':f'csv_before/{i:05d}.csv'}:
            raise ValueError('發布紀錄檔案身分不符')
        if entry['before_sha256'] is not None and file_hash(directory/entry['backup']) != entry['before_sha256']:
            raise ValueError('回復 CSV 備份 hash 不符')
    for field in ('source_db','source_sha256','daily_before_hash','technical_before_hash','root'):
        if journal[field] != evidence[field]:
            raise ValueError('發布紀錄來源不符')
    if (rollback and journal['state'] != 'applied') or (not rollback and journal['state'] != 'pending'):
        raise ValueError('只允許回復 applied 或恢復 pending')
    root = Path(evidence['root'])
    lock = acquire_heavy_chain_reservation(root/'output/release_v4/.ml_heavy_chain.lock')
    if lock is None: raise ValueError('維護鎖忙碌')
    try:
        # 回復途中被中斷仍可由 resume 判定 SQLite 最後提交狀態。
        journal = {**journal,'state':'pending'}
        atomic(directory/'journal.json',encoded(journal))
        with sqlite3.connect(root/'sqlite/twstock.db',timeout=30) as c:
            c.execute('BEGIN IMMEDIATE')
            if table_hash(c,'daily_prices') != evidence['daily_before_hash']:
                raise ValueError('正式日價在重算後已更新，拒絕發布／回復舊來源技指')
            current = table_hash(c,'technical_indicators')
            if current not in (journal['technical_before_hash'],journal.get('technical_after_hash')):
                raise ValueError('發布後技指資料已漂移，拒絕回復')
            after = not rollback and current == journal.get('technical_after_hash')
            if not after and current != journal['technical_before_hash']:
                with readonly(Path(evidence['source_db'])) as saved:
                    columns = [r[1] for r in saved.execute('PRAGMA table_info(technical_indicators)')]
                    c.execute('DELETE FROM technical_indicators')
                    cursor = saved.execute('SELECT * FROM technical_indicators')
                    sql = f'INSERT INTO technical_indicators ({",".join(quote(k) for k in columns)}) VALUES ({",".join("?" for _ in columns)})'
                    while rows := cursor.fetchmany(10000): c.executemany(sql,rows)
                if table_hash(c,'technical_indicators') != journal['technical_before_hash']:
                    raise ValueError('技指回復讀回不符')
            _publish_files(directory,journal,after=after)
        return _finish(directory,journal,'applied' if after else 'rolled_back')
    finally:
        release_heavy_chain_reservation(lock)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--receipt-dir',type=Path,required=True)
    parser.add_argument('--expected-manifest-hash')
    parser.add_argument('--confirm')
    modes=parser.add_mutually_exclusive_group(required=True)
    for mode in ('prepare','stage','apply','resume','rollback'): modes.add_argument('--'+mode,action='store_true')
    a=parser.parse_args()
    if a.prepare:
        if not a.root: parser.error('prepare 需要 root')
        result=prepare(a.root,a.receipt_dir)
    elif a.stage: result=stage(a.receipt_dir)
    else:
        if a.confirm != CONFIRM: parser.error('正式發布／回復需要 confirm')
        if a.apply:
            if not a.expected_manifest_hash: parser.error('apply 需要 manifest hash')
            result=apply(a.receipt_dir,a.expected_manifest_hash)
        else: result=recover(a.receipt_dir,rollback=a.rollback)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__': main()
