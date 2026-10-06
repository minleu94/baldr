"""法人候選觀測的版本化修訂投影；舊列與失敗checkpoint不可變。"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Mapping, Sequence

FIELDS = tuple(f'{group}_{suffix}' for group in ('foreign_investor', 'investment_trust', 'dealer') for suffix in ('buy', 'sell', 'net'))
TABLE = 'institutional_current_revisions'
SUPPORTED_SOURCE_VERSIONS = frozenset({'twse-official-T86', 'tpex-official-3itrade'})
SCHEMA = f'''CREATE TABLE IF NOT EXISTS {TABLE} (
 stock_code TEXT NOT NULL, decision_date TEXT NOT NULL, observation_hash TEXT NOT NULL,
 observed_at TEXT NOT NULL, source_version TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(stock_code, decision_date, observation_hash));'''


def _aware_timestamp(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a timezone-aware ISO timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{field_name} must be a timezone-aware ISO timestamp') from exc
    if parsed.tzinfo is None:
        raise ValueError(f'{field_name} must be a timezone-aware ISO timestamp')
    return parsed


def _row_mapping(cursor: sqlite3.Cursor, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    return {str(column[0]): value for column, value in zip(cursor.description or (), row)}


def _verified_revision_row(
    conn: sqlite3.Connection,
    revision: Mapping[str, Any],
    *,
    stock_code: str,
) -> dict[str, Any]:
    observation = conn.execute(
        "SELECT canonical_payload_json FROM phase3c_source_observations "
        "WHERE source='institutional' AND decision_date=? AND observation_hash=?",
        (revision['decision_date'], revision['observation_hash']),
    ).fetchone()
    if observation is None or not isinstance(observation[0], str):
        raise ValueError('institutional revision source observation is missing')
    canonical_payload_json = observation[0]
    expected_hash = 'sha256:' + hashlib.sha256(canonical_payload_json.encode('utf8')).hexdigest()
    if expected_hash != revision['observation_hash']:
        raise ValueError('institutional revision canonical observation hash mismatch')
    try:
        payload = json.loads(canonical_payload_json)
        row = json.loads(revision['payload_json'])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('institutional revision payload is invalid JSON') from exc
    if not isinstance(payload, dict) or payload.get('schema_version') != 'phase3c-canonical-observation.v1':
        raise ValueError('institutional revision canonical observation schema mismatch')
    observation_clock = _aware_timestamp(payload.get('observation_at'), field_name='observation_at')
    revision_clock = _aware_timestamp(revision['observed_at'], field_name='revision observed_at')
    if observation_clock != revision_clock:
        raise ValueError('institutional revision observation clock mismatch')
    if not isinstance(row, dict) or row.get('stock_code') != stock_code or row.get('decision_date') != revision['decision_date']:
        raise ValueError('institutional revision row identity mismatch')
    if row.get('source_version') != revision['source_version'] or row.get('source_version') not in SUPPORTED_SOURCE_VERSIONS:
        raise ValueError('institutional revision source version mismatch')
    if any(type(row.get(field)) is not int for field in FIELDS):
        raise ValueError('institutional revision flow quantities must be integers')
    if any(row[group + '_buy'] - row[group + '_sell'] != row[group + '_net'] for group in ('foreign_investor', 'investment_trust', 'dealer')):
        raise ValueError('institutional revision buy-sell invariant mismatch')
    rows = payload.get('rows')
    matching = [item for item in rows if isinstance(item, dict) and item.get('stock_code') == stock_code] if isinstance(rows, list) else []
    if matching != [row]:
        raise ValueError('institutional revision row does not match canonical observation')
    return row


def _verify_same_clock_revision_group(
    conn: sqlite3.Connection,
    revisions: Sequence[Mapping[str, Any]],
    *,
    stock_code: str,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """驗證同一觀測時鐘的所有修訂列，並回傳經驗證的一致版本。"""
    if not revisions:
        raise ValueError('institutional revision clock group is empty')
    revision_clocks = {
        _aware_timestamp(row.get('observed_at'), field_name='revision observed_at')
        for row in revisions
    }
    if len(revision_clocks) != 1:
        raise ValueError('institutional revision clock group contains different clocks')
    verified = [
        (revision, _verified_revision_row(conn, revision, stock_code=stock_code))
        for revision in revisions
    ]
    first_row = verified[0][1]
    if any(
        any(first_row[field] != row[field] for field in FIELDS)
        for _, row in verified[1:]
    ):
        raise ValueError('conflicting institutional revisions share one observation clock')
    return max(verified, key=lambda item: str(item[0]['observation_hash']))


def _latest_revision_row(
    conn: sqlite3.Connection,
    *,
    stock_code: str,
    decision_date: str,
    observed_at: datetime,
) -> dict[str, Any] | None:
    cursor = conn.execute(
        f'SELECT * FROM {TABLE} WHERE stock_code=? AND decision_date=?',
        (stock_code, decision_date),
    )
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for raw_row in cursor.fetchall():
        row = _row_mapping(cursor, raw_row)
        assert row is not None
        row_clock = _aware_timestamp(row.get('observed_at'), field_name='revision observed_at')
        if row_clock <= observed_at:
            candidates.append((row_clock, row))
    if not candidates:
        return None
    latest_clock = max(item[0] for item in candidates)
    latest_group = [row for row_clock, row in candidates if row_clock == latest_clock]
    _, latest = _verify_same_clock_revision_group(
        conn,
        latest_group,
        stock_code=stock_code,
    )
    return latest


def project_observation(conn: sqlite3.Connection, observation: dict[str, Any]) -> dict[str, Any]:
    """逐列驗證保留觀測，只追加與舊版不同／缺少的完整數值版本。"""
    payload_text = observation['canonical_payload_json']
    digest = 'sha256:' + hashlib.sha256(payload_text.encode('utf8')).hexdigest()
    if digest != observation['observation_hash']:
        raise ValueError('canonical observation hash不符')
    payload = json.loads(payload_text)
    if not isinstance(payload, dict) or payload.get('schema_version') != 'phase3c-canonical-observation.v1':
        raise ValueError('canonical observation schema不符')
    observed = _aware_timestamp(observation['observed_at'], field_name='observed_at')
    payload_observed = _aware_timestamp(payload.get('observation_at'), field_name='observation_at')
    if observed > datetime.now(timezone.utc) or payload_observed != observed:
        raise ValueError('observation clock不符／未來時間')
    day = observation['decision_date']
    if date.fromisoformat(day) > observed.date():
        raise ValueError('資料日期晚於觀測時間')
    old_cursor = conn.execute('SELECT * FROM institutional_flows WHERE decision_date=?', (day,))
    old_rows = old_cursor.fetchall()
    old = {
        row['stock_code']: row
        for raw_row in old_rows
        if (row := _row_mapping(old_cursor, raw_row)) is not None
    }
    conn.execute(SCHEMA)
    records = payload.get('rows')
    if not isinstance(records,list) or len(records) != observation['row_count']:
        raise ValueError('canonical row_count不符')
    seen: set[str] = set()
    projected = []
    for row in records:
        code = row['stock_code']
        if code in seen or not code or row['decision_date'] != day or row['source_version'] not in SUPPORTED_SOURCE_VERSIONS:
            raise ValueError('canonical key或source identity不符')
        seen.add(code)
        if any(type(row.get(field)) is not int for field in FIELDS):
            raise ValueError('法人數值必須使用整數股數')
        if any(row[group+'_buy']-row[group+'_sell'] != row[group+'_net'] for group in ('foreign_investor','investment_trust','dealer')):
            raise ValueError('法人buy-sell與net不一致')
        for clock_field in ('first_observed_at', 'available_at'):
            row_clock = _aware_timestamp(row.get(clock_field), field_name=clock_field)
            if row_clock > observed:
                raise ValueError(f'{clock_field} cannot be later than observation_at')
        previous = _latest_revision_row(
            conn,
            stock_code=code,
            decision_date=day,
            observed_at=observed,
        )
        if previous is None:
            previous = old.get(code)
        if previous is None or any(previous[field] != row[field] for field in FIELDS):
            projected.append((code,day,digest,observed.isoformat(),row['source_version'],json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))))
    before=conn.total_changes
    for values in projected:
        existing=conn.execute(f'SELECT observed_at,source_version,payload_json FROM {TABLE} WHERE stock_code=? AND decision_date=? AND observation_hash=?',values[:3]).fetchone()
        if existing is not None and tuple(existing) != values[3:]:
            raise ValueError('修訂版本已存在且內容衝突')
    conn.executemany(f'INSERT OR IGNORE INTO {TABLE} VALUES (?,?,?,?,?,?)',projected)
    return {'decision_date':day,'observation_hash':digest,'observed_at':observed.isoformat(),'source_rows_verified':len(records),'revision_rows':len(projected),'inserted_count':conn.total_changes-before,'historical_pit_eligible':False,'original_rows_and_checkpoint_unchanged':True}


def read_current_institutional(
    conn: sqlite3.Connection,
    *,
    stock_code: str,
    observed_at: datetime,
    decision_date: date,
) -> dict[str, Any] | None:
    """Read the latest observation valid at the supplied current-observation clock."""
    if observed_at.tzinfo is None:
        raise ValueError('observed_at must be timezone-aware')
    cutoff = observed_at.isoformat()
    base_cursor = conn.execute(
        'SELECT * FROM institutional_flows '
        'WHERE stock_code=? AND decision_date<=? '
        'AND julianday(available_at)<=julianday(?) '
        'ORDER BY decision_date DESC LIMIT 1',
        (stock_code, decision_date.isoformat(), cutoff),
    )
    base = base_cursor.fetchone()
    selected = _row_mapping(base_cursor, base)
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE,),
    ).fetchone()
    if not exists:
        return selected

    revision_cursor = conn.execute(
        f'SELECT * FROM {TABLE} WHERE stock_code=? AND decision_date<=?',
        (stock_code, decision_date.isoformat()),
    )
    raw_revisions = revision_cursor.fetchall()
    revisions: list[tuple[date, datetime, dict[str, Any]]] = []
    for raw_row in raw_revisions:
        mapping = _row_mapping(revision_cursor, raw_row)
        assert mapping is not None
        revision_date = date.fromisoformat(mapping['decision_date'])
        revision_clock = _aware_timestamp(mapping.get('observed_at'), field_name='revision observed_at')
        if revision_clock <= observed_at:
            revisions.append((revision_date, revision_clock, mapping))
    if not revisions:
        return selected
    revision_date = max(item[0] for item in revisions)
    same_date = [item for item in revisions if item[0] == revision_date]
    revision_clock = max(item[1] for item in same_date)
    latest_group = [item[2] for item in same_date if item[1] == revision_clock]
    revision, row = _verify_same_clock_revision_group(
        conn,
        latest_group,
        stock_code=stock_code,
    )

    if selected is not None and revision_date.isoformat() < selected['decision_date']:
        return selected
    row.update(
        available_at=revision['observed_at'],
        observed_at=revision['observed_at'],
        revision_observation_hash=revision['observation_hash'],
        quality='observed',
        historical_pit_eligible=False,
    )
    return row
