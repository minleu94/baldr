"""整合既有恢復工具，為明選試用包建立一次性新根；不搬私人環境。"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Callable

from app_module.research_output_copy import (
    ResearchOutputCopyBudget, _cancel, _digest, _emit, _stamp, restore_research_output,
)
from app_module.recommendation_portfolio_calendar_artifact_v1 import _canonical_path
from app_module.technical_source_copy import restore_technical_source, copy_price_bookmarks, _tree_layout

SCHEMA = "baldr-trial-first-setup.v1"
_HASH = re.compile(r"[0-9a-f]{64}")
_BUDGET = ResearchOutputCopyBudget(256 * 1024**2, 4 * 1024**3, 100000, 391)


class TrialSetupError(ValueError):
    """缺件、身分不符或既有狀態未經搬移；保留原件。"""


def _json(path: Path, expected_sha: str, maximum: int = 4 * 1024**2) -> dict[str, Any]:
    if type(expected_sha) is not str or not _HASH.fullmatch(expected_sha):
        raise TrialSetupError("需要外部固定SHA")
    stamp = _stamp(path)
    if stamp[0] > maximum:
        raise TrialSetupError("試用清冊超限")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) != stamp[0] or _stamp(path) != stamp or sha256(raw).hexdigest() != expected_sha:
        raise TrialSetupError("試用清冊SHA不符或讀中改變")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TrialSetupError("試用清冊鍵重複")
            result[key] = value
        return result
    def invalid(value):
        raise TrialSetupError("試用清冊含非有限JSON常數：" + value)
    result = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(result, dict):
        raise TrialSetupError("試用清冊須為object")
    return result


def _member(root: Path, name: str) -> Path:
    if (type(name) is not str or not name or "\\" in name or ":" in name
            or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
            or PurePosixPath(name).as_posix() != name):
        raise TrialSetupError("試用清冊相對路徑不合法")
    return _canonical_path(root / name, "trial_package_member", allow_missing=False)


def _verify_files(root: Path, entries: Any, prefix: str, cancel) -> list[tuple[Path, str]]:
    if type(entries) is not list or not entries or len(entries) > _BUDGET.max_entries:
        raise TrialSetupError("試用檔案清冊缺失或超限")
    seen: set[str] = set()
    total = 0
    files = []
    for entry in entries:
        _cancel(cancel)
        if not isinstance(entry, dict):
            raise TrialSetupError("試用檔案清冊列格式錯誤")
        name, size, digest = entry.get("path"), entry.get("bytes"), entry.get("sha256")
        if (type(name) is not str or not name.startswith(prefix + "/") or name in seen
                or type(size) is not int or not 0 <= size <= _BUDGET.max_file_bytes
                or type(digest) is not str or not _HASH.fullmatch(digest)):
            raise TrialSetupError("試用檔案清冊範圍、大小或SHA不符")
        path = _member(root, name)
        total += size
        if total > _BUDGET.max_total_bytes or _stamp(path)[0] != size or _digest(path, cancel) != digest:
            raise TrialSetupError("試用原件SHA不符或總bytes超限")
        seen.add(name)
        files.append((path, digest))
    expected = {path.relative_to(root / prefix).as_posix(): _stamp(path)[0] for path, _ in files}
    if _tree_layout(root / prefix, _BUDGET.max_entries, cancel) != expected:
        raise TrialSetupError("試用原件完整集合不符")
    return files


def prepare_trial_package(package_directory: Path, manifest_sha256: str, *,
                          check_cancel: Callable[[], bool] | None = None) -> Path:
    """首次移位後設定；同根重開保留使用者寫入，既有state移位一律拒絕。"""
    root = _canonical_path(package_directory, "trial_package", allow_missing=False)
    manifest_path = _member(root, "TRIAL_PACKAGE.json")
    manifest = _json(manifest_path, manifest_sha256)
    if (manifest.get("schema") != SCHEMA or manifest.get("private_state_included") is not False
            or manifest.get("scope") != "fresh_trial_only"):
        raise TrialSetupError("只接受明選全新試用包，不接受私人環境")
    # 固定路徑不由清冊決定，避免把寫入導向正式或私人根。
    state = _canonical_path(root / "state", "trial_state", allow_missing=True)
    receipt = state / "TRIAL_SETUP_RECEIPT.json"
    config = state / "config.json"
    if os.path.lexists(state):
        if (not receipt.is_file() or any(os.path.lexists(state / name) for name in
                ("TRIAL_SETUP_PENDING.json", "TRIAL_SETUP_FAILURE.json"))):
            raise TrialSetupError("既有state未完成；保留原件，不覆寫或重設")
        proof = _json(receipt, _digest(receipt, check_cancel))
        if (proof.get("schema") != SCHEMA or proof.get("status") != "prepared_and_readers_verified"
                or proof.get("package_directory") != str(root) or proof.get("manifest_sha256") != manifest_sha256):
            raise TrialSetupError("已使用state的位置或身分不同；請依搬移清冊另作副本，不重設")
        if _digest(_member(state, "config.json"), check_cancel) != proof.get("config_sha256"):
            raise TrialSetupError("既有試用設定已改變；保留狀態供核對")
        return receipt
    for name in ("DATA_ROOT", "OUTPUT_ROOT", "PERSONAL_DATA_ROOT", "PERSONAL_STORE_ROOT", "PERSONAL_JOURNAL_ROOT"):
        value = os.environ.get(name, "D:/Min/Python/Project/FA_Data" if name == "DATA_ROOT" else "")
        if value:
            protected = Path(value).absolute()
            if state.is_relative_to(protected) or protected.is_relative_to(state):
                raise TrialSetupError("試用新根不得重疊正式／私人根")
    runtime_files = _verify_files(root, manifest.get("runtime_files"), "app", check_cancel)
    market = _verify_files(root, manifest.get("market_files"), "assets/market", check_cancel)
    fundamental = _verify_files(root, manifest.get("fundamental_files"), "assets/fundamental", check_cancel)
    if "app/baldr.exe" not in {path.relative_to(root).as_posix() for path, _ in runtime_files}:
        raise TrialSetupError("完整runtime缺baldr.exe")
    ids = manifest.get("bookmark_ids")
    if (type(ids) is not list or not ids or len(ids) > _BUDGET.max_runs
            or any(type(value) is not str or not _HASH.fullmatch(value) for value in ids)
            or len(set(ids)) != len(ids)):
        raise TrialSetupError("須明選價格收藏ID")
    for key in ("research_receipt_sha256", "technical_receipt_sha256", "watchlist_sha256",
                "fundamental_manifest_sha256", "fundamental_receipt_sha256"):
        if type(manifest.get(key)) is not str or not _HASH.fullmatch(manifest[key]):
            raise TrialSetupError("試用封存缺外部固定SHA：" + key)
    watchlist = _member(root, "assets/source_watchlist.json")
    if _digest(watchlist, check_cancel) != manifest["watchlist_sha256"]:
        raise TrialSetupError("試用原收藏SHA不符")
    for name, field in (("manifest.json", "fundamental_manifest_sha256"), ("receipt.json", "fundamental_receipt_sha256")):
        if _digest(_member(root, "assets/fundamental/" + name), check_cancel) != manifest[field]:
            raise TrialSetupError("試用基本面入口與原件SHA不符")
    research = _member(root, "assets/research")
    technical = _member(root, "assets/technical")
    _cancel(check_cancel)
    state.mkdir(exist_ok=False)
    pending = state / "TRIAL_SETUP_PENDING.json"
    _emit(pending, {"schema": SCHEMA, "manifest_sha256": manifest_sha256})
    try:
        for prefix, files in (("assets/market", market), ("assets/fundamental", fundamental)):
            directory = "market" if prefix.endswith("market") else "fundamental-version"
            for source, digest in files:
                _cancel(check_cancel)
                target = state / directory / source.relative_to(root / prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                _canonical_path(target, "trial_copy_target", allow_missing=True)
                if _digest(source, check_cancel, target) != digest:
                    raise TrialSetupError("試用資料在複製中變更")
        research_receipt = restore_research_output(research, manifest["research_receipt_sha256"],
            state / "output", budget=_BUDGET, check_cancel=check_cancel)
        pin = restore_technical_source(technical, manifest["technical_receipt_sha256"],
            state / "technical-source", budget=_BUDGET, cancel_callback=check_cancel)
        technical_receipt = state / "technical-source/TECHNICAL_COPY_RECEIPT.json"
        bookmark_receipt = copy_price_bookmarks(watchlist, manifest["watchlist_sha256"],
            technical_receipt.parent, _digest(technical_receipt, check_cancel), state / "bookmark-copy",
            bookmark_ids=ids, budget=_BUDGET, cancel_callback=check_cancel)
        new_watchlist = state / "output/watchlist/default.json"
        new_watchlist.parent.mkdir(exist_ok=False)
        _digest(state / "bookmark-copy/watchlist/default.json", check_cancel, new_watchlist)
        settings = {"DATA_ROOT": str(state / "market"), "OUTPUT_ROOT": str(state / "output"),
            "RESEARCH_STATE_ROOT": str(state / "registry"),
            "OFFICIAL_CALENDAR_CACHE_PATH": str(state / "calendar"),
            "TECHNICAL_UNIVERSE_READ_ROOT": str(pin.store_output_root)}
        _emit(config, settings)
        # 只在所有封存／原值reader通過後發行設定；原清冊與只讀資料再核一次。
        _json(manifest_path, manifest_sha256)
        for files in (runtime_files, market, fundamental):
            for source, digest in files:
                if _digest(source, check_cancel) != digest:
                    raise TrialSetupError("試用原件在設定中變更")
        _emit(receipt, {"schema": SCHEMA, "status": "prepared_and_readers_verified",
            "package_directory": str(root), "manifest_sha256": manifest_sha256,
            "config_sha256": _digest(config, check_cancel),
            "research_receipt_sha256": _digest(research_receipt, check_cancel),
            "technical_receipt_sha256": _digest(technical_receipt, check_cancel),
            "bookmark_receipt_sha256": _digest(bookmark_receipt, check_cancel),
            "financial_artifacts_reencoded": False, "private_state_imported": False,
            "existing_environment_migration_accepted": False, "full_gate_accepted": False})
        pending.unlink()
        return receipt
    except Exception as error:
        _emit(state / "TRIAL_SETUP_FAILURE.json", {"schema": SCHEMA, "reason": str(error)[:2048]})
        raise
