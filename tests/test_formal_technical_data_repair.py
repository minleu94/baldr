"""隔離重算的正式發布只改技指欄位，異常與回復不碰原始表。"""
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import repair_formal_technical_data as repair


@pytest.fixture
def scenario(tmp_path):
    root=tmp_path/'formal'
    (root/'sqlite').mkdir(parents=True)
    (root/'technical_analysis').mkdir()
    db=root/'sqlite/twstock.db'
    columns=list(repair.CAUSAL_INDICATOR_COLUMNS)
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE daily_prices (日期 TEXT,證券代號 TEXT,收盤價 REAL,PRIMARY KEY(證券代號,日期))')
        c.execute("INSERT INTO daily_prices VALUES ('20260102','1256',123)")
        c.execute('CREATE TABLE technical_indicators (日期 TEXT,證券代號 TEXT,extra TEXT,'+','.join(repair.quote(k)+' REAL' for k in columns)+',PRIMARY KEY(證券代號,日期))')
        c.execute("INSERT INTO technical_indicators (日期,證券代號,extra,RSI) VALUES ('20260102','1256','keep',1)")
    target=root/'technical_analysis/1256_indicators.csv'
    target.write_text('old',encoding='utf-8')
    directory=root/repair.RECEIPT_DIR/'run01'
    evidence=repair.prepare(root,directory)
    stage=directory/'stage'
    stage.mkdir()
    computed=stage/'computed.sqlite'
    with sqlite3.connect(computed) as c:
        c.execute('CREATE TABLE computed (日期 TEXT,證券代號 TEXT,'+','.join(repair.quote(k)+' REAL' for k in columns)+',PRIMARY KEY(證券代號,日期))')
        c.execute('INSERT INTO computed VALUES ('+','.join('?' for _ in range(len(columns)+2))+')',('20260102','1256',*range(len(columns))))
        c.execute('INSERT INTO computed VALUES ('+','.join('?' for _ in range(len(columns)+2))+')',('20260103','1256',*[None]*len(columns)))
    staged=stage/'1256.csv'
    staged.write_text('new',encoding='utf-8')
    new_target=root/'technical_analysis/1477_indicators.csv'
    new_staged=stage/'1477.csv'
    new_staged.write_text('new1477',encoding='utf-8')
    manifest={'source_db':evidence['source_db'],'source_sha256':evidence['source_sha256'],'computed_db':str(computed),'computed_sha256':repair.file_hash(computed),'computed_table':'computed','rows':2,'symbols':['1256'],'files':[
        {'target_path':str(target),'staged_path':str(staged),'before_sha256':repair.file_hash(target),'after_sha256':repair.file_hash(staged)},
        {'target_path':str(new_target),'staged_path':str(new_staged),'before_sha256':None,'after_sha256':repair.file_hash(new_staged)}]}
    (stage/'manifest.json').write_bytes(repair.encoded(manifest))
    return root,db,directory,target,new_target


def perform(scenario):
    directory=scenario[2]
    return repair.apply(directory,repair.file_hash(directory/'stage/manifest.json'))


def test_apply_preserves_other_columns_and_rollback(scenario):
    _,db,directory,target,new_target=scenario
    assert perform(scenario)['state']=='applied'
    assert target.read_text()=='new'
    with repair.readonly(db) as c:
        assert c.execute('SELECT extra FROM technical_indicators WHERE 日期=?',('20260102',)).fetchone()==('keep',)
        assert c.execute('SELECT 收盤價 FROM daily_prices').fetchone()==(123,)
        assert c.execute('SELECT RSI FROM technical_indicators WHERE 日期=?',('20260103',)).fetchone()==(None,)
    repair.recover(directory,rollback=True)
    assert target.read_text()=='old'
    assert not new_target.exists()
    with repair.readonly(db) as c:
        assert c.execute('SELECT count(*),RSI FROM technical_indicators').fetchone()==(1,1)
    with pytest.raises(ValueError,match='只允許'):
        repair.recover(directory,rollback=True)


