"""用明示 request raw pin 處理完整已保存 H20 cohort；不發現 latest、不啟 Task。"""
from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.recommendation.personal_current_observed_h20_capture import (
    H20CaptureError, digest, read_personal_current_observed_h20_capture, require_digest,
)
from app_module.recommendation.queries import _read_regular_file_no_follow
from app_module.recommendation.personal_h20_natural_outcome_batch import run_personal_h20_natural_outcome_batch
from scripts.scheduled.run_personal_current_observed_h20_daily import personal_current_observed_h20_read_ports

REQUEST_SCHEMA = "personal-h20-natural-outcome-batch-request.v1"
REQUIRED = frozenset({"schema_version", "manifest_path", "manifest_sha256", "root"})
OPTIONAL = frozenset({"input_capture_path", "input_capture_sha256", "outcome_path", "outcome_sha256"})


def decode_request(path: str | Path, raw_sha256: str) -> Mapping[str, Any]:
    """同份有界 nofollow raw bytes decode；不接受模糊路徑、未知 key 或 caller 時鐘。"""
    file = Path(path)
    require_digest(raw_sha256)
    raw = _read_regular_file_no_follow(file, file.parent, max_bytes=64 * 1024)
    if digest(raw) != raw_sha256:
        raise H20CaptureError("natural_batch_request_raw_pin_mismatch")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise H20CaptureError("duplicate_json_key")
            result[key] = value
        return result
    def reject(value: str) -> None:
        raise H20CaptureError("nonfinite_json:" + value)
    request = json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
    if not isinstance(request, dict):
        raise H20CaptureError("natural_batch_request_object_required")
    if (set(request) - REQUIRED - OPTIONAL or not REQUIRED <= set(request)
            or request["schema_version"] != REQUEST_SCHEMA):
        raise H20CaptureError("natural_batch_exact_request_schema_required")
    for key in ("root", "manifest_path", "input_capture_path", "outcome_path"):
        value = request.get(key)
        if value is None and key in OPTIONAL:
            continue
        if (not isinstance(value, str) or not Path(value).is_absolute()
                or ".." in Path(value).parts or any(c in value for c in "*?")):
            raise H20CaptureError("natural_batch_absolute_exact_path_required")
    for key in ("manifest_sha256", "input_capture_sha256", "outcome_sha256"):
        if request.get(key) is not None:
            require_digest(request[key])
    for prefix in ("input_capture", "outcome"):
        if (request.get(prefix + "_path") is None) != (request.get(prefix + "_sha256") is None):
            raise H20CaptureError("natural_batch_exact_path_pin_pair_required")
    if request.get("outcome_path") is not None and request.get("input_capture_path") is None:
        raise H20CaptureError("exact_input_capture_required_for_outcome")
    return {k: v for k, v in request.items() if k != "schema_version"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        request = decode_request(args.request_json, args.request_sha256)
        ports = personal_current_observed_h20_read_ports()
        prediction_reader = partial(read_personal_current_observed_h20_capture,
            source_verifier=ports["source_verifier"], contract_verifier=ports["contract_verifier"])
        result = run_personal_h20_natural_outcome_batch(**request, prediction_reader=prediction_reader,
            source_verifier=ports["source_verifier"], contract_verifier=ports["contract_verifier"],
            input_capture_verifier=ports["input_capture_verifier"], outcome_verifier=ports["outcome_verifier"])
    except (KeyboardInterrupt, InterruptedError):
        result = {"status": "cancelled"}
    except Exception as exc:
        result = {"status": "failed", "error_type": type(exc).__name__, "reason": str(exc)}
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "completed" else 130 if result["status"] == "cancelled" else 2


if __name__ == "__main__":
    raise SystemExit(main())
