from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("test_daily_market_technical_official_disposition_bundle_v1",)

from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import (
    decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4,
    publish_daily_market_monthly_revenue_archive_reference_artifact_v4,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_recipe_v3 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error,
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2,
    DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2,
)
from tests.test_daily_market_technical_official_disposition_revenue_query_v2 import (
    _daily_f17_environment,
)
from tests.test_daily_market_technical_official_disposition_revenue_source_v2 import (
    _PROTECTED_ROOTS,
    _open_bundle,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def archived_recipe_case(
    bundle_fixture: Any,
    tmp_path_factory: pytest.TempPathFactory,
) -> Any:
    """用既有完整 V2 reader 與 publisher 建立一份真正綁定的 archive recipe。"""

    root = tmp_path_factory.mktemp("archived-recipe-v3")
    provider, reader, _pin, _market_readers, _market_roots = _daily_f17_environment(
        root / "daily-source",
    )
    v3_root = root / "monthly-reference-v3"
    opened = _open_bundle(
        bundle_fixture,
        provider=provider,
        reader=reader,
        operation_root=root / "f17-operation",
        artifact_root=v3_root,
        artifact_id="original-monthly-reference",
    )
    try:
        index_session = opened._state.monthly_index_session
        assert index_session is not None
        archive_reference = index_session.archive_monthly_raw_sources(root / "raw-archive")
        archive_reference_raw = archive_reference.to_json().encode("utf-8")
        archive_reference_sha256 = _sha(archive_reference_raw)

        v4_root = root / "monthly-archive-v4"
        v4_root.mkdir()
        archive_descriptor = publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
            v4_root,
            artifact_id="archived-monthly-source",
            index_session=index_session,
            original_artifact_root=v3_root,
            original_descriptor=opened.artifact_descriptor,
            expected_original_descriptor_sha256=opened.artifact_descriptor.external_descriptor_sha256,
            raw_archive_reference=archive_reference,
            expected_archive_reference_sha256=archive_reference_sha256,
            monthly_provider=provider,
            daily_monthly_cohort_reader=reader,
            protected_roots=_PROTECTED_ROOTS,
        )
        recipe = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.create(
            opened.saved_recipe,
            archive_descriptor,
            expected_archive_descriptor_sha256=archive_descriptor.external_descriptor_sha256,
            expected_archive_reference_sha256=archive_reference_sha256,
        )
        yield {
            "opened": opened,
            "base": opened.saved_recipe,
            "descriptor": archive_descriptor,
            "archive_sha": archive_reference_sha256,
            "recipe": recipe,
        }
    finally:
        opened.close()


def test_archived_recipe_roundtrip_keeps_original_v2_binding_and_page_seam(
    archived_recipe_case: Any,
) -> None:
    recipe = archived_recipe_case["recipe"]
    base = archived_recipe_case["base"]
    reopened = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(
        recipe.to_json()
    )
    assert reopened.to_json() == recipe.to_json()
    assert reopened.base_recipe.to_json() == base.to_json()
    assert reopened.base_recipe.artifact_descriptor_external_sha256 == base.artifact_descriptor_external_sha256
    assert reopened.base_recipe.monthly_source_reference_external_sha256 == base.monthly_source_reference_external_sha256
    assert reopened.archive_reference_external_sha256 == archived_recipe_case["archive_sha"]
    assert reopened.archive_artifact_descriptor.is_writer_issued is False
    assert reopened.archive_artifact_descriptor.historical_pit_eligible is False
    assert reopened.archive_artifact_descriptor.formal_pit_eligible is False

    next_page = reopened.with_page(1, 8)
    next_base = next_page.base_recipe
    assert next_base.page_index == 1
    assert next_base.page_size == 8
    assert next_base.f17_query_json == base.f17_query_json
    assert next_base.revenue_query_json == base.revenue_query_json
    assert next_base.monthly_source_reference_json == base.monthly_source_reference_json
    assert next_base.monthly_source_reference_external_sha256 == base.monthly_source_reference_external_sha256
    assert next_base.artifact_descriptor_json == base.artifact_descriptor_json
    assert next_base.artifact_descriptor_external_sha256 == base.artifact_descriptor_external_sha256
    assert next_page.archive_artifact_descriptor_json == reopened.archive_artifact_descriptor_json
    assert next_page.archive_reference_external_sha256 == reopened.archive_reference_external_sha256
    assert next_page.recipe_identity_sha256 != reopened.recipe_identity_sha256
    assert reopened.base_recipe.page_index == base.page_index