@pytest.mark.parametrize('point',['database','csv','source'])
def test_prepublication_drift_never_overwrites_other_changes(scenario,point):
    _,db,directory,target,_=scenario
    if point=='csv': target.write_text('concurrent',encoding='utf-8')
    elif point=='database':
        with sqlite3.connect(db) as c: c.execute('UPDATE technical_indicators SET RSI=9')
    else: (directory/'source.sqlite').write_bytes(b'broken')
    with pytest.raises(ValueError): perform(scenario)
    assert target.read_text()==('concurrent' if point=='csv' else 'old')
    with repair.readonly(db) as c:
        assert c.execute('SELECT count(*),RSI FROM technical_indicators').fetchone()==(1,9 if point=='database' else 1)


@pytest.mark.parametrize('point',['csv','receipt'])
def test_failure_restores_or_resumes_consistently(scenario,monkeypatch,point):
    _,db,directory,target,_=scenario
    original_copy=repair.copy_atomic
    original_atomic=repair.atomic
    def copy(src,dst):
        original_copy(src,dst)
        if point=='csv' and dst==target and src.parent.name=='stage': raise RuntimeError('interrupted')
    def atomic(path,body):
        original_atomic(path,body)
        if point=='receipt' and path.name=='receipt.json': raise RuntimeError('interrupted')
    monkeypatch.setattr(repair,'copy_atomic',copy)
    monkeypatch.setattr(repair,'atomic',atomic)
    with pytest.raises(RuntimeError): perform(scenario)
    monkeypatch.setattr(repair,'copy_atomic',original_copy)
    monkeypatch.setattr(repair,'atomic',original_atomic)
    assert repair.recover(directory,rollback=False)['state']==('rolled_back' if point=='csv' else 'applied')
    assert target.read_text()==('old' if point=='csv' else 'new')


def test_recovery_refuses_journal_path_drift(scenario):
    _,_,directory,_,_=scenario
    perform(scenario)
    journal=json.loads((directory/'journal.json').read_text())
    journal['files'][0]['target_path']='C:/unrelated/file.csv'
    (directory/'journal.json').write_bytes(repair.encoded(journal))
    with pytest.raises(ValueError,match='身分'):
        repair.recover(directory,rollback=True)


def test_recovery_refuses_newer_price_source(scenario):
    _,db,directory,target,_=scenario
    perform(scenario)
    with sqlite3.connect(db) as c: c.execute('UPDATE daily_prices SET 收盤價=130')
    with pytest.raises(ValueError,match='日價'):
        repair.recover(directory,rollback=True)
    assert target.read_text()=='new'


def test_real_stager_adapter_publication_and_rollback(scenario):
    root,db,_,target,_=scenario
    with sqlite3.connect(db) as c:
        for name in ('開盤價','最高價','最低價','成交股數'):
            c.execute('ALTER TABLE daily_prices ADD COLUMN '+repair.quote(name)+' REAL')
        c.execute('UPDATE daily_prices SET 開盤價=122,最高價=124,最低價=121,成交股數=100')
    target.write_text('日期,證券代號,RSI,custom\n2026-01-02,1256,1,preserve\n',encoding='utf-8-sig')
    before=target.read_bytes()
    directory=root/repair.RECEIPT_DIR/'run02'
    repair.prepare(root,directory)
    manifest=repair.stage(directory)
    assert manifest['rows']==1
    repair.apply(directory,repair.file_hash(directory/'stage/manifest.json'))
    import csv
    with target.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert rows[0]['custom']=='preserve'
    assert rows[0]['RSI']==''
    with repair.readonly(db) as c:
        assert c.execute('SELECT RSI,extra FROM technical_indicators').fetchone()==(None,'keep')
    repair.recover(directory,rollback=True)
    assert target.read_bytes()==before
    assert not (root/'meta_data/all_stocks_data.csv').exists()
