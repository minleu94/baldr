"""個人即時推薦共用決策日與保存來源資料日的回歸測試。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.recommendation import execute as execute_module
from app_module.recommendation.composition import build_recommendation_composition
from app_module.recommendation.contracts import ReferenceKind
from app_module.recommendation.input_preparation import (
    prepare_recommendation_market,
)
from app_module.recommendation.personal_use_policy import (
    RULE_ONLY_MODE,
    RecommendationPersonalUsePolicyV1,
    RecommendationPersonalUseSelectionV1,
    save_personal_use_policy,
)
from app_module.recommendation_market_data_provider import (
    DefaultRecommendationMarketDataProvider,
)
from recommendation_test_support import build_recommendation_test_service


_DECISION_CLOCK = datetime(2026, 9, 26, 18, 30, tzinfo=timezone.utc)
_DECISION_DATE = "2026-09-27"
_SOURCE_DATE = "2026-09-24"


class _FrozenClock(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        value = _DECISION_CLOCK
        return value if tz is None else value.astimezone(tz)


class _PolicyConfirmationClock(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        value = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        return value if tz is None else value.astimezone(tz)


class _LiveFrameProvider(DefaultRecommendationMarketDataProvider):
    def __init__(self, config: Any, frame: pd.DataFrame) -> None:
        super().__init__(config)
        self.frame = frame
        self.calls = 0

    def __call__(self) -> pd.DataFrame:
        self.calls += 1
        return self.frame.copy(deep=True)


def _market_frame() -> pd.DataFrame:
    rows = [
        {
            "日期": date(2026, 9, 1) + timedelta(days=offset),
            "available_date": date(2026, 9, 1) + timedelta(days=offset),
            "證券代號": "2330",
            "證券名稱": "台積電",
            "收盤價": Decimal("100.00") + Decimal(offset),
            "成交股數": 1_000,
        }
        for offset in range(24)
    ]
    rows.append(
        {
            "日期": date(2026, 9, 28),
            "available_date": date(2026, 9, 28),
            "證券代號": "2330",
            "證券名稱": "台積電",
            "收盤價": Decimal("999.00"),
            "成交股數": 1_000,
        }
    )
    return pd.DataFrame(rows)


def _runtime_config() -> dict[str, Any]:
    # 不設定 as_of_date：這是明示個人政策下的 natural/live 呼叫。
    return {
        "profile_id": "personal-live-clock-test",
        "profile_version": "1",
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "filters": {"industry": "全部"},
    }


def _service(tmp_path: Path, provider: _LiveFrameProvider):
    config = SimpleNamespace(
        db_file=tmp_path / "missing-source.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
        default_start_date="2020-01-01",
        output_root=tmp_path / "output",
    )
    config.resolve_output_path = lambda subfolder: config.output_root / subfolder
    mapper = MagicMock()
    mapper.get_stock_industries.return_value = []
    mapper.get_industry_performance.return_value = None
    service = build_recommendation_test_service(
        config,
        industry_mapper=mapper,
        market_data_provider=provider,
        regime_detector=MagicMock(),
    )
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = "合成測試理由"

    observed_market_dates: list[str] = []

    def generate(stock_frame: pd.DataFrame, _config: dict[str, Any]) -> pd.DataFrame:
        observed_market_dates.append(
            pd.Timestamp(stock_frame.iloc[-1]["日期"]).date().isoformat()
        )
        return pd.DataFrame(
            {
                "FinalScore": [Decimal("91.50")],
                "TotalScore": [Decimal("91.50")],
                "IndicatorScore": [Decimal("31.25")],
                "PatternScore": [Decimal("27.50")],
                "VolumeScore": [Decimal("18.00")],
                "收盤價": [stock_frame.iloc[-1]["收盤價"]],
            }
        )

    service.strategy_configurator.generate_recommendations = generate
    return config, service, observed_market_dates


@pytest.mark.parametrize("persisted_policy", (False, True))
def test_personal_live_execute_save_query_keeps_decision_and_market_dates_separate(
    tmp_path: Path,
    monkeypatch,
    persisted_policy: bool,
) -> None:
    import app_module.recommendation_service as recommendation_service_module
    import app_module.recommendation.personal_use_policy as personal_policy_module

    frame = _market_frame()
    provider = _LiveFrameProvider(SimpleNamespace(use_sqlite=False), frame)
    config, service, observed_dates = _service(tmp_path, provider)
    if persisted_policy:
        monkeypatch.setattr(personal_policy_module, "datetime", _PolicyConfirmationClock)
        policy = save_personal_use_policy(
            tmp_path / "personal-policy.json",
            RecommendationPersonalUseSelectionV1(
                scope_id="desktop-user",
                mode=RULE_ONLY_MODE,
            ),
            expected_revision=0,
        )
    else:
        policy = RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")
    service = service.with_personal_use_policy(policy)
    monkeypatch.setattr(recommendation_service_module, "datetime", _FrozenClock)

    execution = execute_module.execute_recommendation(
        service,
        _runtime_config(),
        max_stocks=1,
        top_n=1,
        result_id="personal-live-clock-20260927",
    )

    assert execution.status.value == "completed"
    assert provider.calls == 1
    assert observed_dates == [_SOURCE_DATE]
    assert execution.request.as_of_date == date.fromisoformat(_DECISION_DATE)
    assert execution.context.as_of_date == date.fromisoformat(_DECISION_DATE)
    assert execution.context.decision_at == _DECISION_CLOCK
    assert len(execution.context.data_snapshot_refs) == 1
    market_ref = execution.context.data_snapshot_refs[0]
    assert market_ref.kind is ReferenceKind.DATA_SNAPSHOT
    assert market_ref.version.endswith(f":{_SOURCE_DATE}")
    invocation_event = next(
        event
        for event in execution.events
        if event.event_type == "legacy_invocation_context"
    )
    assert market_ref.reference_id.removeprefix("sha256:") == (
        invocation_event.details["market_data_fingerprint"]
    )

    source_event = next(
        event
        for event in execution.events
        if event.event_type == "company_registry_source_snapshot"
    )
    assert source_event.details["snapshot"]["schema_version"] == (
        "recommendation-company-registry-source-snapshot.v2"
    )
    assert source_event.details["snapshot"]["decision_date"] == _DECISION_DATE
    assert source_event.details["snapshot"]["data_as_of_date"] == _SOURCE_DATE
    assert source_event.details["snapshot"]["market_data_fingerprint"] == (
        market_ref.reference_id.removeprefix("sha256:")
    )

    composition = build_recommendation_composition(config)
    composition.save_service.save_execution(execution)
    readback = composition.queries.get(execution.result_id)
    assert readback is not None
    assert readback.execution == execution
    assert readback.execution.context.as_of_date == date.fromisoformat(_DECISION_DATE)
    assert readback.execution.context.data_snapshot_refs == execution.context.data_snapshot_refs
    persisted_source_event = next(
        event
        for event in readback.execution.events
        if event.event_type == "company_registry_source_snapshot"
    )
    assert persisted_source_event.details["snapshot"]["data_as_of_date"] == _SOURCE_DATE


def test_prepare_recommendation_market_uses_decision_date_only_for_live_filtering() -> None:
    provider = object()
    prepared = prepare_recommendation_market(
        source_frame=_market_frame(),
        cutoff=None,
        decision_date=_DECISION_DATE,
        market_data_provider=provider,
    )

    assert prepared.decision_cutoff == _DECISION_DATE
    assert prepared.data_date == _SOURCE_DATE
    assert prepared.frame["日期"].max().date().isoformat() == _SOURCE_DATE
    assert prepared.market_data_fingerprint


def test_personal_live_empty_market_keeps_frozen_decision_clock_on_early_return(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    empty_frame = _market_frame().iloc[:0].copy()
    provider = _LiveFrameProvider(SimpleNamespace(use_sqlite=False), empty_frame)
    config, service, observed_dates = _service(tmp_path, provider)
    service = service.with_personal_use_policy(
        RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")
    )
    monkeypatch.setattr(recommendation_service_module, "datetime", _FrozenClock)

    execution = execute_module.execute_recommendation(
        service,
        _runtime_config(),
        max_stocks=1,
        top_n=1,
        result_id="personal-live-empty-market-20260927",
    )

    assert execution.status.value == "completed"
    assert execution.request.as_of_date == date.fromisoformat(_DECISION_DATE)
    assert execution.context.as_of_date == date.fromisoformat(_DECISION_DATE)
    assert execution.context.decision_at == _DECISION_CLOCK
    assert execution.decision.items == ()
    assert provider.calls == 1
    assert observed_dates == []

    policy_event = next(
        event
        for event in execution.events
        if event.event_type == "personal_use_policy_snapshot"
    )
    assert policy_event.details["decision_at"] == _DECISION_CLOCK

    composition = build_recommendation_composition(config)
    composition.save_service.save_execution(execution)
    readback = composition.queries.get(execution.result_id)
    assert readback is not None
    assert readback.execution == execution
    assert readback.execution.context.decision_at == _DECISION_CLOCK


@pytest.mark.parametrize(
    ("field", "bad_value"),
    (("decision_date", "2026-09-26"), ("data_as_of_date", "2026-09-23")),
)
def test_personal_live_company_snapshot_rejects_mismatched_date_bindings(
    tmp_path: Path,
    monkeypatch,
    field: str,
    bad_value: str,
) -> None:
    import app_module.recommendation_service as recommendation_service_module

    provider = _LiveFrameProvider(SimpleNamespace(use_sqlite=False), _market_frame())
    _config, service, _observed_dates = _service(tmp_path, provider)
    service = service.with_personal_use_policy(
        RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")
    )
    monkeypatch.setattr(recommendation_service_module, "datetime", _FrozenClock)
    original_finalize = recommendation_service_module.RecommendationService._finalize_current_industry_mapping_snapshot

    def mismatched_finalize(invocation) -> None:
        original_finalize(invocation)
        snapshot = invocation.last_run_context["industry_mapping_source_snapshot"]
        snapshot[field] = bad_value
        invocation._refresh_current_industry_mapping_snapshot_hash(snapshot)

    monkeypatch.setattr(
        recommendation_service_module.RecommendationService,
        "_finalize_current_industry_mapping_snapshot",
        mismatched_finalize,
    )

    with pytest.raises(ValueError, match="industry mapping source snapshot binding 無效"):
        execute_module.execute_recommendation(
            service,
            _runtime_config(),
            max_stocks=1,
            top_n=1,
            result_id=f"personal-live-bad-{field}",
        )


def test_legacy_input_session_keeps_original_prepare_market_keywords(
    tmp_path: Path,
) -> None:
    frame = _market_frame().iloc[:24].copy()
    provider = _LiveFrameProvider(SimpleNamespace(use_sqlite=False), frame)
    _config, service, _observed_dates = _service(tmp_path, provider)
    delegate_preparer = service.recommendation_input_preparer
    calls: list[tuple[str | None, Sequence[str] | None]] = []

    class _LegacySignatureSession:
        def __init__(self, delegate: Any) -> None:
            self._delegate = delegate

        def __getattr__(self, name: str) -> Any:
            return getattr(self._delegate, name)

        def prepare_market(
            self,
            *,
            cutoff: str | None,
            universe: Sequence[str] | None = None,
        ):
            calls.append((cutoff, universe))
            return self._delegate.prepare_market(
                cutoff=cutoff,
                universe=universe,
            )

    class _LegacySignaturePreparer:
        def __init__(self, delegate: Any) -> None:
            self._delegate = delegate

        def begin(self, *args: Any, **kwargs: Any) -> _LegacySignatureSession:
            return _LegacySignatureSession(self._delegate.begin(*args, **kwargs))

    service.recommendation_input_preparer = _LegacySignaturePreparer(
        delegate_preparer
    )

    execution = execute_module.execute_recommendation(
        service,
        _runtime_config(),
        max_stocks=1,
        top_n=1,
        result_id="legacy-input-session-signature",
    )

    assert execution.status.value == "completed"
    assert calls == [(None, None)]
    assert execution.context.as_of_date == date.fromisoformat(_SOURCE_DATE)
    assert execution.context.data_snapshot_refs == ()
    source_event = next(
        event
        for event in execution.events
        if event.event_type == "company_registry_source_snapshot"
    )
    assert source_event.details["snapshot"]["schema_version"] == (
        "recommendation-company-registry-source-snapshot.v1"
    )
    assert source_event.details["snapshot"]["data_as_of_date"] == _SOURCE_DATE
