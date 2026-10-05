"""既有 MA 研究名單的純函式生命週期分類器。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_METHOD_IDS = frozenset(
    {
        "daily_market.close_above_ma20",
        "daily_market.close_above_ma60",
    }
)

_REASON_DISPLAY_ZH = {
    "history_stock_identity_mismatch": "歷史觀測包含不同股票身分，無法比較。",
    "current_publication_after_as_of": "目前快照在指定觀測時點之後才發布。",
    "current_cutoff_after_as_of": "目前資料截點晚於指定觀測時點。",
    "current_source_available_after_as_of": "目前來源在指定觀測時點尚不可得。",
    "current_retrospective_backfill_after_cutoff": "目前來源可得時間晚於原資料截點，屬回填資料。",
    "current_expected_session_unverified": "目前交易日邊界未通過日曆驗證。",
    "current_expected_previous_not_before_date": "目前排程提供的前一交易日不早於觀測日。",
    "current_membership_unknown": "目前入選狀態未知，無法判斷名單變化。",
    "same_session_multiple_observations_or_revisions": "同一交易日有多個截點或修訂，不能選一筆覆寫歷史。",
    "history_boundary_not_complete": "歷史範圍不完整，無法確認這是否為首次觀測。",
    "first_observation_in_verified_archive_scope": "這是可驗證快照範圍內的首次觀測。",
    "method_identity_changed": "前次觀測使用不同方法、版本、參數或AND/OR條件。",
    "universe_identity_changed": "前次觀測使用不同研究母體或母體版本。",
    "previous_expected_session_unverified": "前次交易日邊界未通過日曆驗證。",
    "expected_session_schedule_identity_changed": "前後觀測使用不同交易日曆版本。",
    "previous_source_available_after_as_of": "前次來源在指定觀測時點尚不可得。",
    "previous_retrospective_backfill_after_cutoff": "前次來源可得時間晚於原資料截點，不能視為當時已知。",
    "expected_session_gap_or_missing_observation": "相鄰預期交易日缺少完整觀測，不能判為進出名單。",
    "previous_membership_unknown": "前一個預期交易日的入選狀態未知。",
    "consecutive_match": "連續預期交易日都符合條件。",
    "prior_hit_then_consecutive_no_match_to_match": "可回放到先前符合、連續未符合後再次符合。",
    "first_hit_after_consecutive_no_match_history": "在可驗證歷史範圍內，連續未符合後首次符合。",
    "cannot_distinguish_first_hit_from_reselection": "歷史邊界不足，無法區分首次符合與重新符合。",
    "consecutive_match_to_no_match": "連續預期交易日由符合轉為未符合。",
    "consecutive_no_match": "連續預期交易日都未符合條件。",
}


class MembershipState(str, Enum):
    """區分符合、不符合與資料未知。"""

    MATCH = "match"
    NO_MATCH = "no_match"
    UNKNOWN = "unknown"


class LifecycleStatus(str, Enum):
    """描述目前觀測的可解釋狀態。"""

    NEWLY_SELECTED = "new"
    CONTINUING = "continued"
    RESELECTED = "reentered"
    NO_LONGER_SELECTED = "exited"
    REMAINS_NOT_SELECTED = "still_no_match"
    FIRST_OBSERVATION = "first_observation"
    HISTORY_INSUFFICIENT = "history_insufficient"
    INCOMPARABLE = "incomparable"
    UNKNOWN = "unknown"


class HistoryCoverage(str, Enum):
    """標記可見且已驗證的快照歷史範圍。"""

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MethodIdentity:
    """保存方法版本、參數及精確 AND/OR 條件身份。"""

    method_id: str
    version: str
    parameters_json: str
    predicate_semantic_key: str
    window_policy_key: str

    def __post_init__(self) -> None:
        if self.method_id not in _SUPPORTED_METHOD_IDS:
            raise ValueError("method_id must identify an existing close_above_ma20/60 method")
        _require_text(self.version, "method version")
        _require_text(self.predicate_semantic_key, "predicate semantic key")
        _require_text(self.window_policy_key, "window policy key")
        parsed = _parse_parameters(self.parameters_json)
        if _canonical_json(parsed) != self.parameters_json:
            raise ValueError("parameters_json must be canonical JSON")

    @classmethod
    def from_parameters(
        cls,
        *,
        method_id: str,
        version: str,
        parameters: Mapping[str, Any],
        predicate_semantic_key: str,
        window_policy_key: str,
    ) -> MethodIdentity:
        """以不含二進位浮點數的 JSON 參數建立身份。"""

        return cls(
            method_id=method_id,
            version=version,
            parameters_json=_canonical_json(parameters),
            predicate_semantic_key=predicate_semantic_key,
            window_policy_key=window_policy_key,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "method_id": self.method_id,
            "version": self.version,
            "parameters_json": self.parameters_json,
            "predicate_semantic_key": self.predicate_semantic_key,
            "window_policy_key": self.window_policy_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MethodIdentity:
        _require_keys(
            value,
            {
                "method_id",
                "version",
                "parameters_json",
                "predicate_semantic_key",
                "window_policy_key",
            },
        )
        return cls(
            method_id=_string(value["method_id"], "method_id"),
            version=_string(value["version"], "version"),
            parameters_json=_string(value["parameters_json"], "parameters_json"),
            predicate_semantic_key=_string(
                value["predicate_semantic_key"], "predicate_semantic_key"
            ),
            window_policy_key=_string(value["window_policy_key"], "window_policy_key"),
        )


@dataclass(frozen=True, slots=True)
class UniverseIdentity:
    """保存具名研究母體及穩定語意版本身份。"""

    universe_id: str
    version: str
    semantic_key: str

    def __post_init__(self) -> None:
        _require_text(self.universe_id, "universe_id")
        _require_text(self.version, "universe version")
        _require_text(self.semantic_key, "universe semantic key")

    def to_dict(self) -> dict[str, str]:
        return {
            "universe_id": self.universe_id,
            "version": self.version,
            "semantic_key": self.semantic_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> UniverseIdentity:
        _require_keys(value, {"universe_id", "version", "semantic_key"})
        return cls(
            universe_id=_string(value["universe_id"], "universe_id"),
            version=_string(value["version"], "version"),
            semantic_key=_string(value["semantic_key"], "semantic_key"),
        )


@dataclass(frozen=True, slots=True)
class ExpectedSession:
    """保存單一預期交易日的已驗證日曆邊界與可用來源身份。"""

    calendar_key: str
    calendar_version: str
    expected_previous_date: date | None
    verified: bool
    calendar_manifest_id: str | None = None
    calendar_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.calendar_key, "calendar_key")
        _require_text(self.calendar_version, "calendar_version")
        if type(self.verified) is not bool:
            raise ValueError("verified must be bool")
        if self.expected_previous_date is not None and type(self.expected_previous_date) is not date:
            raise ValueError("expected_previous_date must be a date or None")
        if self.calendar_manifest_id is not None:
            _require_text(self.calendar_manifest_id, "calendar_manifest_id")
        if self.calendar_manifest_sha256 is not None:
            _require_sha256(self.calendar_manifest_sha256, "calendar_manifest_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "calendar_key": self.calendar_key,
            "calendar_version": self.calendar_version,
            "expected_previous_date": (
                self.expected_previous_date.isoformat()
                if self.expected_previous_date is not None
                else None
            ),
            "verified": self.verified,
            "calendar_manifest_id": self.calendar_manifest_id,
            "calendar_manifest_sha256": self.calendar_manifest_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ExpectedSession:
        _require_keys(
            value,
            {
                "calendar_key",
                "calendar_version",
                "expected_previous_date",
                "verified",
                "calendar_manifest_id",
                "calendar_manifest_sha256",
            },
        )
        previous = value["expected_previous_date"]
        return cls(
            calendar_key=_string(value["calendar_key"], "calendar_key"),
            calendar_version=_string(value["calendar_version"], "calendar_version"),
            expected_previous_date=_parse_date(previous) if previous is not None else None,
            verified=value["verified"],
            calendar_manifest_id=(
                _string(value["calendar_manifest_id"], "calendar_manifest_id")
                if value["calendar_manifest_id"] is not None
                else None
            ),
            calendar_manifest_sha256=(
                _string(value["calendar_manifest_sha256"], "calendar_manifest_sha256")
                if value["calendar_manifest_sha256"] is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MembershipObservation:
    """保存 pinned 快照中的單股、方法及母體觀測。"""

    stock_id: str
    state: MembershipState
    method: MethodIdentity
    universe: UniverseIdentity
    decision_date: date
    cutoff_at: datetime
    published_at: datetime
    source_available_at: datetime | None
    schedule: ExpectedSession
    source_manifest_id: str
    source_manifest_sha256: str
    source_artifact_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.stock_id, "stock_id")
        if not isinstance(self.state, MembershipState):
            raise ValueError("state must be a MembershipState")
        if type(self.decision_date) is not date:
            raise ValueError("decision_date must be a date")
        _require_aware_datetime(self.cutoff_at, "cutoff_at")
        _require_aware_datetime(self.published_at, "published_at")
        if self.source_available_at is not None:
            _require_aware_datetime(self.source_available_at, "source_available_at")
        _require_text(self.source_manifest_id, "source_manifest_id")
        _require_sha256(self.source_manifest_sha256, "source_manifest_sha256")
        _require_sha256(self.source_artifact_sha256, "source_artifact_sha256")

    @property
    def observation_id(self) -> str:
        """以完整觀測內容計算確定性身份。"""

        return _sha256_json(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "stock_id": self.stock_id,
            "state": self.state.value,
            "method": self.method.to_dict(),
            "universe": self.universe.to_dict(),
            "decision_date": self.decision_date.isoformat(),
            "cutoff_at": _datetime_text(self.cutoff_at),
            "published_at": _datetime_text(self.published_at),
            "source_available_at": (
                _datetime_text(self.source_available_at)
                if self.source_available_at is not None
                else None
            ),
            "schedule": self.schedule.to_dict(),
            "source_manifest_id": self.source_manifest_id,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_artifact_sha256": self.source_artifact_sha256,
        }
        if include_identity:
            value["observation_id"] = self.observation_id
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MembershipObservation:
        _require_keys(
            value,
            {
                "stock_id",
                "state",
                "method",
                "universe",
                "decision_date",
                "cutoff_at",
                "published_at",
                "source_available_at",
                "schedule",
                "source_manifest_id",
                "source_manifest_sha256",
                "source_artifact_sha256",
                "observation_id",
            },
        )
        try:
            state = MembershipState(_string(value["state"], "state"))
        except ValueError as exc:
            raise ValueError("unsupported membership state") from exc
        observation = cls(
            stock_id=_string(value["stock_id"], "stock_id"),
            state=state,
            method=MethodIdentity.from_dict(_mapping(value["method"], "method")),
            universe=UniverseIdentity.from_dict(_mapping(value["universe"], "universe")),
            decision_date=_parse_date(value["decision_date"]),
            cutoff_at=_parse_datetime(value["cutoff_at"]),
            published_at=_parse_datetime(value["published_at"]),
            source_available_at=(
                _parse_datetime(value["source_available_at"])
                if value["source_available_at"] is not None
                else None
            ),
            schedule=ExpectedSession.from_dict(_mapping(value["schedule"], "schedule")),
            source_manifest_id=_string(value["source_manifest_id"], "source_manifest_id"),
            source_manifest_sha256=_string(
                value["source_manifest_sha256"], "source_manifest_sha256"
            ),
            source_artifact_sha256=_string(
                value["source_artifact_sha256"], "source_artifact_sha256"
            ),
        )
        if value["observation_id"] != observation.observation_id:
            raise ValueError("observation_id does not match the immutable observation payload")
        return observation


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    """保存單次目前觀測的唯讀、可回放分類結果。"""

    status: LifecycleStatus
    reason: str
    current: MembershipObservation
    as_of: datetime
    history_coverage: HistoryCoverage
    first_seen: date | None
    last_hit: date | None
    streak: int
    previous_date: date | None
    previous_state: MembershipState | None
    source_observations: tuple[MembershipObservation, ...]

    def __post_init__(self) -> None:
        _require_text(self.reason, "reason")
        _require_aware_datetime(self.as_of, "as_of")
        if type(self.streak) is not int or self.streak < 0:
            raise ValueError("streak must be a non-negative integer")
        if not isinstance(self.status, LifecycleStatus):
            raise ValueError("status must be a LifecycleStatus")
        if not isinstance(self.history_coverage, HistoryCoverage):
            raise ValueError("history_coverage must be a HistoryCoverage")

    @property
    def result_id(self) -> str:
        """以結果與精確來源觀測計算穩定身份。"""

        return _sha256_json(self.to_dict(include_identity=False))

    @property
    def reason_display(self) -> str:
        """回傳穩定 machine reason code 的繁體中文說明。"""

        return _REASON_DISPLAY_ZH.get(self.reason, f"無法完成可比性判定：{self.reason}")

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "status": self.status.value,
            "reason": self.reason,
            "reason_display": self.reason_display,
            "current": self.current.to_dict(),
            "as_of": _datetime_text(self.as_of),
            "history_coverage": self.history_coverage.value,
            "first_seen": self.first_seen.isoformat() if self.first_seen is not None else None,
            "last_hit": self.last_hit.isoformat() if self.last_hit is not None else None,
            "streak": self.streak,
            "previous_date": (
                self.previous_date.isoformat() if self.previous_date is not None else None
            ),
            "previous_state": self.previous_state.value if self.previous_state is not None else None,
            "source_observations": [item.to_dict() for item in self.source_observations],
        }
        if include_identity:
            value["result_id"] = self.result_id
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LifecycleResult:
        _require_keys(
            value,
            {
                "status",
                "reason",
                "reason_display",
                "current",
                "as_of",
                "history_coverage",
                "first_seen",
                "last_hit",
                "streak",
                "previous_date",
                "previous_state",
                "source_observations",
                "result_id",
            },
        )
        try:
            status = LifecycleStatus(_string(value["status"], "status"))
            coverage = HistoryCoverage(_string(value["history_coverage"], "history_coverage"))
            prior_state = (
                MembershipState(_string(value["previous_state"], "previous_state"))
                if value["previous_state"] is not None
                else None
            )
        except ValueError as exc:
            raise ValueError("unsupported lifecycle enum value") from exc
        raw_observations = value["source_observations"]
        if not isinstance(raw_observations, list):
            raise ValueError("source_observations must be a list")
        result = cls(
            status=status,
            reason=_string(value["reason"], "reason"),
            current=MembershipObservation.from_dict(_mapping(value["current"], "current")),
            as_of=_parse_datetime(value["as_of"]),
            history_coverage=coverage,
            first_seen=_parse_optional_date(value["first_seen"]),
            last_hit=_parse_optional_date(value["last_hit"]),
            streak=_integer(value["streak"], "streak"),
            previous_date=_parse_optional_date(value["previous_date"]),
            previous_state=prior_state,
            source_observations=tuple(
                MembershipObservation.from_dict(_mapping(item, "source observation"))
                for item in raw_observations
            ),
        )
        if value["result_id"] != result.result_id:
            raise ValueError("result_id does not match the lifecycle projection payload")
        if value["reason_display"] != result.reason_display:
            raise ValueError("reason_display does not match the lifecycle reason code")
        return result


def classify_membership_lifecycle(
    current: MembershipObservation,
    history: Sequence[MembershipObservation],
    *,
    as_of: datetime,
    history_coverage: HistoryCoverage,
) -> LifecycleResult:
    """只依連續已驗證交易日分類 pinned 觀測；修訂衝突不會覆寫歷史。"""

    _require_aware_datetime(as_of, "as_of")
    if not isinstance(history_coverage, HistoryCoverage):
        raise ValueError("history_coverage must be a HistoryCoverage")

    unique: dict[str, MembershipObservation] = {current.observation_id: current}
    for item in history:
        if not isinstance(item, MembershipObservation):
            raise ValueError("history must contain MembershipObservation values")
        unique.setdefault(item.observation_id, item)
    source_observations = tuple(unique[key] for key in sorted(unique))

    if any(item.stock_id != current.stock_id for item in source_observations):
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "history_stock_identity_mismatch",
            current,
            as_of,
            history_coverage,
            source_observations,
        )
    if current.cutoff_at > as_of:
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "current_cutoff_after_as_of",
            current,
            as_of,
            history_coverage,
            source_observations,
        )
    if current.published_at > as_of:
        return _result(
            LifecycleStatus.UNKNOWN,
            "current_publication_after_as_of",
            current,
            as_of,
            history_coverage,
            source_observations,
        )
    if (
        current.schedule.expected_previous_date is not None
        and current.schedule.expected_previous_date >= current.decision_date
    ):
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "current_expected_previous_not_before_date",
            current,
            as_of,
            history_coverage,
            source_observations,
        )
    if current.source_available_at is not None:
        if current.source_available_at > as_of:
            return _result(
                LifecycleStatus.UNKNOWN,
                "current_source_available_after_as_of",
                current,
                as_of,
                history_coverage,
                source_observations,
            )
        if current.source_available_at > current.cutoff_at:
            return _result(
                LifecycleStatus.INCOMPARABLE,
                "current_retrospective_backfill_after_cutoff",
                current,
                as_of,
                history_coverage,
                source_observations,
            )
    if not current.schedule.verified:
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "current_expected_session_unverified",
            current,
            as_of,
            history_coverage,
            source_observations,
        )
    if current.state is MembershipState.UNKNOWN:
        return _result(
            LifecycleStatus.UNKNOWN,
            "current_membership_unknown",
            current,
            as_of,
            history_coverage,
            source_observations,
        )

    visible = [
        item
        for item in source_observations
        if item.published_at <= as_of
        and item.cutoff_at <= as_of
        and item.decision_date <= current.decision_date
        and (item.source_available_at is None or item.source_available_at <= as_of)
    ]
    by_date: dict[date, list[MembershipObservation]] = {}
    for item in visible:
        by_date.setdefault(item.decision_date, []).append(item)
    if any(len(items) > 1 for items in by_date.values()):
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "same_session_multiple_observations_or_revisions",
            current,
            as_of,
            history_coverage,
            source_observations,
            _comparable_summary(current, visible, as_of),
        )

    previous_candidates = [item for item in visible if item.decision_date < current.decision_date]
    previous = max(previous_candidates, key=lambda item: item.decision_date, default=None)
    summary = _comparable_summary(current, visible, as_of)
    if previous is None:
        status = (
            LifecycleStatus.FIRST_OBSERVATION
            if history_coverage is HistoryCoverage.COMPLETE
            else LifecycleStatus.HISTORY_INSUFFICIENT
        )
        reason = (
            "first_observation_in_verified_archive_scope"
            if status is LifecycleStatus.FIRST_OBSERVATION
            else "history_boundary_not_complete"
        )
        return _result(
            status,
            reason,
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
        )

    if previous.method != current.method:
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "method_identity_changed",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )
    if previous.universe != current.universe:
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "universe_identity_changed",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )
    if not previous.schedule.verified:
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "previous_expected_session_unverified",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )
    if not _same_schedule(current, previous):
        return _result(
            LifecycleStatus.INCOMPARABLE,
            "expected_session_schedule_identity_changed",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )
    if previous.source_available_at is not None:
        if previous.source_available_at > as_of:
            return _result(
                LifecycleStatus.UNKNOWN,
                "previous_source_available_after_as_of",
                current,
                as_of,
                history_coverage,
                source_observations,
                summary,
                previous,
            )
        if previous.source_available_at > previous.cutoff_at:
            return _result(
                LifecycleStatus.INCOMPARABLE,
                "previous_retrospective_backfill_after_cutoff",
                current,
                as_of,
                history_coverage,
                source_observations,
                summary,
                previous,
            )
    if current.schedule.expected_previous_date != previous.decision_date:
        return _result(
            LifecycleStatus.HISTORY_INSUFFICIENT,
            "expected_session_gap_or_missing_observation",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )
    if previous.state is MembershipState.UNKNOWN:
        return _result(
            LifecycleStatus.UNKNOWN,
            "previous_membership_unknown",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
        )

    streak = _same_state_streak(current, visible)
    if current.state is MembershipState.MATCH:
        if previous.state is MembershipState.MATCH:
            return _result(
                LifecycleStatus.CONTINUING,
                "consecutive_match",
                current,
                as_of,
                history_coverage,
                source_observations,
                summary,
                previous,
                streak,
            )
        had_prior_hit, reached_complete_start = _prior_hit_in_consecutive_chain(current, visible)
        if had_prior_hit:
            return _result(
                LifecycleStatus.RESELECTED,
                "prior_hit_then_consecutive_no_match_to_match",
                current,
                as_of,
                history_coverage,
                source_observations,
                summary,
                previous,
                streak,
            )
        if reached_complete_start and history_coverage is HistoryCoverage.COMPLETE:
            return _result(
                LifecycleStatus.NEWLY_SELECTED,
                "first_hit_after_consecutive_no_match_history",
                current,
                as_of,
                history_coverage,
                source_observations,
                summary,
                previous,
                streak,
            )
        return _result(
            LifecycleStatus.HISTORY_INSUFFICIENT,
            "cannot_distinguish_first_hit_from_reselection",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
            streak,
        )

    if previous.state is MembershipState.MATCH:
        return _result(
            LifecycleStatus.NO_LONGER_SELECTED,
            "consecutive_match_to_no_match",
            current,
            as_of,
            history_coverage,
            source_observations,
            summary,
            previous,
            streak,
        )
    return _result(
        LifecycleStatus.REMAINS_NOT_SELECTED,
        "consecutive_no_match",
        current,
        as_of,
        history_coverage,
        source_observations,
        summary,
        previous,
        streak,
    )


def _result(
    status: LifecycleStatus,
    reason: str,
    current: MembershipObservation,
    as_of: datetime,
    coverage: HistoryCoverage,
    source_observations: tuple[MembershipObservation, ...],
    summary: tuple[date | None, date | None, int] | None = None,
    previous: MembershipObservation | None = None,
    streak: int | None = None,
) -> LifecycleResult:
    if summary is None:
        summary = _comparable_summary(current, source_observations, as_of)
    first_seen, last_hit, summary_streak = summary
    actual_streak = summary_streak if streak is None else streak
    if current.state is MembershipState.UNKNOWN:
        actual_streak = 0
    return LifecycleResult(
        status=status,
        reason=reason,
        current=current,
        as_of=as_of,
        history_coverage=coverage,
        first_seen=first_seen,
        last_hit=last_hit,
        streak=actual_streak,
        previous_date=previous.decision_date if previous is not None else None,
        previous_state=previous.state if previous is not None else None,
        source_observations=source_observations,
    )


def _comparable_summary(
    current: MembershipObservation,
    visible: Sequence[MembershipObservation],
    as_of: datetime,
) -> tuple[date | None, date | None, int]:
    eligible = [
        item
        for item in visible
        if item.stock_id == current.stock_id
        and item.method == current.method
        and item.universe == current.universe
        and item.published_at <= as_of
        and item.cutoff_at <= as_of
        and item.decision_date <= current.decision_date
        and (item.source_available_at is None or item.source_available_at <= as_of)
        and (item.source_available_at is None or item.source_available_at <= item.cutoff_at)
    ]
    grouped: dict[date, list[MembershipObservation]] = {}
    for item in eligible:
        grouped.setdefault(item.decision_date, []).append(item)
    comparable = [items[0] for items in grouped.values() if len(items) == 1]
    first_seen = min((item.decision_date for item in comparable), default=None)
    last_hit = max(
        (
            item.decision_date
            for item in comparable
            if item.state is MembershipState.MATCH
            and (item.source_available_at is None or item.source_available_at <= item.cutoff_at)
        ),
        default=None,
    )
    return first_seen, last_hit, _same_state_streak(current, comparable)


def _same_state_streak(
    current: MembershipObservation,
    observations: Sequence[MembershipObservation],
) -> int:
    if (
        current.state is MembershipState.UNKNOWN
        or not current.schedule.verified
        or current.schedule.expected_previous_date is not None
        and current.schedule.expected_previous_date >= current.decision_date
    ):
        return 0
    if not any(item.observation_id == current.observation_id for item in observations):
        return 0
    dated: dict[date, list[MembershipObservation]] = {}
    for item in observations:
        if item.method == current.method and item.universe == current.universe:
            dated.setdefault(item.decision_date, []).append(item)
    if len(dated.get(current.decision_date, ())) != 1:
        return 0
    by_date = {
        day: items[0]
        for day, items in dated.items()
        if len(items) == 1
    }
    count = 1
    newer = current
    seen_dates = {current.decision_date}
    while newer.schedule.expected_previous_date is not None:
        previous_date = newer.schedule.expected_previous_date
        if previous_date in seen_dates:
            break
        seen_dates.add(previous_date)
        prior = by_date.get(previous_date)
        if prior is None or not prior.schedule.verified:
            break
        if (
            prior.schedule.expected_previous_date is not None
            and prior.schedule.expected_previous_date >= prior.decision_date
        ):
            break
        if not _same_schedule(newer, prior) or prior.state is not current.state:
            break
        if prior.source_available_at is not None and prior.source_available_at > prior.cutoff_at:
            break
        count += 1
        newer = prior
    return count


def _prior_hit_in_consecutive_chain(
    current: MembershipObservation,
    observations: Sequence[MembershipObservation],
) -> tuple[bool, bool]:
    """回傳是否找到過往符合，及是否連續抵達完整歷史起點。"""

    by_date = {
        item.decision_date: item
        for item in observations
        if item.method == current.method and item.universe == current.universe
    }
    cursor = current
    seen_dates: set[date] = {current.decision_date}
    while cursor.schedule.expected_previous_date is not None:
        previous_date = cursor.schedule.expected_previous_date
        if previous_date in seen_dates:
            return False, False
        seen_dates.add(previous_date)
        prior = by_date.get(previous_date)
        if prior is None:
            # COMPLETE 僅指已保存觀測範圍。前一 session 早於整個範圍時，
            # 可稱範圍內首次命中；範圍內漏日／其他方法邊界仍不算新入選。
            archive_start = min(item.decision_date for item in observations)
            return False, previous_date < archive_start
        if (
            not prior.schedule.verified
            or not _same_schedule(cursor, prior)
            or prior.schedule.expected_previous_date is not None
            and prior.schedule.expected_previous_date >= prior.decision_date
            or prior.source_available_at is not None
            and prior.source_available_at > prior.cutoff_at
        ):
            return False, False
        if prior.state is MembershipState.UNKNOWN:
            return False, False
        if prior.state is MembershipState.MATCH:
            return True, False
        cursor = prior
    return False, True


def _same_schedule(left: MembershipObservation, right: MembershipObservation) -> bool:
    return (
        left.schedule.calendar_key == right.schedule.calendar_key
        and left.schedule.calendar_version == right.schedule.calendar_version
    )


def _canonical_json(value: Mapping[str, Any]) -> str:
    _validate_json_value(value)
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        return
    if isinstance(value, float):
        raise ValueError("binary floats are not allowed in method parameters")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("method parameter keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(item)
        return
    raise ValueError("method parameters must contain JSON scalar, object, or array values")


def _parse_parameters(raw: str) -> dict[str, Any]:
    def reject_float(_: str) -> None:
        raise ValueError("binary floats are not allowed in method parameters")

    try:
        value = json.loads(raw, parse_float=reject_float, parse_constant=reject_float)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("parameters_json must be a JSON object without floats") from exc
    if not isinstance(value, dict):
        raise ValueError("parameters_json must contain an object")
    _validate_json_value(value)
    return value


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(_string(value, "datetime"))
    _require_aware_datetime(parsed, "datetime")
    return parsed


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("date must be ISO text")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date must use canonical ISO format")
    return parsed


def _parse_optional_date(value: Any) -> date | None:
    return _parse_date(value) if value is not None else None


def _require_aware_datetime(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text")


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value


def _require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _require_keys(value: Mapping[str, Any], expected: set[str]) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("serialized object has missing or unknown fields")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value
