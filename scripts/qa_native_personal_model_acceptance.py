"""以隔離 QA snapshot 驅動個人校準模型的 Qt MainWindow 控件驗收旅程。

此工具只使用 qa_personal_research_ui 已準備的工作區。候選目錄維持
output/qa/pc-fit-v7 唯讀；每個模型階段會以該 run 的 working DB 重新計算
user-declared source-time proof，並核對 V2 policy bytes、來源路徑與檔案身分。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from numbers import Integral
from typing import Any, Mapping
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import qa_personal_research_ui as isolated_launcher


QA_ROOT = REPOSITORY_ROOT / "output" / "qa" / "personal_daily_product_20261006"
RUN_ROOT_BASE = isolated_launcher.RUNS_ROOT
LEARNING_OUTPUT_ROOT = REPOSITORY_ROOT / "output" / "qa" / "pc-fit-v7"
LEARNING_ROOT = LEARNING_OUTPUT_ROOT / "recommendation_learning"
CANDIDATE_ID = "rec-cal-3f8b2c276ef316e28de3806d"
CANDIDATE_ROOT = (
    LEARNING_ROOT
    / "runs"
    / "2026-09-28"
    / "user-declared-snapshot-unified-v7"
    / "candidates"
    / CANDIDATE_ID
)
CANDIDATE_FILE_SHA256 = {
    "candidate.json": "8eeddbbd894a575fbb0ca760474ead035f23deb428c937f8d29667fcc3991328",
    "manifest.json": "2ccceffc7523cdca6834c6df62240096ca88e174455e95f831719b2ec3550a7b",
    "recommendation_calibration.joblib": "8890df64cb66d73af1b34755053d271dad4d38450bdb6e51578681e8684d7310",
    "run_input_binding.json": "395e39f6f0f8a36384812d346251f42306270b5ed5c46694da7b6fd6e89fab67",
}
LINEAGE_SHA256 = "08196ab227047a9df558f15589a35b8ae5613beb7ffead353a383f0189ee3b09"
EXPECTED_SOURCE_SLICE_SHA256 = (
    "sha256:7164751fa33721eff31e763e163a6d23146ff8783a42517059096be196e40875"
)
CANDIDATE_PINS = {
    "candidate_id": CANDIDATE_ID,
    "candidate_json_sha256": "sha256:8eeddbbd894a575fbb0ca760474ead035f23deb428c937f8d29667fcc3991328",
    "candidate_manifest_hash": "sha256:dad777c5eabd4d5af6dccdfc41d603eeb21a5c2b6faaef117b8ba61d3f8ed596",
    "candidate_artifact_hash": "sha256:8890df64cb66d73af1b34755053d271dad4d38450bdb6e51578681e8684d7310",
    "candidate_freeze_hash": "sha256:304ba9b5fa479cd86c177b218197476ac19b7fd5fd7338d2d2c9359480bb9dea",
    "dataset_hash": "sha256:c7605dfabeede76bff22503d9b51451c785473bd6f08c161d2335193adf4669d",
}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SOURCE_SLICE_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_PHASE_SECONDS = 60 * 90
MAX_PROJECTION_RECEIPT_BYTES = 64 * 1024 * 1024
STAGE_TIMEOUT_SECONDS = {
    "waiting_inventory": 10 * 60,
    "waiting_candidate_selection": 10 * 60,
    "waiting_preview": 10 * 60,
    "waiting_policy_revalidation": 10 * 60,
    "waiting_execution": 60 * 60,
    "waiting_save_dialog": 3 * 60,
    "waiting_save": 10 * 60,
    "waiting_capture": 5 * 60,
    "waiting_reload_inventory": 10 * 60,
    "waiting_reload_candidate_selection": 10 * 60,
    "waiting_reload_proof": 10 * 60,
    "waiting_rule_only_save": 3 * 60,
    "waiting_history": 3 * 60,
    "waiting_rollback_candidate_selection": 10 * 60,
    "waiting_rollback_proposal": 10 * 60,
    "waiting_rollback_confirmation": 3 * 60,
    "waiting_rollback_save": 10 * 60,
    "waiting_final_rule_only": 3 * 60,
}


class AcceptanceError(RuntimeError):
    """隔離工作區、候選或來源時間 proof 不符合驗收條件。"""

    def __init__(
        self,
        message: str,
        *,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostic = dict(diagnostic or {})


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_identity_value(value: Any) -> tuple[Any, ...]:
    """將 sealed event 與 JSON receipt 身份遞迴投影到同一種值形狀。

    Execution 封存時會把 JSON list 正規化為 tuple，並把 float 轉成
    Decimal；receipt readback 則保留 list/float。此投影只統一這些表示法，
    不省略任何欄位，也不把 bool、integer 與 decimal 混為一談。
    """

    if value is None:
        return ("none",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("integer", value)
    if type(value) is str:
        return ("string", value)
    if type(value) is float or isinstance(value, Decimal):
        try:
            number = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise AcceptanceError("candidate identity 含無效 decimal") from exc
        if not number.is_finite():
            raise AcceptanceError("candidate identity decimal 必須是有限值")
        return ("decimal", number)
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise AcceptanceError("candidate identity mapping key 必須是 str")
        return (
            "mapping",
            tuple(
                (key, _canonical_identity_value(value[key]))
                for key in sorted(value)
            ),
        )
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_canonical_identity_value(item) for item in value))
    raise AcceptanceError(
        f"candidate identity 含不支援型別：{type(value).__name__}"
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_create_only(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    isolated_launcher._assert_no_reparse_components(path.parent, allow_missing=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256_bytes(content)


def _write_json_create_only(path: Path, payload: Any) -> str:
    return _write_create_only(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n",
    )


def _run_root(run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise AcceptanceError("run_id 僅接受 1–64 個英數、底線或連字號")
    path = RUN_ROOT_BASE / run_id
    normalized = isolated_launcher._assert_no_reparse_components(
        path, allow_missing=True
    )
    if normalized != path.resolve(strict=False):
        raise AcceptanceError("run root 路徑正規化不一致")
    if not isolated_launcher._is_within(normalized, RUN_ROOT_BASE.resolve(strict=False)):
        raise AcceptanceError("run root 必須位於 personal_research_ui 隔離子樹")
    return normalized


def _layout(run_root: Path) -> isolated_launcher.RuntimeLayout:
    expected = isolated_launcher._runtime_layout(run_root)
    if not isolated_launcher._same_path(
        expected.policy_config_path,
        run_root / "app_config" / "personal_use_policy.json",
    ):
        raise AcceptanceError("policy path 不符合隔離 launcher 的固定 layout")
    return expected


def _read_json_regular(path: Path, *, max_bytes: int) -> dict[str, Any]:
    content = isolated_launcher._read_bounded_bytes(path, max_bytes)
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"JSON 無效：{path}") from exc
    if type(value) is not dict:
        raise AcceptanceError(f"JSON 必須是 object：{path}")
    return value


def _verify_candidate_bundle() -> dict[str, Any]:
    root = isolated_launcher._assert_no_reparse_components(
        CANDIDATE_ROOT, allow_missing=False
    )
    learning = isolated_launcher._assert_no_reparse_components(
        LEARNING_ROOT, allow_missing=False
    )
    if not isolated_launcher._is_within(root, learning):
        raise AcceptanceError("固定 candidate root 必須留在 pc-fit-v7 learning root")
    raw_hashes: dict[str, str] = {}
    for name, expected_hash in CANDIDATE_FILE_SHA256.items():
        actual_hash, _size = isolated_launcher._sha256_regular_file(
            root / name,
            max_bytes=isolated_launcher.LEARNING_PIN_MAX_FILE_BYTES,
        )
        if actual_hash != expected_hash:
            raise AcceptanceError(f"候選固定檔案 SHA 不符：{name}")
        raw_hashes[name] = actual_hash
    candidate = _read_json_regular(root / "candidate.json", max_bytes=256 * 1024)
    manifest = _read_json_regular(root / "manifest.json", max_bytes=256 * 1024)
    binding = _read_json_regular(root / "run_input_binding.json", max_bytes=256 * 1024)
    if (
        candidate.get("candidate_id") != CANDIDATE_ID
        or candidate.get("shadow_only") is not True
        or candidate.get("production_eligible") is not False
        or candidate.get("production_action_allowed") is not False
        or manifest.get("model_id") != CANDIDATE_ID
        or manifest.get("artifact_hash") != CANDIDATE_PINS["candidate_artifact_hash"]
        or binding.get("candidate_id") != CANDIDATE_ID
    ):
        raise AcceptanceError("候選、manifest 或 run binding 身分／安全標記不符")
    lineage_raw_path = candidate.get("training_lineage_manifest_path")
    if type(lineage_raw_path) is not str or not Path(lineage_raw_path).is_absolute():
        raise AcceptanceError("候選缺少絕對 training lineage path")
    lineage_path = isolated_launcher._assert_no_reparse_components(
        Path(lineage_raw_path), allow_missing=False
    )
    if not isolated_launcher._is_within(lineage_path, learning):
        raise AcceptanceError("training lineage 必須留在唯讀 pc-fit-v7 learning root")
    lineage_hash, _lineage_size = isolated_launcher._sha256_regular_file(
        lineage_path,
        max_bytes=isolated_launcher.LEARNING_PIN_MAX_FILE_BYTES,
    )
    if lineage_hash != LINEAGE_SHA256:
        raise AcceptanceError("固定候選 training lineage SHA 不符")
    return {
        "candidate_id": CANDIDATE_ID,
        "candidate_root": str(root),
        "candidate_pins": dict(CANDIDATE_PINS),
        "candidate_file_sha256": raw_hashes,
        "lineage_path": str(lineage_path),
        "lineage_sha256": lineage_hash,
        "learning_root_written": False,
    }


def _dto_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    method = getattr(value, "to_dict", None)
    if callable(method):
        result = method()
        if isinstance(result, Mapping):
            return dict(result)
    raise AcceptanceError(f"不支援的 proof DTO：{type(value).__name__}")


def _source_binding_mismatches(
    *,
    policy: Mapping[str, Any],
    proposal: Mapping[str, Any],
    config_db_path: Path,
    expected_candidate_root: Path,
    actual_file_identity: Mapping[str, int],
) -> list[str]:
    """純欄位比較；不將 DB size、official PIT 或 UI 自述當成 proof。"""

    problems: list[str] = []
    trust = policy.get("source_time_trust")
    policy_candidate = policy.get("candidate")
    if type(trust) is not dict or type(policy_candidate) is not dict:
        return ["policy_source_time_trust_missing"]
    if (
        policy.get("schema_version") != "recommendation-personal-use-policy.v2"
        or policy.get("mode") != "personal_calibrated_probability"
    ):
        problems.append("policy_not_v2_calibrated")
    if trust.get("basis") != "user_declared_source_time":
        problems.append("source_time_basis_mismatch")
    if trust.get("research_only") is not True:
        problems.append("source_not_research_only")
    if trust.get("official_historical_pit_verified") is not False:
        problems.append("official_pit_marker_mismatch")
    if proposal.get("basis") != "user_declared_source_time":
        problems.append("proposal_basis_mismatch")
    if proposal.get("research_only") is not True:
        problems.append("proposal_research_marker_mismatch")
    if proposal.get("official_historical_pit_verified") is not False:
        problems.append("proposal_official_marker_mismatch")
    try:
        runtime_path = config_db_path.resolve(strict=True)
        trust_path = Path(str(trust.get("source_database_path", ""))).resolve(
            strict=True
        )
        proposal_path = Path(str(proposal.get("source_database_path", ""))).resolve(
            strict=True
        )
    except (OSError, RuntimeError, ValueError):
        return problems + ["source_database_path_unresolvable"]
    if not (
        isolated_launcher._same_path(runtime_path, trust_path)
        and isolated_launcher._same_path(runtime_path, proposal_path)
    ):
        problems.append("source_database_path_mismatch")
    proposal_identity = proposal.get("file_identity")
    trust_identity = trust.get("file_identity")
    if proposal_identity != trust_identity:
        problems.append("source_file_identity_mismatch")
    if proposal_identity != dict(actual_file_identity):
        problems.append("runtime_file_identity_mismatch")
    slice_hash = proposal.get("source_slice_sha256")
    if (
        type(slice_hash) is not str
        or not SOURCE_SLICE_PATTERN.fullmatch(slice_hash)
        or slice_hash != trust.get("source_slice_sha256")
        or slice_hash != EXPECTED_SOURCE_SLICE_SHA256
    ):
        problems.append("source_slice_sha256_mismatch")
    proposal_scope = proposal.get("replay_scope")
    trust_scope = trust.get("replay_scope")
    scope_shape_ok = False
    if type(proposal_scope) is dict:
        dates = proposal_scope.get("decision_dates")
        symbols = proposal_scope.get("symbols")
        datasets = proposal_scope.get("dataset_ids")
        scope_shape_ok = (
            type(dates) in (list, tuple)
            and type(symbols) in (list, tuple)
            and type(datasets) in (list, tuple)
            and all(type(value) is str for value in dates)
            and all(type(value) is str for value in symbols)
            and all(type(value) is str for value in datasets)
            and proposal_scope.get("sample_count") == 512
            and len(dates) == 64
            and len(symbols) == 8
            and bool(datasets)
        )
    if (
        type(proposal_scope) is not dict
        or proposal_scope != trust_scope
        or not scope_shape_ok
    ):
        problems.append("source_replay_scope_mismatch")
    expected_candidate = dict(CANDIDATE_PINS)
    expected_candidate["candidate_root"] = str(expected_candidate_root.resolve(strict=True))
    if policy_candidate != trust.get("candidate"):
        problems.append("policy_and_trust_candidate_pins_mismatch")
    if policy_candidate != proposal.get("candidate"):
        problems.append("proposal_candidate_pins_mismatch")
    if policy_candidate != expected_candidate:
        problems.append("candidate_pins_not_fixed_candidate")
    if trust.get("schema_version") != "personal-user-declared-source-time-trust.v1":
        problems.append("source_time_trust_schema_mismatch")
    if proposal.get("schema_version") != "personal-source-time-binding-proposal.v1":
        problems.append("source_time_proposal_schema_mismatch")
    if trust.get("confirmed_at") != policy.get("confirmed_at"):
        problems.append("source_time_confirmation_clock_mismatch")
    return problems


def _rollback_policy_mismatches(
    policy: Mapping[str, Any],
    *,
    target_revision: int,
    target_policy_sha256: str,
    target_candidate: Mapping[str, Any],
    target_source_time_trust: Mapping[str, Any],
) -> list[str]:
    """確認新 policy 明確回指所選歷史版，且只刷新其確認時間。"""

    problems: list[str] = []
    if policy.get("rollback_of_revision") != target_revision:
        problems.append("rollback_target_revision_mismatch")
    if policy.get("rollback_of_policy_sha256") != target_policy_sha256:
        problems.append("rollback_target_policy_hash_mismatch")
    if policy.get("candidate") != dict(target_candidate):
        problems.append("rollback_candidate_pins_mismatch")
    actual_trust = policy.get("source_time_trust")
    expected_trust = dict(target_source_time_trust)
    confirmed_at = policy.get("confirmed_at")
    if type(confirmed_at) is not str or not confirmed_at:
        problems.append("rollback_confirmation_clock_missing")
    else:
        expected_trust["confirmed_at"] = confirmed_at
    if actual_trust != expected_trust:
        problems.append("rollback_source_time_trust_mismatch")
    return problems


def _rollback_history_target_mismatches(
    target: Any,
    *,
    target_revision: int | None,
    target_policy_sha256: str | None,
    target_candidate: Mapping[str, Any] | None,
    target_source_time_trust: Mapping[str, Any] | None,
) -> list[str]:
    if (
        target_revision is None
        or target_policy_sha256 is None
        or target_candidate is None
        or target_source_time_trust is None
    ):
        return ["rollback_history_target_not_pinned"]
    problems: list[str] = []
    try:
        if target.revision != target_revision:
            problems.append("rollback_selected_revision_changed")
        if target.policy_sha256 != target_policy_sha256:
            problems.append("rollback_selected_policy_hash_changed")
        if target.candidate.to_dict() != dict(target_candidate):
            problems.append("rollback_selected_candidate_changed")
        if target.source_time_trust.to_dict() != dict(target_source_time_trust):
            problems.append("rollback_selected_source_trust_changed")
    except (AttributeError, TypeError):
        problems.append("rollback_selected_history_entry_invalid")
    return problems


def _rollback_candidate_selection_mismatches(
    *,
    selected_candidate_root: Any,
    selected_source_database_path: Any,
    expected_candidate_root: Path,
    expected_source_database_path: Path,
    source_check_enabled: bool,
) -> list[str]:
    """驗目前 UI 選項與明示來源，不依賴停用後可能已清除的 preview entry。"""

    problems: list[str] = []

    def canonical_existing_path(value: Any) -> Path | None:
        if not isinstance(value, (str, os.PathLike)):
            return None
        try:
            return isolated_launcher._assert_no_reparse_components(
                Path(value), allow_missing=False
            )
        except (OSError, isolated_launcher.IsolationError, TypeError, ValueError):
            return None

    selected_candidate = canonical_existing_path(selected_candidate_root)
    expected_candidate = canonical_existing_path(expected_candidate_root)
    if selected_candidate is None or expected_candidate is None:
        problems.append("candidate_root_missing_or_unsafe")
    elif not isolated_launcher._same_path(selected_candidate, expected_candidate):
        problems.append("candidate_root_mismatch")

    selected_database = canonical_existing_path(selected_source_database_path)
    expected_database = canonical_existing_path(expected_source_database_path)
    if selected_database is None or expected_database is None:
        problems.append("source_database_path_missing_or_unsafe")
    elif not isolated_launcher._same_path(selected_database, expected_database):
        problems.append("source_database_path_mismatch")

    if source_check_enabled is not True:
        problems.append("source_time_check_disabled")
    return problems


def _capture_failure_message(status_text: Any, result_id: str) -> str | None:
    if type(status_text) is not str:
        return None
    prefix = f"結果 {result_id} 已保存；個人模型擷取未完成。"
    if not status_text.startswith(prefix):
        return None
    return status_text[len(prefix) :].split("推薦結果不受影響", 1)[0].strip()


def _require_same_learning_tree_pin(
    expected: Mapping[str, Any], actual: Mapping[str, Any]
) -> None:
    if dict(expected) != dict(actual):
        raise AcceptanceError("唯讀 learning root 在 UI 旅程期間改變")


def _verify_prepared_workspace(run_id: str) -> tuple[Path, Any, dict[str, Any], dict[str, Any]]:
    run_root = _run_root(run_id)
    layout = _layout(run_root)
    verified_layout, manifest, verified = isolated_launcher._verify_prepared_workspace(
        run_root=run_root,
        policy_config_path=layout.policy_config_path,
        learning_output_root=LEARNING_OUTPUT_ROOT,
    )
    if verified_layout != layout:
        raise AcceptanceError("prepared manifest 與 runtime layout 不一致")
    if not isolated_launcher._same_path(
        Path(str(manifest.get("policy_config_path", ""))),
        layout.policy_config_path,
    ):
        raise AcceptanceError("policy path 必須是 run_root/app_config/personal_use_policy.json")
    if not isolated_launcher._same_path(
        Path(str(manifest.get("working_db_path", ""))), layout.working_db_path
    ):
        raise AcceptanceError("prepared workspace DB path 與固定 profile path 不一致")
    if manifest.get("profile") != "test":
        raise AcceptanceError("prepared workspace profile 不是 test")
    candidate_pin = _verify_candidate_bundle()
    if not isolated_launcher._is_within(
        Path(candidate_pin["candidate_root"]).resolve(strict=True),
        Path(str(verified["learning_root"])).resolve(strict=True),
    ):
        raise AcceptanceError("候選不在 prepare 時固定的唯讀 learning root")
    if verified["learning_pin"] != manifest.get("learning_root_read_only_pin"):
        raise AcceptanceError("learning root pin 與 prepared manifest 不一致")
    return run_root, verified_layout, manifest, {
        **verified,
        "candidate_pin": candidate_pin,
    }


def _runtime_config(run_root: Path, layout: Any, *, config: Any = None):
    from data_module.config import TWStockConfig

    if config is None:
        config = TWStockConfig(
            data_root=layout.data_root_base,
            output_root=layout.output_root_base,
            profile="test",
        )
    isolated_launcher._verify_test_profile_config(config, layout)
    actual_db = isolated_launcher._assert_no_reparse_components(
        Path(config.db_file), allow_missing=False
    )
    if not isolated_launcher._same_path(actual_db, layout.working_db_path.resolve(strict=True)):
        raise AcceptanceError("TWStockConfig.db_file 不是本次 isolated working DB")
    if not isolated_launcher._is_within(actual_db, run_root.resolve(strict=True)):
        raise AcceptanceError("TWStockConfig.db_file 離開 isolated run root")
    return config, actual_db


def _recompute_source_proposal(*, db_path: Path, layout: Any):
    from app_module.recommendation.personal_candidate_inventory import (
        inspect_personal_source_time_binding,
    )

    return inspect_personal_source_time_binding(
        candidate_root=str(CANDIDATE_ROOT),
        source_database_path=str(db_path),
        data_root=str(layout.data_root_actual),
        explicit_output_root=str(LEARNING_OUTPUT_ROOT),
    )


def _verify_saved_policy_source(
    *, run_root: Path, layout: Any, config: Any, db_path: Path
) -> dict[str, Any]:
    from app_module.recommendation.personal_use_policy import (
        RecommendationPersonalUsePolicyV2,
        load_personal_use_policy_snapshot,
    )

    policy_path = layout.policy_config_path
    policy = load_personal_use_policy_snapshot(policy_path)
    if type(policy) is not RecommendationPersonalUsePolicyV2:
        raise AcceptanceError("模型階段必須讀回 run-local V2 policy")
    if policy.mode != "personal_calibrated_probability":
        raise AcceptanceError("模型階段 policy 不是個人校準模式")
    if not isolated_launcher._same_path(policy.storage_path, policy_path.resolve(strict=True)):
        raise AcceptanceError("V2 policy storage path 不在隔離 app_config")
    policy.validate_snapshot()
    on_disk = load_personal_use_policy_snapshot(policy_path)
    if type(on_disk) is not RecommendationPersonalUsePolicyV2:
        raise AcceptanceError("V2 policy fresh readback 型別錯誤")
    if on_disk.storage_bytes != policy.storage_bytes or on_disk.to_dict() != policy.to_dict():
        raise AcceptanceError("V2 policy bytes 在讀回間改變")
    if config.profile != "test" or not isolated_launcher._same_path(
        Path(config.db_file).resolve(strict=True), db_path.resolve(strict=True)
    ):
        raise AcceptanceError("執行設定與 V2 source DB 不一致")
    db_stat = db_path.stat()
    actual_identity = {"device": int(db_stat.st_dev), "inode": int(db_stat.st_ino)}
    proposal = _recompute_source_proposal(db_path=db_path, layout=layout)
    proposal_mapping = _dto_mapping(proposal)
    policy_mapping = policy.to_dict()
    mismatches = _source_binding_mismatches(
        policy=policy_mapping,
        proposal=proposal_mapping,
        config_db_path=Path(config.db_file),
        expected_candidate_root=CANDIDATE_ROOT,
        actual_file_identity=actual_identity,
    )
    if mismatches:
        raise AcceptanceError("來源綁定重驗失敗：" + ",".join(mismatches))
    if proposal.candidate.to_dict() != CANDIDATE_PINS | {
        "candidate_root": str(CANDIDATE_ROOT.resolve(strict=True))
    }:
        raise AcceptanceError("最新 source replay proposal candidate pins 不符")
    return {
        "policy_revision": policy.revision,
        "policy_sha256": policy.policy_sha256,
        "policy_storage_sha256": _sha256_bytes(policy.storage_bytes or b""),
        "source_database_path": str(db_path.resolve(strict=True)),
        "source_file_identity": actual_identity,
        "source_database_size_bytes": db_stat.st_size,
        "source_slice_sha256": proposal.source_slice_sha256,
        "replay_scope": proposal.replay_scope.to_dict(),
        "basis": proposal.basis,
        "research_only": proposal.research_only,
        "official_historical_pit_verified": proposal.official_historical_pit_verified,
        "candidate_pins": proposal.candidate.to_dict(),
    }


def _verify_initial_proposal(*, proposal: Any, db_path: Path) -> dict[str, Any]:
    mapping = _dto_mapping(proposal)
    replay_scope = mapping.get("replay_scope")
    scope_is_fixed = (
        type(replay_scope) is dict
        and type(replay_scope.get("sample_count")) is int
        and replay_scope.get("sample_count") == 512
        and type(replay_scope.get("decision_dates")) in (list, tuple)
        and len(replay_scope["decision_dates"]) == 64
        and all(type(value) is str and value for value in replay_scope["decision_dates"])
        and type(replay_scope.get("symbols")) in (list, tuple)
        and len(replay_scope["symbols"]) == 8
        and all(type(value) is str and value for value in replay_scope["symbols"])
        and type(replay_scope.get("dataset_ids")) in (list, tuple)
        and bool(replay_scope["dataset_ids"])
        and all(type(value) is str and value for value in replay_scope["dataset_ids"])
    )
    info = db_path.stat()
    identity = {"device": int(info.st_dev), "inode": int(info.st_ino)}
    if (
        proposal.basis != "user_declared_source_time"
        or proposal.research_only is not True
        or proposal.official_historical_pit_verified is not False
        or proposal.candidate.candidate_id != CANDIDATE_ID
        or proposal.candidate.candidate_root
        != str(CANDIDATE_ROOT.resolve(strict=True))
        or Path(proposal.source_database_path).resolve(strict=True)
        != db_path.resolve(strict=True)
        or proposal.file_identity.to_dict() != identity
        or mapping.get("schema_version")
        != "personal-source-time-binding-proposal.v1"
        or mapping.get("source_slice_sha256") != EXPECTED_SOURCE_SLICE_SHA256
        or not scope_is_fixed
    ):
        raise AcceptanceError("新 UI source preview 不符合本 run source identity")
    return {
        "source_database_path": str(db_path.resolve(strict=True)),
        "file_identity": identity,
        "source_database_size_bytes": proposal.source_database_size_bytes,
        "source_slice_sha256": proposal.source_slice_sha256,
        "replay_scope": proposal.replay_scope.to_dict(),
        "basis": proposal.basis,
        "research_only": True,
        "official_historical_pit_verified": False,
        "candidate_pins": proposal.candidate.to_dict(),
        "proposal_sha256": _sha256_bytes(_canonical_json_bytes(mapping)),
    }


def _read_saved_state(path: Path) -> dict[str, Any]:
    return _read_json_regular(path, max_bytes=256 * 1024)


def _diagnostic_scalar(value: Any, *, max_chars: int = 240) -> Any:
    """Keep failure evidence compact and JSON-safe; never serialize whole objects."""

    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return value[:max_chars]
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())[:max_chars]
        except (TypeError, ValueError):
            pass
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, bool)):
        return _diagnostic_scalar(enum_value, max_chars=max_chars)
    return type(value).__name__


def _aware_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _bounded_json_object(value: Any, *, max_bytes: int = 256 * 1024) -> Mapping[str, Any]:
    if not isinstance(value, str) or len(value.encode("utf-8", errors="replace")) > max_bytes:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _sealed_ml_projection_diagnostic(execution: Any) -> dict[str, Any]:
    """Extract bounded receipt-failure facts from the sealed execution only."""

    events_value = getattr(execution, "events", ())
    events = events_value if isinstance(events_value, (tuple, list)) else ()
    receipt_events: list[dict[str, Any]] = []
    matching_event_count = 0
    scanned_event_count = 0
    for event in events:
        scanned_event_count += 1
        if scanned_event_count > 512:
            break
        if getattr(event, "event_type", None) != "ml_projection_receipt_capture":
            continue
        matching_event_count += 1
        if len(receipt_events) >= 3:
            continue
        raw_details = getattr(event, "details", None)
        details = raw_details if isinstance(raw_details, Mapping) else {}
        raw_codes = details.get("projected_stock_codes")
        receipt_events.append(
            {
                "event_type": "ml_projection_receipt_capture",
                "attempted": details.get("attempted")
                if type(details.get("attempted")) is bool
                else None,
                "persisted": details.get("persisted")
                if type(details.get("persisted")) is bool
                else None,
                "readback_verified": details.get("readback_verified")
                if type(details.get("readback_verified")) is bool
                else None,
                "identity_verified": details.get("identity_verified")
                if type(details.get("identity_verified")) is bool
                else None,
                "error": (
                    details.get("error")[:300]
                    if isinstance(details.get("error"), str)
                    else None
                ),
                "projected_stock_code_count": (
                    len(raw_codes)
                    if isinstance(raw_codes, (tuple, list))
                    and len(raw_codes) <= 1000
                    else None
                ),
                "projection_rows_sha256_present": bool(
                    isinstance(details.get("projection_rows_sha256"), str)
                    and details.get("projection_rows_sha256")
                ),
                "cost_scenario_hash_present": bool(
                    isinstance(details.get("cost_scenario_hash"), str)
                    and details.get("cost_scenario_hash")
                ),
            }
        )

    items_value = getattr(execution, "items", ())
    items = items_value if isinstance(items_value, (tuple, list)) else ()
    status_counts: dict[str, int] = {}
    compatibility_status_counts: dict[str, int] = {}
    cost_hash_presence_counts = {"present": 0, "missing": 0}
    rows_with_any_projection_metadata = 0
    distinct_cost_hashes: set[str] = set()
    for item in items[:1000]:
        row_has_projection_metadata = False
        try:
            status_value = getattr(item, "calibrated_probability_status", None)
        except Exception:
            status_value = None
        provenance = getattr(item, "calibration_provenance", None)
        provenance = provenance if isinstance(provenance, Mapping) else {}
        if status_value is None:
            status_value = provenance.get("calibrated_probability_status")
        if isinstance(status_value, str) and status_value:
            status_counts[status_value[:80]] = status_counts.get(status_value[:80], 0) + 1
            row_has_projection_metadata = True

        compatibility = getattr(item, "provenance_compatibility", None)
        if not isinstance(compatibility, Mapping):
            compatibility = provenance.get("provenance_compatibility")
        compatibility = compatibility if isinstance(compatibility, Mapping) else {}
        compatibility_status = compatibility.get("status")
        if isinstance(compatibility_status, str) and compatibility_status:
            key = compatibility_status[:80]
            compatibility_status_counts[key] = (
                compatibility_status_counts.get(key, 0) + 1
            )
            row_has_projection_metadata = True

        cost_hash = getattr(item, "cost_scenario_hash", None)
        if not isinstance(cost_hash, str) or not cost_hash:
            cost_hash = provenance.get("cost_scenario_hash")
        if isinstance(cost_hash, str) and cost_hash:
            cost_hash_presence_counts["present"] += 1
            distinct_cost_hashes.add(cost_hash)
            row_has_projection_metadata = True
        else:
            cost_hash_presence_counts["missing"] += 1
        rows_with_any_projection_metadata += int(row_has_projection_metadata)

    return {
        "evidence_scope": "sealed_execution_events_and_items_only",
        "receipt_event_type": "ml_projection_receipt_capture",
        "receipt_event_count": matching_event_count,
        "events_truncated": scanned_event_count > 512 or matching_event_count > 3,
        "receipt_events": receipt_events,
        "sealed_item_count": len(items),
        "items_with_projection_metadata": min(rows_with_any_projection_metadata, 1000),
        "row_status_counts": dict(sorted(status_counts.items())[:12]),
        "compatibility_status_counts": dict(
            sorted(compatibility_status_counts.items())[:12]
        ),
        "cost_hash_presence_counts": cost_hash_presence_counts,
        "distinct_cost_hash_count": min(len(distinct_cost_hashes), 1000),
        "row_projection_metadata_available": rows_with_any_projection_metadata > 0,
    }


def _active_execution_failure_diagnostic(
    *,
    view: Any,
    execution: Any,
    event: Any,
    expected_policy: Mapping[str, Any],
    predicate_matches: Mapping[str, bool],
) -> dict[str, Any]:
    """Capture bounded facts from the sealed invocation and label live UI separately."""

    context = getattr(execution, "context", None)
    request = getattr(execution, "request", None)
    execution_decision_at = getattr(context, "decision_at", None)
    execution_as_of_date = getattr(context, "as_of_date", None)
    request_config_snapshot = getattr(request, "config_snapshot", None)
    raw_request_config = getattr(request_config_snapshot, "raw_config_json", None)
    request_config = _bounded_json_object(raw_request_config)
    context_warnings = getattr(context, "warnings", ())
    if not isinstance(context_warnings, (tuple, list)):
        context_warnings = ()

    # execute() may use a per-invocation service copy. This view-owned service context
    # is retained only as a clearly labelled non-authoritative observation.
    service = getattr(view, "recommendation_service", None)
    raw_base_context = getattr(service, "last_run_context", None)
    base_service_context = raw_base_context if isinstance(raw_base_context, Mapping) else {}
    items = tuple(getattr(execution, "items", ()) or ())
    status_counts: dict[str, int] = {}
    active_count = 0
    for item in items:
        raw_status = getattr(item, "calibrated_probability_status", None)
        status = str(_diagnostic_scalar(raw_status, max_chars=80) or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "active_effective":
            active_count += 1

    expected_confirmed_at = expected_policy.get("confirmed_at")
    actual_decision_utc = _aware_utc(execution_decision_at)
    confirmed_utc = _aware_utc(expected_confirmed_at)
    if actual_decision_utc is None or confirmed_utc is None:
        policy_clock_valid: bool | None = None
    else:
        policy_clock_valid = confirmed_utc <= actual_decision_utc

    event_mapping = event if isinstance(event, Mapping) else {}
    actual_snapshot = event_mapping.get("policy_snapshot")
    expected_snapshot_keys = set(expected_policy)
    actual_snapshot_keys = (
        set(actual_snapshot) if isinstance(actual_snapshot, Mapping) else set()
    )
    snapshot_mismatch_keys = sorted(
        key
        for key in expected_snapshot_keys | actual_snapshot_keys
        if not isinstance(actual_snapshot, Mapping)
        or actual_snapshot.get(key) != expected_policy.get(key)
    )[:24]

    request_filters = request_config.get("filters")
    request_filter_summary: dict[str, Any] = {}
    if isinstance(request_filters, Mapping):
        for key in (
            "price_change_min",
            "price_change_max",
            "volume_ratio_min",
            "rsi_min",
            "rsi_max",
        ):
            if key in request_filters:
                request_filter_summary[key] = _diagnostic_scalar(request_filters[key])

    live_config = getattr(view, "current_config", None)
    raw_live_filters = (
        live_config.get("filters")
        if isinstance(live_config, Mapping)
        else getattr(live_config, "filters", None)
    )
    live_filter_summary: dict[str, Any] = {}
    if isinstance(raw_live_filters, Mapping):
        for key in (
            "price_change_min",
            "price_change_max",
            "volume_ratio_min",
            "rsi_min",
            "rsi_max",
        ):
            if key in raw_live_filters:
                live_filter_summary[key] = _diagnostic_scalar(raw_live_filters[key])

    def _label_text(name: str) -> str | None:
        label = getattr(view, name, None)
        getter = getattr(label, "text", None)
        if not callable(getter):
            return None
        try:
            return str(getter())[:320]
        except RuntimeError:
            return "<deleted-widget>"

    normalized_warnings = [
        str(_diagnostic_scalar(warning, max_chars=160))
        for warning in context_warnings[:12]
    ]
    profile_combo = getattr(view, "profile_combo", None)
    profile_current_data = getattr(profile_combo, "currentData", None)
    profile_current_text = getattr(profile_combo, "currentText", None)
    signal_widget_names = (
        "ma_check",
        "adx_check",
        "macd_check",
        "rsi_check",
        "kd_check",
        "bollinger_check",
        "atr_check",
        "pattern_w_bottom",
        "pattern_head_shoulder_bottom",
        "pattern_double_bottom",
        "pattern_v_reversal",
        "pattern_rounding_bottom",
        "pattern_flag",
        "pattern_wedge",
        "pattern_rectangle",
        "pattern_triangle",
        "pattern_head_shoulder_top",
        "pattern_double_top",
        "pattern_rounding_top",
    )
    selected_signals: dict[str, bool] = {}
    for name in signal_widget_names:
        widget = getattr(view, name, None)
        is_checked = getattr(widget, "isChecked", None)
        if callable(is_checked):
            try:
                selected_signals[name] = bool(is_checked())
            except RuntimeError:
                selected_signals[name] = False

    config_signals = request_config.get("signals")
    config_signal_summary: dict[str, Any] = {}
    if isinstance(config_signals, Mapping):
        for key, value in list(config_signals.items())[:24]:
            if isinstance(value, Mapping):
                config_signal_summary[str(key)[:80]] = {
                    str(nested_key)[:80]: _diagnostic_scalar(nested_value)
                    for nested_key, nested_value in list(value.items())[:6]
                    if isinstance(nested_value, (str, int, float, bool))
                    or nested_value is None
                }
            elif isinstance(value, (str, int, float, bool)) or value is None:
                config_signal_summary[str(key)[:80]] = _diagnostic_scalar(value)

    universe_identity = getattr(context, "universe_identity", None)
    snapshot_identity = getattr(universe_identity, "snapshot", None)
    raw_universe_spec = getattr(snapshot_identity, "universe_snapshot_spec_json", None)
    universe_spec = _bounded_json_object(raw_universe_spec)
    selected_count = universe_spec.get("selected_count")
    selected_codes = universe_spec.get("selected_codes")
    if type(selected_count) is not int or selected_count < 0:
        selected_count = (
            len(selected_codes) if isinstance(selected_codes, (tuple, list)) else None
        )
    selection_mode = universe_spec.get("selection_mode")
    request_profile_ref = getattr(request, "profile_ref", None)
    request_profile_id = getattr(request_profile_ref, "reference_id", None)
    request_date = None
    for key in ("data_date", "decision_date", "as_of_date"):
        if key in request_config:
            request_date = request_config[key]
            break
    fallback_row_count = sum(
        count
        for status, count in status_counts.items()
        if "fallback" in status.casefold() or "rule_only" in status.casefold()
    )
    if not items:
        projection_from_items = "no_delivered_rows"
    elif active_count and fallback_row_count:
        projection_from_items = "mixed_active_and_fallback"
    elif active_count == len(items):
        projection_from_items = "active_only"
    elif fallback_row_count == len(items):
        projection_from_items = "fallback_or_rule_only"
    else:
        projection_from_items = "other_nonactive_statuses"
    try:
        profile_data_value = profile_current_data() if callable(profile_current_data) else None
        profile_text_value = profile_current_text() if callable(profile_current_text) else None
    except RuntimeError:
        profile_data_value = None
        profile_text_value = "<deleted-widget>"

    return {
        "schema_version": "native-personal-model-execution-failure-diagnostic.v2",
        "evidence_source": "sealed RecommendationExecution.context/request/items plus canonical event",
        "event_predicates": {
            "requested_mode_matches_personal_calibrated": predicate_matches.get(
                "requested_mode", False
            ),
            "effective_mode_matches_personal_calibrated": predicate_matches.get(
                "effective_mode", False
            ),
            "policy_snapshot_matches_saved_v2": predicate_matches.get(
                "policy_snapshot", False
            ),
            "policy_snapshot_mismatch_keys": snapshot_mismatch_keys,
            "actual_requested_mode": _diagnostic_scalar(event_mapping.get("requested_mode")),
            "actual_effective_mode": _diagnostic_scalar(event_mapping.get("effective_mode")),
        },
        "execution": {
            "result_id": _diagnostic_scalar(getattr(execution, "result_id", None)),
            "status": _diagnostic_scalar(
                getattr(getattr(execution, "status", None), "value", None)
            ),
            "decision_at": _diagnostic_scalar(execution_decision_at),
            "as_of_date": _diagnostic_scalar(execution_as_of_date),
            "request_as_of_date": _diagnostic_scalar(getattr(request, "as_of_date", None)),
            "request_config_data_or_decision_date": _diagnostic_scalar(request_date),
            "request_profile_reference_id": _diagnostic_scalar(request_profile_id),
            "request_max_stocks": _diagnostic_scalar(getattr(request, "max_stocks", None)),
            "request_top_n": _diagnostic_scalar(getattr(request, "top_n", None)),
            "delivered_row_count": len(items),
            "selected_universe_count": selected_count,
            "selection_mode": _diagnostic_scalar(selection_mode),
            "calibration_status_counts": dict(sorted(status_counts.items())[:12]),
            "projection_status_from_sealed_items": projection_from_items,
            "active_candidate_row_count": active_count,
            "fallback_or_rule_row_count": fallback_row_count,
            "ml_projection_receipt_diagnostic": _sealed_ml_projection_diagnostic(
                execution
            ),
        },
        "policy_clock": {
            "confirmed_at": _diagnostic_scalar(expected_confirmed_at),
            "decision_at": _diagnostic_scalar(execution_decision_at),
            "confirmed_at_not_after_decision_at": policy_clock_valid,
        },
        "base_service_context_observation": {
            "evidence_scope": "base_service_only_not_invocation_evidence",
            "context_present": bool(base_service_context),
            **{
                key: _diagnostic_scalar(base_service_context.get(key))
                for key in (
                    "result_id",
                    "decision_at",
                    "decision_date",
                    "as_of_date",
                    "data_date",
                    "personal_use_requested_mode",
                    "personal_use_effective_mode",
                    "calibration_projection_status",
                )
                if key in base_service_context
            },
        },
        "sealed_invocation_warnings": normalized_warnings,
        "sealed_request_config": {
            "snapshot_present": request_config_snapshot is not None,
            "snapshot_sha256": _diagnostic_scalar(
                getattr(request_config_snapshot, "raw_json_sha256", None)
            ),
            "filters": request_filter_summary,
            "signals": config_signal_summary,
        },
        "ui": {
            "execution_state": _diagnostic_scalar(getattr(view, "_execution_state", None)),
            "execution_status_label": _label_text("execution_status_label"),
            "result_status_label": _label_text("result_status_label"),
            "is_beginner_mode": _diagnostic_scalar(getattr(view, "is_beginner_mode", None)),
            "current_profile": _diagnostic_scalar(getattr(view, "current_profile", None)),
            "profile_combo_current_data": _diagnostic_scalar(profile_data_value),
            "profile_combo_current_text": _diagnostic_scalar(profile_text_value),
            "selected_universe_count_from_sealed_context": selected_count,
            "current_config_data_date": _diagnostic_scalar(
                getattr(live_config, "data_date", None)
                if not isinstance(live_config, Mapping)
                else live_config.get("data_date")
            ),
            "current_config_filters_live_ui_only": live_filter_summary,
            "selected_signal_widgets_live_ui_only": selected_signals,
        },
    }


def _require_projection_identity(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _verified_projection_rows(
    *,
    execution: Any,
    receipt_event: Mapping[str, Any],
    expected_policy: Mapping[str, Any],
    expected_source_proof: Mapping[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    """從封存 event 指向的 bounded canonical receipt 核對真實模型列。"""

    from ml_module.recommendation_inference_provenance import (
        read_inference_projection_receipt,
    )

    for flag in ("attempted", "persisted", "readback_verified", "identity_verified"):
        _require_projection_identity(
            receipt_event.get(flag) is True,
            f"sealed ML projection receipt event {flag} 未確認",
        )
    _require_projection_identity(
        receipt_event.get("receipt_body_hash_verified") is True,
        "sealed ML projection receipt body hash 未確認",
    )

    result_id = str(getattr(execution, "result_id", "") or "")
    context = getattr(execution, "context", None)
    decision_at = getattr(context, "decision_at", None)
    decision_date_value = getattr(context, "as_of_date", None)
    decision_date = str(
        decision_date_value.isoformat()
        if callable(getattr(decision_date_value, "isoformat", None))
        else decision_date_value or ""
    )
    _require_projection_identity(bool(result_id), "sealed execution 缺 result id")
    _require_projection_identity(
        _aware_utc(decision_at) is not None,
        "sealed execution decision_at 不是 aware clock",
    )

    event_result_id = receipt_event.get("result_id")
    event_decision_date = receipt_event.get("decision_date")
    candidate_id = receipt_event.get("candidate_id")
    receipt_hash = receipt_event.get("receipt_hash")
    cost_scenario_hash = receipt_event.get("cost_scenario_hash")
    event_path = receipt_event.get("path")
    for name, value in (
        ("result id", event_result_id),
        ("decision date", event_decision_date),
        ("candidate id", candidate_id),
        ("receipt hash", receipt_hash),
        ("cost scenario hash", cost_scenario_hash),
        ("cost scenario id", receipt_event.get("cost_scenario_id")),
        ("receipt path", event_path),
    ):
        _require_projection_identity(
            isinstance(value, str) and bool(value.strip()),
            f"sealed ML projection receipt event 缺 {name}",
        )
    _require_projection_identity(event_result_id == result_id, "ML receipt result id 不符")
    _require_projection_identity(
        event_decision_date == decision_date,
        "ML receipt decision date 與 sealed execution 不符",
    )
    _require_projection_identity(candidate_id == CANDIDATE_ID, "ML receipt candidate id 不符")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(receipt_hash)):
        raise AcceptanceError("ML receipt hash 格式無效")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(cost_scenario_hash)):
        raise AcceptanceError("ML receipt cost scenario hash 格式無效")

    run_root = run_root.resolve(strict=True)
    expected_path = (
        run_root
        / "app_config"
        / "inference_projection"
        / str(event_decision_date)
        / CANDIDATE_ID
        / f"{str(receipt_hash).split(':', 1)[1]}.json"
    )
    raw_event_path = Path(str(event_path)).expanduser()
    if not raw_event_path.is_absolute() or any(
        part in {".", ".."} for part in raw_event_path.parts[1:]
    ):
        raise AcceptanceError("ML projection receipt path 不是正規絕對路徑")
    normalized_event_path = Path(os.path.abspath(raw_event_path))
    if os.path.normcase(os.path.normpath(str(normalized_event_path))) != os.path.normcase(
        os.path.normpath(str(expected_path))
    ):
        raise AcceptanceError("ML projection receipt path 不在本 run-local policy root")

    try:
        verified_receipt = read_inference_projection_receipt(
            normalized_event_path,
            expected_receipt_hash=str(receipt_hash),
            expected_decision_date=str(event_decision_date),
            expected_candidate_id=CANDIDATE_ID,
            expected_result_id=result_id,
            expected_cost_scenario_hash=str(cost_scenario_hash),
            max_receipt_bytes=MAX_PROJECTION_RECEIPT_BYTES,
        )
    except Exception as exc:
        raise AcceptanceError(
            "ML projection receipt bounded canonical readback rejected: "
            f"{type(exc).__name__}: {str(exc)[:240]}"
        ) from exc

    _require_projection_identity(
        verified_receipt.receipt_hash == receipt_hash,
        "ML receipt canonical readback hash 與 sealed event 不符",
    )
    actual_readback_path = Path(str(verified_receipt.receipt_path or ""))
    _require_projection_identity(
        actual_readback_path.is_absolute()
        and os.path.normcase(os.path.normpath(str(actual_readback_path)))
        == os.path.normcase(os.path.normpath(str(expected_path))),
        "ML receipt readback path 與 run-local event path 不符",
    )
    payload = verified_receipt.payload
    candidate_identity = payload.get("candidate_identity")
    inference = payload.get("inference_provenance")
    training = payload.get("training_provenance")
    compatibility = payload.get("provenance_compatibility")
    rows = payload.get("projections")
    _require_projection_identity(
        isinstance(candidate_identity, Mapping)
        and isinstance(inference, Mapping)
        and isinstance(training, Mapping)
        and isinstance(compatibility, Mapping)
        and isinstance(rows, list)
        and bool(rows),
        "ML receipt canonical payload 缺 candidate/source/projection rows",
    )

    _require_projection_identity(
        payload.get("result_id") == result_id
        and payload.get("decision_date") == event_decision_date
        and candidate_identity.get("candidate_id") == CANDIDATE_ID,
        "ML receipt payload result/date/candidate identity 不符",
    )
    event_candidate_identity = receipt_event.get("candidate_identity")
    _require_projection_identity(
        isinstance(event_candidate_identity, Mapping)
        and _canonical_identity_value(event_candidate_identity)
        == _canonical_identity_value(candidate_identity),
        "ML receipt candidate identity 與 sealed event 不符",
    )
    _require_projection_identity(
        payload.get("projection_rows_sha256")
        == receipt_event.get("projection_rows_sha256"),
        "ML receipt projection rows hash 與 sealed event 不符",
    )
    event_codes = receipt_event.get("projected_stock_codes")
    _require_projection_identity(
        isinstance(event_codes, (tuple, list))
        and all(type(code) is str and code for code in event_codes),
        "sealed ML receipt event stock-code identity 無效",
    )
    receipt_codes = [str(row.get("stock_code") or "") for row in rows if isinstance(row, Mapping)]
    _require_projection_identity(
        len(receipt_codes) == len(rows)
        and all(receipt_codes)
        and len(receipt_codes) == len(set(receipt_codes))
        and tuple(event_codes) == tuple(receipt_codes),
        "ML receipt stock codes 與 sealed event 不完全相符",
    )
    item_codes = [
        str(getattr(item, "stock_code", "") or "")
        for item in tuple(getattr(execution, "items", ()) or ())
    ]
    _require_projection_identity(
        len(item_codes) == len(receipt_codes)
        and all(item_codes)
        and len(item_codes) == len(set(item_codes))
        and set(item_codes) == set(receipt_codes),
        "ML receipt stock codes 與 sealed delivered items 不完全相符",
    )

    source_path = expected_source_proof.get("source_database_path")
    source_slice_hash = expected_source_proof.get("source_slice_sha256")
    source_identity = expected_source_proof.get("source_file_identity")
    source_candidate_pins = expected_source_proof.get("candidate_pins")
    policy_candidate = expected_policy.get("candidate")
    source_trust = expected_policy.get("source_time_trust")
    _require_projection_identity(
        isinstance(source_path, str)
        and bool(source_path)
        and SOURCE_SLICE_PATTERN.fullmatch(str(source_slice_hash or "")) is not None
        and isinstance(source_identity, Mapping)
        and isinstance(source_candidate_pins, Mapping)
        and isinstance(policy_candidate, Mapping)
        and isinstance(source_trust, Mapping),
        "執行前 V2 source proof 欄位不完整",
    )
    expected_candidate_pins = {
        **CANDIDATE_PINS,
        "candidate_root": str(CANDIDATE_ROOT.resolve(strict=True)),
    }
    _require_projection_identity(
        dict(source_candidate_pins) == expected_candidate_pins
        and dict(policy_candidate) == expected_candidate_pins,
        "V2 policy/source proof candidate pins 不等於固定候選",
    )
    _require_projection_identity(
        source_trust.get("basis") == "user_declared_source_time"
        and source_trust.get("research_only") is True
        and source_trust.get("official_historical_pit_verified") is False
        and source_trust.get("source_database_path") == source_path
        and source_trust.get("source_slice_sha256") == source_slice_hash
        and source_trust.get("file_identity") == dict(source_identity)
        and dict(source_trust.get("candidate") or {}) == expected_candidate_pins,
        "V2 policy source trust 與執行前 fresh source proof 不一致",
    )
    _require_projection_identity(
        candidate_identity.get("candidate_root")
        == str(CANDIDATE_ROOT.resolve(strict=True))
        and candidate_identity.get("candidate_manifest_hash")
        == CANDIDATE_PINS["candidate_manifest_hash"]
        and candidate_identity.get("candidate_artifact_hash")
        == CANDIDATE_PINS["candidate_artifact_hash"]
        and candidate_identity.get("candidate_freeze_hash")
        == CANDIDATE_PINS["candidate_freeze_hash"]
        and candidate_identity.get("dataset_hash") == CANDIDATE_PINS["dataset_hash"],
        "ML receipt candidate identity 與固定 candidate pins 不一致",
    )

    expected_source_path = str(Path(source_path).resolve(strict=True))
    _require_projection_identity(
        inference.get("status") == "verified"
        and inference.get("decision_date") == decision_date
        and inference.get("source_database") == expected_source_path
        and inference.get("cost_scenario_hash") == cost_scenario_hash
        and training.get("status") == "verified"
        and compatibility.get("status") == "verified",
        "ML receipt verified source/training compatibility 與本次 V2 proof 不符",
    )
    _require_projection_identity(
        payload.get("cost_scenario_hash") == cost_scenario_hash
        and training.get("cost_scenario_hash") == cost_scenario_hash
        and inference.get("cost_scenario_hash") == cost_scenario_hash
        and receipt_event.get("cost_scenario_id") == inference.get("cost_scenario_id")
        and receipt_event.get("inference_source_hash")
        == inference.get("inference_source_hash")
        and receipt_event.get("inference_pit_hash") == inference.get("inference_pit_hash")
        and receipt_event.get("feature_rows_sha256")
        == inference.get("feature_rows_sha256"),
        "ML receipt source/cost identity 與 sealed event 不一致",
    )

    lineage = candidate_identity.get("probability_lineage")
    _require_projection_identity(
        isinstance(lineage, list), "ML receipt 缺 candidate probability lineage"
    )
    active_lineage = [
        item
        for item in lineage
        if isinstance(item, Mapping)
        and item.get("kind") == "active_model"
        and item.get("candidate_id") == CANDIDATE_ID
    ]
    _require_projection_identity(
        len(active_lineage) == 1,
        "ML receipt active candidate probability lineage 不唯一",
    )
    model_lineage = active_lineage[0]
    _require_projection_identity(
        model_lineage.get("cost_scenario_hash") == cost_scenario_hash
        and model_lineage.get("model_id") == CANDIDATE_ID
        and bool(model_lineage.get("baseline_id"))
        and bool(model_lineage.get("baseline_kind")),
        "ML receipt active model lineage cost/baseline identity 不符",
    )

    active_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise AcceptanceError("ML receipt projection row 不是 object")
        row_inference = row.get("inference_provenance")
        _require_projection_identity(
            isinstance(row_inference, Mapping)
            and dict(row_inference) == dict(inference)
            and row.get("cost_scenario_hash") == cost_scenario_hash
            and row.get("cost_scenario_id") == inference.get("cost_scenario_id"),
            "ML receipt row inference identity 與同次 top-level source 不符",
        )
        if row.get("calibrated_probability_status") != "active_effective":
            continue
        row_training = row.get("training_provenance")
        _require_projection_identity(
            isinstance(row_training, Mapping)
            and row_training.get("status") == "verified"
            and row_training.get("source_time_basis") == source_trust.get("basis")
            and row_training.get("source_time_confirmed_at")
            == source_trust.get("confirmed_at")
            and row_training.get("source_time_source_database_path") == expected_source_path
            and row_training.get("source_time_slice_sha256") == source_slice_hash
            and row_training.get("source_time_research_only") is True
            and row_training.get("official_historical_pit_verified") is False,
            "ML receipt active row V2 source-time trust 與本次 fresh proof 不符",
        )
        probability = row.get("calibrated_probability_bp")
        if (
            row.get("status") != "active_candidate"
            or row.get("model_version") != CANDIDATE_ID
            or type(probability) is not int
            or not 0 <= probability <= 10_000
            or row.get("cost_scenario_hash") != cost_scenario_hash
            or row.get("cost_scenario_id") != inference.get("cost_scenario_id")
            or row.get("probability_baseline_id") != model_lineage.get("baseline_id")
            or row.get("probability_baseline_kind") != model_lineage.get("baseline_kind")
            or row.get("probability_transform_id") != model_lineage.get("transform_id")
            or row.get("provenance_status") != "verified"
        ):
            raise AcceptanceError("ML receipt active row candidate/cost/baseline/bp identity 無效")
        active_rows.append(
            {
                "symbol": str(row.get("stock_code") or ""),
                "probability_bp": probability,
                "model_version": CANDIDATE_ID,
                "baseline_id": str(row.get("probability_baseline_id") or ""),
                "baseline_kind": str(row.get("probability_baseline_kind") or ""),
                "cost_scenario_hash": str(cost_scenario_hash),
            }
        )
    active_symbols = [row["symbol"] for row in active_rows]
    _require_projection_identity(
        bool(active_rows)
        and all(active_symbols)
        and len(active_symbols) == len(set(active_symbols)),
        "canonical ML projection receipt 沒有 active candidate probability row",
    )
    return {
        "receipt_path": str(expected_path),
        "receipt_hash": str(receipt_hash),
        "receipt_size_bytes_bounded_by": MAX_PROJECTION_RECEIPT_BYTES,
        "projection_rows_sha256": str(payload.get("projection_rows_sha256") or ""),
        "result_id": result_id,
        "decision_date": decision_date,
        "candidate_id": CANDIDATE_ID,
        "source_database_path": expected_source_path,
        "source_file_identity": dict(source_identity),
        "source_slice_sha256": str(source_slice_hash),
        "cost_scenario_hash": str(cost_scenario_hash),
        "delivered_symbols": sorted(receipt_codes),
        "delivered_row_count": len(receipt_codes),
        "active_probability_rows": active_rows,
    }


def _verify_active_execution(
    view: Any,
    expected_policy: Mapping[str, Any],
    *,
    run_root: Path | None = None,
    expected_source_proof: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from app_module.personalization_contract import read_personal_use_policy_snapshot_event

    execution = getattr(view, "current_execution", None)
    if execution is None or getattr(getattr(execution, "status", None), "value", None) != "completed":
        raise AcceptanceError("真 UI 推薦沒有 completed sealed execution")
    event = read_personal_use_policy_snapshot_event(
        execution, expected_result_id=str(execution.result_id)
    )
    event_mapping = event if isinstance(event, Mapping) else {}
    predicate_matches = {
        "requested_mode": (
            event_mapping.get("requested_mode")
            == "personal_calibrated_probability"
        ),
        "effective_mode": (
            event_mapping.get("effective_mode")
            == "personal_calibrated_probability"
        ),
        "policy_snapshot": event_mapping.get("policy_snapshot") == expected_policy,
    }
    failed_predicates = [name for name, matches in predicate_matches.items() if not matches]
    if failed_predicates:
        diagnostic = _active_execution_failure_diagnostic(
            view=view,
            execution=execution,
            event=event_mapping,
            expected_policy=expected_policy,
            predicate_matches=predicate_matches,
        )
        raise AcceptanceError(
            "canonical execution event 驗收失敗："
            + ",".join(failed_predicates),
            diagnostic=diagnostic,
        )
    if run_root is None or expected_source_proof is None:
        raise AcceptanceError("驗收 active model 必須綁本 run path 與 fresh source proof")
    receipt_events = [
        item
        for item in tuple(getattr(execution, "events", ()) or ())
        if getattr(item, "event_type", None) == "ml_projection_receipt_capture"
    ]
    if len(receipt_events) != 1:
        raise AcceptanceError("sealed execution 必須恰有一個 ML projection receipt event")
    receipt_details = getattr(receipt_events[0], "details", None)
    if not isinstance(receipt_details, Mapping):
        raise AcceptanceError("sealed ML projection receipt event details 無效")
    try:
        projection = _verified_projection_rows(
            execution=execution,
            receipt_event=receipt_details,
            expected_policy=expected_policy,
            expected_source_proof=expected_source_proof,
            run_root=run_root,
        )
    except AcceptanceError as exc:
        diagnostic = _active_execution_failure_diagnostic(
            view=view,
            execution=execution,
            event=event_mapping,
            expected_policy=expected_policy,
            predicate_matches=predicate_matches,
        )
        diagnostic["projection_receipt_rejection"] = str(exc)[:320]
        raise AcceptanceError(str(exc), diagnostic=diagnostic) from exc
    return {
        "result_id": str(execution.result_id),
        "decision_at": execution.context.decision_at.isoformat(),
        "requested_mode": event["requested_mode"],
        "effective_mode": event["effective_mode"],
        "policy_revision": expected_policy["revision"],
        "policy_sha256": expected_policy["policy_sha256"],
        "active_probability_rows": projection["active_probability_rows"],
        "delivered_row_count": len(tuple(execution.items)),
        "projection_receipt": projection,
    }


def _visible_probability_projection(
    view: Any,
    execution: Any,
    verified_projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the actual Qt table projection after canonical save readback."""

    table_model = getattr(view, "recommendations_model", None)
    if table_model is None or view.results_table.model() is not table_model:
        raise AcceptanceError("Qt 推薦表格沒有使用本次 recommendation model")
    frame = table_model.getDataFrame()
    required = {
        "證券代號",
        "calibrated_probability_bp",
        "calibrated_probability_status",
        "calibration_model_version",
        "calibration_probability_baseline_id",
        "calibration_probability_baseline_kind",
    }
    if not required.issubset(set(frame.columns)):
        raise AcceptanceError("Qt 推薦表格缺少模型機率／身份欄位")
    if str(verified_projection.get("result_id") or "") != str(
        getattr(execution, "result_id", "") or ""
    ):
        raise AcceptanceError("canonical save execution 與 verified ML receipt result id 不符")
    receipt_active_rows = verified_projection.get("active_probability_rows")
    if not isinstance(receipt_active_rows, list):
        raise AcceptanceError("verified ML receipt 缺 active row projection")
    expected_by_symbol: dict[str, dict[str, Any]] = {}
    for row in receipt_active_rows:
        if not isinstance(row, Mapping):
            raise AcceptanceError("verified ML receipt active row shape 無效")
        symbol = str(row.get("symbol") or "").strip()
        if not symbol or symbol in expected_by_symbol:
            raise AcceptanceError("verified ML receipt active rows 缺少唯一股票身份")
        receipt_probability = row.get("probability_bp")
        if (
            type(receipt_probability) is not int
            or not 0 <= receipt_probability <= 10_000
        ):
            raise AcceptanceError("verified ML receipt basis-point value is invalid")
        expected_by_symbol[symbol] = {
            "calibrated_probability_bp": receipt_probability,
            "calibration_model_version": row.get("model_version"),
            "calibration_probability_baseline_id": row.get("baseline_id"),
            "calibration_probability_baseline_kind": row.get("baseline_kind"),
        }
    actual_by_symbol: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        symbol = str(row.get("證券代號", "")).strip()
        is_active = row.get("calibrated_probability_status") == "active_effective"
        if not symbol:
            if is_active:
                raise AcceptanceError("Qt 表格 active model row 缺少股票身份")
            continue
        if is_active:
            if symbol in actual_by_symbol:
                raise AcceptanceError("Qt 表格出現重複 active model 股票列")
            probability = row.get("calibrated_probability_bp")
            if isinstance(probability, bool) or not isinstance(probability, Integral):
                raise AcceptanceError("Qt 表格 active probability 不是整數基點")
            probability = int(probability)
            if not 0 <= probability <= 10_000:
                raise AcceptanceError("Qt 表格 active probability 超出整數基點範圍")
            actual_by_symbol[symbol] = {
                "calibrated_probability_bp": probability,
                "calibration_model_version": row.get("calibration_model_version"),
                "calibration_probability_baseline_id": row.get(
                    "calibration_probability_baseline_id"
                ),
                "calibration_probability_baseline_kind": row.get(
                    "calibration_probability_baseline_kind"
                ),
            }
    if not expected_by_symbol or set(expected_by_symbol) != set(actual_by_symbol):
        raise AcceptanceError("Qt 表格 active model 股票集合與 canonical ML receipt 不完全相符")
    for symbol, expected in expected_by_symbol.items():
        if actual_by_symbol[symbol] != expected:
            raise AcceptanceError(f"Qt 表格模型投影與 sealed execution 不符：{symbol}")
    return {
        "comparison_scope": "canonical receipt-bound active calibrated probability row set and values only",
        "table_object_name": str(view.results_table.objectName()),
        "model_type": type(table_model).__name__,
        "row_count": int(len(frame)),
        "column_names": [str(column) for column in frame.columns],
        "active_rows": [
            {"symbol": symbol, **values}
            for symbol, values in sorted(actual_by_symbol.items())
        ],
    }


