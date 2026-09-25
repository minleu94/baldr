"""正式大盤歷史修訂的可得時間保護；不把晚取得資料追認為歷史 PIT。"""

from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
from collections.abc import Iterable, Mapping
import stat
from typing import Any

from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
)


RECEIPT_DIR = Path('output/scheduled/formal_market_repair_receipts')
_MARKET_REPAIR_SCHEMA_VERSION = 'formal-market-repair.v1'


class _MarketEvidenceCapture:
    """只在單次 market revision 驗證內保存已讀 bytes 的摘要。"""

    def __init__(self, receipt_root: Path) -> None:
        self.receipt_root = receipt_root.resolve(strict=True)
        self.files: list[ValidatedEvidenceFileV1] = []

    def _read_bytes(self, path: Path) -> bytes:
        try:
            resolved_before = path.resolve(strict=True)
        except RuntimeError as exc:
            raise ValueError('大盤修訂證據路徑含循環連結') from exc
        try:
            resolved_before.relative_to(self.receipt_root)
        except ValueError as exc:
            raise ValueError('大盤修訂證據路徑超出固定 receipt root') from exc

        payload = path.read_bytes()
        try:
            resolved_after = path.resolve(strict=True)
        except RuntimeError as exc:
            raise ValueError('大盤修訂證據路徑含循環連結') from exc
        try:
            resolved_after.relative_to(self.receipt_root)
        except ValueError as exc:
            raise ValueError('大盤修訂證據路徑超出固定 receipt root') from exc
        if resolved_after != resolved_before:
            raise ValueError('大盤修訂證據路徑在讀取期間改變')
        return payload

    def read_json_with_hash(self, path: Path, role_id: str) -> tuple[Any, str]:
        payload = self._read_bytes(path)
        digest = hashlib.sha256(payload).hexdigest()
        self.files.append(
            ValidatedEvidenceFileV1(role_id=role_id, sha256=digest)
        )
        return json.loads(payload.decode('utf-8')), digest

    def read_json(self, path: Path, role_id: str) -> Any:
        payload, _ = self.read_json_with_hash(path, role_id)
        return payload

    def read_hash_link(self, path: Path, role_id: str) -> str:
        payload = self._read_bytes(path)
        digest = hashlib.sha256(payload).hexdigest()
        self.files.append(ValidatedEvidenceFileV1(role_id=role_id, sha256=digest))
        return digest


def _market_root(database_path: Path) -> Path:
    root = database_path.resolve().parent
    if root.name.lower() == 'sqlite':
        root = root.parent
    return root


def _market_receipt_root(database_path: Path) -> Path | None:
    root = _market_root(database_path)
    root_resolved = root.resolve(strict=True)
    current = root
    parts = RECEIPT_DIR.parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            # 只有已逐段確認的普通祖先下，真正不存在的下一段才代表 EMPTY。
            return None
        except OSError as exc:
            raise ValueError(f'無法檢查大盤修訂 receipt root：{current}') from exc
        try:
            resolved = current.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'大盤修訂 receipt root 含失效連結：{current}') from exc
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError('大盤修訂 receipt root 超出資料根目錄') from exc
        try:
            is_directory = stat.S_ISDIR(resolved.stat().st_mode)
        except OSError as exc:
            raise ValueError(f'無法檢查大盤修訂 receipt root：{resolved}') from exc
        if not is_directory:
            raise ValueError(f'大盤修訂 receipt root 路徑元件不是目錄：{current}')
        if index == len(parts) - 1:
            return resolved
    return None


def _market_marker_paths(receipt_root: Path) -> list[Path]:
    markers: list[Path] = []
    resolved_runs: set[Path] = set()
    try:
        with os.scandir(receipt_root) as entries:
            run_paths = sorted(
                (Path(entry.path) for entry in entries),
                key=lambda path: path.name,
            )
    except OSError as exc:
        raise ValueError(f'無法完整掃描大盤修訂 receipt root：{receipt_root}') from exc

    for run_path in run_paths:
        try:
            run_path.lstat()
        except OSError as exc:
            raise ValueError(f'無法檢查大盤修訂 run 目錄：{run_path}') from exc
        try:
            resolved_run = run_path.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'大盤修訂 run 目錄含失效連結：{run_path}') from exc
        try:
            run_mode = resolved_run.stat().st_mode
        except OSError as exc:
            raise ValueError(f'無法檢查大盤修訂 run 目錄：{run_path}') from exc
        if not stat.S_ISDIR(run_mode):
            continue
        try:
            resolved_run.relative_to(receipt_root)
        except ValueError as exc:
            raise ValueError(f'大盤修訂 run 目錄超出固定 receipt root：{run_path}') from exc
        if resolved_run in resolved_runs:
            raise ValueError(f'多個大盤修訂 run 路徑指向同一目錄：{run_path}')
        resolved_runs.add(resolved_run)
        marker = run_path / 'revision.json'
        try:
            marker.lstat()
        except FileNotFoundError:
            try:
                if run_path.resolve(strict=True) != resolved_run:
                    raise ValueError(f'大盤修訂 run 目錄在掃描期間改變：{run_path}')
            except (FileNotFoundError, RuntimeError, OSError) as exc:
                raise ValueError(f'大盤修訂 run 目錄在掃描期間消失：{run_path}') from exc
            continue
        except OSError as exc:
            raise ValueError(f'無法完整檢查大盤修訂 marker：{marker}') from exc
        markers.append(marker)
    return sorted(markers)


