"""MOPS現況財報HTML正規化；以明示單位及報表基礎建立非PIT觀測。"""
from __future__ import annotations
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup

STATEMENTS={'income':('t163sb04','income_statement','年初累計'),'balance':('t163sb05','balance_sheet','期末'),'cashflow':('t163sb20','cash_flows_statement','本期（期間基礎未明示）')}
BASIS_METADATA={
    'income':('year_to_date_cumulative',True,False),
    'balance':('period_end',True,False),
    'cashflow':('unknown',False,False),
}


def parse_current_statement_html(html: str, *, market: str, period: str, statement: str, observed_at: datetime, source_available_at: datetime | None = None) -> tuple[list[dict[str,str]],dict[str,Any]]:
    if market not in {'twse','tpex'} or statement not in STATEMENTS:
        raise ValueError('未知市場／財報類型')
    if observed_at.tzinfo is None or observed_at > datetime.now(timezone.utc):
        raise ValueError('觀測時間必須含時區且不得為未來')
    source_time=source_available_at
    if source_time is not None:
        if source_time.tzinfo is None or source_time > observed_at:
            raise ValueError('來源捕獲時間不得晚於本機觀測時間')
        source_time=source_time.astimezone(timezone.utc)
    source_time_text=source_time.isoformat() if source_time is not None else ''
    capture_marker=source_time_text or 'unknown'
    year,quarter=map(int,period.split('-Q'))
    if quarter not in {1,2,3,4}: raise ValueError('錯誤季度')
    end=date(year,quarter*3,monthrange(year,quarter*3)[1])
    if end > observed_at.date(): raise ValueError('尚未結束季度')
    soup=BeautifulSoup(html,'html.parser');text=soup.get_text(' ',strip=True)
    if not re.search(r'單位\s*[:：]\s*新[台臺]幣\s*[仟千]元',text):
        raise ValueError('官方HTML未明示金額單位')
    if ('上市公司' if market=='twse' else '上櫃公司') not in text:
        raise ValueError('市場標題不符')
    quarter_label={1:'第一季',2:'第二季',3:'第三季',4:'第四季'}[quarter]
    if quarter_label not in text and f'第{quarter}季' not in text:
        raise ValueError('財報季度標題不符')
    if statement == 'income' and '累計' not in text:
        raise ValueError('未明示年初累計基礎')
    version=f'mops-current-statement-html.v3:{market}:{statement}:sha256:{hashlib.sha256(html.encode()).hexdigest()}:captured_at:{capture_marker}'
    _,prefix,basis=STATEMENTS[statement]
    period_basis,basis_verified,aggregate_feature_eligible=BASIS_METADATA[statement]
    seen: dict[tuple[str,str],dict[str,str]]={};skipped=0
    clean=lambda s: re.sub(r'\s+','',s).replace('\xa0','')
    for table in soup.find_all('table'):
        headers=None
        for tr in table.find_all('tr',recursive=False) or table.find_all('tr'):
            cells=[clean(c.get_text('',strip=True)) for c in tr.find_all(['td','th'],recursive=False)]
            if '公司代號' in cells:
                headers=cells;continue
            if headers is None or len(cells)!=len(headers) or not cells or not re.fullmatch(r'\d{4,6}',cells[0]): continue
            code=cells[0]
            for name,raw in zip(headers[2:],cells[2:]):
                if not name or raw in {'','--','-','不適用'}: skipped+=1;continue
                try: value=Decimal(raw.replace(',',''))
                except InvalidOperation: skipped+=1;continue
                if not value.is_finite(): raise ValueError('非有限財報數值')
                unit='TWD/share' if '每股' in name or 'EPS' in name.upper() else 'shares' if '股數' in name or '單位：股' in name else 'percent' if '%' in name or '％' in name else 'TWD'
                if unit=='TWD': value*=Decimal(1000)
                item_code=f'{prefix}:{name}'
                row={'stock_code':code,'kind':'statement_item','period':period,'as_of_date':end.isoformat(),'item_code':item_code,'item_name':f'{prefix}:{basis}:{name}','value':format(value,'f'),'unit':unit,'observed_at':observed_at.isoformat(),'source':f'mops.current_statement_html.{statement}','source_version':version,'market':market,'period_basis':period_basis,'basis_verified':'1' if basis_verified else '0','aggregate_feature_eligible':'1' if aggregate_feature_eligible else '0'}
                row['aggregate_feature_eligible']='0'
                row['source_available_at']=source_time_text
                key=(code,item_code)
                if key in seen and seen[key]!=row: raise ValueError('同一財報來源含衝突值')
                seen[key]=row
    if not seen: raise ValueError('官方財報HTML沒有可正規化數值')
    rows=list(seen.values())
    summary={'market':market,'period':period,'statement':statement,'row_count':len(rows),'stock_count':len({r['stock_code'] for r in rows}),'source_version':version,'source_unit':'新台幣仟元','basis':basis,'period_basis':period_basis,'basis_verified':basis_verified,'aggregate_feature_eligible':aggregate_feature_eligible,'missing_or_non_numeric_fields':skipped,'historical_pit_eligible':False}
    summary['aggregate_feature_eligible']=False
    summary['source_available_at']=source_time_text or None
    summary['observed_at']=observed_at.isoformat()
    return rows,summary