def _assert_model_not_preprojected(view: Any) -> dict[str, Any]:
    table_model = getattr(view, "recommendations_model", None)
    if table_model is None or view.results_table.model() is not table_model:
        raise AcceptanceError("保存前 Qt 推薦表格模型不存在")
    frame = table_model.getDataFrame()
    status_values = (
        tuple(str(value) for value in frame["calibrated_probability_status"].tolist())
        if "calibrated_probability_status" in frame.columns
        else ()
    )
    model_values = (
        tuple(str(value) for value in frame["calibration_model_version"].tolist())
        if "calibration_model_version" in frame.columns
        else ()
    )
    if "active_effective" in status_values or CANDIDATE_ID in model_values:
        raise AcceptanceError("canonical save 前 UI 已顯示 verified personal model projection")
    return {
        "row_count": int(len(frame)),
        "active_probability_statuses": list(status_values),
        "model_versions": [str(value) for value in model_values],
        "candidate_visible_before_save": False,
    }


def _widget_render_evidence(window: Any, view: Any, path: Path) -> dict[str, Any]:
    """Best-effort QWidget.grab render; it is not an OS screenshot or business gate."""

    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        if not window.isVisible() or not view.isVisible():
            return {"status": "omitted", "reason": "widget_not_visible"}
        pixmap = window.grab()
        if pixmap.isNull():
            return {"status": "omitted", "reason": "widget_grab_returned_null"}
        buffer_bytes = QByteArray()
        buffer = QBuffer(buffer_bytes)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return {"status": "omitted", "reason": "png_buffer_open_failed"}
        saved = pixmap.save(buffer, "PNG")
        buffer.close()
        payload = bytes(buffer_bytes)
        if not saved or not payload or len(payload) > 24 * 1024 * 1024:
            return {"status": "omitted", "reason": "png_render_invalid_or_over_limit"}
        digest = _write_create_only(path, payload)
        return {
            "status": "saved",
            "capture_kind": "Qt_widget_render_not_OS_screenshot",
            "path": str(path.resolve(strict=True)),
            "sha256": digest,
            "size_bytes": len(payload),
            "width": int(pixmap.width()),
            "height": int(pixmap.height()),
            "window_type": type(window).__name__,
            "window_object_name": str(window.objectName()),
            "view_type": type(view).__name__,
            "view_object_name": str(view.objectName()),
            "table_object_name": str(view.results_table.objectName()),
        }
    except Exception as exc:
        return {
            "status": "omitted",
            "reason": f"{type(exc).__name__}: {exc}",
            "capture_kind": "Qt_widget_render_not_OS_screenshot",
        }


