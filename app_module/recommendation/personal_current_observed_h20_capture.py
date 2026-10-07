"""保存原 H20 模型研究輸出；來源與模型驗證由 composition 注入。"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

Verifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]
SCHEMA = "personal-current-observed-h20-prediction.v1"
MAX_BYTES = 16 * 1024 * 1024


class H20CaptureError(ValueError):
    """來源、保存或讀回契約不符。"""


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def require_digest(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise H20CaptureError("exact_sha256_required")
    if any(c not in "0123456789abcdef" for c in value[7:]):
        raise H20CaptureError("exact_sha256_required")
    return value


def plain(path: Path, *, file: bool = False) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise H20CaptureError("absolute_plain_path_required")
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise H20CaptureError("link_or_reparse_rejected")
        if part == path and file:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise H20CaptureError("single_link_regular_file_required")
        elif not stat.S_ISDIR(info.st_mode):
            raise H20CaptureError("plain_directory_required")


def _stat_key(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def _directory_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    """核對父路徑身份；合法兄弟項目新增不改變原檔來源身份。"""
    return info.st_dev, info.st_ino, info.st_mode, getattr(info, "st_file_attributes", 0)


def read_pinned_json(path: Path, expected: str | None = None) -> dict[str, Any]:
    plain(path, file=True)
    before = path.stat()
    ancestors = [(p, _directory_identity(p.lstat())) for p in path.parents]
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        if _stat_key(os.fstat(fd)) != _stat_key(before) or before.st_size > MAX_BYTES:
            raise H20CaptureError("source_changed_or_over_budget")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_BYTES + 1)
        plain(path, file=True)
        if (len(raw) != before.st_size or _stat_key(os.fstat(fd)) != _stat_key(before)
                or _stat_key(path.stat()) != _stat_key(before)
                or any(_directory_identity(p.lstat()) != key for p, key in ancestors)):
            raise H20CaptureError("source_changed_during_read")
    finally:
        os.close(fd)
    if expected is not None and digest(raw) != require_digest(expected):
        raise H20CaptureError("raw_pin_mismatch")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise H20CaptureError("duplicate_json_key")
            result[key] = item
        return result
    def reject(value: str) -> None:
        raise H20CaptureError("nonfinite_json:" + value)
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
    if not isinstance(value, dict):
        raise H20CaptureError("json_object_required")
    return value


def publish(root: Path, directory: str, name: str, payload: Mapping[str, Any]) -> Path:
    plain(root)
    target_dir = root / directory
    target_dir.mkdir(exist_ok=True)
    plain(target_dir)
    target = target_dir / name
    raw = encoded(payload)
    if len(raw) > MAX_BYTES:
        raise H20CaptureError("capture_over_budget")
    if target.exists():
        if read_pinned_json(target) != payload:
            raise H20CaptureError("create_only_conflict")
        return target
    fd, temp_name = tempfile.mkstemp(prefix=".h20-", dir=target_dir)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        plain(target_dir)
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
    finally:
        temporary.unlink()
    if read_pinned_json(target, digest(raw)) != payload:
        raise H20CaptureError("publish_readback_mismatch")
    return target


def _assert_store_sources(root: Path, source: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """僅已選 FA_Data/personal/recommendation_h20 可位於市場根內。"""
    from app_module.personal_data_paths import resolve_personal_data_paths
    from app_module.personal_store_selection import assert_personal_store_path

    market = Path(source["data_root"])
    if not market.is_absolute() or ".." in market.parts:
        raise H20CaptureError("absolute_source_path_required")
    if root.is_relative_to(market):
        if root != market / "personal" / "recommendation_h20":
            raise H20CaptureError("personal_store_must_be_disjoint_from_sources")
        paths = resolve_personal_data_paths(market, personal_root=market / "personal", environ={})
        assert_personal_store_path(paths, root / "activation.json")
    elif root == market or root in market.parents:
        raise H20CaptureError("personal_store_must_be_disjoint_from_sources")
    for candidate in (contract["fit_receipt_path"], contract["artifact_root"],
                      source["pins"]["snapshot_database_path"]):
        path = Path(candidate)
        if (not path.is_absolute() or ".." in path.parts or root == path
                or root in path.parents or path in root.parents):
            raise H20CaptureError("personal_store_must_be_disjoint_from_sources")


def _clock(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None or value > datetime.now(timezone.utc):
        raise H20CaptureError("true_aware_observation_required")
    return value


def _binding(source: Mapping[str, Any], contract: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    return {"cycle_id": source["cycle_id"], "cycle_terminal_sha256": source["cycle_terminal_sha256"],
            "inference_pin_hash": digest(encoded({k: v for k, v in source["pins"].items() if k != "observed_at"})),
            "decision_date": source["decision_date"], "symbol": symbol,
            "candidate_id": contract["candidate_id"], "contract_hash": contract["contract_hash"],
            "fit_receipt_sha256": contract["fit_receipt_sha256"]}


def _retry_key(identity: Mapping[str, Any]) -> str:
    # 同 raw cycle/model/symbol 跨午夜重試仍取得第一次原輸出；日期留在 payload 身分。
    return digest(encoded({k: v for k, v in identity.items() if k != "decision_date"}))[7:]


def _validate(payload: Mapping[str, Any], source_verifier: Verifier, contract_verifier: Verifier) -> None:
    if not callable(source_verifier) or not callable(contract_verifier):
        raise H20CaptureError("verification_ports_required")
    if payload.get("schema_version") != SCHEMA or "result_id" in payload or payload.get("research_only") is not True:
        raise H20CaptureError("research_prediction_schema_required")
    if any(payload.get(k) is not False for k in
           ("historical_pit_eligible", "formal_training_allowed", "production_action_allowed", "promotion_credit_created")):
        raise H20CaptureError("qualification_not_allowed")
    source = payload["source_binding"]
    contract = payload["contract_binding"]
    for value in (source["cycle_terminal_sha256"], contract["contract_hash"],
                  contract["fit_receipt_sha256"], contract["artifact_hash"], contract["lineage_hash"]):
        require_digest(value)
    if dict(source_verifier(source)) != source or dict(contract_verifier(contract)) != contract:
        raise H20CaptureError("verified_binding_mismatch")
    observed = _clock(payload["observed_at"])
    if observed.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat() != source["decision_date"]:
        raise H20CaptureError("decision_observation_day_mismatch")
    symbol = payload["identity"]["symbol"]
    identity = _binding(source, contract, symbol)
    if payload["identity"] != identity or payload["sample_id"] != "h20-observed:" + digest(encoded(identity))[7:]:
        raise H20CaptureError("sample_identity_mismatch")
    prediction = payload["prediction"]
    request = prediction["request"]
    row = source["feature_rows_by_symbol"][symbol]
    if _clock(row["local_current_observed_at"]) > observed:
        raise H20CaptureError("feature_observed_after_prediction")
    if (prediction["status"] != "h20_gross_available" or type(prediction["predicted_gross_return_bp"]) is not int
            or prediction.get("blockers") not in ([], ())
            or prediction["model_contract_hash"] != contract["contract_hash"]
            or prediction["artifact_hash"] != contract["artifact_hash"]
            or prediction["lineage_hash"] != contract["lineage_hash"]
            or prediction["model_id"] != contract["model_id"]
            or prediction["model_version"] != contract["model_version"]
            or prediction["target"] != "absolute_forward_stock_return_bp"
            or type(prediction["horizon_trading_days"]) is not int or prediction["horizon_trading_days"] != 20
            or prediction["price_basis"] != "close_to_close_event_date"
            or prediction["cost_basis"] != "no_cost_gross"
            or prediction["contract_version"] != "personal-h20-gross.v1"
            or any(prediction.get(k) is not False for k in ("formal_eligible", "natural_evidence_eligible", "production_action_allowed"))):
        raise H20CaptureError("original_h20_output_mismatch")
    if (request["symbol"] != symbol or request["decision_date"] != source["decision_date"]
            or request["feature_snapshot_hash"] != row["row_sha256"]
            or request["feature_source_hash"] != source["source_fingerprint"]
            or request["model_contract_hash"] != contract["contract_hash"]
            or request["feature_schema"] != contract["feature_schema"]
            or any(value is not None and type(value) is not int for value in request["feature_values"])
            or request["feature_values"] != [value for _, value in row["values"]]
            or request["feature_as_of_date"] != row["feature_as_of_date"]
            or request["feature_available_date"] != source["decision_date"]
            or date.fromisoformat(request["feature_as_of_date"]) >= date.fromisoformat(request["decision_date"])):
        raise H20CaptureError("original_request_source_mismatch")
    original_request_hash = digest(json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if prediction["prediction_id"] != "personal-h20:" + original_request_hash[7:]:
        raise H20CaptureError("original_prediction_identity_mismatch")
    body = dict(payload)
    declared = body.pop("payload_sha256")
    if declared != digest(encoded(body)):
        raise H20CaptureError("capture_content_hash_mismatch")


def read_personal_current_observed_h20_capture(path: str | Path, *, root: str | Path,
        source_verifier: Verifier, contract_verifier: Verifier, expected_sha256: str | None = None) -> dict[str, Any]:
    file = Path(path)
    if file.parent != Path(root) / "h20_predictions" or file.suffix != ".json":
        raise H20CaptureError("capture_outside_personal_store")
    payload = read_pinned_json(file, expected_sha256)
    _assert_store_sources(Path(root), payload["source_binding"], payload["contract_binding"])
    _validate(payload, source_verifier, contract_verifier)
    if file.stem not in {payload["sample_id"].split(":", 1)[1], _retry_key(payload["identity"])}:
        raise H20CaptureError("filename_identity_mismatch")
    return payload


def capture_personal_current_observed_h20_prediction(*, root: str | Path,
        source_binding: Mapping[str, Any], contract_binding: Mapping[str, Any], symbol: str,
        source_verifier: Verifier, contract_verifier: Verifier,
        predictor: Callable[[], Mapping[str, Any]], cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    if not all(callable(port) for port in (source_verifier, contract_verifier, predictor)):
        raise H20CaptureError("verification_and_prediction_ports_required")
    destination_root = Path(root)
    plain(destination_root)
    _assert_store_sources(destination_root, source_binding, contract_binding)
    # 同 cycle/model/day/symbol 先讀原保存值；不以新 clock 或新推論改寫自然樣本。
    identity = _binding(source_binding, contract_binding, symbol)
    sample_id = "h20-observed:" + digest(encoded(identity))[7:]
    retry_key = _retry_key(identity)
    destination = destination_root / "h20_predictions" / (retry_key + ".json")
    # 相容本輪早先已發布的完整 sample-id 檔名；只建原 pin 指標，不複製預測。
    legacy = destination_root / "h20_predictions" / (sample_id.split(":", 1)[1] + ".json")
    reference = destination_root / "h20_prediction_refs" / (retry_key + ".json")
    expected_existing_sha: str | None = None
    if reference.exists():
        ref = read_pinned_json(reference)
        destination = Path(ref["prediction_path"])
        expected_existing_sha = require_digest(ref["prediction_sha256"])
    elif not destination.exists() and legacy.exists():
        destination = legacy
    if destination.exists():
        existing = read_personal_current_observed_h20_capture(destination, root=root,
            expected_sha256=expected_existing_sha, source_verifier=source_verifier, contract_verifier=contract_verifier)
        if _retry_key(existing["identity"]) != retry_key:
            raise H20CaptureError("retry_identity_conflict")
        if destination == legacy:
            publish(destination_root, "h20_prediction_refs", retry_key + ".json",
                {"prediction_path": str(destination), "prediction_sha256": digest(encoded(existing))})
        return {"path": str(destination), "raw_sha256": digest(encoded(existing)), "idempotent": True,
                "sample_id": existing["sample_id"], "prediction_id": existing["prediction"]["prediction_id"]}
    if reference.exists():
        raise H20CaptureError("retry_original_prediction_missing")
    if cancelled is not None and cancelled():
        raise InterruptedError("cancelled_before_prediction")
    source = dict(source_verifier(source_binding))
    contract = dict(contract_verifier(contract_binding))
    if source != source_binding or contract != contract_binding:
        raise H20CaptureError("verified_binding_mismatch")
    observation = datetime.now(timezone.utc).isoformat()
    prediction = json.loads(encoded(predictor()))
    body: dict[str, Any] = {"schema_version": SCHEMA, "sample_id": sample_id,
        "identity": identity, "observed_at": observation, "source_binding": source,
        "contract_binding": contract, "prediction": prediction,
        "historical_pit_eligible": False, "formal_training_allowed": False,
        "production_action_allowed": False, "promotion_credit_created": False, "research_only": True,
        "natural_outcome_status": "pending_exact_entry_capture_and_twenty_sessions"}
    body["payload_sha256"] = digest(encoded(body))
    _validate(body, source_verifier, contract_verifier)
    path = publish(destination_root, "h20_predictions", retry_key + ".json", body)
    read_personal_current_observed_h20_capture(path, root=root,
        source_verifier=source_verifier, contract_verifier=contract_verifier)
    return {"path": str(path), "raw_sha256": digest(encoded(body)), "idempotent": False,
            "sample_id": sample_id, "prediction_id": prediction["prediction_id"]}
