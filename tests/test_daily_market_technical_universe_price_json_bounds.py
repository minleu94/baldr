"""F07 舊 decoder 的超深 JSON 在解析前拒絕，保留原樹深度與 canonical 守衛。"""
from __future__ import annotations

import json
from typing import Any
import pytest
import app_module.daily_market_technical_universe_price_query_v1 as price


@pytest.mark.parametrize('decoder', (
    price.DailyMarketTechnicalUniversePriceQueryV1.from_json,
    price.DailyMarketTechnicalUniversePricePageRequestV1.from_json,
))
def test_public_price_decoder_rejects_deep_json_before_json_loads(
    decoder: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PageRequest 原4096-byte上限維持；此反例在byte cap內超過parser安全深度。
    raw = ('[' * 1024 + '0' + ']' * 1024).encode('utf-8')
    def forbidden_parse(*_args: object, **_kwargs: object) -> None:
        pytest.fail('超深輸入不得先進入 JSON parser')
    monkeypatch.setattr(price.json, 'loads', forbidden_parse)
    with pytest.raises(price.DailyMarketTechnicalUniversePriceQueryV1Error) as caught:
        decoder(raw)
    assert caught.value.code == 'technical_universe_price_json_depth_limit'


def test_price_json_depth_preflight_ignores_escaped_string_delimiters() -> None:
    expected = {'text': '[' * 5000 + '\\"}[' + ']' * 5000}
    raw = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert price._parse_json(raw, maximum=len(raw), code='invalid') == expected


def test_price_json_preflight_retains_original_zero_based_tree_boundary() -> None:
    raw = ('[' * 33 + ']' * 33).encode('utf-8')
    value = price._parse_json(raw, maximum=len(raw), code='invalid')
    price._reject_float_tree(value)
    too_deep_leaf = ('[' * 33 + '0' + ']' * 33).encode('utf-8')
    with pytest.raises(price.DailyMarketTechnicalUniversePriceQueryV1Error) as caught:
        price._parse_json(too_deep_leaf, maximum=len(too_deep_leaf), code='invalid')
    assert caught.value.code == 'technical_universe_price_json_depth_limit'