def _verify_canonical_save(view: Any, result_id: str) -> dict[str, Any]:
    read_model = getattr(view, "current_read_model", None)
    receipt = getattr(view, "current_save_receipt", None)
    if read_model is None or receipt is None:
        raise AcceptanceError("UI save 缺 canonical read model 或 save receipt")
    if (
        read_model.result_id != result_id
        or read_model.integrity_basis != "canonical_payload_and_index_verified"
        or receipt.result_id != result_id
        or receipt.payload_hash != read_model.payload_hash
        or receipt.artifact_location != read_model.artifact_location
    ):
        raise AcceptanceError("canonical save receipt/readback 身分不一致")
    composition = view._get_recommendation_composition()
    fresh = composition.queries.get(result_id)
    if (
        fresh is None
        or fresh.result_id != result_id
        or fresh.payload_hash != receipt.payload_hash
        or fresh.execution != read_model.execution
        or fresh.integrity_basis != "canonical_payload_and_index_verified"
    ):
        raise AcceptanceError("canonical query fresh readback 不一致")
    return {
        "result_id": result_id,
        "payload_hash": str(read_model.payload_hash),
        "raw_artifact_sha256": str(read_model.raw_artifact_sha256),
        "artifact_location": str(read_model.artifact_location),
        "persisted_at": read_model.persisted_at.isoformat(),
        "integrity_basis": read_model.integrity_basis,
        "index_status": str(getattr(receipt.index_status, "value", receipt.index_status)),
    }


