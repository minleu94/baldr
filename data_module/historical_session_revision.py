"""補回真實歷史交易日後，保護新來源可得時間及重匯完整性。"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from data_module.contracts.source_revision import (
    SourceEvidenceNamespaceV1,
    SourceEvidencePresenceV1,
    ValidatedEvidenceFileV1,
    ValidatedNamespaceEvidenceV1,
)

RECEIPT_DIR = Path('output/scheduled/historical_session_repair_receipts')


def _root(database_path: Path) -> Path:
    parent = database_path.resolve().parent
    return parent.parent if parent.name.lower() == 'sqlite' else parent


class _SessionEvidenceCapture:
    """只在單次 session revision 驗證內摘要實際讀取的 bytes。"""

    def __init__(self, receipt_root: Path) -> None:
        self.receipt_root = receipt_root.resolve(strict=True)
        self.files: list[ValidatedEvidenceFileV1] = []

    def _read_bytes(self, path: Path, expected_run: Path) -> bytes:
        try:
            resolved_before = path.resolve(strict=True)
            run_before = path.parent.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'歷史交易日修訂證據路徑無法解析：{path}') from exc
        try:
            resolved_before.relative_to(self.receipt_root)
            run_before.relative_to(self.receipt_root)
        except ValueError as exc:
            raise ValueError(f'歷史交易日修訂證據路徑超出固定 receipt root：{path}') from exc
        if run_before != expected_run:
            raise ValueError(f'歷史交易日修訂 run 路徑在掃描後改變：{path.parent}')
        try:
            if not stat.S_ISREG(resolved_before.stat().st_mode):
                raise ValueError(f'歷史交易日修訂證據不是一般檔案：{path}')
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日修訂證據：{path}') from exc

        payload = path.read_bytes()
        try:
            resolved_after = path.resolve(strict=True)
            run_after = path.parent.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'歷史交易日修訂證據讀取後路徑無法解析：{path}') from exc
        try:
            resolved_after.relative_to(self.receipt_root)
            run_after.relative_to(self.receipt_root)
        except ValueError as exc:
            raise ValueError(f'歷史交易日修訂證據讀取後超出固定 receipt root：{path}') from exc
        if resolved_after != resolved_before or run_after != expected_run:
            raise ValueError(f'歷史交易日修訂證據路徑在讀取期間改變：{path}')
        try:
            if not stat.S_ISREG(resolved_after.stat().st_mode):
                raise ValueError(f'歷史交易日修訂證據讀取後不是一般檔案：{path}')
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日修訂證據：{path}') from exc
        return payload

    def read_bytes_with_hash(
        self, path: Path, role_id: str, expected_run: Path
    ) -> tuple[bytes, str]:
        payload = self._read_bytes(path, expected_run)
        digest = hashlib.sha256(payload).hexdigest()
        self.files.append(ValidatedEvidenceFileV1(role_id=role_id, sha256=digest))
        return payload, digest

    def read_json(self, path: Path, role_id: str, expected_run: Path) -> Any:
        payload = self._read_bytes(path, expected_run)
        digest = hashlib.sha256(payload).hexdigest()
        parsed = json.loads(payload.decode('utf-8'))
        self.files.append(ValidatedEvidenceFileV1(role_id=role_id, sha256=digest))
        return parsed


def _read_json(
    path: Path,
    *,
    capture: _SessionEvidenceCapture | None,
    role_id: str | None,
    expected_run: Path | None,
) -> Any:
    if capture is None:
        return json.loads(path.read_text(encoding='utf-8'))
    if role_id is None or expected_run is None:
        raise ValueError('session evidence capture 缺少檔案角色或 run 身分')
    return capture.read_json(path, role_id, expected_run)


def _read_bytes_with_hash(
    path: Path,
    *,
    capture: _SessionEvidenceCapture | None,
    role_id: str | None,
    expected_run: Path | None,
) -> tuple[bytes, str]:
    if capture is not None:
        if role_id is None or expected_run is None:
            raise ValueError('session evidence capture 缺少檔案角色或 run 身分')
        return capture.read_bytes_with_hash(path, role_id, expected_run)
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return payload, digest


def _validated_plan(
    path: Path,
    database_path: Path,
    *,
    capture: _SessionEvidenceCapture | None = None,
    run_role: str | None = None,
    expected_run: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        marker = _read_json(
            path,
            capture=capture,
            role_id=None if run_role is None else f'{run_role}/revision.json',
            expected_run=expected_run,
        )
        if marker['schema_version'] != 'historical-session-revision.v1' or Path(marker['database_path']).resolve() != database_path.resolve():
            raise ValueError('修訂標記不符')
        plan_bytes, plan_sha256 = _read_bytes_with_hash(
            path.parent / 'plan.json',
            capture=capture,
            role_id=None if run_role is None else f'{run_role}/plan.json',
            expected_run=expected_run,
        )
        if plan_sha256 != marker['plan_sha256']:
            raise ValueError('修訂計畫 hash 不符')
        plan = json.loads(plan_bytes)
        if marker['state'] not in {'pending', 'applied', 'rolled_back'} or plan['database_path'] != marker['database_path'] or marker.get('historical_pit') is not False:
            raise ValueError('修訂狀態不符')
        if plan['schema_version'] != 'historical-session-repair.v1' or plan['source_start_date'].replace('-', '') != min(plan['dates']):
            raise ValueError('修訂範圍不符')
        if marker['state'] in {'applied', 'rolled_back'}:
            receipt_name = 'receipt.json' if marker['state'] == 'applied' else 'rollback.json'
            receipt_bytes, receipt_sha256 = _read_bytes_with_hash(
                path.parent / receipt_name,
                capture=capture,
                role_id=None if run_role is None else f'{run_role}/{receipt_name}',
                expected_run=expected_run,
            )
            if receipt_sha256 != marker['receipt_sha256']:
                raise ValueError('修訂完成證據不符')
            receipt = json.loads(receipt_bytes)
            if receipt['state'] != marker['state'] or receipt['plan_sha256'] != marker['plan_sha256'] or receipt['dates'] != plan['dates']:
                raise ValueError('完成證據與修訂計畫不符')
        return marker, plan
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'歷史交易日修訂證據無法驗證：{path}') from exc


def _plan(path: Path, database_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """保留既有 tuple API，並共用 session revision 的單一鏈驗證路徑。"""
    return _validated_plan(path, database_path)


def _session_receipt_root(database_path: Path) -> Path | None:
    root = _root(database_path)
    try:
        resolved_root = root.resolve(strict=True)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        raise ValueError(f'無法解析歷史交易日資料根目錄：{root}') from exc

    current = root
    expected_parent = resolved_root
    for component in RECEIPT_DIR.parts:
        current = current / component
        try:
            current.lstat()
        except FileNotFoundError:
            try:
                resolved_parent = current.parent.resolve(strict=True)
                resolved_parent.relative_to(resolved_root)
                if resolved_parent != expected_parent or not stat.S_ISDIR(
                    resolved_parent.stat().st_mode
                ):
                    raise ValueError(
                        f'歷史交易日 receipt root 祖先在掃描期間改變：{current.parent}'
                    )
            except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
                raise ValueError(
                    f'歷史交易日 receipt root 缺少穩定祖先：{current.parent}'
                ) from exc
            return None
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日 receipt root：{current}') from exc
        try:
            resolved = current.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'歷史交易日 receipt root 含失效連結：{current}') from exc
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f'歷史交易日 receipt root 超出資料根目錄：{current}') from exc
        try:
            if not stat.S_ISDIR(resolved.stat().st_mode):
                raise ValueError(f'歷史交易日 receipt root 元件不是目錄：{current}')
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日 receipt root：{current}') from exc
        expected_parent = resolved
    return resolved


def _session_marker_paths(receipt_root: Path) -> list[tuple[Path, Path]]:
    try:
        with os.scandir(receipt_root) as entries:
            run_paths = sorted(
                (Path(entry.path) for entry in entries), key=lambda item: item.name
            )
    except OSError as exc:
        raise ValueError(f'無法完整掃描歷史交易日 receipt root：{receipt_root}') from exc

    markers: list[tuple[Path, Path]] = []
    resolved_runs: set[Path] = set()
    for run_path in run_paths:
        try:
            run_path.lstat()
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日 run 目錄：{run_path}') from exc
        try:
            resolved_run = run_path.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise ValueError(f'歷史交易日 run 目錄含失效連結：{run_path}') from exc
        try:
            resolved_run.relative_to(receipt_root)
        except ValueError as exc:
            raise ValueError(f'歷史交易日 run 目錄超出固定 receipt root：{run_path}') from exc
        try:
            is_directory = stat.S_ISDIR(resolved_run.stat().st_mode)
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日 run 目錄：{run_path}') from exc
        if not is_directory:
            continue
        if resolved_run in resolved_runs:
            raise ValueError(f'多個歷史交易日 run 路徑指向同一目錄：{run_path}')
        resolved_runs.add(resolved_run)

        marker_path = run_path / 'revision.json'
        try:
            marker_path.lstat()
        except FileNotFoundError:
            try:
                if run_path.resolve(strict=True) != resolved_run:
                    raise ValueError(f'歷史交易日 run 目錄在掃描期間改變：{run_path}')
            except (FileNotFoundError, RuntimeError, OSError) as exc:
                raise ValueError(f'歷史交易日 run 目錄在掃描期間消失：{run_path}') from exc
            continue
        except OSError as exc:
            raise ValueError(f'無法檢查歷史交易日 marker：{marker_path}') from exc
        markers.append((marker_path, resolved_run))
    return sorted(markers, key=lambda item: item[0].as_posix())


def _session_run_role_id(marker_path: Path, receipt_root: Path) -> str:
    relative_run = marker_path.parent.relative_to(receipt_root).as_posix()
    if not relative_run or relative_run.startswith('/') or any(
        part in {'', '.', '..'} for part in relative_run.split('/')
    ):
        raise ValueError('歷史交易日 run 路徑不是固定 receipt root 下的相對路徑')
    encoded = base64.urlsafe_b64encode(relative_run.encode('utf-8')).decode('ascii')
    return f'run_{encoded.rstrip("=")}'


def collect_session_revision_evidence(
    database_path: Path, decision_date: date
) -> ValidatedNamespaceEvidenceV1:
    """驗證 session revision 並摘要同次解析與 hash-link 使用的 bytes。

    本摘要固定單次掃描實際讀取的檔案；不同檔案／來源之間不宣稱原子性。
    """
    try:
        receipt_root = _session_receipt_root(database_path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f'歷史交易日修訂證據無法驗證：{database_path}') from exc
    if receipt_root is None:
        return ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )

    try:
        marker_paths = _session_marker_paths(receipt_root)
    except ValueError as exc:
        raise ValueError(f'歷史交易日修訂證據無法驗證：{receipt_root}') from exc
    if not marker_paths:
        return ValidatedNamespaceEvidenceV1(
            namespace=SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
            presence=SourceEvidencePresenceV1.EMPTY,
            files=(),
        )

    capture = _SessionEvidenceCapture(receipt_root)
    files: list[ValidatedEvidenceFileV1] = []
    for marker_path, expected_run in marker_paths:
        try:
            run_role = _session_run_role_id(marker_path, receipt_root)
            marker, plan = _validated_plan(
                marker_path,
                database_path,
                capture=capture,
                run_role=run_role,
                expected_run=expected_run,
            )
            first = date.fromisoformat(plan['source_start_date'])
            if marker_path.parent.resolve(strict=True) != expected_run:
                raise ValueError(f'歷史交易日 run 目錄在驗證期間改變：{marker_path.parent}')
            files.extend(capture.files)
            capture.files.clear()
        except (OSError, RuntimeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'歷史交易日修訂證據無法驗證：{marker_path}') from exc
        if marker['state'] != 'rolled_back' and decision_date >= first:
            raise ValueError(
                'historical session source revision blocks historical PIT; '
                'rebuild from explicitly revised sources'
            )

    return ValidatedNamespaceEvidenceV1(
        namespace=SourceEvidenceNamespaceV1.HISTORICAL_SESSION_REVISION,
        presence=SourceEvidencePresenceV1.PRESENT,
        files=tuple(files),
    )


def assert_session_revision_safe(database_path: Path, decision_date: date) -> None:
    collect_session_revision_evidence(database_path, decision_date)


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
