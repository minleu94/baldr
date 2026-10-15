from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from data_module.institutional_credit_flows_service import (
    FlowCaptureError,
    HttpResponse,
    capture_recent_flows,
    rebuild_flow_manifest_from_raw,
)
from scripts import complete_institutional_credit_flows as capture_cli
from test_institutional_credit_flows_service import (
    SESSION_DATES,
    _date_from_params,
    _fake_transport,
    _twse_institutional_payload,
)


def _t86_only_transport() -> tuple[
    list[tuple[str, dict[str, str]]],
    Callable[[str, Mapping[str, str], int], HttpResponse],
]:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(
        url: str, params: Mapping[str, str], timeout_seconds: int
    ) -> HttpResponse:
        calls.append((url, dict(params)))
        if "fund/T86" not in url:
            raise AssertionError(f"unselected endpoint reached transport: {url}")
        return _fake_transport(url, dict(params), timeout_seconds)

    return calls, transport


def test_twse_scope_uses_only_t86_once_per_date_and_preserves_evidence(
    tmp_path: Path,
) -> None:
    calls, transport = _t86_only_transport()
    readback = capture_recent_flows(
        output_root=tmp_path / "flows",
        as_of_date=date(2026, 9, 8),
        sessions=2,
        max_lookback_days=2,
        transport=transport,
        rate_limit_seconds=0,
        capture_scope="twse_institutional",
    )

    assert all("fund/T86" in url for url, _ in calls)
    assert Counter(_date_from_params(params) for _, params in calls) == Counter(
        {session_date: 1 for session_date in SESSION_DATES}
    )

    manifest_path = Path(readback["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scope = manifest["capture_scope"]
    assert scope["name"] == "twse_institutional"
    assert scope["markets"] == ["TWSE"]
    assert scope["source_ids"] == ["institutional_flows"]
    assert scope["endpoint_ids"] == ["twse:T86"]
    assert set(scope["excluded_endpoint_ids"]) == {
        "tpex:3itrade",
        "twse:MI_MARGN",
        "tpex:margin_bal",
    }
    assert scope["coverage_basis"] == "selected_endpoints_only"
    assert readback["capture_scope"] == scope
    assert manifest["totals"] == {"institutional_flows": 2}
    assert set(manifest["code_shape_diagnostics"]) == {"institutional_flows"}
    assert set(readback["totals"]) == {"institutional_flows"}

    for source in manifest["sources"]:
        assert source["source_id"] == "institutional_flows"
        assert len(source["raw_artifacts"]) == 1
        artifact = source["raw_artifacts"][0]
        expected_bytes = _twse_institutional_payload(source["decision_date"])
        raw_path = manifest_path.parent / artifact["path"]
        assert raw_path.read_bytes() == expected_bytes
        assert artifact["sha256"] == hashlib.sha256(expected_bytes).hexdigest()

        metadata = json.loads(
            (manifest_path.parent / artifact["metadata_path"]).read_text(
                encoding="utf-8"
            )
        )
        assert metadata["endpoint_id"] == "twse:T86"
        assert metadata["payload_sha256"] == artifact["sha256"]

        candidate_path = manifest_path.parent / source["candidate_rows_path"]
        rows = json.loads(candidate_path.read_text(encoding="utf-8"))
        assert len(rows) == 1
        values = rows[0]["values"]
        for prefix in ("foreign_investor", "investment_trust", "dealer"):
            buy, sell, net = (
                values[f"{prefix}_{suffix}"] for suffix in ("buy", "sell", "net")
            )
            assert type(buy) is int
            assert type(sell) is int
            assert type(net) is int
            assert buy - sell == net


def test_invalid_capture_scope_fails_before_output_or_transport(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "must-not-exist"
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(
        url: str, params: Mapping[str, str], timeout_seconds: int
    ) -> HttpResponse:
        calls.append((url, dict(params)))
        return _fake_transport(url, dict(params), timeout_seconds)

    with pytest.raises(ValueError):
        capture_recent_flows(
            output_root=output_root,
            as_of_date=date(2026, 9, 8),
            sessions=1,
            max_lookback_days=1,
            transport=transport,
            rate_limit_seconds=0,
            capture_scope="credit_only",
        )

    assert calls == []
    assert not output_root.exists()


def test_rebuild_keeps_original_raw_and_replays_capture_scope(
    tmp_path: Path,
) -> None:
    _, transport = _t86_only_transport()
    capture_readback = capture_recent_flows(
        output_root=tmp_path / "flows",
        as_of_date=date(2026, 9, 8),
        sessions=1,
        max_lookback_days=1,
        transport=transport,
        rate_limit_seconds=0,
        capture_scope="twse_institutional",
    )
    original_manifest_path = Path(capture_readback["manifest_path"])
    run_dir = original_manifest_path.parent
    original_manifest_bytes = original_manifest_path.read_bytes()
    original_raw_bytes = {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "raw").rglob("*")
        if path.is_file()
    }

    replay_readback = rebuild_flow_manifest_from_raw(run_dir)

    assert replay_readback["capture_replayed_without_network"] is True
    assert original_manifest_path.read_bytes() == original_manifest_bytes
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "raw").rglob("*")
        if path.is_file()
    } == original_raw_bytes

    replay_manifest_path = Path(replay_readback["manifest_path"])
    replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    original_manifest = json.loads(original_manifest_bytes)
    assert replay_manifest["capture_scope"] == original_manifest["capture_scope"]
    assert replay_readback["capture_scope"] == original_manifest["capture_scope"]
    assert replay_manifest["totals"] == {"institutional_flows": 1}
    assert set(replay_manifest["code_shape_diagnostics"]) == {"institutional_flows"}
    assert set(replay_readback["totals"]) == {"institutional_flows"}


