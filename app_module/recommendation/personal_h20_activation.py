"""個人 H20 gross 啟用描述；與全域概率／交易權限分開。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

from app_module.personal_data_paths import PersonalDataPaths, resolve_personal_data_paths, to_internal_io_path
from app_module.personal_store_selection import assert_personal_store_path
from app_module.recommendation.queries import _read_regular_file_no_follow

SCHEMA = "personal-current-observed-h20-activation.v1"
MAX_BYTES = 64 * 1024
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _activation_paths(market_root: str, model_root: str) -> PersonalDataPaths:
    """沿已授權 FA_Data/personal；僅模型專屬子樹可位於市場包內。"""
    market, private = Path(market_root), Path(model_root)
    if private.is_relative_to(market):
        if private != market / "personal" / "recommendation_h20":
            raise ValueError("activation_market_subtree_not_personal_h20")
        paths = resolve_personal_data_paths(market, personal_root=market / "personal", environ={})
        assert_personal_store_path(paths, private / "activation.json")
        return paths
    return resolve_personal_data_paths(market, personal_root=private, environ={})


@dataclass(frozen=True, slots=True)
class PersonalH20Activation:
    revision: int
    enabled: bool
    scope_id: str
    market_root: str
    personal_root: str
    fit_receipt: str
    fit_receipt_sha256: str
    candidate_id: str
    model_id: str
    model_contract_hash: str
    history_start_date: str
    schema_version: str = SCHEMA

    def __post_init__(self) -> None:
        from datetime import date

        if self.schema_version != SCHEMA or type(self.revision) is not int or self.revision < 1:
            raise ValueError("activation_revision_or_schema_invalid")
        if type(self.enabled) is not bool:
            raise ValueError("activation_enabled_must_be_bool")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", self.scope_id):
            raise ValueError("activation_scope_required")
        for field in (self.candidate_id, self.model_id):
            if not isinstance(field, str) or not field.strip() or len(field) > 200:
                raise ValueError("activation_model_identity_required")
        for field in (self.fit_receipt_sha256, self.model_contract_hash):
            if not _SHA.fullmatch(field):
                raise ValueError("activation_exact_hash_required")
        for field in (self.market_root, self.personal_root, self.fit_receipt):
            path = Path(field)
            if not path.is_absolute() or ".." in path.parts:
                raise ValueError("activation_absolute_path_required")
        date.fromisoformat(self.history_start_date)
        _activation_paths(self.market_root, self.personal_root)
        package = Path(__file__).resolve().parents[2]
        private = Path(self.personal_root)
        if private.is_relative_to(package) or package.is_relative_to(private):
            raise ValueError("activation_root_overlaps_application")

    @property
    def config_path(self) -> Path:
        return Path(self.personal_root) / "activation.json"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_personal_h20_activation(path: Path, *, expected_sha256: str | None = None) -> PersonalH20Activation:
    """不 mkdir、不 fallback；readback 綁 exact 私有根與原 bytes。"""
    if not path.is_absolute() or path.name != "activation.json" or ".." in path.parts:
        raise ValueError("activation_exact_path_required")
    raw = _read_regular_file_no_follow(path, path.parent, max_bytes=MAX_BYTES)
    if expected_sha256 is not None:
        if not _SHA.fullmatch(expected_sha256) or "sha256:" + hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("activation_raw_pin_mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("activation_object_required")
    activation = PersonalH20Activation(**payload)
    if activation.config_path != path:
        raise ValueError("activation_private_root_mismatch")
    paths = _activation_paths(activation.market_root, activation.personal_root)
    assert_personal_store_path(paths, path)
    return activation


def publish_personal_h20_activation(
    activation: PersonalH20Activation, *, expected_revision: int, execute: bool = False,
) -> dict[str, Any]:
    """預設只預覽；明示執行才發佈 CAS revision，回滾也是新 disabled revision。"""
    if type(expected_revision) is not int or expected_revision < 0 or activation.revision != expected_revision + 1:
        raise ValueError("activation_expected_revision_invalid")
    if type(execute) is not bool:
        raise ValueError("activation_execute_must_be_bool")
    raw = json.dumps(activation.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("activation_byte_limit")
    paths = _activation_paths(activation.market_root, activation.personal_root)
    config = activation.config_path
    assert_personal_store_path(paths, config)
    def current_revision() -> int:
        assert_personal_store_path(paths, config)
        if not Path(to_internal_io_path(config)).exists():
            return 0
        return read_personal_h20_activation(config).revision
    if current_revision() != expected_revision:
        raise ValueError("activation_revision_conflict")
    result = {"status": "preview", "proposed_activation": activation.to_dict(),
              "config_path": str(config), "task_modified": False, "model_loaded": False,
              "fit_performed": False, "effective_model_run": False}
    if not execute:
        return result
    paths.validate()
    Path(to_internal_io_path(activation.personal_root)).mkdir(parents=True, exist_ok=True)
    lock = config.with_suffix(".lock")
    assert_personal_store_path(paths, lock)
    fd = os.open(to_internal_io_path(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        if current_revision() != expected_revision:
            raise ValueError("activation_revision_conflict")
        history = config.with_name(f"activation.revision-{activation.revision}.{hashlib.sha256(raw).hexdigest()}.json")
        temporary = config.with_name(f"activation.{uuid.uuid4().hex}.tmp")
        for path in (history, temporary):
            assert_personal_store_path(paths, path)
            if path == history and Path(to_internal_io_path(path)).exists():
                if _read_regular_file_no_follow(path, path.parent, max_bytes=MAX_BYTES) != raw:
                    raise ValueError("activation_history_conflict")
                continue
            with open(to_internal_io_path(path), "xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        assert_personal_store_path(paths, config)
        assert_personal_store_path(paths, temporary)
        os.replace(to_internal_io_path(temporary), to_internal_io_path(config))
        actual = read_personal_h20_activation(config)
        if actual != activation:
            raise ValueError("activation_publication_readback_mismatch")
        result.update(status="configuration_published", revision=actual.revision)
        return result
    finally:
        os.close(fd)
        assert_personal_store_path(paths, lock)
        os.unlink(to_internal_io_path(lock))
