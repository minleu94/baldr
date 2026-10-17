"""方向欄位的文字證據、HTML 單次解碼及未知值守衛。"""

from decimal import Decimal

import pytest

from app_module.price_change_direction import resolve_signed_change
from data_module.price_change_direction import normalize_twse_change_sign


@pytest.mark.parametrize(("raw", "expected"), [
    ("+", "+"), ("−", "-"), ("＋", "+"), ("跌", "-"),
    ('<p style="color: green">+</p>', "+"),
    ('<p style="color: red">-</p>', "-"),
    ("<span>&#8722;</span>", "-"), ("&#43;", "+"),
    ("&amp;#43;", "unknown"), ("&lt;p&gt;+&lt;/p&gt;", "unknown"),
    ("<p>+-</p>", "unknown"), ("<p style=color:red></p>", "unknown"),
    ("<script>+</script>", "unknown"), ("<span hidden>+</span>", "unknown"),
    ('<span style="display: none">+</span>', "unknown"),
    ("NA", "unknown"), ("nan", "unknown"), ("除權息", "unknown"),
    ("", ""), (" \t", ""), (None, ""),
])
def test_direction_text_is_explicit_and_decoded_once(raw: object, expected: str) -> None:
    assert normalize_twse_change_sign(raw) == expected


@pytest.mark.parametrize("raw", ["X", "NA", "<p style=color:red></p>"])
def test_nonempty_unknown_never_becomes_flat_zero(raw: str) -> None:
    normalized = normalize_twse_change_sign(raw)
    assert resolve_signed_change("0", (normalized,)) == (None, "unknown_change_direction")
    assert resolve_signed_change("5", (normalized,)) == (None, "unknown_change_direction")
    assert resolve_signed_change("0", ("",)) == (Decimal("0"), "")
