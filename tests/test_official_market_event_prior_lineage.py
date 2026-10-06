from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest

from data_module import official_market_event_backfill as module


_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "official_market_events"
    / "twse_twt49u_2024.json"
).read_bytes()


class _FixtureFetcher:
    def fetch(
        self,
        endpoint: module.OfficialMarketEndpoint,
        request_year: int,
        *,
        timeout_seconds: int,
        max_attempts: int,
        retry_delay_seconds: int,
    ) -> module.RawOfficialResponse:
        del timeout_seconds, max_attempts, retry_delay_seconds
        parameters = endpoint.parameters_for_year(request_year)
        return module.RawOfficialResponse(
            endpoint=endpoint,
            request_year=request_year,
            request_parameters=tuple(sorted(parameters.items())),
            source_url=(
                f"{endpoint.endpoint_url}?{urlencode(parameters)}"
            ),
            retrieved_at="2026-07-30T16:00:00+00:00",
            http_status=200,
            content_type="application/json",
            http_date=None,
            etag=None,
            last_modified=None,
            payload=_FIXTURE,
        )


def _builder(now: datetime) -> module.OfficialMarketEventBackfillBuilder:
    endpoint = next(
        item
        for item in module.OFFICIAL_MARKET_ENDPOINTS
        if item.parser_id == "twse_twt49u.v1"
    )
    return module.OfficialMarketEventBackfillBuilder(
        endpoints=(endpoint,),
        fetcher=_FixtureFetcher(),
        now=lambda: now,
        sleep=lambda _: None,
    )


def _strip_latest_raw_index(
    output_root: Path,
    publication: module.OfficialMarketEventPublication,
) -> None:
    """Model a legacy publication that omitted inherited raw entries."""

    manifest_path = publication.manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_index_path = manifest_path.parent / manifest["raw_index"]["path"]
    raw_index_path.write_bytes(module._jsonl_bytes(()))
    manifest["raw_index"]["file_hash"] = module._file_sha256(raw_index_path)
    manifest["raw_index"]["response_count"] = 0
    manifest["raw_index"]["lineage_response_count"] = 0
    manifest["manifest_hash"] = module._sha256_json(
        {
            key: value
            for key, value in manifest.items()
            if key != "manifest_hash"
        }
    )
    module._write_json(manifest_path, manifest)
    pointer_path = output_root / "latest_manifest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_hash"] = manifest["manifest_hash"]
    pointer["manifest_file_hash"] = module._file_sha256(manifest_path)
    module._write_json(pointer_path, pointer)


def test_prior_reader_resolves_legacy_raw_index_from_verified_parent_chain(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "release_v4"
    request = module.OfficialMarketEventBackfillRequest(
        output_root=output_root,
        start_year=2024,
        end_year=2024,
        request_delay_seconds=0,
    )
    first = _builder(
        datetime(2026, 7, 30, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    second = _builder(
        datetime(2026, 7, 31, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    _strip_latest_raw_index(output_root, second)

    prior = module._load_prior_publication(output_root)

    assert len(prior.events) == first.canonical_event_count
    assert len(prior.raw_entries) == 1
    lineage_entry = prior.raw_entries[0]
    lineage_path = str(lineage_entry["response_path"])
    response_hash = str(lineage_entry["response_sha256"])
    assert lineage_path == f"raw_lineage/{response_hash[7:]}.json"
    assert prior.raw_entry_sources[(lineage_path, response_hash)] == (
        first.publication_directory
        / "raw"
        / "twse.TWT49U.ex_right_dividend_result"
        / "year=2024"
        / "response.json"
    )


def test_prior_reader_rejects_tampered_ancestor_raw_response(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "release_v4"
    request = module.OfficialMarketEventBackfillRequest(
        output_root=output_root,
        start_year=2024,
        end_year=2024,
        request_delay_seconds=0,
    )
    first = _builder(
        datetime(2026, 7, 30, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    second = _builder(
        datetime(2026, 7, 31, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    _strip_latest_raw_index(output_root, second)

    ancestor_response = next(
        first.publication_directory.glob(
            "raw/twse.TWT49U.ex_right_dividend_result/year=2024/response.json"
        )
    )
    ancestor_response.write_bytes(ancestor_response.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="prior raw response hash mismatch"):
        module._load_prior_publication(output_root)


def test_prior_reader_rejects_broken_parent_manifest_chain(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "release_v4"
    request = module.OfficialMarketEventBackfillRequest(
        output_root=output_root,
        start_year=2024,
        end_year=2024,
        request_delay_seconds=0,
    )
    _builder(
        datetime(2026, 7, 30, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    second = _builder(
        datetime(2026, 7, 31, 16, 1, tzinfo=timezone.utc)
    ).build(request)
    _strip_latest_raw_index(output_root, second)

    latest_manifest = json.loads(
        second.manifest_path.read_text(encoding="utf-8")
    )
    parent_identity = (
        latest_manifest["parent_manifest_hash"],
        latest_manifest["parent_manifest_file_hash"],
    )
    parent_path = next(
        path
        for path in (output_root / "runs").glob("*/manifest.json")
        if (
            json.loads(path.read_text(encoding="utf-8")).get(
                "manifest_hash"
            )
            == parent_identity[0]
            and module._file_sha256(path) == parent_identity[1]
        )
    )
    parent_path.unlink()

    with pytest.raises(ValueError, match="prior canonical raw lineage missing"):
        module._load_prior_publication(output_root)
