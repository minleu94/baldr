"""Strict natural-maturity session resolver for the recommendation learning lane.

這個模組只負責把「N 個官方預定交易 session」與唯讀 TAIEX 收盤觀測
對齊。它不使用個股 row count 推算 horizon，也不把缺少的中間日期壓縮到
下一筆觀測。個股 endpoint 仍須由 caller 以同一個 ``endpoint_date`` 精確
查詢；本模組提供可驗證的官方 calendar／TAIEX proof 給 natural evidence
consumer 綁定。

所有正式來源都以 bounded SQLite ``mode=ro``／``PRAGMA query_only`` 讀取。
官方 annual cache 的 freshness 與 raw/content hash 由既有 cache loader 重驗；
temporary closure cache 若 caller 有配置但缺件或失效，resolver 會停在
``waiting_for_calendar``。沒有 temporary closure cache 時，proof 明確標示
``annual_plan_only``，不把它升格成完整的未來官方 calendar。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from data_module.official_trading_calendar_cache import (
    OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
    OfficialCalendarCacheError,
    VerifiedOfficialCalendarCache,
    VerifiedTemporaryClosureCache,
    load_verified_twse_calendar_cache,
    load_verified_twse_temporary_closure_cache,
)


NATURAL_MATURITY_SESSION_RESOLVER_ID = "natural-maturity-official-session"
NATURAL_MATURITY_SESSION_RESOLVER_VERSION = "natural-maturity-session.v1"
SESSION_PROOF_SCHEMA_VERSION = "natural-maturity-session-proof.v1"
TAIEX_INDEX_NAME = "TAIEX"
TAIEX_SOURCE_TABLE = "market_indices"
TAIEX_CLOSE_TIME = time(14, 30)
TAIEX_TIMEZONE = "Asia/Taipei"
MAX_HORIZON_SESSIONS = 3_660
MAX_SCAN_DAYS = 12_000
MAX_CACHE_CANDIDATES = 64
_TAIPEI = ZoneInfo(TAIEX_TIMEZONE)
_UTC = timezone.utc


class NaturalMaturitySessionResolverError(ValueError):
    """Session proof or source contract is invalid."""


@dataclass(frozen=True)
class SessionResolution:
    """Bounded official-session resolution returned to natural learning."""

    status: str
    reason: str
    capture_date: str
    evaluation_at: str
    horizon_sessions: int
    endpoint_date: str | None
    session_dates: tuple[str, ...]
    observed_session_dates: tuple[str, ...]
    missing_session_dates: tuple[str, ...]
    proof: Mapping[str, Any] | None = None
    resolver_id: str = NATURAL_MATURITY_SESSION_RESOLVER_ID
    resolver_version: str = NATURAL_MATURITY_SESSION_RESOLVER_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"ready", "pending", "waiting_for_calendar"}:
            raise ValueError("unsupported natural maturity session status")
        if self.horizon_sessions <= 0:
            raise ValueError("horizon_sessions must be positive")
        if self.resolver_id != NATURAL_MATURITY_SESSION_RESOLVER_ID:
            raise ValueError("resolver id mismatch")
        if self.resolver_version != NATURAL_MATURITY_SESSION_RESOLVER_VERSION:
            raise ValueError("resolver version mismatch")

    @property
    def resolution_hash(self) -> str | None:
        """Return the immutable proof hash when this result has a proof."""

        if not isinstance(self.proof, Mapping):
            return None
        value = self.proof.get("proof_hash")
        return str(value) if value else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "natural-maturity-session-resolution.v1",
            "status": self.status,
            "reason": self.reason,
            "capture_date": self.capture_date,
            "evaluation_at": self.evaluation_at,
            "horizon_sessions": self.horizon_sessions,
            "endpoint_date": self.endpoint_date,
            "session_dates": list(self.session_dates),
            "observed_session_dates": list(self.observed_session_dates),
            "missing_session_dates": list(self.missing_session_dates),
            "resolver_id": self.resolver_id,
            "resolver_version": self.resolver_version,
            "resolution_hash": self.resolution_hash,
            "proof": dict(self.proof) if isinstance(self.proof, Mapping) else None,
        }


@dataclass(frozen=True)
class _TAIEXObservation:
    date_text: str
    close_text: str
    close_index_text: str | None
    close_price_text: str | None
    available_at: str
    row_hash: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "date": self.date_text,
            "index_name": TAIEX_INDEX_NAME,
            "source_table": TAIEX_SOURCE_TABLE,
            "close": self.close_text,
            "close_index": self.close_index_text,
            "close_price": self.close_price_text,
            "available_at": self.available_at,
            "row_hash": self.row_hash,
        }


class NaturalMaturitySessionResolver:
    """Resolve an exact official session endpoint from immutable source evidence."""

    def __init__(
        self,
        db_path: str | Path,
        calendar_cache_path: str | Path,
        temporary_closure_path: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.calendar_cache_path = Path(calendar_cache_path).expanduser().resolve()
        self.temporary_closure_path = (
            None
            if temporary_closure_path is None
            else Path(temporary_closure_path).expanduser().resolve()
        )
        self._annual: dict[int, VerifiedOfficialCalendarCache | None] = {}
        self._annual_errors: dict[int, str] = {}
        self._temporary_loaded = False
        self._temporary: dict[date, VerifiedTemporaryClosureCache] = {}
        self._temporary_error: str | None = None

    def resolve(
        self,
        capture_date: str,
        evaluation_at: datetime,
        horizon_sessions: int = 20,
    ) -> SessionResolution:
        """Resolve the exact endpoint without compressing missing sessions."""

        capture = _parse_date(capture_date, "capture_date")
        evaluation = _parse_aware_datetime(evaluation_at, "evaluation_at")
        horizon = _positive_horizon(horizon_sessions)
        if evaluation.astimezone(_TAIPEI).date() < capture:
            raise ValueError("evaluation_at must not precede capture_date")

        # 每次 resolution 都以該次 evaluation 的觀測時間重新驗證 cache；
        # 不沿用較早 evaluation 的 annual／temporary 結果。
        self._reset_resolution_cache()

        scan_end = capture + timedelta(
            days=min(MAX_SCAN_DAYS, max(366, horizon * 3 + 31))
        )
        # DB 查詢不得讀取 evaluation_at 之後的市場列，避免未來資料
        # 的 malformed／duplicate 狀態回頭改寫較早的自然成熟判定。
        observation_end = min(
            scan_end,
            _visible_market_end(evaluation),
        )
        source = self._read_taiex_observations(
            start_date=capture,
            end_date=observation_end,
        )
        if source["status"] != "ready":
            return self._result(
                status="pending",
                reason=str(source["reason"]),
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(),
                proof=None,
            )

        observations = source["observations"]
        assert isinstance(observations, tuple)
        observation_by_date = {item.date_text: item for item in observations}
        baseline = observation_by_date.get(capture.isoformat())
        if baseline is None:
            return self._result(
                status="pending",
                reason="missing_taiex_baseline_observation:" + capture.isoformat(),
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(capture.isoformat(),),
                proof=None,
            )
        if (
            _parse_aware_datetime(baseline.available_at, "baseline.available_at")
            > evaluation
        ):
            return self._result(
                status="pending",
                reason="taiex_baseline_not_available_at_evaluation:" + capture.isoformat(),
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(capture.isoformat(),),
                proof=None,
            )
        capture_annual = self._load_annual(capture.year, evaluation)
        if capture_annual is None:
            return self._result(
                status="waiting_for_calendar",
                reason=self._annual_errors.get(
                    capture.year,
                    "official_calendar_cache_unavailable",
                ),
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(),
                proof=None,
            )
        temporary_status = self._load_temporary(evaluation)
        if temporary_status is not None:
            return self._result(
                status="waiting_for_calendar",
                reason=temporary_status,
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(),
                proof=None,
            )
        if capture.weekday() >= 5 or not self._is_planned_session(
            capture,
            capture_annual,
        ):
            return self._result(
                status="pending",
                reason="calendar_market_session_conflict:" + capture.isoformat(),
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=(),
                observed_dates=(),
                missing_dates=(),
                proof=None,
            )

        sessions: list[date] = []
        years: set[int] = {capture.year}
        current = capture + timedelta(days=1)
        while current <= scan_end and len(sessions) < horizon:
            if current.weekday() < 5:
                years.add(current.year)
                annual = self._load_annual(current.year, evaluation)
                if annual is None:
                    return self._result(
                        status="waiting_for_calendar",
                        reason=self._annual_errors.get(
                            current.year,
                            "official_calendar_cache_unavailable",
                        ),
                        capture=capture,
                        evaluation=evaluation,
                        horizon=horizon,
                        session_dates=tuple(item.isoformat() for item in sessions),
                        observed_dates=(),
                        missing_dates=(),
                        proof=None,
                    )
                temporary_status = self._load_temporary(evaluation)
                if temporary_status is not None:
                    return self._result(
                        status="waiting_for_calendar",
                        reason=temporary_status,
                        capture=capture,
                        evaluation=evaluation,
                        horizon=horizon,
                        session_dates=tuple(item.isoformat() for item in sessions),
                        observed_dates=(),
                        missing_dates=(),
                        proof=None,
                    )
                if self._is_planned_session(current, annual):
                    sessions.append(current)
            current += timedelta(days=1)

        if len(sessions) < horizon:
            return self._result(
                status="waiting_for_calendar",
                reason="official_calendar_coverage_insufficient",
                capture=capture,
                evaluation=evaluation,
                horizon=horizon,
                session_dates=tuple(item.isoformat() for item in sessions),
                observed_dates=(),
                missing_dates=(),
                proof=None,
            )

        session_dates = tuple(item.isoformat() for item in sessions)
        # 只要 bounded source 在 capture 到 endpoint 範圍內出現官方
        # calendar 判定為週末／休市的 TAIEX row，就不能把它靜默當成
        # session 或忽略；這代表 calendar 與市場資料不一致，必須停下。
        planned_session_set = set(session_dates)
        endpoint_bound = sessions[-1]
        for observation in observations:
            observed_day = _parse_date(observation.date_text, "market date")
            if observed_day > endpoint_bound:
                continue
            annual = self._load_annual(observed_day.year, evaluation)
            if annual is None:
                return self._result(
                    status="waiting_for_calendar",
                    reason=self._annual_errors.get(
                        observed_day.year,
                        "official_calendar_cache_unavailable",
                    ),
                    capture=capture,
                    evaluation=evaluation,
                    horizon=horizon,
                    session_dates=session_dates,
                    observed_dates=(),
                    missing_dates=(),
                    proof=None,
                )
            temporary_status = self._load_temporary(evaluation)
            if temporary_status is not None:
                return self._result(
                    status="waiting_for_calendar",
                    reason=temporary_status,
                    capture=capture,
                    evaluation=evaluation,
                    horizon=horizon,
                    session_dates=session_dates,
                    observed_dates=(),
                    missing_dates=(),
                    proof=None,
                )
            if (
                observation.date_text not in planned_session_set
                and (
                    observed_day.weekday() >= 5
                    or not self._is_planned_session(observed_day, annual)
                )
            ):
                return self._result(
                    status="pending",
                    reason="calendar_market_session_conflict:" + observation.date_text,
                    capture=capture,
                    evaluation=evaluation,
                    horizon=horizon,
                    session_dates=session_dates,
                    observed_dates=(),
                    missing_dates=(),
                    proof=None,
                )

        available_observations: list[_TAIEXObservation] = []
        missing_dates: list[str] = []
        unavailable_dates: list[str] = []
        for session in sessions:
            key = session.isoformat()
            observation = observation_by_date.get(key)
            if observation is None:
                missing_dates.append(key)
                continue
            available_at = _parse_aware_datetime(
                observation.available_at,
                "observation.available_at",
            )
            if available_at > evaluation:
                unavailable_dates.append(key)
                continue
            available_observations.append(observation)

        observed_dates = tuple(item.date_text for item in available_observations)
        if missing_dates:
            reason = "missing_taiex_session_observation:" + ",".join(missing_dates[:8])
            status = "pending"
            endpoint = None
        elif unavailable_dates:
            reason = "taiex_session_not_available_at_evaluation:" + ",".join(
                unavailable_dates[:8]
            )
            status = "pending"
            endpoint = None
        else:
            reason = "official_sessions_and_taiex_observations_verified"
            status = "ready"
            endpoint = session_dates[-1]

        proof = self._build_proof(
            status=status,
            reason=reason,
            capture=capture,
            evaluation=evaluation,
            horizon=horizon,
            session_dates=session_dates,
            observed_dates=observed_dates,
            missing_dates=tuple(missing_dates + unavailable_dates),
            endpoint=endpoint,
            observations=tuple(available_observations),
            baseline=baseline,
            source=source,
            years=tuple(sorted(years)),
        )
        return self._result(
            status=status,
            reason=reason,
            capture=capture,
            evaluation=evaluation,
            horizon=horizon,
            session_dates=session_dates,
            observed_dates=observed_dates,
            missing_dates=tuple(missing_dates + unavailable_dates),
            proof=proof,
            endpoint=endpoint,
        )

    def resolve_personal_prediction_horizon(
        self,
        capture_date: str,
        evaluation_at: datetime,
    ) -> SessionResolution:
        """以固定 20 個官方交易日解析個人捕獲的成熟端點。"""

        return self.resolve(
            capture_date=capture_date,
            evaluation_at=evaluation_at,
            horizon_sessions=20,
        )

    def _reset_resolution_cache(self) -> None:
        """清除上一個 evaluation 的 cache 驗證結果。"""

        self._annual.clear()
        self._annual_errors.clear()
        self._temporary_loaded = False
        self._temporary.clear()
        self._temporary_error = None

    @staticmethod
    def verify_session_proof(
        proof: Mapping[str, Any],
        capture_date: str,
        label_end_date: str,
        evaluation_at: datetime,
        *,
        expected_db_path: str | Path,
    ) -> Mapping[str, Any]:
        """Verify an immutable ready proof before natural evidence consumes it."""

        return verify_session_proof(
            proof,
            capture_date,
            label_end_date,
            evaluation_at,
            expected_db_path=expected_db_path,
        )

    def _result(
        self,
        *,
        status: str,
        reason: str,
        capture: date,
        evaluation: datetime,
        horizon: int,
        session_dates: tuple[str, ...],
        observed_dates: tuple[str, ...],
        missing_dates: tuple[str, ...],
        proof: Mapping[str, Any] | None,
        endpoint: str | None = None,
    ) -> SessionResolution:
        return SessionResolution(
            status=status,
            reason=reason,
            capture_date=capture.isoformat(),
            evaluation_at=evaluation.isoformat(),
            horizon_sessions=horizon,
            endpoint_date=endpoint,
            session_dates=session_dates,
            observed_session_dates=observed_dates,
            missing_session_dates=missing_dates,
            proof=proof,
        )

    def _load_annual(
        self,
        calendar_year: int,
        observed_at: datetime,
    ) -> VerifiedOfficialCalendarCache | None:
        if calendar_year in self._annual:
            return self._annual[calendar_year]
        verified: list[VerifiedOfficialCalendarCache] = []
        errors: list[str] = []
        for candidate in self._annual_candidates(calendar_year):
            try:
                verified.append(
                    load_verified_twse_calendar_cache(
                        candidate,
                        calendar_year=calendar_year,
                        observed_at=observed_at,
                    )
                )
            except (OSError, ValueError, OfficialCalendarCacheError) as error:
                errors.append(f"{type(error).__name__}:{str(error)[:240]}")
        selected = (
            max(
                verified,
                key=lambda item: str(item.evidence.get("captured_at", "")),
            )
            if verified
            else None
        )
        self._annual[calendar_year] = selected
        if selected is None:
            self._annual_errors[calendar_year] = (
                errors[0] if errors else "official_calendar_cache_file_missing"
            )
        return selected

    def _annual_candidates(self, calendar_year: int) -> tuple[Path, ...]:
        root = self.calendar_cache_path
        if root.is_file():
            return (root,)
        if root.suffix.casefold() == ".json":
            return (root,)
        if not root.is_dir():
            return ()
        # mtime 只用來在 immutable 檔案很多時做 bounded discovery；真正的
        # calendar authority 仍由 _load_annual 重驗 bytes 後按 captured_at 選擇。
        candidates: list[tuple[int, str, Path]] = []
        for candidate in root.glob(
            f"twse_holiday_schedule_{calendar_year}_*.json"
        ):
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
                stat = resolved.stat()
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                candidates.append((int(stat.st_mtime_ns), str(resolved), resolved))
        exact = root / f"twse_holiday_schedule_{calendar_year}.json"
        if exact.is_file():
            try:
                resolved_exact = exact.resolve()
                resolved_exact.relative_to(root)
                stat = resolved_exact.stat()
            except (OSError, ValueError):
                resolved_exact = None
            if resolved_exact is not None and resolved_exact.is_file():
                candidates.append(
                    (int(stat.st_mtime_ns), str(resolved_exact), resolved_exact)
                )
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(item[2] for item in candidates[:MAX_CACHE_CANDIDATES])

    def _load_temporary(self, observed_at: datetime) -> str | None:
        if self._temporary_loaded:
            return self._temporary_error
        self._temporary_loaded = True
        if self.temporary_closure_path is None:
            return None
        candidates = _temporary_cache_candidates(self.temporary_closure_path)
        if not candidates:
            self._temporary_error = "official_temporary_closure_cache_missing"
            return self._temporary_error
        errors: list[str] = []
        for candidate in candidates:
            try:
                item = load_verified_twse_temporary_closure_cache(
                    candidate,
                    observed_at=observed_at,
                )
                if item.closure_date in self._temporary:
                    self._temporary_error = (
                        "official_temporary_closure_cache_duplicate_date:"
                        + item.closure_date.isoformat()
                    )
                    return self._temporary_error
                self._temporary[item.closure_date] = item
            except (OSError, ValueError, OfficialCalendarCacheError) as error:
                errors.append(f"{type(error).__name__}:{str(error)[:240]}")
        if errors:
            self._temporary_error = errors[0]
        return self._temporary_error

    def _is_planned_session(
        self,
        target: date,
        annual: VerifiedOfficialCalendarCache,
    ) -> bool:
        if target in self._temporary:
            return False
        return bool(annual.schedule.get(target, True))

    def _read_taiex_observations(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {"status": "pending", "reason": "market_source_missing"}
        try:
            stat_before = self.db_path.stat()
            uri = self.db_path.as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                if connection.execute("PRAGMA query_only").fetchone() != (1,):
                    return {
                        "status": "pending",
                        "reason": "market_source_query_only_unavailable",
                    }
                table = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (TAIEX_SOURCE_TABLE,),
                ).fetchone()
                if table is None:
                    return {
                        "status": "pending",
                        "reason": "market_source_table_missing",
                    }
                columns = tuple(
                    str(row[1])
                    for row in connection.execute(
                        'PRAGMA table_info("market_indices")'
                    ).fetchall()
                )
                if "日期" not in columns or "指數名稱" not in columns:
                    return {
                        "status": "pending",
                        "reason": "market_source_schema_missing_taiex_identity",
                    }
                close_columns = tuple(
                    column
                    for column in ("收盤指數", "收盤價")
                    if column in columns
                )
                if not close_columns:
                    return {
                        "status": "pending",
                        "reason": "market_source_schema_missing_close",
                    }
                selected = ["日期", "指數名稱", *close_columns]
                select_sql = ", ".join(f'"{column}"' for column in selected)
                start_compact = start_date.strftime("%Y%m%d")
                end_compact = end_date.strftime("%Y%m%d")
                start_iso = start_date.isoformat()
                end_iso = end_date.isoformat()
                rows = connection.execute(
                    f'''SELECT {select_sql}
                        FROM "market_indices"
                        WHERE "指數名稱" = ?
                          AND ((length("日期") = 8 AND "日期" BETWEEN ? AND ?)
                               OR (length("日期") = 10 AND "日期" BETWEEN ? AND ?))
                        ORDER BY "日期"''',
                    (
                        TAIEX_INDEX_NAME,
                        start_compact,
                        end_compact,
                        start_iso,
                        end_iso,
                    ),
                ).fetchall()
                schema_hash = _hash_payload(
                    {"table": TAIEX_SOURCE_TABLE, "columns": list(columns)}
                )
            stat_after = self.db_path.stat()
            if (stat_before.st_size, stat_before.st_mtime_ns) != (
                stat_after.st_size,
                stat_after.st_mtime_ns,
            ):
                return {
                    "status": "pending",
                    "reason": "market_source_changed_during_read",
                }
        except (OSError, sqlite3.Error) as error:
            return {
                "status": "pending",
                "reason": f"market_source_read_failed:{type(error).__name__}",
            }

        observations: list[_TAIEXObservation] = []
        seen: set[str] = set()
        try:
            for row in rows:
                row_date = _canonical_date_value(row[0])
                if row_date in seen:
                    return {
                        "status": "pending",
                        "reason": f"market_source_duplicate_taiex_session:{row_date}",
                    }
                seen.add(row_date)
                close_values = {
                    column: row[2 + index]
                    for index, column in enumerate(close_columns)
                }
                close_index = close_values.get("收盤指數")
                close_price = close_values.get("收盤價")
                close = _resolve_close(close_index, close_price)
                close_text = _decimal_text(close)
                available_at = _session_available_at(row_date)
                row_hash = _hash_payload(
                    {
                        "source_table": TAIEX_SOURCE_TABLE,
                        "index_name": TAIEX_INDEX_NAME,
                        "date": row_date,
                        "close_index": _raw_text(close_index),
                        "close_price": _raw_text(close_price),
                        "close": close_text,
                        "available_at": available_at,
                    }
                )
                observations.append(
                    _TAIEXObservation(
                        date_text=row_date,
                        close_text=close_text,
                        close_index_text=_raw_text(close_index),
                        close_price_text=_raw_text(close_price),
                        available_at=available_at,
                        row_hash=row_hash,
                    )
                )
        except (NaturalMaturitySessionResolverError, ValueError) as error:
            return {"status": "pending", "reason": str(error)}
        observations.sort(key=lambda item: item.date_text)
        source_fingerprint = _hash_payload(
            {
                "path": str(self.db_path),
                "size": stat_before.st_size,
                "mtime_ns": stat_before.st_mtime_ns,
                "schema_hash": schema_hash,
            }
        )
        observations_hash = _hash_payload(
            {"row_hashes": [item.row_hash for item in observations]}
        )
        return {
            "status": "ready",
            "reason": "taiex_source_loaded",
            "observations": tuple(observations),
            "source_db_path": str(self.db_path),
            "source_db_stat": {
                "size": stat_before.st_size,
                "mtime_ns": stat_before.st_mtime_ns,
            },
            "source_db_fingerprint": source_fingerprint,
            "source_schema_hash": schema_hash,
            "observations_hash": observations_hash,
            "query_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "index_name": TAIEX_INDEX_NAME,
            },
        }

    def _build_proof(
        self,
        *,
        status: str,
        reason: str,
        capture: date,
        evaluation: datetime,
        horizon: int,
        session_dates: tuple[str, ...],
        observed_dates: tuple[str, ...],
        missing_dates: tuple[str, ...],
        endpoint: str | None,
        observations: tuple[_TAIEXObservation, ...],
        baseline: _TAIEXObservation,
        source: Mapping[str, Any],
        years: tuple[int, ...],
    ) -> dict[str, Any]:
        annual_sources = []
        for year in years:
            annual = self._annual.get(year)
            if annual is not None:
                annual_sources.append(
                    {
                        "calendar_year": year,
                        "evidence": dict(annual.evidence),
                    }
                )
        temporary_evidence = [
            {
                "closure_date": item.closure_date.isoformat(),
                "evidence": dict(item.evidence),
            }
            for item in sorted(
                self._temporary.values(), key=lambda item: item.closure_date
            )
        ]
        calendar_status = (
            "annual_plan_only"
            if self.temporary_closure_path is None
            else "official_event_cache_verified"
        )
        body: dict[str, Any] = {
            "schema_version": SESSION_PROOF_SCHEMA_VERSION,
            "resolver_id": NATURAL_MATURITY_SESSION_RESOLVER_ID,
            "resolver_version": NATURAL_MATURITY_SESSION_RESOLVER_VERSION,
            "status": status,
            "reason": reason,
            "capture_date": capture.isoformat(),
            "evaluation_at": evaluation.isoformat(),
            "horizon_sessions": horizon,
            "endpoint_date": endpoint,
            "session_dates": list(session_dates),
            "observed_session_dates": list(observed_dates),
            "missing_session_dates": list(missing_dates),
            "calendar": {
                "status": calendar_status,
                "schema_version": OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION,
                "calendar_cache_path": str(self.calendar_cache_path),
                "annual_sources": annual_sources,
                "temporary_closure_path": (
                    None
                    if self.temporary_closure_path is None
                    else str(self.temporary_closure_path)
                ),
                "temporary_closure_evidence": temporary_evidence,
            },
            "market": {
                "source_table": TAIEX_SOURCE_TABLE,
                "index_name": TAIEX_INDEX_NAME,
                "close_time": TAIEX_CLOSE_TIME.isoformat(),
                "timezone": TAIEX_TIMEZONE,
                "baseline_observation": baseline.to_dict(),
                "observations": [item.to_dict() for item in observations],
                "observations_hash": _hash_payload(
                    {"row_hashes": [item.row_hash for item in observations]}
                ),
                "bounded_source_observations_hash": source.get(
                    "observations_hash"
                ),
                "query_range": source.get("query_range"),
                "source_db_path": source.get("source_db_path"),
                "source_db_stat": source.get("source_db_stat"),
                "source_db_fingerprint": source.get("source_db_fingerprint"),
                "source_schema_hash": source.get("source_schema_hash"),
            },
        }
        body["proof_hash"] = _hash_payload(body)
        return body


def verify_session_proof(
    proof: Mapping[str, Any],
    capture_date: str,
    label_end_date: str,
    evaluation_at: datetime,
    *,
    expected_db_path: str | Path,
) -> Mapping[str, Any]:
    """以原始 cache bytes 與 bounded SQLite rows 重建並驗證 ready proof。"""

    if not isinstance(proof, Mapping):
        raise ValueError("session proof must be an object")
    payload = dict(proof)
    supplied_hash = payload.get("proof_hash")
    if not isinstance(supplied_hash, str) or supplied_hash != _hash_payload(
        {key: value for key, value in payload.items() if key != "proof_hash"}
    ):
        raise ValueError("session proof hash mismatch")
    required = {
        "schema_version",
        "resolver_id",
        "resolver_version",
        "status",
        "reason",
        "capture_date",
        "evaluation_at",
        "horizon_sessions",
        "endpoint_date",
        "session_dates",
        "observed_session_dates",
        "missing_session_dates",
        "calendar",
        "market",
        "proof_hash",
    }
    if set(payload) != required:
        raise ValueError("session proof fields are invalid")
    if payload["schema_version"] != SESSION_PROOF_SCHEMA_VERSION:
        raise ValueError("session proof schema version is invalid")
    if payload["resolver_id"] != NATURAL_MATURITY_SESSION_RESOLVER_ID:
        raise ValueError("session proof resolver id is invalid")
    if payload["resolver_version"] != NATURAL_MATURITY_SESSION_RESOLVER_VERSION:
        raise ValueError("session proof resolver version is invalid")
    if payload["status"] != "ready":
        raise ValueError("session proof is not ready")

    capture = _parse_date(capture_date, "capture_date")
    label_end = _parse_date(label_end_date, "label_end_date")
    evaluation = _parse_aware_datetime(evaluation_at, "evaluation_at")
    if payload["capture_date"] != capture.isoformat():
        raise ValueError("session proof capture date mismatch")
    if payload["endpoint_date"] != label_end.isoformat():
        raise ValueError("session proof endpoint date mismatch")
    proof_evaluation = _parse_aware_datetime(
        str(payload["evaluation_at"]), "proof.evaluation_at"
    )
    if proof_evaluation != evaluation:
        raise ValueError("session proof evaluation timestamp mismatch")
    if label_end <= capture:
        raise ValueError("session proof endpoint must follow capture date")
    if _visible_market_end(proof_evaluation) < label_end:
        raise ValueError("session proof endpoint is after evaluation cutoff")

    session_dates = payload["session_dates"]
    observed_dates = payload["observed_session_dates"]
    missing_dates = payload["missing_session_dates"]
    if (
        not isinstance(session_dates, list)
        or not isinstance(observed_dates, list)
        or not isinstance(missing_dates, list)
        or any(not isinstance(value, str) for value in session_dates)
    ):
        raise ValueError("session proof date lists are invalid")
    horizon = payload["horizon_sessions"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("session proof horizon is invalid")
    _positive_horizon(horizon)
    if len(session_dates) != horizon or session_dates[-1] != label_end.isoformat():
        raise ValueError("session proof session endpoint is invalid")
    parsed_sessions = tuple(
        _parse_date(value, "session date") for value in session_dates
    )
    if tuple(sorted(parsed_sessions)) != parsed_sessions:
        raise ValueError("session proof sessions are not ordered")
    if any(value <= capture for value in parsed_sessions):
        raise ValueError("session proof session precedes capture")
    if missing_dates or tuple(observed_dates) != tuple(session_dates):
        raise ValueError("session proof does not cover every planned session")

    market = payload["market"]
    calendar = payload["calendar"]
    if not isinstance(market, Mapping) or not isinstance(calendar, Mapping):
        raise ValueError("session proof market/calendar payload is invalid")
    if market.get("source_table") != TAIEX_SOURCE_TABLE:
        raise ValueError("session proof market source table is invalid")
    if market.get("index_name") != TAIEX_INDEX_NAME:
        raise ValueError("session proof index identity is invalid")
    if market.get("close_time") != TAIEX_CLOSE_TIME.isoformat():
        raise ValueError("session proof close time is invalid")
    if market.get("timezone") != TAIEX_TIMEZONE:
        raise ValueError("session proof timezone is invalid")
    expected_path = Path(expected_db_path).expanduser().resolve()
    if market.get("source_db_path") != str(expected_path):
        raise ValueError("session proof database path mismatch")

    baseline = market.get("baseline_observation")
    if not isinstance(baseline, Mapping):
        raise ValueError("session proof baseline observation is missing")
    _validate_observation_mapping(
        baseline,
        expected_date=capture.isoformat(),
        evaluation=evaluation,
        field_name="baseline observation",
    )

    observations = market.get("observations")
    if not isinstance(observations, list) or len(observations) != horizon:
        raise ValueError("session proof market observations are incomplete")
    row_hashes: list[str] = []
    seen_dates: set[str] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise ValueError("session proof observation is invalid")
        date_text = _validate_observation_mapping(
            observation,
            expected_date=None,
            evaluation=evaluation,
            field_name="observation",
        )
        if date_text in seen_dates or date_text not in session_dates:
            raise ValueError("session proof observation date is duplicated or unplanned")
        seen_dates.add(date_text)
        row_hashes.append(str(observation["row_hash"]))
    if tuple(sorted(seen_dates)) != tuple(session_dates):
        raise ValueError("session proof observation dates do not cover endpoint")
    expected_observation_hash = _hash_payload({"row_hashes": row_hashes})
    if market.get("observations_hash") != expected_observation_hash:
        raise ValueError("session proof observations hash mismatch")

    # 先用 proof 原 evaluation_at 重讀每一個 annual cache；不能只信任
    # proof 自報的 schedule 或 hash。
    if calendar.get("schema_version") != OFFICIAL_CALENDAR_CACHE_SCHEMA_VERSION:
        raise ValueError("session proof calendar schema is invalid")
    calendar_cache_path_value = calendar.get("calendar_cache_path")
    if not isinstance(calendar_cache_path_value, str) or not calendar_cache_path_value:
        raise ValueError("session proof calendar cache path is missing")
    annual_cache_root = Path(calendar_cache_path_value).expanduser().resolve()
    annual_sources = calendar.get("annual_sources")
    if not isinstance(annual_sources, list) or not annual_sources:
        raise ValueError("session proof annual cache evidence is missing")
    annual_by_year: dict[int, VerifiedOfficialCalendarCache] = {}
    for source_item in annual_sources:
        if not isinstance(source_item, Mapping):
            raise ValueError("session proof annual source is invalid")
        year = source_item.get("calendar_year")
        evidence = source_item.get("evidence")
        if isinstance(year, bool) or not isinstance(year, int) or not isinstance(
            evidence, Mapping
        ):
            raise ValueError("session proof annual source evidence is invalid")
        if year in annual_by_year:
            raise ValueError("session proof annual source is duplicated")
        path_value = evidence.get("path")
        if not isinstance(path_value, str):
            raise ValueError("session proof annual cache path is invalid")
        annual_cache_path = Path(path_value).expanduser().resolve()
        if not _is_cache_path_under_root(annual_cache_path, annual_cache_root):
            raise ValueError("session proof annual cache path is outside scope")
        try:
            verified = load_verified_twse_calendar_cache(
                annual_cache_path,
                calendar_year=year,
                observed_at=proof_evaluation,
            )
        except (OSError, ValueError, OfficialCalendarCacheError) as error:
            raise ValueError(
                f"session proof annual cache revalidation failed:{type(error).__name__}"
            ) from error
        _assert_evidence_binding(evidence, verified.evidence, "annual calendar")
        annual_by_year[year] = verified

    temporary_path_value = calendar.get("temporary_closure_path")
    temporary_evidence = calendar.get("temporary_closure_evidence")
    if not isinstance(temporary_evidence, list):
        raise ValueError("session proof temporary closure evidence is invalid")
    temporary_by_date: dict[date, VerifiedTemporaryClosureCache] = {}
    if temporary_path_value is None:
        if calendar.get("status") != "annual_plan_only" or temporary_evidence:
            raise ValueError("session proof temporary calendar scope is invalid")
    else:
        if not isinstance(temporary_path_value, str) or not temporary_path_value:
            raise ValueError("session proof temporary closure path is invalid")
        if calendar.get("status") != "official_event_cache_verified":
            raise ValueError("session proof temporary calendar status is invalid")
        temporary_root = Path(temporary_path_value).expanduser().resolve()
        if not temporary_evidence:
            raise ValueError("session proof temporary closure evidence is missing")
        for evidence_item in temporary_evidence:
            if not isinstance(evidence_item, Mapping) or not isinstance(
                evidence_item.get("evidence"), Mapping
            ):
                raise ValueError("session proof temporary closure evidence is invalid")
            evidence = evidence_item["evidence"]
            closure_text = evidence_item.get("closure_date")
            expected_path_text = evidence.get("path")
            if not isinstance(closure_text, str) or not isinstance(
                expected_path_text, str
            ):
                raise ValueError("session proof temporary closure evidence is invalid")
            closure_date = _parse_date(closure_text, "temporary closure date")
            cache_path = Path(expected_path_text).expanduser().resolve()
            if not _is_cache_path_under_root(cache_path, temporary_root):
                raise ValueError("session proof temporary closure path is outside scope")
            try:
                temporary_verified = load_verified_twse_temporary_closure_cache(
                    cache_path,
                    observed_at=proof_evaluation,
                )
            except (OSError, ValueError, OfficialCalendarCacheError) as error:
                raise ValueError(
                    "session proof temporary closure revalidation failed:"
                    + type(error).__name__
                ) from error
            if temporary_verified.closure_date != closure_date:
                raise ValueError("session proof temporary closure date mismatch")
            if temporary_verified.closure_date in temporary_by_date:
                raise ValueError("session proof temporary closure is duplicated")
            _assert_evidence_binding(
                evidence,
                temporary_verified.evidence,
                "temporary closure",
            )
            temporary_by_date[temporary_verified.closure_date] = temporary_verified

    planned = _reconstruct_planned_sessions(
        capture=capture,
        horizon=horizon,
        annual_by_year=annual_by_year,
        temporary_dates=set(temporary_by_date),
    )
    if planned != parsed_sessions:
        raise ValueError("session proof planned session sequence mismatch")

    scan_end = capture + timedelta(
        days=min(MAX_SCAN_DAYS, max(366, horizon * 3 + 31))
    )
    query_end = min(scan_end, _visible_market_end(proof_evaluation))
    reader = NaturalMaturitySessionResolver(
        expected_path,
        Path(calendar_cache_path_value),
        None if temporary_path_value is None else Path(str(temporary_path_value)),
    )
    source = reader._read_taiex_observations(
        start_date=capture,
        end_date=query_end,
    )
    if source.get("status") != "ready":
        raise ValueError("session proof bounded market reread failed")
    if market.get("query_range") != source.get("query_range"):
        raise ValueError("session proof market query range mismatch")
    if market.get("bounded_source_observations_hash") != source.get(
        "observations_hash"
    ):
        raise ValueError("session proof bounded market hash mismatch")
    if market.get("source_schema_hash") != source.get("source_schema_hash"):
        raise ValueError("session proof market schema hash mismatch")
    source_stat = market.get("source_db_stat")
    if not isinstance(source_stat, Mapping) or any(
        isinstance(source_stat.get(key), bool)
        or not isinstance(source_stat.get(key), int)
        for key in ("size", "mtime_ns")
    ):
        raise ValueError("session proof source db stat is invalid")
    current_observations = source.get("observations")
    if not isinstance(current_observations, tuple):
        raise ValueError("session proof bounded market observations are invalid")
    current_by_date = {item.date_text: item for item in current_observations}
    current_baseline = current_by_date.get(capture.isoformat())
    if current_baseline is None or current_baseline.to_dict() != dict(baseline):
        raise ValueError("session proof baseline does not match source")
    current_planned = [current_by_date.get(value) for value in session_dates]
    if any(item is None for item in current_planned):
        raise ValueError("session proof planned market rows are missing")
    current_planned_dicts = [item.to_dict() for item in current_planned if item]
    if current_planned_dicts != [dict(item) for item in observations]:
        raise ValueError("session proof planned market rows do not match source")

    # 再次檢查 bounded market rows 與 official session sequence 的一致性；
    # capture 日也必須是 official open session 才能作 close-to-close baseline。
    planned_set = set(session_dates)
    for item in current_observations:
        item_date = _parse_date(item.date_text, "market date")
        if item_date > label_end:
            continue
        annual = annual_by_year.get(item_date.year)
        if annual is None:
            raise ValueError("session proof calendar year coverage is incomplete")
        is_planned = (
            item_date.weekday() < 5
            and item_date not in temporary_by_date
            and bool(annual.schedule.get(item_date, True))
        )
        if item_date == capture:
            if not is_planned:
                raise ValueError("session proof calendar market baseline conflict")
        elif item_date.isoformat() not in planned_set or not is_planned:
            raise ValueError("session proof calendar market session conflict")

    return payload


def _validate_observation_mapping(
    observation: Mapping[str, Any],
    *,
    expected_date: str | None,
    evaluation: datetime,
    field_name: str,
) -> str:
    """驗證一筆 proof observation 的欄位、可見時間與 row hash。"""

    required_observation = {
        "date",
        "index_name",
        "source_table",
        "close",
        "close_index",
        "close_price",
        "available_at",
        "row_hash",
    }
    if set(observation) != required_observation:
        raise ValueError(f"session proof {field_name} fields are invalid")
    current_date = _parse_date(str(observation["date"]), f"{field_name}.date")
    date_text = current_date.isoformat()
    if expected_date is not None and date_text != expected_date:
        raise ValueError(f"session proof {field_name} date is invalid")
    if observation["index_name"] != TAIEX_INDEX_NAME:
        raise ValueError(f"session proof {field_name} index is invalid")
    if observation["source_table"] != TAIEX_SOURCE_TABLE:
        raise ValueError(f"session proof {field_name} source is invalid")
    close = _parse_positive_decimal(
        str(observation["close"]), f"{field_name}.close"
    )
    resolved_close = _resolve_close(
        observation["close_index"],
        observation["close_price"],
    )
    if resolved_close != close:
        raise ValueError(f"session proof {field_name} close columns disagree")
    available = _parse_aware_datetime(
        str(observation["available_at"]), f"{field_name}.available_at"
    )
    expected_available = _session_available_at(date_text)
    if available != _parse_aware_datetime(
        expected_available,
        f"expected {field_name} availability",
    ):
        raise ValueError(f"session proof {field_name} availability is invalid")
    if available > evaluation:
        raise ValueError(f"session proof {field_name} is future-dated")
    expected_row_hash = _hash_payload(
        {
            "source_table": TAIEX_SOURCE_TABLE,
            "index_name": TAIEX_INDEX_NAME,
            "date": date_text,
            "close_index": observation["close_index"],
            "close_price": observation["close_price"],
            "close": _decimal_text(close),
            "available_at": expected_available,
        }
    )
    if observation["row_hash"] != expected_row_hash:
        raise ValueError(f"session proof {field_name} row hash mismatch")
    return date_text


def _assert_evidence_binding(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    label: str,
) -> None:
    """要求 proof custody evidence 與重新讀出的 evidence 完全相同。"""

    if set(expected) != set(actual):
        raise ValueError(f"session proof {label} evidence fields mismatch")
    for key in expected:
        if expected[key] != actual[key]:
            raise ValueError(f"session proof {label} evidence mismatch:{key}")


def _temporary_cache_candidates(path: Path) -> tuple[Path, ...]:
    """列出 bounded temporary cache candidates，不作遞迴或全量掃描。"""

    root = path.expanduser().resolve()
    if root.is_file():
        return (root,)
    if root.suffix.casefold() == ".json":
        return (root,)
    if not root.is_dir():
        return ()
    return tuple(
        sorted(root.glob("twse_temporary_closure_*.json"))
    )[:MAX_CACHE_CANDIDATES]


def _is_cache_path_under_root(path: Path, root: Path) -> bool:
    """Check direct-file/direct-child custody without recursive path walking."""

    resolved_path = path.expanduser().resolve()
    resolved_root = root.expanduser().resolve()
    if resolved_root.suffix.casefold() == ".json":
        return resolved_path == resolved_root
    return resolved_path.parent == resolved_root


def _reconstruct_planned_sessions(
    *,
    capture: date,
    horizon: int,
    annual_by_year: Mapping[int, VerifiedOfficialCalendarCache],
    temporary_dates: set[date],
) -> tuple[date, ...]:
    """以已重驗的 official schedule 重建 exact session sequence。"""

    scan_end = capture + timedelta(
        days=min(MAX_SCAN_DAYS, max(366, horizon * 3 + 31))
    )
    sessions: list[date] = []
    current = capture + timedelta(days=1)
    while current <= scan_end and len(sessions) < horizon:
        if current.weekday() < 5:
            annual = annual_by_year.get(current.year)
            if annual is None:
                raise ValueError("session proof calendar year coverage is incomplete")
            if current not in temporary_dates and bool(
                annual.schedule.get(current, True)
            ):
                sessions.append(current)
        current += timedelta(days=1)
    if len(sessions) < horizon:
        raise ValueError("session proof calendar coverage is insufficient")
    return tuple(sessions)


def _positive_horizon(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("horizon_sessions must be an integer")
    if value <= 0 or value > MAX_HORIZON_SESSIONS:
        raise ValueError("horizon_sessions is outside the bounded range")
    return value


def _parse_date(value: str, field_name: str) -> date:
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from error


def _canonical_date_value(value: object) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])).isoformat()
    return _parse_date(text, "market date").isoformat()


def _parse_aware_datetime(value: datetime | str, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError(f"{field_name} must contain timezone") from error
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError(f"{field_name} must contain timezone")
            return parsed.astimezone(_UTC)
        raise ValueError(f"{field_name} must contain timezone")
    return value.astimezone(_UTC)


def _session_available_at(date_text: str) -> str:
    day = _parse_date(date_text, "session date")
    return datetime.combine(day, TAIEX_CLOSE_TIME, tzinfo=_TAIPEI).isoformat()


def _visible_market_end(evaluation: datetime) -> date:
    """Return the latest TAIEX date whose 14:30 close is visible."""

    local = evaluation.astimezone(_TAIPEI)
    if local.time() < TAIEX_CLOSE_TIME:
        return local.date() - timedelta(days=1)
    return local.date()


def _raw_text(value: object) -> str | None:
    return None if value is None else str(value)


def _parse_positive_decimal(value: str, field_name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise NaturalMaturitySessionResolverError(
            f"{field_name} is not Decimal-compatible"
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise NaturalMaturitySessionResolverError(
            f"{field_name} must be finite and positive"
        )
    return parsed


def _resolve_close(value_index: object, value_price: object) -> Decimal:
    parsed_index = (
        None
        if value_index is None or str(value_index).strip() == ""
        else _parse_positive_decimal(str(value_index), "收盤指數")
    )
    parsed_price = (
        None
        if value_price is None or str(value_price).strip() == ""
        else _parse_positive_decimal(str(value_price), "收盤價")
    )
    if parsed_index is None and parsed_price is None:
        raise NaturalMaturitySessionResolverError("market_source_close_missing")
    if parsed_index is not None and parsed_price is not None and parsed_index != parsed_price:
        raise NaturalMaturitySessionResolverError("market_source_conflicting_close")
    return parsed_index if parsed_index is not None else parsed_price  # type: ignore[return-value]


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _hash_payload(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