def _market_run_role_id(marker: Path, receipt_root: Path) -> str:
    relative_run = marker.parent.relative_to(receipt_root).as_posix()
    if not relative_run or relative_run.startswith('/') or any(
        part in {'', '.', '..'} for part in relative_run.split('/')
    ):
        raise ValueError('大盤修訂 run 路徑不是固定 receipt root 下的相對路徑')
    encoded = base64.urlsafe_b64encode(relative_run.encode('utf-8')).decode('ascii')
    return f'run_{encoded.rstrip("=")}'


def collect_market_revision_evidence(
    database_path: Path, decision_date: date
) -> ValidatedNamespaceEvidenceV1:
    """驗證 market revision 並摘要同次解析／hash-link 使用的 bytes。

    這只固定單次呼叫實際讀取的檔案 bytes；不宣稱多檔或跨資源具原子性。
    """
    try:
        receipt_root = _market_receipt_root(database_path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f'大盤來源修訂紀錄無法驗證：{database_path}') from exc
    if receipt_root is None:
        return ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )

    try:
        marker_paths = _market_marker_paths(receipt_root)
    except ValueError as exc:
        raise ValueError(f'大盤來源修訂紀錄無法驗證：{receipt_root}') from exc
    if not marker_paths:
        return ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )

    capture = _MarketEvidenceCapture(receipt_root)
    files: list[ValidatedEvidenceFileV1] = []
    for marker_path in marker_paths:
        try:
            run_role = _market_run_role_id(marker_path, receipt_root)
            marker_role = f'{run_role}/revision.json'
            journal_role = f'{run_role}/journal.json'
            plan_role = f'{run_role}/plan.json'
            payload = capture.read_json(marker_path, marker_role)
            if payload['schema_version'] != 'formal-market-revision.v1':
                raise ValueError('不支援的大盤修訂標記')
            if Path(payload['database_path']).resolve() != database_path.resolve():
                raise ValueError('大盤修訂資料庫不符')
            state = payload['state']
            if state not in {'pending', 'applied', 'rolled_back'}:
                raise ValueError('未知大盤修訂狀態')

            journal = capture.read_json(
                marker_path.parent / 'journal.json', journal_role
            )
            plan, plan_sha256 = capture.read_json_with_hash(
                marker_path.parent / 'plan.json', plan_role
            )
            if (
                journal['schema_version'] != _MARKET_REPAIR_SCHEMA_VERSION
                or plan['schema_version'] != _MARKET_REPAIR_SCHEMA_VERSION
            ):
                raise ValueError('不支援的大盤修訂鏈格式')
            if plan_sha256 != journal['plan_sha256']:
                raise ValueError('大盤修訂計畫 hash 不符')
            if any(
                payload[field] != plan[field]
                for field in ('database_path', 'source_start_date', 'source_end_date')
            ):
                raise ValueError('大盤修訂標記與計畫範圍不符')

            if state == 'applied':
                receipt_role = f'{run_role}/receipt.json'
                receipt, receipt_sha256 = capture.read_json_with_hash(
                    marker_path.parent / 'receipt.json', receipt_role
                )
                if (
                    receipt['schema_version'] != _MARKET_REPAIR_SCHEMA_VERSION
                    or receipt_sha256 != payload['receipt_sha256']
                    or receipt['plan_sha256'] != journal['plan_sha256']
                ):
                    raise ValueError('不支援或不符的大盤修訂完成紀錄')
            start = date.fromisoformat(plan['source_start_date'])
            if state == 'rolled_back':
                rollback_role = f'{run_role}/rollback.json'
                rollback_sha256 = capture.read_hash_link(
                    marker_path.parent / 'rollback.json', rollback_role
                )
                if rollback_sha256 != payload['rollback_sha256']:
                    raise ValueError('大盤回復紀錄不符')
            files.extend(capture.files)
            capture.files.clear()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f'大盤來源修訂紀錄無法驗證：{marker_path}') from exc
        if state != 'rolled_back' and decision_date >= start:
            raise ValueError(
                f'formal market source revision blocks historical PIT from {start}; '
                'use a revision-aware rebuilt dataset; current data is not historical availability'
            )

    return ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.MARKET_REVISION,
        presence=SourceEvidencePresenceV1.PRESENT,
        files=tuple(files),
    )


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
    collect_market_revision_evidence(database_path, decision_date)