def _verify_capture(view: Any, result_id: str, layout: Any) -> dict[str, Any]:
    from app_module.recommendation.personal_prediction_capture import (
        read_personal_prediction_capture,
    )

    capture_receipt = getattr(view, "_personal_prediction_capture_receipt", None)
    if capture_receipt is None or capture_receipt.result_id != result_id:
        raise AcceptanceError("UI 未完成 personal prediction capture/readback")
    personal_root = Path(view.config.output_root).resolve(strict=True) / "personal_prediction"
    if not isolated_launcher._is_within(
        personal_root, layout.output_root_actual.resolve(strict=True)
    ):
        raise AcceptanceError("capture root 離開本次隔離 output root")
    composition = view._get_recommendation_composition()
    readback = read_personal_prediction_capture(
        capture_receipt.path,
        composition.queries,
        personal_root,
        expected_result_id=result_id,
    )
    capture_hash, capture_size = isolated_launcher._sha256_regular_file(
        capture_receipt.path,
        max_bytes=16 * 1024 * 1024,
    )
    return {
        "capture_id": capture_receipt.capture_id,
        "capture_path": str(capture_receipt.path.resolve(strict=True)),
        "capture_sha256": capture_hash,
        "capture_size_bytes": capture_size,
        "payload_sha256": capture_receipt.payload_sha256,
        "result_id": result_id,
        "readback_schema": readback.get("schema_version"),
        "idempotent": capture_receipt.idempotent,
    }


