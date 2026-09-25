"""Scheduled result config must retain typed cutoff provenance."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app_module.recommendation.contracts import (
    RecommendationResultConfigSnapshot,
    _validate_scheduled_result_config,
)
from app_module.recommendation.execute import _validate_postprocess_facts
from scripts.scheduled.scheduled_clock import SCHEDULE_TIMEZONE
from test_r019_postprocess_typed_facts import (
    CREATED_AT,
    _body_result,
    _postprocess_input,
    _scheduled_callback,
    _scheduled_date_from_created_at,
)
from scripts.scheduled.run_scheduled_recommendation_snapshot import (
    _build_scheduled_postprocess_callback,
)


_TYPED_CUTOFF_KEYS = (
    "data_as_of_date",
    "temporal_mode",
    "cutoff_selection",
    "cutoff_policy",
)


@pytest.fixture(autouse=True)
def _isolated_temp_test_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROFILE", "test")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "output"))


def _result_config(facts: Any) -> dict[str, object]:
    return json.loads(facts.result_config_snapshot.raw_result_config_json)


def _facts_with_config(facts: Any, config: dict[str, object]) -> Any:
    raw = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return replace(
        facts,
        result_config_snapshot=RecommendationResultConfigSnapshot(
            raw_result_config_json=raw,
            config_sha256=digest,
        ),
    )


def test_scheduled_callback_projects_typed_cutoff_and_keeps_run_date_distinct() -> None:
    body_result, rows = _body_result()
    facts = _scheduled_callback(body_result, rows)
    config = _result_config(facts)

    assert config["data_as_of_date"] == body_result.context.as_of_date
    assert config["temporal_mode"] == body_result.context.temporal_mode
    assert config["cutoff_selection"] == body_result.context.cutoff_selection
    assert config["cutoff_policy"] == body_result.context.cutoff_policy
    assert config["decision_date"] == _scheduled_date_from_created_at(CREATED_AT)
    assert config["decision_date"] != config["data_as_of_date"]
    _validate_postprocess_facts(
        facts=facts,
        body_result=body_result,
        scheduled=True,
    )


@pytest.mark.parametrize("key", _TYPED_CUTOFF_KEYS)
def test_scheduled_postprocess_rejects_missing_typed_cutoff_keys(key: str) -> None:
    body_result, rows = _body_result()
    facts = _scheduled_callback(body_result, rows)
    config = _result_config(facts)
    del config[key]

    with pytest.raises(ValueError, match=f"缺少同次 typed {key}"):
        _validate_postprocess_facts(
            facts=_facts_with_config(facts, config),
            body_result=body_result,
            scheduled=True,
        )


@pytest.mark.parametrize("key", _TYPED_CUTOFF_KEYS)
def test_scheduled_postprocess_rejects_contradictory_typed_cutoff_keys(key: str) -> None:
    body_result, rows = _body_result()
    facts = _scheduled_callback(body_result, rows)
    config = _result_config(facts)
    config[key] = "wrong-typed-cutoff"

    with pytest.raises(ValueError, match=f"{key} 與 typed BodyResult 不一致"):
        _validate_postprocess_facts(
            facts=_facts_with_config(facts, config),
            body_result=body_result,
            scheduled=True,
        )


def test_scheduled_decision_date_is_bound_to_invocation_start_not_market_cutoff() -> None:
    body_result, rows = _body_result()
    facts = _scheduled_callback(body_result, rows)
    config = _result_config(facts)
    assert config["decision_date"] == _scheduled_date_from_created_at(CREATED_AT)
    assert config["decision_date"] != body_result.context.as_of_date

    config["decision_date"] = "2099-01-01"
    with pytest.raises(
        ValueError,
        match="decision_date 必須符合同次 invocation created_at 排程日期",
    ):
        _validate_postprocess_facts(
            facts=_facts_with_config(facts, config),
            body_result=body_result,
            scheduled=True,
        )


def test_scheduled_start_and_completion_crossing_midnight_keeps_start_date() -> None:
    created_at = datetime.fromisoformat("2026-09-22T23:59:59-07:00")
    decision_at = datetime.fromisoformat("2026-09-23T00:00:01-07:00")
    body_result, rows = _body_result(decision_at=decision_at)
    facts = _scheduled_callback(body_result, rows, created_at=created_at)
    config = _result_config(facts)

    assert config["decision_date"] == "2026-09-22"
    assert (
        datetime.fromisoformat(body_result.context.decision_at)
        .astimezone(SCHEDULE_TIMEZONE)
        .date()
        .isoformat()
        == "2026-09-23"
    )
    _validate_postprocess_facts(
        facts=facts,
        body_result=body_result,
        scheduled=True,
    )

    config["decision_date"] = "2026-09-23"
    with pytest.raises(
        ValueError,
        match="decision_date 必須符合同次 invocation created_at 排程日期",
    ):
        _validate_postprocess_facts(
            facts=_facts_with_config(facts, config),
            body_result=body_result,
            scheduled=True,
        )


def test_conflicting_caller_cutoff_cannot_override_typed_body_context() -> None:
    body_result, rows = _body_result()
    callback = _build_scheduled_postprocess_callback(
        caller_config={"cutoff_selection": "caller-conflict"},
        decision_date=_scheduled_date_from_created_at(CREATED_AT),
        max_stocks=10,
        top_n=1,
    )

    with pytest.raises(ValueError, match="caller config cutoff_selection"):
        callback(_postprocess_input(body_result, rows))


def test_old_scheduled_result_config_remains_readable_without_new_cutoff_keys() -> None:
    body_result, rows = _body_result()
    facts = _scheduled_callback(body_result, rows)
    legacy_config = _result_config(facts)
    for key in _TYPED_CUTOFF_KEYS:
        legacy_config.pop(key)

    # Decoder compatibility for already-saved recommendation-result-config.v1.
    _validate_scheduled_result_config(legacy_config)
