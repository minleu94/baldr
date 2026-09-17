from __future__ import annotations

import json

from scripts.qa_validate_price_unavailable_consumer_scope import (
    _iter_json_array_field,
)


def test_array_field_reader_yields_nested_objects_without_loading_siblings(
    tmp_path,
) -> None:
    path = tmp_path / "mapping.json"
    path.write_text(
        json.dumps(
            {
                "before": {"text": "not an array field"},
                "invalid_rows": [
                    {"date": "20240101", "symbol": "2330", "raw": {"x": [1, 2]}},
                    {"date": "20240102", "symbol": "2330", "raw": {"text": "] }"}},
                ],
                "after": {"invalid_rows": "not this nested value"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert tuple(_iter_json_array_field(path, "invalid_rows")) == (
        {"date": "20240101", "symbol": "2330", "raw": {"x": [1, 2]}},
        {"date": "20240102", "symbol": "2330", "raw": {"text": "] }"}},
    )