class _PersonalModelJourneyDriver:
    """兩階段真 Qt journey；QTimer 只協調 widget 動作與正式 worker。"""

    def __init__(self, *, app: Any, window: Any, phase: str, run_id: str, run_root: Path):
        from PySide6.QtCore import QTimer

        self.app = app
        self.window = window
        self.phase = phase
        self.run_id = run_id
        self.run_root = run_root
        self.layout = isolated_launcher._runtime_layout(run_root)
        self.timer = QTimer(window)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.tick)
        self.stage = "exposure"
        self.started = time.monotonic()
        self.step_started = self.started
        self.error = ""
        self.exit_code = 1
        self.status = "FAILED"
        self.actions: list[dict[str, Any]] = []
        self.proof_records: list[dict[str, Any]] = []
        self.receipt_path = self.layout.receipts_dir / f"personal_model_{phase}.json"
        self.state_path = self.layout.receipts_dir / "personal_model_activation_state.json"
        self._modal_seen = False
        self._save_name = f"隔離個人模型研究 {run_id}"
        self._candidate_loaded = False
        self._last_verified_source: dict[str, Any] | None = None
        self._execution: dict[str, Any] | None = None
        self._canonical_save: dict[str, Any] | None = None
        self._capture: dict[str, Any] | None = None
        self._visible_projection: dict[str, Any] | None = None
        self._pre_save_projection_state: dict[str, Any] | None = None
        self._widget_render: dict[str, Any] | None = None
        self._policy_revision_before_rollback: int | None = None
        self._rollback_target_revision: int | None = None
        self._rollback_target_policy_sha256: str | None = None
        self._rollback_target_candidate: dict[str, Any] | None = None
        self._rollback_target_source_time_trust: dict[str, Any] | None = None
        self._rollback_evidence: dict[str, Any] | None = None
        self._visible_window_at_exit = False
        self._failure_details: dict[str, Any] = {}
        self._deferred_click_pending = False

    def _action(self, action: str, detail: Mapping[str, Any] | None = None) -> None:
        self.actions.append(
            {
                "sequence": len(self.actions) + 1,
                "action": action,
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "detail": dict(detail or {}),
            }
        )

    def _click_in_stage(
        self,
        stage: str,
        button: Any,
        action: str,
        detail: Mapping[str, Any] | None = None,
        *,
        expected_modal: Any | None,
    ) -> None:
        """先發布 stage，待目前 timer slot 返回後再安全點擊。"""

        from PySide6.QtCore import QTimer

        self.stage = stage
        self.step_started = time.monotonic()
        self._action(action, detail)
        if self._deferred_click_pending:
            self._finish("FAILED", "前一個 deferred Qt click 尚未執行")
            return
        self._deferred_click_pending = True

        def invoke_click() -> None:
            self._deferred_click_pending = False
            if self.stage == "closing":
                return
            if self.stage != stage:
                self._finish(
                    "FAILED",
                    f"deferred Qt click 階段已改變：預期 {stage}，目前 {self.stage}",
                )
                return
            now = time.monotonic()
            stage_timeout = STAGE_TIMEOUT_SECONDS.get(stage, MAX_PHASE_SECONDS)
            if (
                now - self.started >= MAX_PHASE_SECONDS
                or now - self.step_started >= stage_timeout
            ):
                self._finish("TIMEOUT", f"{stage} 階段在 deferred Qt click 前逾時")
                return
            try:
                active_modal = self.app.activeModalWidget()
                if active_modal is not expected_modal:
                    expectation = "無 modal" if expected_modal is None else "原 modal"
                    actual = (
                        "無 modal"
                        if active_modal is None
                        else type(active_modal).__name__
                    )
                    raise AcceptanceError(
                        f"deferred Qt click 的 modal 身分改變：預期 {expectation}，目前 {actual}"
                    )
                if button is None or not button.isEnabled() or not button.isVisible():
                    raise AcceptanceError("deferred Qt click 的按鈕已失效、停用或不可見")
                self._action("執行已排程的 Qt 按鈕點擊", {"stage": stage})
                button.click()
            except Exception as exc:
                self._finish("FAILED", f"deferred Qt click 失敗：{type(exc).__name__}: {exc}")

        QTimer.singleShot(0, invoke_click)

    def _reject_active_modal_for_stop(self) -> None:
        """失敗／timeout 時拒絕目前 modal，避免巢狀 event loop 遺留。"""

        modal = self.app.activeModalWidget()
        if modal is None:
            return
        title_getter = getattr(modal, "windowTitle", None)
        title = str(title_getter() if callable(title_getter) else "")[:160]
        reject = getattr(modal, "reject", None)
        close = getattr(modal, "close", None)
        try:
            if callable(reject):
                reject()
            elif callable(close):
                close()
        except Exception:
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        self._failure_details["modal_rejected_on_fail_closed_stop"] = {
            "window_title": title,
            "class_name": type(modal).__name__[:120],
        }

    def _view(self):
        view = getattr(self.window, "recommendation_view", None)
        if view is None:
            raise AcceptanceError("MainWindow 沒有 RecommendationView")
        return view

    def _navigate_to_recommendation(self) -> None:
        navigation = getattr(self.window, "left_navigation", None)
        button = navigation.button_for_key("recommendation") if navigation else None
        if button is None:
            raise AcceptanceError("MainWindow 沒有推薦分析導覽按鈕")
        button.click()
        self._action("點擊推薦分析導覽")

    def _candidate_index(self, view: Any) -> int:
        combo = view.personal_candidate_combo
        for index in range(combo.count()):
            if str(combo.itemData(index)) == str(CANDIDATE_ROOT.resolve(strict=True)):
                return index
        return -1

    def _select_candidate(self, view: Any) -> None:
        index = self._candidate_index(view)
        if index < 0:
            raise AcceptanceError("UI candidate inventory 沒有固定候選 root")
        view.personal_candidate_combo.setCurrentIndex(index)
        self.app.processEvents()
        self._candidate_loaded = True
        self._action("由真候選清冊選取固定候選", {"candidate_id": CANDIDATE_ID})

    def _click_refresh_candidates(self, view: Any) -> None:
        button = view.personal_candidate_refresh_button
        if button.isEnabled():
            button.click()
            self._action("點擊讀取候選清冊")

    def _set_source_path(self, view: Any, db_path: Path) -> None:
        value = str(db_path.resolve(strict=True))
        if view.personal_source_database_input.text().strip() != value:
            view.personal_source_database_input.setText(value)
            self.app.processEvents()
        if view.personal_source_database_input.text().strip() != value:
            raise AcceptanceError("UI 未保留本次 working DB 的明示絕對路徑")

    def _verify_proposal(self, view: Any, db_path: Path) -> dict[str, Any]:
        proposal = getattr(view, "_personal_source_time_proposal", None)
        if proposal is None:
            raise AcceptanceError("UI 尚無 source-time preview proposal")
        record = _verify_initial_proposal(proposal=proposal, db_path=db_path)
        self.proof_records.append({"phase": self.phase, "stage": self.stage, **record})
        self._last_verified_source = record
        return record

    def _fresh_saved_policy_proof(self, view: Any, db_path: Path) -> dict[str, Any]:
        config, actual_db = _runtime_config(
            self.run_root, self.layout, config=getattr(view, "config", None)
        )
        if not isolated_launcher._same_path(actual_db, db_path.resolve(strict=True)):
            raise AcceptanceError("runtime config DB 與本次 source proof DB 不同")
        # 使用現有 production inventory/source replay API；不手造 policy、pins 或 proof。
        proof = _verify_saved_policy_source(
            run_root=self.run_root,
            layout=self.layout,
            config=config,
            db_path=actual_db,
        )
        self.proof_records.append({"phase": self.phase, "stage": self.stage, **proof})
        self._last_verified_source = proof
        return proof

    def _dismiss_modal(self) -> bool:
        from PySide6.QtWidgets import QDialogButtonBox, QInputDialog, QMessageBox

        modal = self.app.activeModalWidget()
        if modal is None:
            self._modal_seen = False
            return False
        if isinstance(modal, QInputDialog) and self.stage == "waiting_save_dialog":
            modal.setTextValue(self._save_name)
            buttons = modal.findChild(QDialogButtonBox)
            button = buttons.button(QDialogButtonBox.StandardButton.Ok) if buttons else None
            if button is None:
                raise AcceptanceError("保存對話框缺少確認按鈕")
            self._click_in_stage(
                "waiting_save",
                button,
                "在真保存對話框輸入隔離結果名稱",
                expected_modal=modal,
            )
            return True
        if isinstance(modal, QMessageBox):
            text = modal.text()
            if self.stage == "waiting_save" and "canonical readback 驗證" in text:
                button = modal.button(QMessageBox.StandardButton.Ok)
                if button is None:
                    raise AcceptanceError("保存成功對話框缺少 OK")
                self._click_in_stage(
                    "waiting_save",
                    button,
                    "確認 canonical 保存成功提示",
                    expected_modal=modal,
                )
                return True
            if self.stage == "waiting_rollback_confirmation":
                button = modal.button(QMessageBox.StandardButton.Yes)
                if button is None:
                    raise AcceptanceError("V2 rollback 確認對話框缺少 Yes")
                self._click_in_stage(
                    "waiting_rollback_save",
                    button,
                    "明確確認 V2 歷史政策回退",
                    expected_modal=modal,
                )
                return True
            raise AcceptanceError(
                f"旅程出現未預期 QMessageBox：{modal.windowTitle()}／{text[:240]}"
            )
        raise AcceptanceError(
            f"旅程出現未預期 modal：{type(modal).__name__}／{modal.windowTitle()}"
        )

    def _verify_visible_window(self) -> bool:
        handle = self.window.windowHandle()
        return bool(self.window.isVisible() and handle is not None and handle.isExposed())

    def _start(self) -> None:
        self._navigate_to_recommendation()
        self.stage = "recommendation_ready" if self.phase == "activate" else "reload_ready"
        self.step_started = time.monotonic()

    def _finish(self, status: str, error: str = "") -> None:
        if self.stage == "closing":
            return
        self.status = status
        self.error = error
        self.exit_code = 0 if status == "PASS" else 2
        self.stage = "closing"
        self._reject_active_modal_for_stop()
        self.window.close()
        self.step_started = time.monotonic()

    def _activation_tick(self, view: Any) -> None:
        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUsePolicyV2,
            load_personal_use_policy_snapshot,
        )

        db_path = self.layout.working_db_path.resolve(strict=True)
        if self.stage == "recommendation_ready":
            self._click_refresh_candidates(view)
            self.stage = "waiting_inventory"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_inventory":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            self._select_candidate(view)
            self._set_source_path(view, db_path)
            self.stage = "waiting_candidate_selection"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_candidate_selection":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            entry = getattr(view, "_personal_candidate_entry", None)
            if (
                entry is None
                or getattr(entry, "candidate_id", None) != CANDIDATE_ID
                or not isolated_launcher._same_path(
                    Path(getattr(entry, "candidate_root", "")), CANDIDATE_ROOT
                )
            ):
                raise AcceptanceError("UI 所選候選 inventory entry 身份不符")
            if not view.personal_source_time_check_button.isEnabled():
                raise AcceptanceError("UI source-time check 按鈕尚未啟用")
            view.personal_source_time_check_button.click()
            self._action("點擊指定來源時間檢查", {"db_path": str(db_path)})
            self.stage = "waiting_preview"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_preview":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            record = self._verify_proposal(view, db_path)
            if not SOURCE_SLICE_PATTERN.fullmatch(record["source_slice_sha256"]):
                raise AcceptanceError("UI preview source slice SHA 格式錯誤")
            mode = view.personal_policy_mode_combo
            index = mode.findData("personal_calibrated_probability")
            if index < 0:
                raise AcceptanceError("UI 沒有 personal calibrated mode")
            mode.setCurrentIndex(index)
            checkbox = view.personal_source_time_trust_checkbox
            if not checkbox.isChecked():
                checkbox.click()
            if not view.personal_policy_confirm_button.isEnabled():
                raise AcceptanceError("來源信任未明確勾選，V2 CAS 確認鈕仍停用")
            view.personal_policy_confirm_button.click()
            self._action("明確信任此研究來源並保存 V2 CAS")
            self.stage = "waiting_policy_revalidation"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_policy_revalidation":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if (
                type(policy) is not RecommendationPersonalUsePolicyV2
                or policy.mode != "personal_calibrated_probability"
                or not view._personal_policy_source_is_verified(policy)
            ):
                raise AcceptanceError("V2 CAS 後 UI 未完成 fresh source readback")
            self.stage = "pre_execute_source_check"
        if self.stage == "pre_execute_source_check":
            config, actual_db = _runtime_config(self.run_root, self.layout)
            proof = self._fresh_saved_policy_proof(view, actual_db)
            if not proof["candidate_pins"]:
                raise AcceptanceError("執行前 source proof 缺候選 pins")
            view.execute_btn.click()
            self._action("執行前重算來源 proof 後點擊真推薦按鈕", {"db_path": str(actual_db)})
            self.stage = "waiting_execution"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_execution":
            worker = getattr(view, "worker", None)
            if worker is not None and worker.isRunning():
                return
            execution = getattr(view, "current_execution", None)
            if execution is None or not view.execute_btn.isEnabled():
                return
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if self._last_verified_source is None:
                raise AcceptanceError("本次 invocation 缺少執行前 fresh source proof")
            self._execution = _verify_active_execution(
                view,
                policy.to_dict(),
                run_root=self.run_root,
                expected_source_proof=self._last_verified_source,
            )
            self._pre_save_projection_state = _assert_model_not_preprojected(view)
            if not view.save_result_btn.isVisible() or not view.save_result_btn.isEnabled():
                raise AcceptanceError("active model execution 完成但真保存按鈕不可用")
            self._click_in_stage(
                "waiting_save_dialog",
                view.save_result_btn,
                "點擊真 canonical 保存按鈕",
                expected_modal=None,
            )
            return
        if self.stage == "waiting_save":
            result_id = view._verified_saved_result_id()
            if not result_id:
                return
            self._canonical_save = _verify_canonical_save(view, result_id)
            saved_view = self._view()
            if not isinstance(self._execution, Mapping):
                raise AcceptanceError("canonical save 前缺少 receipt-bound execution evidence")
            projection_receipt = self._execution.get("projection_receipt")
            if not isinstance(projection_receipt, Mapping):
                raise AcceptanceError("canonical save 前缺少 verified projection receipt")
            self._visible_projection = _visible_probability_projection(
                saved_view,
                saved_view.current_read_model.execution,
                projection_receipt,
            )
            self.stage = "waiting_capture"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_capture":
            result_id = str((self._canonical_save or {}).get("result_id") or "")
            status_label = getattr(view, "personal_prediction_capture_status_label", None)
            status_text = status_label.text() if status_label is not None else ""
            failure = _capture_failure_message(status_text, result_id)
            if failure is not None:
                worker = getattr(view, "_personal_prediction_capture_worker", None)
                if worker is None or not worker.isRunning():
                    raise AcceptanceError(
                        f"本次結果個人模型擷取 worker 已失敗／取消：{failure or 'no detail'}"
                    )
            capture_receipt = getattr(view, "_personal_prediction_capture_receipt", None)
            if capture_receipt is None:
                return
            self._capture = _verify_capture(view, result_id, self.layout)
            self._widget_render = _widget_render_evidence(
                self.window,
                view,
                self.layout.receipts_dir / "personal_model_active_widget.png",
            )
            self._write_activation_state(view)
            self._finish("PASS")
            return
        raise AcceptanceError(f"activation phase 未知狀態：{self.stage}")

    def _write_activation_state(self, view: Any) -> None:
        policy = _read_json_regular(self.layout.policy_config_path, max_bytes=2 * 1024 * 1024)
        state = {
            "schema_version": "native-personal-model-activation-state.v1",
            "run_id": self.run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "candidate_id": CANDIDATE_ID,
            "candidate_pins": dict(CANDIDATE_PINS),
            "run_root": str(self.run_root.resolve(strict=True)),
            "working_db_path": str(self.layout.working_db_path.resolve(strict=True)),
            "policy_path": str(self.layout.policy_config_path.resolve(strict=True)),
            "policy_revision": policy.get("revision"),
            "policy_sha256": policy.get("policy_sha256"),
            "source_time_trust": policy.get("source_time_trust"),
            "execution": self._execution,
            "canonical_save": self._canonical_save,
            "capture": self._capture,
            "pre_save_projection_state": self._pre_save_projection_state,
            "visible_probability_projection": self._visible_projection,
            "widget_render": self._widget_render,
            "source_proofs": self.proof_records,
        }
        _write_json_create_only(self.state_path, state)

    def _rollback_disable_tick(self, view: Any) -> None:
        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUsePolicyV2,
            load_personal_use_policy_snapshot,
        )

        db_path = self.layout.working_db_path.resolve(strict=True)
        if self.stage == "reload_ready":
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if type(policy) is not RecommendationPersonalUsePolicyV2 or policy.mode != "personal_calibrated_probability":
                raise AcceptanceError("cold restart 未載入原 V2 personal calibrated policy")
            if Path(str(policy.source_time_trust.source_database_path)).resolve(strict=True) != db_path:
                raise AcceptanceError("cold restart policy source path 不等於本次 working DB")
            self._click_refresh_candidates(view)
            self.stage = "waiting_reload_inventory"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_reload_inventory":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            self._select_candidate(view)
            self._set_source_path(view, db_path)
            self.stage = "waiting_reload_candidate_selection"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_reload_candidate_selection":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            entry = getattr(view, "_personal_candidate_entry", None)
            if (
                entry is None
                or getattr(entry, "candidate_id", None) != CANDIDATE_ID
                or not isolated_launcher._same_path(
                    Path(getattr(entry, "candidate_root", "")), CANDIDATE_ROOT
                )
            ):
                raise AcceptanceError("cold restart UI candidate entry 身份不符")
            if not view.personal_source_time_check_button.isEnabled():
                raise AcceptanceError("cold restart source-time check 按鈕尚未啟用")
            view.personal_source_time_check_button.click()
            self._action("cold restart 後重新檢查已保存 V2 來源")
            self.stage = "waiting_reload_proof"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_reload_proof":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if not view._personal_policy_source_is_verified(policy):
                raise AcceptanceError("cold restart 未 fresh revalidate saved V2 source")
            proof = self._fresh_saved_policy_proof(view, db_path)
            self._action("cold restart source proof 重算成功", proof)
            mode = view.personal_policy_mode_combo
            rule_index = mode.findData("rule_only")
            if rule_index < 0:
                raise AcceptanceError("UI 沒有 rule_only mode")
            mode.setCurrentIndex(rule_index)
            view.personal_policy_confirm_button.click()
            self._action("停用個人校準並保存 rule_only V2")
            self.stage = "waiting_rule_only_save"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_rule_only_save":
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if policy.mode != "rule_only" or getattr(policy, "candidate", None) is not None:
                return
            if getattr(policy, "source_time_trust", None) is not None:
                raise AcceptanceError("停用 V2 尚未清除 source trust")
            self._policy_revision_before_rollback = policy.revision
            view.personal_policy_history_refresh_button.click()
            self._action("讀取封存的政策 revision 清冊")
            self.stage = "waiting_history"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_history":
            if getattr(view, "_personal_policy_history_worker", None) is not None:
                return
            combo = view.personal_policy_history_combo
            target_index = -1
            for index in range(combo.count()):
                target = combo.itemData(index)
                if (
                    getattr(target, "mode", None) == "personal_calibrated_probability"
                    and getattr(target, "candidate", None) is not None
                    and getattr(target, "source_time_trust", None) is not None
                    and target.candidate.candidate_id == CANDIDATE_ID
                    and _personal_policy_revision_matches_state(target, self.state_path)
                ):
                    target_index = index
                    self._rollback_target_revision = target.revision
                    self._rollback_target_policy_sha256 = target.policy_sha256
                    self._rollback_target_candidate = target.candidate.to_dict()
                    self._rollback_target_source_time_trust = (
                        target.source_time_trust.to_dict()
                    )
                    break
            if target_index < 0:
                raise AcceptanceError("policy history 未讀回本次保存的 V2 candidate revision")
            combo.setCurrentIndex(target_index)
            self._select_candidate(view)
            self._set_source_path(view, db_path)
            self.stage = "waiting_rollback_candidate_selection"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_rollback_candidate_selection":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            candidate_combo: Any = getattr(view, "personal_candidate_combo", None)
            source_input: Any = getattr(view, "personal_source_database_input", None)
            source_check: Any = getattr(view, "personal_source_time_check_button", None)
            selected_candidate_root: Any = None
            selected_source_path: Any = None
            source_check_enabled = False
            try:
                selected_candidate_root = candidate_combo.currentData()
                selected_source_path = source_input.text().strip()
                source_check_enabled = source_check.isEnabled()
            except (AttributeError, RuntimeError, TypeError):
                source_check_enabled = False
            mismatches = _rollback_candidate_selection_mismatches(
                selected_candidate_root=selected_candidate_root,
                selected_source_database_path=selected_source_path,
                expected_candidate_root=CANDIDATE_ROOT,
                expected_source_database_path=db_path,
                source_check_enabled=source_check_enabled,
            )
            if mismatches:
                raise AcceptanceError(
                    "V2 rollback UI candidate/source 選取不符："
                    + ",".join(mismatches)
                )
            source_check.click()
            self._action("為 V2 rollback 取得新鮮來源提案")
            self.stage = "waiting_rollback_proposal"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_rollback_proposal":
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            proposal = getattr(view, "_personal_source_time_proposal", None)
            if proposal is None:
                raise AcceptanceError("V2 rollback 缺 fresh source-time proposal")
            target = view.personal_policy_history_combo.currentData()
            target_mismatches = _rollback_history_target_mismatches(
                target,
                target_revision=self._rollback_target_revision,
                target_policy_sha256=self._rollback_target_policy_sha256,
                target_candidate=self._rollback_target_candidate,
                target_source_time_trust=self._rollback_target_source_time_trust,
            )
            if target_mismatches:
                raise AcceptanceError(
                    "V2 rollback history target 與所選封存版本不符："
                    + ",".join(target_mismatches)
                )
            proposal_map = _dto_mapping(proposal)
            target_trust = target.source_time_trust.to_dict()
            compare_policy = {
                "schema_version": "recommendation-personal-use-policy.v2",
                "mode": "personal_calibrated_probability",
                "candidate": target.candidate.to_dict(),
                "source_time_trust": target_trust,
                "confirmed_at": target.confirmed_at,
            }
            info = db_path.stat()
            mismatches = _source_binding_mismatches(
                policy=compare_policy,
                proposal=proposal_map,
                config_db_path=db_path,
                expected_candidate_root=CANDIDATE_ROOT,
                actual_file_identity={"device": int(info.st_dev), "inode": int(info.st_ino)},
            )
            if mismatches:
                raise AcceptanceError("V2 rollback source proposal 不匹配：" + ",".join(mismatches))
            self.proof_records.append(
                {"phase": self.phase, "stage": self.stage, **_verify_initial_proposal(proposal=proposal, db_path=db_path)}
            )
            self._click_in_stage(
                "waiting_rollback_confirmation",
                view.personal_policy_rollback_button,
                "點擊 V2 rollback 操作",
                expected_modal=None,
            )
            return
        if self.stage == "waiting_rollback_save":
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if (
                type(policy) is not RecommendationPersonalUsePolicyV2
                or policy.mode != "personal_calibrated_probability"
            ):
                return
            if policy.revision <= int(self._policy_revision_before_rollback or 0):
                return
            rollback_mismatches = _rollback_policy_mismatches(
                policy.to_dict(),
                target_revision=int(self._rollback_target_revision or 0),
                target_policy_sha256=str(self._rollback_target_policy_sha256 or ""),
                target_candidate=self._rollback_target_candidate or {},
                target_source_time_trust=self._rollback_target_source_time_trust or {},
            )
            if rollback_mismatches:
                raise AcceptanceError(
                    "V2 rollback readback 未精確回指所選版本："
                    + ",".join(rollback_mismatches)
                )
            self._rollback_evidence = {
                "target_revision": self._rollback_target_revision,
                "target_policy_sha256": self._rollback_target_policy_sha256,
                "source_database_path": policy.source_time_trust.source_database_path,
                "current_revision_before_rollback": self._policy_revision_before_rollback,
                "new_revision": policy.revision,
                "new_policy_sha256": policy.policy_sha256,
                "rollback_of_revision": policy.rollback_of_revision,
                "rollback_of_policy_sha256": policy.rollback_of_policy_sha256,
            }
            self._action("V2 rollback 新 revision 精確回指選定歷史版本", self._rollback_evidence)
            if getattr(view, "_personal_candidate_worker", None) is not None:
                return
            if not view._personal_policy_source_is_verified(policy):
                return
            self._fresh_saved_policy_proof(view, db_path)
            mode = view.personal_policy_mode_combo
            rule_index = mode.findData("rule_only")
            mode.setCurrentIndex(rule_index)
            view.personal_policy_confirm_button.click()
            self._action("回退來源重驗後再次保存最終 rule_only")
            self.stage = "waiting_final_rule_only"
            self.step_started = time.monotonic()
            return
        if self.stage == "waiting_final_rule_only":
            policy = load_personal_use_policy_snapshot(self.layout.policy_config_path)
            if policy.mode != "rule_only" or getattr(policy, "candidate", None) is not None:
                return
            if getattr(policy, "source_time_trust", None) is not None:
                raise AcceptanceError("最終 rule_only policy 仍帶 source trust")
            state = _read_saved_state(self.state_path)
            if (
                state.get("candidate_id") != CANDIDATE_ID
                or state.get("run_id") != self.run_id
                or policy.revision <= int(self._policy_revision_before_rollback or 0)
            ):
                raise AcceptanceError("final rule_only revision/state identity 不符")
            self._widget_render = _widget_render_evidence(
                self.window,
                view,
                self.layout.receipts_dir / "personal_model_rule_only_widget.png",
            )
            self._finish("PASS")
            return
        raise AcceptanceError(f"restart/rollback phase 未知狀態：{self.stage}")

    def tick(self) -> None:
        if time.monotonic() - self.started > MAX_PHASE_SECONDS:
            self._finish("TIMEOUT", f"phase 超過 {MAX_PHASE_SECONDS} 秒")
            return
        stage_timeout = STAGE_TIMEOUT_SECONDS.get(self.stage)
        if (
            stage_timeout is not None
            and time.monotonic() - self.step_started > stage_timeout
        ):
            self._finish(
                "TIMEOUT",
                f"{self.stage} 階段超過 {stage_timeout} 秒；停止旅程且不啟動後續 phase",
            )
            return
        if self.stage == "closing":
            if not self.window.isVisible():
                self.timer.stop()
                self.app.exit(self.exit_code)
            elif time.monotonic() - self.step_started > 60:
                self.timer.stop()
                self.app.exit(2)
            return
        try:
            if self.app.activeModalWidget() is not None:
                self._dismiss_modal()
                return
            if self.stage == "exposure":
                if not self._verify_visible_window():
                    if time.monotonic() - self.step_started > 30:
                        raise AcceptanceError("MainWindow 未在 30 秒內 visible/exposed")
                    return
                self._start()
                return
            view = self._view()
            if self.phase == "activate":
                self._activation_tick(view)
            else:
                self._rollback_disable_tick(view)
        except Exception as exc:
            diagnostic = getattr(exc, "diagnostic", None)
            if isinstance(diagnostic, Mapping):
                self._failure_details = dict(diagnostic)
            self._finish("FAILED", f"{type(exc).__name__}: {exc}")

    def run(self) -> int:
        self.timer.start()
        return int(self.app.exec())

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "native-personal-model-phase-receipt.v1",
            "phase": self.phase,
            "run_id": self.run_id,
            "status": self.status,
            "error": self.error,
            "failure_details": self._failure_details,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "process_id": os.getpid(),
            "parent_process_id": os.getppid(),
            "runtime_executable": str(Path(sys.executable).resolve(strict=True)),
            "candidate_id": CANDIDATE_ID,
            "candidate_root": str(CANDIDATE_ROOT.resolve(strict=True)),
            "run_root": str(self.run_root.resolve(strict=True)),
            "profile": os.environ.get("PROFILE"),
            "working_db_path": str(self.layout.working_db_path.resolve(strict=True)),
            "policy_path": str(self.layout.policy_config_path.resolve(strict=False)),
            "learning_output_root": os.environ.get("RECOMMENDATION_LEARNING_OUTPUT_ROOT"),
            "actions": self.actions,
            "source_proofs": self.proof_records,
            "candidate_file_sha256": _verify_candidate_bundle()["candidate_file_sha256"],
            "lineage_sha256": LINEAGE_SHA256,
            "execution": self._execution,
            "canonical_save": self._canonical_save,
            "capture": self._capture,
            "pre_save_projection_state": self._pre_save_projection_state,
            "visible_probability_projection": self._visible_projection,
            "widget_render": self._widget_render,
            "visible_window_before_deferred_delete_drain": self._visible_window_at_exit,
            "rollback": self._rollback_evidence,
            "all_business_actions_via_qt_controls": True,
            "qscreen_screenshot_required": False,
            "formal_database_written": False,
            "candidate_learning_root_written": False,
            "global_pointer_touched": False,
            "scheduler_started": False,
            "http_requested": False,
        }


