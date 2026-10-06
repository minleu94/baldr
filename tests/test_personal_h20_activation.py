"""明示配置 CAS／預覽／回滾；只用隔離合成檔，不操作 Task／模型。"""
from dataclasses import replace
import hashlib
import os
from pathlib import Path

import pytest

from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation, publish_personal_h20_activation, read_personal_h20_activation,
)


def _activation(tmp_path: Path) -> PersonalH20Activation:
    return PersonalH20Activation(1, True, "personal.default", str(tmp_path / "market"),
        str(tmp_path / "private"), str(tmp_path / "fit.json"), "sha256:" + "a" * 64,
        "candidate", "model", "sha256:" + "b" * 64, "2014-01-01")


def test_preview_has_no_io_or_effective_model_claim(tmp_path):
    activation = _activation(tmp_path)
    result = publish_personal_h20_activation(activation, expected_revision=0)
    assert result["status"] == "preview"
    assert result["effective_model_run"] is False
    assert result["task_modified"] is False
    assert not Path(activation.personal_root).exists()


def test_selected_market_personal_model_subtree_publishes_without_market_writes(tmp_path):
    market = tmp_path / "market"
    market.mkdir()
    sentinel = market / "sqlite" / "source.sqlite"
    sentinel.parent.mkdir()
    sentinel.write_bytes(b"original-market-sentinel")
    before = sentinel.stat()
    activation = replace(_activation(tmp_path), personal_root=str(market / "personal" / "recommendation_h20"))
    preview = publish_personal_h20_activation(activation, expected_revision=0)
    assert preview["status"] == "preview"
    assert not Path(activation.personal_root).exists()
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    assert read_personal_h20_activation(activation.config_path) == activation
    rollback = replace(activation, revision=2, enabled=False)
    publish_personal_h20_activation(rollback, expected_revision=1, execute=True)
    assert read_personal_h20_activation(activation.config_path) == rollback
    assert sentinel.read_bytes() == b"original-market-sentinel"
    assert sentinel.stat().st_mtime_ns == before.st_mtime_ns
    for root in (market, market / "sqlite" / "recommendation_h20", market / "personal" / "other-domain"):
        with pytest.raises(ValueError):
            replace(activation, personal_root=str(root))


def test_publication_cas_and_disable_preserve_original_revision(tmp_path):
    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    original_path = next(Path(activation.personal_root).glob("activation.revision-1.*.json"))
    original = original_path.read_bytes()
    digest = "sha256:" + hashlib.sha256(activation.config_path.read_bytes()).hexdigest()
    assert read_personal_h20_activation(activation.config_path, expected_sha256=digest) == activation
    with pytest.raises(ValueError, match="revision_conflict"):
        publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    rollback = replace(activation, enabled=False, revision=2)
    publish_personal_h20_activation(rollback, expected_revision=1, execute=True)
    assert read_personal_h20_activation(activation.config_path) == rollback
    assert original_path.read_bytes() == original


def test_rollback_cli_does_not_require_original_fit_artifact(tmp_path, monkeypatch):
    from scripts import prepare_personal_h20_activation as cli

    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    monkeypatch.setattr(cli, "prepare_contract", lambda *args, **kwargs: pytest.fail("rollback loaded fit"))
    assert cli.main(["--market-root", activation.market_root, "--personal-root", activation.personal_root,
                     "--scope-id", activation.scope_id, "--expected-revision", "1", "--disable", "--execute"]) == 0
    assert read_personal_h20_activation(activation.config_path).enabled is False


@pytest.mark.parametrize("mutation", ["market_overlap", "bool_revision", "nonbool_enabled", "wrong_hash"])
def test_activation_rejects_unbound_configuration(tmp_path, mutation):
    activation = _activation(tmp_path)
    change = {"market_overlap": {"personal_root": activation.market_root},
              "bool_revision": {"revision": True}, "nonbool_enabled": {"enabled": "true"},
              "wrong_hash": {"model_contract_hash": "unverified"}}[mutation]
    with pytest.raises(ValueError):
        replace(activation, **change)


def test_post_selection_hardlink_is_rejected_before_publication(tmp_path):
    activation = _activation(tmp_path)
    root = Path(activation.personal_root)
    root.mkdir()
    outside = tmp_path / "sentinel.json"
    outside.write_text("sentinel", encoding="utf-8")
    os.link(outside, activation.config_path)
    with pytest.raises(ValueError):
        publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    assert outside.read_text(encoding="utf-8") == "sentinel"


def test_unpublished_history_does_not_block_safe_disable_revision(tmp_path, monkeypatch):
    import app_module.recommendation.personal_h20_activation as module

    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    enabled2 = replace(activation, revision=2)
    with monkeypatch.context() as patch:
        def fail(*args):
            raise OSError("synthetic publication failure")
        patch.setattr(module.os, "replace", fail)
        with pytest.raises(OSError):
            publish_personal_h20_activation(enabled2, expected_revision=1, execute=True)
    assert read_personal_h20_activation(activation.config_path) == activation
    rollback = replace(activation, revision=2, enabled=False)
    publish_personal_h20_activation(rollback, expected_revision=1, execute=True)
    assert read_personal_h20_activation(activation.config_path) == rollback
    assert len(list(Path(activation.personal_root).glob("activation.revision-2.*.json"))) == 2
