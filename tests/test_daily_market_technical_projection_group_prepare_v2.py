"""同一真保存 bundle 的三路候選核驗；不授 session/seal。"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

import pytest

from app_module import daily_market_technical_universe_projection_group_prepare_v2 as prepare
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DailyMarketTechnicalUniverseProjectionGroupV2Error,
)
from test_daily_market_technical_ma_group_prepare import _assert_poisoned, _read_group
from test_daily_market_technical_official_disposition_bundle_v1 import bundle_fixture


def test_full_two_parent_members_have_one_source_and_remain_unqualified(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module import daily_market_technical_universe_ma_alignment_query_v1 as ma_module

    group, builder, state, query, selection = _read_group(bundle_fixture)

    def forbidden_issue(**kwargs: object) -> None:
        pytest.fail("三路 prepare 不得發行 MA session")

    monkeypatch.setattr(ma_module, "_issue_ma_alignment_read_session_v1", forbidden_issue)
    original_prepare = type(group._ma_collector)._prepare_for_projection_group
    original_index_transport = ma_module.DailyMarketTechnicalMaAlignmentCompactIndexV1.to_dict

    def prepare_then_forbid_full_index_transport(*args: Any, **kwargs: Any) -> Any:
        prepared = original_prepare(*args, **kwargs)

        def forbidden_index_transport(self: Any) -> Any:
            pytest.fail("group 層不得再 materialize 完整 MA transport")

        monkeypatch.setattr(ma_module.DailyMarketTechnicalMaAlignmentCompactIndexV1, "to_dict", forbidden_index_transport)
        return prepared

    monkeypatch.setattr(type(group._ma_collector), "_prepare_for_projection_group", prepare_then_forbid_full_index_transport)
    candidate = prepare._prepare_projection_group_v2(group, builder, state, query, selection)
    assert candidate.reader_issued is False
    assert candidate.ma.reader_issued is False
    assert candidate.kdj.reader_issued is False
    assert candidate.volatility.reader_issued is False
    assert candidate.ma.builder is builder
    assert candidate.ma.bundle_state is state
    assert candidate.ma.selection is selection
    assert len(selection.stock_codes) == 1
    assert len(candidate.ma.parent_observations) == 2
    for entries in (candidate.ma.index.entries, candidate.kdj.entries, candidate.volatility.entries):
        assert tuple(row.stock_code for row in entries) == bundle_fixture.included_codes
    assert candidate.total_canonical_payload_bytes <= group._max_total_bytes
    assert len(candidate.preparation_identity_sha256) == 64
    assert len(candidate.parent_ledger_identity_sha256) == 64
    assert group.status == "between_parents"
    assert group._ma_collector._issued_session is None
    assert group._ma_collector._finished is False
    assert group.qualification_status == "projection_group_unqualified"
    assert len(group._row_provenance) == len(bundle_fixture.included_codes)
    for saved, ma, kdj, volatility in zip(
        group._row_provenance, group._ma_collector._entries,
        candidate.kdj.entries, candidate.volatility.entries, strict=True,
    ):
        assert saved.ma_entry is ma
        assert saved.kdj_entry is kdj
        assert saved.volatility_entry is volatility
        assert saved.source_pin_sha256 == kdj.source_pin_sha256 == volatility.source_pin_sha256
    # 真 index 的舊 canonical bytes 是 oracle；測試內才建立完整比較複本。
    import hashlib
    import json
    from dataclasses import asdict

    encode = lambda payload: json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    legacy_ma = encode(original_index_transport(candidate.ma.index))
    streamed_ma = prepare._digest_payload(prepare._ma_index_payload_references(candidate.ma.index), len(legacy_ma), None)
    assert streamed_ma == (hashlib.sha256(legacy_ma).hexdigest(), len(legacy_ma))
    legacy_ledger = encode(tuple(asdict(item) for item in candidate.ma.parent_observations))
    streamed_ledger = prepare._digest_payload(candidate.ma.parent_observations, len(legacy_ledger), None)
    assert streamed_ledger == (hashlib.sha256(legacy_ledger).hexdigest(), len(legacy_ledger))
    assert streamed_ledger[0] == candidate.parent_ledger_identity_sha256


@pytest.mark.parametrize("fault", (
    "kdj_missing", "row_reordered", "member_limit", "aggregate_limit", "late_cancel", "late_budget",
    "same_value_replaced", "all_rehashed", "late_all_replaced",
))
def test_member_or_envelope_failure_clears_all_three_buffers(
    bundle_fixture: Any, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    group, builder, state, query, selection = _read_group(bundle_fixture)
    cancelled = threading.Event()
    if fault == "kdj_missing":
        group._kdj_collector._entries.pop()
    elif fault == "row_reordered":
        group._kdj_collector._entries.reverse()
    elif fault == "member_limit":
        monkeypatch.setattr(prepare, "DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1", 1)
    elif fault == "aggregate_limit":
        # 已完成 callback 的 entry buffer 仍合法；最終完整 envelope 額外受此限。
        group._max_total_bytes = sum(group._member_bytes)
    elif fault in {"same_value_replaced", "all_rehashed"}:
        if fault == "all_rehashed":
            import hashlib
            import json

            original = group._volatility_collector._entries[0]
            modified = {"snapshot_identity_sha256": "a" * 64, "source_pin_sha256": "b" * 64}
            evidence = replace(original.evidence, **modified)
            payload = original._body()
            payload.update(modified)
            payload["evidence"] = evidence.to_dict()
            new_identity = hashlib.sha256(json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")).hexdigest()
            group._volatility_collector._entries[0] = replace(
                original, evidence=evidence, compact_identity_sha256=new_identity, **modified,
            )
            group._kdj_collector._entries[0] = replace(group._kdj_collector._entries[0], **modified)
            group._ma_collector._entries[0] = replace(
                group._ma_collector._entries[0], snapshot_identity_sha256=modified["snapshot_identity_sha256"],
            )
            # 三路 transport 均有效、自我 hash 可重算；不代表原 callback provenance。
            for collector in (group._ma_collector, group._kdj_collector, group._volatility_collector):
                assert collector._entries[0].to_dict()["snapshot_identity_sha256"] == "a" * 64
        else:
            for collector in (group._ma_collector, group._kdj_collector, group._volatility_collector):
                collector._entries[0] = replace(collector._entries[0])
    else:
        original = prepare._prepare_member

        def cancel_after_first_member(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            if fault == "late_all_replaced":
                for collector in (group._ma_collector, group._kdj_collector, group._volatility_collector):
                    collector._entries[0] = replace(collector._entries[0])
            elif fault == "late_budget":
                group._max_total_bytes -= 1
            else:
                cancelled.set()
            return result

        monkeypatch.setattr(prepare, "_prepare_member", cancel_after_first_member)
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error) as rejected:
        prepare._prepare_projection_group_v2(
            group, builder, state, query, selection, cancel_callback=cancelled.is_set,
        )
    _assert_poisoned(group)
    assert group._row_provenance == []
    if fault in {"same_value_replaced", "all_rehashed", "late_all_replaced"}:
        assert rejected.value.code == "technical_projection_group_v2_callback_provenance_mismatch"


def test_stream_digest_counts_full_utf8_payload_and_polls_cancellation() -> None:
    import hashlib
    import json

    payload = {"中文字": tuple(range(300))}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    calls = 0

    def count_checks() -> bool:
        nonlocal calls
        calls += 1
        return False

    identity, size = prepare._digest_payload(payload, len(encoded), count_checks)
    assert identity == hashlib.sha256(encoded).hexdigest()
    assert size == len(encoded)
    assert calls >= 3
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error, match="prepared_payload_limit"):
        prepare._digest_payload(payload, len(encoded) - 1, count_checks)
    with pytest.raises(DailyMarketTechnicalUniverseProjectionGroupV2Error, match="cancelled"):
        prepare._digest_payload(payload, len(encoded), lambda: True)


def test_identity_fields_are_included_in_complete_envelope_byte_accounting() -> None:
    import json

    body = {"metadata": "中文字", "count": 257}
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    for field in ("body_identity_sha256", "preparation_identity_sha256"):
        complete = {**body, field: "a" * 64}
        assert prepare._identified_payload_size(len(encode(body)), field) == len(encode(complete))