def test_archived_recipe_requires_writer_issued_v4_and_rejects_legacy_recipe_schemas(
    archived_recipe_case: Any,
) -> None:
    recipe = archived_recipe_case["recipe"]
    base = archived_recipe_case["base"]
    descriptor = archived_recipe_case["descriptor"]
    raw_descriptor = descriptor.to_bytes()
    decoded = decode_daily_market_monthly_revenue_archive_reference_artifact_descriptor_v4(
        raw_descriptor,
        descriptor.external_descriptor_sha256,
    )
    assert decoded.is_writer_issued is False
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.create(
            base,
            decoded,
            expected_archive_descriptor_sha256=descriptor.external_descriptor_sha256,
            expected_archive_reference_sha256=recipe.archive_reference_external_sha256,
        )

    assert base.to_dict()["schema_version"] == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(
            base.to_json()
        )

    # 舊版標記不得走成 Archived V3；缺少 V3 envelope 欄位時明確拒絕。
    legacy_v1 = _canonical_bytes(
        {"schema_version": "daily-market-technical-official-disposition-revenue-saved-recipe.v1"}
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(legacy_v1)


def test_archived_recipe_rejects_rehashed_archive_reference_and_descriptor_mismatches(
    archived_recipe_case: Any,
) -> None:
    recipe = archived_recipe_case["recipe"]
    base = recipe.to_dict()
    base.pop("recipe_identity_sha256")
    base["archive_reference_external_sha256"] = "0" * 64
    raw = _canonical_bytes(base)
    forged_pointer = {
        **base,
        "recipe_identity_sha256": _sha(raw),
    }
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_dict(
            forged_pointer
        )

    descriptor = json.loads(recipe.archive_artifact_descriptor_json)
    descriptor["original_descriptor_sha256"] = "f" * 64
    forged_descriptor_raw = _canonical_bytes(descriptor)
    forged_body = recipe.to_dict()
    forged_body.pop("recipe_identity_sha256")
    forged_body["archive_artifact_descriptor_json"] = forged_descriptor_raw.decode("utf-8")
    forged_body["archive_artifact_descriptor_external_sha256"] = _sha(forged_descriptor_raw)
    forged_payload = {
        **forged_body,
        "recipe_identity_sha256": _sha(_canonical_bytes(forged_body)),
    }
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_dict(
            forged_payload
        )


def test_archived_recipe_codec_rejects_duplicate_extra_float_depth_and_bad_identity(
    archived_recipe_case: Any,
) -> None:
    recipe = archived_recipe_case["recipe"]
    canonical = recipe.to_json()
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(
            '{"schema_version":"x","schema_version":"y"}'
        )

    extra = recipe.to_dict()
    extra["unrecognized"] = "must not be ignored"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_dict(extra)

    floating = canonical.replace(
        '"archive_reference_external_sha256":"',
        '"archive_reference_external_sha256":0.5,"ignored":"',
        1,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(floating)

    too_deep = b'{"nested":' + (b"[" * 50) + b"0" + (b"]" * 50) + b"}"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(too_deep)

    wrong_identity = recipe.to_dict()
    wrong_identity["recipe_identity_sha256"] = "1" * 64
    with pytest.raises(DailyMarketTechnicalOfficialDispositionRevenueArchivedRecipeV3Error):
        DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_dict(
            wrong_identity
        )


def test_archived_recipe_v3_schema_marker_is_exact(archived_recipe_case: Any) -> None:
    payload = archived_recipe_case["recipe"].to_dict()
    assert payload["schema_version"] == DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_ARCHIVED_RECIPE_SCHEMA_V3
