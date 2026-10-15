"""驗證 V2 複合收藏 envelope 的版本、inner bytes 與新 reader round-trip。"""

from __future__ import annotations

import hashlib
import json

import pytest

import app_module.daily_market_technical_official_disposition_composite_bookmark_storage_v2 as storage_v2
import app_module.daily_market_technical_official_disposition_composite_bookmark_v2 as bookmark_v2

pytest_plugins = (
    "test_daily_market_technical_official_disposition_composite_bookmark_v2",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reseal_outer_identity(payload: dict[str, object]) -> bytes:
    payload.pop("view_bookmark_identity_sha256", None)
    payload["view_bookmark_identity_sha256"] = hashlib.sha256(
        _canonical(payload)
    ).hexdigest()
    return _canonical(payload)


def test_v2_envelope_round_trips_through_a_new_public_reader_instance(
    saved_v2_bookmark,
) -> None:
    envelope = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    raw = envelope.to_json().encode("utf-8")
    writer_identity = envelope.view_bookmark_identity_sha256

    reopened = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
        raw
    )
    reopened_from_dict = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_dict(
        envelope.to_dict()
    )
    assert reopened is not envelope
    assert reopened_from_dict == reopened
    assert reopened.to_json().encode("utf-8") == raw
    assert reopened.bookmark_json == saved_v2_bookmark.to_json()
    assert reopened.bookmark_sha256 == hashlib.sha256(
        reopened.bookmark_json.encode("utf-8")
    ).hexdigest()
    assert reopened.bookmark_identity_sha256 == saved_v2_bookmark.bookmark_id
    assert reopened.stock_code == saved_v2_bookmark.stock_code
    assert reopened.source == bookmark_v2.DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_COMPOSITE_BOOKMARK_SOURCE_V2
    assert reopened.view_bookmark_identity_sha256 == writer_identity

    inner = bookmark_v2.DailyMarketTechnicalOfficialDispositionCompositeBookmarkV2.from_json(
        reopened.bookmark_json
    )
    assert inner.basket_stock_codes == saved_v2_bookmark.basket_stock_codes
    assert inner.scroll_position == saved_v2_bookmark.scroll_position
    payload = reopened.to_dict()
    assert payload["scope"] == "current_only"
    assert payload["official_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["storage_envelope_is_reader_certification"] is False

    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="bookmark_type_invalid",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
            object()  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "tamper",
    (
        "inner_json",
        "inner_sha256",
        "inner_bookmark_identity",
        "selected_stock_code",
        "source",
    ),
)
def test_v2_envelope_rejects_inner_or_watchlist_identity_mismatch(
    saved_v2_bookmark,
    tamper: str,
) -> None:
    envelope = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    payload = envelope.to_dict()
    if tamper == "inner_json":
        payload["bookmark_json"] = str(payload["bookmark_json"]) + " "
    elif tamper == "inner_sha256":
        current = str(payload["bookmark_sha256"])
        payload["bookmark_sha256"] = "0" * 64 if current != "0" * 64 else "1" * 64
    elif tamper == "inner_bookmark_identity":
        current = str(payload["bookmark_identity_sha256"])
        payload["bookmark_identity_sha256"] = "0" * 64 if current != "0" * 64 else "1" * 64
    elif tamper == "selected_stock_code":
        payload["stock_code"] = "YYYY" if envelope.stock_code == "ZZZZ" else "ZZZZ"
    else:
        payload["source"] = "another_composite_source_v2"

    with pytest.raises(storage_v2.CompositeBookmarkStorageEnvelopeV2Error):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            _reseal_outer_identity(payload)
        )


def test_v2_envelope_rejects_v1_extra_duplicate_float_and_overdeep_payloads(
    saved_v2_bookmark,
) -> None:
    envelope = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )

    v1_schema = envelope.to_dict()
    v1_schema["schema_version"] = "daily-market-technical-official-disposition-composite-view-state.v1"
    with pytest.raises(storage_v2.CompositeBookmarkStorageEnvelopeV2Error):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            _reseal_outer_identity(v1_schema)
        )

    extra_field = envelope.to_dict()
    extra_field["unexpected"] = "not-accepted"
    with pytest.raises(storage_v2.CompositeBookmarkStorageEnvelopeV2Error):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            _canonical(extra_field)
        )

    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="duplicate_json_key",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            b'{"schema_version":"x","schema_version":"y"}'
        )

    float_payload = envelope.to_json().replace(
        '"historical_pit_eligible":false',
        '"historical_pit_eligible":0.0',
    )
    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="float_forbidden",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            float_payload
        )

    too_deep = b"[" * 33 + b"0" + b"]" * 33
    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="json_depth_limit",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            too_deep
        )


def test_v2_envelope_enforces_serialized_byte_and_inner_selection_bounds(
    saved_v2_bookmark,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.create(
        saved_v2_bookmark
    )
    raw = envelope.to_json()

    monkeypatch.setattr(storage_v2, "_MAX_BYTES_V2", 8)
    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="byte_limit",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            b" " * 9
        )

    monkeypatch.setattr(storage_v2, "_MAX_BYTES_V2", 2 * 64 * 1024 * 1024 + 4096)
    monkeypatch.setattr(storage_v2, "_MAX_SELECTIONS_V2", 1)
    with pytest.raises(
        storage_v2.CompositeBookmarkStorageEnvelopeV2Error,
        match="bookmark_count_limit",
    ):
        storage_v2.DailyMarketTechnicalOfficialDispositionCompositeViewBookmarkEnvelopeV2.from_json(
            raw
        )
