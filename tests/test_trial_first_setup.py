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
        return SimpleNamespace(store_output_root=target / "live/universe"), object()
    def bookmarks(source, digest, technical, technical_sha, target, **kwargs):
        calls.append("bookmarks")
        (target / "watchlist").mkdir(parents=True)
        (target / "watchlist/default.json").write_bytes(b"original values, new IDs")
        receipt = target / "BOOKMARK_COPY_RECEIPT.json"
        receipt.write_bytes(b"bookmark proof")
        return receipt
    monkeypatch.setattr(setup, "restore_research_output", research)
    monkeypatch.setattr(setup, "restore_technical_source_with_price_session", technical)
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


def _add_monthly(package):
    root, _ = package
    directory = root / "assets/quanta-monthly"
    directory.mkdir()
    names = ("monthly.raw", "monthly-http.json", "twse-company.raw.json", "identity-publication.json",
             "identity-receipt.json", "identity-archive.json", "manifest.json", "receipt.json")
    originals, entries = {}, []
    for name in names:
        raw = ("immutable " + name).encode()
        (directory / name).write_bytes(raw)
        originals[name] = raw
        entries.append({"path": "assets/quanta-monthly/" + name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
    manifest = root / "TRIAL_PACKAGE.json"
    body = json.loads(manifest.read_bytes())
    body["schema"] = setup.EXTENDED_SCHEMA
    body["quanta_monthly_sales"] = {"files": entries,
        "manifest_sha256": sha256(originals["manifest.json"]).hexdigest(),
        "receipt_sha256": sha256(originals["receipt.json"]).hexdigest()}
    manifest.write_text(json.dumps(body), encoding="utf-8")
    return root, sha256(manifest.read_bytes()).hexdigest(), originals


@pytest.mark.parametrize("frozen", [False, True])
def test_optional_monthly_copies_all_original_bytes_and_allows_normal_boot(package, monkeypatch, frozen):
    root, digest, originals = _add_monthly(package)
    calls = _fake_copiers(monkeypatch)
    receipt = setup.prepare_trial_package(root, digest)
    assert calls == ["research", "technical", "bookmarks"]
    copied = root / "state/monthly-sales-version"
    assert {path.name: path.read_bytes() for path in copied.iterdir()} == originals
    config = json.loads((root / "state/config.json").read_bytes())
    assert not any(key.startswith("QUANTA_MONTHLY_SALES_") for key in config)
    # 專用provider由啟動器明選環境；config只保留共同啟動器接受的契約。
    from app_module.application_bootstrap import resolve_application_settings
    (root / "state/technical-source/live/universe").mkdir(parents=True)
    resolved = resolve_application_settings(environ={"LOCALAPPDATA": str(root / "local"),
        "BALDR_CONFIG": str(root / "state/config.json")}, resource_root=root / "app/_internal", frozen=frozen)
    assert resolved.configured and resolved.environment["DATA_ROOT"] == str(root / "state/market")
    assert resolved.environment["OUTPUT_ROOT"] == str(root / "state/output")
    proof = json.loads(receipt.read_bytes())
    assert proof["quanta_monthly_sales_verification"] == "copied_bytes_verified_not_source_acceptance"
    before = receipt.read_bytes()
    user = root / "state/output/user-research.json"
    user.write_bytes(b"saved after setup")
    assert setup.prepare_trial_package(root, digest) == receipt
    assert receipt.read_bytes() == before and user.read_bytes() == b"saved after setup"
    assert len(calls) == 3


@pytest.mark.parametrize("problem", ["partial", "null", "wrong_manifest", "wrong_receipt", "changed", "extra", "escape", "undeclared"])
def test_invalid_optional_monthly_never_creates_state(package, problem):
    root, digest, _ = _add_monthly(package)
    manifest = root / "TRIAL_PACKAGE.json"
    body = json.loads(manifest.read_bytes())
    binding = body["quanta_monthly_sales"]
    if problem == "partial":
        del binding["receipt_sha256"]
    elif problem == "null":
        body["quanta_monthly_sales"] = None
    elif problem == "wrong_manifest":
        binding["manifest_sha256"] = "0" * 64
    elif problem == "wrong_receipt":
        binding["receipt_sha256"] = "0" * 64
    elif problem == "changed":
        (root / "assets/quanta-monthly/monthly.raw").write_bytes(b"changed")
    elif problem == "extra":
        (root / "assets/quanta-monthly/extra.raw").write_bytes(b"unlisted")
    elif problem == "escape":
        binding["files"][0]["path"] = "assets/quanta-monthly/../../outside.raw"
    else:
        del body["quanta_monthly_sales"]
    manifest.write_text(json.dumps(body), encoding="utf-8")
    digest = sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        setup.prepare_trial_package(root, digest)
    assert not (root / "state").exists()


@pytest.mark.parametrize("destination", [False, True])
def test_late_monthly_mutation_keeps_failure_and_does_not_publish_config(package, monkeypatch, destination):
    root, digest, _ = _add_monthly(package)
    _fake_copiers(monkeypatch)
    original = setup.restore_technical_source_with_price_session
    def technical(*args, **kwargs):
        result = original(*args, **kwargs)
        parent = "state/monthly-sales-version" if destination else "assets/quanta-monthly"
        (root / parent / "monthly.raw").write_bytes(b"changed during setup")
        return result
    monkeypatch.setattr(setup, "restore_technical_source_with_price_session", technical)
    with pytest.raises(ValueError, match="變更"):
        setup.prepare_trial_package(root, digest)
    assert (root / "state/TRIAL_SETUP_PENDING.json").is_file()
    assert (root / "state/TRIAL_SETUP_FAILURE.json").is_file()
    assert not (root / "state/TRIAL_SETUP_RECEIPT.json").exists()
    assert not (root / "state/config.json").exists()


@pytest.mark.parametrize("data_root", ["", "isolated-qa"])
def test_default_formal_target_remains_protected_without_touching_it(monkeypatch, tmp_path, data_root):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / data_root) if data_root else "")
    with pytest.raises(setup.TrialSetupError, match="正式"):
        setup._reject_protected_target(Path("D:/Min/Python/Project/FA_Data/trial/state").absolute())


