"""Controlled monthly revenue backfill into the fundamental SQLite tables."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from data_module.contracts.fundamental import SourceDiagnostic
from data_module.fundamental_availability_sources import (
    load_monthly_revenue_availability_overrides_csv,
)
from data_module.fundamental_data import (
    MonthlyRevenueRecord,
    legacy_monthly_revenue_quality_value,
    parse_monthly_revenue_rows,
)
from data_module.monthly_revenue_availability_history import (
    _snapshot_session_available_date,
)

MOPS_MONTHLY_REVENUE_SNAPSHOT_SOURCE = "mops.monthly_revenue_static_snapshot"
_RESEARCH_SOURCE_CONTRACT_SCHEMA = "monthly-revenue-source-contract.v1"
_RESEARCH_SOURCE_CONTRACT_ID = "official_twse_tpex_openapi_monthly_revenue.v1"
_RESEARCH_COMPOSITE_SOURCE = "twse_tpex.open_api.monthly_revenue_snapshot"
_RESEARCH_SOURCE_SCOPE_SCHEMA = "monthly-revenue-full-official-research-scope.v1"
_RESEARCH_SNAPSHOT_SOURCE_FIELD_MAP = {
    "company_name": "公司名稱",
    "current_month_revenue": "營業收入-當月營收",
    "previous_month_revenue": "營業收入-上月營收",
    "previous_year_month_revenue": "營業收入-去年當月營收",
    "mom_pct": "營業收入-上月比較增減(%)",
    "yoy_pct": "營業收入-去年同月增減(%)",
    "cumulative_revenue": "累計營業收入-當月累計營收",
    "previous_year_cumulative_revenue": "累計營業收入-去年累計營收",
    "cumulative_yoy_pct": "累計營業收入-前期比較增減(%)",
    "note": "備註",
}
_RESEARCH_SOURCE_VENUES = {
    "twse": {
        "source": "twse.open_api.monthly_revenue",
        "source_id": "twse-openapi-t187ap05_L",
        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        "raw_file": "source/twse.json",
    },
    "tpex": {
        "source": "tpex.open_api.monthly_revenue",
        "source_id": "tpex-openapi-mopsfin_t187ap05_O",
        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
        "raw_file": "source/tpex.json",
    },
}
_RESEARCH_CAPTURE_MANIFEST_FILE = "source/capture_run.json"
_MAX_SOURCE_CONTRACT_FILE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class MonthlyRevenueBackfillPlan:
    records: tuple[MonthlyRevenueRecord, ...]
    diagnostics: tuple[SourceDiagnostic, ...]
    raw_row_count: int
    snapshot_duplicate_row_count: int = 0
    snapshot_unmatched_mapping_count: int = 0
    snapshot_invalid_row_count: int = 0
    snapshot_scope: str = "complete"
    full_snapshot_row_count: int | None = None
    excluded_snapshot_row_count: int = 0
    formal_apply_blocked_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def ready_for_apply(self) -> bool:
        """Whether the parsed preview is internally complete and diagnostic-free."""

        return bool(self.records) and not self.diagnostics

    @property
    def formal_apply_eligible(self) -> bool:
        """Whether this plan uses a source lane accepted by the existing writer."""

        accepted_sources = {
            MOPS_MONTHLY_REVENUE_SNAPSHOT_SOURCE,
            "financial_data.monthly_revenue_csv",
        }
        return (
            self.ready_for_apply
            and self.formal_apply_blocked_reason is None
            and all(
                record.source in accepted_sources for record in self.records
            )
        )

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Monthly Revenue Backfill Plan",
                "",
                f"- ready_for_apply: {str(self.ready_for_apply).lower()}",
                f"- formal_apply_eligible: {str(self.formal_apply_eligible).lower()}",
                f"- formal_apply_blocked_reason: {self.formal_apply_blocked_reason or 'none'}",
                f"- raw_row_count: {self.raw_row_count}",
                f"- normalized_record_count: {len(self.records)}",
                f"- snapshot_duplicate_row_count: {self.snapshot_duplicate_row_count}",
                f"- snapshot_unmatched_mapping_count: {self.snapshot_unmatched_mapping_count}",
                f"- snapshot_invalid_row_count: {self.snapshot_invalid_row_count}",
                f"- snapshot_scope: {self.snapshot_scope}",
                f"- full_snapshot_row_count: {self.full_snapshot_row_count}",
                f"- excluded_snapshot_row_count: {self.excluded_snapshot_row_count}",
                f"- diagnostics: {len(self.diagnostics)}",
            ]
        )


@dataclass(frozen=True)
class MonthlyRevenueBackfillApplyResult:
    applied: bool
    inserted_count: int
    backup_file: Path | None
    plan: MonthlyRevenueBackfillPlan


def plan_monthly_revenue_backfill(
    *,
    raw_dir: Path,
    availability_file: Path,
    source_version: str,
) -> MonthlyRevenueBackfillPlan:
    availability_result = load_monthly_revenue_availability_overrides_csv(
        Path(availability_file)
    )
    if availability_result.diagnostics:
        return MonthlyRevenueBackfillPlan(
            records=(),
            diagnostics=availability_result.diagnostics,
            raw_row_count=0,
        )

    raw_rows = list(_iter_monthly_revenue_rows(Path(raw_dir)))
    parse_result = parse_monthly_revenue_rows(
        raw_rows,
        available_dates=availability_result.overrides,
        source_version=source_version,
    )
    return MonthlyRevenueBackfillPlan(
        records=parse_result.records,
        diagnostics=parse_result.diagnostics,
        raw_row_count=len(raw_rows),
    )


def plan_mops_snapshot_monthly_revenue_backfill(
    *,
    snapshot_file: Path,
    availability_file: Path,
    source_version: str,
    scope_manifest_file: Path | None = None,
) -> MonthlyRevenueBackfillPlan:
    snapshot = _load_mops_snapshot_rows(Path(snapshot_file))
    (
        snapshot_scope,
        full_snapshot_row_count,
        excluded_snapshot_row_count,
        scope_diagnostics,
    ) = _load_snapshot_scope_manifest(
        Path(scope_manifest_file) if scope_manifest_file is not None else None,
        snapshot_row_count=snapshot.raw_row_count,
        snapshot_file=Path(snapshot_file),
        snapshot_rows=snapshot.rows,
    )
    snapshot_source, source_diagnostics = _load_snapshot_source_contract(
        scope_manifest_file=(
            Path(scope_manifest_file) if scope_manifest_file is not None else None
        ),
        snapshot_file=Path(snapshot_file),
    )
    availability_result = load_monthly_revenue_availability_overrides_csv(
        Path(availability_file)
    )
    if availability_result.diagnostics:
        return MonthlyRevenueBackfillPlan(
            records=(),
            diagnostics=(
                tuple(snapshot.diagnostics)
                + scope_diagnostics
                + source_diagnostics
                + availability_result.diagnostics
            ),
            raw_row_count=snapshot.raw_row_count,
            snapshot_duplicate_row_count=snapshot.duplicate_row_count,
            snapshot_invalid_row_count=snapshot.invalid_row_count,
            snapshot_scope=snapshot_scope,
            full_snapshot_row_count=full_snapshot_row_count,
            excluded_snapshot_row_count=excluded_snapshot_row_count,
        )

    availability_keys = set(availability_result.overrides)
    mapped_rows = [
        row for row in snapshot.rows if (row["stock_id"], row["period"]) in availability_keys
    ]
    unmatched_mapping_count = sum(
        (row["stock_id"], row["period"]) not in availability_keys
        for row in snapshot.rows
    )
    diagnostics = (
        list(snapshot.diagnostics)
        + list(scope_diagnostics)
        + list(source_diagnostics)
    )
    if unmatched_mapping_count:
        sample = next(
            (
                f"{row['stock_id']}|{row['period']}"
                for row in snapshot.rows
                if (row["stock_id"], row["period"]) not in availability_keys
            ),
            "",
        )
        diagnostics.append(
            SourceDiagnostic(
                code="fundamental_availability.snapshot_mapping_incomplete",
                stock_code="",
                message=(
                    "MOPS snapshot rows without a governed availability mapping; "
                    f"unmatched_count={unmatched_mapping_count}; sample={sample}"
                ),
            )
        )

    session_available_dates = {
        row["__snapshot_session_available_date"]
        for row in mapped_rows
        if row.get("__snapshot_session_available_date")
    }
    for row in mapped_rows:
        session_available_date = row.get("__snapshot_session_available_date")
        override = availability_result.overrides[(row["stock_id"], row["period"])]
        if (
            session_available_date
            and session_available_date > override.available_date.isoformat()
        ):
            diagnostics.append(
                SourceDiagnostic(
                    code="fundamental_availability.snapshot_capture_after_available_date",
                    stock_code=row["stock_id"],
                    message=(
                        "MOPS snapshot value was captured after the mapping available_date; "
                        f"period={row['period']}; session_available_date={session_available_date}; "
                        f"mapped_available_date={override.available_date.isoformat()}"
                    ),
                )
            )

    if len(session_available_dates) > 1:
        diagnostics.append(
            SourceDiagnostic(
                code="fundamental_availability.snapshot_capture_date_inconsistent",
                stock_code="",
                message=(
                    "MOPS snapshot contains more than one capture date; "
                    f"session_available_dates={','.join(sorted(session_available_dates))}"
                ),
            )
        )

    parse_result = parse_monthly_revenue_rows(
        mapped_rows,
        available_dates=availability_result.overrides,
        source_version=source_version,
    )
    diagnostics.extend(parse_result.diagnostics)
    row_lineage = {
        (row["stock_id"], row["period"]): str(row.get("source_version") or "").strip()
        for row in mapped_rows
    }
    records = tuple(
        replace(
            record,
            source=snapshot_source or MOPS_MONTHLY_REVENUE_SNAPSHOT_SOURCE,
            source_version=_compose_snapshot_source_version(
                source_version,
                row_lineage.get((record.stock_code, record.period), ""),
            ),
        )
        for record in parse_result.records
    )
    return MonthlyRevenueBackfillPlan(
        records=records,
        diagnostics=tuple(diagnostics),
        raw_row_count=snapshot.raw_row_count,
        snapshot_duplicate_row_count=snapshot.duplicate_row_count,
        snapshot_unmatched_mapping_count=unmatched_mapping_count,
        snapshot_invalid_row_count=snapshot.invalid_row_count,
        snapshot_scope=snapshot_scope,
        full_snapshot_row_count=full_snapshot_row_count,
        excluded_snapshot_row_count=excluded_snapshot_row_count,
    )


def apply_monthly_revenue_backfill(
    *,
    db_file: Path,
    backup_dir: Path,
    raw_dir: Path,
    availability_file: Path,
    source_version: str,
    backup_file: Path | None = None,
) -> MonthlyRevenueBackfillApplyResult:
    plan = plan_monthly_revenue_backfill(
        raw_dir=raw_dir,
        availability_file=availability_file,
        source_version=source_version,
    )
    if not plan.ready_for_apply:
        return MonthlyRevenueBackfillApplyResult(
            applied=False,
            inserted_count=0,
            backup_file=None,
            plan=plan,
        )

    db_file = Path(db_file)
    backup_file = _create_consistent_sqlite_backup(
        db_file,
        Path(backup_dir),
        label="monthly_revenue_backfill",
        backup_file=backup_file,
    )
    if backup_file is None:
        raise FileNotFoundError(db_file)

    conn = sqlite3.connect(db_file, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        inserted_count = _insert_monthly_revenue_records(conn, plan.records)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return MonthlyRevenueBackfillApplyResult(
        applied=True,
        inserted_count=inserted_count,
        backup_file=backup_file,
        plan=plan,
    )


def apply_mops_snapshot_monthly_revenue_backfill(
    *,
    db_file: Path,
    backup_dir: Path,
    snapshot_file: Path,
    availability_file: Path,
    source_version: str,
    scope_manifest_file: Path | None = None,
    backup_file: Path | None = None,
) -> MonthlyRevenueBackfillApplyResult:
    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=snapshot_file,
        availability_file=availability_file,
        source_version=source_version,
        scope_manifest_file=scope_manifest_file,
    )
    if not plan.ready_for_apply:
        return MonthlyRevenueBackfillApplyResult(
            applied=False,
            inserted_count=0,
            backup_file=None,
            plan=plan,
        )

    if not plan.formal_apply_eligible:
        blocked_plan = replace(
            plan,
            formal_apply_blocked_reason=(
                "research-only OpenAPI candidate has no hash-bound source/unit "
                "acceptance receipt; formal apply is not authorized"
            ),
        )
        return MonthlyRevenueBackfillApplyResult(
            applied=False,
            inserted_count=0,
            backup_file=None,
            plan=blocked_plan,
        )

    db_file = Path(db_file)
    backup_file = _create_consistent_sqlite_backup(
        db_file,
        Path(backup_dir),
        label="mops_monthly_revenue_backfill",
        backup_file=backup_file,
    )
    if backup_file is None:
        raise FileNotFoundError(db_file)

    conn = sqlite3.connect(db_file, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        inserted_count = _insert_monthly_revenue_records(conn, plan.records)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return MonthlyRevenueBackfillApplyResult(
        applied=True,
        inserted_count=inserted_count,
        backup_file=backup_file,
        plan=plan,
    )


def _create_consistent_sqlite_backup(
    db_file: Path,
    backup_dir: Path,
    *,
    label: str,
    backup_file: Path | None = None,
) -> Path | None:
    """以 SQLite online backup 建立唯一備份，不清理既有任務備份。"""

    db_file = Path(db_file)
    if not db_file.is_file():
        return None
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_file = Path(backup_file) if backup_file is not None else (
        backup_dir
        / f"{db_file.stem}_{label}_{timestamp}_{uuid4().hex}.db"
    )
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    if backup_file.exists():
        raise FileExistsError(backup_file)
    source: sqlite3.Connection | None = None
    destination: sqlite3.Connection | None = None
    failure: Exception | None = None
    try:
        source = sqlite3.connect(
            f"file:{db_file.as_posix()}?mode=ro",
            uri=True,
            timeout=30,
        )
        source.execute("PRAGMA busy_timeout=30000")
        destination = sqlite3.connect(backup_file, timeout=30)
        destination.execute("PRAGMA busy_timeout=30000")
        source.backup(destination, pages=256, sleep=0.1)
        destination.commit()
    except Exception as exc:
        failure = exc
    finally:
        if destination is not None:
            try:
                destination.close()
            except Exception as exc:
                if failure is None:
                    failure = exc
        if source is not None:
            try:
                source.close()
            except Exception as exc:
                if failure is None:
                    failure = exc
    if failure is not None:
        try:
            if backup_file.exists():
                backup_file.unlink()
        except OSError:
            # Windows 可能仍保留一個無法立即刪除的 partial backup；
            # 不覆蓋原始 backup 失敗，留待任務清理流程處理。
            pass
        raise failure.with_traceback(failure.__traceback__)

    verification: sqlite3.Connection | None = None
    verification_failure: Exception | None = None
    try:
        verification = sqlite3.connect(
            f"file:{backup_file.as_posix()}?mode=ro",
            uri=True,
        )
        verification.execute("PRAGMA query_only=ON")
        quick_check = verification.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(
                f"SQLite backup quick_check failed: {backup_file}"
            )
    except Exception as exc:
        verification_failure = exc
    finally:
        if verification is not None:
            try:
                verification.close()
            except Exception as exc:
                if verification_failure is None:
                    verification_failure = exc
    if verification_failure is not None:
        try:
            if backup_file.exists():
                backup_file.unlink()
        except OSError:
            pass
        raise verification_failure.with_traceback(
            verification_failure.__traceback__
        )
    return backup_file


def reserve_monthly_revenue_sqlite_backup_path(
    db_file: Path,
    backup_dir: Path,
    *,
    label: str,
) -> Path | None:
    """預留本任務 SQLite 備份路徑；不建立資料庫副本。"""

    db_file = Path(db_file)
    if not db_file.is_file():
        return None
    backup_dir = Path(backup_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backup_dir / f"{db_file.stem}_{label}_{timestamp}_{uuid4().hex}.db"


def _load_snapshot_scope_manifest(
    manifest_file: Path | None,
    *,
    snapshot_row_count: int,
    snapshot_file: Path,
    snapshot_rows: tuple[dict[str, str], ...],
) -> tuple[str, int, int, tuple[SourceDiagnostic, ...]]:
    """讀取 accepted scope manifest，將 partial 邊界固定在可稽核分母。"""

    if manifest_file is None:
        return "complete", snapshot_row_count, 0, ()

    path = Path(manifest_file)
    diagnostics: list[SourceDiagnostic] = []
    try:
        manifest_bytes = _read_source_contract_file(path.parent, path.name)
        payload = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                f"snapshot scope manifest cannot be read; path={path}; error={exc}"
            )
        )
        return "complete", snapshot_row_count, 0, tuple(diagnostics)

    if not isinstance(payload, dict):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest must contain a JSON object"
            )
        )
        return "complete", snapshot_row_count, 0, tuple(diagnostics)

    candidate_rows = payload.get("candidate_rows")
    mapping_rows = payload.get("mapping_rows")
    accepted_rows = payload.get("accepted_rows")
    excluded_rows = payload.get("excluded_rows")
    excluded_keys = payload.get("excluded_keys")
    integer_values = (candidate_rows, mapping_rows, accepted_rows, excluded_rows)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in integer_values
    ):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest row counts must be non-negative integers"
            )
        )
        return "complete", snapshot_row_count, 0, tuple(diagnostics)
    assert isinstance(candidate_rows, int)
    assert isinstance(mapping_rows, int)
    assert isinstance(accepted_rows, int)
    assert isinstance(excluded_rows, int)
    if accepted_rows != snapshot_row_count:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "accepted scope row count does not match the supplied snapshot; "
                f"manifest={accepted_rows}; snapshot={snapshot_row_count}"
            )
        )
    if mapping_rows != accepted_rows:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest mapping_rows does not match accepted_rows; "
                f"mapping={mapping_rows}; accepted={accepted_rows}"
            )
        )
    if candidate_rows != accepted_rows + excluded_rows:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest denominator is inconsistent; "
                f"candidate={candidate_rows}; accepted={accepted_rows}; "
                f"excluded={excluded_rows}"
            )
        )
    if not isinstance(excluded_keys, list) or any(
        not isinstance(value, str) or not value.strip()
        for value in excluded_keys
    ):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest excluded_keys must be non-empty strings"
            )
        )
    elif len(excluded_keys) != excluded_rows or len(set(excluded_keys)) != len(
        excluded_keys
    ):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest excluded_keys count or uniqueness is invalid"
            )
        )

    candidate_file = _resolve_scope_candidate_file(
        payload.get("candidate_file"),
        manifest_path=path,
    )
    candidate_file_sha256 = payload.get("candidate_file_sha256")
    accepted_file_sha256 = payload.get("accepted_file_sha256")
    candidate_key_sha256 = payload.get("candidate_key_sha256")
    accepted_key_sha256 = payload.get("accepted_key_sha256")
    excluded_key_sha256 = payload.get("excluded_key_sha256")
    for field_name, value in (
        ("candidate_file_sha256", candidate_file_sha256),
        ("accepted_file_sha256", accepted_file_sha256),
        ("candidate_key_sha256", candidate_key_sha256),
        ("accepted_key_sha256", accepted_key_sha256),
        ("excluded_key_sha256", excluded_key_sha256),
    ):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
            diagnostics.append(
                _snapshot_scope_diagnostic(
                    f"snapshot scope manifest {field_name} must be a SHA-256 digest"
                )
            )

    accepted_keys = {
        f"{row['stock_id']}|{row['period']}" for row in snapshot_rows
    }
    excluded_key_set = (
        set(excluded_keys)
        if isinstance(excluded_keys, list)
        and all(isinstance(value, str) for value in excluded_keys)
        else set()
    )
    if accepted_key_set := accepted_keys & excluded_key_set:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest accepted and excluded keys overlap; "
                f"sample={sorted(accepted_key_set)[0]}"
            )
        )

    accepted_digest = _snapshot_key_digest(accepted_keys)
    if isinstance(accepted_key_sha256, str) and accepted_key_sha256.lower() != accepted_digest:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope accepted key digest does not match supplied snapshot"
            )
        )
    excluded_digest = _snapshot_key_digest(excluded_key_set)
    if isinstance(excluded_key_sha256, str) and excluded_key_sha256.lower() != excluded_digest:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope excluded key digest does not match manifest"
            )
        )
    actual_accepted_file_sha256 = _sha256_file(snapshot_file)
    if (
        isinstance(accepted_file_sha256, str)
        and actual_accepted_file_sha256 != accepted_file_sha256.lower()
    ):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope accepted file digest does not match supplied snapshot"
            )
        )

    candidate_keys: set[str] = set()
    candidate_file_keys: tuple[str, ...] = ()
    if candidate_file is None:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope manifest candidate_file is missing or unreadable"
            )
        )
    else:
        try:
            candidate_file_keys = _read_snapshot_keys(candidate_file)
            candidate_keys = set(candidate_file_keys)
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            diagnostics.append(
                _snapshot_scope_diagnostic(
                    f"snapshot scope candidate file cannot be read; error={exc}"
                )
            )
        actual_candidate_file_sha256 = _sha256_file(candidate_file)
        if (
            isinstance(candidate_file_sha256, str)
            and actual_candidate_file_sha256 != candidate_file_sha256.lower()
        ):
            diagnostics.append(
                _snapshot_scope_diagnostic(
                    "snapshot scope candidate file digest does not match manifest"
                )
            )
    if candidate_file_keys and len(candidate_file_keys) != candidate_rows:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope candidate file row count does not match manifest; "
                f"file={len(candidate_file_keys)}; manifest={candidate_rows}"
            )
        )
    candidate_digest = _snapshot_key_digest(candidate_keys)
    if (
        isinstance(candidate_key_sha256, str)
        and candidate_key_sha256.lower() != candidate_digest
    ):
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope candidate key digest does not match candidate file"
            )
        )
    if candidate_keys and candidate_keys != accepted_keys | excluded_key_set:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope candidate keys do not equal accepted plus excluded keys"
            )
        )
    if candidate_keys and len(candidate_keys) != candidate_rows:
        diagnostics.append(
            _snapshot_scope_diagnostic(
                "snapshot scope candidate key set contains duplicate or invalid keys"
            )
        )

    if diagnostics:
        return "complete", snapshot_row_count, 0, tuple(diagnostics)
    scope = "partial" if excluded_rows else "complete"
    return scope, candidate_rows, excluded_rows, ()


def _resolve_scope_candidate_file(
    value: object,
    *,
    manifest_path: Path,
) -> Path | None:
    """解析 scope manifest 的完整 candidate 路徑，不猜測其他資料源。"""

    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    relative_to_manifest = manifest_path.parent / candidate
    if relative_to_manifest.is_file():
        return relative_to_manifest
    relative_to_cwd = Path.cwd() / candidate
    if relative_to_cwd.is_file():
        return relative_to_cwd
    return None


def _read_snapshot_keys(path: Path) -> tuple[str, ...]:
    """讀取完整 snapshot 的自然鍵，保留重複以供分母檢查。"""

    keys: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stock_code = (row.get("stock_code") or "").strip()
            period = (row.get("period") or "").strip()
            if not stock_code or not period:
                raise ValueError("candidate snapshot row is missing stock_code or period")
            keys.append(f"{stock_code}|{period}")
    return tuple(keys)


def _snapshot_key_digest(keys: set[str]) -> str:
    """以排序自然鍵建立 scope 的可重算 digest。"""

    payload = "\n".join(sorted(keys)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str | None:
    """計算 scope 檔案內容 hash；讀取失敗時回傳空值。"""

    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _snapshot_scope_diagnostic(message: str) -> SourceDiagnostic:
    return SourceDiagnostic(
        code="fundamental_revenue.snapshot_scope_manifest_invalid",
        stock_code="",
        message=message,
    )


def _load_snapshot_source_contract(
    *,
    scope_manifest_file: Path | None,
    snapshot_file: Path,
) -> tuple[str | None, tuple[SourceDiagnostic, ...]]:
    """Validate snapshot provenance before assigning the persisted source.

    Legacy static MOPS snapshots retain their historical source identity.  A
    non-legacy source must use the explicit, versioned TWSE+TPEx contract and
    prove its raw source bytes, capture metadata, row scope, and row lineage.
    """

    try:
        snapshot_rows = _read_snapshot_source_rows(snapshot_file)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        return None, (
            _snapshot_scope_diagnostic(
                f"snapshot source lineage cannot be read; error={exc}"
            ),
        )

    observed_sources = {
        str(row.get("source", "")).strip() for row in snapshot_rows
    }
    legacy_static_source_only = bool(snapshot_rows) and observed_sources == {
        MOPS_MONTHLY_REVENUE_SNAPSHOT_SOURCE
    }
    if scope_manifest_file is None:
        if not legacy_static_source_only:
            return None, (
                _snapshot_scope_diagnostic(
                    "snapshot has a missing or non-legacy source without a validated source contract"
                ),
            )
        return None, ()

    try:
        manifest_path = Path(scope_manifest_file)
        manifest_bytes = _read_source_contract_file(
            manifest_path.parent,
            manifest_path.name,
        )
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return None, (
            _snapshot_scope_diagnostic(
                f"snapshot source contract manifest cannot be read; error={exc}"
            ),
        )
    if not isinstance(manifest, dict):
        return None, (
            _snapshot_scope_diagnostic(
                "snapshot source contract manifest must be a JSON object"
            ),
        )

    contract = manifest.get("source_contract")
    if contract is None:
        if not legacy_static_source_only:
            return None, (
                _snapshot_scope_diagnostic(
                    "snapshot source requires an explicit, versioned source contract"
                ),
            )
        return None, ()
    try:
        return (
            _validate_openapi_research_source_contract(
                contract=contract,
                manifest=manifest,
                scope_manifest_file=Path(scope_manifest_file),
                snapshot_file=Path(snapshot_file),
                snapshot_rows=snapshot_rows,
            ),
            (),
        )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        return None, (
            _snapshot_scope_diagnostic(
                f"snapshot source contract is invalid; error={exc}"
            ),
        )


def _read_snapshot_source_rows(snapshot_file: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with Path(snapshot_file).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({str(key): str(value or "").strip() for key, value in row.items()})
    return rows


def _validate_openapi_research_source_contract(
    *,
    contract: object,
    manifest: Mapping[str, Any],
    scope_manifest_file: Path,
    snapshot_file: Path,
    snapshot_rows: list[dict[str, str]],
) -> str:
    if not isinstance(contract, Mapping):
        raise ValueError("source_contract must be an object")
    if (
        manifest.get("schema_version") != _RESEARCH_SOURCE_SCOPE_SCHEMA
        or contract.get("schema_version") != _RESEARCH_SOURCE_CONTRACT_SCHEMA
        or contract.get("contract_id") != _RESEARCH_SOURCE_CONTRACT_ID
        or contract.get("composite_source") != _RESEARCH_COMPOSITE_SOURCE
        or manifest.get("owner_acceptance") is not False
        or manifest.get("formal_apply_authorized") is not False
        or manifest.get("historical_pit_credit") is not False
    ):
        raise ValueError("source contract version, scope, or research-only claims are invalid")

    period = str(contract.get("candidate_period") or "")
    period_match = re.fullmatch(r"(?P<year>\d{4})-(?P<month>\d{2})", period)
    if period_match is None:
        raise ValueError("source contract period must be YYYY-MM")
    year = int(period_match.group("year"))
    month = int(period_match.group("month"))
    if year < 1912 or not 1 <= month <= 12:
        raise ValueError("source contract period is outside ROC calendar bounds")
    roc_period = f"{year - 1911:03d}{month:02d}"
    scope = manifest.get("source_scope")
    if not isinstance(scope, Mapping) or scope.get("period") != period:
        raise ValueError("source contract period does not match full-scope manifest")

    source_contracts = contract.get("venues")
    if not isinstance(source_contracts, Mapping) or set(source_contracts) != set(
        _RESEARCH_SOURCE_VENUES
    ):
        raise ValueError("source contract must declare exactly the TWSE and TPEx venues")
    capture_relative = str(contract.get("capture_manifest_file") or "")
    if capture_relative != _RESEARCH_CAPTURE_MANIFEST_FILE:
        raise ValueError("source contract capture manifest path is outside the allowed layout")
    capture_bytes = _read_source_contract_file(
        scope_manifest_file.parent,
        capture_relative,
    )
    capture_sha256 = hashlib.sha256(capture_bytes).hexdigest()
    if contract.get("capture_manifest_sha256") != capture_sha256:
        raise ValueError("source contract capture manifest hash does not match")
    try:
        capture = json.loads(capture_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("source capture manifest is invalid JSON") from exc
    if (
        not isinstance(capture, Mapping)
        or capture.get("schema_version") != "monthly-revenue-openapi-capture.v1"
        or capture.get("status") != "captured"
        or capture.get("requested_period") != period
        or not isinstance(capture.get("results"), Mapping)
    ):
        raise ValueError("source capture manifest version, status, or period is invalid")

    source_rows_by_venue: dict[str, dict[str, Mapping[str, Any]]] = {}
    expected_snapshot_row_counts: dict[str, int] = {}
    latest_capture_at: datetime | None = None
    capture_results = capture["results"]
    for venue, expected in _RESEARCH_SOURCE_VENUES.items():
        venue_contract = source_contracts.get(venue)
        if not isinstance(venue_contract, Mapping):
            raise ValueError(f"source contract entry is missing: {venue}")
        if (
            venue_contract.get("source") != expected["source"]
            or venue_contract.get("source_id") != expected["source_id"]
            or venue_contract.get("raw_file") != expected["raw_file"]
        ):
            raise ValueError(f"source identity is not allowed for venue: {venue}")
        raw_bytes = _read_source_contract_file(
            scope_manifest_file.parent,
            expected["raw_file"],
        )
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        if (
            venue_contract.get("raw_sha256") != raw_sha256
            or venue_contract.get("raw_bytes") != len(raw_bytes)
            or venue_contract.get("source_version")
            != f"{expected['source_id']}-{roc_period}-sha256-{raw_sha256}"
        ):
            raise ValueError(f"source raw hash, size, or version differs: {venue}")
        try:
            raw_payload = json.loads(raw_bytes.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"source raw JSON is invalid: {venue}") from exc
        if not isinstance(raw_payload, list) or not raw_payload:
            raise ValueError(f"source raw rows are empty or invalid: {venue}")

        capture_entry = capture_results.get(venue)
        if not isinstance(capture_entry, Mapping):
            raise ValueError(f"source capture metadata is missing: {venue}")
        period_row_count_key = f"rows_for_{period.replace('-', '_')}"
        if (
            capture_entry.get("status") != "captured"
            or capture_entry.get("http_status") != 200
            or capture_entry.get("requested_url") != expected["url"]
            or capture_entry.get("final_url") != expected["url"]
            or capture_entry.get("content_sha256") != raw_sha256
            or capture_entry.get("content_bytes") != len(raw_bytes)
            or capture_entry.get("json_row_count") != len(raw_payload)
            or capture_entry.get(period_row_count_key) != len(raw_payload)
            or roc_period
            not in {
                str(value).strip()
                for value in (capture_entry.get("period_values_sample") or [])
            }
        ):
            raise ValueError(f"source capture receipt does not match raw rows: {venue}")
        capture_at = _parse_contract_timestamp(
            capture_entry.get("observed_at_utc"),
            f"{venue}.observed_at_utc",
        )
        latest_capture_at = (
            capture_at
            if latest_capture_at is None
            else max(latest_capture_at, capture_at)
        )
        if venue_contract.get("captured_at_utc") != capture_entry.get("observed_at_utc"):
            raise ValueError(f"source capture timestamp is not bound to its receipt: {venue}")

        raw_by_code: dict[str, Mapping[str, Any]] = {}
        for row in raw_payload:
            if not isinstance(row, Mapping):
                raise ValueError(f"source row is not an object: {venue}")
            stock_code = str(row.get("公司代號") or "").strip()
            if (
                row.get("資料年月") != roc_period
                or not re.fullmatch(r"\d{4,6}", stock_code)
                or stock_code in raw_by_code
            ):
                raise ValueError(f"source row period or key is invalid: {venue}")
            raw_by_code[stock_code] = row
        if venue_contract.get("row_count") != len(raw_by_code):
            raise ValueError(f"source contract row count differs: {venue}")
        if scope.get(f"{venue}_row_count") != len(raw_by_code):
            raise ValueError(f"full-scope row count differs from source contract: {venue}")
        source_rows_by_venue[venue] = raw_by_code
        expected_snapshot_row_counts[venue] = len(raw_by_code)

    candidate_available_at = _parse_contract_timestamp(
        contract.get("candidate_available_at_utc"),
        "candidate_available_at_utc",
    )
    if latest_capture_at is None or candidate_available_at < latest_capture_at:
        raise ValueError("candidate availability predates source capture completion")

    if not snapshot_rows or set(_RESEARCH_SOURCE_VENUES) != {
        str(row.get("market", "")).strip() for row in snapshot_rows
    }:
        raise ValueError("snapshot must contain both allowed source venues")
    source_version_by_venue = {
        venue: str(source_contracts[venue].get("source_version") or "")
        for venue in _RESEARCH_SOURCE_VENUES
    }
    seen_keys: set[tuple[str, str]] = set()
    seen_mapping_keys: set[tuple[str, str]] = set()
    actual_counts: dict[str, int] = {venue: 0 for venue in _RESEARCH_SOURCE_VENUES}
    raw_to_snapshot_fields = _RESEARCH_SNAPSHOT_SOURCE_FIELD_MAP
    for snapshot_row in snapshot_rows:
        venue = str(snapshot_row.get("market", "")).strip()
        stock_code = str(snapshot_row.get("stock_code", "")).strip()
        key = (venue, stock_code)
        if (
            venue not in _RESEARCH_SOURCE_VENUES
            or key in seen_keys
            or (stock_code, period) in seen_mapping_keys
            or snapshot_row.get("period") != period
            or snapshot_row.get("source") != _RESEARCH_SOURCE_VENUES[venue]["source"]
            or snapshot_row.get("source_version") != source_version_by_venue[venue]
        ):
            raise ValueError("snapshot contains an unknown, mixed, or duplicate source identity")
        raw_row = source_rows_by_venue[venue].get(stock_code)
        if raw_row is None:
            raise ValueError(f"snapshot key is absent from the official raw source: {venue}:{stock_code}")
        expected_capture_at = str(source_contracts[venue].get("captured_at_utc"))
        if snapshot_row.get("fetched_at") != expected_capture_at:
            raise ValueError(f"snapshot capture timestamp differs from raw source: {venue}:{stock_code}")
        for snapshot_field, raw_field in raw_to_snapshot_fields.items():
            if snapshot_row.get(snapshot_field, "") != str(raw_row.get(raw_field) or "").strip():
                raise ValueError(f"snapshot value differs from official raw source: {venue}:{stock_code}:{snapshot_field}")
        seen_keys.add(key)
        seen_mapping_keys.add((stock_code, period))
        actual_counts[venue] += 1
    if actual_counts != expected_snapshot_row_counts:
        raise ValueError("snapshot venue row counts do not equal complete official source counts")
    return _RESEARCH_COMPOSITE_SOURCE


def _read_source_contract_file(root: Path, relative_text: str) -> bytes:
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("source contract path must be a safe relative path")
    root_path = _absolute_path_without_links(Path(root))
    try:
        root_stat = root_path.lstat()
        candidate = Path(os.path.abspath(os.fspath(root_path.joinpath(*relative.parts))))
        candidate.relative_to(root_path)
        candidate_path = _absolute_path_without_links(candidate)
        path_stat = candidate_path.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("source contract file escaped its manifest root") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("source contract manifest root is not a directory")
    if not _is_bounded_single_link_file(path_stat):
        raise ValueError("source contract file is not a bounded single-link regular file")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(os.fspath(candidate_path), flags)
    try:
        before_stat = os.fstat(file_descriptor)
        if (
            not _is_bounded_single_link_file(before_stat)
            or _stat_fingerprint(before_stat) != _stat_fingerprint(path_stat)
        ):
            raise ValueError("source contract file changed before it was read")

        chunks: list[bytes] = []
        remaining = _MAX_SOURCE_CONTRACT_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(file_descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > _MAX_SOURCE_CONTRACT_FILE_BYTES:
            raise ValueError("source contract file exceeds the bounded read limit")

        after_stat = os.fstat(file_descriptor)
        path_after_stat = candidate_path.lstat()
        root_after_stat = root_path.lstat()
        _absolute_path_without_links(root_path)
        _absolute_path_without_links(candidate_path)
        if (
            len(data) != before_stat.st_size
            or _stat_fingerprint(after_stat) != _stat_fingerprint(before_stat)
            or _stat_fingerprint(path_after_stat) != _stat_fingerprint(before_stat)
            or _directory_identity(root_after_stat) != _directory_identity(root_stat)
        ):
            raise ValueError("source contract file changed while it was read")
        return data
    finally:
        os.close(file_descriptor)


def _absolute_path_without_links(path: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise ValueError("source contract path has a linked component")
    return absolute


def _is_bounded_single_link_file(file_stat: os.stat_result) -> bool:
    return (
        stat.S_ISREG(file_stat.st_mode)
        and file_stat.st_nlink == 1
        and 0 < file_stat.st_size <= _MAX_SOURCE_CONTRACT_FILE_BYTES
    )


def _stat_fingerprint(
    file_stat: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
        file_stat.st_nlink,
    )


def _directory_identity(directory_stat: os.stat_result) -> tuple[int, int, int]:
    return (directory_stat.st_dev, directory_stat.st_ino, directory_stat.st_mode)


def _parse_contract_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source contract timestamp is missing: {field}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"source contract timestamp is invalid: {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"source contract timestamp is not timezone-aware: {field}")
    return parsed.astimezone(timezone.utc)


def _iter_monthly_revenue_rows(raw_dir: Path) -> Iterable[dict[str, str]]:
    for csv_path in sorted(Path(raw_dir).glob("*_monthly_revenue.csv")):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            yield from reader


def _iter_mops_snapshot_rows(
    snapshot_file: Path,
    *,
    availability_keys: set[tuple[str, str]] | None = None,
) -> Iterable[dict[str, str]]:
    with Path(snapshot_file).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            stock_code = (row.get("stock_code") or "").strip()
            period = (row.get("period") or "").strip()
            if availability_keys is not None and (stock_code, period) not in availability_keys:
                continue
            yield _snapshot_row_to_revenue_row(row)


@dataclass(frozen=True)
class _MopsSnapshotRows:
    rows: tuple[dict[str, str], ...]
    raw_row_count: int
    duplicate_row_count: int
    invalid_row_count: int
    diagnostics: tuple[SourceDiagnostic, ...] = ()


def _load_mops_snapshot_rows(snapshot_file: Path) -> _MopsSnapshotRows:
    rows: list[dict[str, str]] = []
    diagnostics: list[SourceDiagnostic] = []
    seen_keys: set[tuple[str, str]] = set()
    raw_row_count = 0
    duplicate_row_count = 0
    invalid_row_count = 0
    with Path(snapshot_file).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for source_row in reader:
            raw_row_count += 1
            try:
                row = _snapshot_row_to_revenue_row(source_row)
            except (TypeError, ValueError, KeyError) as exc:
                invalid_row_count += 1
                diagnostics.append(
                    SourceDiagnostic(
                        code="fundamental_revenue.snapshot_invalid_row",
                        stock_code=str(source_row.get("stock_code") or "").strip(),
                        message=f"MOPS snapshot row is invalid; error={exc}",
                    )
                )
                continue
            key = (row["stock_id"], row["period"])
            if key in seen_keys:
                duplicate_row_count += 1
                continue
            seen_keys.add(key)
            rows.append(row)
    if duplicate_row_count:
        diagnostics.append(
            SourceDiagnostic(
                code="fundamental_revenue.snapshot_duplicate_rows",
                stock_code="",
                message=(
                    "MOPS snapshot has duplicate (stock_code, period) rows; "
                    f"duplicate_count={duplicate_row_count}"
                ),
            )
        )
    return _MopsSnapshotRows(
        rows=tuple(rows),
        raw_row_count=raw_row_count,
        duplicate_row_count=duplicate_row_count,
        invalid_row_count=invalid_row_count,
        diagnostics=tuple(diagnostics),
    )


def _snapshot_row_to_revenue_row(source_row: dict[str, str]) -> dict[str, str]:
    stock_code = (source_row.get("stock_code") or "").strip()
    period = (source_row.get("period") or "").strip()
    if not re.fullmatch(r"\d{4,6}", stock_code):
        raise ValueError("invalid stock_code")
    year_text, month_text = period.split("-", maxsplit=1)
    year = int(year_text)
    month = int(month_text)
    if f"{year:04d}-{month:02d}" != period or month < 1 or month > 12:
        raise ValueError("invalid period")
    revenue = (source_row.get("current_month_revenue") or "").strip()
    if not revenue:
        raise ValueError("missing current_month_revenue")
    fetched_at = (source_row.get("fetched_at") or "").strip()
    if not fetched_at:
        raise ValueError("missing fetched_at")
    session_available_date = _snapshot_session_available_date(fetched_at)
    row_source_version = (source_row.get("source_version") or "").strip()
    if not row_source_version:
        raise ValueError("missing source_version")
    return {
        "date": _raw_date_from_period(period),
        "stock_id": stock_code,
        "country": "Taiwan",
        "revenue": revenue,
        "revenue_month": str(month),
        "revenue_year": str(year),
        "period": period,
        "__snapshot_session_available_date": session_available_date.isoformat(),
        "source_version": row_source_version,
    }


def _compose_snapshot_source_version(batch_source_version: str, row_source_version: str) -> str:
    """保留批次身份與每個市場／期別 HTML 內容 lineage。"""
    batch = batch_source_version.strip()
    lineage = row_source_version.strip()
    if not batch:
        raise ValueError("missing batch source_version")
    if not lineage:
        raise ValueError("missing snapshot source_version lineage")
    if lineage == batch:
        return batch
    return f"{batch}|snapshot={lineage}"


def _insert_monthly_revenue_records(
    conn: sqlite3.Connection,
    records: tuple[MonthlyRevenueRecord, ...],
) -> int:
    # 保留不同 source_version 的歷史內容；相同 source_version 由主鍵上的
    # INSERT OR REPLACE 維持冪等，provider 再以獨立 mapping 選取可用版本。
    conn.executemany(
        """
        INSERT OR REPLACE INTO fundamental_monthly_revenues(
            stock_code, period, as_of_date, announced_date, available_date,
            revenue, source, source_version, quality
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.stock_code,
                record.period,
                record.as_of_date.isoformat(),
                record.announced_date.isoformat() if record.announced_date else None,
                record.available_date.isoformat(),
                str(record.revenue),
                record.source,
                record.source_version,
                legacy_monthly_revenue_quality_value(record),
            )
            for record in records
        ],
    )
    return len(records)


def _raw_date_from_period(period: str) -> str:
    year_text, month_text = period.split("-", maxsplit=1)
    year = int(year_text)
    month = int(month_text) + 1
    if month == 13:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}-01"
