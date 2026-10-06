from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from data_module import monthly_revenue_research_candidate as capture_module
from data_module.monthly_revenue_availability_history import OFFICIAL_OPENAPI_URLS
from data_module.monthly_revenue_backfill import plan_mops_snapshot_monthly_revenue_backfill
from scripts import capture_monthly_revenue_research_candidate as capture_cli


_TAIPEI = ZoneInfo("Asia/Taipei")


class _Response:
    def __init__(self, url: str, body: bytes, headers: dict[str, str] | None = None):
        self.status = 200
        self._url = url
        self._stream = BytesIO(body)
        self.headers = headers or {"Content-Type": "application/json; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self._stream.close()

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _previous_period_and_announcement() -> tuple[str, str]:
    today = datetime.now(_TAIPEI).date()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    period = f"{year - 1911:03d}{month:02d}"
    announced = today - timedelta(days=1)
    announcement = (
        f"{announced.year - 1911:03d}"
        f"{announced.month:02d}{announced.day:02d}"
    )
    return period, announcement


def _row(stock_code: str, *, period: str | None = None, amount: str = "1000") -> dict[str, str]:
    default_period, announcement = _previous_period_and_announcement()
    return {
        "出表日期": announcement,
        "資料年月": period or default_period,
        "公司代號": stock_code,
        "公司名稱": f"測試公司{stock_code}",
        "產業別": "測試業",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "900",
        "營業收入-去年當月營收": "800",
        "營業收入-上月比較增減(%)": "",
        "營業收入-去年同月增減(%)": "25.00",
        "累計營業收入-當月累計營收": "7000",
        "累計營業收入-去年累計營收": "6000",
        "累計營業收入-前期比較增減(%)": "16.66",
        "備註": "-",
    }


def _run_capture(
    tmp_path: Path,
    monkeypatch,
    *,
    rows_by_venue: dict[str, list[dict[str, str]]] | None = None,
    content_encodings: dict[str, str] | None = None,
    bodies: dict[str, bytes] | None = None,
    free_bytes: int = 64 * 1024 * 1024,
) -> tuple[dict, list[tuple[str, int]], Path]:
    monkeypatch.setattr(capture_module, "REPO_ROOT", tmp_path)
    calls: list[tuple[str, int]] = []
    rows = rows_by_venue or {"twse": [_row("2330")], "tpex": [_row("6488")]}
    encodings = content_encodings or {}
    body_overrides = bodies or {}

    def opener(request, *, timeout):
        url = request.full_url
        calls.append((url, timeout))
        assert request.get_method() == "GET"
        assert request.get_header("Accept-encoding") == "identity"
        venue = next(key for key, source_url in OFFICIAL_OPENAPI_URLS.items() if source_url == url)
        body = body_overrides.get(
            venue,
            json.dumps(rows[venue], ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if venue in encodings:
            headers["Content-Encoding"] = encodings[venue]
        return _Response(url, body, headers)

    result = capture_module._capture_monthly_revenue_research_candidate(
        candidate_parent=tmp_path / "candidates",
        opener=opener,
        disk_usage=lambda _path: SimpleNamespace(free=free_bytes),
    )
    return result, calls, Path(result.get("run_root", tmp_path / "no-run"))


def test_capture_creates_hash_bound_full_scope_candidate_and_preserves_preview_contract(
    tmp_path: Path, monkeypatch
) -> None:
    result, calls, run_root = _run_capture(tmp_path, monkeypatch)

    assert result["status"] == "captured"
    assert result["source_requests_made"] == 2
    assert calls == [
        (OFFICIAL_OPENAPI_URLS["twse"], 30),
        (OFFICIAL_OPENAPI_URLS["tpex"], 30),
    ]
    candidate = json.loads((run_root / "candidate_manifest.json").read_text("utf-8"))
    scope = json.loads((run_root / "full_source_scope_manifest.json").read_text("utf-8"))
    capture = json.loads((run_root / "source" / "capture_run.json").read_text("utf-8"))
    assert candidate["status"] == "research_only_candidate_created"
    assert candidate["source_row_count"] == 2
    assert candidate["availability_row_count"] == 2
    assert candidate["owner_acceptance"] is False
    assert candidate["formal_apply_authorized"] is False
    assert candidate["units"]["source_api_unit_explicit"] is False
    assert candidate["readback"]["status"] == "verified"
    assert candidate["candidate_completed_at_utc"]
    assert scope["candidate_rows"] == 2
    assert scope["source_scope"]["twse_row_count"] == 1
    assert scope["source_scope"]["tpex_row_count"] == 1
    assert scope["owner_acceptance"] is False
    assert capture["status"] == "captured"
    assert capture["source_row_count"] == 2
    assert capture["numeric_qa"]["amount_fields"]["營業收入-當月營收"][
        "finite_decimal_count"
    ] == 2
    assert capture["numeric_qa"]["blank_percentage_cells"] == 2
    for venue in ("twse", "tpex"):
        raw_path = run_root / "source" / f"{venue}.json"
        raw_bytes = raw_path.read_bytes()
        assert hashlib.sha256(raw_bytes).hexdigest() == capture["results"][venue][
            "content_sha256"
        ]
        observed = datetime.fromisoformat(
            capture["results"][venue]["observed_at_utc"].replace("Z", "+00:00")
        )
        assert observed.tzinfo is not None

    policy = capture["availability_policy"]
    observed_at = datetime.fromisoformat(policy["source_observed_at_utc"])
    source_date = observed_at.astimezone(_TAIPEI).date()
    assert policy["source_capture_date_taipei"] == source_date.isoformat()
    assert policy["snapshot_capture_available_date"] == (
        source_date + timedelta(days=1)
    ).isoformat()
    availability_path = run_root / candidate["availability_file"]
    availability_rows = list(
        __import__("csv").DictReader(
            availability_path.read_text(encoding="utf-8-sig").splitlines()
        )
    )
    assert all(
        row["available_date"] >= policy["snapshot_capture_available_date"]
        for row in availability_rows
    )

    plan = plan_mops_snapshot_monthly_revenue_backfill(
        snapshot_file=run_root / candidate["candidate_file"],
        availability_file=availability_path,
        source_version="monthly-revenue-research-test",
        scope_manifest_file=run_root / candidate["scope_manifest_file"],
    )
    assert plan.ready_for_apply is True
    assert plan.formal_apply_eligible is False
    assert len(plan.records) == 2
    assert {record.revenue for record in plan.records} == {
        Decimal("1000"),
        Decimal("1000"),
    }


def test_capture_rejects_non_identity_content_encoding_and_keeps_raw_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    twse_raw = json.dumps([_row("2330")], ensure_ascii=False).encode("utf-8")
    result, calls, run_root = _run_capture(
        tmp_path,
        monkeypatch,
        bodies={"twse": gzip.compress(twse_raw)},
        content_encodings={"twse": "gzip"},
    )

    assert result["status"] == "failed"
    assert len(calls) == 2
    capture = json.loads((run_root / "source" / "capture_run.json").read_text("utf-8"))
    twse_result = capture["results"]["twse"]
    assert twse_result["status"] == "failed"
    assert twse_result["error_type"] == "ValueError"
    assert twse_result["content_encoding"] == "gzip"
    assert (run_root / "source" / "twse.json").read_bytes() == gzip.compress(twse_raw)
    assert not list(run_root.glob("*full.csv"))


@pytest.mark.parametrize(
    "rows_by_venue",
    [
        {"twse": [_row("2330")], "tpex": [_row("6488", period="11507")]},
        {"twse": [_row("2330")], "tpex": [_row("2330")]},
        {"twse": [_row("2330", amount="NaN")], "tpex": [_row("6488")]},
    ],
    ids=("period-mismatch", "duplicate-natural-key", "nonfinite-amount"),
)
def test_capture_fails_closed_on_inconsistent_scope_or_decimal_values(
    tmp_path: Path,
    monkeypatch,
    rows_by_venue: dict[str, list[dict[str, str]]],
) -> None:
    result, calls, run_root = _run_capture(
        tmp_path,
        monkeypatch,
        rows_by_venue=rows_by_venue,
    )

    assert result["status"] == "rejected"
    assert len(calls) == 2
    assert result["diagnostics"]
    assert (run_root / "source" / "twse.json").exists()
    assert (run_root / "source" / "tpex.json").exists()
    assert not (run_root / "candidate_manifest.json").exists()


def test_capture_rejects_oversized_source_and_preserves_only_bounded_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    oversized = b"[" + b" " * capture_module.MAX_VENUE_ENTITY_BYTES
    result, calls, run_root = _run_capture(
        tmp_path,
        monkeypatch,
        bodies={"twse": oversized},
    )

    assert result["status"] == "failed"
    assert len(calls) == 2
    prefix_path = run_root / "source" / "twse.failed-prefix.bin"
    assert prefix_path.stat().st_size == capture_module.FAILED_BODY_PREFIX_BYTES
    capture = json.loads((run_root / "source" / "capture_run.json").read_text("utf-8"))
    assert capture["results"]["twse"]["body_capture_scope"] == "prefix_65536_bytes"
    assert capture["results"]["twse"]["persisted_prefix_bytes"] == (
        capture_module.FAILED_BODY_PREFIX_BYTES
    )
    assert "content_sha256" not in capture["results"]["twse"]


def test_capture_checks_disk_reserve_before_request_or_run_creation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(capture_module, "REPO_ROOT", tmp_path)
    output_parent = tmp_path / "candidates"

    def forbidden_opener(*_args, **_kwargs):
        pytest.fail("disk preflight must run before the official API request")

    result = capture_module._capture_monthly_revenue_research_candidate(
        candidate_parent=output_parent,
        opener=forbidden_opener,
        disk_usage=lambda _path: SimpleNamespace(
            free=(
                capture_module.MAX_AGGREGATE_ENTITY_BYTES
                + capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES
                - 1
            )
        ),
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "research_candidate_free_space_below_reserve"
    assert result["source_requests_made"] == 0
    assert output_parent.exists() is False


def test_candidate_writer_checks_each_write_reserve_before_create(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    target = run_root / "candidate.json"
    data = b'{"candidate":true}\n'

    with pytest.raises(OSError, match="minimum free-space reserve"):
        capture_module._write_create_only(
            target,
            data,
            allowed_root=run_root,
            disk_usage=lambda _path: SimpleNamespace(
                free=(
                    len(data)
                    + capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES
                    - 1
                )
            ),
            max_file_bytes=capture_module.MAX_CANDIDATE_METADATA_BYTES,
            reserve_bytes=capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES,
            prior_output_bytes=0,
        )

    assert target.exists() is False


def test_candidate_writer_enforces_file_and_run_output_caps(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    target = run_root / "candidate.json"
    no_disk_check = lambda _path: pytest.fail("size caps must be checked before disk use")

    with pytest.raises(ValueError, match="per-file limit"):
        capture_module._write_create_only(
            target,
            b"too large",
            allowed_root=run_root,
            disk_usage=no_disk_check,
            max_file_bytes=4,
            reserve_bytes=capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES,
            prior_output_bytes=0,
        )
    with pytest.raises(ValueError, match="total output limit"):
        capture_module._write_create_only(
            target,
            b"x",
            allowed_root=run_root,
            disk_usage=no_disk_check,
            max_file_bytes=4,
            reserve_bytes=capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES,
            prior_output_bytes=capture_module.MAX_CANDIDATE_OUTPUT_BYTES,
        )

    assert target.exists() is False


def test_candidate_writer_rejects_linked_parent_component(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    real_parent = run_root / "real"
    run_root.mkdir()
    real_parent.mkdir()
    linked_parent = run_root / "linked"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink privilege unavailable: {exc}")

    target = linked_parent / "candidate.json"
    with pytest.raises(ValueError, match="linked component"):
        capture_module._write_create_only(
            target,
            b'{"candidate":true}\n',
            allowed_root=run_root,
            disk_usage=lambda _path: SimpleNamespace(free=64 * 1024 * 1024),
            max_file_bytes=capture_module.MAX_CANDIDATE_METADATA_BYTES,
            reserve_bytes=capture_module.MINIMUM_FREE_SPACE_RESERVE_BYTES,
            prior_output_bytes=0,
        )

    assert (real_parent / "candidate.json").exists() is False


@pytest.mark.parametrize("failure_stage", ("write", "readback"))
def test_candidate_manifest_failure_never_reports_success(
    tmp_path: Path, monkeypatch, failure_stage: str
) -> None:
    if failure_stage == "write":
        original_write = capture_module._write_create_only

        def fail_manifest_write(path, data, **kwargs):
            if path.name == "candidate_manifest.json":
                raise OSError("injected candidate manifest write failure")
            return original_write(path, data, **kwargs)

        monkeypatch.setattr(capture_module, "_write_create_only", fail_manifest_write)
    else:
        original_readback = capture_module._read_bounded

        def mismatch_manifest_readback(path, max_bytes):
            data = original_readback(path, max_bytes)
            if path.name == "candidate_manifest.json":
                return data + b" "
            return data

        monkeypatch.setattr(capture_module, "_read_bounded", mismatch_manifest_readback)

    result, calls, run_root = _run_capture(tmp_path, monkeypatch)

    assert len(calls) == 2
    assert result["status"] == "rejected"
    assert result["candidate_manifest_file"] is None
    assert result["candidate_manifest_sha256"] is None
    assert result["diagnostics"]
    if failure_stage == "write":
        assert not (run_root / "candidate_manifest.json").exists()
    else:
        assert (run_root / "candidate_manifest.json").is_file()

    monkeypatch.setattr(
        capture_cli,
        "capture_monthly_revenue_research_candidate",
        lambda: result,
    )
    assert capture_cli.main([]) == 2
