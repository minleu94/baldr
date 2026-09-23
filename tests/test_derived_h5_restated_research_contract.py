from __future__ import annotations

from dataclasses import replace

import pytest

from ml_module.allocation_contracts import (
    AllocationWeightContract,
    CausalPortfolioState,
    PITFeatureValue,
    PortfolioMLDatasetRow,
)
from ml_module.derived_h5_restated_research_contract import (
    DERIVED_H5_FEATURE_ORDER,
    FEATURE_ORDER_HASH,
    FEATURE_REGISTRY_HASH,
    HORIZON_DAYS,
    REQUIRED_SOURCE_HASH_KEYS,
    RUN02_REVISION_ID,
    RUN02_SNAPSHOT_HASH,
    DerivedH5ResearchCandidateEvidence,
    DerivedH5RestatedResearchRow,
    RestatedH5FeatureVector,
    RestatedH5FoldIdentity,
    RestatedH5LabelEvidence,
    RestatedH5SourceIdentity,
    dataset_identity_hash,
    feature_mask_hash,
    feature_values_hash,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _source_identity(
    *, source_hashes_override: dict[str, str] | None = None
) -> RestatedH5SourceIdentity:
    source_hashes = {
        key: _digest(chr(ord("a") + index % 6))
        for index, key in enumerate(sorted(REQUIRED_SOURCE_HASH_KEYS))
    }
    source_hashes["run02_snapshot"] = RUN02_SNAPSHOT_HASH
    if source_hashes_override is not None:
        source_hashes.update(source_hashes_override)
    ordered_hashes = tuple(sorted(source_hashes.items()))
    dataset_id = "restated-derived-h5-20260922-synthetic"
    identity_hash = dataset_identity_hash(
        dataset_id=dataset_id,
        source_revision_id=RUN02_REVISION_ID,
        source_hashes=ordered_hashes,
    )
    return RestatedH5SourceIdentity(
        dataset_id=dataset_id,
        source_revision_id=RUN02_REVISION_ID,
        source_hashes=ordered_hashes,
        dataset_identity_sha256=identity_hash,
    )


def _feature_vector(
    *,
    values_i64: tuple[int | None, ...] | None = None,
    observed_mask: tuple[bool, ...] | None = None,
) -> RestatedH5FeatureVector:
    values = values_i64 or tuple(100 + index for index in range(62))
    mask = observed_mask or tuple(value is not None for value in values)
    scales = tuple(1 for _ in range(62))
    return RestatedH5FeatureVector(
        feature_order=DERIVED_H5_FEATURE_ORDER,
        feature_order_sha256=FEATURE_ORDER_HASH,
        feature_registry_sha256=FEATURE_REGISTRY_HASH,
        values_i64=values,
        scales=scales,
        observed_mask=mask,
        values_sha256=feature_values_hash(values_i64=values, scales=scales),
        mask_sha256=feature_mask_hash(observed_mask=mask),
    )


def _label(**overrides: object) -> RestatedH5LabelEvidence:
    values: dict[str, object] = {
        "horizon_days": HORIZON_DAYS,
        "horizon_end_date": "2026-05-27",
        "authoritative_available_at": "2026-06-02T00:00:00+00:00",
        "label_value_sha256": _digest("7"),
        "availability_evidence_sha256": _digest("8"),
        "corporate_action_affected": False,
    }
    values.update(overrides)
    return RestatedH5LabelEvidence(**values)  # type: ignore[arg-type]


def _fold(
    source_identity: RestatedH5SourceIdentity,
    **overrides: object,
) -> RestatedH5FoldIdentity:
    source_hashes = dict(source_identity.source_hashes)
    values: dict[str, object] = {
        "fold_id": "synthetic-fold-01",
        "fold_manifest_sha256": source_hashes["fold_manifest"],
        "train_start_date": "2014-01-01",
        "train_end_date": "2026-06-30",
        "test_start_date": "2026-07-15",
        "test_end_date": "2026-08-31",
        "purge_trading_days": 60,
        "embargo_trading_days": 5,
        "row_role": "train",
    }
    values.update(overrides)
    return RestatedH5FoldIdentity(**values)  # type: ignore[arg-type]


def _research_row(**overrides: object) -> DerivedH5RestatedResearchRow:
    source_identity = _source_identity()
    values: dict[str, object] = {
        "row_id": "synthetic:0050:2026-05-20",
        "historical_decision_at": "2026-05-20T08:30:00+08:00",
        "revision_observed_at": "2026-09-22T07:30:49+00:00",
        "training_as_of": "2026-09-23T00:00:00+00:00",
        "source_identity": source_identity,
        "features": _feature_vector(),
        "label": _label(),
        "fold": _fold(source_identity),
    }
    values.update(overrides)
    return DerivedH5RestatedResearchRow(**values)  # type: ignore[arg-type]


def test_late_revision_is_only_a_future_research_candidate() -> None:
    row = _research_row()

    assert row.research_only is True
    assert row.historical_pit is False
    assert row.formal_oos is False
    assert row.promotion is False
    assert row.production is False
    assert not hasattr(row, "fit_eligible")
    with pytest.raises(TypeError):
        _research_row(formal_oos=True)


def test_feature_vector_is_fixed_to_derived_h5_order_registry_and_hashes() -> None:
    assert len(DERIVED_H5_FEATURE_ORDER) == 62
    with pytest.raises(ValueError, match="feature order"):
        replace(
            _feature_vector(),
            feature_order=tuple(reversed(DERIVED_H5_FEATURE_ORDER)),
        )
    with pytest.raises(ValueError, match="feature_order_sha256"):
        replace(_feature_vector(), feature_order_sha256=_digest("9"))
    with pytest.raises(ValueError, match="registry"):
        replace(_feature_vector(), feature_registry_sha256=_digest("9"))
    with pytest.raises(ValueError, match="values_sha256"):
        replace(_feature_vector(), values_sha256=_digest("9"))
    with pytest.raises(ValueError, match="mask_sha256"):
        replace(_feature_vector(), mask_sha256=_digest("9"))


def test_feature_dtype_and_missing_mask_are_explicit() -> None:
    values = (None, *tuple(100 + index for index in range(1, 62)))
    mask = (False, *tuple(True for _ in range(61)))
    features = _feature_vector(values_i64=values, observed_mask=mask)
    assert features.dtype == "int64"
    assert features.values_i64[0] is None
    with pytest.raises(ValueError, match="value and mask disagree"):
        replace(features, observed_mask=(True, *mask[1:]))
    with pytest.raises(TypeError, match="int64"):
        replace(features, values_i64=(1.5, *features.values_i64[1:]))
    with pytest.raises(ValueError, match="signed int64"):
        replace(features, values_i64=(2**63, *features.values_i64[1:]))


def test_source_identity_requires_run02_and_every_provenance_hash() -> None:
    identity = _source_identity()
    assert dict(identity.source_hashes)["run02_snapshot"] == RUN02_SNAPSHOT_HASH
    missing = tuple(
        (key, value)
        for key, value in identity.source_hashes
        if key != "feature_lineage_manifest"
    )
    with pytest.raises(ValueError, match="every required source"):
        RestatedH5SourceIdentity(
            dataset_id=identity.dataset_id,
            source_revision_id=RUN02_REVISION_ID,
            source_hashes=missing,
            dataset_identity_sha256=dataset_identity_hash(
                dataset_id=identity.dataset_id,
                source_revision_id=RUN02_REVISION_ID,
                source_hashes=missing,
            ),
        )
    with pytest.raises(ValueError, match="approved snapshot"):
        _source_identity(source_hashes_override={"run02_snapshot": _digest("9")})
    with pytest.raises(ValueError, match="new restated derived-h5"):
        replace(identity, dataset_id="all-field-enriched-direct")
    with pytest.raises(ValueError, match="source_revision_id"):
        replace(identity, source_revision_id="unrelated-revision")
    with pytest.raises(ValueError, match="does not match its source identity"):
        replace(identity, dataset_identity_sha256=_digest("9"))


def test_label_needs_authoritative_available_at_and_mature_training_clock() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _label(authoritative_available_at=None)
    with pytest.raises(ValueError, match="availability_evidence_sha256"):
        _label(availability_evidence_sha256=None)
    with pytest.raises(ValueError, match="must not precede horizon_end_date"):
        _label(authoritative_available_at="2026-05-26T00:00:00+00:00")
    with pytest.raises(ValueError, match="requires horizon 5"):
        _label(horizon_days=10)
    with pytest.raises(ValueError, match="training_as_of must not precede authoritative"):
        _research_row(
            training_as_of="2026-09-23T00:00:00+00:00",
            label=_label(authoritative_available_at="2026-10-01T00:00:00+00:00"),
        )


def test_horizon_date_comparison_uses_taipei_trading_day() -> None:
    label = _label(authoritative_available_at="2026-05-26T16:30:00+00:00")

    assert label.horizon_end_date == "2026-05-27"


def test_revision_clock_must_not_be_backdated_or_after_training_cutoff() -> None:
    with pytest.raises(ValueError, match="must not precede revision_observed_at"):
        _research_row(training_as_of="2026-09-21T23:59:00+00:00")
    with pytest.raises(ValueError, match="observed after historical decision"):
        _research_row(revision_observed_at="2026-05-20T08:30:00+08:00")


def test_corporate_action_affected_labels_are_excluded() -> None:
    identity = _source_identity()
    label = _label(corporate_action_affected=True)
    with pytest.raises(ValueError, match="must be excluded"):
        _research_row(label=label, source_identity=identity, fold=_fold(identity))
    missing = tuple(
        (key, value)
        for key, value in identity.source_hashes
        if key != "corporate_action_exclusion_manifest"
    )
    with pytest.raises(ValueError, match="every required source"):
        RestatedH5SourceIdentity(
            dataset_id=identity.dataset_id,
            source_revision_id=RUN02_REVISION_ID,
            source_hashes=missing,
            dataset_identity_sha256=dataset_identity_hash(
                dataset_id=identity.dataset_id,
                source_revision_id=RUN02_REVISION_ID,
                source_hashes=missing,
            ),
        )


def test_fold_identity_is_hash_bound_chronological_and_row_scoped() -> None:
    identity = _source_identity()
    with pytest.raises(ValueError, match="chronological"):
        _fold(identity, test_start_date="2026-06-01")
    assert _fold(identity, purge_trading_days=61, embargo_trading_days=6)
    with pytest.raises(ValueError, match="at least a 60-day purge"):
        _fold(identity, purge_trading_days=59)
    with pytest.raises(ValueError, match="at least a 60-day purge"):
        _fold(identity, embargo_trading_days=4)
    wrong_fold = _fold(identity, fold_id="other-fold")
    wrong_hash_identity = _source_identity(
        source_hashes_override={"fold_manifest": _digest("9")}
    )
    with pytest.raises(ValueError, match="fold identity"):
        _research_row(source_identity=wrong_hash_identity, fold=wrong_fold)


def test_dataset_evidence_stays_pending_until_full_lineage_and_coverage() -> None:
    identity = _source_identity()
    pending = DerivedH5ResearchCandidateEvidence(
        source_identity=identity,
        candidate_row_count=868,
        rows_with_complete_62_features=0,
        rows_with_feature_lineage=0,
        rows_with_authoritative_label_availability=0,
        rows_with_mature_labels_at_training_as_of=0,
        corporate_action_exclusion_verified=False,
        full_window_lineage_verified=False,
        fold_manifest_verified=False,
    )
    assert pending.evidence_status == "pending"
    assert pending.research_only is True
    assert pending.historical_pit is False
    assert pending.formal_oos is False
    assert pending.promotion is False
    assert pending.production is False


def test_complete_synthetic_evidence_is_not_fit_or_oos_authorization() -> None:
    identity = _source_identity()
    evidence = DerivedH5ResearchCandidateEvidence(
        source_identity=identity,
        candidate_row_count=1,
        rows_with_complete_62_features=1,
        rows_with_feature_lineage=1,
        rows_with_authoritative_label_availability=1,
        rows_with_mature_labels_at_training_as_of=1,
        corporate_action_exclusion_verified=True,
        full_window_lineage_verified=True,
        fold_manifest_verified=True,
    )
    assert evidence.evidence_status == (
        "research_candidate_evidence_declared_complete_unverified"
    )
    assert evidence.research_only is True
    assert evidence.historical_pit is False
    assert evidence.formal_oos is False
    assert evidence.promotion is False
    assert evidence.production is False
    assert not hasattr(evidence, "fit_eligible")


def test_existing_pit_dataset_row_still_rejects_late_feature() -> None:
    digest = _digest("a")
    feature = PITFeatureValue(
        feature_id="technical_indicators.ADX",
        family_id="price_liquidity_technical",
        source_id="sqlite.technical_indicators",
        value_int=100,
        scale=1,
        event_at="2026-05-19",
        available_at="2026-09-22T15:30:00+08:00",
        revision_id=RUN02_REVISION_ID,
        quality="observed",
        content_hash=digest,
        observed=True,
    )
    state = CausalPortfolioState.create(
        as_of_date="2026-05-19",
        weights=AllocationWeightContract(positions_bp=(), cash_bp=10_000),
        weekly_turnover_used_bp=0,
    )
    with pytest.raises(ValueError, match="available_at.*decision_at"):
        PortfolioMLDatasetRow(
            row_id="2026-05-20:0050",
            decision_at="2026-05-20T08:30:00+08:00",
            symbol="0050",
            features=(feature,),
            missing_family_ids=(),
            portfolio_state=state,
            dataset_identity_hash=digest,
            feature_registry_hash=digest,
            source_manifest_hashes=(("sqlite.technical_indicators", digest),),
        )
