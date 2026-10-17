"""初次設定須拒絕不完整包，重開與移位不得重設使用者狀態。"""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module import trial_first_setup as setup


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "package with spaces"
    root.mkdir()
    entries = {}
    for prefix, name in (("app", "baldr.exe"), ("assets/market", "sqlite/twstock.db"),
                         ("assets/fundamental", "manifest.json")):
        path = root / prefix / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen-original")
        entries[prefix] = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                            "sha256": sha256(path.read_bytes()).hexdigest()}]
    for name in ("research", "technical"):
        (root / "assets" / name).mkdir()
    fundamental_receipt = root / "assets/fundamental/receipt.json"
    fundamental_receipt.write_bytes(b"fixed-fundamental-receipt")
    entries["assets/fundamental"].append({"path": "assets/fundamental/receipt.json",
        "bytes": fundamental_receipt.stat().st_size, "sha256": sha256(fundamental_receipt.read_bytes()).hexdigest()})
    watchlist = root / "assets/source_watchlist.json"
    watchlist.write_bytes(b'{"items":[]}')
    value = {"schema": setup.SCHEMA, "scope": "fresh_trial_only", "private_state_included": False,
        "runtime_files": entries["app"], "market_files": entries["assets/market"],
        "fundamental_files": entries["assets/fundamental"], "bookmark_ids": ["1" * 64],
        "research_receipt_sha256": "2" * 64, "technical_receipt_sha256": "3" * 64,
        "watchlist_sha256": sha256(watchlist.read_bytes()).hexdigest(),
        "fundamental_manifest_sha256": entries["assets/fundamental"][0]["sha256"],
        "fundamental_receipt_sha256": entries["assets/fundamental"][1]["sha256"]}
    manifest = root / "TRIAL_PACKAGE.json"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    return root, sha256(manifest.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", ["wrong_sha", "changed", "extra", "escape", "private", "existing", "fundamental_pin"])
def test_unsafe_or_incomplete_package_does_not_create_or_reset_state(package, problem):
    root, digest = package
    manifest = root / "TRIAL_PACKAGE.json"
    if problem == "wrong_sha":
        digest = "0" * 64
    elif problem == "changed":
        (root / "assets/market/sqlite/twstock.db").write_bytes(b"modified")
    elif problem == "extra":
        (root / "app/extra.dll").write_bytes(b"unexpected")
    elif problem in {"escape", "private", "fundamental_pin"}:
        body = json.loads(manifest.read_bytes())
        if problem == "escape":
            body["market_files"][0]["path"] = "assets/market/../../outside.db"
        elif problem == "private":
            body["private_state_included"] = True
        else:
            body["fundamental_manifest_sha256"] = "0" * 64
        manifest.write_text(json.dumps(body), encoding="utf-8")
        digest = sha256(manifest.read_bytes()).hexdigest()
    else:
        (root / "state").mkdir()
        (root / "state/user-research.json").write_bytes(b"keep-user-data")
    with pytest.raises(ValueError):
        setup.prepare_trial_package(root, digest)
    if problem == "existing":
        assert (root / "state/user-research.json").read_bytes() == b"keep-user-data"
        assert list((root / "state").iterdir()) == [root / "state/user-research.json"]
    else:
        assert not (root / "state").exists()


def _fake_copiers(monkeypatch, *, fail=False):
    calls = []
    def research(source, digest, target, **kwargs):
        calls.append("research")
        target.mkdir()
        if fail:
            raise ValueError("source incomplete")
        path = target / "RESEARCH_COPY_RECEIPT.json"
        path.write_bytes(b"research proof")
        return path
    def technical(source, digest, target, **kwargs):
        calls.append("technical")
        target.mkdir()
        (target / "TECHNICAL_COPY_RECEIPT.json").write_bytes(b"technical proof")
        return SimpleNamespace(store_output_root=target / "live/universe")
    def bookmarks(source, digest, technical, technical_sha, target, **kwargs):
        calls.append("bookmarks")
        (target / "watchlist").mkdir(parents=True)
        (target / "watchlist/default.json").write_bytes(b"original values, new IDs")
        receipt = target / "BOOKMARK_COPY_RECEIPT.json"
        receipt.write_bytes(b"bookmark proof")
        return receipt
    monkeypatch.setattr(setup, "restore_research_output", research)
    monkeypatch.setattr(setup, "restore_technical_source", technical)
    monkeypatch.setattr(setup, "copy_price_bookmarks", bookmarks)
    return calls


def test_same_root_reopen_preserves_user_writes_and_moved_state_is_refused(package, monkeypatch):
    root, digest = package
    calls = _fake_copiers(monkeypatch)
    receipt = setup.prepare_trial_package(root, digest)
    assert calls == ["research", "technical", "bookmarks"]
    before = receipt.read_bytes()
    user = root / "state/output/user-research.json"
    user.write_bytes(b"saved after setup")
    monkeypatch.setenv("DATA_ROOT", str(root / "state/market"))
    assert setup.prepare_trial_package(root, digest) == receipt
    assert user.read_bytes() == b"saved after setup" and receipt.read_bytes() == before
    assert len(calls) == 3
    moved = root.with_name("moved after use")
    root.rename(moved)
    with pytest.raises(setup.TrialSetupError, match="位置"):
        setup.prepare_trial_package(moved, digest)
    assert (moved / "state/output/user-research.json").read_bytes() == b"saved after setup"


def test_failed_setup_keeps_pending_and_never_publishes_config(package, monkeypatch):
    root, digest = package
    _fake_copiers(monkeypatch, fail=True)
    with pytest.raises(ValueError, match="incomplete"):
        setup.prepare_trial_package(root, digest)
    assert (root / "state/TRIAL_SETUP_PENDING.json").is_file()
    assert (root / "state/TRIAL_SETUP_FAILURE.json").is_file()
    assert not (root / "state/config.json").exists()
    with pytest.raises(ValueError, match="不覆寫"):
        setup.prepare_trial_package(root, digest)


def test_protected_target_and_cancel_are_read_only(package, monkeypatch):
    root, digest = package
    monkeypatch.setenv("PERSONAL_DATA_ROOT", str(root))
    with pytest.raises(ValueError, match="私人"):
        setup.prepare_trial_package(root, digest)
    monkeypatch.delenv("PERSONAL_DATA_ROOT")
    with pytest.raises(ValueError, match="cancelled"):
        setup.prepare_trial_package(root, digest, check_cancel=lambda: True)
    assert not (root / "state").exists()
