from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app_module.forward_daily_price_source_binding import (
    ForwardDailyPriceSourceBinder,
    unknown_price_source_binding,
)
from data_module.daily_price_qualification_binding import (
    DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
    DailyPriceQualificationBindingError,
    DailyPriceQualificationError,
    DailyPriceQualificationPolicy,
    DailyPriceRevisionLedger,
    DailyPriceRowRevision,
    PinnedDailyPriceQualificationResolver,
    compute_daily_price_available_at,
    evaluate_bound_daily_price_row_qualification,
    verify_qualified_binding_payload,
)

_TAIPEI = ZoneInfo("Asia/Taipei")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_prefixed(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_available_at_enforces_hourly_ceiling_and_market_close_floor():
    d = date(2026, 10, 20)
    avail, basis = compute_daily_price_available_at(
        trading_date=d,
        fetched_at=datetime(2026, 10, 20, 14, 15, tzinfo=_TAIPEI),
        written_at=datetime(2026, 10, 20, 14, 16, tzinfo=_TAIPEI),
    )
    assert avail.astimezone(_TAIPEI) == datetime(2026, 10, 20, 15, 0, tzinfo=_TAIPEI)
    assert "daily-hour.v1" in str(basis.availability_basis)

    # Premature availability before market close (13:30) must fail closed
    with pytest.raises(DailyPriceQualificationError, match="premature_availability_before_market_close"):
        compute_daily_price_available_at(
            trading_date=d,
            fetched_at=datetime(2026, 10, 20, 11, 30, tzinfo=_TAIPEI),
            written_at=datetime(2026, 10, 20, 11, 35, tzinfo=_TAIPEI),
        )

    # Written before first observed must fail closed
    with pytest.raises(DailyPriceQualificationError, match="publication_written_before_first_observed"):
        compute_daily_price_available_at(
            trading_date=d,
            fetched_at=datetime(2026, 10, 20, 14, 30, tzinfo=_TAIPEI),
            written_at=datetime(2026, 10, 20, 14, 20, tzinfo=_TAIPEI),
        )


def test_pinned_daily_price_qualification_resolver(tmp_path: Path):
    binding_payload = {
        "schema_version": DAILY_PRICE_QUALIFICATION_BINDING_SCHEMA_V1,
        "binding_id": "daily-price-twse-tpex-qualified-v1",
        "created_at": "2026-10-22T08:00:00+00:00",
        "decision": {
            "source_id": "twse.mi_index.daily_price",
            "decision_revision_id": "accept-twse-tpex-daily-price-20261022",
            "parent_revision_id": None,
            "status": "accepted",
            "allowed_use_cases": [
                "forward_decision_baseline",
                "forward_outcome_evaluation",
                "ml_training",
                "ml_validation",
            ],
            "blockers": [],
            "license_evidence_ids": ["sha256:" + "a" * 64],
            "quality_evidence_ids": ["sha256:" + "b" * 64],
            "pit_evidence_ids": ["sha256:" + "c" * 64],
            "owner_role": "quant_data_architect",
            "reviewer_role": "operations_owner",
            "decided_at": "2026-10-22T00:00:00+00:00",
            "rollback_reference": "initial_decision",
        },
    }
    raw = _canonical_bytes(binding_payload) + b"\n"
    binding_sha = _sha256_prefixed(raw)
    binding_file = tmp_path / "binding.json"
    binding_file.write_bytes(raw)

    resolver = PinnedDailyPriceQualificationResolver(
        binding_path=binding_file,
        expected_sha256=binding_sha,
    )
    loaded_raw, decision = resolver.load_verified_binding()
    assert decision.decision_revision_id == "accept-twse-tpex-daily-price-20261022"
    assert decision.status == "accepted"

    # Mismatch SHA raises
    bad_resolver = PinnedDailyPriceQualificationResolver(
        binding_path=binding_file,
        expected_sha256="sha256:" + "f" * 64,
    )
    with pytest.raises(DailyPriceQualificationError, match="binding_external_sha256_mismatch"):
        bad_resolver.load_verified_binding()

    # Build policy
    cutoff = datetime(2026, 10, 22, 16, 0, tzinfo=_TAIPEI)
    policy = resolver.build_policy(
        temporal_role="decision_baseline",
        cutoff_at=cutoff,
        oos_purge_cutoff_date=date(2026, 10, 31),
    )
    assert policy.temporal_role == "decision_baseline"
    assert policy.source_use_accepted is True
    assert policy.acceptance_binding_sha256 == binding_sha


def test_evaluate_bound_row_qualification_and_proof(tmp_path: Path):
    d = date(2026, 10, 20)
    rev = DailyPriceRowRevision(
        source_id="twse.mi_index.daily_price",
        source_date="2026-10-20",
        trading_date=d,
        stock_code="2330",
        publication_sha256="sha256:" + "1" * 64,
        sqlite_projection_row_sha256="sha256:" + "2" * 64,
        revision_number=1,
        revision_id="rev-20261020-001",
        parent_revision_id=None,
        parent_publication_sha256=None,
        first_observed_at="2026-10-20T14:15:00+08:00",
        written_at="2026-10-20T14:16:00+08:00",
        available_at="2026-10-20T15:00:00+08:00",
        availability_basis="daily-hour.v1",
        source_published_at=None,
        is_value_restatement=False,
    )

    class DummyLedger:
        revision_closure_verified = True

        def resolve_row_revision(self, **kwargs):
            cutoff = kwargs.get("cutoff_at")
            avail_dt = datetime.fromisoformat(rev.available_at).astimezone(timezone.utc)
            if cutoff is not None and avail_dt > cutoff:
                raise DailyPriceQualificationError("available_after_cutoff")
            return rev

    ledger = DummyLedger()

    policy = DailyPriceQualificationPolicy(
        temporal_role="decision_baseline",
        cutoff_at=datetime(2026, 10, 20, 16, 0, tzinfo=_TAIPEI),
        oos_purge_cutoff_date=date(2026, 10, 31),
        source_use_accepted=True,
        accepted_uses=("forward_decision_baseline", "ml_training"),
        source_id="twse.mi_index.daily_price",
        acceptance_decision_id="accept-001",
        acceptance_binding_sha256="sha256:" + "a" * 64,
    )

    bound_row = {
        "status": "source_identity_bound",
        "source_id": "twse.mi_index.daily_price",
        "source_date": "2026-10-20",
        "stock_code": "2330",
        "publication_sha256": "sha256:" + "1" * 64,
        "sqlite_projection_row_sha256": "sha256:" + "2" * 64,
    }

    # 1. Qualified under normal cutoff
    res = evaluate_bound_daily_price_row_qualification(
        bound_row=bound_row,
        revision_ledger=ledger,  # type: ignore[arg-type]
        policy=policy,
    )
    assert res["status"] == "source_qualified"
    assert res["source_use_accepted"] is True
    assert res["pit_eligible"] is True
    assert res["training_eligible"] is True
    assert res["available_at"] == "2026-10-20T15:00:00+08:00"
    assert res["source_published_at"] is None
    assert verify_qualified_binding_payload(res) is False

    # 2. Tampering fails proof check
    tampered = dict(res)
    tampered["available_at"] = "2026-10-20T14:00:00+08:00"
    assert verify_qualified_binding_payload(tampered) is False

    # 3. Available after cutoff fails
    policy_tight = DailyPriceQualificationPolicy(
        temporal_role="decision_baseline",
        cutoff_at=datetime(2026, 10, 20, 14, 0, tzinfo=_TAIPEI),
        source_use_accepted=True,
        accepted_uses=("forward_decision_baseline",),
        source_id="twse.mi_index.daily_price",
        acceptance_decision_id="accept-001",
        acceptance_binding_sha256="sha256:" + "a" * 64,
    )
    res_tight = evaluate_bound_daily_price_row_qualification(
        bound_row=bound_row,
        revision_ledger=ledger,  # type: ignore[arg-type]
        policy=policy_tight,
    )
    assert res_tight["status"] == "unknown"
    assert "cutoff" in res_tight["reason_code"]
    assert res_tight["source_use_accepted"] is False
    assert res_tight["pit_eligible"] is False