def _personal_policy_revision_matches_state(target: Any, state_path: Path) -> bool:
    try:
        state = _read_saved_state(state_path)
        return (
            target.revision == state.get("policy_revision")
            and target.policy_sha256 == state.get("policy_sha256")
            and target.candidate.to_dict() == state.get("source_time_trust", {}).get("candidate")
        )
    except (AcceptanceError, AttributeError, TypeError):
        return False


def _configure_child_environment(layout: Any) -> dict[str, str]:
    env = os.environ.copy()
    env["DATA_ROOT"] = str(layout.data_root_base.resolve())
    env["OUTPUT_ROOT"] = str(layout.output_root_base.resolve())
    env["PROFILE"] = "test"
    env["RECOMMENDATION_LEARNING_OUTPUT_ROOT"] = str(
        LEARNING_OUTPUT_ROOT.resolve(strict=True)
    )
    env["QT_QPA_PLATFORM"] = "windows"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for key in isolated_launcher._ISOLATED_ARTIFACT_ENV:
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("FORMAL_DAILY_", "PIT_SECTOR_", "PIT_MEMBERSHIP_")):
            env.pop(key, None)
    env["FORMAL_DAILY_RUNTIME_ENVIRONMENT_FILE"] = str(
        layout.run_root / ".missing-formal-runtime-binding.json"
    )
    return env


