"""原收藏摘要沿真公開讀回保留原觀察時間，不補現在時間或最新預測。"""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from app_module.recommendation.personal_h20_activation import publish_personal_h20_activation
from app_module.recommendation.personal_h20_bookmark_product_evidence import project_personal_h20_bookmark_product_evidence
from app_module.recommendation.personal_h20_research_bookmark import read_personal_h20_research_bookmark
from tests.test_personal_h20_research_bookmark import _fixture
from tests.test_personal_h20_research_cohort import public_reader


def _state(fixture, prediction_reader=public_reader):
    return read_personal_h20_research_bookmark(
        fixture["bookmark"], config_path=fixture["activation"].config_path,
        market_root=fixture["market_root"], prediction_reader=prediction_reader,
    )


def test_original_prediction_and_observation_clock_are_preserved(tmp_path):
    fixture = _fixture(tmp_path)
    state = _state(fixture)
    original = json.loads(Path(state.selected_row.capture_path).read_bytes())
    evidence = project_personal_h20_bookmark_product_evidence(state)
    assert evidence.gross_return_bp == 684
    assert evidence.observed_at == state.selected_row.observed_at == original["observed_at"]
    assert evidence.prediction_id == state.bookmark.selected_row.prediction_id
    assert evidence.feature_date == state.selected_row.feature_as_of_date


def test_disabled_model_still_shows_original_historical_prediction(tmp_path):
    fixture = _fixture(tmp_path)
    publish_personal_h20_activation(
        replace(fixture["activation"], enabled=False, revision=2),
        expected_revision=1, execute=True,
    )
    state = _state(fixture)
    assert state.current_model_binding_status == "disabled"
    evidence = project_personal_h20_bookmark_product_evidence(state)
    assert evidence.status == "available" and evidence.gross_return_bp == 684
    assert "目前個人模型停用" in evidence.reason
    assert "原保存研究" in evidence.reason


def test_missing_original_capture_does_not_publish_prediction_or_clock(tmp_path):
    fixture = _fixture(tmp_path)
    def missing(*args, **kwargs):
        raise ValueError("synthetic_original_capture_missing")
    evidence = project_personal_h20_bookmark_product_evidence(_state(fixture, missing))
    assert evidence.status == "unavailable"
    assert evidence.gross_return_bp is None and evidence.observed_at is None
    assert "synthetic_original_capture_missing" in evidence.reason


@pytest.mark.parametrize("field,value", [
    ("observed_at", None), ("feature_as_of_date", "2026-12-31"),
    ("source_date", "2026-12-31"), ("prediction_id", "different-prediction"),
])
def test_incomplete_future_or_mismatched_row_is_rejected(tmp_path, field, value):
    state = _state(_fixture(tmp_path))
    row = replace(state.selected_row, **{field: value})
    cohort = replace(state.cohort, rows=tuple(row if item.symbol == row.symbol else item for item in state.cohort.rows))
    with pytest.raises(ValueError):
        project_personal_h20_bookmark_product_evidence(replace(state, selected_row=row, cohort=cohort))