def test_capture_cli_forwards_scope_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: dict[str, object] = {}

    def fake_capture(**kwargs: object) -> dict[str, object]:
        received.update(kwargs)
        return {"manifest_path": "capture.json"}

    monkeypatch.setattr(capture_cli, "capture_recent_flows", fake_capture)
    result = capture_cli.main(
        [
            "capture",
            "--output-root",
            str(tmp_path / "flows"),
            "--as-of-date",
            "2026-09-08",
            "--sessions",
            "1",
            "--max-lookback-days",
            "1",
            "--rate-limit-seconds",
            "0",
            "--capture-scope",
            "twse_institutional",
        ]
    )

    assert result == 0
    assert received["capture_scope"] == "twse_institutional"
    assert received["as_of_date"] == date(2026, 9, 8)


def test_capture_cli_scope_default_and_choices() -> None:
    parser = capture_cli.build_parser()
    assert parser.parse_args(["capture"]).capture_scope == "legacy_all"
    assert (
        parser.parse_args(["capture", "--capture-scope", "twse_institutional"])
        .capture_scope
        == "twse_institutional"
    )
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["capture", "--capture-scope", "credit_only"])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("corruption", ["market", "duplicate", "missing", "extra_day", "unit"])
def test_scoped_replay_rejects_false_coverage_before_output(tmp_path: Path, corruption: str) -> None:
    """不能在重播時擴張市場／單位，或把缺件與重複分區當完成。"""
    _, transport = _t86_only_transport()
    captured = capture_recent_flows(
        output_root=tmp_path / "flows", as_of_date=date(2026, 9, 8),
        sessions=1, max_lookback_days=1, transport=transport,
        rate_limit_seconds=0, capture_scope="twse_institutional",
    )
    manifest_path = Path(captured["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_entry = manifest["sources"][0]["raw_artifacts"][0]
    if corruption == "market":
        manifest["capture_scope"]["markets"] = ["TPEx"]
    elif corruption == "duplicate":
        manifest["sources"][0]["raw_artifacts"].append(dict(raw_entry))
    elif corruption == "missing":
        manifest["sources"][0]["raw_artifacts"] = []
    elif corruption == "extra_day":
        manifest["discovered_sessions"].append("2026-09-07")
    else:
        metadata_path = manifest_path.parent / raw_entry["metadata_path"]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["quantity_unit"] = "lots"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FlowCaptureError):
        rebuild_flow_manifest_from_raw(manifest_path.parent)
    assert not (manifest_path.parent / "candidate_v2").exists()
    assert not (manifest_path.parent / "manifest_with_observed_at.json").exists()


def test_old_unscoped_bundle_remains_replayable(tmp_path: Path) -> None:
    captured = capture_recent_flows(
        output_root=tmp_path / "flows", as_of_date=date(2026, 9, 8),
        sessions=1, max_lookback_days=1, transport=_fake_transport, rate_limit_seconds=0,
    )
    manifest_path = Path(captured["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["capture_scope"]["name"] == "legacy_all"
    assert len(manifest["capture_scope"]["endpoint_ids"]) == 4
    del manifest["capture_scope"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    replay = rebuild_flow_manifest_from_raw(manifest_path.parent)
    assert replay["totals"] == {"institutional_flows": 2, "credit_transactions": 2}
    assert "capture_scope" not in replay
    saved = json.loads(Path(replay["manifest_path"]).read_text(encoding="utf-8"))
    assert "capture_scope" not in saved
