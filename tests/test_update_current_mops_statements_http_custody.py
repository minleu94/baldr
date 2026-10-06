from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
import requests

from scripts import update_current_mops_statements as updater


@pytest.mark.parametrize(
    ("failure_kind", "expected_status", "unexpected_final_url"),
    [
        ("http_520", 520, None),
        ("redirect_302", 302, None),
        ("unexpected_url_200", 200, "https://unexpected.example/mops"),
    ],
)
def test_live_http_failures_keep_raw_body_without_parse_or_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_kind: str,
    expected_status: int,
    unexpected_final_url: str | None,
) -> None:
    output_root = tmp_path / "output"
    database = tmp_path / "formal.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE existing_records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO existing_records VALUES ('preserve-me')")
    database_before = database.read_bytes()

    class FakeResponse:
        def __init__(self, status_code: int, url: str, body: bytes) -> None:
            self.status_code = status_code
            self.url = url
            self.body = body

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def iter_content(self, chunk_size: int):
            assert chunk_size == 65536
            yield self.body

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    requested: list[tuple[str, dict[str, object]]] = []
    response_bodies: list[bytes] = []

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        requested.append((url, dict(kwargs)))
        index = len(requested) - 1
        body = f"response-body-{index}-{failure_kind}".encode("utf-8")
        response_bodies.append(body)
        if index == 0:
            status_code = expected_status
            final_url = unexpected_final_url or url
        else:
            status_code = 200
            final_url = url
        return FakeResponse(status_code, final_url, body)

    parsed_bodies: list[str] = []

    def parse_body(
        html: str,
        *,
        market: str,
        period: str,
        statement: str,
        observed_at: datetime,
        source_available_at: datetime | None = None,
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        assert observed_at.tzinfo is not None and observed_at.utcoffset() is not None
        assert source_available_at is not None
        assert source_available_at.tzinfo is not None
        assert source_available_at.utcoffset() is not None
        parsed_bodies.append(html)
        return ([{"stock_code": "2330", "market": market, "statement": statement}], {})

    apply_calls: list[list[dict[str, str]]] = []
    monkeypatch.setattr(updater.requests, "post", fake_post)
    monkeypatch.setattr(updater, "parse_current_statement_html", parse_body)
    monkeypatch.setattr(
        updater,
        "insert_observations",
        lambda _connection, records: apply_calls.append(records) or len(records),
    )

    result_code = updater.main(
        [
            "--period",
            "2026-Q2",
            "--output-root",
            str(output_root),
            "--db-path",
            str(database),
            "--apply",
            "--confirm",
            "append-current-mops-statements",
        ]
    )
    stdout = capsys.readouterr().out

    assert result_code == 2
    assert len(requested) == len(updater.STATEMENTS) * 2
    assert all(kwargs.get("allow_redirects") is False for _, kwargs in requested)
    assert len(parsed_bodies) == len(requested) - 1
    assert response_bodies[0].decode("utf-8") not in parsed_bodies
    assert apply_calls == []

    run_roots = list(output_root.glob("current-mops-statements-*"))
    assert len(run_roots) == 1
    run_root = run_roots[0]
    receipt = json.loads((run_root / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "blocked"
    assert receipt["formal_statement_items_written"] is False
    assert receipt["normalized_rows"] == len(requested) - 1

    failed = receipt["requests"][0]
    assert failed["status"] == "failed"
    assert failed["http_status"] == expected_status
    assert failed["final_url"] == unexpected_final_url or (
        unexpected_final_url is None and failed["final_url"] == failed["requested_url"]
    )
    assert failed["source_available_at"] is None
    completed_at = datetime.fromisoformat(failed["response_body_completed_at"])
    assert completed_at.tzinfo is not None and completed_at.utcoffset() is not None
    raw_file = Path(failed["raw_file"])
    assert raw_file.parent == run_root
    assert raw_file.read_bytes() == response_bodies[0]
    assert failed["bytes"] == len(response_bodies[0])
    assert failed["sha256"] == hashlib.sha256(response_bodies[0]).hexdigest()
    raw_paths = [Path(item["raw_file"]) for item in receipt["requests"]]
    assert len(set(raw_paths)) == len(requested)
    assert [path.read_bytes() for path in raw_paths] == response_bodies
    for successful in receipt["requests"][1:]:
        assert successful["status"] == "normalized"
        assert successful["source_available_at"] == successful["response_body_completed_at"]

    assert not (run_root / "before.sqlite").exists()
    assert database.read_bytes() == database_before
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT value FROM existing_records").fetchone() == (
            "preserve-me",
        )
    assert "current-mops-statements-update.v1" in stdout