def test_fixed_regime_history_is_preserved_without_private_output_import(package, monkeypatch):
    root, _ = package
    path = root / "assets/market-regime/regime_history.json"
    path.parent.mkdir()
    raw = b'{"observations":["original history"]}'
    path.write_bytes(raw)
    manifest = root / "TRIAL_PACKAGE.json"
    body = json.loads(manifest.read_bytes())
    body["schema"] = setup.EXTENDED_SCHEMA
    body["market_regime_files"] = [{"path": "assets/market-regime/regime_history.json", "bytes": len(raw),
                                   "sha256": sha256(raw).hexdigest()}]
    manifest.write_text(json.dumps(body), encoding="utf-8")
    _fake_copiers(monkeypatch)
    setup.prepare_trial_package(root, sha256(manifest.read_bytes()).hexdigest())
    assert (root / "state/output/regime_history.json").read_bytes() == raw
    assert not (root / "state/output/private-account.json").exists()


def test_regime_family_cannot_import_other_output_files(package):
    root, _ = package
    path = root / "assets/market-regime/private-account.json"
    path.parent.mkdir()
    raw = b"not authorized"
    path.write_bytes(raw)
    manifest = root / "TRIAL_PACKAGE.json"
    body = json.loads(manifest.read_bytes())
    body["schema"] = setup.EXTENDED_SCHEMA
    body["market_regime_files"] = [{"path": "assets/market-regime/private-account.json", "bytes": len(raw),
                                   "sha256": sha256(raw).hexdigest()}]
    manifest.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(setup.TrialSetupError, match="僅接受"):
        setup.prepare_trial_package(root, sha256(manifest.read_bytes()).hexdigest())
    assert not (root / "state").exists()


def test_extended_family_cannot_hide_in_legacy_v1_manifest(package):
    root, _, _ = _add_monthly(package)
    manifest = root / "TRIAL_PACKAGE.json"
    body = json.loads(manifest.read_bytes())
    body["schema"] = setup.SCHEMA
    manifest.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(setup.TrialSetupError, match="須使用v2"):
        setup.prepare_trial_package(root, sha256(manifest.read_bytes()).hexdigest())
    assert not (root / "state").exists()
