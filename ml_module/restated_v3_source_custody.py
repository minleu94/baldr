"""核對官方市場 v3 的實際 build-start 證據，不放寬舊 sidecar 契約。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from data_module.ml_restatement_research_dataset_v3 import SOURCE_FILES, V3_SCHEMA_VERSION
from data_module.ml_restatement_official_market import file_sha256


def _clock(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("v3 custody 缺少時鐘")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("v3 custody 時鐘須含時區")
    return result


def _same_path(left: Any, right: Path) -> bool:
    return isinstance(left, str) and os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(right.resolve()))


def validate_v3_source_custody(
    payload: Mapping[str, Any], *, manifest_path: Path, manifest_hash: str,
    manifest: Mapping[str, Any], row_count: int,
) -> None:
    if (
        manifest.get("schema_version") != V3_SCHEMA_VERSION
        or payload.get("schema_version") != "model-repair-source-custody.v2"
        or payload.get("historical_pit") is not False
    ):
        raise ValueError("v3 dataset 必須使用實際開始證據的 custody v2")
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict) or (
        not _same_path(dataset.get("manifest_path"), manifest_path)
        or dataset.get("manifest_file_sha256") != manifest_hash
        or dataset.get("dataset_identity_hash") != manifest.get("dataset_identity_hash")
        or type(dataset.get("row_count")) is not int or dataset["row_count"] != row_count
        or dataset.get("build_status") != "complete_research_build"
    ):
        raise ValueError("v3 custody 與資料集 path/hash/identity/count 不符")
    for field in ("source_hashes", "computation_source_hashes", "market_source"):
        if payload.get(field) != manifest.get(field):
            raise ValueError(f"v3 custody {field} 與封存清冊不符")
    clocks = payload.get("job_clocks")
    if not isinstance(clocks, dict) or (
        clocks.get("start_source_verification") != "observed_before_build"
        or clocks.get("end_source_verification") != "rechecked_before_manifest_publication"
    ):
        raise ValueError("v3 custody 缺少真實開始／完成來源檢查")
    started = _clock(clocks.get("started_at_observed"))
    verified = _clock(clocks.get("start_source_verified_at"))
    finished = _clock(clocks.get("finished_at"))
    revision = _clock(clocks.get("revision_observed_at"))
    created = _clock(manifest.get("dataset_created_at"))
    if (
        not started <= verified == revision <= created <= finished <= datetime.now(timezone.utc)
        or revision != _clock(manifest.get("revision_observed_at"))
        or revision != _clock(manifest.get("training_as_of"))
        or _clock(manifest["market_source"]["available_at"]) > started
    ):
        raise ValueError("v3 custody 執行時鐘、來源可得性或修訂鐘不一致")
    start_binding = payload.get("source_start")
    if not isinstance(start_binding, dict) or not isinstance(start_binding.get("path"), str):
        raise ValueError("v3 custody 缺少 source_start binding")
    start_path = Path(start_binding["path"]).resolve(strict=True)
    if start_path.is_relative_to(manifest_path.resolve().parent):
        raise ValueError("v3 source_start 證據須在封存資料集外")
    if file_sha256(start_path) != start_binding.get("file_sha256"):
        raise ValueError("v3 source_start 檔案 hash 不符")
    start = json.loads(start_path.read_text(encoding="utf-8"))
    sources = manifest["source_hashes"]
    if not isinstance(start, dict) or (
        start.get("schema_version") != "model-repair-source-start.v1"
        or start.get("historical_pit") is not False
        or _clock(start.get("started_at")) != started
        or _clock(start.get("source_verified_at")) != verified
        or start.get("computation_source_hashes") != manifest["computation_source_hashes"]
        or start.get("snapshot_db_sha256") != sources["snapshot_db"]["sha256"]
        or start.get("official_market_manifest_sha256") != sources["official_market_capture"]["file_sha256"]
        or start.get("direct_manifest_file_sha256") != sources["direct_manifest"]["file_sha256"]
    ):
        raise ValueError("v3 source_start 內容與完成清冊不一致")
    code_root = payload.get("source_code_root")
    if not isinstance(code_root, str) or not _same_path(start.get("source_code_root"), Path(code_root)):
        raise ValueError("v3 producer code root 前後不一致")
    for name, relative in SOURCE_FILES.items():
        source_path = Path(code_root) / relative
        if not source_path.is_file() or file_sha256(source_path) != manifest["computation_source_hashes"][name]:
            raise ValueError(f"v3 producer source 已變更：{name}")
    if file_sha256(start_path) != start_binding["file_sha256"]:
        raise ValueError("v3 source_start 在驗證期間變更")


def v3_custody_identity(payload: Mapping[str, Any], *, sidecar_hash: str) -> dict[str, Any]:
    """僅整理已由 validator 驗證的內容；不捏造不存在的 git commit。"""
    return {
        "schema_version": "model-repair-source-custody.v2", "status": "verified",
        "sidecar_sha256": sidecar_hash,
        "dataset": payload["dataset"], "source_start": payload["source_start"],
        "job_clocks": payload["job_clocks"], "source_code_root": payload["source_code_root"],
        "computation_source_hashes": payload["computation_source_hashes"],
        "market_source": payload["market_source"],
    }