def _capture_owned_process_tree(
    *, child_pid: int, expected_parent_pid: int, expected_create_time: float
) -> dict[str, Any]:
    """Snapshot a runner-owned process tree, proving its root and parent chain."""

    try:
        import psutil
    except ImportError as exc:
        return {"error": f"psutil_unavailable:{type(exc).__name__}"}
    try:
        root = psutil.Process(child_pid)
        root_info = root.as_dict(attrs=("pid", "ppid", "create_time", "name"))
        root_create_time = float(root_info["create_time"])
        if root_info.get("ppid") != expected_parent_pid:
            return {"error": "popen_root_parent_mismatch"}
        if abs(root_create_time - expected_create_time) > 0.001:
            return {"error": "popen_root_creation_time_changed"}
        raw_descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return {"error": "popen_root_disappeared_before_tree_capture"}
    except (psutil.AccessDenied, OSError) as exc:
        return {"error": f"process_tree_read_denied:{type(exc).__name__}"}

    entries: dict[int, dict[str, Any]] = {}
    for process in raw_descendants:
        try:
            info = process.as_dict(attrs=("pid", "ppid", "create_time", "name", "cmdline"))
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError) as exc:
            return {"error": f"descendant_identity_unreadable:{type(exc).__name__}"}
        pid = info.get("pid")
        ppid = info.get("ppid")
        created = info.get("create_time")
        if type(pid) is not int or type(ppid) is not int or type(created) not in (int, float):
            return {"error": "descendant_identity_incomplete"}
        cmdline = info.get("cmdline")
        cmdline_bytes = json.dumps(
            cmdline if isinstance(cmdline, list) else [],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="replace")
        entries[pid] = {
            "pid": pid,
            "parent_process_id": ppid,
            "create_time": f"{float(created):.6f}",
            "create_time_value": float(created),
            "name": str(info.get("name") or "")[:120],
            "command_line_sha256": hashlib.sha256(cmdline_bytes).hexdigest(),
        }

    root_entry = {
        "pid": child_pid,
        "parent_process_id": expected_parent_pid,
        "create_time": f"{root_create_time:.6f}",
        "create_time_value": root_create_time,
        "name": str(root_info.get("name") or "")[:120],
        "command_line_sha256": None,
        "depth": 0,
    }
    for pid, entry in entries.items():
        cursor = entry["parent_process_id"]
        depth = 1
        visited = {pid}
        while cursor != child_pid:
            if cursor in visited or cursor not in entries:
                return {"error": "descendant_parent_chain_not_owned"}
            visited.add(cursor)
            cursor = entries[cursor]["parent_process_id"]
            depth += 1
        entry["depth"] = depth
    ordered = [root_entry] + sorted(
        entries.values(), key=lambda value: (value["depth"], value["pid"])
    )
    for entry in ordered:
        entry.pop("create_time_value", None)
    return {
        "root": root_entry,
        "processes": ordered,
        "descendant_count": len(entries),
    }


def _process_still_matches(entry: Mapping[str, Any]) -> bool:
    try:
        import psutil

        process = psutil.Process(int(entry["pid"]))
        current_create_time = float(process.create_time())
        expected_create_time = float(entry["create_time"])
        return abs(current_create_time - expected_create_time) <= 0.001
    except (ImportError, KeyError, TypeError, ValueError, OSError):
        return False
    except Exception as exc:
        # psutil exposes platform-specific NoSuchProcess/AccessDenied exceptions.
        if type(exc).__module__.startswith("psutil"):
            return False
        raise


def _wait_for_owned_child(
    child: subprocess.Popen[Any], *, timeout_seconds: float
) -> tuple[int | None, dict[str, Any] | None]:
    """Bounded wait; timeout cleanup is limited to a verified Popen-owned tree."""

    try:
        import psutil

        root_process = psutil.Process(child.pid)
        root_info = root_process.as_dict(attrs=("pid", "ppid", "create_time"))
        initial_root_create_time = float(root_info["create_time"])
        initial_identity_error = (
            None
            if root_info.get("ppid") == os.getpid()
            else "popen_root_parent_mismatch_before_wait"
        )
    except ImportError:
        initial_root_create_time = None
        initial_identity_error = "psutil_unavailable"
    except Exception as exc:
        initial_root_create_time = None
        initial_identity_error = f"popen_root_identity_unavailable:{type(exc).__name__}"

    try:
        return child.wait(timeout=timeout_seconds), None
    except subprocess.TimeoutExpired:
        actions: list[dict[str, Any]] = []
        tree_evidence: list[dict[str, Any]] = []
        manual_attention_required = False
        termination_action = "no_signal_identity_unverified"
        identity_error = initial_identity_error
        if child.poll() is not None:
            identity_error = "popen_launcher_exited_before_timeout_tree_cleanup"
            manual_attention_required = True
        elif initial_root_create_time is None or initial_identity_error is not None:
            manual_attention_required = True
        else:
            termination_action = "verified_process_tree_cleanup"
            # Re-scan while the Popen root is alive so processes it spawned during the
            # first pass are included. The root is signalled only after descendants end.
            for scan_index in range(3):
                snapshot = _capture_owned_process_tree(
                    child_pid=child.pid,
                    expected_parent_pid=os.getpid(),
                    expected_create_time=initial_root_create_time,
                )
                if "error" in snapshot:
                    previously_observed_descendants = [
                        entry
                        for entry in tree_evidence
                        if entry.get("pid") != child.pid
                        and _process_still_matches(entry)
                    ]
                    if (
                        snapshot.get("error") == "popen_root_disappeared_before_tree_capture"
                        and child.poll() is not None
                        and tree_evidence
                        and not previously_observed_descendants
                    ):
                        termination_action = "verified_tree_exited_after_descendant_termination"
                        break
                    identity_error = str(snapshot["error"])
                    manual_attention_required = True
                    termination_action = "process_tree_identity_unverified_no_further_signal"
                    break
                processes = list(snapshot["processes"])
                for entry in processes:
                    tree_evidence.append(
                        {
                            key: value
                            for key, value in entry.items()
                            if key != "depth"
                        }
                    )
                descendants = sorted(
                    (entry for entry in processes if entry["pid"] != child.pid),
                    key=lambda value: (-int(value["depth"]), int(value["pid"])),
                )
                try:
                    import psutil
                except ImportError:
                    identity_error = "psutil_unavailable_during_cleanup"
                    manual_attention_required = True
                    termination_action = "process_tree_identity_unverified_no_further_signal"
                    break
                descendants_to_wait: list[Any] = []
                for entry in descendants:
                    if not _process_still_matches(entry):
                        continue
                    try:
                        process = psutil.Process(int(entry["pid"]))
                        if process.ppid() != int(entry["parent_process_id"]):
                            identity_error = "descendant_parent_changed_before_terminate"
                            manual_attention_required = True
                            break
                        parent_entry = next(
                            (
                                observed
                                for observed in processes
                                if observed["pid"] == entry["parent_process_id"]
                            ),
                            None,
                        )
                        if parent_entry is not None and not _process_still_matches(parent_entry):
                            identity_error = "descendant_parent_identity_changed_before_terminate"
                            manual_attention_required = True
                            break
                        if parent_entry is not None:
                            parent_process = psutil.Process(int(parent_entry["pid"]))
                            expected_parent_of_parent = (
                                os.getpid()
                                if parent_entry["pid"] == child.pid
                                else int(parent_entry["parent_process_id"])
                            )
                            if parent_process.ppid() != expected_parent_of_parent:
                                identity_error = "descendant_parent_chain_changed_before_terminate"
                                manual_attention_required = True
                                break
                        process.terminate()
                        descendants_to_wait.append(process)
                        actions.append({"pid": entry["pid"], "action": "terminate"})
                    except psutil.NoSuchProcess:
                        continue
                    except (psutil.AccessDenied, OSError) as exc:
                        identity_error = f"descendant_terminate_denied:{type(exc).__name__}"
                        manual_attention_required = True
                        break
                if manual_attention_required:
                    termination_action = "process_tree_identity_unverified_no_further_signal"
                    break
                _gone, alive = psutil.wait_procs(descendants_to_wait, timeout=2.0)
                for process in alive:
                    entry = next(
                        (
                            item
                            for item in descendants
                            if item["pid"] == process.pid
                        ),
                        None,
                    )
                    if entry is None or not _process_still_matches(entry):
                        identity_error = "descendant_identity_changed_before_kill"
                        manual_attention_required = True
                        break
                    try:
                        process.kill()
                        actions.append({"pid": entry["pid"], "action": "kill_after_terminate_timeout"})
                    except psutil.NoSuchProcess:
                        continue
                    except (psutil.AccessDenied, OSError) as exc:
                        identity_error = f"descendant_kill_denied:{type(exc).__name__}"
                        manual_attention_required = True
                        break
                if manual_attention_required:
                    termination_action = "process_tree_identity_unverified_no_further_signal"
                    break
                _gone, alive_after_kill = psutil.wait_procs(alive, timeout=2.0)
                if alive_after_kill:
                    identity_error = "owned_descendant_still_running_after_kill"
                    manual_attention_required = True
                    termination_action = "manual_attention_descendant_still_running"
                    break
                if child.poll() is not None:
                    still_running = [
                        entry
                        for entry in descendants
                        if _process_still_matches(entry)
                    ]
                    if still_running:
                        identity_error = "popen_root_exited_while_owned_descendant_remains"
                        manual_attention_required = True
                        termination_action = "manual_attention_descendant_still_running"
                    else:
                        termination_action = "verified_tree_exited_after_descendant_termination"
                    break
                if descendants:
                    continue
                # The process tree is empty on two observations; now stop the exact
                # Popen launcher after checking its original identity and parent again.
                if child.poll() is None:
                    root_entry = snapshot["root"]
                    if not _process_still_matches(root_entry):
                        identity_error = "popen_root_identity_changed_before_terminate"
                        manual_attention_required = True
                        termination_action = "process_tree_identity_unverified_no_further_signal"
                        break
                    try:
                        root_process = psutil.Process(child.pid)
                        if root_process.ppid() != os.getpid():
                            identity_error = "popen_root_parent_changed_before_terminate"
                            manual_attention_required = True
                            termination_action = "process_tree_identity_unverified_no_further_signal"
                            break
                        root_process.terminate()
                        actions.append({"pid": child.pid, "action": "terminate_popen_root"})
                        try:
                            child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            if not _process_still_matches(root_entry):
                                identity_error = "popen_root_identity_changed_before_kill"
                                manual_attention_required = True
                            else:
                                root_process.kill()
                                actions.append({"pid": child.pid, "action": "kill_popen_root_after_timeout"})
                                try:
                                    child.wait(timeout=3)
                                except subprocess.TimeoutExpired:
                                    manual_attention_required = True
                                    identity_error = "popen_root_still_running_after_kill"
                    except psutil.NoSuchProcess:
                        pass
                    except (psutil.AccessDenied, OSError) as exc:
                        identity_error = f"popen_root_terminate_denied:{type(exc).__name__}"
                        manual_attention_required = True
                    if not manual_attention_required:
                        termination_action = "verified_tree_descendants_then_root_terminated"
                break
            else:
                identity_error = "owned_descendants_kept_spawning_during_cleanup"
                manual_attention_required = True
                termination_action = "manual_attention_process_tree_kept_spawning"

        deduplicated_tree: dict[tuple[Any, Any], dict[str, Any]] = {}
        for entry in tree_evidence:
            deduplicated_tree[(entry.get("pid"), entry.get("create_time"))] = entry
        remaining_processes: list[dict[str, Any]] = []
        for entry in deduplicated_tree.values():
            if _process_still_matches(entry):
                remaining_processes.append(entry)
        if child.poll() is None:
            manual_attention_required = True
        return child.poll(), {
            "status": "TIMEOUT",
            "child_pid": child.pid,
            "child_return_code_after_timeout": child.poll(),
            "termination_action": termination_action,
            "signals_sent": actions,
            "owned_processes_observed": sorted(
                deduplicated_tree.values(), key=lambda value: (value["pid"], value["create_time"])
            )[:32],
            "owned_processes_still_running": remaining_processes[:32],
            "identity_error": identity_error,
            "manual_attention_required": manual_attention_required,
        }


