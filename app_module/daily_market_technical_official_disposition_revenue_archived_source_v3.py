"""原 F17／月營收來源的明示封存入口；收藏保留原外部來源錨點。"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from threading import get_ident
from typing import Any, Callable, Literal, NoReturn, Sequence, cast
import weakref

from app_module.daily_market_monthly_revenue_archive_reference_artifact_v4 import (
    DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
    UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4,
    publish_daily_market_monthly_revenue_archive_reference_artifact_v4,
    read_daily_market_monthly_revenue_archive_reference_artifact_v4,
)
from app_module.daily_market_technical_official_disposition_revenue_archived_recipe_v3 import (
    DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
)
from app_module.daily_market_technical_official_disposition_revenue_source_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
    DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled,
    _canonical_bytes, _guard_operation_root, _open_and_publish_v2, _poll_cancel,
    _stable_reference_matches, _validate_reader_and_provider, _validate_cutoff_and_pin,
    open_daily_market_technical_official_disposition_revenue_bundle_source_v2,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
)
from app_module.daily_market_technical_official_disposition_query_reader_v1 import DailyMarketTechnicalOfficialDispositionQueryV1
from data_module.daily_monthly_revenue_cohort import DailyMonthlyRevenueCohortPin, DailyMonthlyRevenueCohortReader
from data_module.daily_market_monthly_revenue_cohort_v2 import DailyMarketMonthlyRevenueSourceReferenceV3, decode_daily_market_monthly_revenue_source_reference_v3
from data_module.recommendation_current_fundamental_provider import RecommendationCurrentFundamentalProvider


_ISSUER = object()
_ISSUED: dict[int, tuple[weakref.ReferenceType[DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3], str]] = {}


class DailyMarketTechnicalOfficialDispositionRevenueArchivedSourceV3Error(ValueError):
    """封存交叉來源、完整清冊或外部錨點無法驗證。"""


def _fail(reason: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueArchivedSourceV3Error(f"revenue_archive_v3_{reason}")


def _close_after_error(core: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
                       error: BaseException) -> None:
    try:
        core.close()
    except BaseException as cleanup:
        raise BaseExceptionGroup("封存來源失敗及關閉失敗", [error, cleanup]) from error


class DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
    """持有真正 V2 query 結果；封存來源與保存 recipe 使用獨立版本。"""

    __slots__ = ("_core", "_recipe", "_descriptor", "_identity", "_owner", "__weakref__")

    def __init__(self, *, core: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
                 recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3,
                 descriptor: DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4,
                 issuer: object) -> None:
        if (issuer is not _ISSUER or type(core) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV2
                or type(recipe) is not DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3
                or type(descriptor) is not DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4):
            _fail("issued_source_required")
        core._validate_open()
        base = recipe.base_recipe
        original_reference = decode_daily_market_monthly_revenue_source_reference_v3(
            base.monthly_source_reference_json,
            expected_reference_sha256=base.monthly_source_reference_external_sha256).reference
        if (not _stable_reference_matches(core.monthly_reference, original_reference)
                or descriptor.external_descriptor_sha256 != recipe.archive_artifact_descriptor_external_sha256
                or descriptor.to_json() != recipe.archive_artifact_descriptor_json
                or core.f17_query.to_json() != base.f17_query_json):
            _fail("finished_source_does_not_match_original_archive_recipe")
        self._core = core
        self._recipe = recipe
        self._descriptor = descriptor
        self._owner = get_ident()
        self._identity = sha256(_canonical_bytes({
            "schema_version": "daily-market-technical-official-disposition-revenue-archived-source.v3",
            "archive_descriptor_sha256": recipe.archive_artifact_descriptor_external_sha256,
            "archive_reference_sha256": recipe.archive_reference_external_sha256,
            "original_reference_sha256": base.monthly_source_reference_external_sha256,
            "original_descriptor_sha256": base.artifact_descriptor_external_sha256,
            "f17_query_json": base.f17_query_json,
            "revenue_query_json": base.revenue_query_json,
        })).hexdigest()
        key = id(self)

        def remove_reference(reference: weakref.ReferenceType[DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3]) -> None:
            current = _ISSUED.get(key)
            if current is not None and current[0] is reference:
                _ISSUED.pop(key, None)

        _ISSUED[key] = (weakref.ref(self, remove_reference), self._fingerprint())

    def _fingerprint(self) -> str:
        return sha256(_canonical_bytes({
            "core_identity": self._core.source_pair_identity_sha256,
            "recipe": self._recipe.to_dict(), "descriptor": self._descriptor.to_dict(),
            "identity": self._identity, "owner": self._owner,
        })).hexdigest()

    def _validate_open(self) -> None:
        if get_ident() != self._owner:
            _fail("owner_thread_mismatch")
        record = _ISSUED.get(id(self))
        if record is None or record[0]() is not self or record[1] != self._fingerprint():
            _fail("source_not_issued_or_mutated")
        self._core._validate_open()

    @property
    def closed(self) -> bool:
        return self._core.closed

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        self._validate_open()
        return self._core.query

    @property
    def result(self) -> DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2:
        self._validate_open()
        return self._core.result

    @property
    def request(self) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        self._validate_open()
        return self._core.request

    @property
    def page(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        self._validate_open()
        return self._core.page

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        self._validate_open()
        return self._core.f17_query

    @property
    def monthly_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        self._validate_open()
        return self._core.monthly_reference

    @property
    def monthly_cohort_pin(self) -> DailyMonthlyRevenueCohortPin:
        self._validate_open()
        return self._core.monthly_cohort_pin

    @property
    def artifact_descriptor(self) -> DailyMarketMonthlyRevenueArchiveReferenceArtifactDescriptorV4:
        self._validate_open()
        return self._descriptor

    @property
    def source_pair_identity_sha256(self) -> str:
        self._validate_open()
        return self._identity

    @property
    def monthly_sqlite_connection_closed(self) -> bool:
        self._validate_open()
        return self._core.monthly_sqlite_connection_closed

    @property
    def source_scope(self) -> Literal["current_only"]:
        self._validate_open()
        return "current_only"

    @property
    def availability_status(self) -> Literal["unknown"]:
        self._validate_open()
        return "unknown"

    @property
    def monthly_availability_status(self) -> Literal["cohort_hour_bound"]:
        self._validate_open()
        return "cohort_hour_bound"

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        self._validate_open()
        return False

    @property
    def formal_pit_eligible(self) -> Literal[False]:
        self._validate_open()
        return False

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        self._validate_open()
        return self._recipe.with_page(page_index=self.request.page_index, page_size=self.request.page_size)

    def read_page(self, page_index: int, page_size: int, *,
                  cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        self._validate_open()
        return self._core.read_page(page_index, page_size=page_size, cancel_callback=cancel_callback)

    def read_page_request(self, request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2, *,
                          cancel_callback: Callable[[], object] | None = None) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        self._validate_open()
        return self._core.read_page_request(request, cancel_callback=cancel_callback)

    def close(self) -> None:
        if get_ident() != self._owner:
            _fail("owner_thread_mismatch")
        self._core.close()

    def __enter__(self) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
        self._validate_open()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None, traceback: object) -> Literal[False]:
        return self._core.__exit__(exc_type, exc, traceback)


def open_daily_market_technical_official_disposition_revenue_archived_bundle_source_v3(
    *, archive_parent: Path, archived_reference_artifact_root: Path,
    archived_artifact_id: str, **options: Any,
) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
    """真正完成原來源／投影後，保存封存原件與交叉錨定的 recipe。"""
    core = open_daily_market_technical_official_disposition_revenue_bundle_source_v2(**options)
    try:
        index_session = core._state.monthly_index_session
        if index_session is None or not index_session.finished:
            _fail("completed_monthly_index_required")
        cancel = cast(Callable[[], bool] | None, options.get("cancel_callback"))
        archive = index_session.archive_monthly_raw_sources(archive_parent, cancel_callback=cancel)
        archive_sha = sha256(archive.to_json().encode("utf-8")).hexdigest()
        descriptor = publish_daily_market_monthly_revenue_archive_reference_artifact_v4(
            archived_reference_artifact_root, artifact_id=archived_artifact_id, index_session=index_session,
            original_artifact_root=options["monthly_reference_artifact_root"],
            original_descriptor=core.artifact_descriptor,
            expected_original_descriptor_sha256=core.artifact_descriptor.external_descriptor_sha256,
            raw_archive_reference=archive, expected_archive_reference_sha256=archive_sha,
            monthly_provider=index_session._provider, daily_monthly_cohort_reader=index_session._reader,
            protected_roots=options["protected_roots"], cancel_callback=cancel)
        recipe = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.create(
            base_recipe=core.saved_recipe, archive_descriptor=descriptor,
            expected_archive_descriptor_sha256=descriptor.external_descriptor_sha256,
            expected_archive_reference_sha256=archive_sha)
        # V4 已通過最後提交 gate；不能以後到取消撤銷已完成的發行。
        return DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3(
            core=core, recipe=recipe, descriptor=descriptor, issuer=_ISSUER)
    except BaseException as error:
        _close_after_error(core, error)
        raise


def reopen_daily_market_technical_official_disposition_revenue_archived_from_recipe_v3(
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3 | bytes | str, *,
    operation_root: Path | str, monthly_provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    monthly_reference_artifact_root: Path, artifact_id: str,
    archived_reference_artifact_root: Path, expected_archive_descriptor_sha256: str,
    expected_archive_reference_sha256: str, expected_monthly_source_reference_sha256: str,
    protected_roots: Sequence[Path], cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3:
    _poll_cancel(cancel_callback)
    if type(saved_recipe) is DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3:
        recipe = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(saved_recipe.to_json())
    elif type(saved_recipe) is bytes or type(saved_recipe) is str:
        recipe = DailyMarketTechnicalOfficialDispositionRevenueArchivedSavedRecipeV3.from_json(saved_recipe)
    else:
        _fail("archived_recipe_type_invalid")
    base = recipe.base_recipe
    if (expected_archive_descriptor_sha256 != recipe.archive_artifact_descriptor_external_sha256
            or expected_archive_reference_sha256 != recipe.archive_reference_external_sha256
            or expected_monthly_source_reference_sha256 != base.monthly_source_reference_external_sha256):
        _fail("external_archive_anchors_do_not_match_saved_recipe")
    artifact = read_daily_market_monthly_revenue_archive_reference_artifact_v4(
        archived_reference_artifact_root, descriptor=recipe.archive_artifact_descriptor_json.encode("utf-8"),
        expected_descriptor_sha256=expected_archive_descriptor_sha256, protected_roots=protected_roots)
    if type(artifact) is not UnverifiedDailyMarketMonthlyRevenueArchiveReferenceArtifactV4:
        _fail("archive_artifact_reader_returned_wrong_type")
    reference = artifact.source_reference.reference
    archive = artifact.raw_archive_reference.reference
    if (artifact.source_reference.external_reference_sha256 != expected_monthly_source_reference_sha256
            or artifact.raw_archive_reference.external_reference_sha256 != expected_archive_reference_sha256
            or reference.to_json() != base.monthly_source_reference_json
            or artifact.original_descriptor.to_json() != base.artifact_descriptor_json
            or artifact.descriptor.external_descriptor_sha256 != expected_archive_descriptor_sha256):
        _fail("archive_artifact_does_not_match_original_saved_source")
    if _validate_reader_and_provider(provider=monthly_provider, reader=daily_monthly_cohort_reader) != reference.cohort_pin:
        _fail("saved_full_daily_pin_mismatch")
    from app_module.daily_market_technical_official_disposition_query_v1 import DailyMarketTechnicalOfficialDispositionQueryV1
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import open_daily_market_technical_official_disposition_read_session_v1
    from app_module.daily_market_technical_official_disposition_revenue_query_v2 import DailyMarketTechnicalOfficialDispositionRevenueQueryV2
    f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(base.f17_query_json)
    old_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(base.revenue_query_json)
    old_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(base.page_request_json)
    _validate_cutoff_and_pin(f17_query, reference.cohort_pin)
    f17_session = open_daily_market_technical_official_disposition_read_session_v1(f17_query, cancel_callback=cancel_callback)
    if f17_session is None:
        _fail("original_f17_session_unavailable")
    if f17_session.query.to_json() != base.f17_query_json:
        _fail("original_f17_query_changed")
    if f17_session.verified_declared_stock_codes(cancel_callback=cancel_callback) != reference.declared_stock_codes:
        _fail("original_f17_declared_full_cohort_changed")
    root = _guard_operation_root(operation_root, f17_query=f17_query, reader=daily_monthly_cohort_reader,
        provider=monthly_provider, artifact_root=monthly_reference_artifact_root, protected_roots=protected_roots)
    core = _open_and_publish_v2(f17_query=f17_query, f17_session=f17_session, provider=monthly_provider,
        daily_reader=daily_monthly_cohort_reader, pin=reference.cohort_pin,
        cutoff=f17_query.decision_cutoff, declared_codes=reference.declared_stock_codes,
        operation_root=root, monthly_reference_artifact_root=monthly_reference_artifact_root,
        artifact_id=artifact_id, protected_roots=protected_roots, expected_reference=reference,
        expected_reference_sha256=expected_monthly_source_reference_sha256,
        recipe_inputs=(old_query.ma_query.ma_states, old_query.minimum_yoy_percent, old_query.condition_combine_mode,
                       old_query.unknown_policy, old_query.sort_clauses),
        saved_query=old_query, saved_request=old_request, cancel_callback=cancel_callback,
        page_index=base.page_index, page_size=base.page_size, saved_recipe=base,
        archived_reference=archive, expected_archive_reference_sha256=expected_archive_reference_sha256)
    try:
        # 完整 consumer 與 V3 發行已成功；後到取消不撤銷此 token。
        return DailyMarketTechnicalOfficialDispositionRevenueArchivedExactReadV3(
            core=core, recipe=recipe, descriptor=artifact.descriptor, issuer=_ISSUER)
    except BaseException as error:
        _close_after_error(core, error)
        raise
