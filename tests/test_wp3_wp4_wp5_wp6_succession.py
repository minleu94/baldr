from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app_module.monthly_revenue_research_service import (
    MonthlyRevenueResearchService,
    MonthlyRevenueUse,
)
from data_module.formal_runtime_config import _normalise_environment_value
from data_module.formal_runtime_roll_forward import _resolve_calendar_bundle_for_observed
from data_module.monthly_revenue_unit_scale_proof import (
    build_mops_monthly_revenue_period_scale_proof,
    build_openapi_mops_cross_source_parity_proof,
)
from data_module.scheduled_research_acquisition_binding import (
    _path_matches_relocated,
    verify_weekly_acquisition,
)
from scripts.scheduled.run_formal_pit_sidecar_postcutoff import _find_taxonomy_bundle
from tests.test_mops_monthly_revenue_history import _capture
from tests.test_monthly_revenue_unit_scale_proof import _table

ROOT = Path(__file__).resolve().parents[1]


def test_wp3_calendar_successor_chain_and_taxonomy_split_v2_resolution():
    anchor = (
        ROOT
        / "output"
        / "formal_daily_publications"
        / "calendar_candidate_archive"
        / "2026-09-09"
        / "1b6227dd0464eded-aff4c96e1edab151"
        / "v4_calendar_20260909_20260908_104849140.json"
    )
    if not anchor.is_file():
        pytest.skip("Calendar anchor not present")
    pub_root = (ROOT / "output" / "formal_daily_publications").resolve()
    resolved, diag = _resolve_calendar_bundle_for_observed(
        anchor,
        publication_root=pub_root,
        observed=datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc),
    )
    assert resolved is not None
    assert diag["status"] == "anchor_or_successor_selected"
    assert "calendar_2026-10-01_2026-10-31.json" in resolved.name

    tax_bundle = _find_taxonomy_bundle(pub_root, target_date=date(2026, 10, 8))
    assert tax_bundle is not None
    assert "pit_taxonomy_preopen_split_v2" in str(tax_bundle)


def test_wp3_normalise_environment_value_resolves_calendar_and_clock_keys():
    cal_path = ROOT / "output" / "formal_daily_publications"
    norm = _normalise_environment_value(
        "FORMAL_DAILY_ROLLING_CALENDAR_BUNDLE", str(cal_path)
    )
    assert norm.casefold() == str(cal_path.resolve()).casefold()


def test_wp5_period_scale_proof_and_scoring_ranking_projector():
    html_bytes = (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>"
        "<h1>上市公司115年8月份月營業收入彙總表</h1>"
        "<p>出表日期：115/09/11</p>"
        + _table("半導體業", "2330", "千元")
        + "</body></html>"
    ).encode("utf-8")
    cap = _capture(market="twse", period="2026-08", html=html_bytes)
    proof = build_mops_monthly_revenue_period_scale_proof(cap)
    assert proof.market == "twse"
    assert proof.period == "2026-08"
    assert proof.row_count == 1
    assert proof.to_dict()["scale_to_base_unit"] == 1000
    assert proof.to_dict()["currency"] == "unknown"


def test_wp6_missing_original_drive_is_not_custody():
    fa_output = Path(r"F:\Min\Python\Project\FA_Data\output")
    assert not _path_matches_relocated(
        r"D:\Min\Python\Project\FA_Data\output", fa_output
    )
    assert _path_matches_relocated(str(fa_output), fa_output)