def _phase_receipt_rejection(
    phase_receipt: Mapping[str, Any],
    *,
    phase: str,
    expected_pid: int,
    return_code: int | None,
    venv_redirector_verified: bool = False,
    expected_executable: str | None = None,
) -> dict[str, Any] | None:
    """Keep child identity strict without hiding its original phase failure."""

    actual_pid = phase_receipt.get("process_id")
    actual_parent_pid = phase_receipt.get("parent_process_id")
    actual_executable = phase_receipt.get("runtime_executable")
    status = phase_receipt.get("status")
    raw_error = phase_receipt.get("error")
    inner_error = (
        str(raw_error)[:800]
        if isinstance(raw_error, str) and raw_error
        else None
    )
    reasons: list[str] = []
    direct_pid_match = type(actual_pid) is int and actual_pid == expected_pid
    expected_exe_key = (
        os.path.normcase(os.path.normpath(expected_executable))
        if isinstance(expected_executable, str)
        else None
    )
    actual_exe_key = (
        os.path.normcase(os.path.normpath(actual_executable))
        if isinstance(actual_executable, str)
        else None
    )
    verified_redirector_child = (
        venv_redirector_verified
        and type(actual_pid) is int
        and actual_pid > 0
        and actual_pid != expected_pid
        and type(actual_parent_pid) is int
        and actual_parent_pid == expected_pid
        and expected_exe_key is not None
        and actual_exe_key == expected_exe_key
    )
    if not (direct_pid_match or verified_redirector_child):
        reasons.append("phase_receipt_pid_mismatch")
    if status != "PASS":
        reasons.append("phase_receipt_not_pass")
    if return_code != 0:
        reasons.append("child_return_code_nonzero")
    if not reasons:
        return None
    return {
        "schema_version": "native-personal-model-child-failure.v1",
        "phase": phase,
        "rejection_reasons": reasons,
        "receipt_status": _diagnostic_scalar(status),
        "receipt_process_id": _diagnostic_scalar(actual_pid),
        "receipt_parent_process_id": _diagnostic_scalar(actual_parent_pid),
        "receipt_runtime_executable": _diagnostic_scalar(actual_executable),
        "expected_process_id": expected_pid,
        "process_identity_rule": (
            "direct_popen_pid"
            if direct_pid_match
            else "verified_windows_venv_redirector_parent_and_executable"
            if verified_redirector_child
            else "unverified"
        ),
        "venv_redirector_verified": venv_redirector_verified,
        "child_return_code": return_code,
        "child_error": inner_error,
    }


def _is_windows_venv_redirector(executable: str | Path) -> bool:
    """Verify the Popen executable is the expected Windows venv Scripts launcher."""

    if os.name != "nt":
        return False
    try:
        resolved = Path(executable).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if resolved.name.casefold() not in {"python.exe", "pythonw.exe"}:
        return False
    scripts_dir = resolved.parent
    pyvenv_cfg = scripts_dir.parent / "pyvenv.cfg"
    return scripts_dir.name.casefold() == "scripts" and pyvenv_cfg.is_file()


def _verify_db_identity_against_policy(run_root: Path, layout: Any) -> dict[str, Any]:
    from app_module.recommendation.personal_use_policy import (
        load_personal_use_policy_snapshot,
    )

    config, db_path = _runtime_config(run_root, layout)
    policy = load_personal_use_policy_snapshot(layout.policy_config_path)
    if getattr(policy, "mode", None) != "personal_calibrated_probability":
        raise AcceptanceError("模型 phase 起始時 policy 非 calibrated V2")
    trust = getattr(policy, "source_time_trust", None)
    if trust is None or Path(trust.source_database_path).resolve(strict=True) != db_path:
        raise AcceptanceError("模型 phase 起始 policy 未綁定 runtime DB")
    return _verify_saved_policy_source(
        run_root=run_root,
        layout=layout,
        config=config,
        db_path=db_path,
    )


def _run_ui_phase(run_id: str, phase: str) -> int:
    if os.name != "nt":
        raise AcceptanceError("真實 PySide6 MainWindow 控件驗收僅支援 Windows")
    run_root, layout, _manifest, _verified = _verify_prepared_workspace(run_id)
    env = _configure_child_environment(layout)
    for key in tuple(os.environ):
        if key in isolated_launcher._ISOLATED_ARTIFACT_ENV or key.startswith(
            ("FORMAL_DAILY_", "PIT_SECTOR_", "PIT_MEMBERSHIP_")
        ):
            os.environ.pop(key, None)
    os.environ.update(env)
    if phase == "activate":
        if layout.policy_config_path.exists():
            raise AcceptanceError("activate phase 要求全新且尚無 policy 的 run")
    else:
        _read_saved_state(layout.receipts_dir / "personal_model_activation_state.json")
        _verify_db_identity_against_policy(run_root, layout)

    from PySide6.QtWidgets import QApplication

    from ui_qt.main import MainWindow, _drain_qt_deferred_deletes, apply_app_theme

    app = QApplication([str(Path(__file__).resolve()), "--internal-phase", phase])
    app.setOrganizationName("TechnicalAnalysis")
    app.setApplicationName("TechnicalAnalysis-PersonalModelQA")
    apply_app_theme(app)
    window = MainWindow(policy_config_path=layout.policy_config_path)
    window.setWindowTitle(f"個人模型隔離 QA｜{phase}｜{run_id}")
    if not isolated_launcher._same_path(
        Path(window.recommendation_view.config.db_file).resolve(strict=True),
        layout.working_db_path.resolve(strict=True),
    ):
        raise AcceptanceError("MainWindow RecommendationView config DB 路徑錯誤")
    isolated_launcher._verify_test_profile_config(
        window.recommendation_view.config, layout
    )
    window.show()
    driver = _PersonalModelJourneyDriver(
        app=app,
        window=window,
        phase=phase,
        run_id=run_id,
        run_root=run_root,
    )
    exit_code = driver.run()
    driver._visible_window_at_exit = bool(window.isVisible())
    _drain_qt_deferred_deletes(app, (window,))
    receipt_path = driver.receipt_path
    _write_json_create_only(receipt_path, driver.receipt())
    if exit_code != 0 or driver.status != "PASS":
        print(f"phase receipt: {receipt_path}", file=sys.stderr)
        return exit_code or 2
    print(f"phase receipt: {receipt_path}")
    return 0


def _run_child_process(run_id: str, phase: str) -> dict[str, Any]:
    run_root, layout, _manifest, _verified = _verify_prepared_workspace(run_id)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_internal-phase",
        "--run-id",
        run_id,
        "--phase",
        phase,
    ]
    stdout_path = layout.receipts_dir / f"personal_model_{phase}.stdout.log"
    stderr_path = layout.receipts_dir / f"personal_model_{phase}.stderr.log"
    for path in (stdout_path, stderr_path):
        if path.exists():
            raise AcceptanceError(f"phase evidence 已存在，拒絕覆寫：{path}")
    env = _configure_child_environment(layout)
    expected_executable = str(Path(sys.executable).resolve(strict=True))
    venv_redirector_verified = _is_windows_venv_redirector(expected_executable)
    started_at = datetime.now(timezone.utc).isoformat()
    timeout_evidence: dict[str, Any] | None = None
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        child = subprocess.Popen(
            command,
            cwd=REPOSITORY_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            close_fds=True,
        )
        return_code, timeout_state = _wait_for_owned_child(
            child, timeout_seconds=MAX_PHASE_SECONDS
        )
        if timeout_state is not None:
            timeout_evidence = {
                "schema_version": "native-personal-model-timeout.v1",
                "phase": phase,
                "run_id": run_id,
                **timeout_state,
                "started_at_utc": started_at,
                "timed_out_at_utc": datetime.now(timezone.utc).isoformat(),
                "command_argv": command,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
    if timeout_evidence is not None:
        timeout_evidence.update(
            {
                "stdout_sha256": isolated_launcher._sha256_regular_file(stdout_path)[0],
                "stderr_sha256": isolated_launcher._sha256_regular_file(stderr_path)[0],
            }
        )
        timeout_path = layout.receipts_dir / f"personal_model_{phase}.timeout.json"
        _write_json_create_only(timeout_path, timeout_evidence)
        raise AcceptanceError(
            f"{phase} phase 超時；已記錄本 runner 核身的 process-tree 收尾結果與 manual-attention 狀態，證據保留於 {timeout_path}"
        )
    phase_receipt_path = layout.receipts_dir / f"personal_model_{phase}.json"
    phase_receipt = _read_json_regular(phase_receipt_path, max_bytes=8 * 1024 * 1024)
    child_failure = _phase_receipt_rejection(
        phase_receipt,
        phase=phase,
        expected_pid=child.pid,
        return_code=return_code,
        venv_redirector_verified=venv_redirector_verified,
        expected_executable=expected_executable,
    )
    if child_failure is not None:
        summary = json.dumps(
            child_failure,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        raise AcceptanceError(
            f"{phase} phase 未 PASS；child receipt/log 已保留：{summary}",
            diagnostic={"child_failure": child_failure},
        )
    return {
        "phase": phase,
        "command_argv": command,
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_id": child.pid,
        "venv_redirector_verified": venv_redirector_verified,
        "phase_runtime_process_id": phase_receipt.get("process_id"),
        "phase_runtime_parent_process_id": phase_receipt.get("parent_process_id"),
        "return_code": return_code,
        "stdout_path": str(stdout_path.resolve(strict=True)),
        "stdout_sha256": isolated_launcher._sha256_regular_file(stdout_path)[0],
        "stderr_path": str(stderr_path.resolve(strict=True)),
        "stderr_sha256": isolated_launcher._sha256_regular_file(stderr_path)[0],
        "phase_receipt_path": str(phase_receipt_path.resolve(strict=True)),
        "phase_receipt_sha256": isolated_launcher._sha256_regular_file(phase_receipt_path)[0],
        "phase_receipt": phase_receipt,
    }


def preflight_workspace(run_id: str) -> dict[str, Any]:
    run_root, layout, manifest, verified = _verify_prepared_workspace(run_id)
    config, db_path = _runtime_config(run_root, layout)
    policy_exists = layout.policy_config_path.exists()
    if policy_exists:
        raise AcceptanceError("新模型驗收 run 必須以空 policy path 開始")
    return {
        "schema_version": "native-personal-model-preflight.v1",
        "status": "READY_FOR_REVIEWED_QT_WIDGET_RUN",
        "run_id": run_id,
        "run_root": str(run_root.resolve(strict=True)),
        "profile": config.profile,
        "data_root": str(Path(config.data_root).resolve(strict=True)),
        "output_root": str(Path(config.output_root).resolve(strict=True)),
        "runtime_db_path": str(db_path),
        "runtime_db_identity": isolated_launcher._identity(db_path.stat()),
        "policy_path": str(layout.policy_config_path.resolve(strict=False)),
        "policy_exists": policy_exists,
        "snapshot_sha256": manifest["source_snapshot"]["sha256"],
        "working_db_sha256": manifest["working_copy"]["working_sha256"],
        "candidate": verified["candidate_pin"],
        "learning_tree_sha256": verified["learning_pin"]["tree_pin"]["tree_sha256"],
        "formal_database_opened": False,
        "qt_started": False,
        "source_time_replayed": False,
    }


def run_acceptance(run_id: str) -> dict[str, Any]:
    run_root, layout, _manifest, verified_before = _verify_prepared_workspace(run_id)
    learning_pin_before = dict(verified_before["learning_pin"])
    if layout.policy_config_path.exists():
        raise AcceptanceError("acceptance 要求新的 run-local policy，不沿用舊 pc-e2e 設定")
    phases = [
        _run_child_process(run_id, "activate"),
        _run_child_process(run_id, "restart_disable_rollback"),
    ]
    _after_run_root, _after_layout, _after_manifest, verified_after = (
        _verify_prepared_workspace(run_id)
    )
    learning_pin_after = dict(verified_after["learning_pin"])
    _require_same_learning_tree_pin(learning_pin_before, learning_pin_after)
    final_policy_path = layout.policy_config_path
    from app_module.recommendation.personal_use_policy import (
        RecommendationPersonalUsePolicyV2,
        load_personal_use_policy_snapshot,
    )

    final_policy = load_personal_use_policy_snapshot(final_policy_path)
    if (
        type(final_policy) is not RecommendationPersonalUsePolicyV2
        or final_policy.mode != "rule_only"
        or final_policy.candidate is not None
        or final_policy.source_time_trust is not None
    ):
        raise AcceptanceError("最終 policy 未回到 V2 rule_only 並清除候選/trust")
    candidate_pin_after = _verify_candidate_bundle()
    for phase in phases:
        if (
            candidate_pin_after["candidate_file_sha256"]
            != phase["phase_receipt"].get("candidate_file_sha256")
            or phase["phase_receipt"].get("lineage_sha256") != LINEAGE_SHA256
        ):
            raise AcceptanceError("候選檔案或 lineage 在 UI 旅程期間改變")
    receipt = {
        "schema_version": "native-personal-model-acceptance.v1",
        "run_id": run_id,
        "status": "PASS_QT_WIDGET_PERSONAL_MODEL_JOURNEY",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_root": str(run_root.resolve(strict=True)),
        "working_db_path": str(layout.working_db_path.resolve(strict=True)),
        "policy_path": str(final_policy_path.resolve(strict=True)),
        "final_policy_revision": final_policy.revision,
        "final_policy_sha256": final_policy.policy_sha256,
        "final_policy_mode": final_policy.mode,
        "candidate": candidate_pin_after,
        "learning_root_read_only_pin_before": learning_pin_before,
        "learning_root_read_only_pin_after": learning_pin_after,
        "learning_root_unchanged": True,
        "phases": phases,
        "formal_database_written": False,
        "global_pointer_touched": False,
        "candidate_learning_root_written": False,
        "scheduler_started": False,
        "http_requested": False,
        "screenshots_required": False,
        "os_foreground_or_screen_capture_verified": False,
        "limitations": [
            "個人來源時間是 user-declared、research-only，不是官方 historical PIT 證明。",
            "此流程只驗固定 QA snapshot 複本與該 QA candidate，不驗正式 DB 或 global model promotion。",
            "QScreen screenshot identity 不作為本業務 journey 的前置條件。",
            "畫面附件若存在，是 QWidget.grab() widget render，不是 OS foreground 或 desktop screenshot 證據。",
        ],
    }
    final_receipt_path = layout.receipts_dir / "personal_model_acceptance.json"
    _write_json_create_only(final_receipt_path, receipt)
    receipt["receipt_path"] = str(final_receipt_path.resolve(strict=True))
    receipt["receipt_sha256"] = isolated_launcher._sha256_regular_file(final_receipt_path)[0]
    return receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以真實 MainWindow 控件與 widget automation 驗證 fixed QA personal candidate；不宣稱 OS 桌面或前景視窗證據。"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser(
        "preflight", help="唯讀驗證已準備的 run/snapshot/candidate；不啟 Qt 或讀行情 rows"
    )
    preflight.add_argument("--run-id", required=True)
    acceptance = commands.add_parser(
        "accept", help="明確啟動兩個真 MainWindow widget-automation phase；只寫隔離 run root"
    )
    acceptance.add_argument("--run-id", required=True)
    acceptance.add_argument(
        "--confirm-qt-model-run",
        action="store_true",
        help="確認執行隔離的 Qt MainWindow 控件旅程；不代表 OS foreground/screenshot 驗證",
    )
    internal = commands.add_parser("_internal-phase", help=argparse.SUPPRESS)
    internal.add_argument("--run-id", required=True)
    internal.add_argument("--phase", required=True, choices=("activate", "restart_disable_rollback"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            print(json.dumps(preflight_workspace(args.run_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "accept":
            if not args.confirm_qt_model_run:
                raise AcceptanceError("accept 需明確帶 --confirm-qt-model-run")
            result = run_acceptance(args.run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "_internal-phase":
            return _run_ui_phase(args.run_id, args.phase)
    except (AcceptanceError, OSError, RuntimeError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
